"""Data passed between stages: located object, parts, descriptor, loaded value."""
from __future__ import annotations

from dataclasses import dataclass, field

from .limits import Limits
from .util import clip_long, has_scheme, media_key


@dataclass
class Located:
    """A located crate: resolution chain, byte hash and size."""

    pid: str
    crate: object
    chain: list[str]
    crate_sha256: str
    size: int


@dataclass
class Part:
    """Metadata of a resource the crate declares; the resource itself is not read."""

    id: str
    name: str | None
    media_type: str | None
    url: str | None
    size: int | None
    restricted: bool
    payload: bool
    why_not_payload: str | None = None
    media_how: str | None = None
    in_crate: bool = False
    declared_media_type: str | None = None
    access: str | None = None


@dataclass
class Descriptor:
    """Description of the object: declared values and provenance-labelled inferences, kept distinct."""

    pid: str
    identifier: str | None
    name: str | None
    types: list[str]
    resource_type: str | None
    description: str | None
    license: str | None
    date: str | None
    profile: str | None
    parts: list[Part]
    members: list[str]
    identifiers: list[str] = field(default_factory=list)
    profiles: list[str] = field(default_factory=list)
    members_skipped: int = 0
    extra: dict = field(default_factory=dict)
    map_used: str | None = None

    def candidates(self, accepts: list[str]) -> list[Part]:
        """Payload parts of an accepted media type, in crate order."""
        wanted = [media_key(item) for item in accepts]
        found = []
        for part in self.parts:
            if part.payload and part.media_type and media_key(part.media_type) in wanted:
                found.append(part)
        return found

    def to_dict(self, limits: Limits) -> dict:
        """Plain data for a record: parts and members capped, totals kept."""
        plain = dict(self.__dict__)
        for key in ("name", "description", "license", "identifier"):
            plain[key] = clip_long(plain[key])
        plain["parts"] = [dict(part.__dict__) for part in self.parts[:limits.max_parts]]
        plain["parts_total"] = len(self.parts)
        plain["members"] = self.members[:limits.max_members]
        plain["members_total"] = len(self.members)
        return plain


@dataclass
class Loaded:
    """What the consumer receives: kind is reference, lazy or native."""

    kind: str
    value: object
    media_type: str | None
    requires_authorization: bool = False
    note: str = ""

    def to_dict(self) -> dict:
        """Plain data for a record: a text value is kept, any other stays in memory."""
        plain = dict(self.__dict__)
        plain["in_memory"] = not isinstance(self.value, str)
        if plain["in_memory"]:
            plain["value"] = None
        return plain


SCHEMA_SPELLINGS = ("http://schema.org/", "https://schema.org/")


def spellings(iri: str) -> list[str]:
    """An IRI and, for schema.org, the same IRI with the other scheme."""
    for one, other in (SCHEMA_SPELLINGS, SCHEMA_SPELLINGS[::-1]):
        if iri.startswith(one):
            return [iri, other + iri[len(one):]]
    return [iri]


@dataclass
class CanonicalGraph:
    """The object's terms as expanded IRIs: nodes[id][iri] is a list of references or literals."""

    available: bool = False
    nodes: dict = field(default_factory=dict)
    unknown_terms: list[str] = field(default_factory=list)
    unknown_contexts: list[str] = field(default_factory=list)
    contexts: list[str] = field(default_factory=list)
    problems: list[dict] = field(default_factory=list)

    def types(self, node_id: str) -> set[str]:
        """The expanded @type IRIs of a node, each also in its other schema.org spelling."""
        found = set()
        for iri in self.nodes.get(node_id, {}).get("@type", []):
            found.update(spellings(iri))
        return found

    def values(self, node_id: str, iri: str) -> list:
        """The values of one property of a node, under either schema.org spelling; absent is []."""
        node = self.nodes.get(node_id, {})
        found = []
        for spelling in spellings(iri):
            found.extend(node.get(spelling, []))
        return found

    def root_id(self) -> str | None:
        """The root by the RO-Crate rule: the `about` of the metadata descriptor."""
        about = "http://schema.org/about"
        for node_id in self.nodes:
            if node_id == "ro-crate-metadata.json" or node_id.endswith("/ro-crate-metadata.json"):
                for value in self.values(node_id, about):
                    if isinstance(value, dict) and "@id" in value:
                        return value["@id"]
        return None

    def resolve_relative(self, ref: str, base: str) -> str | None:
        """A crate-local reference resolved against the crate base; None when it leaves the base."""
        if has_scheme(ref) or ref.startswith("/") or "\\" in ref:
            return None
        parts = []
        for piece in ref.split("#")[0].split("/"):
            if piece in ("", "."):
                continue
            if piece == "..":
                return None
            parts.append(piece)
        return base.rstrip("/") + "/" + "/".join(parts) if parts else base
