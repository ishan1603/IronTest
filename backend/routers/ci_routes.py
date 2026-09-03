"""CI entry point: a GitHub Action (or any job) triggers a run and gets a
comment back on the pull request.

Authenticated with a per-user key in the X-IronTest-Key header, not a session.
The run uses the user's stored GitHub token to clone and to comment.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from db import PipelineRun, Repository, User, get_session
from llm import configured_providers
from models import PipelineMode
from security import decrypt_token

router = APIRouter(prefix="/api/ci", tags=["ci"])


class CIRunRequest(BaseModel):
    repository: str = Field(..., description="owner/name, must be connected by the key's owner")
    head_ref: str = Field(..., description="Branch/ref to test")
    base_ref: str | None = Field(default=None, description="Base branch for the regression gate")
    requirement: str | None = Field(default=None, max_length=20_000)
    mode: PipelineMode = "existing_code"
    pr_number: int | None = Field(default=None, description="PR to comment on when done")


def _user_for_key(session: Session, key: str | None) -> User:
    if not key:
        raise HTTPException(status_code=401, detail="Missing X-IronTest-Key header.")
    user = session.scalar(select(User).where(User.api_key == key))
    if user is None:
        raise HTTPException(status_code=401, detail="Unrecognised IronTest key.")
    return user


@router.post("/run", status_code=202)
async def ci_run(
    request: CIRunRequest,
    x_irontest_key: str | None = Header(default=None),
    session: Session = Depends(get_session),
):
    from agents.orchestrator import RunRequest
    from main import orchestrator, session_manager

    user = _user_for_key(session, x_irontest_key)

    if not configured_providers():
        raise HTTPException(status_code=503, detail="The IronTest server has no AI provider configured.")

    github_token = decrypt_token(user.encrypted_access_token)
    if not github_token:
        raise HTTPException(
            status_code=409,
            detail="The key's owner has no valid GitHub connection. Sign in to IronTest and reconnect.",
        )

    repo = session.scalar(
        select(Repository).where(
            Repository.user_id == user.id,
            Repository.full_name.ilike(request.repository),
        )
    )
    if repo is None:
        raise HTTPException(
            status_code=404,
            detail=f"{request.repository} is not connected by this key's owner. Connect it in IronTest first.",
        )

    requirement = (request.requirement or "").strip() or (
        f"Regression sweep for {repo.full_name}@{request.head_ref}: generate and run tests "
        f"for the core modules and their edge cases."
    )

    stream_id = await session_manager.create_session(user.id)
    import asyncio

    asyncio.create_task(
        orchestrator.run_pipeline(
            stream_id,
            RunRequest(
                user_id=user.id,
                story_text=requirement,
                repository_id=repo.id,
                mode=request.mode,
                source="ci",
                github_token=github_token,
                repo_full_name=repo.full_name,
                repo_ref=request.head_ref,
                compare_ref=(request.base_ref or "").strip(),
                pr_comment=(
                    {"full_name": repo.full_name, "pr_number": request.pr_number}
                    if request.pr_number
                    else None
                ),
            ),
        )
    )
    return {
        "status": "queued",
        "stream_id": stream_id,
        "message": "IronTest is running. A comment will be posted to the PR when it finishes."
        if request.pr_number
        else "IronTest is running.",
    }
