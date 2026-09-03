"""Persistent Jira / ADO connections: verify-on-connect, encryption, scoping."""

import pytest
from fastapi.testclient import TestClient

import main
import tracker_client
from db import User, session_scope
from db.base import engine
from db.models import Base
from security import create_session_token, decrypt_token


@pytest.fixture(scope="module")
def client():
    Base.metadata.create_all(engine)
    with TestClient(main.app) as c:
        yield c


@pytest.fixture(scope="module")
def token():
    with session_scope() as s:
        u = User(github_id=8201, login="tracker-user")
        s.add(u)
        s.flush()
        return {"user_id": u.id, "auth": create_session_token(u.id)}


def _h(t):
    return {"Authorization": f"Bearer {t}"}


def test_status_is_disconnected_initially(client, token):
    res = client.get("/api/integrations", headers=_h(token["auth"]))
    assert res.status_code == 200
    body = res.json()
    assert body["jira"]["connected"] is False
    assert body["ado"]["connected"] is False


def test_bad_jira_credentials_are_rejected_at_connect(client, token, monkeypatch):
    def boom(*_a, **_k):
        raise tracker_client.TrackerError("Jira rejected those credentials.", status_code=401)

    monkeypatch.setattr(tracker_client, "verify_jira", boom)
    res = client.post(
        "/api/integrations/jira",
        json={"base_url": "https://x.atlassian.net", "email": "a@b.com", "token": "bad"},
        headers=_h(token["auth"]),
    )
    assert res.status_code == 401
    assert "rejected" in res.json()["detail"]


def test_jira_connects_and_stores_the_token_encrypted(client, token, monkeypatch):
    monkeypatch.setattr(tracker_client, "verify_jira", lambda *a, **k: {"display_name": "Tester"})

    res = client.post(
        "/api/integrations/jira",
        json={"base_url": "https://x.atlassian.net/", "email": "a@b.com", "token": "secret-token"},
        headers=_h(token["auth"]),
    )
    assert res.status_code == 200
    assert res.json()["connected"] is True

    with session_scope() as s:
        user = s.get(User, token["user_id"])
        assert user.encrypted_jira_token != "secret-token"
        assert decrypt_token(user.encrypted_jira_token) == "secret-token"
        assert user.jira_base_url == "https://x.atlassian.net"  # trailing slash trimmed


def test_jira_issues_uses_the_saved_connection(client, token, monkeypatch):
    monkeypatch.setattr(tracker_client, "verify_jira", lambda *a, **k: {})
    client.post(
        "/api/integrations/jira",
        json={"base_url": "https://x.atlassian.net", "email": "a@b.com", "token": "t"},
        headers=_h(token["auth"]),
    )

    captured = {}

    def fake_list(base_url, email, tok, **_k):
        captured["base_url"] = base_url
        captured["token"] = tok
        return [{"key": "PROJ-1", "summary": "Do the thing", "status": "To Do", "type": "Story",
                 "requirement": "[PROJ-1] Do the thing\n\nDetails."}]

    monkeypatch.setattr(tracker_client, "list_jira_issues", fake_list)

    res = client.get("/api/integrations/jira/issues", headers=_h(token["auth"]))
    assert res.status_code == 200
    assert res.json()["issues"][0]["key"] == "PROJ-1"
    assert captured["token"] == "t"  # decrypted server-side


def test_issues_409_when_not_connected(client, token, monkeypatch):
    # ADO never connected for this user
    res = client.get("/api/integrations/ado/work-items", headers=_h(token["auth"]))
    assert res.status_code == 409


def test_disconnect_clears_the_stored_secret(client, token, monkeypatch):
    monkeypatch.setattr(tracker_client, "verify_jira", lambda *a, **k: {})
    client.post(
        "/api/integrations/jira",
        json={"base_url": "https://x.atlassian.net", "email": "a@b.com", "token": "t"},
        headers=_h(token["auth"]),
    )
    assert client.delete("/api/integrations/jira", headers=_h(token["auth"])).status_code == 204

    with session_scope() as s:
        user = s.get(User, token["user_id"])
        assert user.encrypted_jira_token is None
        assert user.jira_base_url is None


def test_integration_status_requires_auth(client):
    assert client.get("/api/integrations").status_code == 401
