"""Stage match: the checks the contract names, in order."""
from __future__ import annotations

from .context import Context
from .locate import _adapter


def match(ctx: Context) -> None:
    """Run the checks the contract names, in order."""
    if ctx.spec is None:
        ctx.stopped = "no contract given"
        return
    checks = []
    for name in ctx.spec.get("checks", ["contract"]):
        checks.append(_adapter("check", name, "request.bad_contract"))
    for run in checks:
        ctx.record.steps.extend(run(ctx.descriptor, ctx.spec))
