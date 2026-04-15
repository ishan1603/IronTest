import json
import os
import logging
import hashlib
import tempfile
import threading
import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import Any, List

from pymongo import DESCENDING, MongoClient
from pymongo.collection import Collection
from pymongo.errors import PyMongoError

from models import TestExecutionSummary

logger = logging.getLogger(__name__)

HISTORY_DIR = os.path.join(os.path.dirname(__file__), "data")
HISTORY_FILE = os.path.join(HISTORY_DIR, "history.json")
DEFAULT_DB_NAME = os.getenv("MONGODB_DB_NAME", "irontest")
DEFAULT_COLLECTION = os.getenv("MONGODB_COLLECTION", "executions")
# Default to local file persistence for hackathon-friendly runs.
USE_MONGODB = os.getenv("USE_MONGODB", "false").lower() in {"1", "true", "yes"}

_mongo_client: MongoClient | None = None
_mongo_unavailable_logged = False
_history_lock = threading.Lock()

# Ensure data directory exists
os.makedirs(HISTORY_DIR, exist_ok=True)


def _get_collection() -> Collection | None:
    global _mongo_client
    global _mongo_unavailable_logged

    if not USE_MONGODB:
        return None

    mongo_uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    try:
        if _mongo_client is None:
            _mongo_client = MongoClient(mongo_uri, serverSelectionTimeoutMS=1200)
        _mongo_client.admin.command("ping")

        db_name = os.getenv("MONGODB_DB_NAME", DEFAULT_DB_NAME)
        collection_name = os.getenv("MONGODB_COLLECTION", DEFAULT_COLLECTION)
        collection = _mongo_client[db_name][collection_name]
        try:
            collection.create_index([("created_at", DESCENDING)])
            collection.create_index([("story_key", DESCENDING), ("created_at", DESCENDING)])
            collection.create_index([("run_id", DESCENDING)], unique=True)
        except PyMongoError:
            # Index creation should never block runtime execution.
            pass
        return collection
    except Exception as exc:  # noqa: BLE001
        _mongo_client = None
        if not _mongo_unavailable_logged:
            logger.warning("MongoDB unavailable, falling back to local file history: %s", exc)
            _mongo_unavailable_logged = True
        return None


def _safe_parse_datetime(value: Any) -> datetime:
    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized)
        except ValueError:
            pass
    return datetime.fromtimestamp(0, tz=timezone.utc)


def _normalized_story_key(story_text: str | None, story_intent: str | None, module_names: List[str]) -> tuple[str, str]:
    text_source = (story_text or story_intent or "").strip()
    if text_source:
        compact = " ".join(text_source.split()).lower()
    else:
        compact = " ".join(sorted(module_names)).lower() or "unknown_story"

    digest = hashlib.sha256(compact.encode("utf-8")).hexdigest()[:24]
    label_source = text_source if text_source else (", ".join(module_names) or "Unknown Story")
    label = " ".join(label_source.split())[:160]
    return digest, label


def build_story_identity(
    *,
    story_text: str | None = None,
    story_intent: str | None = None,
    modules: List[str] | None = None,
) -> tuple[str, str]:
    return _normalized_story_key(story_text, story_intent, modules or [])


def _safe_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _normalize_signature_text(value: Any) -> str:
    text = _safe_text(value).lower()
    return "".join(ch for ch in text if ch.isalnum() or ch in {" ", "_", "-", ":"}).strip()


def _test_fingerprint(test_case: dict[str, Any]) -> str:
    basis = "|".join(
        [
            _safe_text(test_case.get("module", "")).lower(),
            _safe_text(test_case.get("type", "")).lower(),
            _safe_text(test_case.get("description", "")).lower(),
            _safe_text(test_case.get("expected_result", "")).lower(),
        ]
    )
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]


def _failure_signature_from_message(error_message: Any, status: str) -> str:
    message = str(error_message or "")
    lines = [line.strip() for line in message.splitlines() if line.strip()]

    reason = ""
    failed_summary = next((line for line in lines if line.startswith("FAILED ") and " - " in line), "")
    if failed_summary:
        reason = failed_summary.split(" - ", 1)[1].strip()

    if not reason:
        assertion_line = next((line for line in lines if "AssertionError:" in line), "")
        if assertion_line:
            reason = assertion_line.split("AssertionError:", 1)[1].strip()

    if not reason and lines:
        reason = lines[-1]

    if not reason:
        reason = f"{status}_without_message"

    return _normalize_signature_text(reason)


