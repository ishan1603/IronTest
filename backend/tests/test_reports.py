"""Sharing a run and the public report view."""

import pytest
from fastapi.testclient import TestClient

import main
from db import PipelineRun, User, session_scope
from db.base import engine
from db.models import Base
from security import create_session_token


@pytest.fixture(scope="module")
def client():
    Base.metadata.create_all(engine)
    with TestClient(main.app) as c:
        yield c


@pytest.fixture(scope="module")
def run_and_token():
    with session_scope() as s:
        user = User(github_id=6001, login="reporter")
        s.add(user)
        s.flush()
        run = PipelineRun(
            user_id=user.id,
            status="complete",
            mode="existing_code",
            story_text="Checkout applies a discount code",
            story_result={"acceptance_criteria": ["valid code reduces total"], "modules": ["Billing"]},
            tests_result=[{"id": "TC-001", "module": "Billing", "description": "applies discount", "expected_result": "10% off"}],
            execution_result={"results": [{"test_id": "TC-001", "status": "fail", "error_message": "assert 90 == 81"}], "duration_seconds": 2.0},
            defects_result={"deployment_recommendation": "NO-GO", "overall_confidence_score": 30, "recommendation_rationale": "core case fails"},
            fixes_result=[{"test_id": "TC-001", "target_file": "billing.py", "explanation": "rounding", "suggested_change": "- a\n+ b", "confidence": "medium"}],
            passed=0, failed=1, errors=0, skipped=0, pass_rate=0.0, confidence_score=30,
        )
        s.add(run)
        s.flush()
        return {"run_id": run.id, "token": create_session_token(user.id)}


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_share_creates_a_stable_token(client, run_and_token):
    r1 = client.post(f"/api/analytics/runs/{run_and_token['run_id']}/share", headers=_auth(run_and_token["token"]))
    r2 = client.post(f"/api/analytics/runs/{run_and_token['run_id']}/share", headers=_auth(run_and_token["token"]))
    assert r1.status_code == 200
    assert r1.json()["token"] == r2.json()["token"]  # idempotent


def test_public_report_needs_no_auth_and_hides_identity(client, run_and_token):
    token = client.post(
        f"/api/analytics/runs/{run_and_token['run_id']}/share", headers=_auth(run_and_token["token"])
    ).json()["token"]

    res = client.get(f"/api/reports/{token}")  # no Authorization header
    assert res.status_code == 200
    body = res.json()

    assert body["repository"] is None
    assert "user_id" not in body
    assert body["defects"]["deployment_recommendation"] == "NO-GO"
    assert body["fixes"][0]["test_id"] == "TC-001"


def test_revoked_link_stops_working(client, run_and_token):
    token = client.post(
        f"/api/analytics/runs/{run_and_token['run_id']}/share", headers=_auth(run_and_token["token"])
    ).json()["token"]
    assert client.get(f"/api/reports/{token}").status_code == 200

    client.delete(f"/api/analytics/runs/{run_and_token['run_id']}/share", headers=_auth(run_and_token["token"]))
    assert client.get(f"/api/reports/{token}").status_code == 404


def test_markdown_export_is_downloadable_and_has_the_essentials(client, run_and_token):
    token = client.post(
        f"/api/analytics/runs/{run_and_token['run_id']}/share", headers=_auth(run_and_token["token"])
    ).json()["token"]

    res = client.get(f"/api/reports/{token}/export.md")
    assert res.status_code == 200
    assert "attachment" in res.headers["content-disposition"]
    text = res.text
    assert "# IronTest report" in text
    assert "NO-GO" in text
    assert "TC-001" in text
    assert "Suggested fixes" in text


def test_an_unknown_token_is_a_clean_404(client):
    res = client.get("/api/reports/definitely-not-a-real-token")
    assert res.status_code == 404
    assert "invalid or was revoked" in res.json()["detail"]


def test_cannot_share_another_users_run(client, run_and_token):
    with session_scope() as s:
        intruder = User(github_id=6099, login="intruder")
        s.add(intruder)
        s.flush()
        intruder_token = create_session_token(intruder.id)

    res = client.post(
        f"/api/analytics/runs/{run_and_token['run_id']}/share", headers=_auth(intruder_token)
    )
    assert res.status_code == 404
