"""Run history and the learning signals derived from it.

Replaces the previous global JSON/Mongo store. Every query is scoped by
user_id: the old store keyed history only by story text, so one visitor's runs
fed another visitor's confidence scores and regression trends.

The signals here are computed from stored run rows only. Nothing is inferred,
padded, or defaulted into existence -- a story with no history reports zero
runs rather than a placeholder baseline.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import PipelineRun

# Trend classification threshold, in pass-rate points.
TREND_EPSILON = 0.05


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _normalize_signature(value: Any) -> str:
    text = _clean(value).lower()
    return "".join(ch for ch in text if ch.isalnum() or ch in {" ", "_", "-", ":"}).strip()


def build_story_identity(
    *,
    story_text: str | None = None,
    story_intent: str | None = None,
    modules: list[str] | None = None,
) -> tuple[str, str]:
    """Stable (key, label) for grouping runs that describe the same work."""
    source = _clean(story_text or story_intent or "")
    if not source:
        source = ", ".join(sorted(modules or [])) or "unknown story"

    digest = hashlib.sha256(source.lower().encode("utf-8")).hexdigest()[:24]
    return digest, source[:300]


def test_fingerprint(test: dict[str, Any]) -> str:
    basis = "|".join(
        _clean(test.get(field)).lower()
        for field in ("module", "type", "description", "expected_result")
    )
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]


def failure_signature(error_message: Any, status: str) -> str:
    """Condense a failure into a comparable signature.

    Prefers pytest's short-summary line, then the assertion text, then the last
    non-empty line, so the same defect recurring across runs hashes alike.
    """
    lines = [line.strip() for line in str(error_message or "").splitlines() if line.strip()]

    summary = next((line for line in lines if line.startswith("FAILED ") and " - " in line), "")
    if summary:
        return _normalize_signature(summary.split(" - ", 1)[1])

    assertion = next((line for line in lines if "AssertionError:" in line), "")
    if assertion:
        return _normalize_signature(assertion.split("AssertionError:", 1)[1])

    if lines:
        return _normalize_signature(lines[-1])
    return _normalize_signature(f"{status} without message")


def _run_test_catalog(run: PipelineRun) -> list[dict[str, Any]]:
    """Per-test records for a run, joined to their outcome."""
    tests = run.tests_result or []
    results = {
        _clean(item.get("test_id")): item
        for item in ((run.execution_result or {}).get("results") or [])
        if isinstance(item, dict)
    }

    catalog: list[dict[str, Any]] = []
    for test in tests:
        if not isinstance(test, dict):
            continue
        test_id = _clean(test.get("id"))
        result = results.get(test_id, {})
        catalog.append(
            {
                "id": test_id,
                "module": _clean(test.get("module")),
                "type": _clean(test.get("type")) or "functional",
                "description": _clean(test.get("description")),
                "expected_result": _clean(test.get("expected_result")),
                "fingerprint": test_fingerprint(test),
                "learning_source": _clean(test.get("learning_source")) or "baseline",
                "derived_from_failure_signature": _normalize_signature(
                    test.get("derived_from_failure_signature")
                ),
                "result_status": _clean(result.get("status")) or "not_executed",
            }
        )
    return catalog


def _run_failure_signatures(run: PipelineRun) -> list[dict[str, Any]]:
    module_by_test = {item["id"]: item["module"] for item in _run_test_catalog(run)}
    seen: set[tuple[str, str]] = set()
    signatures: list[dict[str, Any]] = []

    for item in (run.execution_result or {}).get("results") or []:
        if not isinstance(item, dict):
            continue
        status = _clean(item.get("status")).lower()
        if status not in {"fail", "error"}:
            continue

        test_id = _clean(item.get("test_id"))
        signature = failure_signature(item.get("error_message"), status)
        if not signature or (signature, test_id) in seen:
            continue
        seen.add((signature, test_id))
        signatures.append(
            {
                "signature": signature,
                "module": module_by_test.get(test_id, ""),
                "test_id": test_id,
                "status": status,
            }
        )
    return signatures


def _completed(query_result: Iterable[PipelineRun]) -> list[PipelineRun]:
    return [run for run in query_result if run.status == "complete"]


def story_runs(
    session: Session,
    *,
    user_id: str,
    story_key: str,
    limit: int = 80,
) -> list[PipelineRun]:
    """Completed runs for one story, newest first, scoped to the user."""
    stmt = (
        select(PipelineRun)
        .where(
            PipelineRun.user_id == user_id,
            PipelineRun.story_key == story_key,
            PipelineRun.status == "complete",
        )
        .order_by(PipelineRun.created_at.desc())
        .limit(max(1, min(limit, 300)))
    )
    return list(session.scalars(stmt))


def module_stats(session: Session, *, user_id: str, module: str) -> dict[str, Any]:
    """Historical defect signal for one module, from this user's runs only."""
    stmt = (
        select(PipelineRun)
        .where(PipelineRun.user_id == user_id, PipelineRun.status == "complete")
        .order_by(PipelineRun.created_at.desc())
        .limit(80)
    )
    runs = [
        run
        for run in session.scalars(stmt)
        if any(item.get("module") == module for item in _run_test_catalog(run))
    ]

    if not runs:
        # defect_probability is omitted rather than defaulted: with no runs there
        # is no historical signal, and callers supply their own prior.
        return {
            "historical_defect_count": 0,
            "total_runs": 0,
            "historical_pass_rate": 0.0,
            "has_history": False,
        }

    executed = failures = 0
    for run in runs:
        for item in _run_test_catalog(run):
            if item["module"] != module:
                continue
            status = item["result_status"]
            if status in {"pass", "fail", "error"}:
                executed += 1
            if status in {"fail", "error"}:
                failures += 1

    failure_rate = failures / executed if executed else 0.0
    return {
        "historical_defect_count": failures,
        "total_runs": len(runs),
        "historical_pass_rate": round(1 - failure_rate, 4),
        "defect_probability": round(failure_rate, 4),
        "has_history": True,
    }


