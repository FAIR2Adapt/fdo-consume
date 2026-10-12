"""Compatibility fallback describer "ro-crate" for objects read without a profile map.

Remove when the ro-crate map path passes the fallback tests (root checks, identifiers, part limits, URL safety).
"""
from __future__ import annotations

import ipaddress
import socket
import re
from urllib.parse import urlsplit, urlunsplit

from ..semantics.landing import landing_reason
from ..semantics.media import decide, from_suffix
from ..core import AccessError, Descriptor, Located, Part, has_scheme
from ..registry import register

METADATA_FILES = ("ro-crate-metadata.json", "ro-crate-metadata.jsonld")
RO_CRATE_SPEC = "https://w3id.org/ro/crate/"
RO_CRATE_VERSION = "w3id.org/ro/crate/"
PART_TYPES = ("File", "MediaObject")
ACCESS_TERMS = ("conditionsOfAccess", "accessRights", "dct:accessRights")
RESTRICTED_WORDS = (
    "restricted", "closed", "embargo", "embargoed", "private", "confidential",
    "non-public", "non_public", "c_16ec", "c_14cb", "c_f1cf",
)
OPEN_WORDS = ("open", "public", "c_abf2")
LANDING_HOSTS = ("doi.org", "dx.doi.org")
PAGE_HOSTS = ("github.com",)
SHARED_ADDRESS_SPACE = ipaddress.ip_network("100.64.0.0/10")
INTERNAL_SUFFIXES = (".local", ".localdomain", ".internal", ".lan", ".intranet", ".corp", ".home")
MAX_SIZE_DIGITS = 18
CAMEL = re.compile(r"([a-z])([A-Z])")
INFERRED = "inferred from the URL suffix"
SUFFIX_MEDIA = None  # the table moved to semantics/data/media-suffixes.yaml
NOT_A_WORD = re.compile(r"[^a-z0-9]+")


def is_json_object(located: Located) -> bool:
    """True when the located crate is a JSON object."""
    return isinstance(located.crate, dict)


# TODO: ROHub research objects (folders, nesting) need real samples
@register("describer", "ro-crate", match=is_json_object)
def describe_ro_crate(located: Located) -> Descriptor:
    """Read the root entity, its parts and its members."""
    graph = None
    if isinstance(located.crate, dict):
        graph = located.crate.get("@graph")
    if not isinstance(graph, list):
        raise AccessError("object.no_graph", "the crate has no @graph list")

    entities = []
    for entity in graph:
        if isinstance(entity, dict) and isinstance(entity.get("@id"), str):
            entities.append(entity)
    by_id = {entity["@id"]: entity for entity in entities}
    root = _root(entities, by_id)

    root_access = _access(root)
    parts = []
    for entity in by_id.values():
        if entity is root or _is_metadata_file(entity):
            continue
        if _is_part(entity):
            parts.append(_part(entity, root_access))

    identifiers = _identifiers(root, by_id)
    profiles = _profiles(root)
    members, skipped = _members(root, by_id)
    return Descriptor(
        pid=located.pid,
        identifier=_first(identifiers),
        name=_text(root.get("name")),
        types=[t for t in _as_list(root.get("@type")) if isinstance(t, str)],
        resource_type=_id_or_text(root.get("additionalType")),
        description=_text(root.get("description")),
        license=_id_or_text(root.get("license")),
        date=_text(root.get("datePublished")),
        profile=_first(profiles),
        parts=parts,
        members=members,
        identifiers=identifiers,
        profiles=profiles,
        members_skipped=skipped,
    )


