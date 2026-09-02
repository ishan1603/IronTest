"""Guards against the class of generated test that cannot fail.

The pipeline previously substituted every model-authored snippet with a
template that asserted a dict literal against itself, so the suite reported
passes without exercising anything. These tests keep that shape out.
"""

import pytest

from agents.test_agent import _normalize_test_items, _snippet_rejection_reason

# Verbatim shapes emitted by the removed _fallback_snippet templates.
TAUTOLOGICAL_FUNCTIONAL = [
    "def test_tc_001_coreservice():",
    "    payload = {'module': 'CoreService', 'action': 'primary_path', 'input_id': 'A123'}",
    "    response = {'status': 'success', 'module': 'CoreService', 'decision': 'accepted'}",
    "    assert response['status'] == 'success'",
    "    assert response['module'] == payload['module']",
    "    assert response['decision'] == 'accepted'",
]

TAUTOLOGICAL_EDGE = [
    "def test_tc_002_coreservice():",
    "    payload = {'module': 'CoreService', 'id': '', 'enabled': True}",
    "    response = {'status': 'error', 'error_code': 'VALIDATION_ERROR', 'message': 'id is required'}",
    "    assert response['status'] == 'error'",
    "    assert response['error_code'] == 'VALIDATION_ERROR'",
]

MEANINGFUL = [
    "def test_discount_boundary():",
    "    def discount(total):",
    "        return total * 0.9 if total >= 100 else total",
    "    assert discount(100) == 90",
    "    assert discount(99) == 99",
]


@pytest.mark.parametrize(
    "snippet",
    [TAUTOLOGICAL_FUNCTIONAL, TAUTOLOGICAL_EDGE],
    ids=["functional_template", "edge_case_template"],
)
def test_rejects_self_asserting_snippets(snippet):
    reason = _snippet_rejection_reason(snippet)
    assert reason is not None
    assert "cannot fail" in reason


def test_accepts_snippet_that_computes_a_result():
    assert _snippet_rejection_reason(MEANINGFUL) is None


@pytest.mark.parametrize(
    "snippet,fragment",
    [
        (["def test_x():", "    import requests", "    assert requests.get('http://x').ok"], "sandbox"),
        (["assert 1 == 1"], "no test_* function"),
        (["def test_x(:", "    pass"], "not valid Python"),
        ([], "no automation snippet"),
    ],
    ids=["network_access", "uncollectable", "syntax_error", "empty"],
)
def test_rejects_unusable_snippets(snippet, fragment):
    reason = _snippet_rejection_reason(snippet)
    assert reason is not None
    assert fragment.lower() in reason.lower()


def test_rejected_snippet_is_marked_unautomated_not_replaced():
    """A bad snippet must surface as skipped-with-reason, never as a substitute."""
    items = _normalize_test_items(
        [
            {
                "id": "TC-001",
                "type": "functional",
                "module": "Billing",
                "description": "Reject invalid coupon",
                "expected_result": "Coupon is rejected",
                "automation_snippet": TAUTOLOGICAL_FUNCTIONAL,
            }
        ],
        ["Billing"],
    )

    assert len(items) == 1
    item = items[0]
    assert item["automated"] is False
    assert item["automation_snippet"] == []
    assert "cannot fail" in item["skip_reason"]


def test_valid_snippet_survives_normalization_unchanged():
    items = _normalize_test_items(
        [
            {
                "id": "TC-002",
                "type": "boundary",
                "module": "Pricing",
                "description": "Discount applies at threshold",
                "expected_result": "10% off at 100",
                "automation_snippet": MEANINGFUL,
            }
        ],
        ["Pricing"],
    )

    item = items[0]
    assert item["automated"] is True
    assert item["automation_snippet"] == MEANINGFUL
    assert item["skip_reason"] == ""
