"""GitHub REST client: OAuth exchange, identity, and repository listing."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from config import get_settings

logger = logging.getLogger(__name__)

API_BASE = "https://api.github.com"
OAUTH_AUTHORIZE = "https://github.com/login/oauth/authorize"
OAUTH_TOKEN = "https://github.com/login/oauth/access_token"

# read:user + user:email identify the account; repo is required to read the
# private repositories a user selects. Nothing here grants write access.
OAUTH_SCOPES = "read:user user:email repo"

REQUEST_TIMEOUT = httpx.Timeout(20.0, connect=10.0)


class GitHubError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def authorize_url(state: str) -> str:
    settings = get_settings()
    params = httpx.QueryParams(
        {
            "client_id": settings.github_client_id,
            "redirect_uri": settings.github_callback_url,
            "scope": OAUTH_SCOPES,
            "state": state,
            # Force the account picker so switching accounts is possible.
            "allow_signup": "true",
        }
    )
    return f"{OAUTH_AUTHORIZE}?{params}"


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


async def exchange_code_for_token(code: str) -> tuple[str, str]:
    """Trade an OAuth code for (access_token, granted_scopes)."""
    settings = get_settings()
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        response = await client.post(
            OAUTH_TOKEN,
            headers={"Accept": "application/json"},
            data={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "code": code,
                "redirect_uri": settings.github_callback_url,
            },
        )

    if response.status_code != 200:
        raise GitHubError("GitHub rejected the token exchange.", status_code=response.status_code)

    payload = response.json()
    # GitHub returns 200 with an error body for a reused or expired code.
    if payload.get("error"):
        raise GitHubError(payload.get("error_description") or payload["error"], status_code=400)

    token = payload.get("access_token")
    if not token:
        raise GitHubError("GitHub did not return an access token.", status_code=400)

    return token, payload.get("scope", "")


async def _get(client: httpx.AsyncClient, token: str, path: str, **params) -> Any:
    response = await client.get(f"{API_BASE}{path}", headers=_headers(token), params=params or None)
    if response.status_code == 401:
        raise GitHubError("GitHub token is no longer valid. Please sign in again.", status_code=401)
    if response.status_code == 403 and "rate limit" in response.text.lower():
        raise GitHubError("GitHub API rate limit reached. Try again shortly.", status_code=429)
    if response.status_code >= 400:
        raise GitHubError(f"GitHub request failed: {path}", status_code=response.status_code)
    return response.json()


async def fetch_viewer(token: str) -> dict[str, Any]:
    """The authenticated user, with a usable email even when the profile hides it."""
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        user = await _get(client, token, "/user")

        email = user.get("email")
        if not email:
            try:
                emails = await _get(client, token, "/user/emails")
                primary = next(
                    (item for item in emails if item.get("primary") and item.get("verified")),
                    None,
                )
                email = (primary or {}).get("email")
            except GitHubError:
                # user:email may not have been granted; identity still works.
                email = None

    return {
        "github_id": user["id"],
        "login": user["login"],
        "name": user.get("name") or user["login"],
        "email": email,
        "avatar_url": user.get("avatar_url"),
    }


async def list_repositories(token: str, *, limit: int = 100) -> list[dict[str, Any]]:
    """Repositories the user can access, most recently pushed first."""
    collected: list[dict[str, Any]] = []
    per_page = 100

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        page = 1
        while len(collected) < limit:
            batch = await _get(
                client,
                token,
                "/user/repos",
                per_page=per_page,
                page=page,
                sort="pushed",
                direction="desc",
                affiliation="owner,collaborator,organization_member",
            )
            if not isinstance(batch, list) or not batch:
                break
            collected.extend(batch)
            if len(batch) < per_page:
                break
            page += 1

    return [
        {
            "github_repo_id": repo["id"],
            "full_name": repo["full_name"],
            "name": repo["name"],
            "owner": repo["owner"]["login"],
            "description": repo.get("description"),
            "private": bool(repo.get("private")),
            "default_branch": repo.get("default_branch") or "main",
            "language": repo.get("language"),
            "html_url": repo.get("html_url", ""),
            "pushed_at": repo.get("pushed_at"),
            "stargazers_count": repo.get("stargazers_count", 0),
        }
        for repo in collected[:limit]
    ]


async def fetch_repo_tree(token: str, full_name: str, ref: str) -> list[dict[str, Any]]:
    """Flat file listing for a ref. Large repos come back truncated by GitHub."""
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        payload = await _get(client, token, f"/repos/{full_name}/git/trees/{ref}", recursive="1")

    if payload.get("truncated"):
        logger.info("Tree for %s@%s was truncated by GitHub", full_name, ref)

    return [
        {"path": item["path"], "type": item["type"], "size": item.get("size", 0)}
        for item in payload.get("tree", [])
    ]


async def fetch_file(token: str, full_name: str, path: str, ref: str) -> str:
    """Raw file contents, or "" when the path is missing or is not a text blob."""
    headers = {**_headers(token), "Accept": "application/vnd.github.raw"}
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        response = await client.get(
            f"{API_BASE}/repos/{full_name}/contents/{path}",
            headers=headers,
            params={"ref": ref},
        )

    if response.status_code == 404:
        return ""
    if response.status_code >= 400:
        raise GitHubError(f"Could not read {path}", status_code=response.status_code)

    try:
        return response.text
    except UnicodeDecodeError:
        return ""
