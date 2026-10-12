"""Profile maps: YAML files read once; a map says where a profile puts what, and at which level."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

MAPS = Path(__file__).resolve().parent / "maps"
LEVELS = ("must", "should", "may")


def load_maps(folder: str | Path | None = None) -> dict:
    """The built-in maps plus those of `folder` (a map there with the same id wins); every map is checked."""
    return dict(_load_maps(str(folder) if folder else None))


@lru_cache(maxsize=8)
def _load_maps(folder: str | None) -> dict:
    """All maps by id; a map that is not a mapping with an id, a source and valid levels is refused."""
    places = [MAPS] + ([Path(folder)] if folder else [])
    if folder and not Path(folder).is_dir():
        raise ValueError(f"the profile-map folder does not exist: {folder}")
    found = {}
    for place in places:
        for path in sorted(place.glob("*.yaml")):
            spec = yaml.safe_load(path.read_text(encoding="utf-8"))
            _check(spec, path.name)
            found[spec["id"]] = spec
    return found


def known_terms(maps: dict) -> set[str]:
    """Every concept a contract may name: root fields, entity names, canonical concepts (`provides`), `resources`, `members`."""
    terms = {"resources", "members"}
    for spec in maps.values():
        terms.update(spec.get("fields", {}))
        terms.update(spec.get("entities", {}))
        terms.update(provided(spec))
    return terms


def provided(spec: dict) -> set[str]:
    """Canonical concepts the entity blocks of one map provide, e.g. Assertion."""
    return {c for block in spec.get("entities", {}).values() for c in block.get("provides", [])}


def _check(spec: object, name: str) -> None:
    """Refuse a map without id and source, or with a level that is not must, should or may."""
    if not isinstance(spec, dict) or "id" not in spec or "source" not in spec:
        raise ValueError(f"map {name}: needs an id and a source")
    blocks = [spec.get("fields", {})] + [e.get("fields", {}) for e in spec.get("entities", {}).values()]
    for block in blocks:
        for concept, entry in block.items():
            if entry.get("level") not in LEVELS:
                raise ValueError(f"map {name}: {concept} has level {entry.get('level')!r}")
    for ename, block in spec.get("entities", {}).items():
        if isinstance(block.get("type"), list) and not all(isinstance(t, str) for t in block["type"]):
            raise ValueError(f"map {name}: entity {ename} has a type that is not text")
        if "type" not in block and "via" not in block and not spec.get("overlay"):
            raise ValueError(f"map {name}: entity {ename} needs a type or a via")
        if not isinstance(block.get("provides", []), list) or not all(isinstance(c, str) for c in block.get("provides", [])):
            raise ValueError(f"map {name}: entity {ename} has provides that is not a list of text")
        if block.get("level") is not None and block["level"] not in LEVELS:
            raise ValueError(f"map {name}: entity {ename} has level {block['level']!r}")
