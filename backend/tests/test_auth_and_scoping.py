"""Authentication, token handling, and per-user data isolation.

The previous store was global: history was keyed only by story text, so any
visitor's runs fed every other visitor's confidence scores. These tests pin
the boundary.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.models import Base, PipelineRun, User
from history import global_stats, learning_context, module_stats, story_history
from security import create_session_token, decrypt_token, encrypt_token, read_session_token


@pytest.fixture
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        yield db


def make_user(session, login: str, github_id: int) -> User:
    user = User(github_id=github_id, login=login)
    session.add(user)
    session.commit()
    return user


def add_run(session, user, *, story="Checkout should apply discounts", passed=8, failed=2, module="Billing"):
    results = [{"test_id": f"TC-{i:03d}", "status": "pass", "error_message": ""} for i in range(passed)]
    results += [
        {
            "test_id": f"TC-{passed + i:03d}",
            "status": "fail",
            "error_message": f"FAILED t.py::x - {module} assertion drift",
        }
        for i in range(failed)
    ]
    tests = [
        {"id": r["test_id"], "module": module, "type": "functional", "description": f"case {r['test_id']}",
         "expected_result": "holds"}
        for r in results
    ]

    from history import build_story_identity

    key, label = build_story_identity(story_text=story)
    run = PipelineRun(
        user_id=user.id,
        status="complete",
        story_text=story,
        story_key=key,
        story_label=label,
        tests_result=tests,
        execution_result={"results": results, "duration_seconds": 1.0},
        total_tests=len(results),
        passed=passed,
        failed=failed,
        pass_rate=passed / max(1, passed + failed),
        confidence_score=70,
    )
    session.add(run)
    session.commit()
    return run


# -- session tokens --------------------------------------------------------


def test_session_token_roundtrip():
    token = create_session_token("user-123")
    assert read_session_token(token) == "user-123"


def test_tampered_session_token_is_rejected():
    token = create_session_token("user-123")
    forged = token[:-6] + ("aaaaaa" if not token.endswith("aaaaaa") else "bbbbbb")
    assert read_session_token(forged) is None


def test_garbage_token_is_rejected():
    assert read_session_token("not-a-jwt") is None
    assert read_session_token("") is None


# -- GitHub token encryption ----------------------------------------------


def test_github_token_is_encrypted_at_rest():
    raw = "gho_averysecrettokenvalue"
    stored = encrypt_token(raw)

    assert stored != raw
    assert raw not in stored
    assert decrypt_token(stored) == raw


def test_undecryptable_token_reads_as_signed_out():
    """A rotated key must force re-login, not raise on every request."""
    assert decrypt_token("garbage-ciphertext") == ""
    assert decrypt_token(None) == ""
    assert decrypt_token("") == ""


# -- per-user scoping ------------------------------------------------------


def test_story_history_is_scoped_to_its_owner(session):
    alice = make_user(session, "alice", 1)
    bob = make_user(session, "bob", 2)
    story = "Checkout should apply discounts"

    add_run(session, alice, story=story)
    add_run(session, alice, story=story)
    add_run(session, bob, story=story)

    assert story_history(session, user_id=alice.id, story_text=story)["total_runs"] == 2
    assert story_history(session, user_id=bob.id, story_text=story)["total_runs"] == 1


def test_global_stats_never_span_users(session):
    alice = make_user(session, "alice", 1)
    bob = make_user(session, "bob", 2)

    add_run(session, alice, passed=10, failed=0)
    add_run(session, bob, passed=0, failed=10)

    assert global_stats(session, user_id=alice.id)["average_pass_rate"] == 1.0
    assert global_stats(session, user_id=bob.id)["average_pass_rate"] == 0.0


def test_module_stats_never_span_users(session):
    alice = make_user(session, "alice", 1)
    bob = make_user(session, "bob", 2)

    add_run(session, alice, passed=10, failed=0, module="Billing")
    add_run(session, bob, passed=0, failed=10, module="Billing")

    assert module_stats(session, user_id=alice.id, module="Billing")["historical_defect_count"] == 0
    assert module_stats(session, user_id=bob.id, module="Billing")["historical_defect_count"] == 10


def test_learning_context_never_leaks_another_users_failures(session):
    alice = make_user(session, "alice", 1)
    bob = make_user(session, "bob", 2)
    story = "Checkout should apply discounts"

    add_run(session, bob, story=story, passed=0, failed=5)

    alice_context = learning_context(session, user_id=alice.id, story_text=story)
    assert alice_context["total_runs"] == 0
    assert alice_context["recent_failure_signatures"] == []


def test_module_with_no_history_omits_a_defect_probability(session):
    """No runs means no signal; callers supply their own prior instead."""
    alice = make_user(session, "alice", 1)
    stats = module_stats(session, user_id=alice.id, module="Unseen")

    assert stats["has_history"] is False
    assert "defect_probability" not in stats
    assert float(stats.get("defect_probability", 0.25)) == 0.25


def test_incomplete_runs_are_excluded_from_history(session):
    alice = make_user(session, "alice", 1)
    story = "Checkout should apply discounts"
    add_run(session, alice, story=story)

    from history import build_story_identity

    key, label = build_story_identity(story_text=story)
    session.add(
        PipelineRun(user_id=alice.id, status="failed", story_text=story, story_key=key, story_label=label)
    )
    session.commit()

    assert story_history(session, user_id=alice.id, story_text=story)["total_runs"] == 1
