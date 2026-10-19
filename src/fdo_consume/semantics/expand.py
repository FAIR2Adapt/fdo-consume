"""JSON-LD expansion of a crate into the canonical graph, through pyld with bundled contexts and no network."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote, unquote

from pyld import jsonld

from ..core import CanonicalGraph, has_scheme

TERMS_FILE = Path(__file__).resolve().parent / "data" / "ro-crate-terms.json"
# A relative @id is made absolute under this base, percent-encoded, before expansion and decoded afterwards: pyld then
# neither resolves nor normalises it ("./a.fgb" would become "a.fgb", "../" the root), so ids stay as the crate spells
# them while remote ids stay absolute.
BASE = "crate:/"
# Values of these containers and of @json-typed terms are not node objects; their keys are not terms.
OPAQUE_CONTAINERS = ("@language", "@index", "@id", "@type")


@lru_cache(maxsize=1)
def known_contexts() -> dict:
    """The bundled RO-Crate contexts: URL to term table."""
    return json.loads(TERMS_FILE.read_text(encoding="utf-8"))["contexts"]


def canonical_context_url(url: str) -> str:
    """The bundled spelling of a context URL: https, no trailing slash."""
    text = url.strip().rstrip("/")
    if text.startswith("http://"):
        text = "https://" + text[len("http://"):]
    return text


def expand(crate: object) -> CanonicalGraph:
    """The crate's nodes with every key, @type and @id-typed value as an expanded IRI."""
    graph = CanonicalGraph()
    nodes = _top_nodes(crate, graph)
    if nodes is None:
        return graph
    context = crate.get("@context") if isinstance(crate, dict) else None
    if context is None or not isinstance(context, (str, list, dict)):
        detail = "the document has no @context" if context is None else f"a {type(context).__name__} as @context"
        graph.problems.append({"code": "context_unusable", "detail": detail})
        _add_raw_nodes(graph, nodes)
        return graph
    loader = _Loader()
    options = {"documentLoader": loader, "base": BASE}
    try:
        marked = _marked(crate)
        expanded = _expand_document(marked, context, _top_nodes(marked, CanonicalGraph()) or [], options, graph.problems)
    except RecursionError:
        graph.problems.append({"code": "document_invalid", "detail": "the document is nested too deeply to expand"})
        return graph
    graph.contexts = loader.known
    graph.unknown_contexts = loader.unknown
    if expanded is None:
        return graph
    graph.available = _available(context, loader)
    if not graph.available:
        graph.problems.append({"code": "context_unusable", "detail": "no usable @context"})
        return graph
    # The node map is built here rather than by jsonld.flatten: flatten checks every value it adds against the values
    # already present, which is quadratic on a root that lists thousands of parts.
    nodes_map = _NodeMap(graph)
    for item in expanded:
        nodes_map.add(item)
    graph.unknown_terms = sorted(_unknown_terms(nodes, context, loader.known))
    return graph


def _expand_document(crate: object, context: object, nodes: list, options: dict, problems: list) -> list | None:
    """The expanded nodes; a broken context ends the read (None), a broken node is left out and listed."""
    try:
        return jsonld.expand(crate, options)
    except jsonld.JsonLdError as error:
        first = error
    try:
        jsonld.expand({"@context": context, "@graph": []}, options)
    except jsonld.JsonLdError as error:
        problems.append({"code": "context_unusable", "detail": _error_text(error)})
        return None
    expanded = _expand_tolerant(context, nodes, options, problems)
    if not problems:   # the failure was not in one node either: report it as it came
        problems.append({"code": "document_invalid", "detail": _error_text(first)})
    return expanded


def _expand_tolerant(context: object, nodes: list, options: dict, problems: list) -> list:
    """Expand the nodes in halves until each broken node is isolated and listed with pyld's reason."""
    try:
        return jsonld.expand({"@context": context, "@graph": nodes}, options)
    except jsonld.JsonLdError as error:
        if len(nodes) <= 1:
            node_id = nodes[0].get("@id") if nodes else None
            label = node_id if isinstance(node_id, str) else "a node without a usable @id"
            problems.append({"code": "node_invalid", "detail": f"{label}: {_error_text(error)}"})
            return []
        half = len(nodes) // 2
        return (_expand_tolerant(context, nodes[:half], options, problems)
                + _expand_tolerant(context, nodes[half:], options, problems))


