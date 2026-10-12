"""Interpret an object through a profile map: the canonical graph in, one FDODescription out."""
from __future__ import annotations

from ..core import FAIL, PARTIAL, PASS, AccessError, CanonicalGraph, Descriptor, Part, Step, clip, has_scheme
from ..profiles import ProfileSelection
from ..semantics.landing import landing_reason
from ..semantics.media import decide

CONFORMS = "http://purl.org/dc/terms/conformsTo"
NAME = "https://schema.org/name"
IDENTIFIER = "https://schema.org/identifier"
HAS_PART = "https://schema.org/hasPart"
DATASET = "https://schema.org/Dataset"
COLLECTION = "https://schema.org/Collection"
SHOWN = 8
RESTRICTED = ("RESTRICTED", "NON_PUBLIC")
OPEN_TOKENS = ("PUBLIC", "OPEN")
ACCESS_CONCEPTS = ("access_rights", "conditions_of_access", "policy")
RESOURCE_CONCEPTS = ("url", "media_type", "size", "checksum")


def declared_profiles(graph: CanonicalGraph) -> list[str]:
    """The profile IRIs the root declares by conformsTo, in order, as written."""
    root = graph.root_id()
    if root is None:
        return []
    found = []
    for value in graph.values(root, CONFORMS):
        iri = value.get("@id") if isinstance(value, dict) else value
        if isinstance(iri, str) and iri not in found:
            found.append(iri)
    return found


def merged(spec: dict, overlay: dict | None) -> tuple[dict, dict]:
    """(root fields, entity blocks) of a map with an overlay laid over it; blocks of one name are merged."""
    fields = dict(spec.get("fields", {}))
    entities = {name: dict(block, fields=dict(block.get("fields", {}))) for name, block in spec.get("entities", {}).items()}
    if overlay:
        fields.update(overlay.get("fields", {}))
        for name, block in overlay.get("entities", {}).items():
            mine = entities.setdefault(name, {"fields": {}})
            for key, value in block.items():
                if key == "fields":
                    mine["fields"].update(value)
                elif key == "type" and "type" in mine and mine["type"] != value:
                    mine["type"] = _types(mine) + [value]
                else:
                    mine[key] = value
    return fields, entities


def _types(block: dict) -> list[str]:
    """The type IRIs a block accepts: one, several, or none."""
    value = block.get("type")
    return value if isinstance(value, list) else [value] if value else []


def _has_type(graph: CanonicalGraph, node: str, block: dict) -> bool:
    """True when the node has one of the block's types, or the block names none."""
    wanted = _types(block)
    return not wanted or any(t in graph.types(node) for t in wanted)


def interpret_map(pid: str, graph: CanonicalGraph, selection: ProfileSelection,
                  maps: dict, overlay: str | None, infer_media: bool = True) -> tuple[Descriptor, list[Step], list[Step]]:
    """The description by the selected map (and overlay); steps to put before and after O1."""
    root = graph.root_id()
    if root is None or root not in graph.nodes:
        raise AccessError("object.no_root", "the metadata descriptor names no root entity")
    spec = maps[selection.selected]
    extra_map = maps[overlay] if overlay else None
    if extra_map is not None and extra_map.get("extends") not in (None, selection.selected):
        extra_map, overlay = None, None  # an overlay extends one map
    fields, blocks = merged(spec, extra_map)

    root_fields = {concept: _value(graph, root, entry) for concept, entry in fields.items()}
    identifiers = _values(graph, root, fields["identifier"]) if "identifier" in fields else []
    descriptor = Descriptor(
        pid=pid, identifier=identifiers[0] if identifiers else None, name=root_fields.get("title"),
        types=sorted(graph.types(root)), resource_type=None, description=root_fields.get("description"),
        license=root_fields.get("licence"), date=root_fields.get("date"), profile=(selection.declared or [None])[0],
        parts=[], members=[], identifiers=[i for i in identifiers if i],
        profiles=list(selection.declared), map_used=selection.selected)
    related = _related(graph, root)
    entities = _collect(graph, root, blocks, {r["id"] for r in related})
    root_access = _access(graph, root, fields)
    for entity in entities:
        entity["access"] = _entity_access(graph, entity, blocks[entity["type"]], fields, entities, root_access)
    resources = _resources(graph, entities, blocks, infer_media)
    descriptor.parts = [resource.pop("part") for resource in resources]
    descriptor.members, descriptor.members_skipped = _members(graph, root, {r["id"] for r in resources})
    descriptor.extra.update({
        "root_fields": root_fields, "access": root_access, "entities": [e for e in entities if not _is_resource(blocks[e["type"]])],
        "resources": resources, "related": related, "identity": spec.get("identity", "identifier"), "overlay": overlay,
    })
    must, should = _levels(graph, root, spec, entities)
    before = [Step("describe", "P2", "profile_selected", PASS, clip(_selection_detail(selection, overlay)))]
    after = [_levels_step(must, should)]
    return descriptor, before, after


