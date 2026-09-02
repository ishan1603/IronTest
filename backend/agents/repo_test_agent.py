"""Generates tests that import a repository's real modules.

Differs from the standalone generator in one decisive way: snippets here are
expected to import repository code, so they cannot be validated by "does it
avoid imports" and cannot run on this host. They run in a sandbox against a
real checkout, which is what makes their pass or fail meaningful.

Two modes:

  existing_code  the behavior is shipped. Tests should pass; a failure is a
                 defect in the repository.
  specification  the behavior is not built yet. Tests are expected to fail at
                 import or assertion, and that red phase is the deliverable --
                 they describe what "done" means.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from llm import generate_json
from models import StoryAnalysis, TestCase

logger = logging.getLogger(__name__)

MAX_SYMBOLS_PER_FILE = 14
MAX_CONTEXT_FILES = 10

EXISTING_CODE_GUIDANCE = """
This behavior is ALREADY IMPLEMENTED in the repository. Write tests that
verify it. Import the real functions and classes listed in the context and
call them. A failing test means you found a genuine defect, so make the
assertions precise enough that a real bug would trip them.
"""

SPECIFICATION_GUIDANCE = """
This behavior is NOT YET IMPLEMENTED. Write the tests that SHOULD pass once it
is built -- the red phase of test-driven development. Import the module paths
where the code should live, following the conventions visible in the context,
even though those symbols do not exist yet. These tests are expected to fail
right now; that is correct and is the point. They define what "done" means.
"""

SYSTEM_PROMPT = """
You are the Test Generation Agent in an autonomous QA system. You write tests
against a REAL repository whose structure is given to you.

Rules:
- Import the repository's actual modules using the paths shown in the context.
  Never invent a module path that contradicts the context.
- Call the real functions and classes listed. Match their given signatures.
- Every test must be able to fail. Never assert a literal you just defined
  against itself; that tests nothing.
- Cover the acceptance criteria, then boundaries and negative cases.
- Keep each snippet under 15 lines.

Respond with a JSON object shaped as:
{
  "imports": string[]  (import lines for the whole file, e.g. "from app.billing import apply_discount"),
  "test_cases": [{
    "id": "TC-001",
    "type": "functional" | "boundary" | "edge_case" | "regression",
    "module": string (the repository module under test),
    "description": string,
    "steps": string[],
    "expected_result": string,
    "risk_level": "low" | "medium" | "high",
    "automation_snippet": string[]  (body lines only, no def line, no markdown fences)
  }]
}
"""


def _summarize_context(repo_context: dict[str, Any]) -> dict[str, Any]:
    """Compact the repo context to what fits in a small model's window."""
    files = []
    for entry in repo_context.get("files", [])[:MAX_CONTEXT_FILES]:
        symbols = entry.get("symbols", [])[:MAX_SYMBOLS_PER_FILE]
        if not symbols:
            continue
        files.append(
            {
                "path": entry["path"],
                "symbols": [
                    {
                        "kind": s.get("kind"),
                        "name": s.get("name"),
                        "signature": s.get("signature"),
                        "methods": s.get("methods", [])[:8],
                        "doc": s.get("doc", ""),
                    }
                    for s in symbols
                ],
            }
        )

    stack = repo_context.get("stack", {})
    return {
        "repository": repo_context.get("repository", ""),
        "language": stack.get("language", "python"),
        "test_framework": stack.get("test_framework", "pytest"),
        "source_dirs": stack.get("source_dirs", []),
        "existing_test_files": repo_context.get("existing_tests", [])[:10],
        "files": files,
    }


def _module_path_hints(repo_context: dict[str, Any]) -> list[str]:
    """Importable module paths derived from the context's file paths."""
    hints = []
    for entry in repo_context.get("files", []):
        path = entry.get("path", "")
        if path.endswith(".py"):
            hints.append(path[:-3].replace("/", "."))
        elif any(path.endswith(ext) for ext in (".js", ".ts", ".jsx", ".tsx")):
            hints.append("./" + path.rsplit(".", 1)[0])
    return hints[:MAX_CONTEXT_FILES]


def _coerce_lines(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(line).rstrip() for line in value if str(line).strip()]
    if isinstance(value, str):
        return [line.rstrip() for line in value.splitlines() if line.strip()]
    return []


def _normalize_cases(raw: object, fallback_module: str) -> list[TestCase]:
    if not isinstance(raw, list):
        return []

    valid_types = {"functional", "boundary", "edge_case", "regression"}
    valid_risks = {"low", "medium", "high"}

    cases: list[TestCase] = []
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            continue

        snippet = _coerce_lines(item.get("automation_snippet"))
        case_type = str(item.get("type") or "functional").strip().lower()
        risk = str(item.get("risk_level") or "medium").strip().lower()

        cases.append(
            TestCase(
                id=str(item.get("id") or f"TC-{index:03d}").strip(),
                type=case_type if case_type in valid_types else "functional",
                module=str(item.get("module") or fallback_module).strip() or fallback_module,
                description=str(item.get("description") or "").strip(),
                steps=item.get("steps") if isinstance(item.get("steps"), list) else [],
                expected_result=str(item.get("expected_result") or "").strip(),
                risk_level=risk if risk in valid_risks else "medium",
                automated=bool(snippet),
                automation_snippet=snippet,
                skip_reason="" if snippet else "Model returned no runnable snippet for this case.",
            )
        )
    return cases


async def generate_repo_tests(
    story: StoryAnalysis,
    repo_context: dict[str, Any],
    *,
    requirement: str,
    mode: str = "existing_code",
    learning: dict[str, Any] | None = None,
) -> tuple[list[TestCase], list[str]]:
    """Return (cases, import lines) for a suite targeting this repository."""

    def _call_model() -> tuple[list[TestCase], list[str]]:
        context = _summarize_context(repo_context)
        guidance = SPECIFICATION_GUIDANCE if mode == "specification" else EXISTING_CODE_GUIDANCE
        learning_context = learning or {}

        payload = {
            "requirement": requirement,
            "intent": story.intent,
            "acceptance_criteria": story.acceptance_criteria,
            "risk_factors": story.risk_factors,
            "repository_context": context,
            "importable_module_paths": _module_path_hints(repo_context),
            "prior_failures": learning_context.get("recent_failure_signatures", [])[:5],
        }

        prompt = (
            f"{guidance}\n\n"
            f"Input:\n{json.dumps(payload, indent=None)}\n\n"
            "Return ONLY the JSON object with keys imports and test_cases."
        )

        data = generate_json(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=prompt,
            max_output_tokens=3500,
            temperature=0.2,
        )

        fallback_module = (story.modules or [context.get("repository", "app")])[0]
        cases = _normalize_cases(data.get("test_cases"), fallback_module)
        imports = _coerce_lines(data.get("imports"))

        if not cases:
            raise ValueError("The model returned no usable test cases for this repository.")

        return cases, imports

    return await asyncio.to_thread(_call_model)
