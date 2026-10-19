"""access(): one PID through the stages, as far as `depth`."""
from __future__ import annotations

import hashlib
import json
import sys
import time
from collections.abc import Mapping
from datetime import datetime, timezone

from .. import registry
from .._version import __version__
from ..contracts import load_contract
from ..loaders.binding import refresh_evidence
from ..core import (
    FAIL, PARTIAL, STATUSES, INDETERMINATE, WANTS,
    AccessError, AccessRecord, Limits, Step,
    clip, error_diagnostic, plain, record_hash, set_dimensions, shown, step_diagnostic,
)
from .. import pipeline
from . import ALIASES
from .context import Context

PLAIN_FIELDS = (
    "request", "error", "reached", "stopped", "diagnostics", "semantics", "descriptor", "selected", "loaded",
    "crate_sha256", "contract_id",
)
SELECTORS = ("open-first",)
PACKAGE_VERSION = __version__
_LOG_FAULTS: set[str] = set()


def access(pid: str, contract: str | Mapping | None = None, depth: str = "match",
           source: str = "recorded", want: str = "reference", limits: Limits | None = None,
           log: str | None = None, **options: object) -> AccessRecord:
    """Run the stages for one PID as far as `depth`; return the sealed record."""
    if isinstance(pid, str):
        pid = pid.strip()
    asked = {"contract": contract, "depth": depth, "source": source, "want": want}
    request = {"pid": pid_as_asked(pid)}
    for key, value in asked.items():
        request[key] = plain(value)
    if isinstance(depth, str) and depth in ALIASES:
        request["depth_alias"] = f"{depth} -> {ALIASES[depth]}"
        depth = ALIASES[depth]
    record = AccessRecord(request=request, started=_utc_now(), package_version=PACKAGE_VERSION)
    options = dict(options, source=source, want=want)
    ctx = Context(pid, options, limits or Limits(), None, record)
    clock = time.perf_counter()
    ended = None
    try:
        _run(ctx, contract, depth)
    except AccessError as err:
        ended = err
    except Exception as err:
        ended = AccessError("tool.unexpected", clip(f"{type(err).__name__}: {err}"))
    _seal(ctx, ended, clock)
    _log(record, log)
    return record


def pid_as_asked(pid: object) -> str:
    """The PID for the record: a string as it is, anything else as its repr."""
    if isinstance(pid, str):
        return pid
    try:
        return clip(repr(pid))
    except Exception:
        return f"<{type(pid).__name__}>"


def _run(ctx: Context, contract: object, depth: str) -> None:
    """Check the request, then run the stages until `depth` or a stop."""
    order = pipeline.STAGES
    _check_request(ctx, contract, depth, [name for name, _ in order])
    for name, stage in order:
        ctx.record.reached = name
        stage(ctx)
        dropped = _drop_bad_steps(ctx.record)
        if dropped:
            raise AccessError("tool.bad_step", f"not a step with one of {STATUSES}: {dropped[0]}")
        if ctx.stopped is not None or name == depth:
            return


def _check_request(ctx: Context, contract: object, depth: str, depths: list[str]) -> None:
    """Refuse a bad request before any object is touched."""
    source = ctx.options["source"]
    want = ctx.options["want"]
    if not isinstance(ctx.pid, str):
        raise AccessError("request.bad_pid", f"a PID is a string, not {type(ctx.pid).__name__}")
    if depth not in depths:
        raise AccessError("request.bad_depth", f"unknown depth: {shown(depth)}")
    if source not in registry.names("locator"):
        raise AccessError("request.bad_source", f"unknown source: {shown(source)}")
    if contract is not None:
        ctx.spec = load_contract(contract, ctx.options.get("contracts"), ctx.options.get("profile_maps"))
        ctx.record.contract_id = plain(ctx.spec.get("contract_id"))
        # Hash the content so a change at the same contract id is detectable.
        ctx.record.contract_sha256 = hashlib.sha256(bytes(json.dumps(plain(ctx.spec), sort_keys=True, ensure_ascii=False), "utf-8")).hexdigest()
        _check_adapters_named(ctx.spec)
    if want not in WANTS:
        raise AccessError("request.bad_option", f"unknown want: {shown(want)}; one of {WANTS}")


