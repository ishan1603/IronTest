"""End-to-end pipeline run with the model stubbed.

Exercises the orchestrator for real -- event sequence, agent hand-off, and the
persisted row -- with only the network boundary replaced. The pipeline is the
component most likely to break silently when agents change shape, and it had no
coverage.
"""

import asyncio
import itertools

import pytest

import agents.defect_agent as defect_agent
import agents.story_agent as story_agent
import agents.fix_agent as fix_agent
import agents.test_agent as test_agent
from agents.orchestrator import Orchestrator, RunRequest, SessionManager
from db import PipelineRun, Repository, User, session_scope
from db.base import engine
from db.models import Base

REQUIREMENT = "Users should be able to apply a percentage discount code at checkout."

STORY_RESPONSE = {
    "intent": "Allow shoppers to apply a percentage discount code during checkout.",
    "modules": ["Checkout", "Pricing"],
    "acceptance_criteria": [
        "A valid code reduces the total by its percentage",
        "An expired code is rejected",
    ],
    "risk_factors": ["Rounding errors on the discounted total"],
    "security_vectors": ["Discount code brute forcing"],
    "microservices": ["pricing-service"],
}

# Two genuinely passing snippets and one genuinely failing one.
TESTS_RESPONSE = {
    "test_cases": [
        {
            "id": "TC-001",
            "type": "functional",
            "module": "Pricing",
            "description": "Applies a ten percent discount",
            "expected_result": "Total drops to 90",
            "risk_level": "medium",
            "automation_snippet": [
                "def test_discount():",
                "    def apply(total, pct):",
                "        return total - (total * pct / 100)",
                "    assert apply(100, 10) == 90",
            ],
        },
        {
            "id": "TC-002",
            "type": "boundary",
            "module": "Pricing",
            "description": "Zero percent leaves the total unchanged",
            "expected_result": "Total unchanged",
            "risk_level": "low",
            "automation_snippet": [
                "def test_zero():",
                "    def apply(total, pct):",
                "        return total - (total * pct / 100)",
                "    assert apply(100, 0) == 100",
            ],
        },
        {
            "id": "TC-003",
            "type": "edge_case",
            "module": "Checkout",
            "description": "Deliberately failing case",
            "expected_result": "Total drops to 50",
            "risk_level": "high",
            "automation_snippet": [
                "def test_broken():",
                "    def apply(total, pct):",
                "        return total - (total * pct / 100)",
                "    assert apply(100, 10) == 50",
            ],
        },
    ]
}

FIXES_RESPONSE = {
    "fixes": [
        {
            "test_id": "TC-003",
            "target_file": "app/pricing.py",
            "explanation": "The discount helper divides before applying the cap.",
            "suggested_change": "- return total * pct\n+ return round(total * pct, 2)",
            "confidence": "medium",
        }
    ]
}

DEFECTS_RESPONSE = {
    "module_risks": [],
    "overall_confidence_score": 72,
    "deployment_recommendation": "CONDITIONAL GO",
    "recommendation_rationale": "One checkout case fails.",
    "critical_test_ids": ["TC-003"],
}


@pytest.fixture(autouse=True)
def stub_model(monkeypatch):
    """Replace the provider call in each agent; nothing else is mocked."""

    def fake(*, system_prompt, user_prompt, **_kwargs):
        if "Story Intelligence Agent" in system_prompt:
            return STORY_RESPONSE
        if "Test Generation Agent" in system_prompt:
            return TESTS_RESPONSE
        if "Fix Suggestion Agent" in system_prompt:
            return FIXES_RESPONSE
        return DEFECTS_RESPONSE

    monkeypatch.setattr(story_agent, "generate_json", fake)
    monkeypatch.setattr(test_agent, "generate_json", fake)
    monkeypatch.setattr(defect_agent, "generate_json", fake)
    monkeypatch.setattr(fix_agent, "generate_json", fake)


# Each test gets a fresh account: runs accumulate history, and a later run of
# the same story legitimately gains an adaptive guard from the earlier one.
_ACCOUNT_SEQUENCE = itertools.count(77001)


@pytest.fixture
def user():
    Base.metadata.create_all(engine)
    with session_scope() as session:
        row = User(github_id=next(_ACCOUNT_SEQUENCE), login="pipeline-tester")
        session.add(row)
        session.flush()
        return row.id


@pytest.fixture
def repository(user):
    with session_scope() as session:
        repo = Repository(
            user_id=user,
            github_repo_id=next(_ACCOUNT_SEQUENCE),
            full_name="acme/app",
            name="app",
            owner="acme",
            default_branch="main",
        )
        session.add(repo)
        session.flush()
        return repo.id


def run_pipeline(user_id, **overrides):
    """Drive one run to completion and return the events it emitted."""

    async def drive():
        manager = SessionManager()
        orchestrator = Orchestrator(session_manager=manager)
        session_id = await manager.create_session(user_id)

        # Hold the queue directly: run_pipeline discards the session in its
        # finally block, so it cannot be looked up afterwards.
        queue = await manager.get_queue(session_id)

        # Skip the post-run linger, which only exists for reconnecting clients.
        import agents.orchestrator as module

        original = module.SESSION_LINGER_SECONDS
        module.SESSION_LINGER_SECONDS = 0
        try:
            await orchestrator.run_pipeline(
                session_id,
                RunRequest(user_id=user_id, story_text=REQUIREMENT, source="test", **overrides),
            )
        finally:
            module.SESSION_LINGER_SECONDS = original

        collected = []
        while not queue.empty():
            item = queue.get_nowait()
            if item is None:
                break
            collected.append(item)
        return collected

    return asyncio.run(drive())


