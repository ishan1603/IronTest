"""Executes generated test cases and reports what actually happened.

This agent runs pytest as a subprocess and reports the real outcome. It does
not shape, sample, or synthesize results: if every test passes, the summary
says every test passed.

Note on isolation: snippets originate from an LLM, so this module is only safe
to point at trusted input. Untrusted repositories must go through the sandboxed
runner (see agents/runners/) rather than calling execute_tests directly.
"""

import asyncio
import os
import subprocess
import sys
import tempfile
import textwrap
import time
from typing import List

from models import TestCase, TestExecutionSummary, TestResult

# Wall-clock ceiling for a single test file, in seconds.
TEST_TIMEOUT_SECONDS = int(os.getenv("TEST_TIMEOUT_SECONDS", "20"))

# Cap captured output so a chatty failure cannot balloon the run record.
MAX_CAPTURED_OUTPUT = 2000


def _truncate(text: str, limit: int = MAX_CAPTURED_OUTPUT) -> str:
    clean = (text or "").strip()
    if len(clean) <= limit:
        return clean
    return "...(truncated)...\n" + clean[-limit:]


def _snippet_source(test: TestCase) -> str:
    snippet = test.automation_snippet
    if isinstance(snippet, list):
        source = "\n".join(str(line) for line in snippet)
    else:
        source = str(snippet or "")

    # The generator is instructed to emit a def, but tolerate bare statements.
    if "def " not in source:
        source = "def test_generated_scenario():\n" + textwrap.indent(source, "    ")
    return source


def _run_one(test: TestCase, temp_dir: str) -> TestResult:
    if not test.automation_snippet:
        return TestResult(
            test_id=test.id,
            status="skipped",
            error_message=test.skip_reason or "No automation snippet was generated for this case.",
        )

    test_file = os.path.join(temp_dir, f"{test.id.replace('-', '_')}.py")
    with open(test_file, "w", encoding="utf-8") as handle:
        handle.write(_snippet_source(test))

    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", test_file, "-v", "--tb=short"],
            capture_output=True,
            text=True,
            timeout=TEST_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return TestResult(
            test_id=test.id,
            status="error",
            error_message=f"Execution exceeded the {TEST_TIMEOUT_SECONDS}s timeout.",
        )
    except Exception as exc:  # noqa: BLE001
        return TestResult(test_id=test.id, status="error", error_message=str(exc))

    output = _truncate(proc.stdout or proc.stderr)

    # pytest exit codes: 0 passed, 1 tests failed, 2-5 collection/usage errors.
    if proc.returncode == 0:
        return TestResult(
            test_id=test.id,
            status="pass",
            error_message=output or "Test passed with no captured output.",
        )
    if proc.returncode == 1:
        return TestResult(test_id=test.id, status="fail", error_message=output)
    return TestResult(
        test_id=test.id,
        status="error",
        error_message=output or f"pytest exited with code {proc.returncode}.",
    )


async def execute_tests(tests: List[TestCase]) -> TestExecutionSummary:
    def _run() -> TestExecutionSummary:
        start_time = time.time()
        with tempfile.TemporaryDirectory() as temp_dir:
            results = [_run_one(test, temp_dir) for test in tests]
        duration = time.time() - start_time
        return TestExecutionSummary(results=results, duration_seconds=round(duration, 2))

    return await asyncio.to_thread(_run)
