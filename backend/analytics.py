"""Cross-run analytics for the dashboard, all scoped to one user.

Everything here is computed from stored PipelineRun rows. Nothing is inferred
or synthesized: a user with two runs gets a two-point trend, not a padded one.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import PipelineRun, Repository
from history import _clean, _run_test_catalog

TREND_LIMIT = 60
FLAKY_MIN_RUNS = 3


def _completed_runs(session: Session, user_id: str, limit: int = 200) -> list[PipelineRun]:
    stmt = (
        select(PipelineRun)
        .where(PipelineRun.user_id == user_id, PipelineRun.status == "complete")
        .order_by(PipelineRun.created_at.desc())
        .limit(limit)
    )
    return list(session.scalars(stmt))


def _flaky_tests(runs: list[PipelineRun]) -> list[dict[str, Any]]:
    """Tests (by description within a story) that both passed and failed."""
    seen: dict[tuple[str, str], Counter] = defaultdict(Counter)
    label: dict[tuple[str, str], str] = {}

    for run in runs:
        for item in _run_test_catalog(run):
            desc = item.get("description", "")
            if not desc:
                continue
            key = (run.story_key, desc.lower())
            status = item.get("result_status", "not_executed")
            if status in {"pass", "fail", "error"}:
                seen[key][status] += 1
                label[key] = desc

    flaky = []
    for key, counts in seen.items():
        runs_seen = sum(counts.values())
        passed = counts.get("pass", 0)
        failed = counts.get("fail", 0) + counts.get("error", 0)
        if runs_seen >= FLAKY_MIN_RUNS and passed and failed:
            flaky.append(
                {
                    "description": label[key],
                    "runs": runs_seen,
                    "passed": passed,
                    "failed": failed,
                    "flip_rate": round(min(passed, failed) / runs_seen, 3),
                }
            )
    flaky.sort(key=lambda item: (-item["flip_rate"], -item["runs"]))
    return flaky[:12]


def _worst_modules(runs: list[PipelineRun]) -> list[dict[str, Any]]:
    executed: Counter = Counter()
    failed: Counter = Counter()
    for run in runs:
        for item in _run_test_catalog(run):
            module = item.get("module") or "unknown"
            status = item.get("result_status", "not_executed")
            if status in {"pass", "fail", "error"}:
                executed[module] += 1
            if status in {"fail", "error"}:
                failed[module] += 1

    rows = [
        {
            "module": module,
            "executed": executed[module],
            "failed": failed[module],
            "fail_rate": round(failed[module] / executed[module], 3) if executed[module] else 0.0,
        }
        for module in executed
        if failed[module]
    ]
    rows.sort(key=lambda item: (-item["fail_rate"], -item["failed"]))
    return rows[:10]


def analytics_overview(session: Session, *, user_id: str) -> dict[str, Any]:
    runs = _completed_runs(session, user_id)
    repo_names = {
        repo.id: repo.full_name
        for repo in session.scalars(select(Repository).where(Repository.user_id == user_id))
    }

    if not runs:
        return {
            "totals": {"runs": 0, "tests_executed": 0, "avg_pass_rate": 0.0, "avg_confidence": 0.0},
            "trend": [],
            "by_repository": [],
            "by_mode": {},
            "flaky_tests": [],
            "worst_modules": [],
        }

    tests_executed = sum(r.passed + r.failed + r.errors for r in runs)
    scored = [r.confidence_score for r in runs if r.confidence_score is not None]

    # Oldest -> newest for a left-to-right chart.
    trend = [
        {
            "run_id": r.id,
            "at": r.created_at.isoformat(),
            "pass_rate": round(r.pass_rate, 4),
            "confidence": r.confidence_score,
            "mode": r.mode,
            "repository": repo_names.get(r.repository_id),
        }
        for r in reversed(runs[:TREND_LIMIT])
    ]

    by_repo: dict[str, dict[str, Any]] = {}
    for r in runs:
        name = repo_names.get(r.repository_id) or "(standalone)"
        bucket = by_repo.setdefault(
            name, {"repository": name, "runs": 0, "pass_rate_sum": 0.0, "last_run": None, "last_confidence": None}
        )
        bucket["runs"] += 1
        bucket["pass_rate_sum"] += r.pass_rate
        if bucket["last_run"] is None:
            bucket["last_run"] = r.created_at.isoformat()
            bucket["last_confidence"] = r.confidence_score

    by_repository = [
        {
            "repository": b["repository"],
            "runs": b["runs"],
            "avg_pass_rate": round(b["pass_rate_sum"] / b["runs"], 4),
            "last_run": b["last_run"],
            "last_confidence": b["last_confidence"],
        }
        for b in sorted(by_repo.values(), key=lambda x: -x["runs"])
    ]

    mode_counter = Counter(r.mode for r in runs)

    return {
        "totals": {
            "runs": len(runs),
            "tests_executed": tests_executed,
            "avg_pass_rate": round(sum(r.pass_rate for r in runs) / len(runs), 4),
            "avg_confidence": round(sum(scored) / len(scored), 1) if scored else 0.0,
        },
        "trend": trend,
        "by_repository": by_repository,
        "by_mode": dict(mode_counter),
        "flaky_tests": _flaky_tests(runs),
        "worst_modules": _worst_modules(runs),
    }


def run_list(session: Session, *, user_id: str, limit: int = 100) -> list[dict[str, Any]]:
    """Flat list of every run for the history table."""
    stmt = (
        select(PipelineRun)
        .where(PipelineRun.user_id == user_id)
        .order_by(PipelineRun.created_at.desc())
        .limit(min(limit, 300))
    )
    runs = list(session.scalars(stmt))
    repo_names = {
        repo.id: repo.full_name
        for repo in session.scalars(select(Repository).where(Repository.user_id == user_id))
    }
    return [
        {
            "id": r.id,
            "chat_id": r.chat_id,
            "status": r.status,
            "mode": r.mode,
            "source": r.source,
            "repository": repo_names.get(r.repository_id),
            "story_label": _clean(r.story_label) or _clean(r.story_text)[:120],
            "total_tests": r.total_tests,
            "passed": r.passed,
            "failed": r.failed,
            "errors": r.errors,
            "skipped": r.skipped,
            "pass_rate": round(r.pass_rate, 4),
            "confidence_score": r.confidence_score,
            "duration_seconds": r.duration_seconds,
            "created_at": r.created_at.isoformat(),
        }
        for r in runs
    ]