def _top_nodes(crate: object, graph: CanonicalGraph) -> list | None:
    """The node objects of the document, or None and a problem when the input is not a JSON-LD document."""
    if isinstance(crate, dict):
        if "@graph" in crate and isinstance(crate["@graph"], list):
            return [item for item in crate["@graph"] if isinstance(item, dict)]
        if "@graph" in crate:
            graph.problems.append({"code": "graph_not_a_list", "detail": "@graph is not a list"})
            return None
        return [crate]
    if isinstance(crate, list):
        return [item for item in crate if isinstance(item, dict)]
    graph.problems.append({"code": "not_a_document", "detail": f"a {type(crate).__name__}, not an object"})
    return None


class _Loader:
    """Document loader for pyld: bundled contexts are served, any other URL yields an empty context and is listed."""

    def __init__(self) -> None:
        self.known: list[str] = []
        self.unknown: list[str] = []

    def __call__(self, url: str, options: dict | None = None) -> dict:
        canonical = canonical_context_url(url)
        table = known_contexts().get(canonical)
        if table is not None:
            if canonical not in self.known:
                self.known.append(canonical)
            return {"contextUrl": None, "documentUrl": url, "document": {"@context": table}}
        if url not in self.unknown:
            self.unknown.append(url)
        return {"contextUrl": None, "documentUrl": url, "document": {"@context": {}}}


def _available(context: object, loader: _Loader) -> bool:
    """True when terms are in force at the end of the top-level context: a bundled URL or inline definitions after the
    last null entry (null clears every term); a known context named by a node counts as well."""
    in_force = context if isinstance(context, list) else [context]
    if None in in_force:
        in_force = in_force[len(in_force) - in_force[::-1].index(None):]
    top_known = [c for c in in_force if isinstance(c, str) and canonical_context_url(c) in known_contexts()]
    if top_known or _has_inline_terms(in_force):
        return True
    top_urls = {canonical_context_url(c) for c in (context if isinstance(context, list) else [context]) if isinstance(c, str)}
    return any(url not in top_urls for url in loader.known)


def _error_text(error: BaseException) -> str:
    """The innermost pyld message with its error code; the outer error only says that expansion failed."""
    cause = error
    while getattr(cause, "__cause__", None) is not None:
        cause = cause.__cause__
    text = str(cause.args[0]) if cause.args else type(cause).__name__
    code = getattr(cause, "code", None)
    return f"{code}: {text}" if code else text


def _has_inline_terms(context: object) -> bool:
    """True when the @context defines terms inline (a mapping, possibly inside a list)."""
    if isinstance(context, dict):
        return any(not key.startswith("@") or key == "@vocab" for key in context)
    if isinstance(context, list):
        return any(_has_inline_terms(item) for item in context)
    return False


def _marked(value: object) -> object:
    """A copy of the document in which every relative @id is absolute under BASE and percent-encoded."""
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if key == "@id" and isinstance(item, str) and not has_scheme(item):
                out[key] = BASE + quote(item, safe="")
            elif key == "@context":
                out[key] = item
            else:
                out[key] = _marked(item)
        return out
    if isinstance(value, list):
        return [_marked(item) for item in value]
    return value


def _local(node_id: str) -> str:
    """A node id as the crate spells it: the base removed and the encoding undone; an empty remainder is the root."""
    if node_id.startswith(BASE):
        rest = unquote(node_id[len(BASE):])
        return rest if rest else "./"
    return node_id


class _NodeMap:
    """Expanded node objects into graph.nodes: one entry per id, embedded nodes added and referenced, values deduplicated."""

    def __init__(self, graph: CanonicalGraph) -> None:
        self.graph = graph
        self.blank = 0

    def add(self, item: dict) -> str | None:
        """Add one node object and return its id; an unnamed graph wrapper adds its nodes and returns None."""
        if "@graph" in item and "@id" not in item:
            for node in item["@graph"]:
                if isinstance(node, dict):
                    self.add(node)
            return None
        node_id = item.get("@id")
        if not isinstance(node_id, str):
            node_id = f"_:b{self.blank}"
            self.blank += 1
        node_id = _local(node_id)
        target = self.graph.nodes.setdefault(node_id, {})
        for key, value in item.items():
            if key == "@id":
                continue
            if key == "@type":
                _append(target, "@type", [_local(text) for text in value if isinstance(text, str)])
                continue
            if key == "@included":
                for node in value if isinstance(value, list) else [value]:
                    if isinstance(node, dict):
                        self.add(node)
                continue
            if key.startswith("@"):
                continue
            _append(target, _local(key), self.values(value))
        return node_id

    def values(self, value: object) -> list:
        """Expanded values as {"@id": ...} references or plain literals; lists are flattened in order."""
        found = []
        for item in value if isinstance(value, list) else [value]:
            if isinstance(item, dict):
                if "@list" in item:
                    found.extend(self.values(item["@list"]))
                elif "@value" in item:
                    found.append(item["@value"])
                elif "@id" in item and len(item) == 1:
                    found.append({"@id": _local(item["@id"]) if isinstance(item["@id"], str) else item["@id"]})
                else:
                    reference = self.add(item)
                    if reference is not None:
                        found.append({"@id": reference})
            elif item is not None:
                found.append(item)
        return found


