"""Cross-run analytics and the flat run history."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

import analytics
from auth import current_user
from db import PipelineRun, User, get_session

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("")
async def overview(user: User = Depends(current_user), session: Session = Depends(get_session)):
    return analytics.analytics_overview(session, user_id=user.id)


@router.get("/runs")
async def runs(
    limit: int = Query(default=100, ge=1, le=300),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
):
    return {"runs": analytics.run_list(session, user_id=user.id, limit=limit)}


@router.get("/runs/{run_id}")
async def run_detail(
    run_id: str,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
):
    run = session.get(PipelineRun, run_id)
    if run is None or run.user_id != user.id:
        raise HTTPException(status_code=404, detail="Run not found.")
    return {
        "id": run.id,
        "chat_id": run.chat_id,
        "status": run.status,
        "mode": run.mode,
        "story_text": run.story_text,
        "created_at": run.created_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "error_message": run.error_message,
        "story": run.story_result,
        "tests": run.tests_result,
        "execution": run.execution_result,
        "defects": run.defects_result,
        "fixes": run.fixes_result or [],
        "passed": run.passed,
        "failed": run.failed,
        "errors": run.errors,
        "skipped": run.skipped,
        "pass_rate": run.pass_rate,
        "confidence_score": run.confidence_score,
        "duration_seconds": run.duration_seconds,
    }
