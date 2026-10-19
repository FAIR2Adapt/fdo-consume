"""Contracts: what one consumer needs, by name or as a mapping."""
from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import fields
from functools import lru_cache
from pathlib import Path

import yaml

from ..core import AccessError, Descriptor, shown
from ..profiles import known_terms, load_maps
from .model import ALIASES, as_internal, is_new_form
from .validate import MEDIA_TYPE, check_needs_form

CONTRACT_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
LIST_KEYS = ("must", "should", "accepts", "checks")
TEXT_KEYS = ("profile", "selector")
OTHER_KEYS = ("contract_id", "consumer", "description")
KNOWN_KEYS = OTHER_KEYS + LIST_KEYS + TEXT_KEYS
KNOWN_FIELDS = tuple(item.name for item in fields(Descriptor))


def load_contract(name_or_mapping: str | Mapping, folder: str | Path | None = None,
                  profile_maps: str | Path | None = None) -> dict:
    """A contract by name, or a mapping; a path is refused."""
    terms = known_terms(load_maps(profile_maps))
    if isinstance(name_or_mapping, Mapping):
        return _checked(name_or_mapping, "the given mapping", terms)
    name = name_or_mapping
    if not isinstance(name, str) or not CONTRACT_NAME.fullmatch(name):
        raise AccessError("request.bad_contract", f"not a contract name: {shown(name)}")
    places = [Path(folder)] if folder is not None else []
    if folder is not None and not places[0].is_dir():
        raise AccessError("request.bad_contract", f"the contract folder does not exist: {shown(str(folder))}")
    path = None
    for place in places:
        if (place / f"{name}.yaml").is_file():
            path = place / f"{name}.yaml"
            break
    if path is None:
        where = f"in {shown(str(folder))}" if folder is not None else "(a contract by name is read from the consumer's folder: contracts=)"
        raise AccessError("request.bad_contract", f"no contract named {shown(name)} {where}")
    try:
        spec = _parsed(str(path), path.stat().st_mtime_ns)
    except (yaml.YAMLError, ValueError, RecursionError) as err:
        message = f"contract {name!r} is not YAML: {type(err).__name__}"
        raise AccessError("request.bad_contract", message) from None
    return _checked(spec, f"contract {name!r}", terms)


def _checked(spec: object, label: str, terms: set) -> dict:
    """The contract when its keys and their shapes are known; else an error."""
    if not isinstance(spec, Mapping):
        raise AccessError("request.bad_contract", f"{label} is not a mapping")
    if is_new_form(spec):
        check_needs_form(spec, label, terms)
        internal = as_internal(spec)
        internal["must"] = [ALIASES.get(t, t) for t in internal["must"]]
        internal["should"] = [ALIASES.get(t, t) for t in internal["should"]]
        return internal
    for key in spec:
        if key not in KNOWN_KEYS:
            raise AccessError("request.bad_contract", f"unknown key in {label}: {shown(key)}")
    for key in LIST_KEYS:
        _check_list_of_text(spec.get(key, []), key, label)
    for key in TEXT_KEYS:
        if not isinstance(spec.get(key, ""), str):
            raise AccessError("request.bad_contract", f"{key} is not text in {label}")
    if not any(spec.get(key) for key in ("must", "should", "accepts", "checks", "profile")):
        raise AccessError("request.bad_contract", f"{label} defines no requirements")
    for media in spec.get("accepts", []):
        if not MEDIA_TYPE.fullmatch(media.split(";")[0].strip().lower()):
            raise AccessError("request.bad_contract", f"{label} contains an invalid media type: {shown(media)}")
    for name in spec.get("must", []) + spec.get("should", []):
        if name not in KNOWN_FIELDS:
            message = f"{label} references an unknown descriptor field: {shown(name)}"
            raise AccessError("request.bad_contract", message)
    return spec


def _check_list_of_text(value: object, key: str, label: str) -> None:
    """Refuse a contract key that is not a list of text."""
    if not isinstance(value, list):
        raise AccessError("request.bad_contract", f"{key} is not a list in {label}")
    for item in value:
        if not isinstance(item, str):
            message = f"{key} contains a non-string value in {label}: {shown(item)}"
            raise AccessError("request.bad_contract", message)


@lru_cache(maxsize=32)
def _parsed(path: str, changed: int) -> object:
    """A YAML file, parsed once until the file changes."""
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))
