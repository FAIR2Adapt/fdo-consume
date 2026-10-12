"""JSON-LD terms to canonical IRIs, for the subset RO-Crate crates use."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from ..core import CanonicalGraph, has_scheme

TERMS_FILE = Path(__file__).resolve().parent / "data" / "ro-crate-terms.json"
KEYWORDS = ("@context", "@id", "@type", "@graph", "@value", "@language", "@list", "@set", "@reverse")
DEFINITION_KEYS = ("@id", "@type", "@container", "@context", "@reverse", "@language", "@prefix",
                   "@protected", "@nest", "@index")
GEN_DELIMS = ("/", "#", ":", "?", "@", "[", "]")


@lru_cache(maxsize=1)
def known_contexts() -> dict:
    """The vendored RO-Crate contexts: URL to term table."""
    return json.loads(TERMS_FILE.read_text(encoding="utf-8"))["contexts"]


def expand(crate: object) -> CanonicalGraph:
    """The crate's nodes with every key, @type and @id-typed value as an expanded IRI."""
    graph = CanonicalGraph()
    nodes = _top_nodes(crate, graph)
    if nodes is None:
        return graph
    scope = _Scope(graph)
    scope.read(crate.get("@context") if isinstance(crate, dict) else None)
    graph.contexts = scope.used
    graph.available = scope.usable()
    if not graph.available:
        graph.problems.append({"code": "context_unusable", "detail": scope.why_not or "no usable @context"})
    builder = _Builder(scope, graph)
    for node in nodes:
        builder.node(node)
    graph.unknown_terms = sorted(builder.unknown)
    return graph


def _top_nodes(crate: object, graph: CanonicalGraph) -> list | None:
    """Return the crate nodes, or None and a problem when the input is not a JSON-LD document."""
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


class _Scope:
    """The term definitions, prefixes, @vocab and @base in force for the document."""

    def __init__(self, graph: CanonicalGraph):
        self.graph = graph
        self.terms: dict[str, object] = {}
        self.vocab: str | None = None
        self.base: str | None = None
        self.used: list[str] = []
        self.known_seen = False
        self.why_not: str | None = None

    def usable(self) -> bool:
        """True when at least one context gave term definitions."""
        return bool(self.terms)

    def read(self, context: object) -> None:
        """Take in a context: a URL, an object, or a list of them, in order."""
        if context is None:
            self.why_not = "the document has no @context"
            return
        if isinstance(context, list):
            for item in context:
                self.read(item)
            return
        if isinstance(context, str):
            self._remote(context)
            return
        if isinstance(context, dict):
            self._definitions(context)
            return
        self.graph.problems.append({"code": "context_not_usable", "detail": f"a {type(context).__name__} as @context"})

    def _remote(self, url: str) -> None:
        """A context given by URL: only the vendored ones are known; others are evidence."""
        table = known_contexts().get(url.rstrip("/"))
        if table is None:
            self.graph.unknown_contexts.append(url)
            self.why_not = self.why_not or f"unknown remote context: {url}"
            return
        self.used.append(url)
        self.known_seen = True
        for key, value in table.items():
            self.terms[key] = value

    def _definitions(self, context: dict) -> None:
        """Inline term definitions; a null value removes a term."""
        for key, value in context.items():
            if key == "@vocab":
                self.vocab = value if isinstance(value, str) else None
            elif key == "@base":
                self.base = value if isinstance(value, str) else None
            elif key in ("@language", "@version", "@protected", "@propagate", "@import"):
                continue
            elif value is None:
                self.terms.pop(key, None)
            else:
                if isinstance(value, dict) and "@context" in value:
                    self.graph.problems.append({"code": "scoped_context_ignored", "detail": f"term {key} has its own @context"})
                self.terms[key] = value

    def definition(self, term: str) -> tuple[str | None, str | None]:
        """(id, coercion) of a defined term; the id as written, not yet expanded."""
        entry = self.terms.get(term)
        if entry is None:
            return None, None
        if isinstance(entry, str):
            return entry, None
        if isinstance(entry, dict):
            return entry.get("@id"), entry.get("@type")
        return None, None

    def iri(self, text: str, vocab: bool) -> str | None:
        """A term, compact IRI or absolute IRI as a full IRI; None when it cannot be."""
        for _ in range(8):
            if not vocab:
                break
            target, _coercion = self.definition(text)
            if target is None or target == text:
                break
            text = target
        if self._is_prefixed(text):
            prefix, _, suffix = text.partition(":")
            base, _coercion = self.definition(prefix)
            full = self.iri(base, True)
            return full + suffix if full else None
        if has_scheme(text):
            return text
        if vocab and self.vocab is not None:
            return self.vocab + text
        return None

    def _is_prefixed(self, text: str) -> bool:
        """Return True for a compact IRI whose prefix is defined and whose suffix is not an authority component."""
        prefix, colon, suffix = text.partition(":")
        if not colon or suffix.startswith("//"):
            return False
        target, _coercion = self.definition(prefix)
        return isinstance(target, str) and target.endswith(GEN_DELIMS)


