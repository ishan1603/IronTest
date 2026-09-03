import asyncio
import json
from typing import List

from llm import generate_json
from models import (
  DefectAnalysis,
  HistoricalComparison,
  ModuleRisk,
  ScoreBreakdown,
  StoryAnalysis,
  TestCase,
  TestExecutionSummary,
)


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


def _risk_rank(level: str) -> int:
    return {"high": 3, "medium": 2, "low": 1}.get((level or "").lower(), 0)


def _normalize_recommendation(value: object) -> str:
  text = str(value or "").strip().upper()
  if text in {"GO", "NO-GO", "CONDITIONAL GO"}:
    return text
  compact = text.replace("_", " ").replace("-", " ").strip()
  if compact == "NOGO":
    return "NO-GO"
  if compact == "CONDITIONAL GO":
    return "CONDITIONAL GO"
  raise ValueError(f"Invalid deployment recommendation from model: {value}")


def _clamp(value: float, lower: float, upper: float) -> float:
  return max(lower, min(upper, value))


def _normalize_module_name(value: str) -> str:
  return "".join(ch for ch in str(value or "").lower() if ch.isalnum())


def _trend_from_delta(delta: float) -> str:
  if delta > 0.08:
    return "improving"
  if delta < -0.08:
    return "declining"
  return "stable"


def _module_execution_snapshot(
  *,
  module_name: str,
  tests: list[TestCase],
  execution: TestExecutionSummary,
) -> dict:
  target = _normalize_module_name(module_name)
  module_test_ids = {
    test.id
    for test in tests
    if _normalize_module_name(test.module) == target
  }
  module_results = [item for item in execution.results if item.test_id in module_test_ids]

  total = len(module_results)
  passed = sum(1 for item in module_results if item.status == "pass")
  failed = sum(1 for item in module_results if item.status == "fail")
  errors = sum(1 for item in module_results if item.status == "error")
  skipped = sum(1 for item in module_results if item.status == "skipped")
  pass_rate = passed / max(1, total)

  return {
    "test_count": total,
    "passed": passed,
    "failed": failed,
    "errors": errors,
    "skipped": skipped,
    "pass_rate": pass_rate,
  }


def _module_risk_drivers(
  *,
  probability: float,
  historical_defect_count: int,
  snapshot: dict,
  pass_rate_delta: float,
) -> list[str]:
  drivers: list[str] = []
  if snapshot["errors"] > 0:
    drivers.append("Execution errors detected in current run")
  if snapshot["failed"] > 0:
    drivers.append("Assertion failures in module-specific tests")
  if probability >= 0.6:
    drivers.append("High historical defect probability")
  if historical_defect_count >= 12:
    drivers.append("Recurring defect volume is elevated")
  if snapshot["test_count"] < 2:
    drivers.append("Coverage is thin for this module")
  if pass_rate_delta < -0.1:
    drivers.append("Current pass rate dropped below historical baseline")
  return drivers[:4] if drivers else ["No acute risk driver detected"]


def _module_recommended_actions(snapshot: dict, trend: str, probability: float) -> list[str]:
  actions: list[str] = []
  if snapshot["errors"] > 0:
    actions.append("Stabilize dependencies and environment setup for flaky execution paths")
  if snapshot["failed"] > 0:
    actions.append("Add focused regression tests for failing assertions before release")
  if snapshot["test_count"] < 2:
    actions.append("Increase functional and boundary test coverage for this module")
  if trend == "declining":
    actions.append("Perform root-cause analysis on recent quality regression")
  if probability >= 0.7:
    actions.append("Schedule targeted hardening sprint due to high historical risk")
  return actions[:3] if actions else ["Continue monitoring with routine regression checks"]


def _stable_module_probability(
  *,
  historical_probability: float,
  llm_probability: float,
  snapshot: dict,
) -> float:
  executed = max(1, int(snapshot.get("test_count", 0)))
  failed = int(snapshot.get("failed", 0))
  errors = int(snapshot.get("errors", 0))
  exec_pressure = min(1.0, (failed + errors) / executed)

  base = (historical_probability * 0.75) + (exec_pressure * 0.2) + (llm_probability * 0.05)
  return _clamp(base, 0.0, 1.0)


