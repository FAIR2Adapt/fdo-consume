"""The consumer contract: what one named consumer needs, and where each need comes from."""
from __future__ import annotations

from collections.abc import Mapping

LEVELS = ("must", "should")
ROOT_ATTRIBUTES = {"title": "name", "licence": "license", "date": "date", "description": "description",
                   "identifier": "identifier"}
ALIASES = {"name": "title", "license": "licence"}
NEW_KEYS = ("contract_id", "version", "consumer", "source", "needs", "accepts", "profile",
            "profile_additions", "description")


def is_new_form(spec: Mapping) -> bool:
    """True for a contract written with `needs`, the form of a production contract."""
    return "needs" in spec


def as_internal(spec: Mapping) -> dict:
    """A needs-form contract as the must, should and accepts lists the match step reads."""
    internal = {"contract_id": spec.get("contract_id"), "consumer": _consumer_name(spec.get("consumer")),
                "must": [n["term"] for n in spec["needs"] if n["level"] == "must"],
                "should": [n["term"] for n in spec["needs"] if n["level"] == "should"]}
    for key in ("accepts", "profile", "profile_additions", "description"):
        if key in spec:
            internal[key] = spec[key]
    internal["needs"] = [dict(n) for n in spec["needs"]]
    return internal


def _consumer_name(consumer: object) -> str:
    """The consumer as one line: service and capability."""
    if isinstance(consumer, Mapping):
        return f"{consumer.get('service')}: {consumer.get('capability')}"
    return str(consumer)