class _Builder:
    """Turns node objects into canonical nodes, one property at a time."""

    def __init__(self, scope: _Scope, graph: CanonicalGraph):
        self.scope = scope
        self.graph = graph
        self.unknown: set[str] = set()
        self.blank = 0

    def node(self, item: dict) -> str:
        """Add one node object; return its id (a blank id when it has none)."""
        node_id = item.get("@id")
        if isinstance(node_id, str):
            node_id = self.node_id(node_id)
        else:
            self.blank += 1
            node_id = f"_:b{self.blank}"
        target = self.graph.nodes.setdefault(node_id, {})
        for key, value in item.items():
            if key == "@id" or key == "@context":
                continue
            if key == "@type":
                found = [self.type_iri(text) for text in _as_list(value) if isinstance(text, str)]
                target.setdefault("@type", []).extend(found)
                continue
            if key.startswith("@"):
                continue
            iri = self.scope.iri(key, True)
            if iri is None or not _is_iri(iri):
                self.unknown.add(key)
                iri = key
            _definition, coercion = self.scope.definition(key)
            target.setdefault(iri, []).extend(self.values(value, coercion))
        return node_id

    def node_id(self, text: str) -> str:
        """An @id as written, with a compact IRI expanded; relative ids stay relative."""
        if self.scope._is_prefixed(text):
            return self.scope.iri(text, False) or text
        return text

    def type_iri(self, text: str) -> str:
        """An @type value as an IRI; one that cannot be expanded stays as written and is listed."""
        iri = self.scope.iri(text, True)
        if iri is None or not _is_iri(iri):
            self.unknown.add(text)
            return text
        return iri

    def values(self, value: object, coercion: str | None) -> list:
        """The values of a property as {"@id": ...} references or plain literals."""
        found = []
        for item in _as_list(value):
            if isinstance(item, dict):
                if "@list" in item or "@set" in item:
                    found.extend(self.values(item.get("@list", item.get("@set")), coercion))
                elif "@value" in item:
                    found.append(item["@value"])
                elif "@id" in item and len(item) == 1:
                    found.append({"@id": self.node_id(item["@id"]) if isinstance(item["@id"], str) else item["@id"]})
                else:
                    found.append({"@id": self.node(item)})
            elif isinstance(item, str) and coercion == "@id":
                found.append({"@id": self.node_id(item)})
            elif isinstance(item, str) and coercion == "@vocab":
                found.append({"@id": self.scope.iri(item, True) or item})
            elif item is not None:
                found.append(item)
        return found


def _as_list(value: object) -> list:
    """A value as a list; a list stays, anything else becomes a list of one."""
    return value if isinstance(value, list) else [value]


def _is_iri(text: str) -> bool:
    """True for text with a scheme, as an expanded IRI has."""
    return has_scheme(text)