def _text(value: object) -> str | None:
    """A value as text: a reference by its id, a literal as is."""
    if isinstance(value, dict):
        return value.get("@id")
    return None if value is None else str(value)


def _values(graph: CanonicalGraph, node: str, entry: dict) -> list:
    """The values of a concept of a node, following a path of IRIs when the entry gives one."""
    path = entry["iri"] if isinstance(entry["iri"], list) else [entry["iri"]]
    nodes = [node]
    for step in path[:-1]:
        nodes = [_text(v) for n in nodes for v in graph.values(n, step) if _text(v) in graph.nodes]
    found = [_text(v) for n in nodes for v in graph.values(n, path[-1])]
    return [v for v in found if v is not None and not (isinstance(v, str) and not v.strip())]


def _value(graph: CanonicalGraph, node: str, entry: dict):
    """One concept of a node: the first value, or every value when the entry says `many`."""
    found = _values(graph, node, entry)
    if entry.get("many"):
        return found
    return found[0] if found else None


def _related(graph: CanonicalGraph, root: str) -> list[dict]:
    """Datasets the root holds that declare another profile: records of their own, never merged."""
    mine = {_text(v) for v in graph.values(root, CONFORMS)}
    found = []
    for ref in graph.values(root, HAS_PART):
        node = _text(ref)
        if node not in graph.nodes or DATASET not in graph.types(node):
            continue
        theirs = [_text(v) for v in graph.values(node, CONFORMS)]
        if theirs and not mine.intersection(theirs):
            found.append({"id": node, "name": _first(graph, node, NAME), "profiles": theirs})
    return found


def _collect(graph: CanonicalGraph, root: str, blocks: dict, skip: set) -> list[dict]:
    """Entities of the map blocks: found by type, then reached via a property from the root or a found entity."""
    found: dict[tuple, dict] = {}
    for name, block in blocks.items():
        if "type" in block and "via" not in block:
            for node in graph.nodes:
                if node != root and node not in skip and _has_type(graph, node, block):
                    found[(name, node)] = _entity(graph, name, node, block, None)
    holders = [root] + [key[1] for key in found]
    for name, block in blocks.items():
        if "via" not in block:
            continue
        for holder in holders:
            for ref in graph.values(holder, block["via"]):
                node = _text(ref)
                if node not in graph.nodes or node in skip:
                    continue
                if not _has_type(graph, node, block):
                    continue
                entity = found.get((name, node))
                if entity is None:
                    found[(name, node)] = _entity(graph, name, node, block, holder)
                elif holder not in entity["holders"]:
                    entity["holders"].append(holder)
    return list(found.values())


def _entity(graph: CanonicalGraph, name: str, node: str, block: dict, holder: str | None) -> dict:
    """One entity: its fields by the block, the profiles it declares, and the profiles of the records it points to."""
    fields = {concept: _value(graph, node, entry) for concept, entry in block["fields"].items()}
    for concept, value in list(fields.items()):
        if isinstance(value, str) and value in graph.nodes:
            profiles = [_text(v) for v in graph.values(value, CONFORMS)]
            if profiles:
                fields[concept + "_profiles"] = profiles
    return {"id": node, "type": name, "provides": list(block.get("provides", [])), "holders": [holder] if holder else [],
            "pid": _first(graph, node, IDENTIFIER),
            "profiles": [_text(v) for v in graph.values(node, CONFORMS)], "fields": fields}


def _access(graph: CanonicalGraph, node: str, fields: dict) -> dict:
    """open, restricted or unknown from the access concepts of the map; a name never decides."""
    rights = _values(graph, node, fields["access_rights"]) if "access_rights" in fields else []
    conditions = _values(graph, node, fields["conditions_of_access"]) if "conditions_of_access" in fields else []
    policy = _values(graph, node, fields["policy"]) if "policy" in fields else []
    state = "unknown"
    if any(r.rsplit("/", 1)[-1].upper() in RESTRICTED for r in rights):
        state = "restricted"
    elif any(r.rsplit("/", 1)[-1].upper() in OPEN_TOKENS for r in rights):
        state = "open"
    return {"state": state, "rights": rights, "conditions": conditions, "policy": policy[0] if policy else None,
            "requires_authorization": {"restricted": True, "open": False}.get(state)}


def _entity_access(graph: CanonicalGraph, entity: dict, block: dict, fields: dict, entities: list, root_access: dict) -> dict:
    """An entity's own access terms; an entity that states none takes its holder's, else the root's."""
    own = _access(graph, entity["id"], fields)
    if own["rights"] or own["policy"] or own["conditions"] or "type" in block and not entity["holders"]:
        return own
    by_id = {e["id"]: e for e in entities}
    for holder in entity["holders"]:
        if holder in by_id and "access" in by_id[holder]:
            return by_id[holder]["access"]
    return root_access


def _is_resource(block: dict) -> bool:
    """True for an entity block whose entities are files or stores (role resource)."""
    return block.get("role") == "resource"


