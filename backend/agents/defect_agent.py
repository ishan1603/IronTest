import asyncio
import json
from typing import List
import requests
from models import DefectAnalysis, ModuleRisk, StoryAnalysis, TestCase, TestExecutionSummary
from database import get_module_history_stats


SYSTEM_PROMPT = """
You are the Defect Intelligence Agent. You analyze test execution results and historical defect patterns to produce a predictive risk assessment.

For each module provided, assign:
- defect_probability: 0.0 to 1.0 (float) based on the provided history.
- historical_defect_count: integer (based on the provided data)
- regression_risk: 'low' | 'medium' | 'high' | 'critical'
- top_defect_types: string[] (2-3 defect categories)
- vulnerability_heatmap: string (e.g. 'Critical SQLi Exposure', 'Safe', 'High PII Risk')

Then compute:
- overall_confidence_score: integer 0-100 
  (100 = fully safe to deploy, 0 = do not deploy)
- deployment_recommendation: 'GO' | 'NO-GO' | 'CONDITIONAL GO'
- recommendation_rationale: string (2-3 sentences explaining why)
- critical_test_ids: string[] (IDs of highest-priority tests from the test suite)

Return JSON matching this schema:
{
  'module_risks': [{ 'module': string, 'defect_probability': float, 
    'historical_defect_count': int, 'regression_risk': string,
    'top_defect_types': string[], 'vulnerability_heatmap': string }],
  'overall_confidence_score': int,
  'deployment_recommendation': string,
  'recommendation_rationale': string,
  'critical_test_ids': string[]
}
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
  resp = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=120)
  if not resp.ok:
    raise requests.HTTPError(f"{resp.status_code} {resp.text}", response=resp)
  data = resp.json()
  return data.get("choices", [{}])[0].get("message", {}).get("content", "")


async def analyze_defects(token: str, model_id: str, story: StoryAnalysis, tests: List[TestCase], execution: TestExecutionSummary) -> DefectAnalysis:
  def _call_model() -> DefectAnalysis:
    
    historical_data = {
        m: get_module_history_stats(m) for m in story.modules
    }

    # Trim payload to prevent token limit errors
    trimmed_tests = []
    for test in tests:
        t_dict = test.model_dump()
        t_dict.pop("automation_snippet", None) # LLM doesn't need the code to assess risk
        trimmed_tests.append(t_dict)
    
    trimmed_execution = execution.model_dump()
    for res in trimmed_execution.get("results", []):
        if len(res.get("error_message", "")) > 300:
            res["error_message"] = res["error_message"][:300] + "... [truncated]"

    payload = {
      "modules": story.modules,
      "test_cases": trimmed_tests,
      "execution_summary": trimmed_execution,
      "module_history": historical_data
    }
    prompt = (
      "Input:\n"
      f"{json.dumps(payload)}\n"
      "Return ONLY the JSON object with keys: module_risks, overall_confidence_score, deployment_recommendation, recommendation_rationale, critical_test_ids."
    )
    response_text = _groq_chat(token, model_id, SYSTEM_PROMPT, prompt, max_tokens=768, temperature=0.25)
    data = _extract_json(response_text)
    
    # Ensure data is a dict and has defaults
    if not isinstance(data, dict):
        data = {}
        
    raw_module_risks = data.get("module_risks", [])
    module_risks = []
    for m in raw_module_risks:
        if isinstance(m, dict):
            module_risks.append(ModuleRisk(**m))
            
    return DefectAnalysis(
      module_risks=module_risks,
      overall_confidence_score=data.get("overall_confidence_score", 50), # Default to neutral if failed
      deployment_recommendation=data.get("deployment_recommendation", "CONDITIONAL GO"),
      recommendation_rationale=data.get("recommendation_rationale", "Automated analysis partially incomplete."),
      critical_test_ids=data.get("critical_test_ids", []),
    )

  return await asyncio.to_thread(_call_model)
