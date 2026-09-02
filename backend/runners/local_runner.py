"""Runs self-contained snippets in a subprocess on this host.

The fallback backend, used when no sandbox is available. It can only run
snippets that import nothing from the repository, so it validates behavior
described by the requirement rather than the repository's actual code. Runs
executed this way are labelled so the UI never presents them as evidence that
the repository itself was tested.
"""

from __future__ import annotations

import time

from agents.execution_agent import execute_tests
from models import TestCase
from runners.base import RunnerRequest, RunnerResult, TestRunner


class LocalRunner(TestRunner):
    name = "local"

    def is_available(self) -> bool:
        return True

    async def run(self, request: RunnerRequest) -> RunnerResult:
        """Not used for repository runs; see run_cases."""
        return RunnerResult(
            backend=self.name,
            status="failed",
            error_message="The local runner cannot execute tests against a repository checkout.",
        )

    async def run_cases(self, cases: list[TestCase]) -> RunnerResult:
        started = time.time()
        summary = await execute_tests(cases)
        return RunnerResult(
            backend=self.name,
            status="completed",
            results=summary.results,
            duration_seconds=round(time.time() - started, 2),
        )
