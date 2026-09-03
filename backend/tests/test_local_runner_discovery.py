"""The host runner must run the generated file even when the repo's own pytest
config would send discovery elsewhere."""

import asyncio

import pytest

from runners.base import GeneratedFile, RunnerRequest
from runners.local_repo_runner import LocalRepoRunner


@pytest.fixture
def fake_repo(tmp_path):
    """A checkout whose pyproject would hijack pytest discovery."""
    (tmp_path / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\n"
        "testpaths = ['does_not_exist']\n"
        "addopts = '--strict-markers -p no:randomly'\n",
        encoding="utf-8",
    )
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "app" / "calc.py").write_text(
        "def add(a, b):\n    return a + b\n", encoding="utf-8"
    )
    return tmp_path


def _request(files):
    return RunnerRequest(
        repo_full_name="x/y",
        ref="main",
        github_token="t",
        stack={"language": "python"},
        files=files,
        timeout_seconds=120,
    )


def test_generated_file_runs_despite_repo_pytest_config(fake_repo):
    runner = LocalRepoRunner()
    files = [
        GeneratedFile(
            path="tests/test_irontest_generated.py",
            content=(
                "from app.calc import add\n"
                "def test_TC_001_adds():\n    assert add(2, 3) == 5\n"
                "def test_TC_002_wrong():\n    assert add(2, 2) == 5\n"
            ),
        )
    ]
    # Write the file into the checkout as run() would.
    target = fake_repo / files[0].path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(files[0].content, encoding="utf-8")

    log, results = asyncio.run(runner._run_python(str(fake_repo), _request(files), budget=90))

    by_id = {r.test_id: r.status for r in results}
    assert by_id.get("TC-001") == "pass", log[-800:]
    assert by_id.get("TC-002") == "fail", log[-800:]


def test_zero_collected_tests_gets_a_specific_note(fake_repo):
    runner = LocalRepoRunner()
    files = [GeneratedFile(path="tests/test_empty.py", content="# nothing here\n")]
    (fake_repo / "tests").mkdir(parents=True, exist_ok=True)
    (fake_repo / "tests" / "test_empty.py").write_text("# nothing here\n", encoding="utf-8")

    log, results = asyncio.run(runner._run_python(str(fake_repo), _request(files), budget=60))

    assert results == []
    assert "collected 0 tests" in log
