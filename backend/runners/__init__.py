"""Runner selection.

TEST_RUNNER picks a backend explicitly; "auto" (the default) prefers GitHub
Actions when it is configured, then Docker, and otherwise reports that no
sandbox is available. The local backend is never chosen automatically for
repository runs, because it cannot execute repository code.
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
    "LocalRunner",
    "select_runner",
    "runner_status",
]


def select_runner() -> TestRunner | None:
    """The backend to use for repository runs, or None when none can run."""
    choice = (os.getenv("TEST_RUNNER") or "auto").strip().lower()

    backends = {
        "github_actions": GitHubActionsRunner,
        "docker": DockerRunner,
        "local": LocalRunner,
    }

    if choice in backends:
        runner = backends[choice]()
        if not runner.is_available():
            logger.warning("TEST_RUNNER=%s was requested but is not available here.", choice)
            return None
        return runner

    # Actions first: on a deployed host it is the only safe option, and its
    # presence is an explicit configuration choice.
    for factory in (GitHubActionsRunner, DockerRunner):
        runner = factory()
        if runner.is_available():
            return runner
    return None


def runner_status() -> dict[str, object]:
    """Diagnostic view for the health endpoint."""
    actions, docker = GitHubActionsRunner(), DockerRunner()
    selected = select_runner()
    return {
        "selected": selected.name if selected else None,
        "configured": (os.getenv("TEST_RUNNER") or "auto").strip().lower(),
        "available": {
            "github_actions": actions.is_available(),
            "docker": docker.is_available(),
        },
    }
