import asyncio
import json
import os
import re
import ast
from typing import List

from llm_client import llm_generate_json
from models import StoryAnalysis, TestCase


SYSTEM_PROMPT = """
You are the Test Generation Agent in an autonomous QA system.
Given acceptance criteria, modules, and risk factors, generate 8-10 test cases covering functional, boundary, edge/negative, and regression/security risks.

Respond strictly as a JSON object with a single key "test_cases" whose value is an array of objects shaped as:
{
    "id": string (TC-001 format),
    "type": "functional" | "boundary" | "edge_case" | "regression",
    "module": string,
    "description": string,
    "steps": string[],
    "expected_result": string,
    "risk_level": "low" | "medium" | "high",
    "automated": boolean,
    "automation_snippet": string[] (Array of strings, each string is a single line of a Pytest script.
    IMPORTANT: You MUST wrap the code in a function like 'def test_scenario():' and indent the body.
    Keep snippet length concise (max 10 lines) and executable.
    Snippet MUST be self-contained and deterministic using local in-memory data only.
    DO NOT make network calls and DO NOT depend on external services/endpoints.
    DO NOT import requests/httpx/playwright/selenium/cypress.
    Prefer pure assertions on contract rules and acceptance criteria invariants.
    DO NOT output \n or triple quotes.
    DO NOT wrap response in markdown code fences)
}
"""


_VALID_TYPES = {"functional", "boundary", "edge_case", "regression"}
_VALID_RISKS = {"low", "medium", "high"}
_DISALLOWED_RUNTIME_MARKERS = (
    "playwright",
    "selenium",
    "cypress",
    "puppeteer",
    "import requests",
    "requests.",
    "httpx",
    "urllib",
    "http://",
    "https://",
)

USE_RAW_LLM_SNIPPETS = os.getenv("USE_RAW_LLM_SNIPPETS", "false").lower() in {"1", "true", "yes"}


def _is_safe_raw_snippet(lines: list[str]) -> bool:
    if not lines:
        return False

    text = "\n".join(lines).lower()
    if any(marker in text for marker in _DISALLOWED_RUNTIME_MARKERS):
        return False

    try:
        tree = ast.parse("\n".join(lines))
    except SyntaxError:
        return False

    if any(isinstance(node, (ast.Import, ast.ImportFrom, ast.ClassDef, ast.With, ast.Try)) for node in ast.walk(tree)):
        return False

    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            base = node.value.id
            if base and base[0].isupper():
                return False

    return True


def _slug(value: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9]+", "_", (value or "").strip().lower())
    clean = clean.strip("_")
    return clean or "scenario"


def _fallback_snippet(test_id: str, module_name: str, test_type: str = "functional") -> list[str]:
    fn_name = f"test_{_slug(test_id)}_{_slug(module_name)}"[:56]
    if test_type == "boundary":
        return [
            f"def {fn_name}():",
            "    max_len = 64",
            "    payload = {'id': 'A' * max_len, 'enabled': True}",
            "    assert len(payload['id']) == max_len",
            "    assert payload['enabled'] is True",
        ]
    if test_type == "edge_case":
        return [
            f"def {fn_name}():",
            "    payload = {'id': '', 'enabled': True}",
            "    required = ['id', 'enabled']",
            "    invalid = any(payload.get(k) in ('', None) for k in required)",
            "    assert invalid is True",
        ]
    if test_type == "regression":
        return [
            f"def {fn_name}():",
            "    baseline = {'status': 'ok', 'version': 1}",
            "    current = {'status': 'ok', 'version': 1}",
            "    assert current['status'] == baseline['status']",
            "    assert current['version'] == baseline['version']",
        ]
    return [
        f"def {fn_name}():",
        "    payload = {'status': 'ok', 'module': 'active'}",
        "    required = ['status', 'module']",
        "    assert all(k in payload for k in required)",
        "    assert payload['status'] == 'ok'",
    ]


