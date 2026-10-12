"""Which map reads an object."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

DEFAULT = "ro-crate"


@dataclass
class ProfileSelection:
    """The declared profiles, the map chosen, why, and what was not recognised."""

    declared: list[str] = field(default_factory=list)
    selected: str = DEFAULT
    reason: str = ""
    candidates: list[str] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)
    ambiguous: bool = False
    spelling: str | None = None

    def to_dict(self) -> dict:
        """Plain data for a record."""
        return asdict(self)


def select_profile(declared: list[str], maps: dict, requested: str | None = None) -> ProfileSelection:
    """Choose the map for the declared profile IRIs."""
    out = ProfileSelection(declared=list(declared))
    if requested is not None:
        if requested not in maps:
            raise KeyError(requested)
        out.selected, out.reason = requested, "requested"
        return out
    index = {}
    for spec in maps.values():
        for iri in spec.get("selects", []):
            index[iri.rstrip("/")] = spec["id"]
    hits = {}
    for iri in declared:
        found = index.get(iri.rstrip("/"))
        if found:
            hits.setdefault(found, iri)
        else:
            out.unknown.append(iri)
    if len(hits) == 1:
        (out.selected, out.spelling), = hits.items()
        out.reason = "the one declared profile that has a map"
    elif len(hits) > 1:
        out.candidates = sorted(hits)
        out.ambiguous = True
        out.reason = "two or more declared profiles have a map; none is chosen"
    elif declared:
        out.reason = "declared profiles have no map; the default map is used"
    else:
        out.reason = "no profile declared; the default map is used"
    return out
