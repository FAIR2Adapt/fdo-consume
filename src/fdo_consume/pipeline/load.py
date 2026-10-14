"""Stage load: A9, deliver the selected part."""
from __future__ import annotations

from ..core import (PARTIAL, PASS, WANTS, AccessError, Loaded, Part, Step, clip, shown)
from .. import registry
from ..loaders.binding import build_binding
from .context import Context


def load(ctx: Context) -> None:
    """A9: deliver the selected part; a restricted part stays a reference."""
    part = ctx.selected
    want = ctx.options.get("want", "reference")
    if want not in WANTS:
        raise AccessError("request.bad_option", f"unknown want: {shown(want)}; one of {WANTS}")
    if want == "binding":
        _load_binding(ctx)
        return
    if part is None:
        ctx.stopped = "no part was selected"
        return
    loader, shortfall = _loader(part, want)
    loaded = loader(part)
    if not isinstance(loaded, Loaded):
        loaded = Loaded(want, loaded, part.media_type)
    ctx.record.value = loaded.value
    ctx.record.loaded = loaded.to_dict()
    if shortfall is None:
        ctx.record.steps.append(Step("load", "A9", "bindable", PASS, clip(loaded.note)))
        return
    ctx.record.steps.append(Step("load", "A9", "bindable", PARTIAL, shortfall))


def _loader(part: Part, want: str) -> tuple[Callable, str | None]:
    """The loader to use, and why it is not the wanted one (or None)."""
    reference = registry.get("loader", "reference")
    if part.restricted and want == "reference":
        return reference, None
    if part.restricted:
        return reference, f"restricted: a reference is returned, not a {want} object"
    found = registry.pick("loader", part, want)
    if found is None:
        kind = clip(part.media_type)
        return reference, f"no {want} loader for {kind}; a reference is returned"
    return found, None


def _load_binding(ctx: Context) -> None:
    """A9 for want=binding: the binding is returned whether or not a part was selected; no data is read."""
    binding = build_binding(ctx.descriptor, ctx.record, ctx.spec, ctx.selected)
    ctx.record.value = binding
    ctx.record.loaded = Loaded("binding", None, "application/json", False, "binding built from the record").to_dict()
    ctx.record.loaded["in_memory"] = False
    ctx.record.loaded["value"] = binding
    count = (len(binding["entities"]), len(binding["resources"]))
    ctx.record.steps.append(Step("load", "A9", "bindable", PASS, f"binding of {count[0]} entities and {count[1]} resources; nothing was read"))
