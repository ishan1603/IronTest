import asyncio
import json
from typing import List

from database import get_global_history_stats, get_module_history_stats
from llm_client import gemini_generate_json
from models import DefectAnalysis, ModuleRisk, StoryAnalysis, TestCase, TestExecutionSummary


SYSTEM_PROMPT = """
You are the Defect Intelligence Agent. Analyze test execution plus historical defect trends and produce a predictive release risk assessment.

Output strictly as JSON with these keys:
- module_risks: array of objects with module, defect_probability, historical_defect_count, regression_risk, top_defect_types, vulnerability_heatmap
- overall_confidence_score: integer 0-100
- deployment_recommendation: GO | NO-GO | CONDITIONAL GO
- recommendation_rationale: 2-3 sentence rationale grounded in execution + history
- critical_test_ids: list of highest-priority test case IDs

Rules:
- Probability must be 0.0 to 1.0.
- Regression risk must be low, medium, high, or critical.
- Keep recommendations conservative if recent failures are high.
"""


def _risk_from_probability(probability: float) -> str:
    if probability >= 0.75:
        return "critical"
    if probability >= 0.55:
        return "high"
    if probability >= 0.3:
        return "medium"
    return "low"

def _blended_confidence_score(llm_score: int, execution: TestExecutionSummary, global_history: dict) -> int:
    total = max(1, len(execution.results))
    passed = sum(1 for r in execution.results if r.status == "pass")
    failed = sum(1 for r in execution.results if r.status == "fail")
    errors = sum(1 for r in execution.results if r.status == "error")

    current_pass_rate = passed / total
    historical_pass_rate = float(global_history.get("average_pass_rate", 0.5))
    recent_pass_rate = float(global_history.get("recent_pass_rate", historical_pass_rate))
    trend_delta = recent_pass_rate - historical_pass_rate

    blended = (
        (0.45 * llm_score)
        + (35 * current_pass_rate)
        + (20 * historical_pass_rate)
        + (trend_delta * 20)
        - (failed * 1.8)
        - (errors * 3.2)
    )
    return max(0, min(100, int(round(blended))))


def _recommendation(score: int, execution: TestExecutionSummary) -> str:
    has_errors = any(r.status == "error" for r in execution.results)
    if score < 45 or has_errors and score < 60:
        return "NO-GO"
    if score < 72:
        return "CONDITIONAL GO"
    return "GO"


async def analyze_defects(token: str, model_id: str, story: StoryAnalysis, tests: List[TestCase], execution: TestExecutionSummary) -> DefectAnalysis:
  def _call_model() -> DefectAnalysis:
    historical_data = {m: get_module_history_stats(m) for m in story.modules}
    global_history = get_global_history_stats()

    trimmed_tests = []
    for test in tests:
      t_dict = test.model_dump()
      t_dict.pop("automation_snippet", None)
      trimmed_tests.append(t_dict)

    trimmed_execution = execution.model_dump()
    for res in trimmed_execution.get("results", []):
      if len(res.get("error_message", "")) > 300:
        res["error_message"] = res["error_message"][:300] + "... [truncated]"

    payload = {
      "modules": story.modules,
      "test_cases": trimmed_tests,
      "execution_summary": trimmed_execution,
      "module_history": historical_data,
      "global_history": global_history,
    }
    prompt = (
      "Input:\n"
      f"{json.dumps(payload)}\n"
      "Return ONLY the JSON object with keys: module_risks, overall_confidence_score, deployment_recommendation, recommendation_rationale, critical_test_ids."
    )

    data = gemini_generate_json(
      api_key=token,
      model_id=model_id,
      system_prompt=SYSTEM_PROMPT,
      user_prompt=prompt,
      max_output_tokens=1400,
      temperature=0.2,
    )

    module_risks: list[ModuleRisk] = []
    seen_modules: set[str] = set()

    for item in data.get("module_risks", []):
      if not isinstance(item, dict):
        continue
      try:
        risk = ModuleRisk(**item)
        module_risks.append(risk)
        seen_modules.add(risk.module)
      except Exception:
        continue

    for module_name in story.modules:
      if module_name in seen_modules:
        continue
      stats = historical_data.get(module_name, {})
      probability = float(stats.get("defect_probability", 0.25))
      module_risks.append(
        ModuleRisk(
          module=module_name,
          defect_probability=max(0.0, min(1.0, probability)),
          historical_defect_count=int(stats.get("historical_defect_count", 0)),
          regression_risk=_risk_from_probability(probability),
          top_defect_types=["validation", "integration"],
          vulnerability_heatmap="Needs monitoring",
        )
      )

    llm_score_raw = data.get("overall_confidence_score", 50)
    try:
      llm_score = int(float(llm_score_raw))
    except (TypeError, ValueError):
      llm_score = 50
    blended_score = _blended_confidence_score(llm_score, execution, global_history)
    recommendation = _recommendation(blended_score, execution)

    passed = sum(1 for r in execution.results if r.status == "pass")
    total = max(1, len(execution.results))
    default_rationale = (
      f"Execution pass rate is {round((passed / total) * 100)}% and historical average pass rate is "
      f"{round(float(global_history.get('average_pass_rate', 0.5)) * 100)}%. "
      "Recommendation balances current failures with historical stability trends."
    )

    critical_ids = data.get("critical_test_ids", [])
    if not isinstance(critical_ids, list) or not critical_ids:
      critical_ids = [t.id for t in tests if t.risk_level == "high"][:5]

    rationale = data.get("recommendation_rationale", "")
    if not isinstance(rationale, str) or not rationale.strip():
      rationale = default_rationale

    return DefectAnalysis(
      module_risks=module_risks,
      overall_confidence_score=blended_score,
      deployment_recommendation=recommendation,
      recommendation_rationale=rationale,
      critical_test_ids=critical_ids,
    )

  return await asyncio.to_thread(_call_model)
