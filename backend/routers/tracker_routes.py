"""Persistent Jira / Azure DevOps connections and issue browsing."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import tracker_client
from auth import current_user
from db import User, get_session
from security import decrypt_token, encrypt_token

router = APIRouter(prefix="/api/integrations", tags=["integrations"])


class JiraConnectRequest(BaseModel):
    base_url: str = Field(..., description="https://your-domain.atlassian.net")
    email: str
    token: str = Field(..., description="Jira API token")


class AdoConnectRequest(BaseModel):
    organization: str = Field(..., description="dev.azure.com/<organization>")
    pat: str = Field(..., description="Personal access token with Work Items (read)")


def _status(user: User) -> dict:
    return {
        "jira": {
            "connected": bool(user.encrypted_jira_token),
            "base_url": user.jira_base_url,
            "email": user.jira_email,
        },
        "ado": {
            "connected": bool(user.encrypted_ado_pat),
            "organization": user.ado_org,
        },
    }


@router.get("")
async def integration_status(user: User = Depends(current_user)):
    return _status(user)


# -- Jira ---------------------------------------------------------------------


@router.post("/jira")
async def connect_jira(
    request: JiraConnectRequest,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
):
    base_url = request.base_url.strip().rstrip("/")
    try:
        await asyncio.to_thread(tracker_client.verify_jira, base_url, request.email.strip(), request.token)
    except tracker_client.TrackerError as exc:
        raise HTTPException(status_code=exc.status_code or 400, detail=str(exc)) from exc

    user.jira_base_url = base_url
    user.jira_email = request.email.strip()
    user.encrypted_jira_token = encrypt_token(request.token)
    session.commit()
    return _status(user)["jira"]


@router.delete("/jira", status_code=204)
async def disconnect_jira(user: User = Depends(current_user), session: Session = Depends(get_session)):
    user.jira_base_url = user.jira_email = user.encrypted_jira_token = None
    session.commit()


@router.get("/jira/issues")
async def jira_issues(user: User = Depends(current_user)):
    token = decrypt_token(user.encrypted_jira_token)
    if not token or not user.jira_base_url:
        raise HTTPException(status_code=409, detail="Jira is not connected.")
    try:
        issues = await asyncio.to_thread(
            tracker_client.list_jira_issues, user.jira_base_url, user.jira_email, token
        )
    except tracker_client.TrackerError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc)) from exc
    return {"issues": issues}


# -- Azure DevOps ----------------------------------------------------------


@router.post("/ado")
async def connect_ado(
    request: AdoConnectRequest,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
):
    org = request.organization.strip().strip("/")
    try:
        await asyncio.to_thread(tracker_client.verify_ado, org, request.pat)
    except tracker_client.TrackerError as exc:
        raise HTTPException(status_code=exc.status_code or 400, detail=str(exc)) from exc

    user.ado_org = org
    user.encrypted_ado_pat = encrypt_token(request.pat)
    session.commit()
    return _status(user)["ado"]


@router.delete("/ado", status_code=204)
async def disconnect_ado(user: User = Depends(current_user), session: Session = Depends(get_session)):
    user.ado_org = user.encrypted_ado_pat = None
    session.commit()


@router.get("/ado/work-items")
async def ado_work_items(user: User = Depends(current_user)):
    pat = decrypt_token(user.encrypted_ado_pat)
    if not pat or not user.ado_org:
        raise HTTPException(status_code=409, detail="Azure DevOps is not connected.")
    try:
        items = await asyncio.to_thread(tracker_client.list_ado_work_items, user.ado_org, pat)
    except tracker_client.TrackerError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc)) from exc
    return {"issues": items}