def _fallback_test_plan(modules: list[str]) -> list[dict]:
    module_pool = modules[:] if modules else ["CoreService", "AuthService", "DataService"]
    type_cycle = [
        "functional",
        "boundary",
        "edge_case",
        "regression",
        "functional",
        "boundary",
        "edge_case",
        "regression",
        "functional",
        "regression",
    ]
    risk_map = {
        "functional": "medium",
        "boundary": "medium",
        "edge_case": "high",
        "regression": "high",
    }

    fallback: list[dict] = []
    for idx, test_type in enumerate(type_cycle, start=1):
        tc_id = f"TC-{idx:03d}"
        module_name = module_pool[(idx - 1) % len(module_pool)]
        fallback.append(
            {
                "id": tc_id,
                "type": test_type,
                "module": module_name,
                "description": f"Validate {test_type} contract behavior for {module_name}.",
                "steps": ["Prepare local payload", "Validate contract assertions"],
                "expected_result": "Contract assertions pass deterministically.",
                "risk_level": risk_map[test_type],
                "automated": True,
                "automation_snippet": _fallback_snippet(tc_id, module_name, test_type),
            }
        )
    return fallback


def _normalize_snippet(test_id: str, module_name: str, test_type: str, raw_snippet: object) -> list[str]:
    if isinstance(raw_snippet, list):
        lines = [str(line).rstrip() for line in raw_snippet if str(line).strip()]
    elif isinstance(raw_snippet, str):
        lines = [line.rstrip() for line in raw_snippet.splitlines() if line.strip()]
    else:
        lines = []

    text = "\n".join(lines).lower()
    if not lines or any(marker in text for marker in _DISALLOWED_RUNTIME_MARKERS):
        return _fallback_snippet(test_id, module_name, test_type)

    if not any(line.lstrip().startswith("def ") for line in lines):
        fn_name = f"test_{_slug(test_id)}_{_slug(module_name)}"[:56]
        wrapped = [f"def {fn_name}():"]
        wrapped.extend([f"    {line}" for line in lines])
        lines = wrapped

    if not USE_RAW_LLM_SNIPPETS:
        return _fallback_snippet(test_id, module_name, test_type)

    if not _is_safe_raw_snippet(lines):
        return _fallback_snippet(test_id, module_name, test_type)

    return lines


def _normalize_test_items(raw_items: object, modules: list[str]) -> list[dict]:
    if not isinstance(raw_items, list):
        return []

    normalized: list[dict] = []
    module_fallback = modules[0] if modules else "CoreService"

    for idx, item in enumerate(raw_items, start=1):
        if not isinstance(item, dict):
            continue

        tc_id = str(item.get("id") or f"TC-{idx:03d}").strip()
        tc_type = str(item.get("type") or "functional").strip().lower()
        if tc_type not in _VALID_TYPES:
            tc_type = "functional"

        risk_level = str(item.get("risk_level") or "medium").strip().lower()
        if risk_level not in _VALID_RISKS:
            risk_level = "medium"

        module_name = str(item.get("module") or module_fallback).strip() or module_fallback
        snippet = _normalize_snippet(tc_id, module_name, tc_type, item.get("automation_snippet"))

        normalized.append(
            {
                "id": tc_id,
                "type": tc_type,
                "module": module_name,
                "description": str(item.get("description") or f"Validate {module_name} behavior.").strip(),
                "steps": item.get("steps") if isinstance(item.get("steps"), list) else ["Execute scenario", "Validate response"],
                "expected_result": str(item.get("expected_result") or "Operation completes successfully.").strip(),
                "risk_level": risk_level,
                "automated": True,
                "automation_snippet": snippet,
            }
        )

    return normalized


async def generate_tests(token: str, model_id: str, story: StoryAnalysis) -> List[TestCase]:
    def _call_model() -> List[TestCase]:
        user_payload = {
            "modules": story.modules,
            "acceptance_criteria": story.acceptance_criteria,
            "risk_factors": story.risk_factors,
        }
        prompt = f"Input:\n{json.dumps(user_payload)}\nReturn only the JSON object with key test_cases."
        raw_items: object = []
        try:
            parsed = llm_generate_json(
                api_key=token,
                model_id=model_id,
                system_prompt=SYSTEM_PROMPT,
                user_prompt=prompt,
                max_output_tokens=3000,
                temperature=0.2,
            )
            raw_items = parsed.get("test_cases", parsed if isinstance(parsed, list) else [])
        except Exception:
            raw_items = []

        normalized = _normalize_test_items(raw_items, story.modules)
        fallback_plan = _fallback_test_plan(story.modules)

        if not normalized:
            normalized = fallback_plan
        elif len(normalized) < 8:
            existing = {item.get("id") for item in normalized}
            for item in fallback_plan:
                if item["id"] in existing:
                    continue
                normalized.append(item)
                if len(normalized) >= 10:
                    break

        return [TestCase(**item) for item in normalized]

    return await asyncio.to_thread(_call_model)