def _stable_ai_score(*, llm_score: int, execution: TestExecutionSummary, global_history: dict) -> int:
  passed = sum(1 for item in execution.results if item.status == "pass")
  failed = sum(1 for item in execution.results if item.status == "fail")
  errors = sum(1 for item in execution.results if item.status == "error")
  evaluated = max(1, passed + failed + errors)
  current = (passed / evaluated) * 100.0
  historical = float(global_history.get("average_pass_rate", 0.0)) * 100.0

  deterministic_anchor = (current * 0.8) + (historical * 0.2)
  blended = (deterministic_anchor * 0.85) + (llm_score * 0.15)
  return int(round(_clamp(blended, 0.0, 100.0)))


def _module_attack_surface(module_name: str) -> str:
  name = (module_name or "").lower()
  if any(token in name for token in ["auth", "login", "identity", "session", "token"]):
    return "auth/session abuse and privilege escalation"
  if any(token in name for token in ["payment", "card", "checkout", "billing", "refund"]):
    return "payment tampering and sensitive financial data exposure"
  if any(token in name for token in ["search", "ranking", "filter", "autosuggest", "query"]):
    return "query manipulation, relevance poisoning, and cache abuse"
  if any(token in name for token in ["inventory", "order", "booking", "reservation"]):
    return "race-condition consistency gaps and stale-state updates"
  if any(token in name for token in ["notification", "email", "sms", "alert"]):
    return "message spoofing and replay-trigger abuse"
  return "input validation bypass and authorization drift"


def _resolved_vulnerability_vector(
  *,
  module_name: str,
  model_vector: str,
  top_defect_types: list[str],
  snapshot: dict,
  probability: float,
) -> str:
  cleaned = str(model_vector or "").strip()
  normalized = cleaned.lower()
  if cleaned and normalized not in {"needs monitoring", "monitoring", "needs-monitoring"}:
    return cleaned

  surface = _module_attack_surface(module_name)
  patterns = ", ".join(top_defect_types[:2]) if top_defect_types else "validation gaps"

  if snapshot["errors"] > 0:
    signal = "runtime instability observed"
  elif snapshot["failed"] > 0:
    signal = "assertion regressions observed"
  elif snapshot["test_count"] == 0:
    signal = "coverage blind spot (no module-mapped tests)"
  else:
    signal = "no immediate runtime regression"

  severity = "high" if probability >= 0.65 else "medium" if probability >= 0.35 else "low"
  return f"{surface}; signal: {signal}; patterns: {patterns}; severity: {severity}."


def _recommendation_rank(value: str) -> int:
  return {"GO": 1, "CONDITIONAL GO": 2, "NO-GO": 3}.get(value, 3)


def _derive_recommendation_from_execution(score: int, execution: TestExecutionSummary) -> str:
  total = len(execution.results)
  failed = sum(1 for item in execution.results if item.status == "fail")
  errors = sum(1 for item in execution.results if item.status == "error")
  fail_rate = failed / max(1, total)

  if errors > 0 or fail_rate >= 0.35 or score < 45:
    return "NO-GO"
  if failed > 0 or score < 75:
    return "CONDITIONAL GO"
  return "GO"


