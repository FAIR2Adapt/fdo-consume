"""Check "contract": what one consumer needs from an object, as Steps."""
from __future__ import annotations

from ..contracts.model import ALIASES, ROOT_ATTRIBUTES
from ..core import FAIL, PARTIAL, PASS, INDETERMINATE, Descriptor, Part, Step, clip
from ..profiles import load_maps, provided
from ..registry import register

STAGE = "match"
ABSENT = (None, "", [])
SHOWN = 5


@register("check", "contract")
def check_contract(descriptor: Descriptor, contract: dict) -> list[Step]:
    """Steps A3, A7 and A4 for one descriptor and one contract."""
    steps = []
    if "profile" in contract:
        steps.append(_profile_identified(descriptor, contract["profile"]))
    steps.append(_required_metadata(descriptor, contract))
    if "accepts" in contract:
        steps.append(_resource_declared(descriptor, contract["accepts"]))
    return steps


def _profile_identified(descriptor: Descriptor, wanted: str) -> Step:
    """A3: any profile the crate conforms to, against the contract."""
    stated = list(descriptor.profiles)
    if not stated and descriptor.profile:
        stated = [descriptor.profile]
    if not stated:
        return Step(STAGE, "A3", "profile_identified", FAIL, "the root states no profile")
    for profile in stated:
        if _no_slash(profile) == _no_slash(wanted):
            return Step(STAGE, "A3", "profile_identified", PASS, clip(profile))
    listed = ", ".join(clip(profile) for profile in stated[:SHOWN])
    if len(stated) > SHOWN:
        listed += f", and {len(stated) - SHOWN} more"
    detail = f"the crate states {listed}; the contract expects {wanted}"
    return Step(STAGE, "A3", "profile_identified", PARTIAL, detail)


def _required_metadata(descriptor: Descriptor, contract: dict) -> Step:
    """A7: the `must` and `should` fields of the contract."""
    undefined = _undefined(descriptor, contract)
    no_must = [n for n in _absent(descriptor, contract.get("must", [])) if n not in undefined]
    no_should = [n for n in _absent(descriptor, contract.get("should", [])) if n not in undefined]
    notes = []
    if no_must:
        notes.append("must absent: " + ", ".join(no_must))
    if no_should:
        notes.append("should absent: " + ", ".join(no_should))
    if undefined:
        notes.append("the profile defines no such term: " + ", ".join(undefined))

    if no_must:
        return Step(STAGE, "A7", "required_metadata", FAIL, "; ".join(notes))
    if [n for n in undefined if n in contract.get("must", [])]:
        return Step(STAGE, "A7", "required_metadata", INDETERMINATE, "; ".join(notes))
    if no_should:
        return Step(STAGE, "A7", "required_metadata", PARTIAL, "; ".join(notes))
    if undefined:  # undefined should-terms don't lower the status
        return Step(STAGE, "A7", "required_metadata", PASS, "; ".join(notes),
                    [{"code": "profile.term_undefined", "terms": list(undefined)}])
    return Step(STAGE, "A7", "required_metadata", PASS, "all present")


def _undefined(descriptor: Descriptor, contract: dict) -> list[str]:
    """Terms the contract names that the map used for this object (and its overlay) does not define."""
    if not descriptor.map_used:
        return []
    maps = load_maps(descriptor.extra.get("profile_maps"))
    concepts = {"resources", "members"}
    for name in (descriptor.map_used, descriptor.extra.get("overlay")):
        if name in maps:
            concepts |= set(maps[name].get("fields", {}))
            concepts |= set(maps[name].get("entities", {})) | provided(maps[name])
    out = []
    for term in contract.get("must", []) + contract.get("should", []):
        concept = ALIASES.get(term, term)
        if concept not in concepts and concept not in ROOT_ATTRIBUTES and term not in out:
            out.append(term)
    return out


def _resource_declared(descriptor: Descriptor, accepts: list[str]) -> Step:
    """A4: a payload part of a media type the consumer accepts."""
    found = descriptor.candidates(accepts)
    declared = [part for part in found if part.media_how == "declared"]
    if declared:
        detail = f"{clip(declared[0].id)} [{clip(declared[0].media_type)}]"
        if len(found) > 1:
            detail += f"; one of {len(found)} accepted payload parts"
        return Step(STAGE, "A4", "resource_declared", PASS, detail)
    if found:
        detail = f"{clip(found[0].id)} [{clip(found[0].media_type)}, {found[0].media_how}]"
        detail += "; the crate declares no encodingFormat for it"
        return Step(STAGE, "A4", "resource_declared", PARTIAL, detail)
    if not descriptor.parts:
        return Step(STAGE, "A4", "resource_declared", FAIL, "the crate lists no File part")

    seen = [_as_found(part) for part in descriptor.parts[:SHOWN]]
    detail = "no accepted payload part; found: " + "; ".join(seen)
    if len(descriptor.parts) > SHOWN:
        detail += f"; and {len(descriptor.parts) - SHOWN} more"
    return Step(STAGE, "A4", "resource_declared", FAIL, detail)


def _as_found(part: Part) -> str:
    """One part for the A4 detail: its id, its media type, payload or why not."""
    kind = "payload"
    if not part.payload:
        kind = "not a payload"
    if not part.payload and part.why_not_payload:
        kind = f"not a payload: {clip(part.why_not_payload)}"
    return f"{clip(part.id)} [{clip(part.media_type or 'no media type')}, {kind}]"


def _no_slash(iri: str) -> str:
    """An IRI without one trailing slash."""
    if iri.endswith("/"):
        return iri[:-1]
    return iri


def _absent(descriptor: Descriptor, names: list[str]) -> list[str]:
    """Contract terms with no value in the descriptor: root fields, entity types, `resources`, `members`."""
    absent = []
    entities = descriptor.extra.get("entities", []) + descriptor.extra.get("resources", [])
    root_fields = descriptor.extra.get("root_fields", {})
    for name in names:
        concept = ALIASES.get(name, name)
        if concept == "resources":
            value = descriptor.parts
        elif concept == "members":
            value = descriptor.members
        elif concept in root_fields:
            value = root_fields[concept]
        elif concept in ROOT_ATTRIBUTES:
            value = getattr(descriptor, ROOT_ATTRIBUTES[concept])
        elif any(e["type"] == concept or concept in e.get("provides", []) for e in entities):
            value = [e for e in entities if e["type"] == concept or concept in e.get("provides", [])]
        elif hasattr(descriptor, name):
            value = getattr(descriptor, name)
        else:
            value = None
        if value in ABSENT:
            absent.append(name)
    return absent
