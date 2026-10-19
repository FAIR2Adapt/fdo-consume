"""Rules a needs-form contract must satisfy; a violation is a request error, not an object status."""
from __future__ import annotations

import re
from collections.abc import Mapping

from ..core import AccessError, shown
from .model import ALIASES, LEVELS, NEW_KEYS

MEDIA_TYPE = re.compile(r"[a-z0-9][a-z0-9!#$&^_.+-]*/[a-z0-9][a-z0-9!#$&^_.+-]*")


def check_needs_form(spec: Mapping, label: str, terms: set) -> None:
    """Refuse a needs-form contract that has no consumer, a bad need, or no requirements."""
    for key in spec:
        if key not in NEW_KEYS:
            _refuse(f"unknown key in {label}: {shown(key)}")
    _named(spec.get("consumer"), ("service", "capability"), "consumer", label)
    _check_source(spec.get("source"), label)
    if not str(spec.get("contract_id", "")).strip():
        _refuse(f"{label} has no contract_id")
    needs = spec["needs"]
    accepts = spec.get("accepts", [])
    for key in ("profile", "profile_additions"):
        if key in spec and not isinstance(spec[key], str):
            _refuse(f"{key} is not text in {label}")
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
    """One need: a term some profile map defines and a level; source and reason are optional text."""
    if not isinstance(need, Mapping):
        _refuse(f"a need in {label} is not a mapping")
    if not isinstance(need.get("term"), str):
        _refuse(f"{label}: a need has no term, or a term that is not text: {shown(need.get('term'))}")
    term = ALIASES.get(need["term"], need["term"])
    if term not in terms:
        _refuse(f"{label} names a term no profile map defines: {shown(need.get('term'))}; known terms: {', '.join(sorted(terms))}")
    if need.get("level") not in LEVELS:
        _refuse(f"{label}: {need['term']} has level {shown(need.get('level'))}; one of {LEVELS}")
    for key in ("source", "reason"):
        if key in need and not isinstance(need[key], str):
            _refuse(f"{label}: the {key} of the need {need['term']} is not text")


def _check_source(value: object, label: str) -> None:
    """Optional provenance of the contract: a mapping of text values (repository, path, document, section, ...)."""
    if value is None:
        return
    if not isinstance(value, Mapping) or any(not isinstance(v, str) for v in value.values()):
        _refuse(f"{label} has a source that is not a mapping of text values")


def _named(value: object, keys: tuple, name: str, label: str) -> None:
    """A mapping with non-empty text under each of the keys."""
    if not isinstance(value, Mapping) or any(not str(value.get(k, "")).strip() for k in keys):
        _refuse(f"{label} has no {name} with {' and '.join(keys)}")


def _refuse(message: str) -> None:
    """Raise the request error for a bad contract."""
    raise AccessError("request.bad_contract", message)
