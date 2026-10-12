"""Statuses, the four result dimensions, and how a dimension is judged."""
from __future__ import annotations

PASS = "PASS"
PARTIAL = "PARTIAL"
FAIL = "FAIL"
INDETERMINATE = "INDETERMINATE"
STATUSES = (PASS, PARTIAL, FAIL, INDETERMINATE)

SIDES = ("request", "transport", "resolution", "object", "tool")
OUTCOMES = ("ok", "not_resolved", "error")
WANTS = ("reference", "lazy", "native", "binding")
WHO = ("caller", "operator", "producer", "maintainer")
NOT_ATTEMPTED = "NOT_ATTEMPTED"
DIMENSION_STATUSES = STATUSES + (NOT_ATTEMPTED,)
DIMENSIONS = ("resolution", "validation", "compatibility", "delivery")
STAGE_DIMENSION = {
    "locate": "resolution", "describe": "resolution", "normalize": "resolution",
    "interpret": "resolution", "validate": "validation", "match": "compatibility",
    "check": "compatibility", "select": "delivery", "load": "delivery",
}


def judge(statuses: list[str], outcome_ok: bool = True) -> str:
    """One dimension from its steps: FAIL, INDETERMINATE, PARTIAL, PASS; no step is NOT_ATTEMPTED."""
    if FAIL in statuses:
        return FAIL
    if INDETERMINATE in statuses or not outcome_ok:
        return INDETERMINATE
    if PARTIAL in statuses:
        return PARTIAL
    if statuses:
        return PASS
    return NOT_ATTEMPTED
