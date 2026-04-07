import asyncio

from llm_client import gemini_generate_json
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


async def analyze_story(token: str, model_id: str, user_story: str) -> StoryAnalysis:
    def _call_model() -> StoryAnalysis:
        prompt = (
            "User Story:\n"
            f"{user_story}\n\nReturn ONLY the JSON object with keys: intent, modules, acceptance_criteria, risk_factors, security_vectors, microservices."
        )
        data = gemini_generate_json(
            api_key=token,
            model_id=model_id,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=prompt,
            max_output_tokens=900,
            temperature=0.3,
        )
        return StoryAnalysis(**data)

    return await asyncio.to_thread(_call_model)
