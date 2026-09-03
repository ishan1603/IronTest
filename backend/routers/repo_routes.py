"""Repository browsing and connection."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

import github_client
import repo_analysis
from auth import current_user, github_token
from db import Repository, User, get_session, utcnow

router = APIRouter(prefix="/api/repos", tags=["repositories"])


class ConnectRepoRequest(BaseModel):
    full_name: str = Field(..., description="owner/name")


def _serialize(repo: Repository) -> dict:
    return {
        "id": repo.id,
        "github_repo_id": repo.github_repo_id,
        "full_name": repo.full_name,
        "name": repo.name,
        "owner": repo.owner,
        "description": repo.description,
        "private": repo.private,
        "default_branch": repo.default_branch,
        "language": repo.language,
        "html_url": repo.html_url,
        "stack_profile": repo.stack_profile or {},
        "last_run_at": repo.last_run_at.isoformat() if repo.last_run_at else None,
        "connected_at": repo.created_at.isoformat(),
    }


def _owned_repo(session: Session, user: User, repo_id: str) -> Repository:
    repo = session.get(Repository, repo_id)
    # 404 rather than 403 for someone else's repo: a wrong id and another
    # user's id should be indistinguishable.
    if repo is None or repo.user_id != user.id:
        raise HTTPException(status_code=404, detail="Repository not found.")
    return repo


@router.get("/available")
async def available_repositories(
    user: User = Depends(current_user),
    token: str = Depends(github_token),
    session: Session = Depends(get_session),
):
    """Repositories on GitHub, flagged with whether they are already connected."""
    repos = await github_client.list_repositories(token)
    connected = {
        row.github_repo_id: row.id
        for row in session.scalars(select(Repository).where(Repository.user_id == user.id))
    }

    return {
        "repositories": [
            {**repo, "connected": repo["github_repo_id"] in connected,
             "connected_id": connected.get(repo["github_repo_id"])}
            for repo in repos
        ]
    }


@router.get("")
async def connected_repositories(
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
):
    rows = session.scalars(
        select(Repository).where(Repository.user_id == user.id).order_by(Repository.created_at.desc())
    )
    return {"repositories": [_serialize(repo) for repo in rows]}


@router.post("", status_code=201)
async def connect_repository(
    request: ConnectRepoRequest,
    user: User = Depends(current_user),
    token: str = Depends(github_token),
    session: Session = Depends(get_session),
):
    """Connect a repository and detect its stack.

    Reconnecting an already-connected repository refreshes it rather than
    failing, so the action is idempotent from the UI's point of view.
    """
    available = await github_client.list_repositories(token)
    match = next((r for r in available if r["full_name"].lower() == request.full_name.lower()), None)
    if match is None:
        raise HTTPException(
            status_code=404,
            detail=f"{request.full_name} is not accessible with your GitHub account.",
        )

    repo = session.scalar(
        select(Repository).where(
            Repository.user_id == user.id,
            Repository.github_repo_id == match["github_repo_id"],
        )
    )
    if repo is None:
        repo = Repository(user_id=user.id, github_repo_id=match["github_repo_id"])
        session.add(repo)

    repo.full_name = match["full_name"]
    repo.name = match["name"]
    repo.owner = match["owner"]
    repo.description = match["description"]
    repo.private = match["private"]
    repo.default_branch = match["default_branch"]
    repo.language = match["language"]
    repo.html_url = match["html_url"]

    # Stack detection is best-effort: an empty or unreadable repo should still
    # connect, just without a profile.
    try:
        tree = await github_client.fetch_repo_tree(token, repo.full_name, repo.default_branch)
        manifests = {}
        present = {item["path"] for item in tree if item.get("type") == "blob"}
        for name in ("package.json", "pyproject.toml", "requirements.txt", "go.mod", "Cargo.toml", "Gemfile"):
            if name in present:
                manifests[name] = await github_client.fetch_file(token, repo.full_name, name, repo.default_branch)
        repo.stack_profile = repo_analysis.detect_stack(tree, manifests).to_dict()
    except github_client.GitHubError:
        repo.stack_profile = {}

    session.commit()
    return _serialize(repo)


@router.get("/{repo_id}/branches")
async def repository_branches(
    repo_id: str,
    user: User = Depends(current_user),
    token: str = Depends(github_token),
    session: Session = Depends(get_session),
):
    repo = _owned_repo(session, user, repo_id)
    branches = await github_client.list_branches(token, repo.full_name)
    # Surface the default branch first.
    branches.sort(key=lambda b: (b != repo.default_branch, b))
    return {"branches": branches, "default": repo.default_branch}


@router.get("/{repo_id}")
async def get_repository(
    repo_id: str,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
):
    return _serialize(_owned_repo(session, user, repo_id))


@router.post("/{repo_id}/rescan")
async def rescan_repository(
    repo_id: str,
    user: User = Depends(current_user),
    token: str = Depends(github_token),
    session: Session = Depends(get_session),
):
    """Re-detect the stack, for a repo that has changed since it was connected."""
    repo = _owned_repo(session, user, repo_id)
    tree = await github_client.fetch_repo_tree(token, repo.full_name, repo.default_branch)

    manifests = {}
    present = {item["path"] for item in tree if item.get("type") == "blob"}
    for name in ("package.json", "pyproject.toml", "requirements.txt", "go.mod", "Cargo.toml", "Gemfile"):
        if name in present:
            manifests[name] = await github_client.fetch_file(token, repo.full_name, name, repo.default_branch)

    repo.stack_profile = repo_analysis.detect_stack(tree, manifests).to_dict()
    repo.updated_at = utcnow()
    session.commit()
    return _serialize(repo)


@router.delete("/{repo_id}", status_code=204)
async def disconnect_repository(
    repo_id: str,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
):
    session.delete(_owned_repo(session, user, repo_id))
    session.commit()
