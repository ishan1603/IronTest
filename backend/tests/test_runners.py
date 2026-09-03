"""Result parsing and backend selection.

Results come from the runner's own JUnit report. A run that produced no
report must surface as failed with its logs, never as a pass -- that
substitution is exactly what the old execution layer did.
"""

import pytest

from runners import runner_status, select_runner
from runners.actions_runner import GitHubActionsRunner
from runners.base import NOT_FOUND, TIMED_OUT, failure_result, parse_junit, run_subprocess
from runners.docker_runner import DockerRunner
from runners.local_repo_runner import LocalRepoRunner

PYTEST_REPORT = """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="pytest" errors="1" failures="1" skipped="1" tests="4">
    <testcase classname="tests.test_billing" name="test_TC-001_applies_discount" time="0.01"/>
    <testcase classname="tests.test_billing" name="test_TC-002_rejects_expired">
      <failure message="assert 100 == 90">E assert 100 == 90</failure>
    </testcase>
    <testcase classname="tests.test_billing" name="test_TC-003_boom">
      <error message="ImportError: no module named app">traceback here</error>
    </testcase>
    <testcase classname="tests.test_billing" name="test_TC-004_pending">
      <skipped message="not implemented"/>
    </testcase>
  </testsuite>
</testsuites>
"""

SINGLE_SUITE_REPORT = """<testsuite name="jest" tests="1">
  <testcase classname="cart" name="TC-010 applies tax"/>
</testsuite>
"""


def test_parses_every_outcome_from_a_junit_report():
    results = {r.test_id: r for r in parse_junit(PYTEST_REPORT)}

    assert results["TC-001"].status == "pass"
    assert results["TC-002"].status == "fail"
    assert results["TC-003"].status == "error"
    assert results["TC-004"].status == "skipped"


def test_failure_detail_is_preserved():
    results = {r.test_id: r for r in parse_junit(PYTEST_REPORT)}
    assert "assert 100 == 90" in results["TC-002"].error_message
    assert "ImportError" in results["TC-003"].error_message


def test_handles_a_bare_testsuite_root():
    """pytest emits <testsuites>, jest and vitest emit a bare <testsuite>."""
    results = parse_junit(SINGLE_SUITE_REPORT)
    assert len(results) == 1
    assert results[0].test_id == "TC-010"
    assert results[0].status == "pass"


def test_falls_back_to_classname_when_no_case_id_is_embedded():
    report = '<testsuite><testcase classname="pkg.mod" name="test_something"/></testsuite>'
    assert parse_junit(report)[0].test_id == "pkg.mod::test_something"


@pytest.mark.parametrize(
    "payload", ["", "   ", "not xml at all", "<testsuite><unclosed>"], ids=["empty", "blank", "prose", "malformed"]
)
def test_unparseable_report_yields_no_results_rather_than_raising(payload):
    assert parse_junit(payload) == []


def test_a_run_without_results_is_a_failure_not_a_pass():
    """The critical invariant: absence of evidence is never reported as success."""
    result = failure_result("docker", "no report produced", output="install failed")

    assert result.status == "failed"
    assert result.results == []
    assert result.produced_results is False
    assert "install failed" in result.raw_output


def test_parses_junit_emitted_by_a_real_pytest_run(tmp_path):
    """Validates the parser against genuine output, not a hand-written fixture.

    Hand-written XML can drift from what pytest actually emits; this generates
    a report by running pytest for real and parses that.
    """
    import subprocess
    import sys

    suite = tmp_path / "test_generated.py"
    suite.write_text(
        "import pytest\n"
        "def test_TC_001_passes():\n    assert sum([1, 2, 3]) == 6\n"
        "def test_TC_002_fails():\n    assert sum([1, 2, 3]) == 7\n"
        "@pytest.mark.skip(reason='not implemented yet')\n"
        "def test_TC_003_skipped():\n    pass\n",
        encoding="utf-8",
    )
    report = tmp_path / "results.xml"
    subprocess.run(
        [sys.executable, "-m", "pytest", str(suite), f"--junitxml={report}", "-q"],
        capture_output=True,
        cwd=tmp_path,
    )

    results = {r.test_id: r for r in parse_junit(report.read_text(encoding="utf-8"))}

    assert results["TC-001"].status == "pass"
    assert results["TC-002"].status == "fail"
    assert results["TC-003"].status == "skipped"
    assert "assert 6 == 7" in results["TC-002"].error_message


# -- subprocess execution -----------------------------------------------------


def test_run_subprocess_captures_output_and_exit_code():
    import sys

    code, out = run_subprocess([sys.executable, "-c", "print('hello'); raise SystemExit(3)"], timeout=15)
    assert code == 3
    assert "hello" in out


def test_run_subprocess_reports_a_missing_executable():
    code, out = run_subprocess(["this-command-does-not-exist-xyz"], timeout=5)
    assert code == NOT_FOUND
    assert "not" in out.lower()


def test_run_subprocess_times_out():
    import sys

    code, out = run_subprocess([sys.executable, "-c", "import time; time.sleep(30)"], timeout=1)
    assert code == TIMED_OUT
    assert "exceeded" in out


