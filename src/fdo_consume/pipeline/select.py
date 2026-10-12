"""Stage select: A5, the part to deliver."""
from __future__ import annotations

from ..core import (FAIL, PARTIAL, PASS, STAGE_DIMENSION, INDETERMINATE, Descriptor, Part, Step, clip)
from .context import Context

STAGE = "select"
BLOCKING = ("resolution", "compatibility")   # validation is reported, never blocks delivery
GRANT_NEEDED = "only a restricted part is accepted; a grant is needed"


def select_open_first(descriptor: Descriptor, contract: dict) -> tuple[Part | None, Step]:
    """A5: the first accepted payload part that is open, else the first."""
    found = descriptor.candidates(contract.get("accepts", []))
    if not found:
        detail = "no accepted payload part to select"
        return None, Step(STAGE, "A5", "access_url", FAIL, detail)

    opened = [part for part in found if not part.restricted]
    if not opened:
        return found[0], Step(STAGE, "A5", "access_url", PARTIAL, GRANT_NEEDED)
    detail = clip(opened[0].url)
    if len(found) > 1:
        detail += f"; first of {len(found)} candidates, open parts first"
    return opened[0], Step(STAGE, "A5", "access_url", PASS, detail)


def select(ctx: Context) -> None:
    """A5: choose the part to deliver; stop on a resolution or compatibility FAIL."""
    if any(step.status == FAIL and STAGE_DIMENSION.get(step.stage) in BLOCKING for step in ctx.record.steps):
        ctx.stopped = "a resolution or compatibility check failed; no part is selected or loaded"
        return
    if any(step.stage == "match" and step.status == INDETERMINATE for step in ctx.record.steps):
        ctx.stopped = "a check could not decide; no part is selected or loaded"
        return
    if ctx.spec is None or "accepts" not in ctx.spec:
        if ctx.options.get("want") == "binding" and ctx.spec is not None:
            return
        ctx.stopped = "the contract asks for no part"
        return
    part, step = select_open_first(ctx.descriptor, ctx.spec)
    ctx.record.steps.append(step)
    if part is None:
        return
    ctx.selected = part
    ctx.record.selected = dict(part.__dict__)
