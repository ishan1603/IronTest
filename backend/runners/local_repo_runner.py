"""Runs a repository's real test suite in a subprocess on this host.

This is the development-machine backend. It is NOT a sandbox: the repository's
test suite and its dependency install run with the same privileges as the API
process. It exists so someone running the project locally, with no Docker,
still gets real execution against real code -- which is no more dangerous than
that person running pytest in the repository themselves.

It is available only when the app is not in production, or when
ALLOW_HOST_TEST_EXECUTION is set explicitly. A deployed install must use the
Docker or GitHub Actions backend instead.
"""

from __future__ import annotations

import asyncio
import os
import shlex
import shutil
import sys
import tempfile
import time

from config import get_settings
from runners.base import (
    MAX_OUTPUT_CHARS,
    RunnerRequest,
    RunnerResult,
    RunnerUnavailable,
    TestRunner,
    failure_result,
    parse_junit,
)

CLONE_TIMEOUT = 120
INSTALL_TIMEOUT = 300


def _venv_python(venv_dir: str) -> str:
    bin_dir = "Scripts" if os.name == "nt" else "bin"
    exe = "python.exe" if os.name == "nt" else "python"
    return os.path.join(venv_dir, bin_dir, exe)


async def _run(cmd: list[str], *, cwd: str, timeout: int, env: dict | None = None) -> tuple[int, str]:
    """Run a command, capturing combined output. Returns (exit_code, output)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=cwd,
            env={**os.environ, **(env or {})},
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return proc.returncode, out.decode("utf-8", errors="replace")
    except asyncio.TimeoutError:
        return 124, f"(command exceeded {timeout}s and was stopped: {' '.join(cmd)})"
    except FileNotFoundError:
        return 127, f"(command not found: {cmd[0]})"


class LocalRepoRunner(TestRunner):
    name = "local_host"

    def is_available(self) -> bool:
        if shutil.which("git") is None:
            return False
        if get_settings().is_production:
            return os.getenv("ALLOW_HOST_TEST_EXECUTION", "").strip().lower() in {"1", "true", "yes"}
        return True

    async def run(self, request: RunnerRequest) -> RunnerResult:
        if not self.is_available():
            raise RunnerUnavailable(
                "Host test execution is disabled. Set ALLOW_HOST_TEST_EXECUTION=true, "
                "or run the API with ENVIRONMENT=development."
            )

        started = time.time()
        with tempfile.TemporaryDirectory(prefix="irontest-run-") as work:
            clone_dir = os.path.join(work, "repo")

            # The token is written to a credentials file rather than the clone
            # URL, so it does not appear in the process list or captured logs.
            cred_path = os.path.join(work, ".git-credentials")
            with open(cred_path, "w", encoding="utf-8") as handle:
                handle.write(f"https://x-access-token:{request.github_token}@github.com\n")

            clone_env = {
                "GIT_TERMINAL_PROMPT": "0",
                "GIT_CONFIG_COUNT": "1",
                "GIT_CONFIG_KEY_0": "credential.helper",
                "GIT_CONFIG_VALUE_0": f"store --file={cred_path}",
            }
            code, clone_log = await _run(
                [
                    "git", "clone", "--depth", "1", "--branch", request.ref,
                    f"https://github.com/{request.repo_full_name}.git", clone_dir,
                ],
                cwd=work,
                timeout=CLONE_TIMEOUT,
                env=clone_env,
            )
            try:
                os.remove(cred_path)
            except OSError:
                pass

            if code != 0 or not os.path.isdir(clone_dir):
                return failure_result(
                    self.name,
                    f"Could not clone {request.repo_full_name}@{request.ref}.",
                    output=clone_log,
                    duration=time.time() - started,
                )

            for generated in request.files:
                target = os.path.join(clone_dir, generated.path)
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with open(target, "w", encoding="utf-8") as handle:
                    handle.write(generated.content)

            language = str(request.stack.get("language", "python")).lower()
            remaining = max(60, (request.timeout_seconds or 600) - int(time.time() - started))

            if language in {"javascript", "typescript"}:
                log, results = await self._run_node(clone_dir, request, remaining)
            else:
                log, results = await self._run_python(clone_dir, request, remaining)

        duration = time.time() - started
        combined = (clone_log + "\n" + log).strip()

        if not results:
            return failure_result(
                self.name,
                "The test command produced no JUnit report. Check the repository's "
                "install and test commands, shown on its card.",
                output=combined,
                duration=duration,
            )

        return RunnerResult(
            backend=self.name,
            status="completed",
            results=results,
            raw_output=combined[-MAX_OUTPUT_CHARS:],
            duration_seconds=round(duration, 2),
        )

    async def _run_python(self, clone_dir: str, request: RunnerRequest, budget: int):
        log_parts: list[str] = []
        venv_dir = os.path.join(clone_dir, "_irontest_venv")

        code, venv_out = await _run([sys.executable, "-m", "venv", venv_dir], cwd=clone_dir, timeout=120)
        log_parts.append("--- create venv ---\n" + venv_out)

        py = _venv_python(venv_dir)
        if code != 0 or not os.path.exists(py):
            py = sys.executable  # fall back to the API interpreter

        # pytest is always needed; project dependencies are best-effort.
        await _run(
            [py, "-m", "pip", "install", "-q", "--disable-pip-version-check", "pytest"],
            cwd=clone_dir,
            timeout=INSTALL_TIMEOUT,
        )
        if os.path.exists(os.path.join(clone_dir, "requirements.txt")):
            _, dep_out = await _run(
                [py, "-m", "pip", "install", "-q", "--disable-pip-version-check", "-r", "requirements.txt"],
                cwd=clone_dir,
                timeout=INSTALL_TIMEOUT,
            )
            log_parts.append("--- install requirements.txt ---\n" + dep_out[-2000:])
        elif os.path.exists(os.path.join(clone_dir, "pyproject.toml")):
            _, dep_out = await _run(
                [py, "-m", "pip", "install", "-q", "--disable-pip-version-check", "."],
                cwd=clone_dir,
                timeout=INSTALL_TIMEOUT,
            )
            log_parts.append("--- install project ---\n" + dep_out[-2000:])

        report = os.path.join(clone_dir, "results.xml")
        _, test_out = await _run(
            [py, "-m", "pytest", "-q", "--tb=short", f"--junitxml={report}"],
            cwd=clone_dir,
            timeout=max(60, budget),
            env={"COLUMNS": "200"},
        )
        log_parts.append("--- pytest ---\n" + test_out)

        results = []
        if os.path.exists(report):
            with open(report, encoding="utf-8", errors="replace") as handle:
                results = parse_junit(handle.read())
        return "\n".join(log_parts), results

    async def _run_node(self, clone_dir: str, request: RunnerRequest, budget: int):
        log_parts: list[str] = []
        install_cmd = request.stack.get("install_command") or "npm install"
        _, install_out = await _run(
            shlex.split(install_cmd), cwd=clone_dir, timeout=INSTALL_TIMEOUT, env={"CI": "1"}
        )
        log_parts.append(f"--- {install_cmd} ---\n" + install_out[-2000:])

        test_cmd = request.stack.get("test_command") or "npx jest --reporters=default --reporters=jest-junit"
        _, test_out = await _run(
            shlex.split(test_cmd), cwd=clone_dir, timeout=max(60, budget), env={"CI": "1", "COLUMNS": "200"}
        )
        log_parts.append(f"--- {test_cmd} ---\n" + test_out)

        results = []
        for name in ("results.xml", "junit.xml", "test-results.xml"):
            candidate = os.path.join(clone_dir, name)
            if os.path.exists(candidate):
                with open(candidate, encoding="utf-8", errors="replace") as handle:
                    results = parse_junit(handle.read())
            if results:
                break
        return "\n".join(log_parts), results
