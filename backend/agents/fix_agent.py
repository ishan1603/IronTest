"""Proposes a concrete code change for each failing test.

Runs after the defect agent, only when there are real failures and real source
to point at (a repository run). Output is advisory: a target file, a short
explanation, and a focused change. Nothing is applied.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from llm import LLMError, generate_json
from models import FixSuggestion, StoryAnalysis, TestCase, TestExecutionSummary

logger = logging.getLogger(__name__)

# Cap the work: only the most important failures, and a bounded amount of
# source context per call.
MAX_FIXES = 5
MAX_SNIPPET_CHARS = 1600

SYSTEM_PROMPT = """
You are the Fix Suggestion Agent. Given a failing test, its failure output,
and the relevant source file, propose the smallest change that would make the
test pass -- or, if the test is wrong, say so and propose fixing the test.

Respond with a JSON object: {"fixes": [{
  "test_id": string,
  "target_file": string (the file to change, from the paths given),
  "explanation": string (1-2 sentences: the root cause and what the change does),
  "suggested_change": string (a short unified-diff-style hunk or a focused
     before/after; keep it minimal and specific),
  "confidence": "low" | "medium" | "high"
}]}

Only include a fix when you can point at a concrete cause. It is better to
return fewer, correct suggestions than to guess.
"""


def _failing(execution: TestExecutionSummary) -> list[Any]:
    ranked = [r for r in execution.results if r.status in {"fail", "error"}]
    # errors (couldn't even run) first, then failures
    ranked.sort(key=lambda r: 0 if r.status == "error" else 1)
    return ranked[:MAX_FIXES]


def _relevant_files(repo_context: dict[str, Any], modules: list[str]) -> list[dict[str, str]]:
    files = []
    wanted = {m.lower() for m in modules}
    for entry in repo_context.get("files", []):
        path = entry.get("path", "")
        excerpt = entry.get("excerpt", "")
        if not excerpt:
            continue
        # Prefer files whose path mentions an affected module.
        score = sum(1 for w in wanted if w and w in path.lower())
        files.append((score, {"path": path, "excerpt": excerpt[:MAX_SNIPPET_CHARS]}))
    files.sort(key=lambda item: -item[0])
    return [f for _, f in files[:6]]


async def suggest_fixes(
    story: StoryAnalysis,
    tests: list[TestCase],
    execution: TestExecutionSummary,
    repo_context: dict[str, Any] | None,
) -> list[FixSuggestion]:
    failing = _failing(execution)
    if not failing or not repo_context:
        return []

    tests_by_id = {t.id: t for t in tests}

    def _call() -> list[FixSuggestion]:
        payload = {
            "intent": story.intent,
            "failing_tests": [
                {
                    "test_id": r.test_id,
                    "status": r.status,
                    "description": (tests_by_id.get(r.test_id).description if tests_by_id.get(r.test_id) else ""),
                    "snippet": (
                        tests_by_id.get(r.test_id).automation_snippet if tests_by_id.get(r.test_id) else []
                    ),
                    "failure_output": (r.error_message or "")[:1200],
                }
                for r in failing
            ],
            "source_files": _relevant_files(repo_context, story.modules),
        }
        prompt = (
            f"Input:\n{json.dumps(payload)}\n\n"
            "Return ONLY the JSON object with key fixes."
        )
        data = generate_json(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=prompt,
            max_output_tokens=2000,
            temperature=0.2,
        )

        raw = data.get("fixes", [])
        if not isinstance(raw, list):
            return []

        valid = {"low", "medium", "high"}
        out: list[FixSuggestion] = []
        for item in raw[:MAX_FIXES]:
            if not isinstance(item, dict):
                continue
            conf = str(item.get("confidence") or "medium").strip().lower()
            out.append(
                FixSuggestion(
                    test_id=str(item.get("test_id") or "").strip(),
                    target_file=str(item.get("target_file") or "").strip(),
                    explanation=str(item.get("explanation") or "").strip(),
                    suggested_change=str(item.get("suggested_change") or "").strip(),
                    confidence=conf if conf in valid else "medium",
                )
            )
        return [f for f in out if f.explanation or f.suggested_change]

    try:
        return await asyncio.to_thread(_call)
    except LLMError as exc:
        # Fix suggestions are a bonus; a provider outage here must not fail the
        # run whose results are already computed.
        logger.warning("Fix suggestions unavailable: %s", exc)
        return []
