import json
import os
import logging
import hashlib
import tempfile
import threading
import uuid
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
USE_MONGODB = os.getenv("USE_MONGODB", "true").lower() in {"1", "true", "yes"}

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
    story_text: str | None = None,
    story_intent: str | None = None,
    source: str = "pipeline",
    session_id: str | None = None,
):
    total_tests = len(execution.results)
    passed = sum(1 for r in execution.results if r.status == "pass")
    failed = sum(1 for r in execution.results if r.status == "fail")
    errors = sum(1 for r in execution.results if r.status == "error")
    skipped = sum(1 for r in execution.results if r.status == "skipped")
    executed_tests = passed + failed + errors
    story_key, story_label = _normalized_story_key(story_text, story_intent, module_names)

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
        "results": [r.model_dump() for r in execution.results],
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

    if "pass_rate" in run and "total_tests" in run:
        if "executed_tests" not in run:
            run["executed_tests"] = int(run.get("passed", 0)) + int(run.get("failed", 0)) + int(run.get("errors", 0))
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
        "runs": runs,
    }
