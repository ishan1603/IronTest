"""Runner selection.

TEST_RUNNER picks a backend explicitly; "auto" (the default) prefers GitHub
Actions when it is configured, then Docker, then -- only when the app is not in
production -- host execution, and otherwise reports that no runner is available.

Host execution (`local_host`) is not a sandbox: it runs the repository's own
test suite in a subprocess. It is chosen automatically only outside production,
where it is the difference between a working local demo and none.
"""

from __future__ import annotations

import logging
import os

from runners.actions_runner import GitHubActionsRunner
from runners.base import (
    GeneratedFile,
    RunnerRequest,
    RunnerResult,
    RunnerUnavailable,
    TestRunner,
    failure_result,
    parse_junit,
)
from runners.docker_runner import DockerRunner
from runners.local_repo_runner import LocalRepoRunner
from runners.local_runner import LocalRunner

logger = logging.getLogger(__name__)

__all__ = [
    "GeneratedFile",
    "RunnerRequest",
    "RunnerResult",
    "RunnerUnavailable",
    "TestRunner",
    "failure_result",
    "parse_junit",
    "DockerRunner",
    "GitHubActionsRunner",
    "LocalRepoRunner",
    "LocalRunner",
    "select_runner",
    "runner_status",
    "SANDBOXED_BACKENDS",
]

# Backends that isolate the repository's code from the API host.
SANDBOXED_BACKENDS = {"github_actions", "docker"}

_EXPLICIT_BACKENDS = {
    "github_actions": GitHubActionsRunner,
    "docker": DockerRunner,
    "local_host": LocalRepoRunner,
    "local": LocalRunner,
}

# Order tried in "auto" mode: strongest isolation first, host execution last.
_AUTO_CHAIN = (GitHubActionsRunner, DockerRunner, LocalRepoRunner)


def select_runner() -> TestRunner | None:
    """The backend to use for repository runs, or None when none can run."""
    choice = (os.getenv("TEST_RUNNER") or "auto").strip().lower()

    if choice in _EXPLICIT_BACKENDS:
        runner = _EXPLICIT_BACKENDS[choice]()
        if not runner.is_available():
            logger.warning("TEST_RUNNER=%s was requested but is not available here.", choice)
            return None
        return runner

    for factory in _AUTO_CHAIN:
        runner = factory()
        if runner.is_available():
            return runner
    return None


def runner_status() -> dict[str, object]:
    """Diagnostic view for the health endpoint."""
    selected = select_runner()
    return {
        "selected": selected.name if selected else None,
        "sandboxed": selected.name in SANDBOXED_BACKENDS if selected else None,
        "configured": (os.getenv("TEST_RUNNER") or "auto").strip().lower(),
        "available": {
            "github_actions": GitHubActionsRunner().is_available(),
            "docker": DockerRunner().is_available(),
            "local_host": LocalRepoRunner().is_available(),
        },
    }
