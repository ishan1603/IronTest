import asyncio
import json
import logging
import os
import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException

load_dotenv()
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from models import AnalyzeRequest, AzureDevOpsIngestRequest, JiraIngestRequest, PipelineDashboard, StoryHistoryRequest
from agents.orchestrator import Orchestrator, SessionManager
from agents.story_agent import analyze_story
from agents.test_agent import generate_tests
from agents.execution_agent import execute_tests
from agents.defect_agent import analyze_defects
from jira_client import fetch_jira_issue
from azure_devops_client import fetch_azure_devops_work_item
from database import get_story_history_by_context
from llm import configured_providers, provider_status

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="IronTest Autonomous QA Agent")

# CORS for demo flexibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if not configured_providers():
    logger.error(
        "No LLM provider configured. Set at least one of GROQ_API_KEY, "
        "GEMINI_API_KEY, CEREBRAS_API_KEY, OPENROUTER_API_KEY."
    )

session_manager = SessionManager()
orchestrator = Orchestrator(session_manager=session_manager)


@app.post("/api/analyze")
async def analyze(request: AnalyzeRequest):
    if not configured_providers():
        raise HTTPException(
            status_code=503,
            detail="No LLM provider is configured on the server.",
        )
    if request.send_email and not (request.recipient_email and request.recipient_email.strip()):
        raise HTTPException(status_code=400, detail="recipient_email is required when send_email is enabled.")

    session_id = await session_manager.create_session()
    asyncio.create_task(
        orchestrator.run_pipeline(
            session_id,
            request.user_story,
            send_email=request.send_email,
            recipient_email=request.recipient_email,
        )
    )
    return {"session_id": session_id}


@app.get("/api/stream/{session_id}")
async def stream(session_id: str):
    queue = await session_manager.get_queue(session_id)
    if queue is None:
        raise HTTPException(status_code=404, detail="Session not found or expired.")

    async def event_generator():
        try:
            while True:
                event = await queue.get()
                if event is None:
                    # Keep socket open so frontend can run es.close() without triggering onerror
                    while True:
                        yield ": keepalive\n\n"
                        await asyncio.sleep(5)
                payload = f"data: {json.dumps(event)}\n\n"
                yield payload
        except asyncio.CancelledError:
            logger.info("Client disconnected from stream %s", session_id)
            raise

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/api/ingest/jira")
async def ingest_jira(request: JiraIngestRequest):
    jira_email = request.email or os.getenv("JIRA_EMAIL")
    jira_token = request.token or os.getenv("JIRA_API_TOKEN")

    if not jira_email or not jira_token:
        raise HTTPException(
            status_code=400,
            detail="Jira credentials missing. Provide email and token in request or set JIRA_EMAIL and JIRA_API_TOKEN in environment.",
        )

    try:
        issue_payload = fetch_jira_issue(
            url=request.url,
            email=jira_email,
            token=jira_token,
            issue_key=request.issue_key,
        )
        return issue_payload
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except requests.HTTPError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Jira ingestion failed")
        raise HTTPException(status_code=500, detail=f"Jira ingestion failed: {exc}") from exc


@app.post("/api/ingest/azure-devops")
async def ingest_azure_devops(request: AzureDevOpsIngestRequest):
    pat = request.pat or os.getenv("AZURE_DEVOPS_PAT") or os.getenv("AZURE_API_TOKEN")
    if not pat:
        raise HTTPException(
            status_code=400,
            detail=(
                "Azure DevOps PAT missing. Provide pat in request or set "
                "AZURE_DEVOPS_PAT (or AZURE_API_TOKEN) in environment."
            ),
        )

    try:
        issue_payload = fetch_azure_devops_work_item(
            url=request.url,
            pat=pat,
            organization=request.organization,
            project=request.project,
            work_item_id=request.work_item_id,
        )
        return issue_payload
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except requests.HTTPError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Azure DevOps ingestion failed")
        raise HTTPException(status_code=500, detail=f"Azure DevOps ingestion failed: {exc}") from exc


@app.post("/api/webhook/github")
async def github_webhook(payload: dict):
    # Simulates a DevOps integration endpoint (e.g. GitHub Action webhook triggering QA run)
    if not configured_providers():
        raise HTTPException(status_code=503, detail="No LLM provider is configured on the server.")
    
    # We do a quick synchronous run for the CI/CD pipeline
    try:
        story_text = payload.get("commit_message", "Automated commit deployment validation. Check stability.")
        story = await analyze_story(story_text)
        tests = await generate_tests(story, story_text=story_text)
        execution = await execute_tests(tests)
        defects = await analyze_defects(story, tests, execution)
        
        # Save history just like orchestrator
        from database import save_execution
        save_execution(
            story.modules,
            execution,
            tests=tests,
            story_text=story_text,
            story_intent=story.intent,
            source="github_webhook",
            confidence_score=defects.overall_confidence_score,
        )

        return {
            "status": "success",
            "confidence_score": defects.overall_confidence_score,
            "deployment_recommendation": defects.deployment_recommendation,
            "dashboard": PipelineDashboard(story=story, tests=tests, execution=execution, defects=defects).model_dump()
        }
    except Exception as e:
        logger.exception("Webhook pipeline failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/history/story")
async def story_history(request: StoryHistoryRequest):
    try:
        payload = get_story_history_by_context(
            story_text=request.story_text,
            story_intent=request.story_intent,
            modules=request.modules,
            limit=request.limit,
        )
        return payload
    except Exception as exc:  # noqa: BLE001
        logger.exception("Story history lookup failed")
        raise HTTPException(status_code=500, detail=f"Story history lookup failed: {exc}") from exc


@app.get("/health")
async def health():
    providers = provider_status()
    return {
        "status": "ok" if any(p["active"] for p in providers) else "degraded",
        "llm_providers": providers,
    }


# Serve built frontend if placed under /frontend/dist (optional for docker-compose)
frontend_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(frontend_dist):
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
