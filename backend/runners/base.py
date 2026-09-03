"""Test runner interface and shared JUnit XML parsing.

Generated tests import the repository's real modules, so they cannot run in
this process: the code is untrusted and its dependencies are not installed
here. Every backend below executes elsewhere -- a container or a GitHub
Actions job -- and reports back through the same result shape.

Whatever the backend, results are parsed from the runner's own JUnit output.
Nothing is inferred from an exit code alone, and nothing is synthesized when
output is missing: a run that produced no parseable results reports as failed
with its logs attached, rather than as a pass.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any
from xml.etree import ElementTree

from models import TestResult

logger = logging.getLogger(__name__)

MAX_OUTPUT_CHARS = 12_000
MAX_MESSAGE_CHARS = 2_000


TIMED_OUT = 124
NOT_FOUND = 127


def run_subprocess(
    cmd: list[str],
    *,
    cwd: str | None = None,
    timeout: int,
    env: dict[str, str] | None = None,
) -> tuple[int, str]:
    """Run a command, returning (exit_code, combined_output).

    Blocking on purpose: asyncio.create_subprocess_exec raises
    NotImplementedError under the Selector event loop that uvicorn installs on
    Windows, so runner subprocess work goes through asyncio.to_thread and this.

    Exit code 124 means it timed out; 127 means the executable was not found.
    """
    resolved = list(cmd)
    found = shutil.which(resolved[0])
    if found:
        resolved[0] = found  # npm -> npm.cmd, git -> git.exe on Windows

    try:
        proc = subprocess.run(
            resolved,
            cwd=cwd,
            env={**os.environ, **(env or {})},
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except subprocess.TimeoutExpired as exc:
        partial = ""
        if isinstance(exc.stdout, str):
            partial += exc.stdout
        if isinstance(exc.stderr, str):
            partial += exc.stderr
        return TIMED_OUT, partial + f"\n(command exceeded {timeout}s and was stopped)"
    except FileNotFoundError:
        return NOT_FOUND, f"(command not found: {cmd[0]})"
    except OSError as exc:
        return NOT_FOUND, f"(could not start {cmd[0]}: {exc})"


class RunnerUnavailable(RuntimeError):
    """The backend cannot run here (no Docker daemon, no dispatch repo, ...)."""


@dataclass
class GeneratedFile:
    """A file the pipeline writes into the checkout before running tests."""

    path: str
    content: str


@dataclass
class RunnerRequest:
    repo_full_name: str
    ref: str
    github_token: str
    stack: dict[str, Any]
    files: list[GeneratedFile] = field(default_factory=list)
    #: "specification" runs expect failures: the behavior is not built yet.
    mode: str = "existing_code"
    timeout_seconds: int = 600


@dataclass
class RunnerResult:
    backend: str
    status: str  # completed | failed
    results: list[TestResult] = field(default_factory=list)
    raw_output: str = ""
    duration_seconds: float = 0.0
    error_message: str = ""

    @property
    def produced_results(self) -> bool:
        return bool(self.results)


class TestRunner(ABC):
    """Executes generated tests against a repository checkout."""

    name: str = "abstract"

    @abstractmethod
    def is_available(self) -> bool:
        """Whether this backend can run in the current environment."""

    @abstractmethod
    async def run(self, request: RunnerRequest) -> RunnerResult:
        ...


# -- JUnit parsing ---------------------------------------------------------


def _truncate(text: str, limit: int) -> str:
    clean = (text or "").strip()
    if len(clean) <= limit:
        return clean
    return clean[:limit] + "\n...(truncated)"


def _testcase_id(case: ElementTree.Element) -> str:
    """Prefer the TC-xxx id the generator embedded in the test name."""
    name = case.get("name", "")
    match = re.search(r"(TC[-_]\d+)", name, re.IGNORECASE)
    if match:
        return match.group(1).upper().replace("_", "-")

    classname = case.get("classname", "")
    return f"{classname}::{name}" if classname else name or "unknown"


def parse_junit(xml_text: str) -> list[TestResult]:
    """Convert a JUnit report into TestResults.

    Handles both a single <testsuite> root and a <testsuites> wrapper, which
    differ between pytest, jest, vitest, and go-junit-report.
    """
    if not xml_text or not xml_text.strip():
        return []

    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError as exc:
        logger.warning("Could not parse JUnit XML: %s", exc)
        return []

    suites = [root] if root.tag == "testsuite" else root.findall(".//testsuite")

    results: list[TestResult] = []
    for suite in suites:
        for case in suite.findall("testcase"):
            test_id = _testcase_id(case)

            failure = case.find("failure")
            error = case.find("error")
            skipped = case.find("skipped")

            if error is not None:
                node, status = error, "error"
            elif failure is not None:
                node, status = failure, "fail"
            elif skipped is not None:
                node, status = skipped, "skipped"
            else:
                results.append(
                    TestResult(
                        test_id=test_id,
                        status="pass",
                        error_message=_truncate(case.findtext("system-out", ""), MAX_MESSAGE_CHARS),
                    )
                )
                continue

            detail = (node.get("message") or "") + "\n" + (node.text or "")
            results.append(
                TestResult(test_id=test_id, status=status, error_message=_truncate(detail, MAX_MESSAGE_CHARS))
            )

    return results


def failure_result(backend: str, message: str, *, output: str = "", duration: float = 0.0) -> RunnerResult:
    """A run that could not produce results. Never reports as a pass."""
    return RunnerResult(
        backend=backend,
        status="failed",
        results=[],
        raw_output=_truncate(output, MAX_OUTPUT_CHARS),
        duration_seconds=round(duration, 2),
        error_message=message,
    )
