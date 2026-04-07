import asyncio
import json
from typing import List

from llm_client import gemini_generate_json
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
    "automation_snippet": string[] (Array of strings, each string is a single line of a Pytest/Playwright script.
    IMPORTANT: You MUST wrap the code in a function like 'def test_scenario():' and indent the body.
    Keep snippet length concise (max 6 lines) to preserve output completeness.
    DO NOT use 'yield' for HTTP requests; use standard synchronous 'requests' calls and 'assert' logic.
    DO NOT output \n or triple quotes.
    DO NOT wrap response in markdown code fences)
}
"""


async def generate_tests(token: str, model_id: str, story: StoryAnalysis) -> List[TestCase]:
    def _call_model() -> List[TestCase]:
        user_payload = {
            "modules": story.modules,
            "acceptance_criteria": story.acceptance_criteria,
            "risk_factors": story.risk_factors,
        }
        prompt = f"Input:\n{json.dumps(user_payload)}\nReturn only the JSON object with key test_cases."
        parsed = gemini_generate_json(
            api_key=token,
            model_id=model_id,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=prompt,
            max_output_tokens=3000,
            temperature=0.35,
        )
        raw_items = parsed.get("test_cases", parsed if isinstance(parsed, list) else [])
        return [TestCase(**item) for item in raw_items]

    return await asyncio.to_thread(_call_model)
