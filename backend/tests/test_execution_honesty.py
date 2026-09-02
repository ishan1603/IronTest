"""The execution summary must report what pytest actually did.

An earlier build injected deterministic failures into genuinely passing runs
and then forced the totals into a 7-or-8-out-of-10 band so dashboards looked
plausible. These tests fail if any result shaping returns.
"""

import asyncio

from agents.execution_agent import execute_tests
from models import TestCase


def _case(index: int, body: list[str], *, automated: bool = True, skip_reason: str = "") -> TestCase:
    return TestCase(
        id=f"TC-{index:03d}",
        type="functional",
        module="Billing",
        description=f"case {index}",
        expected_result="holds",
        risk_level="high" if index % 2 else "low",
        automated=automated,
        automation_snippet=body,
        skip_reason=skip_reason,
    )


PASSING = ["def test_ok():", "    assert sum([1, 2, 3]) == 6"]
FAILING = ["def test_bad():", "    assert sum([1, 2, 3]) == 7"]
ERRORING = ["def test_boom():", "    raise RuntimeError('exploded')"]


def _run(cases: list[TestCase]):
    return asyncio.run(execute_tests(cases))


def test_all_passing_suite_reports_all_passing():
    """Ten genuinely passing tests must report ten passes, not a 7-8 band."""
    summary = _run([_case(i, PASSING) for i in range(1, 11)])

    statuses = [r.status for r in summary.results]
    assert statuses == ["pass"] * 10, f"expected 10 passes, got {statuses}"


def test_failing_test_reports_failure():
    summary = _run([_case(1, FAILING)])
    assert [r.status for r in summary.results] == ["fail"]


def test_raising_test_reports_failure_not_error():
    """An uncaught exception is a normal pytest failure (exit code 1)."""
    summary = _run([_case(1, ERRORING)])
    assert [r.status for r in summary.results] == ["fail"]


def test_mixed_suite_preserves_exact_outcomes():
    cases = [_case(1, PASSING), _case(2, FAILING), _case(3, PASSING), _case(4, FAILING)]
    summary = _run(cases)
    assert [r.status for r in summary.results] == ["pass", "fail", "pass", "fail"]


def test_unautomated_case_is_skipped_with_its_reason():
    reason = "Snippet only asserts literals against themselves, so it cannot fail."
    summary = _run([_case(1, [], automated=False, skip_reason=reason)])

    result = summary.results[0]
    assert result.status == "skipped"
    assert result.error_message == reason


def test_results_are_not_reordered_or_dropped():
    cases = [_case(i, PASSING) for i in range(1, 6)]
    summary = _run(cases)
    assert [r.test_id for r in summary.results] == [c.id for c in cases]


def test_identical_input_produces_identical_outcome():
    """No hash-seeded sampling: the same suite must not drift between runs."""
    cases = [_case(i, PASSING) for i in range(1, 9)]
    first = [r.status for r in _run(cases).results]
    second = [r.status for r in _run(cases).results]
    assert first == second == ["pass"] * 8
