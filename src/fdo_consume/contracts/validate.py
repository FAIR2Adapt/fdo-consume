"""Rules a needs-form contract must satisfy; a violation is a request error, not an object status."""
from __future__ import annotations

import re
from collections.abc import Mapping

from ..core import AccessError, shown
from .model import ALIASES, LEVELS, NEW_KEYS

MEDIA_TYPE = re.compile(r"[a-z0-9][a-z0-9!#$&^_.+-]*/[a-z0-9][a-z0-9!#$&^_.+-]*")


def check_needs_form(spec: Mapping, label: str, terms: set) -> None:
    """Refuse a needs-form contract that has no consumer, no source, a bad need, or no requirements."""
    for key in spec:
        if key not in NEW_KEYS:
            _refuse(f"unknown key in {label}: {shown(key)}")
    _named(spec.get("consumer"), ("service", "capability"), "consumer", label)
    _check_source(spec.get("source"), label)
    if not str(spec.get("contract_id", "")).strip():
        _refuse(f"{label} has no contract_id")
    needs = spec["needs"]
    accepts = spec.get("accepts", [])
    if not isinstance(needs, list) or not isinstance(accepts, list):
        _refuse(f"needs and accepts are lists in {label}")
    if not needs and not accepts:
        _refuse(f"{label} defines no requirements")
    seen = set()
    for need in needs:
        _check_need(need, label, terms)
        if need["term"] in seen:
            _refuse(f"{label} names the term {need['term']} twice")
        seen.add(need["term"])
    for media in accepts:
        if not isinstance(media, str) or not MEDIA_TYPE.fullmatch(media.lower()):
            _refuse(f"{label} contains an invalid media type: {shown(media)}")


def _check_need(need: object, label: str, terms: set) -> None:
    """One need: a concept some profile map defines, a level, a source and a reason."""
    if not isinstance(need, Mapping):
        _refuse(f"a need in {label} is not a mapping")
    term = ALIASES.get(need.get("term"), need.get("term"))
    if term not in terms:
        _refuse(f"{label} names a term no profile map defines: {shown(need.get('term'))}; known terms: {', '.join(sorted(terms))}")
    if need.get("level") not in LEVELS:
        _refuse(f"{label}: {need['term']} has level {shown(need.get('level'))}; one of {LEVELS}")
    for key in ("source", "reason"):
        if not str(need.get(key, "")).strip():
            _refuse(f"{label}: the need {need['term']} has no {key}")


def _check_source(value: object, label: str) -> None:
    """Provenance: repository, path, reviewed (revision, symbol, note optional); legacy form document + section."""
    if isinstance(value, Mapping) and "repository" in value:
        _named(value, ("repository", "path", "reviewed"), "source", label)
    else:
        _named(value, ("document", "section"), "source", label)


def _named(value: object, keys: tuple, name: str, label: str) -> None:
    """A mapping with non-empty text under each of the keys."""
    if not isinstance(value, Mapping) or any(not str(value.get(k, "")).strip() for k in keys):
        _refuse(f"{label} has no {name} with {' and '.join(keys)}")


def _refuse(message: str) -> None:
    """Raise the request error for a bad contract."""
    raise AccessError("request.bad_contract", message)
