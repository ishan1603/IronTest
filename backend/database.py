import json
import os
import logging
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
        return _mongo_client[db_name][collection_name]
    except Exception as exc:  # noqa: BLE001
        _mongo_client = None
        if not _mongo_unavailable_logged:
            logger.warning("MongoDB unavailable, falling back to local file history: %s", exc)
            _mongo_unavailable_logged = True
        return None


def load_history() -> List[dict]:
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load history: {e}")
        return []

def save_execution(module_names: List[str], execution: TestExecutionSummary):
    total_tests = len(execution.results)
    passed = sum(1 for r in execution.results if r.status == "pass")
    failed = sum(1 for r in execution.results if r.status == "fail")
    errors = sum(1 for r in execution.results if r.status == "error")
    skipped = sum(1 for r in execution.results if r.status == "skipped")

    run_record = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "modules": module_names,
        "duration": execution.duration_seconds,
        "total_tests": total_tests,
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "skipped": skipped,
        "pass_rate": passed / max(1, total_tests),
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
        with open(HISTORY_FILE, "w") as f:
            json.dump(history, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save history: {e}")


def _normalize_run_record(run: dict[str, Any]) -> dict[str, Any]:
    if "pass_rate" in run and "total_tests" in run:
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
    run["pass_rate"] = passed / max(1, total_tests)
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
    return [_normalize_run_record(run) for run in filtered[-80:]][::-1]


def get_module_history_stats(module_name: str) -> dict:
    runs = _module_runs(module_name)
    total_runs = len(runs)
    total_failures = 0
    total_tests = 0
    recent_failures = 0
    recent_tests = 0

    for idx, run in enumerate(runs):
        total_failures += int(run.get("failed", 0)) + int(run.get("errors", 0))
        total_tests += int(run.get("total_tests", 0))
        if idx < 10:
            recent_failures += int(run.get("failed", 0)) + int(run.get("errors", 0))
            recent_tests += int(run.get("total_tests", 0))

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
            normalized = [_normalize_run_record(run) for run in load_history()[-120:]][::-1]
    else:
        normalized = [_normalize_run_record(run) for run in load_history()[-120:]][::-1]

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
