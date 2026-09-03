"""Analytics aggregation, scoped per user."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import analytics
from db.models import Base, PipelineRun, Repository, User
from history import build_story_identity


@pytest.fixture
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as db:
        yield db


def _user(session, login, gid):
    u = User(github_id=gid, login=login)
    session.add(u)
    session.commit()
    return u


def _run(session, user, *, story, catalog, passed, failed, conf=70, status="complete"):
    key, label = build_story_identity(story_text=story)
    results = [{"test_id": c["id"], "status": c["result_status"], "error_message": ""} for c in catalog]
    run = PipelineRun(
        user_id=user.id,
        status=status,
        story_text=story,
        story_key=key,
        story_label=label,
        tests_result=[
            {"id": c["id"], "module": c["module"], "type": "functional",
             "description": c["description"], "expected_result": "x"}
            for c in catalog
        ],
        execution_result={"results": results, "duration_seconds": 1.0},
        total_tests=len(catalog),
        passed=passed,
        failed=failed,
        pass_rate=passed / max(1, passed + failed),
        confidence_score=conf,
    )
    session.add(run)
    session.commit()
    return run


def test_overview_is_empty_without_runs(session):
    alice = _user(session, "alice", 1)
    data = analytics.analytics_overview(session, user_id=alice.id)
    assert data["totals"]["runs"] == 0
    assert data["trend"] == []


def test_totals_and_trend_reflect_only_this_users_runs(session):
    alice = _user(session, "alice", 1)
    bob = _user(session, "bob", 2)

    cat_pass = [{"id": "TC-001", "module": "Billing", "description": "d1", "result_status": "pass"}]
    _run(session, alice, story="s", catalog=cat_pass, passed=1, failed=0, conf=90)
    _run(session, alice, story="s", catalog=cat_pass, passed=1, failed=0, conf=80)
    _run(session, bob, story="s", catalog=cat_pass, passed=1, failed=0, conf=10)

    data = analytics.analytics_overview(session, user_id=alice.id)
    assert data["totals"]["runs"] == 2
    assert data["totals"]["avg_confidence"] == 85.0
    assert len(data["trend"]) == 2
    # oldest first
    assert data["trend"][0]["confidence"] == 90


def test_flaky_detection_needs_a_pass_and_a_fail_across_enough_runs(session):
    alice = _user(session, "alice", 1)
    story = "checkout discount"

    def cat(status):
        return [{"id": "TC-001", "module": "Billing", "description": "applies discount", "result_status": status}]

    _run(session, alice, story=story, catalog=cat("pass"), passed=1, failed=0)
    _run(session, alice, story=story, catalog=cat("fail"), passed=0, failed=1)
    _run(session, alice, story=story, catalog=cat("pass"), passed=1, failed=0)

    flaky = analytics.analytics_overview(session, user_id=alice.id)["flaky_tests"]
    assert len(flaky) == 1
    assert flaky[0]["description"] == "applies discount"
    assert flaky[0]["passed"] == 2 and flaky[0]["failed"] == 1


def test_consistently_passing_test_is_not_flaky(session):
    alice = _user(session, "alice", 1)
    for _ in range(4):
        _run(
            session, alice, story="s",
            catalog=[{"id": "TC-001", "module": "M", "description": "stable", "result_status": "pass"}],
            passed=1, failed=0,
        )
    assert analytics.analytics_overview(session, user_id=alice.id)["flaky_tests"] == []


def test_worst_modules_ranks_by_failure_rate(session):
    alice = _user(session, "alice", 1)
    _run(
        session, alice, story="s",
        catalog=[
            {"id": "TC-001", "module": "Billing", "description": "a", "result_status": "fail"},
            {"id": "TC-002", "module": "Billing", "description": "b", "result_status": "fail"},
            {"id": "TC-003", "module": "Auth", "description": "c", "result_status": "pass"},
        ],
        passed=1, failed=2,
    )
    worst = analytics.analytics_overview(session, user_id=alice.id)["worst_modules"]
    assert worst[0]["module"] == "Billing"
    assert worst[0]["fail_rate"] == 1.0


def test_run_list_is_scoped_and_ordered_newest_first(session):
    alice = _user(session, "alice", 1)
    bob = _user(session, "bob", 2)
    cat = [{"id": "TC-001", "module": "M", "description": "d", "result_status": "pass"}]
    _run(session, alice, story="first", catalog=cat, passed=1, failed=0)
    _run(session, alice, story="second", catalog=cat, passed=1, failed=0)
    _run(session, bob, story="theirs", catalog=cat, passed=1, failed=0)

    rows = analytics.run_list(session, user_id=alice.id)
    assert len(rows) == 2
    assert rows[0]["story_label"] == "second"
