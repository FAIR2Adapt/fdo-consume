"""Stage describe: O1; the object read into a description."""
from __future__ import annotations

import re

from ..core import FAIL, PARTIAL, PASS, SCHEME, INDETERMINATE, AccessError, Step, clip
from ..profiles import load_maps, select_profile
from ..profiles.selection import DEFAULT
from ..semantics.media import INFERRED
from .. import registry
from .context import Context
from .interpret_map import declared_profiles, interpret_map
from .locate import _adapter

UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
SHOWN = 5


def describe(ctx: Context) -> None:
    """P2 and O1: read the crate into a Descriptor by a profile map when one applies; is it the object asked for?"""
    chosen = _chosen_map(ctx)
    before, after = [], []
    if chosen is None:
        descriptor = _describer(ctx)(ctx.located)
    else:
        selection, maps, overlay = chosen
        descriptor, before, after = interpret_map(ctx.pid, ctx.canonical, selection, maps, overlay,
                                                  infer_media=ctx.options.get("infer_media", True) is not False)
        descriptor.extra["profile_maps"] = ctx.options.get("profile_maps")
    asked = ctx.pid.rstrip("/")
    others = [iri for iri in descriptor.members if iri.rstrip("/") != asked]
    descriptor.members_skipped += len(descriptor.members) - len(others)
    descriptor.members = others
    ctx.descriptor = descriptor
    ctx.record.descriptor = descriptor.to_dict(ctx.limits)
    stated = list(descriptor.identifiers)
    if not stated and descriptor.identifier:
        stated = [descriptor.identifier]
    if ctx.options.get("infer_media", True) is False:
        _declared_only(descriptor)
    ctx.record.steps.extend(before)
    if descriptor.extra.get("identity") == "deposit":
        ctx.record.steps.append(Step("describe", "O1", "identity", PASS, "identity by deposit: the root is the record this PID led to"))
    else:
        ctx.record.steps.append(_identity(ctx.pid, stated))
    ctx.record.steps.extend(after)


def _declared_only(descriptor) -> None:
    """Undo every inferred media type: the consumer asked for declared facts only."""
    for part in descriptor.parts:
        if part.media_how == INFERRED:
            part.media_type = part.declared_media_type
            part.media_how = "declared" if part.declared_media_type else None
    for row in descriptor.extra.get("resources", []):
        if row.get("media_type_source") == INFERRED:
            row["media_type"] = row["declared_media_type"]
            row["media_type_source"] = "declared" if row["declared_media_type"] else None


def _chosen_map(ctx: Context):
    """(selection, maps, overlay) when a map other than the default reads this object, else None."""
    graph = ctx.canonical
    if graph is None or not graph.available:
        return None
    maps = load_maps(ctx.options.get("profile_maps"))
    overlay = ctx.options.get("overlay") or (ctx.spec or {}).get("profile_additions")
    if overlay is not None and (overlay not in maps or not maps[overlay].get("overlay")):
        raise AccessError("request.bad_option", f"unknown overlay: {overlay!r}")
    try:
        selection = select_profile(declared_profiles(graph), maps, ctx.options.get("profile"))
    except KeyError:
        raise AccessError("request.bad_option", f"unknown profile map: {ctx.options.get('profile')!r}") from None
    if ctx.record.semantics is not None:
        ctx.record.semantics["profile"] = selection.to_dict()
    if selection.ambiguous:
        ctx.record.steps.append(Step("describe", "P2", "profile_selected", INDETERMINATE, clip(
            f"{selection.reason}: {', '.join(selection.candidates)}")))
        return None
    if selection.selected == DEFAULT and overlay is None and ctx.options.get("profile") is None:
        return None
    return selection, maps, overlay


DOI_HOSTS = ("doi.org", "dx.doi.org", "www.doi.org")
HANDLE_HOSTS = ("hdl.handle.net",)


def normal_pid(text: str) -> str:
    """Normal form under explicit rules only: DOI and Handle spellings, host case. No scheme change."""
    text = text.strip()
    if not SCHEME.match(text):
        return text
    scheme, _, rest = text.partition(":")
    scheme = scheme.lower()
    if scheme == "doi":
        return "doi:" + rest.lower()                      # DOI names are case-insensitive
    if scheme == "hdl":
        return "hdl:" + rest
    if not rest.startswith("//"):
        return f"{scheme}:{rest}"
    host, slash, path = rest[2:].partition("/")
    host = host.lower()
    if scheme in ("http", "https") and host in DOI_HOSTS and path:
        return "doi:" + path.lower()
    if scheme in ("http", "https") and host in HANDLE_HOSTS and path:
        return "hdl:" + path
    return f"{scheme}://{host}{slash}{path}"


def _candidate(asked: str, stated: str) -> str | None:
    """Reason two identifiers are equivalence candidates without an equivalence rule; None if not candidates."""
    a, b = normal_pid(asked), normal_pid(stated)
    if a.rstrip("/") == b.rstrip("/"):
        return "differs only by a trailing slash"
    if a.split(":", 1)[-1] == b.split(":", 1)[-1] and {a.split(":", 1)[0], b.split(":", 1)[0]} == {"http", "https"}:
        return "differs only by http/https"
    ua, ub = UUID.search(asked.lower()), UUID.search(stated.lower())
    if ua and ub and ua.group() == ub.group():
        return "shares a UUID"
    return None


def _describer(ctx: Context) -> Callable:
    """The describer the caller named, or the first that matches the crate."""
    name = ctx.options.get("describer")
    if name is not None:
        return _adapter("describer", name, "request.bad_option")
    found = registry.pick("describer", ctx.located)
    if found is None:
        raise AccessError("object.no_describer", "no describer matches what the PID led to")
    return found


def _identity(pid: str, identifiers: list[str]) -> Step:
    """O1: does any identifier the crate states name the object asked for?"""
    if not identifiers:
        return Step("describe", "O1", "identity", PARTIAL, "the crate states no identifier")
    if pid in identifiers:
        return Step("describe", "O1", "identity", PASS, clip(pid))
    for identifier in identifiers:
        if normal_pid(pid) == normal_pid(identifier):
            detail = f"same object, other spelling: {clip(identifier)}"
            return Step("describe", "O1", "identity", PASS, detail)
    for identifier in identifiers:
        why = _candidate(pid, identifier)
        if why is not None:
            detail = f"alternate identifier candidate: {clip(identifier)} {why}; no rule establishes equivalence"
            return Step("describe", "O1", "identity", INDETERMINATE, detail)
    stated = ", ".join(clip(identifier) for identifier in identifiers[:SHOWN])
    if len(identifiers) > SHOWN:
        stated += f", and {len(identifiers) - SHOWN} more"
    detail = f"asked for {pid}; the crate states {stated}"
    return Step("describe", "O1", "identity", FAIL, detail)
