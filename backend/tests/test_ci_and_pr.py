"""CI trigger auth and the open-a-PR endpoint."""

import pytest
from fastapi.testclient import TestClient

import main
from db import PipelineRun, Repository, User, session_scope
from db.base import engine
from db.models import Base
from security import create_session_token, encrypt_token


@pytest.fixture(scope="module")
def client():
    Base.metadata.create_all(engine)
    with TestClient(main.app) as c:
        yield c


@pytest.fixture(scope="module")
def fixtures():
    with session_scope() as s:
        user = User(github_id=7101, login="ci-user", api_key="irt_known_key")
        user.encrypted_access_token = encrypt_token("gho_fake_token")
        s.add(user)
        s.flush()
        repo = Repository(
            user_id=user.id, github_repo_id=7777, full_name="ci-user/app",
            name="app", owner="ci-user", default_branch="main",
        )
        s.add(repo)
        s.flush()
        run = PipelineRun(
            user_id=user.id, repository_id=repo.id, status="complete", mode="existing_code",
            story_text="Discount codes", passed=3, failed=1, pass_rate=0.75, confidence_score=60,
            tests_result=[{"id": "TC-001", "module": "M", "description": "d"}],
            suite_files=[{"path": "tests/test_irontest_generated.py", "content": "def test_x():\n    assert True\n"}],
        )
        s.add(run)
        # a second run with no suite_files (standalone / legacy)
        legacy = PipelineRun(user_id=user.id, status="complete", mode="existing_code", story_text="x")
        s.add(legacy)
        s.flush()
        return {
            "token": create_session_token(user.id),
            "run_id": run.id,
            "legacy_run_id": legacy.id,
            "repo_id": repo.id,
        }


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


# -- CI trigger --------------------------------------------------------------


def test_ci_run_rejects_a_missing_key(client):
    res = client.post("/api/ci/run", json={"repository": "ci-user/app", "head_ref": "feat"})
    assert res.status_code == 401
    assert "Missing" in res.json()["detail"]


def test_ci_run_rejects_an_unknown_key(client):
    res = client.post(
        "/api/ci/run",
        json={"repository": "ci-user/app", "head_ref": "feat"},
        headers={"X-IronTest-Key": "irt_not_a_real_key"},
    )
    assert res.status_code == 401
    assert "Unrecognised" in res.json()["detail"]


def test_ci_run_404s_for_a_repo_the_key_owner_has_not_connected(client, fixtures):
    res = client.post(
        "/api/ci/run",
        json={"repository": "someone-else/other", "head_ref": "feat"},
        headers={"X-IronTest-Key": "irt_known_key"},
    )
    assert res.status_code == 404
    assert "not connected" in res.json()["detail"]


def test_ci_run_queues_for_a_valid_key_and_connected_repo(client, fixtures, monkeypatch):
    # Do not actually launch the pipeline.
    import routers.ci_routes as ci

    launched = {}

    async def fake_run_pipeline(session_id, request):
        launched["repo"] = request.repo_full_name
        launched["head"] = request.repo_ref
        launched["pr"] = request.pr_comment

    monkeypatch.setattr(main.orchestrator, "run_pipeline", fake_run_pipeline)
    monkeypatch.setattr(ci, "configured_providers", lambda: [object()])

    res = client.post(
        "/api/ci/run",
        json={"repository": "ci-user/app", "head_ref": "feature-x", "base_ref": "main", "pr_number": 12},
        headers={"X-IronTest-Key": "irt_known_key"},
    )
    assert res.status_code == 202
    # give the created task a tick
    import asyncio

    asyncio.get_event_loop().run_until_complete(asyncio.sleep(0.05))
    assert launched["repo"] == "ci-user/app"
    assert launched["head"] == "feature-x"
    assert launched["pr"] == {"full_name": "ci-user/app", "pr_number": 12}


# -- open a PR -------------------------------------------------------------


def test_pull_request_needs_generated_files(client, fixtures):
    res = client.post(
        f"/api/analytics/runs/{fixtures['legacy_run_id']}/pull-request", headers=_auth(fixtures["token"])
    )
    assert res.status_code == 400
    assert "no generated test files" in res.json()["detail"]


def test_pull_request_creates_a_branch_commits_and_opens_a_pr(client, fixtures, monkeypatch):
    import routers.integration_routes as integ

    calls = {"put": [], "pr": None, "branch": None}

    async def fake_sha(*_a, **_k):
        return "basesha"

    async def fake_create_branch(_t, _r, branch, _sha):
        calls["branch"] = branch

    async def fake_put_file(_t, _r, path, _c, message, branch):
        calls["put"].append((path, branch))

    async def fake_create_pr(_t, _r, *, title, body, head, base):
        calls["pr"] = {"title": title, "head": head, "base": base}
        return {"html_url": "https://github.com/ci-user/app/pull/9", "number": 9}

    monkeypatch.setattr(integ.github_client, "default_branch_sha", fake_sha)
    monkeypatch.setattr(integ.github_client, "create_branch", fake_create_branch)
    monkeypatch.setattr(integ.github_client, "put_file", fake_put_file)
    monkeypatch.setattr(integ.github_client, "create_pull_request", fake_create_pr)

    res = client.post(
        f"/api/analytics/runs/{fixtures['run_id']}/pull-request", headers=_auth(fixtures["token"])
    )
    assert res.status_code == 200
    body = res.json()
    assert body["pull_request_url"].endswith("/pull/9")
    assert calls["branch"].startswith("irontest/tests-")
    assert calls["put"][0][0] == "tests/test_irontest_generated.py"
    assert calls["pr"]["base"] == "main"


def test_cannot_open_a_pr_on_another_users_run(client, fixtures):
    with session_scope() as s:
        other = User(github_id=7199, login="other")
        s.add(other)
        s.flush()
        other_token = create_session_token(other.id)

    res = client.post(
        f"/api/analytics/runs/{fixtures['run_id']}/pull-request", headers=_auth(other_token)
    )
    assert res.status_code == 404