def _root(entities: list[dict], by_id: dict) -> dict:
    """The root entity: `./`, else what a metadata file entity is about."""
    roots = [entity for entity in entities if entity["@id"] == "./"]
    if len(roots) > 1:
        raise AccessError("object.ambiguous_root", f"{len(roots)} entities have the id ./")
    if roots:
        return roots[0]
    pointers = [entity for entity in entities if _conforms_to_ro_crate(entity)]
    pointers += [by_id[name] for name in METADATA_FILES if name in by_id]
    for entity in pointers:
        found = by_id.get(_id_or_text(entity.get("about")))
        if found is not None:
            return found
    raise AccessError("object.no_root", "the crate has no root entity")


def _conforms_to_ro_crate(entity: dict) -> bool:
    """True when the entity conforms to a version of the RO-Crate specification."""
    for item in _as_list(entity.get("conformsTo")):
        if (_id_or_text(item) or "").startswith(RO_CRATE_SPEC):
            return True
    return False


def _is_metadata_file(entity: dict) -> bool:
    """True for the entity that describes the crate file itself."""
    return entity["@id"] in METADATA_FILES or _conforms_to_ro_crate(entity)


def _is_part(entity: dict) -> bool:
    """True for an entity typed File or MediaObject."""
    for name in PART_TYPES:
        if _is_type(entity, name):
            return True
    return False


def _part(entity: dict, root_access: str | None) -> Part:
    """One File or MediaObject entity as a Part; its bytes are not touched."""
    part_id = entity["@id"]
    if has_scheme(part_id):
        part_id = _without_user_info(part_id)
    url = _id_or_text(entity.get("contentUrl"))
    if url is None and has_scheme(part_id):
        url = part_id
    if url is not None:
        url = _without_user_info(url)
    why_not = _why_not_payload(url)
    access = _access(entity) or root_access
    declared = _text(entity.get("encodingFormat"))
    media_type, media_how = decide(url, declared, True)
    return Part(
        id=part_id,
        name=_text(entity.get("name")),
        media_type=media_type,
        url=url,
        size=_size(entity.get("contentSize")),
        restricted=access == "restricted",
        payload=why_not is None,
        why_not_payload=why_not,
        media_how=media_how,
        declared_media_type=declared,
        access=access,
    )


def _media_from_suffix(url: str | None) -> str | None:
    """A media type for the last suffix of the URL path, when it is a known one (shared table)."""
    return from_suffix(url)


def _without_user_info(url: str) -> str:
    """The URL without `user:password@`: credentials are never stored."""
    try:
        parsed = urlsplit(url)
    except ValueError:
        scheme, separator, rest = url.partition("://")
        return scheme + separator + rest.rpartition("@")[2]
    if "@" not in parsed.netloc:
        return url
    return urlunsplit(parsed._replace(netloc=parsed.netloc.rpartition("@")[2]))


def _why_not_payload(url: str | None) -> str | None:
    """Why the parsed URL is not a payload to fetch; None when it is one."""
    if url is None:
        return "no URL"
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").rstrip(".")
    except ValueError:
        return "the URL does not parse"
    if not parsed.scheme:
        return "no scheme"
    if parsed.scheme not in ("http", "https"):
        return f"scheme {parsed.scheme} is not supported"
    if not host:
        return "no host"
    if landing_reason(url):
        return "landing page"
    if host in PAGE_HOSTS and "/raw/" not in parsed.path:
        return "a page, not a file"
    if host == "localhost" or _is_private_address(host):
        return "private address"
    return None


def _is_private_address(host: str) -> bool:
    """True for a loopback, private, link-local or internal host, including numeric forms inet_aton accepts."""
    lowered = host.lower()
    if lowered == "localhost" or lowered.endswith(INTERNAL_SUFFIXES) or ("." not in lowered and ":" not in lowered):
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        try:
            address = ipaddress.ip_address(socket.inet_ntoa(socket.inet_aton(host)))
        except (OSError, ValueError):
            return False
    mapped = getattr(address, "ipv4_mapped", None)
    if mapped is not None:
        address = mapped
    return (address.is_loopback or address.is_private or address.is_link_local or address.is_unspecified
            or (address.version == 4 and address in SHARED_ADDRESS_SPACE))


