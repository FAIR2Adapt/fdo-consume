"""Stage locate: A1, A2."""
from __future__ import annotations

import copy
from dataclasses import replace

from ..core import (PASS, INDETERMINATE, AccessError, Step, has_scheme, refuse_large_crate, shown)
from .. import registry
from .context import Context

NO_PID = ("", "TBD", "?")


def locate(ctx: Context) -> None:
    """A1, A2: is there a PID, and does it resolve to a crate within the size limit?"""
    if not isinstance(ctx.pid, str) or ctx.pid.strip().upper() in NO_PID:
        _not_a_pid(ctx, "no PID given")
        return
    if not has_scheme(ctx.pid):
        _not_a_pid(ctx, "not a PID: no scheme")
        return
    steps = ctx.record.steps
    steps.append(Step("locate", "A1", "pid_known", PASS))

    source = ctx.options.get("source", "recorded")
    locator = _adapter("locator", source, "request.bad_source")
    pinned = ctx.options.get("snapshot")
    if pinned is not None and pinned.pid == ctx.pid:
        located = replace(pinned, crate=copy.deepcopy(pinned.crate), chain=[*pinned.chain, "snapshot reused"])
    else:
        located = locator(ctx.pid, ctx.options, ctx.limits)
    refuse_large_crate(located.size, ctx.limits)
    ctx.located = located
    ctx.record.crate_sha256 = located.crate_sha256
    steps.append(Step("locate", "A2", "pid_resolves", PASS, " -> ".join(located.chain)))


def _not_a_pid(ctx: Context, reason: str) -> None:
    """No usable PID was given: step A1 (pid_known) is INDETERMINATE and resolution stops."""
    ctx.record.steps.append(Step("locate", "A1", "pid_known", INDETERMINATE, reason))
    ctx.record.outcome = "not_resolved"
    ctx.stopped = reason


def _adapter(kind: str, name: str, code: str):
    """The adapter `name` of `kind`; an unknown name is a request error."""
    try:
        return registry.get(kind, name)
    except (KeyError, TypeError):
        known = ", ".join(registry.names(kind))
        raise AccessError(code, f"unknown {kind}: {shown(name)}; known: {known}") from None


