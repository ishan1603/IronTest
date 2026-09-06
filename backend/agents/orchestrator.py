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

import repo_analysis
from agents.defect_agent import analyze_defects
from agents.execution_agent import execute_tests
from agents.fix_agent import suggest_fixes
from agents.repo_test_agent import generate_repo_tests
from agents.story_agent import analyze_story
from agents.suite_builder import build_suite
from agents.test_agent import generate_tests
from db import PipelineRun, Repository, session_scope, utcnow
from email_notifier import send_execution_summary_email
from history import build_story_identity, global_stats, learning_context, module_stats
from models import DefectAnalysis, FixSuggestion, PipelineDashboard, StoryAnalysis, TestCase, TestExecutionSummary
from runners import SANDBOXED_BACKENDS, RunnerRequest, RunnerUnavailable, select_runner

logger = logging.getLogger(__name__)

#: Grace period after a run ends before the SSE queue is discarded, so a
#: client that reconnects briefly still receives the terminal event.
SESSION_LINGER_SECONDS = 30


def _diff_runs(*, base_ref: str, head_ref: str, base, head) -> dict[str, Any]:
    """Compare the same suite across two refs.

    A test that passed on base and fails on head is a regression; the reverse
    is a fix. Anything the base run could not measure is reported as such
    rather than assumed.
    """
    def _by_id(outcome) -> dict[str, str]:
        if outcome.status != "completed":
            return {}
        return {r.test_id: r.status for r in outcome.results}

    base_map = _by_id(base)
    head_map = _by_id(head)

    regressions, fixed, still_failing, still_passing = [], [], [], []
    for test_id, head_status in head_map.items():
        base_status = base_map.get(test_id)
        head_ok = head_status == "pass"
        base_ok = base_status == "pass"
        if base_status is None:
            continue
        if base_ok and not head_ok:
            regressions.append({"test_id": test_id, "base": base_status, "head": head_status})
        elif not base_ok and head_ok:
            fixed.append({"test_id": test_id, "base": base_status, "head": head_status})
        elif not base_ok and not head_ok:
            still_failing.append(test_id)
        else:
            still_passing.append(test_id)

    return {
        "base_ref": base_ref,
        "head_ref": head_ref,
        "base_measured": base.status == "completed",
        "base_error": "" if base.status == "completed" else (base.error_message or "base run produced no results"),
        "regressions": regressions,
        "fixed": fixed,
        "still_failing": still_failing,
        "still_passing": still_passing,
        "verdict": "regressions_found" if regressions else ("clean" if base.status == "completed" else "base_unmeasured"),
    }



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
    #: Present for repository runs; enables cloning and sandboxed execution.
    github_token: str = ""
    repo_full_name: str = ""
    repo_ref: str = ""
    #: When set, run the same generated suite against this base ref too and
    #: diff the outcomes -- the regression gate.
    compare_ref: str = ""
    #: {full_name, pr_number} -> post a summary comment when the run completes.
    pr_comment: dict[str, Any] | None = None

    @property
    def is_repository_run(self) -> bool:
        return bool(self.repository_id and self.repo_full_name and self.github_token)


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

            learning = await asyncio.to_thread(
                self._learning_for, request.user_id, request.story_text, story
            )

            if request.is_repository_run:
                tests, execution, repo_context, comparison = await self._run_against_repository(
                    emit, request, story, learning
                )
            else:
                tests, execution, repo_context, comparison = await self._run_standalone(
                    emit, request, story, learning
                )

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

            fixes: list[FixSuggestion] = []
            if any(r.status in {"fail", "error"} for r in execution.results) and repo_context:
                await emit({"event": "agent_start", "agent": "fix", "message": "Drafting fix suggestions..."})
                fixes = await suggest_fixes(story, tests, execution, repo_context)
                await emit(
                    {"event": "agent_complete", "agent": "fix", "result": [f.model_dump() for f in fixes]}
                )

            suite_files = (repo_context or {}).get("_suite_files")
            await asyncio.to_thread(
                self._complete_run, run_id, story, tests, execution, defects, fixes, comparison, suite_files
            )

            if request.send_email and request.recipient_email:
                await self._notify(emit, request, story, execution, defects, session_id)

            if request.pr_comment:
                await asyncio.to_thread(self._post_pr_comment, request, run_id)

            dashboard = PipelineDashboard(
                story=story, tests=tests, execution=execution, defects=defects, fixes=fixes
            )
            await emit({"event": "pipeline_complete", "run_id": run_id, "dashboard": dashboard.model_dump()})

        except Exception as exc:  # noqa: BLE001
            logger.exception("Pipeline failed for run %s", run_id)
            await asyncio.to_thread(self._fail_run, run_id, str(exc))
            await emit({"event": "error", "run_id": run_id, "message": str(exc)})
        finally:
            await queue.put(None)
            await asyncio.sleep(SESSION_LINGER_SECONDS)
            await self.sessions.close_session(session_id)

    # -- generation and execution -----------------------------------------

    async def _run_standalone(
        self, emit, request: RunRequest, story: StoryAnalysis, learning: dict[str, Any]
    ) -> tuple[list[TestCase], TestExecutionSummary, dict[str, Any] | None, dict[str, Any] | None]:
        """No repository: run self-contained snippets on this host.

        Snippets here import nothing, so they validate the behavior described
        by the requirement rather than any real code.
        """
        await emit({"event": "agent_start", "agent": "test", "message": "Generating test suite..."})
        tests = await generate_tests(story, story_text=request.story_text, learning=learning)
        await emit(
            {"event": "agent_complete", "agent": "test", "result": [t.model_dump() for t in tests]}
        )

        await emit({"event": "agent_start", "agent": "execution", "message": "Executing tests..."})
        execution = await execute_tests(tests)
        await emit(
            {
                "event": "agent_complete",
                "agent": "execution",
                "backend": "local",
                "scope": "standalone",
                "result": execution.model_dump(),
            }
        )
        return tests, execution, None, None

    async def _run_against_repository(
        self, emit, request: RunRequest, story: StoryAnalysis, learning: dict[str, Any]
    ) -> tuple[list[TestCase], TestExecutionSummary, dict[str, Any], dict[str, Any] | None]:
        """Generate tests that import the repository's code, then run them in a sandbox."""
        runner = select_runner()
        if runner is None:
            raise RunnerUnavailable(
                "No test runner is available. For local development, run the API with "
                "ENVIRONMENT=development (the default) and make sure git is on PATH -- tests "
                "then run in a subprocess on this machine. For a sandboxed run, install Docker, "
                "or set ACTIONS_RUNNER_REPO and ACTIONS_DISPATCH_TOKEN to use GitHub Actions."
            )

        sandboxed = runner.name in SANDBOXED_BACKENDS
        if not sandboxed:
            await emit(
                {
                    "event": "runner_notice",
                    "backend": runner.name,
                    "message": (
                        "Running on this machine rather than in a sandbox. Fine for local "
                        "development; a deployed install uses Docker or GitHub Actions."
                    ),
                }
            )

        await emit(
            {"event": "agent_start", "agent": "test", "message": f"Reading {request.repo_full_name}..."}
        )
        repo_context = await repo_analysis.build_code_context(
            request.github_token,
            request.repo_full_name,
            request.repo_ref,
            request.story_text,
        )
        await emit(
            {
                "event": "repo_context",
                "stack": repo_context.get("stack", {}),
                "files_examined": [f["path"] for f in repo_context.get("files", [])],
                "existing_tests": repo_context.get("existing_tests", []),
            }
        )

        tests, imports = await generate_repo_tests(
            story,
            repo_context,
            requirement=request.story_text,
            mode=request.mode,
            learning=learning,
        )
        await emit(
            {
                "event": "agent_complete",
                "agent": "test",
                "result": [t.model_dump() for t in tests],
                "imports": imports,
            }
        )

        stack = repo_context.get("stack", {})
        files = build_suite(
            tests,
            imports,
            language=stack.get("language", "python"),
            module_system=stack.get("module_system", "cjs"),
        )
        if not files:
            raise ValueError("No runnable tests were generated for this repository.")
        repo_context["_suite_files"] = [{"path": f.path, "content": f.content} for f in files]

        await emit(
            {
                "event": "agent_start",
                "agent": "execution",
                "message": f"Running tests in {runner.name} sandbox...",
                "backend": runner.name,
            }
        )
        outcome = await runner.run(
            RunnerRequest(
                repo_full_name=request.repo_full_name,
                ref=request.repo_ref,
                github_token=request.github_token,
                stack=stack,
                files=files,
                mode=request.mode,
            )
        )

        if outcome.status != "completed":
            # No parseable results: surface the failure *with* the runner's own
            # output, so the error is actionable rather than just "no report".
            await emit(
                {
                    "event": "agent_complete",
                    "agent": "execution",
                    "backend": outcome.backend,
                    "sandboxed": sandboxed,
                    "scope": "repository",
                    "status": "failed",
                    "message": outcome.error_message,
                    "logs": outcome.raw_output[-6000:],
                }
            )
            tail = "\n".join(outcome.raw_output.strip().splitlines()[-25:])
            detail = outcome.error_message or "The test run produced no results."
            raise RuntimeError(f"{detail}\n\n--- runner output (tail) ---\n{tail}" if tail else detail)

        execution = TestExecutionSummary(
            results=outcome.results, duration_seconds=outcome.duration_seconds
        )
        await emit(
            {
                "event": "agent_complete",
                "agent": "execution",
                "backend": outcome.backend,
                "sandboxed": sandboxed,
                "scope": "repository",
                "mode": request.mode,
                "result": execution.model_dump(),
                "logs": outcome.raw_output[-4000:],
            }
        )

        if request.compare_ref and request.compare_ref != request.repo_ref:
            await emit(
                {
                    "event": "agent_start",
                    "agent": "compare",
                    "message": f"Running the same suite against {request.compare_ref}...",
                }
            )
            base = await runner.run(
                RunnerRequest(
                    repo_full_name=request.repo_full_name,
                    ref=request.compare_ref,
                    github_token=request.github_token,
                    stack=stack,
                    files=files,
                    mode=request.mode,
                )
            )
            comparison = _diff_runs(
                base_ref=request.compare_ref,
                head_ref=request.repo_ref,
                base=base,
                head=outcome,
            )
            await emit({"event": "agent_complete", "agent": "compare", "result": comparison})
        else:
            comparison = None

        return tests, execution, repo_context, comparison

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
        fixes: list[FixSuggestion] | None = None,
        comparison: dict[str, Any] | None = None,
        suite_files: list[dict] | None = None,
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
            run.fixes_result = [f.model_dump() for f in (fixes or [])]
            run.compare_result = comparison
            run.suite_files = suite_files
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
    def _post_pr_comment(request: "RunRequest", run_id: str) -> None:
        """Post the run's verdict back on the pull request that triggered it."""
        import asyncio as _asyncio
        import secrets

        import github_client
        from db import PipelineRun as _Run

        try:
            with session_scope() as session:
                run = session.get(_Run, run_id)
                if run is None or run.status != "complete":
                    return
                if not run.share_token:
                    run.share_token = secrets.token_urlsafe(24)
                token_link = run.share_token
                executed = run.passed + run.failed + run.errors
                pct = round((run.passed / executed) * 100) if executed else 0
                verdict = (run.defects_result or {}).get("deployment_recommendation", "?")
                compare = run.compare_result or {}
                regressions = len(compare.get("regressions", []))

            frontend = get_settings().frontend_url.rstrip("/")
            lines = [
                "### IronTest",
                "",
                f"**{verdict}** — {run.passed}/{executed} passed ({pct}%)"
                + (f", confidence {run.confidence_score}/100" if run.confidence_score is not None else ""),
            ]
            if compare:
                lines.append("")
                lines.append(
                    f"Regression gate ({compare.get('base_ref')} → {compare.get('head_ref')}): "
                    + (f"**{regressions} regression(s)**" if regressions else "no regressions")
                )
            lines.append("")
            lines.append(f"[Full report]({frontend}/r/{token_link})")

            _asyncio.run(
                github_client.comment_on_issue(
                    request.github_token,
                    request.pr_comment["full_name"],
                    int(request.pr_comment["pr_number"]),
                    "\n".join(lines),
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not post PR comment for run %s: %s", run_id, exc)

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