def _normalize_failure_signature_item(item: Any) -> dict[str, Any] | None:
    if isinstance(item, str):
        signature = _normalize_signature_text(item)
        return {"signature": signature, "module": "", "test_id": "", "status": "fail"} if signature else None

    if not isinstance(item, dict):
        return None

    signature = _normalize_signature_text(item.get("signature") or item.get("reason") or "")
    if not signature:
        signature = _failure_signature_from_message(item.get("error_message"), str(item.get("status") or "fail"))
    if not signature:
        return None

    return {
        "signature": signature,
        "module": _safe_text(item.get("module")),
        "test_id": _safe_text(item.get("test_id")),
        "status": _safe_text(item.get("status") or "fail").lower() or "fail",
    }


def _normalize_test_catalog_item(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None

    test_id = _safe_text(item.get("id"))
    module = _safe_text(item.get("module"))
    test_type = _safe_text(item.get("type") or "functional").lower() or "functional"
    description = _safe_text(item.get("description"))
    expected_result = _safe_text(item.get("expected_result"))
    learning_source = _safe_text(item.get("learning_source") or "baseline").lower()
    if learning_source not in {"baseline", "adaptive", "fallback"}:
        learning_source = "baseline"

    derived_signature = _normalize_signature_text(item.get("derived_from_failure_signature"))
    fingerprint = _safe_text(item.get("fingerprint")) or _test_fingerprint(
        {
            "module": module,
            "type": test_type,
            "description": description,
            "expected_result": expected_result,
        }
    )

    return {
        "id": test_id,
        "module": module,
        "type": test_type,
        "risk_level": _safe_text(item.get("risk_level") or "medium").lower() or "medium",
        "description": description,
        "expected_result": expected_result,
        "fingerprint": fingerprint,
        "learning_source": learning_source,
        "derived_from_failure_signature": derived_signature,
        "novelty_reason": _safe_text(item.get("novelty_reason")),
        "result_status": _safe_text(item.get("result_status") or "not_executed").lower() or "not_executed",
    }


def _run_test_catalog(run: dict[str, Any]) -> list[dict[str, Any]]:
    catalog = run.get("test_catalog", [])
    if not isinstance(catalog, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in catalog:
        parsed = _normalize_test_catalog_item(item)
        if parsed is not None:
            normalized.append(parsed)
    return normalized


def _run_failure_signature_items(run: dict[str, Any]) -> list[dict[str, Any]]:
    raw_items = run.get("failure_signatures", [])
    if not isinstance(raw_items, list):
        raw_items = []

    normalized: list[dict[str, Any]] = []
    for item in raw_items:
        parsed = _normalize_failure_signature_item(item)
        if parsed is not None:
            normalized.append(parsed)

    if normalized:
        return normalized

    for result in run.get("results", []):
        if not isinstance(result, dict):
            continue
        status = _safe_text(result.get("status")).lower()
        if status not in {"fail", "error"}:
            continue
        signature = _failure_signature_from_message(result.get("error_message"), status)
        if not signature:
            continue
        normalized.append(
            {
                "signature": signature,
                "module": "",
                "test_id": _safe_text(result.get("test_id")),
                "status": status,
            }
        )
    return normalized


def _build_story_learning_summary(runs: list[dict[str, Any]]) -> dict[str, Any]:
    if not runs:
        return {
            "current_run_id": "",
            "previous_run_id": "",
            "current_total_tests": 0,
            "adaptive_tests": 0,
            "baseline_tests": 0,
            "new_test_fingerprints": 0,
            "novelty_ratio": 0.0,
            "prior_failure_signatures": 0,
            "failure_targeted_tests": 0,
            "prior_failure_signatures_covered": 0,
            "targeted_coverage": 0.0,
            "resolved_recurring_failure_signatures": 0,
            "resolution_rate": 0.0,
            "recurring_failure_signatures": [],
        }

    current_run = runs[0]
    previous_run = runs[1] if len(runs) > 1 else None

    current_catalog = _run_test_catalog(current_run)
    previous_catalog = _run_test_catalog(previous_run) if previous_run else []

    current_fingerprints = {item.get("fingerprint", "") for item in current_catalog if item.get("fingerprint")}
    previous_fingerprints = {item.get("fingerprint", "") for item in previous_catalog if item.get("fingerprint")}
    new_fingerprints = current_fingerprints - previous_fingerprints if previous_fingerprints else current_fingerprints

    prior_failure_signatures = {
        item.get("signature", "")
        for item in (_run_failure_signature_items(previous_run) if previous_run else [])
        if item.get("signature")
    }
    targeted_signatures = {
        _normalize_signature_text(item.get("derived_from_failure_signature", ""))
        for item in current_catalog
        if _normalize_signature_text(item.get("derived_from_failure_signature", ""))
    }
    covered_signatures = prior_failure_signatures.intersection(targeted_signatures)

    resolved_signatures: set[str] = set()
    for item in current_catalog:
        target_signature = _normalize_signature_text(item.get("derived_from_failure_signature", ""))
        if not target_signature or target_signature not in prior_failure_signatures:
            continue
        if _safe_text(item.get("result_status", "")).lower() == "pass":
            resolved_signatures.add(target_signature)

    recurring_counter: Counter[str] = Counter()
    for run in runs:
        seen_this_run = {
            item.get("signature", "")
            for item in _run_failure_signature_items(run)
            if item.get("signature")
        }
        recurring_counter.update(seen_this_run)

    adaptive_tests = sum(1 for item in current_catalog if item.get("learning_source") == "adaptive")
    baseline_tests = sum(1 for item in current_catalog if item.get("learning_source") != "adaptive")
    failure_targeted_tests = sum(1 for item in current_catalog if item.get("derived_from_failure_signature"))

    return {
        "current_run_id": _safe_text(current_run.get("run_id")),
        "previous_run_id": _safe_text(previous_run.get("run_id")) if previous_run else "",
        "current_total_tests": len(current_catalog),
        "adaptive_tests": adaptive_tests,
        "baseline_tests": baseline_tests,
        "new_test_fingerprints": len(new_fingerprints),
        "novelty_ratio": round(len(new_fingerprints) / max(1, len(current_fingerprints)), 4),
        "prior_failure_signatures": len(prior_failure_signatures),
        "failure_targeted_tests": failure_targeted_tests,
        "prior_failure_signatures_covered": len(covered_signatures),
        "targeted_coverage": round(len(covered_signatures) / max(1, len(prior_failure_signatures)), 4)
        if prior_failure_signatures
        else 0.0,
        "resolved_recurring_failure_signatures": len(resolved_signatures),
        "resolution_rate": round(len(resolved_signatures) / max(1, len(prior_failure_signatures)), 4)
        if prior_failure_signatures
        else 0.0,
        "recurring_failure_signatures": [
            {"signature": signature, "count": count}
            for signature, count in recurring_counter.most_common(6)
            if count >= 2
        ],
    }


def _atomic_write_history(history: List[dict]) -> None:
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        delete=False,
        dir=HISTORY_DIR,
        suffix=".tmp",
    ) as temp_file:
        json.dump(history, temp_file, indent=2, ensure_ascii=False)
        temp_path = temp_file.name
    os.replace(temp_path, HISTORY_FILE)


def load_history() -> List[dict]:
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with _history_lock:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                payload = json.load(f)
                return payload if isinstance(payload, list) else []
    except Exception as e:
        logger.error(f"Failed to load history: {e}")
        return []


def save_execution(
    module_names: List[str],
    execution: TestExecutionSummary,
    *,
    tests: List[Any] | None = None,
    story_text: str | None = None,
    story_intent: str | None = None,
    source: str = "pipeline",
    session_id: str | None = None,
    confidence_score: int | None = None,
):
    total_tests = len(execution.results)
    passed = sum(1 for r in execution.results if r.status == "pass")
    failed = sum(1 for r in execution.results if r.status == "fail")
    errors = sum(1 for r in execution.results if r.status == "error")
    skipped = sum(1 for r in execution.results if r.status == "skipped")
    executed_tests = passed + failed + errors
    story_key, story_label = _normalized_story_key(story_text, story_intent, module_names)
    result_by_id = {item.test_id: item for item in execution.results}

    test_catalog: list[dict[str, Any]] = []
    for test in tests or []:
        if hasattr(test, "model_dump"):
            raw_test = test.model_dump()
        elif isinstance(test, dict):
            raw_test = test
        else:
            continue

        normalized_test = _normalize_test_catalog_item(raw_test)
        if normalized_test is None:
            continue

        test_id = normalized_test.get("id", "")
        result = result_by_id.get(test_id)
        normalized_test["result_status"] = (result.status if result is not None else "not_executed").lower()
        test_catalog.append(normalized_test)

    test_by_id = {item.get("id", ""): item for item in test_catalog if item.get("id")}
    failure_signatures: list[dict[str, Any]] = []
    seen_failures: set[tuple[str, str]] = set()
    for item in execution.results:
        if item.status not in {"fail", "error"}:
            continue

        signature = _failure_signature_from_message(item.error_message, item.status)
        module = _safe_text(test_by_id.get(item.test_id, {}).get("module", ""))
        dedupe_key = (signature, item.test_id)
        if dedupe_key in seen_failures:
            continue
        seen_failures.add(dedupe_key)
        failure_signatures.append(
            {
                "signature": signature,
                "module": module,
                "test_id": item.test_id,
                "status": item.status,
            }
        )

    adaptive_count = sum(1 for item in test_catalog if item.get("learning_source") == "adaptive")

    run_record = {
        "schema_version": 2,
        "run_id": uuid.uuid4().hex,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "session_id": session_id,
        "story_key": story_key,
        "story_label": story_label,
        "modules": module_names,
        "duration": execution.duration_seconds,
        "total_tests": total_tests,
        "executed_tests": executed_tests,
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "skipped": skipped,
        "pass_rate": passed / max(1, executed_tests),
        "confidence_score": int(confidence_score) if confidence_score is not None else None,
        "results": [r.model_dump() for r in execution.results],
        "test_catalog": test_catalog,
        "failure_signatures": failure_signatures,
        "learning_artifacts": {
            "test_catalog_size": len(test_catalog),
            "adaptive_tests": adaptive_count,
            "baseline_tests": max(0, len(test_catalog) - adaptive_count),
            "failure_signature_count": len(failure_signatures),
        },
    }

    collection = _get_collection()
    if collection is not None:
        try:
            collection.insert_one(run_record)
            return
        except PyMongoError as exc:
            logger.error("Failed to save history in MongoDB, using local file: %s", exc)

    history = load_history()
    history.append(run_record)
    try:
        with _history_lock:
            _atomic_write_history(history)
    except Exception as e:
        logger.error(f"Failed to save history: {e}")


def _normalize_run_record(run: dict[str, Any]) -> dict[str, Any]:
    if "schema_version" not in run:
        run["schema_version"] = 1
    if "run_id" not in run:
        run["run_id"] = uuid.uuid4().hex
    if "source" not in run:
        run["source"] = "pipeline"
    if "story_key" not in run:
        story_key, story_label = _normalized_story_key(
            story_text=None,
            story_intent=None,
            module_names=run.get("modules", []),
        )
        run["story_key"] = story_key
        run["story_label"] = story_label

    normalized_catalog = _run_test_catalog(run)
    run["test_catalog"] = normalized_catalog

    normalized_failure_signatures = _run_failure_signature_items(run)
    run["failure_signatures"] = normalized_failure_signatures

    adaptive_count = sum(1 for item in normalized_catalog if item.get("learning_source") == "adaptive")
    run["learning_artifacts"] = {
        "test_catalog_size": len(normalized_catalog),
        "adaptive_tests": adaptive_count,
        "baseline_tests": max(0, len(normalized_catalog) - adaptive_count),
        "failure_signature_count": len(normalized_failure_signatures),
    }

    def _legacy_confidence_estimate(item: dict[str, Any]) -> int:
        executed = int(item.get("executed_tests", item.get("total_tests", 0)) or 0)
        if executed <= 0:
            return 50
        passed = int(item.get("passed", 0) or 0)
        failed = int(item.get("failed", 0) or 0)
        errors = int(item.get("errors", 0) or 0)
        skipped = int(item.get("skipped", 0) or 0)
        pass_rate = passed / max(1, executed)

        # Legacy runs may not have defect-agent confidence; estimate conservatively.
        score = 42 + (pass_rate * 46)
        score -= failed * 2.5
        score -= errors * 4.0
        score -= skipped * 1.5
        score -= 5
        return max(15, min(95, round(score)))

    if "pass_rate" in run and "total_tests" in run:
        if "executed_tests" not in run:
            run["executed_tests"] = int(run.get("passed", 0)) + int(run.get("failed", 0)) + int(run.get("errors", 0))
        if "confidence_score" not in run or run.get("confidence_score") is None:
            run["confidence_score"] = _legacy_confidence_estimate(run)
        return run

    results = run.get("results", [])
    total_tests = len(results)
    passed = sum(1 for item in results if item.get("status") == "pass")
    failed = sum(1 for item in results if item.get("status") == "fail")
    errors = sum(1 for item in results if item.get("status") == "error")
    skipped = sum(1 for item in results if item.get("status") == "skipped")
    run["total_tests"] = total_tests
    run["passed"] = passed
    run["failed"] = failed
    run["errors"] = errors
    run["skipped"] = skipped
    run["executed_tests"] = passed + failed + errors
    run["pass_rate"] = passed / max(1, run["executed_tests"])
    if "confidence_score" not in run or run.get("confidence_score") is None:
        run["confidence_score"] = _legacy_confidence_estimate(run)
    return run


def _module_runs(module_name: str) -> List[dict[str, Any]]:
    collection = _get_collection()
    if collection is not None:
        try:
            docs = list(
                collection.find({"modules": module_name}, {"_id": 0}).sort("created_at", DESCENDING).limit(80)
            )
            return [_normalize_run_record(doc) for doc in docs]
        except PyMongoError as exc:
            logger.warning("MongoDB query failed for module history, falling back to file: %s", exc)

    history = load_history()
    filtered = [run for run in history if module_name in run.get("modules", [])]
    normalized = [_normalize_run_record(run) for run in filtered]
    normalized.sort(key=lambda item: _safe_parse_datetime(item.get("created_at")), reverse=True)
    return normalized[:80]


def get_module_history_stats(module_name: str) -> dict:
    runs = _module_runs(module_name)
    total_runs = len(runs)
    total_failures = 0
    total_tests = 0
    recent_failures = 0
    recent_tests = 0

    for idx, run in enumerate(runs):
        total_failures += int(run.get("failed", 0)) + int(run.get("errors", 0))
        total_tests += int(run.get("executed_tests", run.get("total_tests", 0)))
        if idx < 10:
            recent_failures += int(run.get("failed", 0)) + int(run.get("errors", 0))
            recent_tests += int(run.get("executed_tests", run.get("total_tests", 0)))

    if total_runs == 0:
        return {
            "historical_defect_count": 0,
            "defect_probability": 0.2,
            "total_runs": 0,
            "historical_pass_rate": 0.0,
        }

    failure_rate = total_failures / max(1, total_tests)
    recent_failure_rate = recent_failures / max(1, recent_tests)
    probability = min(1.0, 0.12 + (failure_rate * 0.68) + (recent_failure_rate * 0.2))

    return {
        "historical_defect_count": total_failures,
        "defect_probability": round(probability, 4),
        "total_runs": total_runs,
        "historical_pass_rate": round(1 - failure_rate, 4),
    }


def get_global_history_stats() -> dict:
    collection = _get_collection()
    if collection is not None:
        try:
            runs = list(collection.find({}, {"_id": 0}).sort("created_at", DESCENDING).limit(120))
            normalized = [_normalize_run_record(run) for run in runs]
        except PyMongoError as exc:
            logger.warning("MongoDB query failed for global history, falling back to file: %s", exc)
            normalized = [_normalize_run_record(run) for run in load_history()]
    else:
        normalized = [_normalize_run_record(run) for run in load_history()]

    normalized.sort(key=lambda item: _safe_parse_datetime(item.get("created_at")), reverse=True)
    normalized = normalized[:120]

    if not normalized:
        return {
            "total_runs": 0,
            "average_pass_rate": 0.0,
            "recent_pass_rate": 0.0,
            "average_duration_seconds": 0.0,
        }

    avg_pass_rate = sum(float(run.get("pass_rate", 0.0)) for run in normalized) / len(normalized)
    recent_slice = normalized[:10]
    recent_pass = sum(float(run.get("pass_rate", 0.0)) for run in recent_slice) / max(1, len(recent_slice))
    avg_duration = sum(float(run.get("duration", 0.0)) for run in normalized) / len(normalized)

    return {
        "total_runs": len(normalized),
        "average_pass_rate": round(avg_pass_rate, 4),
        "recent_pass_rate": round(recent_pass, 4),
        "average_duration_seconds": round(avg_duration, 2),
    }


def get_story_history(*, story_key: str, limit: int = 80) -> List[dict[str, Any]]:
    capped_limit = max(1, min(limit, 300))
    collection = _get_collection()
    if collection is not None:
        try:
            docs = list(
                collection.find({"story_key": story_key}, {"_id": 0}).sort("created_at", DESCENDING).limit(capped_limit)
            )
            return [_normalize_run_record(doc) for doc in docs]
        except PyMongoError as exc:
            logger.warning("MongoDB query failed for story history, falling back to file: %s", exc)

    runs = [_normalize_run_record(item) for item in load_history() if item.get("story_key") == story_key]
    runs.sort(key=lambda item: _safe_parse_datetime(item.get("created_at")), reverse=True)
    return runs[:capped_limit]


def get_story_learning_context(
    *,
    story_text: str | None = None,
    story_intent: str | None = None,
    modules: List[str] | None = None,
    limit: int = 25,
) -> dict[str, Any]:
    module_names = modules or []
    story_key, story_label = build_story_identity(
        story_text=story_text,
        story_intent=story_intent,
        modules=module_names,
    )
    runs = get_story_history(story_key=story_key, limit=max(1, min(limit, 80)))

    known_fingerprints: set[str] = set()
    for run in runs:
        for item in _run_test_catalog(run):
            fingerprint = _safe_text(item.get("fingerprint"))
            if fingerprint:
                known_fingerprints.add(fingerprint)

    recent_failure_signatures = _run_failure_signature_items(runs[0]) if runs else []
    recurring_counter: Counter[str] = Counter()
    signature_module_hint: dict[str, str] = {}
    for run in runs:
        for entry in _run_failure_signature_items(run):
            signature = entry.get("signature", "")
            if not signature:
                continue
            recurring_counter[signature] += 1
            if signature not in signature_module_hint and entry.get("module"):
                signature_module_hint[signature] = entry.get("module", "")

    recurring_failure_signatures = [
        {
            "signature": signature,
            "count": count,
            "module": signature_module_hint.get(signature, ""),
        }
        for signature, count in recurring_counter.most_common(8)
        if count >= 2
    ]

    return {
        "story_key": story_key,
        "story_label": story_label,
        "total_runs": len(runs),
        "known_test_fingerprints": sorted(known_fingerprints),
        "recent_failure_signatures": recent_failure_signatures,
        "recurring_failure_signatures": recurring_failure_signatures,
    }


def get_story_history_by_context(
    *,
    story_text: str | None = None,
    story_intent: str | None = None,
    modules: List[str] | None = None,
    limit: int = 80,
) -> dict[str, Any]:
    module_names = modules or []
    story_key, story_label = build_story_identity(
        story_text=story_text,
        story_intent=story_intent,
        modules=module_names,
    )
    runs = get_story_history(story_key=story_key, limit=limit)

    if not runs:
        return {
            "story_key": story_key,
            "story_label": story_label,
            "total_runs": 0,
            "average_pass_rate": 0.0,
            "recent_pass_rate": 0.0,
            "trend": "stable",
            "learning_summary": _build_story_learning_summary([]),
            "runs": [],
        }

    avg_pass = sum(float(run.get("pass_rate", 0.0)) for run in runs) / len(runs)
    recent_slice = runs[:5]
    recent_pass = sum(float(run.get("pass_rate", 0.0)) for run in recent_slice) / max(1, len(recent_slice))
    delta = recent_pass - avg_pass
    trend = "stable"
    if delta > 0.05:
        trend = "improving"
    elif delta < -0.05:
        trend = "declining"

    return {
        "story_key": story_key,
        "story_label": story_label,
        "total_runs": len(runs),
        "average_pass_rate": round(avg_pass, 4),
        "recent_pass_rate": round(recent_pass, 4),
        "trend": trend,
        "learning_summary": _build_story_learning_summary(runs),
        "runs": runs,
    }
