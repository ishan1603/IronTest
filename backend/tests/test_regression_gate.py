"""The regression-gate diff: same suite, two refs."""

from types import SimpleNamespace

from agents.orchestrator import _diff_runs
from models import TestResult
from runners.base import RunnerResult


def _outcome(pairs, status="completed"):
    return RunnerResult(
        backend="stub",
        status=status,
        results=[TestResult(test_id=tid, status=st) for tid, st in pairs],
    )


def test_a_test_that_passed_on_base_and_fails_on_head_is_a_regression():
    base = _outcome([("TC-001", "pass"), ("TC-002", "pass")])
    head = _outcome([("TC-001", "pass"), ("TC-002", "fail")])

    diff = _diff_runs(base_ref="main", head_ref="feature", base=base, head=head)

    assert diff["verdict"] == "regressions_found"
    assert [r["test_id"] for r in diff["regressions"]] == ["TC-002"]
    assert diff["regressions"][0] == {"test_id": "TC-002", "base": "pass", "head": "fail"}
    assert diff["still_passing"] == ["TC-001"]


def test_a_test_that_failed_on_base_and_passes_on_head_is_a_fix_not_a_regression():
    base = _outcome([("TC-001", "fail")])
    head = _outcome([("TC-001", "pass")])

    diff = _diff_runs(base_ref="main", head_ref="feature", base=base, head=head)

    assert diff["regressions"] == []
    assert diff["fixed"][0]["test_id"] == "TC-001"
    assert diff["verdict"] == "clean"


def test_no_change_is_a_clean_verdict():
    base = _outcome([("TC-001", "pass"), ("TC-002", "fail")])
    head = _outcome([("TC-001", "pass"), ("TC-002", "fail")])

    diff = _diff_runs(base_ref="main", head_ref="feature", base=base, head=head)
    assert diff["verdict"] == "clean"
    assert diff["regressions"] == []
    assert diff["still_failing"] == ["TC-002"]


def test_an_unmeasurable_base_is_reported_not_assumed():
    base = _outcome([], status="failed")
    base.error_message = "could not install dependencies"
    head = _outcome([("TC-001", "pass")])

    diff = _diff_runs(base_ref="main", head_ref="feature", base=base, head=head)

    assert diff["base_measured"] is False
    assert diff["verdict"] == "base_unmeasured"
    assert "install" in diff["base_error"]
    assert diff["regressions"] == []


def test_tests_new_on_head_with_no_base_counterpart_are_ignored():
    base = _outcome([("TC-001", "pass")])
    head = _outcome([("TC-001", "pass"), ("TC-002", "fail")])  # TC-002 didn't exist on base

    diff = _diff_runs(base_ref="main", head_ref="feature", base=base, head=head)
    assert diff["regressions"] == []
    assert diff["still_failing"] == []
