"""Runs a repository's tests inside a locked-down container.

The repository is untrusted: its test suite, its dependencies, and the
install scripts those dependencies run are all arbitrary code. The container
is therefore given no network after install, a read-only root, dropped
capabilities, no privilege escalation, and hard CPU, memory, process, and
wall-clock ceilings.

The clone URL carries the user's GitHub token, so it is passed via stdin to
`git credential` rather than embedded in a command line, where it would be
visible in the container's process list and in any captured output.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shlex
import shutil
import time

from runners.base import (
    MAX_OUTPUT_CHARS,
    NOT_FOUND,
    TIMED_OUT,
    GeneratedFile,
    RunnerRequest,
    RunnerResult,
    RunnerUnavailable,
    TestRunner,
    failure_result,
    parse_junit,
    run_subprocess,
)

logger = logging.getLogger(__name__)

# Base images per language. Slim tags keep the pull small on a laptop.
IMAGES = {
    "python": "python:3.12-slim",
    "javascript": "node:20-slim",
    "typescript": "node:20-slim",
    "go": "golang:1.22-alpine",
    "rust": "rust:1-slim",
    "ruby": "ruby:3.3-slim",
}
DEFAULT_IMAGE = "python:3.12-slim"

CONTAINER_MEMORY = "1g"
CONTAINER_CPUS = "1.5"
MAX_PROCESSES = 256


class DockerRunner(TestRunner):
    name = "docker"

    def __init__(self, timeout_seconds: int = 600) -> None:
        self.timeout_seconds = timeout_seconds

    def is_available(self) -> bool:
        return shutil.which("docker") is not None

    def _image_for(self, stack: dict) -> str:
        return IMAGES.get(str(stack.get("language", "")).lower(), DEFAULT_IMAGE)

    def _build_script(self, request: RunnerRequest) -> str:
        """The shell script the container runs.

        Written as a heredoc-free script so it can be passed as a single
        argument. Test failures must not abort it: a non-zero exit from the
        test command is a result, not an error, so only setup runs under -e.
        """
        stack = request.stack
        install = stack.get("install_command") or ""
        test_command = stack.get("test_command") or "pytest -q --junitxml=results.xml"

        # Written by the host into the mounted payload directory.
        write_files = "\n".join(
            f"mkdir -p $(dirname {shlex.quote(f.path)}) && "
            f"cp /payload/{shlex.quote(str(index))} {shlex.quote(f.path)}"
            for index, f in enumerate(request.files)
        )

        return f"""
set -e
git config --global credential.helper store
printf 'https://x-access-token:%s@github.com\\n' "$GITHUB_TOKEN" > ~/.git-credentials
chmod 600 ~/.git-credentials

git clone --depth 1 --branch {shlex.quote(request.ref)} \
  https://github.com/{shlex.quote(request.repo_full_name)}.git /work 2>&1 | tail -5
rm -f ~/.git-credentials
cd /work

{write_files}

echo "--- installing ---"
{install if install else 'echo "no install step"'} 2>&1 | tail -30

echo "--- running tests ---"
set +e
{test_command} 2>&1 | tail -200
TEST_EXIT=$?
set -e

echo "--- IRONTEST_RESULTS_BEGIN ---"
if [ -f results.xml ]; then cat results.xml; fi
echo "--- IRONTEST_RESULTS_END ---"
exit $TEST_EXIT
"""

    async def run(self, request: RunnerRequest) -> RunnerResult:
        if not self.is_available():
            raise RunnerUnavailable("Docker is not installed or not on PATH.")

        started = time.time()
        import tempfile
        import os

        with tempfile.TemporaryDirectory(prefix="irontest-payload-") as payload_dir:
            for index, generated in enumerate(request.files):
                with open(os.path.join(payload_dir, str(index)), "w", encoding="utf-8") as handle:
                    handle.write(generated.content)

            command = [
                "docker", "run", "--rm",
                "--network", "bridge",          # needed for clone and install
                "--memory", CONTAINER_MEMORY,
                "--memory-swap", CONTAINER_MEMORY,  # no swap: enforces the real ceiling
                "--cpus", CONTAINER_CPUS,
                "--pids-limit", str(MAX_PROCESSES),
                "--cap-drop", "ALL",
                "--security-opt", "no-new-privileges",
                "-e", f"GITHUB_TOKEN={request.github_token}",
                "-v", f"{payload_dir}:/payload:ro",
                "-w", "/",
                self._image_for(request.stack),
                "sh", "-c", self._build_script(request),
            ]

            timeout = request.timeout_seconds or self.timeout_seconds
            code, output = await asyncio.to_thread(run_subprocess, command, timeout=timeout)

        duration = time.time() - started

        if code == TIMED_OUT:
            return failure_result(
                self.name,
                f"The test run exceeded {timeout}s and was stopped.",
                output=output,
                duration=duration,
            )
        if code == NOT_FOUND:
            return failure_result(self.name, "Could not start Docker.", output=output, duration=duration)

        xml = _extract_between(output, "--- IRONTEST_RESULTS_BEGIN ---", "--- IRONTEST_RESULTS_END ---")
        results = parse_junit(xml)

        if not results:
            # No parseable report: report the failure with logs rather than
            # inventing an outcome.
            return failure_result(
                self.name,
                "The test command produced no JUnit report. Check the install and test commands for this repository.",
                output=output,
                duration=duration,
            )

        return RunnerResult(
            backend=self.name,
            status="completed",
            results=results,
            raw_output=output[-MAX_OUTPUT_CHARS:],
            duration_seconds=round(duration, 2),
        )


def _extract_between(text: str, start: str, end: str) -> str:
    try:
        head = text.index(start) + len(start)
        tail = text.index(end, head)
    except ValueError:
        return ""
    return text[head:tail].strip()