def test_runner_subprocess_works_under_a_selector_event_loop():
    """Regression: uvicorn installs a Selector loop on Windows, and
    asyncio.create_subprocess_exec raises NotImplementedError there. The
    runners must go through a worker thread instead."""
    import asyncio
    import sys

    loop = asyncio.SelectorEventLoop()
    try:
        code, out = loop.run_until_complete(
            asyncio.to_thread(run_subprocess, [sys.executable, "-c", "print('ok')"], timeout=15)
        )
    finally:
        loop.close()

    assert code == 0
    assert "ok" in out


# -- backend selection -----------------------------------------------------


@pytest.fixture(autouse=True)
def clean_runner_env(monkeypatch):
    for key in ("TEST_RUNNER", "ACTIONS_RUNNER_REPO", "ACTIONS_DISPATCH_TOKEN", "ALLOW_HOST_TEST_EXECUTION"):
        monkeypatch.delenv(key, raising=False)
    # Most selection tests want to reason about the sandboxed backends alone.
    monkeypatch.setattr(LocalRepoRunner, "is_available", lambda self: False)


def test_actions_runner_needs_both_repo_and_token(monkeypatch):
    assert GitHubActionsRunner().is_available() is False

    monkeypatch.setenv("ACTIONS_RUNNER_REPO", "me/runner")
    assert GitHubActionsRunner().is_available() is False

    monkeypatch.setenv("ACTIONS_DISPATCH_TOKEN", "ghp_x")
    assert GitHubActionsRunner().is_available() is True


def test_auto_prefers_actions_when_configured(monkeypatch):
    monkeypatch.setenv("ACTIONS_RUNNER_REPO", "me/runner")
    monkeypatch.setenv("ACTIONS_DISPATCH_TOKEN", "ghp_x")
    monkeypatch.setattr(DockerRunner, "is_available", lambda self: True)

    assert select_runner().name == "github_actions"


def test_auto_falls_back_to_docker(monkeypatch):
    monkeypatch.setattr(DockerRunner, "is_available", lambda self: True)
    assert select_runner().name == "docker"


def test_auto_returns_none_when_nothing_is_available(monkeypatch):
    monkeypatch.setattr(DockerRunner, "is_available", lambda self: False)
    assert select_runner() is None


def test_explicit_choice_that_is_unavailable_returns_none(monkeypatch):
    monkeypatch.setenv("TEST_RUNNER", "docker")
    monkeypatch.setattr(DockerRunner, "is_available", lambda self: False)
    assert select_runner() is None


def test_auto_falls_back_to_host_execution_only_after_the_sandboxes(monkeypatch):
    """local_host is the last resort, never chosen over Docker or Actions."""
    monkeypatch.setattr(DockerRunner, "is_available", lambda self: True)
    monkeypatch.setattr(LocalRepoRunner, "is_available", lambda self: True)
    assert select_runner().name == "docker"

    monkeypatch.setattr(DockerRunner, "is_available", lambda self: False)
    assert select_runner().name == "local_host"


def test_host_execution_is_gated_by_environment(monkeypatch):
    # This test exercises the real is_available; drop the autouse stub.
    monkeypatch.undo()
    monkeypatch.setattr("runners.local_repo_runner.shutil.which", lambda _name: "/usr/bin/git")
    from config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SECRET_KEY", "x")
    get_settings.cache_clear()
    assert LocalRepoRunner().is_available() is False

    monkeypatch.setenv("ALLOW_HOST_TEST_EXECUTION", "true")
    assert LocalRepoRunner().is_available() is True

    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.delenv("ALLOW_HOST_TEST_EXECUTION", raising=False)
    get_settings.cache_clear()
    assert LocalRepoRunner().is_available() is True
    get_settings.cache_clear()


def test_status_flags_whether_the_selected_runner_is_sandboxed(monkeypatch):
    monkeypatch.setattr(DockerRunner, "is_available", lambda self: True)
    assert runner_status()["sandboxed"] is True

    monkeypatch.setattr(DockerRunner, "is_available", lambda self: False)
    monkeypatch.setattr(LocalRepoRunner, "is_available", lambda self: True)
    assert runner_status()["sandboxed"] is False


def test_status_reports_availability_without_secrets(monkeypatch):
    monkeypatch.setenv("ACTIONS_RUNNER_REPO", "me/runner")
    monkeypatch.setenv("ACTIONS_DISPATCH_TOKEN", "ghp_supersecret")

    status = runner_status()
    assert status["available"]["github_actions"] is True
    assert "ghp_supersecret" not in str(status)


# -- container hardening ---------------------------------------------------


def test_container_script_never_puts_the_token_on_a_command_line():
    """The token must reach git via a credentials file, not argv."""
    from runners.base import GeneratedFile, RunnerRequest

    request = RunnerRequest(
        repo_full_name="acme/app",
        ref="main",
        github_token="ghp_secret_value",
        stack={"language": "python", "install_command": "pip install -r requirements.txt",
               "test_command": "pytest --junitxml=results.xml"},
        files=[GeneratedFile(path="tests/test_gen.py", content="def test_x(): assert True")],
    )
    script = DockerRunner()._build_script(request)

    assert "ghp_secret_value" not in script
    assert "$GITHUB_TOKEN" in script
    assert "git clone" in script


def test_container_script_lets_test_failures_through():
    """A failing suite is a result; only setup runs under `set -e`."""
    from runners.base import RunnerRequest

    script = DockerRunner()._build_script(
        RunnerRequest(
            repo_full_name="acme/app",
            ref="main",
            github_token="t",
            stack={"language": "python", "test_command": "pytest"},
        )
    )
    assert "set +e" in script
    assert "TEST_EXIT" in script
