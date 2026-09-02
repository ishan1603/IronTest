"""Failure signatures must distinguish one defect from another.

They are the whole basis of the learning features: recurring-failure detection
and the adaptive regression guards both group runs by signature. A signature
that collapses unrelated failures together makes both meaningless.
"""

import asyncio

import pytest

from agents.execution_agent import execute_tests
from history import failure_signature
from models import TestCase

# pytest truncates its short-summary line to the terminal width. Under a long
# temp path that leaves a stub, which previously became the entire signature.
TRUNCATED_SUMMARY = """\
=================================== FAILURES ===================================
_________________________________ test_broken __________________________________
    def test_broken():
>       assert apply(100, 10) == 50
E       assert 90.0 == 50
E        +  where 90.0 = <function apply>(100, 10)
=========================== short test summary info ============================
FAILED ..\\..\\..\\AppData\\Local\\Temp\\tmp2pl54res\\TC_003.py::test_broken - as...
"""

FULL_SUMMARY = """\
=========================== short test summary info ============================
FAILED test_billing.py::test_discount - assert 90.0 == 50
"""


def test_truncated_summary_line_is_not_used_as_the_signature():
    signature = failure_signature(TRUNCATED_SUMMARY, "fail")

    assert signature != "as"
    assert "90" in signature and "50" in signature


def test_distinct_failures_get_distinct_signatures():
    """The regression this guards: everything collapsing to one value."""
    first = failure_signature(
        TRUNCATED_SUMMARY.replace("assert 90.0 == 50", "assert 90.0 == 50"), "fail"
    )
    second = failure_signature(
        TRUNCATED_SUMMARY.replace("assert 90.0 == 50", "assert 12.5 == 99"), "fail"
    )

    assert first != second


def test_untruncated_summary_line_is_still_used():
    assert failure_signature(FULL_SUMMARY, "fail") == "assert 900  50"


def test_explicit_exception_message_is_preferred():
    message = "E   AssertionError: coupon EXPIRED should be rejected\nFAILED x.py::y - As..."
    assert "coupon expired should be rejected" in failure_signature(message, "fail")


def test_intermediate_value_lines_are_skipped():
    """The "+ where ..." continuations explain values, not the failure."""
    message = "E    +  where 90.0 = apply(100, 10)\nE   assert 90.0 == 50"
    signature = failure_signature(message, "fail")
    assert not signature.startswith("where")


@pytest.mark.parametrize("payload", ["", "   ", None], ids=["empty", "blank", "none"])
def test_missing_message_still_yields_a_signature(payload):
    assert failure_signature(payload, "error") == "error without message"


def test_real_pytest_failure_produces_a_meaningful_signature():
    """End-to-end against genuine pytest output, not a fixture."""
    case = TestCase(
        id="TC-003",
        module="Checkout",
        description="deliberately failing",
        automated=True,
        automation_snippet=[
            "def test_broken():",
            "    def apply(total, pct):",
            "        return total - (total * pct / 100)",
            "    assert apply(100, 10) == 50",
        ],
    )
    summary = asyncio.run(execute_tests([case]))
    signature = failure_signature(summary.results[0].error_message, "fail")

    assert len(signature) >= 8, f"signature too short to distinguish anything: {signature!r}"
    assert "90" in signature and "50" in signature, signature


def test_two_different_real_failures_do_not_collide():
    def case(case_id, expected):
        return TestCase(
            id=case_id,
            module="Checkout",
            description="failing",
            automated=True,
            automation_snippet=[
                f"def test_{case_id.replace('-', '_')}():",
                f"    assert 100 - 10 == {expected}",
            ],
        )

    summary = asyncio.run(execute_tests([case("TC-001", 50), case("TC-002", 77)]))
    signatures = {failure_signature(r.error_message, "fail") for r in summary.results}

    assert len(signatures) == 2, f"distinct failures collided: {signatures}"
