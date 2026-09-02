"""Drives the four-agent pipeline and persists the result.

The orchestrator is the only component here that touches the database. Agents
receive already-computed history so they hold no session and cannot read
another user's runs by accident.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from agents.defect_agent import analyze_defects
from agents.execution_agent import execute_tests
from agents.story_agent import analyze_story
from agents.test_agent import generate_tests
from db import PipelineRun, session_scope, utcnow
from email_notifier import send_execution_summary_email
from history import build_story_identity, global_stats, learning_context, module_stats
from models import DefectAnalysis, PipelineDashboard, StoryAnalysis, TestCase, TestExecutionSummary

logger = logging.getLogger(__name__)

#: Grace period after a run ends before the SSE queue is discarded, so a
#: client that reconnects briefly still receives the terminal event.
SESSION_LINGER_SECONDS = 30


@dataclass
class RunRequest:
    """Everything a pipeline run needs, resolved before it starts."""

    user_id: str
    story_text: str
    repository_id: str | None = None
    chat_id: str | None = None
    #: "existing_code" tests shipped behaviour; "specification" tests behaviour
    #: that does not exist yet, where failures are the expected red phase.
    mode: str = "existing_code"
    source: str = "chat"
    send_email: bool = False
    recipient_email: str | None = None
    repo_context: dict[str, Any] = field(default_factory=dict)


class SessionManager:
    """In-memory fan-out for Server-Sent Events, keyed by session id.

    Sessions record their owner so a stream cannot be read by another account
    that guesses or is handed a session id.
    """

    def __init__(self) -> None:
        self.sessions: dict[str, asyncio.Queue] = {}
        self.owners: dict[str, str] = {}
        self.lock = asyncio.Lock()

    async def create_session(self, user_id: str) -> str:
        session_id = uuid.uuid4().hex
        async with self.lock:
            self.sessions[session_id] = asyncio.Queue()
            self.owners[session_id] = user_id
        return session_id

    async def get_queue(self, session_id: str, *, user_id: str | None = None) -> asyncio.Queue | None:
        async with self.lock:
            if user_id is not None and self.owners.get(session_id) != user_id:
                return None
            return self.sessions.get(session_id)

    async def close_session(self, session_id: str) -> None:
        async with self.lock:
            self.sessions.pop(session_id, None)
            self.owners.pop(session_id, None)


class Orchestrator:
    def __init__(self, session_manager: SessionManager) -> None:
        self.sessions = session_manager

    async def run_pipeline(self, session_id: str, request: RunRequest) -> None:
        queue = await self.sessions.get_queue(session_id)
        if queue is None:
            logger.error("Queue missing for session %s", session_id)
            return

        async def emit(payload: dict) -> None:
            await queue.put(payload)

        story_key, story_label = build_story_identity(story_text=request.story_text)
        run_id = await asyncio.to_thread(self._create_run, request, story_key, story_label)
        await emit({"event": "run_created", "run_id": run_id, "mode": request.mode})

        try:
            await emit({"event": "agent_start", "agent": "story", "message": "Analyzing the requirement..."})
            story: StoryAnalysis = await analyze_story(request.story_text)
            await emit({"event": "agent_complete", "agent": "story", "result": story.model_dump()})

            await emit({"event": "agent_start", "agent": "test", "message": "Generating test suite..."})
            learning = await asyncio.to_thread(
                self._learning_for, request.user_id, request.story_text, story
            )
            tests: list[TestCase] = await generate_tests(
                story, story_text=request.story_text, learning=learning
            )
            await emit(
                {
                    "event": "agent_complete",
                    "agent": "test",
                    "result": [test.model_dump() for test in tests],
                }
            )

            await emit({"event": "agent_start", "agent": "execution", "message": "Executing tests..."})
            execution: TestExecutionSummary = await execute_tests(tests)
            await emit({"event": "agent_complete", "agent": "execution", "result": execution.model_dump()})

            await emit({"event": "agent_start", "agent": "defect", "message": "Assessing release risk..."})
            module_history, overall = await asyncio.to_thread(
                self._history_for, request.user_id, story.modules
            )
            defects: DefectAnalysis = await analyze_defects(
                story,
                tests,
                execution,
                module_history=module_history,
                global_history=overall,
            )
            await emit({"event": "agent_complete", "agent": "defect", "result": defects.model_dump()})

            await asyncio.to_thread(self._complete_run, run_id, story, tests, execution, defects)

            if request.send_email and request.recipient_email:
                await self._notify(emit, request, story, execution, defects, session_id)

            dashboard = PipelineDashboard(story=story, tests=tests, execution=execution, defects=defects)
            await emit({"event": "pipeline_complete", "run_id": run_id, "dashboard": dashboard.model_dump()})

        except Exception as exc:  # noqa: BLE001
            logger.exception("Pipeline failed for run %s", run_id)
            await asyncio.to_thread(self._fail_run, run_id, str(exc))
            await emit({"event": "error", "run_id": run_id, "message": str(exc)})
        finally:
            await queue.put(None)
            await asyncio.sleep(SESSION_LINGER_SECONDS)
            await self.sessions.close_session(session_id)

    # -- database work, all run off the event loop -------------------------

    @staticmethod
    def _create_run(request: RunRequest, story_key: str, story_label: str) -> str:
        with session_scope() as session:
            run = PipelineRun(
                user_id=request.user_id,
                repository_id=request.repository_id,
                chat_id=request.chat_id,
                status="running",
                mode=request.mode,
                source=request.source,
                story_text=request.story_text,
                story_key=story_key,
                story_label=story_label,
            )
            session.add(run)
            session.flush()
            return run.id

    @staticmethod
    def _learning_for(user_id: str, story_text: str, story: StoryAnalysis) -> dict[str, Any]:
        with session_scope() as session:
            return learning_context(
                session,
                user_id=user_id,
                story_text=story_text,
                story_intent=story.intent,
                modules=story.modules,
            )

    @staticmethod
    def _history_for(user_id: str, modules: list[str]) -> tuple[dict[str, dict], dict]:
        with session_scope() as session:
            per_module = {
                module: module_stats(session, user_id=user_id, module=module) for module in modules
            }
            return per_module, global_stats(session, user_id=user_id)

    @staticmethod
    def _complete_run(
        run_id: str,
        story: StoryAnalysis,
        tests: list[TestCase],
        execution: TestExecutionSummary,
        defects: DefectAnalysis,
    ) -> None:
        counts = {status: 0 for status in ("pass", "fail", "error", "skipped")}
        for result in execution.results:
            counts[result.status] = counts.get(result.status, 0) + 1
        executed = counts["pass"] + counts["fail"] + counts["error"]

        with session_scope() as session:
            run = session.get(PipelineRun, run_id)
            if run is None:
                return
            run.status = "complete"
            run.story_result = story.model_dump()
            run.tests_result = [test.model_dump() for test in tests]
            run.execution_result = execution.model_dump()
            run.defects_result = defects.model_dump()
            run.total_tests = len(execution.results)
            run.passed = counts["pass"]
            run.failed = counts["fail"]
            run.errors = counts["error"]
            run.skipped = counts["skipped"]
            # Skipped cases are excluded from the rate: they never ran, so
            # counting them as failures would misreport a suite with gaps.
            run.pass_rate = round(counts["pass"] / executed, 4) if executed else 0.0
            run.confidence_score = defects.overall_confidence_score
            run.duration_seconds = execution.duration_seconds
            run.finished_at = utcnow()

    @staticmethod
    def _fail_run(run_id: str, message: str) -> None:
        with session_scope() as session:
            run = session.get(PipelineRun, run_id)
            if run is None:
                return
            run.status = "failed"
            run.error_message = message[:2000]
            run.finished_at = utcnow()

    @staticmethod
    async def _notify(emit, request, story, execution, defects, session_id) -> None:
        await emit(
            {
                "event": "notification",
                "channel": "email",
                "status": "processing",
                "message": f"Sending summary to {request.recipient_email}...",
            }
        )
        delivered, message = await asyncio.to_thread(
            send_execution_summary_email,
            recipient_email=request.recipient_email,
            user_story=request.story_text,
            story=story,
            execution=execution,
            defects=defects,
            session_id=session_id,
        )
        await emit(
            {
                "event": "notification",
                "channel": "email",
                "status": "sent" if delivered else "failed",
                "message": message,
            }
        )
