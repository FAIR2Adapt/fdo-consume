"""The failure catalogue and the error that ends a chain."""
from __future__ import annotations

from .status import INDETERMINATE

BLOCKING_STEPS = ("A2b",)
SOURCE_RAISED = ("transport.timeout", "transport.connection", "transport.http_error", "resolution.gone")

FAILURES = {
    "request.bad_pid": {"retryable": False, "who": "caller"},
    "request.bad_depth": {"retryable": False, "who": "caller"},
    "request.bad_source": {"retryable": False, "who": "caller"},
    "request.bad_contract": {"retryable": False, "who": "caller"},
    "request.bad_option": {"retryable": False, "who": "caller"},
    "request.bad_fixtures": {"retryable": False, "who": "caller"},
    "transport.timeout": {"retryable": True, "who": "operator"},
    "transport.connection": {"retryable": True, "who": "operator"},
    "transport.http_error": {"retryable": True, "who": "operator"},
    "resolution.not_recorded": {"retryable": False, "who": "producer"},
    "resolution.gone": {"retryable": False, "who": "producer"},
    "object.too_large": {"retryable": False, "who": "producer"},
    "object.not_json": {"retryable": False, "who": "producer"},
    "object.no_graph": {"retryable": False, "who": "producer"},
    "object.no_root": {"retryable": False, "who": "producer"},
    "object.ambiguous_root": {"retryable": False, "who": "producer"},
    "object.no_describer": {"retryable": False, "who": "producer"},
    "tool.bad_step": {"retryable": False, "who": "maintainer"},
    "tool.unexpected": {"retryable": False, "who": "maintainer"},
}
NOT_CATALOGUED = {"retryable": False, "who": "maintainer"}


class AccessError(Exception):
    """Error raised when a pipeline stage cannot continue; the catalogue says who can act."""

    def __init__(self, code: str, message: str):
        """Take side, retryable and who from the code."""
        super().__init__(message)
        known = FAILURES.get(code, NOT_CATALOGUED)
        self.code = code
        self.message = message
        self.side = code.split(".")[0]
        self.retryable = known["retryable"]
        self.who = known["who"]

    def to_dict(self) -> dict:
        """The error as plain data, for a record."""
        return {
            "code": self.code,
            "side": self.side,
            "message": self.message,
            "retryable": self.retryable,
            "who": self.who,
        }


def step_diagnostic(step: object) -> dict:
    """Convert a non-passing step to a structured diagnostic."""
    return {
        "stage": step.stage,
        "id": step.id,
        "code": f"{step.id}.{step.name}",
        "side": "object",
        "status": step.status,
        "blocking": step.id in BLOCKING_STEPS,
        "retryable": False,
        "who": "producer",
        "detail": step.detail,
    }


def error_diagnostic(error: AccessError, stage: str | None, step_id: str | None) -> dict:
    """The error that ended the chain as a diagnostic."""
    return {
        "stage": stage,
        "id": step_id,
        "code": error.code,
        "side": error.side,
        "status": INDETERMINATE,
        "blocking": True,
        "retryable": error.retryable,
        "who": error.who,
        "detail": error.message,
    }
