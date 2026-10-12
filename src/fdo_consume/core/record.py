"""The record every access ends in: steps, four result dimensions, hash."""
from __future__ import annotations

from dataclasses import dataclass, field

from .status import DIMENSIONS, NOT_ATTEMPTED, STAGE_DIMENSION, INDETERMINATE, judge
from .util import sha256_of

SCHEMA = "fdo-consume-record/4"
UNHASHED = ("started", "duration_ms", "duration_us", "record_sha256")


@dataclass
class Step:
    """One piece of evidence added by a stage."""

    stage: str
    id: str
    name: str
    status: str
    detail: str = ""
    notes: list = field(default_factory=list)   # structured, e.g. {"code": "profile.term_undefined", "terms": [...]}


def empty_dimension() -> dict:
    """An empty dimension, status NOT_ATTEMPTED."""
    return {"status": NOT_ATTEMPTED, "evidence": [], "diagnostics": []}


@dataclass
class AccessRecord:
    """Structured record of one consumption attempt."""

    schema: str = SCHEMA
    request: dict = field(default_factory=dict)
    outcome: str = "ok"
    error: dict | None = None
    resolution: dict = field(default_factory=empty_dimension)
    validation: dict = field(default_factory=empty_dimension)
    compatibility: dict = field(default_factory=empty_dimension)
    delivery: dict = field(default_factory=empty_dimension)
    reached: str | None = None
    stopped: str | None = None
    steps: list[Step] = field(default_factory=list)
    diagnostics: list[dict] = field(default_factory=list)
    semantics: dict | None = None
    descriptor: dict | None = None
    selected: dict | None = None
    loaded: dict | None = None
    crate_sha256: str | None = None
    contract_id: str | None = None
    contract_sha256: str | None = None
    package_version: str = ""
    record_sha256: str = ""
    started: str = ""
    duration_ms: int = 0
    duration_us: int = 0
    value: object = field(default=None, repr=False)

    def to_dict(self) -> dict:
        """The record as plain data: no live value, no deep copy."""
        return {
            "schema": self.schema,
            "request": self.request,
            "outcome": self.outcome,
            "error": self.error,
            "resolution": self.resolution,
            "validation": self.validation,
            "compatibility": self.compatibility,
            "delivery": self.delivery,
            "reached": self.reached,
            "stopped": self.stopped,
            "steps": [dict(step.__dict__) for step in self.steps],
            "diagnostics": self.diagnostics,
            "semantics": self.semantics,
            "descriptor": self.descriptor,
            "selected": self.selected,
            "loaded": self.loaded,
            "crate_sha256": self.crate_sha256,
            "contract_id": self.contract_id,
            "contract_sha256": self.contract_sha256,
            "package_version": self.package_version,
            "record_sha256": self.record_sha256,
            "started": self.started,
            "duration_ms": self.duration_ms,
            "duration_us": self.duration_us,
        }


def set_dimensions(record: AccessRecord) -> None:
    """Judge the four dimensions from the steps, the diagnostics and the outcome."""
    for name in DIMENSIONS:
        steps = [s for s in record.steps if STAGE_DIMENSION.get(s.stage, "resolution") == name]
        codes = [d["code"] for d in record.diagnostics
                 if STAGE_DIMENSION.get(d.get("stage"), "resolution") == name]
        ok = name != "resolution" or record.outcome == "ok"
        status = judge([s.status for s in steps], ok)
        if name != "resolution" and not steps:
            status = NOT_ATTEMPTED
        found = {"status": status, "evidence": [s.id for s in steps], "diagnostics": codes}
        if name == "validation":
            ran = any(s.id.startswith("V1") for s in steps)
            found["validator"] = {"ran": ran, "reason": None if ran else "no authoritative profile validator is configured"}
            if status == "PASS" and not ran:
                found["status"] = INDETERMINATE
                found["note"] = "terms are present; no profile validator ran, so conformance is not established"
        setattr(record, name, found)


def exit_code(records: list[dict], no_members: bool = False) -> int:
    """2 bad request; 1 not resolved, error or no members; 3 a dimension is FAIL; else 0."""
    for record in records:
        if record["error"] and record["error"]["side"] == "request":
            return 2
    for record in records:
        if record["outcome"] != "ok":
            return 1
    if no_members:
        return 1
    for record in records:
        if any(record[name]["status"] == "FAIL" for name in DIMENSIONS):
            return 3
    return 0


def record_hash(record: dict) -> str:
    """Hash of a record dict without its time fields and itself."""
    kept = {key: value for key, value in record.items() if key not in UNHASHED}
    return sha256_of(kept)
