import asyncio
import json
import logging
import os
import uuid
from typing import Dict
from agents.story_agent import analyze_story
from agents.test_agent import generate_tests
from agents.defect_agent import analyze_defects
from models import PipelineDashboard, StoryAnalysis, TestCase, DefectAnalysis

logger = logging.getLogger(__name__)


class SessionManager:
    def __init__(self) -> None:
        self.sessions: Dict[str, asyncio.Queue] = {}
        self.lock = asyncio.Lock()

    async def create_session(self) -> str:
        session_id = uuid.uuid4().hex
        async with self.lock:
            self.sessions[session_id] = asyncio.Queue()
        return session_id

    async def get_queue(self, session_id: str) -> asyncio.Queue | None:
        async with self.lock:
            return self.sessions.get(session_id)

    async def close_session(self, session_id: str) -> None:
        async with self.lock:
            self.sessions.pop(session_id, None)


class Orchestrator:
    def __init__(self, api_key: str, model_id: str, session_manager: SessionManager) -> None:
        self.model_id = model_id
        self.api_key = api_key
        self.sessions = session_manager

    async def run_pipeline(self, session_id: str, user_story: str) -> None:
        queue = await self.sessions.get_queue(session_id)
        if queue is None:
            logger.error("Queue missing for session %s", session_id)
            return

        async def emit(payload: dict) -> None:
            await queue.put(payload)

        try:
            await emit({"event": "agent_start", "agent": "story", "message": "Analyzing user story..."})
            story_result: StoryAnalysis = await analyze_story(self.api_key, self.model_id, user_story)
            await emit({"event": "agent_complete", "agent": "story", "result": story_result.model_dump()})

            await emit({"event": "agent_start", "agent": "test", "message": "Generating test suite..."})
            test_result: list[TestCase] = await generate_tests(self.api_key, self.model_id, story_result)
            await emit({"event": "agent_complete", "agent": "test", "result": [t.model_dump() for t in test_result]})

            await emit({"event": "agent_start", "agent": "defect", "message": "Running risk analysis..."})
            defect_result: DefectAnalysis = await analyze_defects(self.api_key, self.model_id, story_result, test_result)
            await emit({"event": "agent_complete", "agent": "defect", "result": defect_result.model_dump()})

            dashboard = PipelineDashboard(
                story=story_result,
                tests=test_result,
                defects=defect_result,
            )
            await emit({"event": "pipeline_complete", "dashboard": dashboard.model_dump()})
        except Exception as exc:  # noqa: BLE001
            logger.exception("Pipeline error")
            await emit({"event": "error", "message": f"Pipeline failed: {exc}"})
        finally:
            await queue.put(None)
            await asyncio.sleep(4)
            await self.sessions.close_session(session_id)
