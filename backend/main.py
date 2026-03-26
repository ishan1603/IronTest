import asyncio
import json
import logging
import os
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException

load_dotenv()
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from models import AnalyzeRequest, JiraIngestRequest, PipelineDashboard
from agents.orchestrator import Orchestrator, SessionManager
from agents.story_agent import analyze_story
from agents.test_agent import generate_tests
from agents.execution_agent import execute_tests
from agents.defect_agent import analyze_defects

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

API_KEY = os.getenv("GROQ_API_KEY")
MODEL_ID = os.getenv("GROQ_MODEL_ID", "llama-3.1-8b-instant")
if not API_KEY:
    logger.error("GROQ_API_KEY is not set. API calls will fail.")

session_manager = SessionManager()
orchestrator: Orchestrator | None = None

if API_KEY:
    orchestrator = Orchestrator(api_key=API_KEY, model_id=MODEL_ID, session_manager=session_manager)


@app.post("/api/analyze")
async def analyze(request: AnalyzeRequest):
    if not API_KEY:
        raise HTTPException(status_code=500, detail="Missing GROQ_API_KEY environment variable.")

    session_id = await session_manager.create_session()
    assert orchestrator is not None
    asyncio.create_task(orchestrator.run_pipeline(session_id, request.user_story))
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
    # For hackathon purposes, we simulate Jira ticket extraction.
    # In production, this would use the Jira REST API with the provided URL and Token.
    ticket_id = request.url.split("/")[-1] if "/" in request.url else "PROJ-123"
    
    simulated_story = f"As a user of '{ticket_id}', I need the system to validate inputs correctly so that invalid data is rejected. Acceptance Criteria: - Fields cannot be blank - Email must contain @ symbol - Passwords require 8+ characters and special symbol."
    
    return {"user_story": simulated_story}


@app.post("/api/webhook/github")
async def github_webhook(payload: dict):
    # Simulates a DevOps integration endpoint (e.g. GitHub Action webhook triggering QA run)
    if not API_KEY:
        raise HTTPException(status_code=500, detail="Missing GROQ_API_KEY")
    
    # We do a quick synchronous run for the CI/CD pipeline
    try:
        story_text = payload.get("commit_message", "Automated commit deployment validation. Check stability.")
        story = await analyze_story(API_KEY, MODEL_ID, story_text)
        tests = await generate_tests(API_KEY, MODEL_ID, story)
        execution = await execute_tests(tests)
        defects = await analyze_defects(API_KEY, MODEL_ID, story, tests, execution)
        
        # Save history just like orchestrator
        from database import save_execution
        save_execution(story.modules, execution)

        return {
            "status": "success",
            "confidence_score": defects.overall_confidence_score,
            "deployment_recommendation": defects.deployment_recommendation,
            "dashboard": PipelineDashboard(story=story, tests=tests, execution=execution, defects=defects).model_dump()
        }
    except Exception as e:
        logger.exception("Webhook pipeline failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health():
    return {"status": "ok"}


# Serve built frontend if placed under /frontend/dist (optional for docker-compose)
frontend_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(frontend_dist):
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
