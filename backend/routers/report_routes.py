"""Sharing a run and viewing / exporting a shared report (public)."""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

import reports
from auth import current_user
from db import PipelineRun, User, get_session

# Two routers: one authed (manage sharing), one public (view the report).
manage = APIRouter(prefix="/api/analytics/runs", tags=["reports"])
public = APIRouter(prefix="/api/reports", tags=["reports"])


def _owned_run(session: Session, user: User, run_id: str) -> PipelineRun:
    run = session.get(PipelineRun, run_id)
    if run is None or run.user_id != user.id:
        raise HTTPException(status_code=404, detail="Run not found.")
    return run


@manage.post("/{run_id}/share")
async def share_run(
    run_id: str,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
):
    run = _owned_run(session, user, run_id)
    if run.status != "complete":
        raise HTTPException(status_code=400, detail="Only a completed run can be shared.")
    if not run.share_token:
        run.share_token = secrets.token_urlsafe(24)
        session.commit()
    return {"token": run.share_token}


@manage.delete("/{run_id}/share", status_code=204)
async def unshare_run(
    run_id: str,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
):
    run = _owned_run(session, user, run_id)
    run.share_token = None
    session.commit()


def _run_by_token(session: Session, token: str) -> PipelineRun:
    run = session.scalar(select(PipelineRun).where(PipelineRun.share_token == token))
    if run is None:
        raise HTTPException(status_code=404, detail="This report link is invalid or was revoked.")
    return run


@public.get("/{token}")
async def view_report(token: str, session: Session = Depends(get_session)):
    return reports.public_view(_run_by_token(session, token))


@public.get("/{token}/export.md", response_class=PlainTextResponse)
async def export_markdown(token: str, session: Session = Depends(get_session)):
    run = _run_by_token(session, token)
    return PlainTextResponse(
        reports.to_markdown(run),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="irontest-{run.id[:8]}.md"'},
    )
