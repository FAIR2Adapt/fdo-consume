"""Shape hints: what the vocabulary of an object suggests about where it came from."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from ..core import CanonicalGraph

SHAPE_FILE = Path(__file__).resolve().parent / "data" / "shape-hints.yaml"


@lru_cache(maxsize=1)
def _rules() -> list[dict]:
    """The namespace rules, read once."""
    return yaml.safe_load(SHAPE_FILE.read_text(encoding="utf-8"))["namespaces"]


def hints(graph: CanonicalGraph) -> list[dict]:
    """One hint per pre-profile namespace found among the types and properties of the graph."""
    seen = set()
    for node, props in graph.nodes.items():
        for key, values in props.items():
            if key == "@type":
                seen.update(values)
            else:
                seen.add(key)
    found = []
    for rule in _rules():
        wanted = set(rule.get("terms", []))
        matched = sorted(s for s in seen if isinstance(s, str) and (s in wanted if wanted else s.startswith(rule["prefix"])))
        if matched:
            found.append({"namespace": rule["prefix"], "terms": matched[:8], "hint": rule["hint"]})
    return found
