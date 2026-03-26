import json
import os
import logging
from typing import List
from models import TestExecutionSummary

logger = logging.getLogger(__name__)

HISTORY_DIR = os.path.join(os.path.dirname(__file__), "data")
HISTORY_FILE = os.path.join(HISTORY_DIR, "history.json")

# Ensure data directory exists
os.makedirs(HISTORY_DIR, exist_ok=True)

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
    history = load_history()
    
    # Store the run data
    run_record = {
        "modules": module_names,
        "duration": execution.duration_seconds,
        "results": [r.model_dump() for r in execution.results]
    }
    history.append(run_record)
    
    try:
        with open(HISTORY_FILE, "w") as f:
            json.dump(history, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save history: {e}")

def get_module_history_stats(module_name: str) -> dict:
    history = load_history()
    
    total_runs = 0
    total_failures = 0
    
    for run in history:
        if module_name in run.get("modules", []):
            total_runs += 1
            for res in run.get("results", []):
                if res.get("status") in ("fail", "error"):
                    total_failures += 1
                    
    prob = (total_failures / max(1, total_failures + total_runs * 5)) # basic formula
    
    return {
        "historical_defect_count": total_failures,
        "defect_probability": min(1.0, prob),
        "total_runs": total_runs
    }