def _compute_score(
  *,
  ai_score: int,
  execution: TestExecutionSummary,
  global_history: dict,
  module_risks: list[ModuleRisk],
) -> tuple[int, ScoreBreakdown, HistoricalComparison]:
  total = len(execution.results)
  passed = sum(1 for item in execution.results if item.status == "pass")
  failed = sum(1 for item in execution.results if item.status == "fail")
  errors = sum(1 for item in execution.results if item.status == "error")
  skipped = sum(1 for item in execution.results if item.status == "skipped")
  evaluated_total = passed + failed + errors

  current_pass_rate = passed / max(1, evaluated_total)
  fail_rate = failed / max(1, evaluated_total)
  error_rate = errors / max(1, evaluated_total)
  skipped_rate = skipped / max(1, total)

  historical_avg_pass_rate = float(global_history.get("average_pass_rate", 0.0))
  recent_pass_rate = float(global_history.get("recent_pass_rate", historical_avg_pass_rate))
  total_runs = int(global_history.get("total_runs", 0))

  # First-run bootstrap: avoid penalizing confidence because history does not exist yet.
  if total_runs == 0:
    historical_avg_pass_rate = current_pass_rate
    recent_pass_rate = current_pass_rate

  avg_module_risk = sum(item.defect_probability for item in module_risks) / max(1, len(module_risks))

  current_score = round(current_pass_rate * 100)
  historical_score = round(((historical_avg_pass_rate + recent_pass_rate) / 2.0) * 100)
  trend_delta_recent = current_pass_rate - recent_pass_rate
  trend_adjustment = round(_clamp(trend_delta_recent * 25.0, -8.0, 8.0))
  raw_module_risk_penalty = round(_clamp(avg_module_risk * 18.0, 0.0, 18.0))
  raw_execution_penalty = round(_clamp((fail_rate * 24.0) + (error_rate * 35.0) + (skipped_rate * 2.0), 0.0, 40.0))

  if total_runs == 0:
    weighted_base = (ai_score * 0.25) + (current_score * 0.75)
    module_risk_penalty = round(raw_module_risk_penalty * 0.5)
    execution_penalty = round(raw_execution_penalty * 0.5)
  else:
    weighted_base = (ai_score * 0.38) + (current_score * 0.47) + (historical_score * 0.15)
    module_risk_penalty = raw_module_risk_penalty
    execution_penalty = raw_execution_penalty

  final_score = round(
    _clamp(
      weighted_base + trend_adjustment - module_risk_penalty - execution_penalty,
      5.0,
      100.0,
    )
  )

  delta_vs_average = current_pass_rate - historical_avg_pass_rate
  delta_vs_recent = current_pass_rate - recent_pass_rate
  if delta_vs_recent > 0.03:
    trend = "improving"
  elif delta_vs_recent < -0.03:
    trend = "declining"
  else:
    trend = "stable"

  breakdown = ScoreBreakdown(
    llm_score=ai_score,
    current_pass_rate=round(current_pass_rate, 4),
    current_score=current_score,
    historical_average_pass_rate=round(historical_avg_pass_rate, 4),
    historical_score=historical_score,
    recent_pass_rate=round(recent_pass_rate, 4),
    trend_delta_recent=round(trend_delta_recent, 4),
    trend_adjustment=trend_adjustment,
    module_risk_penalty=module_risk_penalty,
    execution_penalty=execution_penalty,
    final_score=final_score,
  )
  comparison = HistoricalComparison(
    total_runs=total_runs,
    current_pass_rate=round(current_pass_rate, 4),
    historical_average_pass_rate=round(historical_avg_pass_rate, 4),
    recent_pass_rate=round(recent_pass_rate, 4),
    delta_vs_average=round(delta_vs_average, 4),
    delta_vs_recent=round(delta_vs_recent, 4),
    trend=trend,
  )
  return final_score, breakdown, comparison


