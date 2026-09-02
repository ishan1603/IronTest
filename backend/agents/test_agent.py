"""Generates executable test cases from an analyzed story.

Cases come from the model. When a generated snippet fails validation it is
marked non-automated and reported as skipped with the reason -- it is never
replaced with a substitute that asserts a literal against itself.
"""

import ast
import asyncio
import hashlib
import json
from typing import Any, List

from llm import generate_json
from models import StoryAnalysis, TestCase

SYSTEM_PROMPT = """
You are the Test Generation Agent in an autonomous QA system.
Given acceptance criteria, modules, and risk factors, generate 8-10 test cases covering functional, boundary, edge/negative, and regression/security risks.

Every test MUST be able to fail. A test whose assertions compare a literal you
just defined against itself is worthless -- do not emit one. Assert on the
behavior described by the acceptance criteria, so that a violation of that
behavior makes the assertion fail.

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
    Implement the rule under test as a small function inside the snippet, then
    assert that function's output across representative and boundary inputs.
    DO NOT make network calls and DO NOT depend on external services/endpoints.
    DO NOT import requests/httpx/playwright/selenium/cypress.
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


def _normalize_signature(value: str | None) -> str:
    text = " ".join(str(value or "").split()).lower()
    return "".join(ch for ch in text if ch.isalnum() or ch in {" ", "_", "-", ":"}).strip()


def _test_fingerprint(item: dict[str, Any]) -> str:
    basis = "|".join(
        [
            str(item.get("module", "")).strip().lower(),
            str(item.get("type", "")).strip().lower(),
            str(item.get("description", "")).strip().lower(),
            str(item.get("expected_result", "")).strip().lower(),
        ]
    )
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]


def _is_tautological(tree: ast.Module) -> bool:
    """Reject snippets whose assertions only compare literals to themselves.

    Catches the degenerate shape where a dict is defined inline and then each
    assertion reads a key back out of it, which passes unconditionally.
    """
    literal_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                try:
                    ast.literal_eval(node.value)
                except (ValueError, SyntaxError, TypeError):
                    continue
                literal_names.add(target.id)

    asserts = [node for node in ast.walk(tree) if isinstance(node, ast.Assert)]
    if not asserts:
        return True

    def _reads_only_literals(node: ast.AST) -> bool:
        names = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
        calls = [n for n in ast.walk(node) if isinstance(n, ast.Call)]
        if calls:
            return False
        return bool(names) and names.issubset(literal_names)

    return all(_reads_only_literals(node.test) for node in asserts)


def _snippet_rejection_reason(lines: list[str]) -> str | None:
    """Return None when the snippet is safe and meaningful, else why it is not."""
    if not lines:
        return "Model returned no automation snippet."

    text = "\n".join(lines)
    lowered = text.lower()
    for marker in _DISALLOWED_RUNTIME_MARKERS:
        if marker in lowered:
            return f"Snippet reaches outside the sandbox ({marker!r})."

    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return f"Snippet is not valid Python: {exc.msg} (line {exc.lineno})."

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            return "Snippet imports a module; only self-contained snippets run locally."

    if not any(isinstance(node, ast.FunctionDef) and node.name.startswith("test") for node in tree.body):
        return "Snippet defines no test_* function for pytest to collect."

    if _is_tautological(tree):
        return "Snippet only asserts literals against themselves, so it cannot fail."

    return None


def _coerce_snippet_lines(raw_snippet: object) -> list[str]:
    if isinstance(raw_snippet, list):
        return [str(line).rstrip() for line in raw_snippet if str(line).strip()]
    if isinstance(raw_snippet, str):
        return [line.rstrip() for line in raw_snippet.splitlines() if line.strip()]
    return []


def _adaptive_test_plan(
    signatures: list[dict[str, Any]],
    modules: list[str],
    *,
    start_index: int,
    count: int,
) -> list[dict[str, Any]]:
    """Describe regression guards for signatures that really failed before.

    These carry no snippet: they are reported as manual follow-ups rather than
    executed, because a template cannot meaningfully reproduce a past failure.
    """
    if count <= 0:
        return []

    module_pool = modules[:] if modules else ["CoreService"]
    selected: list[dict[str, Any]] = []

    for idx, entry in enumerate(signatures):
        if len(selected) >= count:
            break

        signature = _normalize_signature(str(entry.get("signature") or ""))
        if not signature:
            continue

        module_hint = str(entry.get("module") or "").strip() or module_pool[idx % len(module_pool)]
        tc_id = f"TC-{start_index + len(selected):03d}"
        selected.append(
            {
                "id": tc_id,
                "type": "regression",
                "module": module_hint,
                "description": f"Adaptive regression guard for {module_hint} targeting prior failure signature: {signature}.",
                "steps": [
                    "Prepare payload that recreates the historical failure path",
                    "Execute behavior contract for the same condition",
                    "Assert prior failure signature no longer reproduces",
                ],
                "expected_result": f"System behavior remains compliant for previously failing signature: {signature}.",
                "risk_level": "high",
                "automated": False,
                "automation_snippet": [],
                "skip_reason": "Regression guard derived from run history; needs a human-authored reproduction.",
                "learning_source": "adaptive",
                "derived_from_failure_signature": signature,
                "novelty_reason": "Generated from prior run failure signature.",
            }
        )

    return selected


def _attach_learning_evidence(items: list[dict[str, Any]], known_fingerprints: set[str]) -> list[dict[str, Any]]:
    stamped: list[dict[str, Any]] = []
    for item in items:
        learning_source = str(item.get("learning_source") or "baseline").strip().lower()
        if learning_source not in {"baseline", "adaptive"}:
            learning_source = "baseline"

        already_seen = _test_fingerprint(item) in known_fingerprints
        novelty_reason = str(item.get("novelty_reason") or "").strip()
        if not novelty_reason:
            if learning_source == "adaptive":
                novelty_reason = (
                    "Historical defect guard re-validated for consistency."
                    if already_seen
                    else "New targeted guard generated from historical defect pattern."
                )
            else:
                novelty_reason = (
                    "Known behavior path re-validated for stability."
                    if already_seen
                    else "New baseline behavior path introduced in this run."
                )

        stamped.append(
            {
                **item,
                "learning_source": learning_source,
                "derived_from_failure_signature": _normalize_signature(
                    str(item.get("derived_from_failure_signature") or "")
                ),
                "novelty_reason": novelty_reason,
            }
        )
    return stamped


def _normalize_test_items(raw_items: object, modules: list[str]) -> list[dict]:
    if not isinstance(raw_items, list):
        return []

    normalized: list[dict] = []
    module_fallback = modules[0] if modules else "CoreService"

    for idx, item in enumerate(raw_items, start=1):
        if not isinstance(item, dict):
            continue

        tc_type = str(item.get("type") or "functional").strip().lower()
        if tc_type not in _VALID_TYPES:
            tc_type = "functional"

        risk_level = str(item.get("risk_level") or "medium").strip().lower()
        if risk_level not in _VALID_RISKS:
            risk_level = "medium"

        lines = _coerce_snippet_lines(item.get("automation_snippet"))
        rejection = _snippet_rejection_reason(lines)

        normalized.append(
            {
                "id": str(item.get("id") or f"TC-{idx:03d}").strip(),
                "type": tc_type,
                "module": str(item.get("module") or module_fallback).strip() or module_fallback,
                "description": str(item.get("description") or "").strip(),
                "steps": item.get("steps") if isinstance(item.get("steps"), list) else [],
                "expected_result": str(item.get("expected_result") or "").strip(),
                "risk_level": risk_level,
                "automated": rejection is None,
                "automation_snippet": [] if rejection else lines,
                "skip_reason": rejection or "",
                "learning_source": "baseline",
                "derived_from_failure_signature": _normalize_signature(
                    item.get("derived_from_failure_signature")
                ),
                "novelty_reason": str(item.get("novelty_reason") or "").strip(),
            }
        )

    return normalized


async def generate_tests(
    story: StoryAnalysis,
    *,
    story_text: str | None = None,
    learning: dict[str, Any] | None = None,
) -> List[TestCase]:
    """Generate cases for a story, informed by prior runs of the same story.

    The learning context is injected rather than queried here so the agent
    holds no database session and the caller controls user scoping.
    """
    def _call_model() -> List[TestCase]:
        learning_context = learning or {}
        known_fingerprints = {
            str(item).strip()
            for item in learning_context.get("known_test_fingerprints", [])
            if str(item).strip()
        }
        recent_failure_signatures = [
            item
            for item in learning_context.get("recent_failure_signatures", [])
            if isinstance(item, dict) and str(item.get("signature") or "").strip()
        ]

        user_payload = {
            "modules": story.modules,
            "acceptance_criteria": story.acceptance_criteria,
            "risk_factors": story.risk_factors,
            "learning_context": {
                "total_runs": learning_context.get("total_runs", 0),
                "recent_failure_signatures": recent_failure_signatures[:6],
                "recurring_failure_signatures": learning_context.get("recurring_failure_signatures", [])[:6],
                "known_test_fingerprint_count": len(known_fingerprints),
            },
        }
        prompt = f"Input:\n{json.dumps(user_payload)}\nReturn only the JSON object with key test_cases."

        parsed = generate_json(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=prompt,
            max_output_tokens=3000,
            temperature=0.2,
        )
        raw_items = parsed.get("test_cases", parsed if isinstance(parsed, list) else [])
        normalized = _normalize_test_items(raw_items, story.modules)

        if recent_failure_signatures:
            normalized.extend(
                _adaptive_test_plan(
                    recent_failure_signatures,
                    story.modules,
                    start_index=len(normalized) + 1,
                    count=min(3, len(recent_failure_signatures)),
                )
            )

        normalized = _attach_learning_evidence(normalized, known_fingerprints)
        return [TestCase(**item) for item in normalized]

    return await asyncio.to_thread(_call_model)