def test_pipeline_emits_every_stage_in_order(user):
    events = run_pipeline(user)
    starts = [e["agent"] for e in events if e["event"] == "agent_start"]
    completes = [e["agent"] for e in events if e["event"] == "agent_complete"]

    assert starts == ["story", "test", "execution", "defect"]
    assert completes == ["story", "test", "execution", "defect"]
    assert events[-1]["event"] == "pipeline_complete"


def test_pipeline_reports_the_real_mix_of_outcomes(user):
    """Two passing snippets and one failing one must report exactly that."""
    events = run_pipeline(user)
    execution = next(
        e for e in events if e["event"] == "agent_complete" and e["agent"] == "execution"
    )["result"]

    statuses = {r["test_id"]: r["status"] for r in execution["results"]}
    assert statuses == {"TC-001": "pass", "TC-002": "pass", "TC-003": "fail"}


def test_completed_run_is_persisted_with_real_counts(user):
    events = run_pipeline(user)
    run_id = next(e for e in events if e["event"] == "run_created")["run_id"]

    with session_scope() as session:
        run = session.get(PipelineRun, run_id)

        assert run.status == "complete"
        assert (run.passed, run.failed, run.errors) == (2, 1, 0)
        assert run.pass_rate == pytest.approx(2 / 3, abs=0.001)
        assert run.confidence_score is not None
        assert run.finished_at is not None
        assert run.story_result["intent"] == STORY_RESPONSE["intent"]
        assert len(run.tests_result) == 3


class _StubRunner:
    name = "docker"  # pretend to be sandboxed

    async def run(self, request):
        from models import TestResult
        from runners.base import RunnerResult

        return RunnerResult(
            backend="docker",
            status="completed",
            results=[
                TestResult(test_id="TC-001", status="pass"),
                TestResult(test_id="TC-002", status="pass"),
                TestResult(test_id="TC-003", status="fail", error_message="assert 90 == 50"),
            ],
            duration_seconds=1.0,
        )


def test_fix_suggestions_are_produced_for_failures_on_a_repo_run(user, repository, monkeypatch):
    import agents.orchestrator as orch

    monkeypatch.setattr(orch, "select_runner", lambda: _StubRunner())

    async def fake_context(*_a, **_k):
        return {
            "repository": "acme/app",
            "stack": {"language": "python", "test_framework": "pytest"},
            "files": [{"path": "app/pricing.py", "symbols": [], "excerpt": "def apply(total, pct): return total * pct"}],
            "existing_tests": [],
        }

    monkeypatch.setattr(orch.repo_analysis, "build_code_context", fake_context)
    monkeypatch.setattr(
        orch, "generate_repo_tests",
        lambda *a, **k: __import__("asyncio").sleep(0, result=([__import__("models").TestCase(
            id="TC-003", module="Pricing", description="fails", automated=True,
            automation_snippet=["def test_x():", "    assert 1 == 2"])], [])),
    )

    events = run_pipeline(
        user,
        repository_id=repository,
        repo_full_name="acme/app",
        repo_ref="main",
        github_token="gho_test",
    )

    err = next((e for e in events if e["event"] == "error"), None)
    assert err is None, err

    fix_complete = next(
        (e for e in events if e["event"] == "agent_complete" and e["agent"] == "fix"), None
    )
    assert fix_complete is not None
    assert fix_complete["result"][0]["test_id"] == "TC-003"


def test_dashboard_payload_is_complete(user):
    events = run_pipeline(user)
    dashboard = events[-1]["dashboard"]

    assert set(dashboard) == {"story", "tests", "execution", "defects", "fixes"}
    assert dashboard["defects"]["deployment_recommendation"] in {"GO", "CONDITIONAL GO", "NO-GO"}


def test_a_failing_agent_marks_the_run_failed_and_reports_it(user, monkeypatch):
    """A model failure must never leave a half-finished run looking complete."""

    def explode(**_kwargs):
        raise RuntimeError("provider exhausted")

    monkeypatch.setattr(story_agent, "generate_json", explode)

    events = run_pipeline(user)
    error = next(e for e in events if e["event"] == "error")
    assert "provider exhausted" in error["message"]

    with session_scope() as session:
        run = session.get(PipelineRun, error["run_id"])
        assert run.status == "failed"
        assert "provider exhausted" in run.error_message
        assert run.passed == 0


def test_repository_run_without_a_sandbox_fails_loudly(user, repository, monkeypatch):
    """It must never fall back to local execution that cannot import the repo."""
    import agents.orchestrator as module

    monkeypatch.setattr(module, "select_runner", lambda: None)

    events = run_pipeline(
        user,
        repository_id=repository,
        repo_full_name="acme/app",
        repo_ref="main",
        github_token="gho_test",
    )

    error = next(e for e in events if e["event"] == "error")
    assert "No test runner is available" in error["message"]

    # No results were fabricated to fill the gap.
    assert not any(e.get("agent") == "execution" and e["event"] == "agent_complete" for e in events)


def test_second_run_of_the_same_story_sees_the_first_as_history(user):
    """Runs group by story identity, which is what makes trends meaningful."""
    from history import story_history

    run_pipeline(user)
    run_pipeline(user)

    with session_scope() as session:
        history = story_history(session, user_id=user, story_text=REQUIREMENT)
        assert history["total_runs"] >= 2
        assert all(entry["pass_rate"] == pytest.approx(2 / 3, abs=0.001) for entry in history["runs"])