def _check_adapters_named(spec: Mapping) -> None:
    """Refuse a contract that names an unregistered check or an unknown selector."""
    for name in spec.get("checks", []):
        if name not in registry.names("check"):
            raise AccessError("request.bad_contract", f"unknown check: {shown(name)}")
    name = spec.get("selector", "open-first")
    if name not in SELECTORS:
        raise AccessError("request.bad_contract", f"unknown selector: {shown(name)}")


def _drop_bad_steps(record: AccessRecord) -> list[str]:
    """Take out of the record what is not a Step with one of the four statuses."""
    good = []
    dropped = []
    for step in record.steps:
        if isinstance(step, Step) and isinstance(step.status, str) and step.status in STATUSES:
            good.append(step)
        else:
            dropped.append(clip(plain(getattr(step, "__dict__", step))))
    record.steps[:] = good
    return dropped


def _seal(ctx: Context, ended: AccessError | None, clock: float) -> None:
    """Set outcome, stopped, diagnostics, dimensions, duration and hash."""
    record = ctx.record
    record.diagnostics = []
    _drop_bad_steps(record)
    if ended is not None:
        _end_with(ctx, ended)
    record.stopped = ctx.stopped
    reported = {(d["stage"], d["id"]) for d in record.diagnostics}
    for step in record.steps:
        if step.status in (FAIL, PARTIAL, INDETERMINATE) and (step.stage, step.id) not in reported:
            record.diagnostics.append(step_diagnostic(step))
    set_dimensions(record)
    if isinstance(record.value, dict) and record.value.get("schema", "").startswith("fdo-consume-binding/"):
        refresh_evidence(record.value, record)
    elapsed = time.perf_counter() - clock
    record.duration_ms = int(elapsed * 1000)
    record.duration_us = int(elapsed * 1_000_000)
    try:
        record.record_sha256 = record_hash(record.to_dict())
    except (TypeError, ValueError, RecursionError):
        _make_plain(record)
        record.record_sha256 = record_hash(record.to_dict())


def _end_with(ctx: Context, err: AccessError) -> None:
    """An error ended the chain: its side and the running stage say what it becomes."""
    record = ctx.record
    stage = record.reached
    reason = f"{err.code}: {err.message}"
    ctx.stopped = reason
    if err.side == "resolution" and stage == "locate":
        record.steps.append(Step("locate", "A2", "pid_resolves", INDETERMINATE, reason))
        record.outcome = "not_resolved"
        record.diagnostics.append(error_diagnostic(err, stage, "A2"))
        return
    if err.side == "object" and stage in ("locate", "describe"):
        record.steps.append(Step(stage, "A2b", "crate_parses", FAIL, reason))
        return
    record.outcome = "error"
    record.error = dict(err.to_dict(), stage=stage)
    record.diagnostics.append(error_diagnostic(err, stage, None))



def _make_plain(record: AccessRecord) -> None:
    """Replace what JSON cannot carry, in the steps and the fields, by plain data."""
    for step in record.steps:
        for key, value in list(step.__dict__.items()):
            setattr(step, key, plain(value))
    for name in PLAIN_FIELDS:
        setattr(record, name, plain(getattr(record, name)))


def _log(record: AccessRecord, log: object) -> None:
    """Append the record as one JSON line to `log`; a fault never touches the record."""
    if log is None:
        return
    try:
        line = json.dumps(record.to_dict(), separators=(",", ":"), ensure_ascii=False, default=repr)
        with open(str(log), "a", encoding="utf-8") as out:
            out.write(line + "\n")
    except Exception as err:
        _say_once(str(log), err)


def _say_once(path: str, err: Exception) -> None:
    """Report a sink fault on stderr, once per log path."""
    if path in _LOG_FAULTS:
        return
    _LOG_FAULTS.add(path)
    print(f"fdo_consume: log not written to {path}: {type(err).__name__}: {err}", file=sys.stderr)


def _utc_now() -> str:
    """The time now, ISO 8601, UTC, to the second."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
