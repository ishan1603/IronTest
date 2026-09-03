"""Per-repository conversations and the runs launched from them."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth import current_user, github_token
from db import Chat, Message, PipelineRun, Repository, User, get_session, utcnow
from models import PipelineMode

router = APIRouter(prefix="/api/chats", tags=["chats"])

#: Chat titles are derived from the opening message when the user has not
#: named the chat, mirroring how most assistants label a thread.
TITLE_LENGTH = 60


class CreateChatRequest(BaseModel):
    repository_id: str
    title: str | None = None


class SendMessageRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=20_000)


class StartRunRequest(BaseModel):
    # Optional for existing-code runs: the pipeline can test a repository as it
    # stands with no prompt. A specification run must describe the feature.
    requirement: str | None = Field(default=None, max_length=20_000)
    mode: PipelineMode = "existing_code"
    send_email: bool = False
    recipient_email: str | None = None


def _resolve_requirement(request: "StartRunRequest", repo: Repository) -> str:
    text = (request.requirement or "").strip()
    if request.mode == "specification":
        if len(text) < 10:
            raise HTTPException(
                status_code=400,
                detail="Describe the feature you are planning (at least a sentence).",
            )
        return text
    # existing_code: fall back to a repo-wide regression sweep.
    if len(text) >= 10:
        return text
    return (
        f"Review the existing code in {repo.full_name} and generate a regression "
        f"test suite for its core modules, covering their main paths and edge cases."
    )


def _owned_chat(session: Session, user: User, chat_id: str) -> Chat:
    chat = session.get(Chat, chat_id)
    if chat is None or chat.user_id != user.id:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return chat


def _serialize_chat(chat: Chat, *, repo: Repository | None = None) -> dict:
    return {
        "id": chat.id,
        "title": chat.title,
        "repository_id": chat.repository_id,
        "repository_full_name": repo.full_name if repo else None,
        "created_at": chat.created_at.isoformat(),
        "updated_at": chat.updated_at.isoformat(),
    }


def _serialize_message(message: Message) -> dict:
    return {
        "id": message.id,
        "role": message.role,
        "content": message.content,
        "kind": message.kind,
        "run_id": message.run_id,
        "created_at": message.created_at.isoformat(),
    }


def _serialize_run(run: PipelineRun) -> dict:
    return {
        "id": run.id,
        "status": run.status,
        "mode": run.mode,
        "story_text": run.story_text,
        "total_tests": run.total_tests,
        "passed": run.passed,
        "failed": run.failed,
        "errors": run.errors,
        "skipped": run.skipped,
        "pass_rate": run.pass_rate,
        "confidence_score": run.confidence_score,
        "duration_seconds": run.duration_seconds,
        "error_message": run.error_message,
        "created_at": run.created_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "story": run.story_result,
        "tests": run.tests_result,
        "execution": run.execution_result,
        "defects": run.defects_result,
        "fixes": run.fixes_result or [],
    }


@router.get("")
async def list_chats(user: User = Depends(current_user), session: Session = Depends(get_session)):
    rows = session.scalars(
        select(Chat).where(Chat.user_id == user.id).order_by(Chat.updated_at.desc()).limit(100)
    )
    chats = list(rows)
    repos = {
        repo.id: repo
        for repo in session.scalars(
            select(Repository).where(Repository.id.in_([c.repository_id for c in chats] or [""]))
        )
    }
    return {"chats": [_serialize_chat(chat, repo=repos.get(chat.repository_id)) for chat in chats]}


@router.post("", status_code=201)
async def create_chat(
    request: CreateChatRequest,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
):
    repo = session.get(Repository, request.repository_id)
    if repo is None or repo.user_id != user.id:
        raise HTTPException(status_code=404, detail="Repository not found.")

    chat = Chat(
        user_id=user.id,
        repository_id=repo.id,
        title=request.title or f"Testing {repo.name}",
    )
    session.add(chat)
    session.commit()
    return _serialize_chat(chat, repo=repo)


@router.get("/{chat_id}")
async def get_chat(
    chat_id: str,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
):
    chat = _owned_chat(session, user, chat_id)
    repo = session.get(Repository, chat.repository_id)
    runs = session.scalars(
        select(PipelineRun).where(PipelineRun.chat_id == chat.id).order_by(PipelineRun.created_at)
    )
    return {
        **_serialize_chat(chat, repo=repo),
        "messages": [_serialize_message(m) for m in chat.messages],
        "runs": [_serialize_run(run) for run in runs],
    }


@router.post("/{chat_id}/messages", status_code=201)
async def post_message(
    chat_id: str,
    request: SendMessageRequest,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
):
    chat = _owned_chat(session, user, chat_id)
    message = Message(chat_id=chat.id, role="user", content=request.content)
    session.add(message)

    # Name the thread from its opening message, like most chat UIs.
    if not chat.messages:
        chat.title = request.content[:TITLE_LENGTH].strip() or chat.title
    chat.updated_at = utcnow()

    session.commit()
    return _serialize_message(message)


@router.post("/{chat_id}/runs", status_code=202)
async def start_run(
    chat_id: str,
    request: StartRunRequest,
    user: User = Depends(current_user),
    token: str = Depends(github_token),
    session: Session = Depends(get_session),
):
    """Launch the pipeline for this chat and return its event-stream id."""
    # Imported here to avoid a circular import at module load: main wires the
    # orchestrator, and main imports this router.
    from agents.orchestrator import RunRequest
    from main import orchestrator, session_manager

    chat = _owned_chat(session, user, chat_id)
    repo = session.get(Repository, chat.repository_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repository is no longer connected.")

    if request.send_email and not (request.recipient_email or "").strip():
        raise HTTPException(status_code=400, detail="recipient_email is required when send_email is enabled.")

    requirement = _resolve_requirement(request, repo)

    session.add(Message(chat_id=chat.id, role="user", content=requirement))
    if len(chat.messages) <= 1:
        chat.title = requirement[:TITLE_LENGTH].strip() or chat.title
    chat.updated_at = utcnow()
    repo.last_run_at = utcnow()
    session.commit()

    stream_id = await session_manager.create_session(user.id)
    asyncio.create_task(
        orchestrator.run_pipeline(
            stream_id,
            RunRequest(
                user_id=user.id,
                story_text=requirement,
                repository_id=repo.id,
                chat_id=chat.id,
                mode=request.mode,
                source="chat",
                send_email=request.send_email,
                recipient_email=request.recipient_email,
                github_token=token,
                repo_full_name=repo.full_name,
                repo_ref=repo.default_branch,
            ),
        )
    )
    return {"session_id": stream_id, "chat_id": chat.id}


@router.get("/{chat_id}/runs/{run_id}")
async def get_run(
    chat_id: str,
    run_id: str,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
):
    _owned_chat(session, user, chat_id)
    run = session.get(PipelineRun, run_id)
    if run is None or run.user_id != user.id or run.chat_id != chat_id:
        raise HTTPException(status_code=404, detail="Run not found.")
    return _serialize_run(run)


@router.delete("/{chat_id}", status_code=204)
async def delete_chat(
    chat_id: str,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
):
    session.delete(_owned_chat(session, user, chat_id))
    session.commit()