def _access(entity: dict) -> str | None:
    """What the entity states about access: "restricted", "open" or None."""
    words = []
    for term in ACCESS_TERMS:
        for item in _as_list(entity.get(term)):
            text = CAMEL.sub(r"\1 \2", _id_or_text(item) or "")
            words.extend(NOT_A_WORD.split(text.lower()))
    if not words:
        return None
    stated = set(words)
    for first, second in zip(words, words[1:]):
        stated.add(f"{first}-{second}")
        stated.add(f"{first}_{second}")
    if stated.intersection(RESTRICTED_WORDS):
        return "restricted"
    if stated.intersection(OPEN_WORDS):
        return "open"
    return None


def _identifiers(root: dict, by_id: dict) -> list[str]:
    """Every identifier the root states, as text, once each."""
    found = []
    for item in _as_list(root.get("identifier")):
        text = _identifier(item, by_id)
        if text is not None and text not in found:
            found.append(text)
    return found


def _identifier(item: object, by_id: dict) -> str | None:
    """One identifier: text, an @value, a PropertyValue's value, or an absolute @id."""
    if not isinstance(item, dict):
        return _text(item)
    if "value" in item:
        return _text(item["value"])
    reference = item.get("@id")
    if not isinstance(reference, str):
        return _text(item)
    target = by_id.get(reference, {})
    if "value" in target:
        return _text(target["value"])
    if has_scheme(reference):
        return reference
    return None


def _profiles(root: dict) -> list[str]:
    """Every conformsTo of the root that is not an RO-Crate version, once each."""
    found = []
    for item in _as_list(root.get("conformsTo")):
        iri = _id_or_text(item)
        if iri and RO_CRATE_VERSION not in iri and iri not in found:
            found.append(iri)
    return found


def _members(root: dict, by_id: dict) -> tuple[list[str], int]:
    """PIDs a Collection root lists in hasPart, once each; and the entries skipped."""
    if not _is_type(root, "Collection"):
        return [], 0
    members = []
    seen = set()
    skipped = 0
    for item in _as_list(root.get("hasPart")):
        iri = _id_or_text(item)
        if iri is not None and _is_part(by_id.get(iri, {})):
            continue
        if not has_scheme(iri):
            skipped += 1
            continue
        if iri.rstrip("/") in seen:
            continue
        seen.add(iri.rstrip("/"))
        members.append(iri)
    return members, skipped


def _first(texts: list[str]) -> str | None:
    """The first text of a list; None for an empty list."""
    if texts:
        return texts[0]
    return None


def _as_list(value: object) -> list:
    """None gives [], a list stays, one value gives [value]."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _text(value: object) -> str | None:
    """First text in a string, an @value object or a list."""
    for item in _as_list(value):
        if isinstance(item, dict):
            item = item.get("@value")
        if isinstance(item, str) and item.strip():
            return item
    return None


def _id_or_text(value: object) -> str | None:
    """First @id or text in a value; None when there is none."""
    for item in _as_list(value):
        if isinstance(item, dict) and isinstance(item.get("@id"), str):
            return item["@id"]
        text = _text(item)
        if text is not None:
            return text
    return None


def _is_type(entity: dict, name: str) -> bool:
    """True when the entity has the schema.org type `name`."""
    spellings = (name, "schema:" + name, "http://schema.org/" + name, "https://schema.org/" + name)
    for stated in _as_list(entity.get("@type")):
        if stated in spellings:
            return True
    return False


def _size(value: object) -> int | None:
    """Return contentSize as a non-negative integer, or None when invalid."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    if isinstance(value, float) and value >= 0 and value.is_integer():
        return int(value)
    if not isinstance(value, str):
        return None
    digits = value.strip()
    if digits.isascii() and digits.isdigit() and len(digits) <= MAX_SIZE_DIGITS:
        return int(digits)
    return None