def global_stats(session: Session, *, user_id: str) -> dict[str, Any]:
    stmt = (
        select(PipelineRun)
        .where(PipelineRun.user_id == user_id, PipelineRun.status == "complete")
        .order_by(PipelineRun.created_at.desc())
        .limit(120)
    )
    runs = list(session.scalars(stmt))
    if not runs:
        return {
            "total_runs": 0,
            "average_pass_rate": 0.0,
            "recent_pass_rate": 0.0,
            "average_duration_seconds": 0.0,
        }

    recent = runs[:10]
    return {
        "total_runs": len(runs),
        "average_pass_rate": round(sum(r.pass_rate for r in runs) / len(runs), 4),
        "recent_pass_rate": round(sum(r.pass_rate for r in recent) / len(recent), 4),
        "average_duration_seconds": round(sum(r.duration_seconds for r in runs) / len(runs), 2),
    }


def learning_context(
    session: Session,
    *,
    user_id: str,
    story_text: str | None = None,
    story_intent: str | None = None,
    modules: list[str] | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """What previous runs of this story taught us, for the test generator."""
    story_key, story_label = build_story_identity(
        story_text=story_text, story_intent=story_intent, modules=modules
    )
    runs = story_runs(session, user_id=user_id, story_key=story_key, limit=limit)

    fingerprints: set[str] = set()
    recurring: Counter[str] = Counter()
    module_hint: dict[str, str] = {}

    for run in runs:
        for item in _run_test_catalog(run):
            if item["fingerprint"]:
                fingerprints.add(item["fingerprint"])
        # Count a signature once per run so a flaky suite cannot inflate it.
        for entry in {e["signature"]: e for e in _run_failure_signatures(run)}.values():
            recurring[entry["signature"]] += 1
            module_hint.setdefault(entry["signature"], entry["module"])

    return {
        "story_key": story_key,
        "story_label": story_label,
        "total_runs": len(runs),
        "known_test_fingerprints": sorted(fingerprints),
        "recent_failure_signatures": _run_failure_signatures(runs[0]) if runs else [],
        "recurring_failure_signatures": [
            {"signature": sig, "count": count, "module": module_hint.get(sig, "")}
            for sig, count in recurring.most_common(8)
            if count >= 2
        ],
    }


def story_history(
    session: Session,
    *,
    user_id: str,
    story_text: str | None = None,
    story_intent: str | None = None,
    modules: list[str] | None = None,
    limit: int = 80,
) -> dict[str, Any]:
    """Trend view for one story, for the history panel."""
    story_key, story_label = build_story_identity(
        story_text=story_text, story_intent=story_intent, modules=modules
    )
    runs = story_runs(session, user_id=user_id, story_key=story_key, limit=limit)

    if not runs:
        return {
            "story_key": story_key,
            "story_label": story_label,
            "total_runs": 0,
            "average_pass_rate": 0.0,
            "recent_pass_rate": 0.0,
            "trend": "stable",
            "runs": [],
        }

    average = sum(run.pass_rate for run in runs) / len(runs)
    recent_slice = runs[:5]
    recent = sum(run.pass_rate for run in recent_slice) / len(recent_slice)
    delta = recent - average

    trend = "stable"
    if delta > TREND_EPSILON:
        trend = "improving"
    elif delta < -TREND_EPSILON:
        trend = "declining"

    return {
        "story_key": story_key,
        "story_label": story_label,
        "total_runs": len(runs),
        "average_pass_rate": round(average, 4),
        "recent_pass_rate": round(recent, 4),
        "trend": trend,
        "runs": [
            {
                "run_id": run.id,
                "created_at": run.created_at.isoformat(),
                "mode": run.mode,
                "total_tests": run.total_tests,
                "passed": run.passed,
                "failed": run.failed,
                "errors": run.errors,
                "skipped": run.skipped,
                "pass_rate": run.pass_rate,
                "confidence_score": run.confidence_score,
                "duration": run.duration_seconds,
            }
            for run in runs
        ],
    }
