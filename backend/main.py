"""IronTest API."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

import requests
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from agents.orchestrator import Orchestrator, RunRequest, SessionManager
from auth import current_user
from azure_devops_client import fetch_azure_devops_work_item
from config import get_settings
from db import User, get_session, init_db
from github_client import GitHubError
from history import story_history
from jira_client import fetch_jira_issue
from llm import LLMError, configured_providers, provider_status
from runners import runner_status
from models import AnalyzeRequest, AzureDevOpsIngestRequest, JiraIngestRequest, StoryHistoryRequest
from routers import auth_routes, chat_routes, repo_routes
from security import read_session_token

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    if not configured_providers():
        logger.error(
            "No LLM provider configured. Set at least one of GROQ_API_KEY, "
            "GEMINI_API_KEY, CEREBRAS_API_KEY, OPENROUTER_API_KEY."
        )
    if not settings.github_oauth_configured:
        logger.warning("GitHub OAuth is not configured; sign-in will be unavailable.")
    yield


app = FastAPI(title="IronTest", version="2.0.0", lifespan=lifespan)

# Credentialed requests cannot use a wildcard origin. The previous
# allow_origins=["*"] with allow_credentials=True is rejected by browsers, and
# would have exposed the API to every site if it were honoured.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

session_manager = SessionManager()
orchestrator = Orchestrator(session_manager=session_manager)

app.include_router(auth_routes.router)
app.include_router(repo_routes.router)
app.include_router(chat_routes.router)


@app.exception_handler(GitHubError)
async def _github_error_handler(_request: Request, exc: GitHubError):
    return JSONResponse(status_code=exc.status_code or 502, content={"detail": str(exc)})


@app.exception_handler(LLMError)
async def _llm_error_handler(_request: Request, exc: LLMError):
    return JSONResponse(
        status_code=503,
        content={
            "detail": "All configured AI providers are unavailable or rate limited.",
            "diagnostics": str(exc),
        },
    )


def _require_llm() -> None:
    if not configured_providers():
        raise HTTPException(status_code=503, detail="No AI provider is configured on the server.")


@app.post("/api/analyze")
async def analyze(request: AnalyzeRequest, user: User = Depends(current_user)):
    """Start a pipeline run and return the id of its event stream."""
    _require_llm()
    if request.send_email and not (request.recipient_email or "").strip():
        raise HTTPException(
            status_code=400,
            detail="recipient_email is required when send_email is enabled.",
        )

    session_id = await session_manager.create_session(user.id)
    asyncio.create_task(
        orchestrator.run_pipeline(
            session_id,
            RunRequest(
                user_id=user.id,
                story_text=request.user_story,
                mode=request.mode,
                source="api",
                send_email=request.send_email,
                recipient_email=request.recipient_email,
            ),
        )
    )
    return {"session_id": session_id}


@app.get("/api/stream/{session_id}")
async def stream(session_id: str, token: str = Query(...)):
    """Server-Sent Events for a run.

    EventSource cannot set an Authorization header, so the session token
    arrives as a query parameter and is checked against the session's owner.
    """
    user_id = read_session_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired session token.")

    queue = await session_manager.get_queue(session_id, user_id=user_id)
    if queue is None:
        raise HTTPException(status_code=404, detail="Session not found or expired.")

    async def event_generator():
        try:
            while True:
                event = await queue.get()
                if event is None:
                    # Hold the socket open so the client closes it deliberately,
                    # rather than EventSource treating EOF as an error.
                    while True:
                        yield ": keepalive\n\n"
                        await asyncio.sleep(15)
                yield f"data: {json.dumps(event)}\n\n"
        except asyncio.CancelledError:
            logger.info("Client disconnected from stream %s", session_id)
            raise

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/history/story")
async def story_history_endpoint(
    request: StoryHistoryRequest,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
):
    return story_history(
        session,
        user_id=user.id,
        story_text=request.story_text,
        story_intent=request.story_intent,
        modules=request.modules,
        limit=request.limit,
    )


@app.post("/api/ingest/jira")
async def ingest_jira(request: JiraIngestRequest, _user: User = Depends(current_user)):
    jira_email = request.email or os.getenv("JIRA_EMAIL")
    jira_token = request.token or os.getenv("JIRA_API_TOKEN")

    if not jira_email or not jira_token:
        raise HTTPException(
            status_code=400,
            detail="Jira credentials missing. Provide email and token, or set JIRA_EMAIL and JIRA_API_TOKEN.",
        )

    try:
        return fetch_jira_issue(
            url=request.url,
            email=jira_email,
            token=jira_token,
            issue_key=request.issue_key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except requests.HTTPError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/ingest/azure-devops")
async def ingest_azure_devops(request: AzureDevOpsIngestRequest, _user: User = Depends(current_user)):
    pat = request.pat or os.getenv("AZURE_DEVOPS_PAT")
    if not pat:
        raise HTTPException(
            status_code=400,
            detail="Azure DevOps PAT missing. Provide pat, or set AZURE_DEVOPS_PAT.",
        )

    try:
        return fetch_azure_devops_work_item(
            url=request.url,
            pat=pat,
            organization=request.organization,
            project=request.project,
            work_item_id=request.work_item_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except requests.HTTPError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/health")
async def health():
    providers = provider_status()
    return {
        "status": "ok" if any(p["active"] for p in providers) else "degraded",
        "version": app.version,
        "llm_providers": providers,
        "test_runner": runner_status(),
        "github_oauth": settings.github_oauth_configured,
    }


# Serve the built frontend when it is bundled alongside the API.
frontend_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(frontend_dist):
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
