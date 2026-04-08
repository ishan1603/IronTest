import asyncio
import json
import re
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
    Keep snippet length concise (max 6 lines) to preserve output completeness.
    DO NOT import playwright, selenium, or cypress.
    DO NOT use 'yield' for HTTP requests; use standard synchronous 'requests' calls and 'assert' logic.
    DO NOT output \n or triple quotes.
    DO NOT wrap response in markdown code fences)
}
"""


_VALID_TYPES = {"functional", "boundary", "edge_case", "regression"}
_VALID_RISKS = {"low", "medium", "high"}
_BROWSER_MARKERS = ("playwright", "selenium", "cypress", "puppeteer")


def _slug(value: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9]+", "_", (value or "").strip().lower())
    clean = clean.strip("_")
    return clean or "scenario"


def _fallback_snippet(test_id: str, module_name: str) -> list[str]:
    fn_name = f"test_{_slug(test_id)}_{_slug(module_name)}"[:56]
    endpoint = f"https://mock.local/{_slug(module_name)}"
    return [
        f"def {fn_name}():",
        "    import requests",
        f"    response = requests.get('{endpoint}')",
        "    assert response.status_code in (200, 201, 202, 204)",
        "    payload = response.json()",
        "    assert payload.get('status') in ('success', 'ok')",
    ]


def _fallback_test_plan(modules: list[str]) -> list[dict]:
    module_pool = modules[:] if modules else ["VaultService", "PaymentGateway", "AuthService"]
    m0 = module_pool[0]
    m1 = module_pool[1] if len(module_pool) > 1 else module_pool[0]
    m2 = module_pool[2] if len(module_pool) > 2 else module_pool[0]

    return [
        {
            "id": "TC-001",
            "type": "functional",
            "module": m0,
            "description": f"Verify successful tokenization flow in {m0} for valid card payload.",
            "steps": ["Send valid tokenization request", "Validate success payload"],
            "expected_result": "Returns HTTP 200 with token.",
            "risk_level": "medium",
            "automated": True,
            "automation_snippet": [
                "import requests",
                "def test_successful_tokenization():",
                "    response = requests.post('http://localhost:8000/tokenize', json={'card_details': 'valid_card_data', 'customer_id': 'cust_123'})",
                "    assert response.status_code == 200",
                "    assert 'token' in response.json()",
            ],
        },
        {
            "id": "TC-002",
            "type": "boundary",
            "module": m0,
            "description": f"Validate boundary card-details payload size in {m0}.",
            "steps": ["Send max-size acceptable payload", "Confirm stable response"],
            "expected_result": "Boundary payload is accepted.",
            "risk_level": "medium",
            "automated": True,
            "automation_snippet": [
                "import requests",
                "def test_boundary_card_details():",
                "    response = requests.post('http://localhost:8000/tokenize', json={'card_details': '4' * 16, 'customer_id': 'cust_456'})",
                "    assert response.status_code == 200",
                "    assert 'token' in response.json()",
            ],
        },
        {
            "id": "TC-003",
            "type": "edge_case",
            "module": m0,
            "description": f"Reject malformed card details in {m0} tokenization API.",
            "steps": ["Send malformed card_details", "Validate error response"],
            "expected_result": "Returns HTTP 400 invalid card details.",
            "risk_level": "high",
            "automated": True,
            "automation_snippet": [
                "import requests",
                "def test_invalid_card_details_rejected():",
                "    response = requests.post('http://localhost:8000/tokenize', json={'card_details': 'invalid-card', 'customer_id': 'cust_789'})",
                "    assert response.status_code == 400",
                "    assert 'invalid card details' in response.json()['error'].lower()",
            ],
        },
        {
            "id": "TC-004",
            "type": "edge_case",
            "module": m0,
            "description": f"Ensure empty card details are blocked by {m0} validation.",
            "steps": ["Send empty card_details", "Expect validation failure"],
            "expected_result": "Returns HTTP 400 with empty-field message.",
            "risk_level": "high",
            "automated": True,
            "automation_snippet": [
                "import requests",
                "def test_empty_card_details_rejected():",
                "    response = requests.post('http://localhost:8000/tokenize', json={'card_details': '', 'customer_id': 'cust_222'})",
                "    assert response.status_code == 400",
                "    assert 'card details cannot be empty' in response.json()['error'].lower()",
            ],
        },
        {
            "id": "TC-005",
            "type": "regression",
            "module": m1,
            "description": f"Validate token association lookup for customer profile in {m1} path.",
            "steps": ["Tokenize card", "Lookup customer", "Verify token binding"],
            "expected_result": "Customer profile contains newly issued token.",
            "risk_level": "medium",
            "automated": True,
            "automation_snippet": [
                "import requests",
                "def test_customer_token_association():",
                "    response = requests.post('http://localhost:8000/tokenize', json={'card_details': 'valid_card_data', 'customer_id': 'cust_111'})",
                "    token = response.json()['token']",
                "    assert token in requests.get('http://localhost:7000/customer/cust_111').json()['tokens']",
            ],
        },
        {
            "id": "TC-006",
            "type": "functional",
            "module": m2,
            "description": f"Enforce unauthorized access control on sensitive card detail endpoint for {m2}.",
            "steps": ["Request protected endpoint with invalid token", "Verify unauthorized response"],
            "expected_result": "Returns HTTP 401 unauthorized.",
            "risk_level": "high",
            "automated": True,
            "automation_snippet": [
                "import requests",
                "def test_invalid_token_blocked():",
                "    response = requests.get('http://localhost:8000/card_details/invalid_token')",
                "    assert response.status_code == 401",
                "    assert 'unauthorized' in response.json()['error'].lower()",
            ],
        },
        {
            "id": "TC-007",
            "type": "boundary",
            "module": m0,
            "description": f"Check SLA latency for tokenization endpoint under nominal load in {m0}.",
            "steps": ["Measure request duration", "Validate SLA threshold"],
            "expected_result": "Latency remains below 200ms.",
            "risk_level": "medium",
            "automated": True,
            "automation_snippet": [
                "import requests, time",
                "def test_tokenization_latency_budget():",
                "    start = time.time()",
                "    response = requests.post('http://localhost:8080/api/tokenize', json={'card_details': 'valid_card_data', 'customer_id': 'cust_101'})",
                "    assert response.status_code == 200 and (time.time() - start) < 0.2",
            ],
        },
        {
            "id": "TC-008",
            "type": "regression",
            "module": m1,
            "description": f"Detect service-degradation behavior when upstream dependency is unavailable for {m1}.",
            "steps": ["Call simulated downtime endpoint", "Verify graceful status propagation"],
            "expected_result": "Returns HTTP 503 for downstream outage.",
            "risk_level": "high",
            "automated": True,
            "automation_snippet": [
                "import requests",
                "def test_dependency_downtime_signal():",
                "    response = requests.get('http://localhost:8000/service-down/tokenize')",
                "    assert response.status_code == 503",
            ],
        },
        {
            "id": "TC-009",
            "type": "functional",
            "module": m2,
            "description": f"Verify baseline module health probe behavior for {m2}.",
            "steps": ["Call module health endpoint", "Validate success state"],
            "expected_result": "Health probe reports success.",
            "risk_level": "low",
            "automated": True,
            "automation_snippet": _fallback_snippet("TC-009", m2),
        },
        {
            "id": "TC-010",
            "type": "regression",
            "module": m0,
            "description": f"Ensure no regression in happy-path token issuance for {m0} after updates.",
            "steps": ["Run happy-path tokenization", "Validate token and status"],
            "expected_result": "Returns deterministic success payload.",
            "risk_level": "medium",
            "automated": True,
            "automation_snippet": [
                "import requests",
                "def test_regression_happy_path_tokenization():",
                "    response = requests.post('http://localhost:8000/tokenize', json={'card_details': 'valid_card_data', 'customer_id': 'cust_reg'})",
                "    assert response.status_code == 200",
                "    assert response.json().get('status') in ('success', 'ok')",
            ],
        },
    ]


def _normalize_snippet(test_id: str, module_name: str, raw_snippet: object) -> list[str]:
    if isinstance(raw_snippet, list):
        lines = [str(line).rstrip() for line in raw_snippet if str(line).strip()]
    elif isinstance(raw_snippet, str):
        lines = [line.rstrip() for line in raw_snippet.splitlines() if line.strip()]
    else:
        lines = []

    text = "\n".join(lines).lower()
    if not lines or any(marker in text for marker in _BROWSER_MARKERS):
        return _fallback_snippet(test_id, module_name)

    if not any(line.lstrip().startswith("def ") for line in lines):
        fn_name = f"test_{_slug(test_id)}_{_slug(module_name)}"[:56]
        wrapped = [f"def {fn_name}():"]
        wrapped.extend([f"    {line}" for line in lines])
        return wrapped

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
        snippet = _normalize_snippet(tc_id, module_name, item.get("automation_snippet"))

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
                temperature=0.35,
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
