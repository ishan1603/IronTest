"""Every data route must reject an unauthenticated or foreign request.

Before user accounts existed each of these endpoints was fully public, so
these tests pin the boundary rather than trusting each handler to check.
"""

import asyncio

import pytest
from fastapi.testclient import TestClient

import main
from db import Repository, User, session_scope
from db.base import engine
from db.models import Base
from security import create_session_token


@pytest.fixture(scope="module")
def client():
    Base.metadata.create_all(engine)
    with TestClient(main.app) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def alice():
    with session_scope() as session:
        user = User(github_id=9001, login="alice")
        session.add(user)
        session.flush()
        repo = Repository(
            user_id=user.id,
            github_repo_id=555,
            full_name="alice/project",
            name="project",
            owner="alice",
        )
        session.add(repo)
        session.flush()
        return {"user_id": user.id, "repo_id": repo.id, "token": create_session_token(user.id)}


@pytest.fixture(scope="module")
def bob():
    with session_scope() as session:
        user = User(github_id=9002, login="bob")
        session.add(user)
        session.flush()
        return {"user_id": user.id, "token": create_session_token(user.id)}


PROTECTED = [
    ("GET", "/api/auth/me"),
    ("GET", "/api/repos"),
    ("GET", "/api/repos/available"),
    ("POST", "/api/repos"),
    ("GET", "/api/chats"),
    ("POST", "/api/chats"),
    ("POST", "/api/analyze"),
    ("POST", "/api/history/story"),
    ("POST", "/api/ingest/jira"),
    ("POST", "/api/ingest/azure-devops"),
]


@pytest.mark.parametrize("method,path", PROTECTED, ids=[f"{m}:{p}" for m, p in PROTECTED])
def test_route_requires_authentication(client, method, path):
    response = client.request(method, path, json={})
    assert response.status_code == 401, f"{method} {path} returned {response.status_code}"


@pytest.mark.parametrize("header", ["", "Token abc", "Bearer ", "Bearer not-a-jwt"])
def test_malformed_authorization_headers_are_rejected(client, header):
    response = client.get("/api/auth/me", headers={"Authorization": header} if header else {})
    assert response.status_code == 401


def test_valid_token_identifies_the_user(client, alice):
    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {alice['token']}"})

    assert response.status_code == 200
    assert response.json()["login"] == "alice"


def test_me_never_returns_the_github_token(client, alice):
    body = client.get("/api/auth/me", headers={"Authorization": f"Bearer {alice['token']}"}).json()

    assert "encrypted_access_token" not in body
    assert not any("token" in key.lower() for key in body)


def test_another_users_repository_is_not_found(client, alice, bob):
    """A foreign id must be indistinguishable from a wrong one."""
    response = client.get(
        f"/api/repos/{alice['repo_id']}",
        headers={"Authorization": f"Bearer {bob['token']}"},
    )
    assert response.status_code == 404


def test_owner_can_read_their_own_repository(client, alice):
    response = client.get(
        f"/api/repos/{alice['repo_id']}",
        headers={"Authorization": f"Bearer {alice['token']}"},
    )
    assert response.status_code == 200
    assert response.json()["full_name"] == "alice/project"


def test_chat_cannot_be_created_against_a_foreign_repository(client, alice, bob):
    response = client.post(
        "/api/chats",
        json={"repository_id": alice["repo_id"]},
        headers={"Authorization": f"Bearer {bob['token']}"},
    )
    assert response.status_code == 404


def test_stream_rejects_a_missing_or_invalid_token(client):
    assert client.get("/api/stream/whatever").status_code == 422
    assert client.get("/api/stream/whatever", params={"token": "bogus"}).status_code == 401


def test_stream_rejects_a_valid_token_for_a_session_owned_by_someone_else(client, alice, bob):
    """A session id plus a valid token for a different account is still a 404."""
    # Registered directly rather than through create_session, so the manager's
    # asyncio.Lock binds to the app's loop rather than a throwaway one.
    session_id = "session-owned-by-alice"
    main.session_manager.sessions[session_id] = asyncio.Queue()
    main.session_manager.owners[session_id] = alice["user_id"]
    try:
        response = client.get(f"/api/stream/{session_id}", params={"token": bob["token"]})
        assert response.status_code == 404
    finally:
        main.session_manager.sessions.pop(session_id, None)
        main.session_manager.owners.pop(session_id, None)


def test_health_is_public_and_reports_provider_state(client):
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"ok", "degraded"}
    assert isinstance(body["llm_providers"], list)
    # Diagnostics must never carry key material.
    assert not any("api_key" in str(p).lower() and len(str(p.get("key_env", ""))) > 40 for p in body["llm_providers"])