def _append(target: dict, key: str, items: list) -> None:
    """Add values to a property once each, in order."""
    existing = target.setdefault(key, [])
    seen = {json.dumps(v, sort_keys=True, default=str) for v in existing}
    for value in items:
        marker = json.dumps(value, sort_keys=True, default=str)
        if marker not in seen:
            seen.add(marker)
            existing.append(value)


def _add_raw_nodes(graph: CanonicalGraph, nodes: list) -> None:
    """Without a usable context the terms stay as written, so a record can still list what the document holds."""
    unknown: set[str] = set()
    blank = 0

    def node(item: dict) -> str:
        nonlocal blank
        node_id = item.get("@id")
        if not isinstance(node_id, str):
            node_id = f"_:b{blank}"
            blank += 1
        if len(item) == 1 and "@id" in item:
            return node_id
        target = graph.nodes.setdefault(node_id, {})
        for key, value in item.items():
            if key in ("@id", "@context"):
                continue
            items = value if isinstance(value, list) else [value]
            if key == "@type":
                found = [text for text in items if isinstance(text, str)]
                unknown.update(text for text in found if not has_scheme(text))
                target.setdefault("@type", []).extend(found)
                continue
            if key.startswith("@"):
                continue
            if not has_scheme(key):
                unknown.add(key)
            target.setdefault(key, []).extend({"@id": node(v)} if isinstance(v, dict) and "@value" not in v else v.get("@value") if isinstance(v, dict) else v
                                              for v in items if v is not None)
        return node_id

    for item in nodes:
        node(item)
    graph.unknown_terms = sorted(unknown)


def _unknown_terms(nodes: list, context: object, known: list[str]) -> set[str]:
    """Keys and @type values that no context in force defines; pyld drops them silently, the record lists them."""
    defined: set[str] = set()
    opaque: set[str] = set()
    vocab = False
    for url in known:
        defined.update(known_contexts()[url])
    for inline in _inline_contexts(context, nodes):
        if inline.get("@vocab"):
            vocab = True
        for key, definition in inline.items():
            if key.startswith("@"):
                continue
            defined.add(key)
            if isinstance(definition, dict) and (definition.get("@type") == "@json" or definition.get("@container") in OPAQUE_CONTAINERS):
                opaque.add(key)
    if vocab:
        return set()
    unknown: set[str] = set()
    for item in nodes:
        _collect_unknown(item, defined, opaque, unknown)
    return unknown


def _inline_contexts(context: object, nodes: list) -> list[dict]:
    """Every inline context mapping: top level, node level, and the scoped contexts inside term definitions."""
    found = []

    def take(value: object) -> None:
        if isinstance(value, dict):
            found.append(value)
            for definition in value.values():
                if isinstance(definition, dict) and "@context" in definition:
                    take(definition["@context"])
        elif isinstance(value, list):
            for item in value:
                take(item)

    take(context)
    for item in nodes:
        take(item.get("@context"))
    return found


def _collect_unknown(item: dict, defined: set[str], opaque: set[str], unknown: set[str]) -> None:
    for key, value in item.items():
        if key.startswith("@"):
            if key == "@type":
                for text in value if isinstance(value, list) else [value]:
                    if isinstance(text, str) and not has_scheme(text) and text not in defined:
                        unknown.add(text)
            continue
        if not has_scheme(key) and key not in defined:
            unknown.add(key)
        if key in opaque:
            continue
        for nested in value if isinstance(value, list) else [value]:
            if isinstance(nested, dict) and "@value" not in nested:
                _collect_unknown(nested, defined, opaque, unknown)