async def analyze_defects(
  story: StoryAnalysis,
  tests: List[TestCase],
  execution: TestExecutionSummary,
  *,
  module_history: dict[str, dict] | None = None,
  global_history: dict | None = None,
) -> DefectAnalysis:
  """Score release confidence from this run plus the caller's history.

  History is injected rather than queried here so the agent stays free of a
  database session and the caller controls user scoping.
  """
  def _call_model() -> DefectAnalysis:
    historical_data = module_history or {}
    global_stats = global_history or {"total_runs": 0, "average_pass_rate": 0.0, "recent_pass_rate": 0.0}

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
      "story_intelligence": {
        "intent": story.intent,
        "modules": story.modules,
        "acceptance_criteria": story.acceptance_criteria,
        "risk_factors": story.risk_factors,
        "security_vectors": story.security_vectors,
        "microservices": story.microservices,
      },
      "test_cases": trimmed_tests,
      "execution_summary": trimmed_execution,
      "module_history": historical_data,
      "global_history": global_stats,
    }
    prompt = (
      "Input:\n"
      f"{json.dumps(payload)}\n"
      "Return ONLY the JSON object with keys: module_risks, overall_confidence_score, deployment_recommendation, recommendation_rationale, critical_test_ids."
    )

    data = generate_json(
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

    enriched_module_risks: list[ModuleRisk] = []
    for risk in module_risks:
      stats = historical_data.get(risk.module, {})
      total_runs_for_module = int(stats.get("total_runs", 0))
      historical_pass_rate = float(stats.get("historical_pass_rate", 0.0))
      snapshot = _module_execution_snapshot(module_name=risk.module, tests=tests, execution=execution)
      pass_rate_delta = snapshot["pass_rate"] - historical_pass_rate
      trend = "first_run" if total_runs_for_module == 0 else _trend_from_delta(pass_rate_delta)
      historical_probability = float(stats.get("defect_probability", 0.2))
      stable_probability = _stable_module_probability(
        historical_probability=historical_probability,
        llm_probability=float(risk.defect_probability),
        snapshot=snapshot,
      )

      raw_top_types = list(risk.top_defect_types or [])
      if snapshot["errors"] > 0 and "runtime_error" not in raw_top_types:
        raw_top_types.append("runtime_error")
      if snapshot["failed"] > 0 and "assertion_failure" not in raw_top_types:
        raw_top_types.append("assertion_failure")

      vulnerability_heatmap = _resolved_vulnerability_vector(
        module_name=risk.module,
        model_vector=risk.vulnerability_heatmap,
        top_defect_types=raw_top_types,
        snapshot=snapshot,
        probability=stable_probability,
      )

      enriched_module_risks.append(
        ModuleRisk(
          module=risk.module,
          defect_probability=round(stable_probability, 4),
          historical_defect_count=int(stats.get("historical_defect_count", risk.historical_defect_count)),
          regression_risk=_risk_from_probability(stable_probability),
          top_defect_types=raw_top_types[:5],
          vulnerability_heatmap=vulnerability_heatmap,
          module_test_count=snapshot["test_count"],
          module_pass_rate=round(snapshot["pass_rate"], 4),
          module_failed=snapshot["failed"],
          module_errors=snapshot["errors"],
          module_skipped=snapshot["skipped"],
          historical_pass_rate=round(historical_pass_rate, 4),
          pass_rate_delta=round(pass_rate_delta, 4),
          trend_vs_history=trend,
          risk_drivers=_module_risk_drivers(
            probability=stable_probability,
            historical_defect_count=int(stats.get("historical_defect_count", 0)),
            snapshot=snapshot,
            pass_rate_delta=pass_rate_delta,
          ),
          recommended_actions=_module_recommended_actions(
            snapshot=snapshot,
            trend=trend,
            probability=stable_probability,
          ),
        )
      )

    module_risks = enriched_module_risks

    llm_score_raw = data.get("overall_confidence_score")
    try:
      llm_score = max(0, min(100, int(float(llm_score_raw))))
    except (TypeError, ValueError):
      raise ValueError(f"Model returned invalid overall_confidence_score: {llm_score_raw}")

    ai_score = _stable_ai_score(
      llm_score=llm_score,
      execution=execution,
      global_history=global_stats,
    )

    llm_recommendation = _normalize_recommendation(data.get("deployment_recommendation"))

    final_score, score_breakdown, historical_comparison = _compute_score(
      ai_score=ai_score,
      execution=execution,
      global_history=global_stats,
      module_risks=module_risks,
    )
    deterministic_recommendation = _derive_recommendation_from_execution(final_score, execution)
    recommendation = (
      deterministic_recommendation
      if _recommendation_rank(deterministic_recommendation) >= _recommendation_rank(llm_recommendation)
      else llm_recommendation
    )

    # Keep the number and the verdict in the same band. A 91/100 next to a
    # NO-GO reads as a bug; the verdict is the stricter signal, so the score
    # follows it rather than the other way around.
    if recommendation == "NO-GO":
      final_score = min(final_score, 40)
    elif recommendation == "CONDITIONAL GO":
      final_score = max(45, min(final_score, 74))
    else:
      final_score = max(final_score, 75)
    score_breakdown.final_score = final_score

    critical_ids = data.get("critical_test_ids", [])
    if not isinstance(critical_ids, list) or not critical_ids:
      ranked = sorted(tests, key=lambda t: (_risk_rank(t.risk_level), t.id), reverse=True)
      critical_ids = [t.id for t in ranked[:5]]

    rationale = data.get("recommendation_rationale", "")
    if not isinstance(rationale, str) or not rationale.strip():
      raise ValueError("Model returned empty recommendation_rationale")

    rationale_text = (
      f"{rationale.strip()} "
      f"Score model: final={final_score}, ai={score_breakdown.llm_score}, current={score_breakdown.current_score}, "
      f"historical={score_breakdown.historical_score}, execution_penalty={score_breakdown.execution_penalty}, "
      f"risk_penalty={score_breakdown.module_risk_penalty}."
    )

    return DefectAnalysis(
      module_risks=module_risks,
      overall_confidence_score=final_score,
      deployment_recommendation=recommendation,
      recommendation_rationale=rationale_text,
      critical_test_ids=critical_ids,
      score_breakdown=score_breakdown,
      historical_comparison=historical_comparison,
    )

  return await asyncio.to_thread(_call_model)
