import asyncio

from llm import generate_json
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


def _to_string_list(value: object, *, min_items: int = 0) -> list[str]:
    if not isinstance(value, list):
        return []
    cleaned = [str(item).strip() for item in value if str(item).strip()]
    return cleaned if len(cleaned) >= min_items else []


def _validate_story(data: dict, user_story: str) -> StoryAnalysis:
    intent = str(data.get("intent", "")).strip()
    modules = _to_string_list(data.get("modules"), min_items=1)
    acceptance_criteria = _to_string_list(data.get("acceptance_criteria"), min_items=1)
    risk_factors = _to_string_list(data.get("risk_factors"), min_items=1)
    security_vectors = _to_string_list(data.get("security_vectors"), min_items=1)
    microservices = _to_string_list(data.get("microservices"), min_items=1)

    if len(intent) < 12:
        raise ValueError("Model returned invalid business intent.")
    if not modules:
        raise ValueError("Model returned no affected modules.")
    if not acceptance_criteria:
        raise ValueError("Model returned no acceptance criteria.")

    # Keep the output tied to the submitted story by requiring overlap with story vocabulary.
    story_tokens = {token.lower() for token in user_story.replace("\n", " ").split() if len(token) > 4}
    intent_tokens = {token.lower().strip(".,:;()[]{}") for token in intent.split() if len(token) > 4}
    if story_tokens and intent_tokens and not (story_tokens & intent_tokens):
        raise ValueError("Business intent appears unrelated to the submitted story.")

    return StoryAnalysis(
        intent=intent,
        modules=modules[:8],
        acceptance_criteria=acceptance_criteria[:10],
        risk_factors=risk_factors[:8],
        security_vectors=security_vectors[:8],
        microservices=microservices[:8],
    )


async def analyze_story(user_story: str) -> StoryAnalysis:
    def _call_model() -> StoryAnalysis:
        base_prompt = (
            "User Story:\n"
            f"{user_story}\n\n"
            "Return ONLY the JSON object with keys: intent, modules, acceptance_criteria, risk_factors, security_vectors, microservices.\n"
            "Constraints: intent must be exactly one sentence and directly derived from this user story text."
        )

        last_error: Exception | None = None
        for attempt in range(2):
            prompt = base_prompt
            if attempt == 1:
                prompt += (
                    "\nValidation reminder: provide non-empty arrays for modules, acceptance_criteria, risk_factors,"
                    " security_vectors, and microservices."
                )

            data = generate_json(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=prompt,
                max_output_tokens=900,
                temperature=0.3,
            )
            try:
                return _validate_story(data, user_story)
            except Exception as exc:  # noqa: BLE001
                last_error = exc

        raise RuntimeError(f"Story intelligence generation failed: {last_error}")

    return await asyncio.to_thread(_call_model)
