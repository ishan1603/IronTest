import asyncio
import json
import requests
from models import StoryAnalysis


SYSTEM_PROMPT = """
You are the Story Intelligence Agent in an autonomous QA system. 
Your job is to analyze a Jira user story and extract:
1. Business intent (1 sentence)
2. Affected modules (list of 3-6 module names like 'PaymentGateway', 'AuthService', 'NotificationEngine', etc.)
3. Acceptance criteria (bullet list)
4. Risk factors (what could go wrong, 2-4 items)
5. Security vectors (potential attack surfaces, e.g., 'SQLi in form', 'OAuth token hijack', list of 2-3 items)
6. Microservices (list of likely microservices involved, e.g., 'auth-service', 'billing-db')
Respond ONLY as a JSON object with keys intent, modules, acceptance_criteria, risk_factors, security_vectors, microservices.
"""


def _extract_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
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
    resp = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=90)
    if not resp.ok:
        raise requests.HTTPError(f"{resp.status_code} {resp.text}", response=resp)
    data = resp.json()
    return data.get("choices", [{}])[0].get("message", {}).get("content", "")


async def analyze_story(token: str, model_id: str, user_story: str) -> StoryAnalysis:
    def _call_model() -> StoryAnalysis:
        prompt = (
            "User Story:\n"
            f"{user_story}\n\nReturn ONLY the JSON object with keys: intent, modules, acceptance_criteria, risk_factors, security_vectors, microservices."
        )
        response_text = _groq_chat(token, model_id, SYSTEM_PROMPT, prompt, max_tokens=512, temperature=0.3)
        data = _extract_json(response_text)
        return StoryAnalysis(**data)

    return await asyncio.to_thread(_call_model)
