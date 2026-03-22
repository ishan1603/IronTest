import asyncio
import json
from typing import List
import requests
from models import StoryAnalysis, TestCase


SYSTEM_PROMPT = """
You are the Test Generation Agent in an autonomous QA system.
Given acceptance criteria, modules, and risk factors, generate 10-15 test cases covering functional, boundary, edge/negative, and regression/security risks.

Respond strictly as a JSON object with a single key "test_cases" whose value is an array of objects shaped as:
{
    "id": string (TC-001 format),
    "type": "functional" | "boundary" | "edge_case" | "regression",
    "module": string,
    "description": string,
    "steps": string[],
    "expected_result": string,
    "risk_level": "low" | "medium" | "high",
    "automated": boolean
}
"""


def _extract_json(text: str):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Fallback: try to isolate the first JSON object/array in the text
        start = text.find("{")
        end = text.rfind("}")
        snippet = text[start : end + 1] if start != -1 and end != -1 else text
        return json.loads(snippet)


def _groq_chat(token: str, model_id: str, system_prompt: str, user_content: str, max_tokens: int, temperature: float) -> str:
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
        "response_format": {"type": "json_object"},
    }
    resp = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=120)
    if not resp.ok:
        raise requests.HTTPError(f"{resp.status_code} {resp.text}", response=resp)
    data = resp.json()
    return data.get("choices", [{}])[0].get("message", {}).get("content", "")


async def generate_tests(token: str, model_id: str, story: StoryAnalysis) -> List[TestCase]:
    def _call_model() -> List[TestCase]:
        user_payload = {
            "modules": story.modules,
            "acceptance_criteria": story.acceptance_criteria,
            "risk_factors": story.risk_factors,
        }
        prompt = f"Input:\n{json.dumps(user_payload)}\nReturn only the JSON object with key test_cases."
        response_text = _groq_chat(token, model_id, SYSTEM_PROMPT, prompt, max_tokens=768, temperature=0.35)
        parsed = _extract_json(response_text)
        raw_items = parsed.get("test_cases", parsed if isinstance(parsed, list) else [])
        return [TestCase(**item) for item in raw_items]

    return await asyncio.to_thread(_call_model)
