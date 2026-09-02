"""Runs a repository's tests on GitHub Actions.

The backend for deployed installs, where running untrusted code on the API
host is neither safe nor affordable. Tests execute on GitHub's runners inside
a dedicated dispatch repository, so nothing is ever written to the user's own
repository and the compute is covered by the free Actions allowance.

Requires ACTIONS_RUNNER_REPO (owner/name of the dispatch repository) and
ACTIONS_DISPATCH_TOKEN (a token with actions:write on it). See
docs/deployment.md for the workflow file that repository must contain.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import os
import time
import uuid
import zipfile

import httpx

from runners.base import (
    MAX_OUTPUT_CHARS,
    RunnerRequest,
    RunnerResult,
    RunnerUnavailable,
    TestRunner,
    failure_result,
    parse_junit,
)

logger = logging.getLogger(__name__)

API_BASE = "https://api.github.com"
WORKFLOW_FILE = "irontest-runner.yml"
POLL_INTERVAL_SECONDS = 5
#: GitHub takes a moment to register a dispatched run before it is queryable.
DISPATCH_SETTLE_SECONDS = 4


class GitHubActionsRunner(TestRunner):
    name = "github_actions"

    def __init__(self) -> None:
        self.runner_repo = (os.getenv("ACTIONS_RUNNER_REPO") or "").strip()
        self.dispatch_token = (os.getenv("ACTIONS_DISPATCH_TOKEN") or "").strip()
        self.workflow_file = (os.getenv("ACTIONS_WORKFLOW_FILE") or WORKFLOW_FILE).strip()

    def is_available(self) -> bool:
        return bool(self.runner_repo and self.dispatch_token)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.dispatch_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def run(self, request: RunnerRequest) -> RunnerResult:
        if not self.is_available():
            raise RunnerUnavailable(
                "GitHub Actions runner is not configured. Set ACTIONS_RUNNER_REPO and ACTIONS_DISPATCH_TOKEN."
            )

        started = time.time()
        # Correlates the dispatch with its run, since the dispatch endpoint
        # does not return a run id.
        correlation_id = uuid.uuid4().hex

        payload = base64.b64encode(
            json.dumps([{"path": f.path, "content": f.content} for f in request.files]).encode("utf-8")
        ).decode("ascii")

        inputs = {
            "correlation_id": correlation_id,
            "target_repo": request.repo_full_name,
            "target_ref": request.ref,
            "target_token": request.github_token,
            "language": str(request.stack.get("language", "python")),
            "install_command": str(request.stack.get("install_command", "")),
            "test_command": str(request.stack.get("test_command", "")),
            "files_payload": payload,
        }

        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            dispatch = await client.post(
                f"{API_BASE}/repos/{self.runner_repo}/actions/workflows/{self.workflow_file}/dispatches",
                headers=self._headers(),
                json={"ref": os.getenv("ACTIONS_RUNNER_REF", "main"), "inputs": inputs},
            )
            if dispatch.status_code not in (201, 204):
                return failure_result(
                    self.name,
                    f"Could not dispatch the runner workflow ({dispatch.status_code}). "
                    "Check ACTIONS_RUNNER_REPO, the token's actions:write scope, and that the workflow exists.",
                    output=dispatch.text[:1000],
                )

            await asyncio.sleep(DISPATCH_SETTLE_SECONDS)
            run_id = await self._find_run(client, correlation_id, request.timeout_seconds)
            if run_id is None:
                return failure_result(
                    self.name,
                    "The runner workflow was dispatched but never appeared. Check the dispatch repository's Actions tab.",
                    duration=time.time() - started,
                )

            conclusion = await self._await_completion(client, run_id, request.timeout_seconds, started)
            if conclusion is None:
                return failure_result(
                    self.name,
                    f"The test run exceeded {request.timeout_seconds}s and was abandoned.",
                    duration=time.time() - started,
                )

            xml = await self._download_report(client, run_id)

        duration = time.time() - started
        results = parse_junit(xml)

        if not results:
            return failure_result(
                self.name,
                "The workflow finished but produced no JUnit report. "
                f"Workflow conclusion: {conclusion}.",
                duration=duration,
            )

        return RunnerResult(
            backend=self.name,
            status="completed",
            results=results,
            raw_output=f"GitHub Actions run {run_id} concluded: {conclusion}",
            duration_seconds=round(duration, 2),
        )

    async def _find_run(self, client: httpx.AsyncClient, correlation_id: str, timeout: int) -> int | None:
        """Locate the dispatched run by the correlation id in its run name."""
        deadline = time.time() + min(120, timeout)
        while time.time() < deadline:
            response = await client.get(
                f"{API_BASE}/repos/{self.runner_repo}/actions/runs",
                headers=self._headers(),
                params={"event": "workflow_dispatch", "per_page": 30},
            )
            if response.status_code == 200:
                for run in response.json().get("workflow_runs", []):
                    if correlation_id in (run.get("name") or "") or correlation_id in (
                        run.get("display_title") or ""
                    ):
                        return run["id"]
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
        return None

    async def _await_completion(
        self, client: httpx.AsyncClient, run_id: int, timeout: int, started: float
    ) -> str | None:
        while time.time() - started < timeout:
            response = await client.get(
                f"{API_BASE}/repos/{self.runner_repo}/actions/runs/{run_id}",
                headers=self._headers(),
            )
            if response.status_code == 200:
                body = response.json()
                if body.get("status") == "completed":
                    return body.get("conclusion") or "unknown"
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
        return None

    async def _download_report(self, client: httpx.AsyncClient, run_id: int) -> str:
        """Pull the JUnit XML out of the run's uploaded artifact."""
        listing = await client.get(
            f"{API_BASE}/repos/{self.runner_repo}/actions/runs/{run_id}/artifacts",
            headers=self._headers(),
        )
        if listing.status_code != 200:
            return ""

        artifact = next(
            (a for a in listing.json().get("artifacts", []) if a.get("name") == "irontest-results"),
            None,
        )
        if artifact is None:
            return ""

        download = await client.get(
            artifact["archive_download_url"], headers=self._headers(), follow_redirects=True
        )
        if download.status_code != 200:
            return ""

        try:
            with zipfile.ZipFile(io.BytesIO(download.content)) as bundle:
                name = next((n for n in bundle.namelist() if n.endswith(".xml")), None)
                if name is None:
                    return ""
                return bundle.read(name).decode("utf-8", errors="replace")
        except (zipfile.BadZipFile, KeyError) as exc:
            logger.warning("Could not read results artifact for run %s: %s", run_id, exc)
            return ""