def _resources(graph: CanonicalGraph, entities: list[dict], blocks: dict, infer_media: bool) -> list[dict]:
    """Every resource entity as a plain row plus the Part the select and load steps read."""
    rows = []
    for entity in entities:
        if not _is_resource(blocks[entity["type"]]):
            continue
        f = entity["fields"]
        url = f.get("url") or entity["id"]
        in_crate = "://" not in url and ":" not in url.split("/")[0]
        landing = None if in_crate else landing_reason(url)
        size = f.get("size")
        restricted = entity["access"]["state"] == "restricted"
        media, how = decide(url, f.get("media_type"), infer_media)
        part = Part(id=entity["id"], name=_first(graph, entity["id"], NAME), media_type=media,
                    url=("in-crate:" + url) if in_crate else url, size=int(size) if str(size).isdigit() else None,
                    restricted=restricted, payload=landing is None, why_not_payload="landing page" if landing else None,
                    media_how=how, in_crate=in_crate)
        rows.append({"id": entity["id"], "type": entity["type"], "holders": entity["holders"], "pid": entity["pid"],
                     "url": part.url, "in_crate": in_crate, "media_type": media, "media_type_source": how,
                     "declared_media_type": f.get("media_type"), "size": part.size,
                     "checksum": f.get("checksum"), "payload": part.payload, "why_not_payload": part.why_not_payload,
                     "access": entity["access"], "part": part})
    return rows


def _members(graph: CanonicalGraph, root: str, resource_ids: set) -> tuple[list[str], int]:
    """PIDs a Collection root lists in hasPart, once each, and how many entries were skipped (no scheme: not a PID)."""
    if COLLECTION not in graph.types(root):
        return [], 0
    members, seen, skipped = [], set(), 0
    for ref in graph.values(root, HAS_PART):
        iri = _text(ref)
        if iri is None or iri in resource_ids:
            continue
        if not has_scheme(iri):
            skipped += 1
            continue
        if iri.rstrip("/") in seen:
            continue
        seen.add(iri.rstrip("/"))
        members.append(iri)
    return members, skipped


def _first(graph: CanonicalGraph, node: str, iri: str):
    """The first value of a property as text."""
    values = graph.values(node, iri)
    return _text(values[0]) if values else None


def _levels(graph: CanonicalGraph, root: str, spec: dict, entities: list[dict]) -> tuple[list, list]:
    """(must absent, should absent) by the map alone: root fields, each entity present, entity blocks, map rules."""
    must, should = [], []

    def note(level: str, text: str) -> None:
        """Put an absent term on the list of its level."""
        (must if level == "must" else should if level == "should" else []).append(text)

    for concept, entry in spec.get("fields", {}).items():
        if not _values(graph, root, entry):
            note(entry["level"], f"{concept} <{entry['iri']}>")
    blocks = spec.get("entities", {})
    for entity in entities:
        block = blocks.get(entity["type"])
        if block is None:
            continue
        for concept, entry in block.get("fields", {}).items():
            if entity["fields"].get(concept) in (None, "", []):
                note(entry["level"], f"{entity['type']} {entity['id']}: {concept}")
    for name, block in blocks.items():
        if block.get("level") and not any(e["type"] == name for e in entities):
            note(block["level"], f"{name}: none stated")
    for rule in spec.get("rules", []):
        text = _broken_rule(graph, root, spec, rule, entities)
        if text:
            must.append(text)
    return must, should


def _broken_rule(graph: CanonicalGraph, root: str, spec: dict, rule: dict, entities: list[dict]) -> str | None:
    """The text of a map rule the object breaks; None when it holds or does not apply."""
    field = spec["fields"][rule["when"]["field"]]
    if rule["when"]["equals"] not in _values(graph, root, field):
        return None
    need = rule["require"]
    if "entity" in need and sum(e["type"] == need["entity"] for e in entities) < need.get("min", 1):
        return f"rule: {rule['reason']}"
    if "field" in need and not _values(graph, root, spec["fields"][need["field"]]):
        return f"rule: {rule['reason']}"
    return None


def _levels_step(must: list[str], should: list[str]) -> Step:
    """V0: presence of the map's terms by level; built in, not the profile's own validator."""
    if not must and not should:
        return Step("validate", "V0", "levels_present", PASS, "every term of the map is stated")
    parts = []
    if must:
        parts.append("must absent: " + _shown(must))
    if should:
        parts.append("should absent: " + _shown(should))
    return Step("validate", "V0", "levels_present", FAIL if must else PARTIAL, clip("; ".join(parts)))


def _shown(items: list[str]) -> str:
    """At most SHOWN items, then a count."""
    text = "; ".join(items[:SHOWN])
    return text + (f"; and {len(items) - SHOWN} more" if len(items) > SHOWN else "")


def _selection_detail(selection: ProfileSelection, overlay: str | None) -> str:
    """One line: the map used, why, and the spelling of the profile IRI the crate carried."""
    text = f"{selection.selected} ({selection.reason})"
    if selection.spelling:
        text += f"; declared as {selection.spelling}"
    if overlay:
        text += f"; overlay {overlay}"
    return text
