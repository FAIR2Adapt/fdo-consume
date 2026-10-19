"""Loader "binding": one plain JSON any consumer can read, built only from what the record holds."""
from __future__ import annotations

from ..core import Descriptor, Part
from ..profiles import load_maps

SCHEMA = "fdo-consume-binding/5"
SCHEMA_FILE = "binding.schema.json"
ACCESS_VALUES = ("open", "restricted", "unknown")


def build_binding(descriptor: Descriptor, record, spec: dict | None, selected: Part | None) -> dict:
    """The binding of one object."""
    accepts = [media.split(";")[0].strip().lower() for media in (spec or {}).get("accepts", [])]
    extra = descriptor.extra
    known = {iri.rstrip("/") for m in load_maps(extra.get("profile_maps")).values() for iri in m.get("selects", [])}
    resources = []
    for row in extra.get("resources", None) if "resources" in extra else _rows_from_parts(descriptor):
        media = (row["media_type"] or "").split(";")[0].strip().lower()
        resources.append({key: row[key] for key in ("id", "type", "holders", "pid", "url", "in_crate", "media_type",
                                                    "media_type_source", "declared_media_type", "size", "checksum",
                                                    "payload", "why_not_payload", "access")}
                         | {"name": row.get("name"), "fields": dict(row.get("fields") or {}),
                            "accepted": bool(row["payload"] and media and media in accepts)})
    inferred = [r["id"] for r in resources if r["accepted"] and r["media_type_source"] and r["media_type_source"] != "declared"]
    return {
        "schema": SCHEMA,
        "object": {"pid": descriptor.pid, "identifier": descriptor.identifier, "crate_sha256": record.crate_sha256,
                   "name": descriptor.name, "description": descriptor.description, "date": descriptor.date,
                   "licence": descriptor.license, "profiles": descriptor.profiles, "map": descriptor.map_used,
                   "overlay": extra.get("overlay"), "fields": extra.get("root_fields", {}),
                   "access": extra.get("access", _unknown())},
        "consumer": {"contract": record.contract_id, "compatibility": record.compatibility},
        "entities": [dict(e) for e in extra.get("entities", [])],
        "resources": resources,
        "selected": [selected.id] if selected else [],
        "related": [dict(r, has_map=any(p.rstrip("/") in known for p in r["profiles"])) for r in extra.get("related", [])],
        "evidence": {"statuses": {name: getattr(record, name)["status"]
                                 for name in ("resolution", "validation", "compatibility", "delivery")},
                     "inference_used": inferred, "shape_hints": (record.semantics or {}).get("shape_hints", []),
                     "steps": [{"id": s.id, "status": s.status, "detail": s.detail} for s in record.steps if s.status != "PASS"]},
    }


def _rows_from_parts(descriptor: Descriptor) -> list[dict]:
    """Resource rows for an object read by the fallback describer (no profile map)."""
    rows = []
    for part in descriptor.parts:
        state = part.access if part.access in ACCESS_VALUES else ("restricted" if part.restricted else "unknown")
        rows.append({"id": part.id, "type": "File", "holders": [], "pid": None, "url": part.url, "in_crate": part.in_crate,
                     "media_type": part.media_type, "media_type_source": part.media_how,
                     "declared_media_type": part.declared_media_type, "size": part.size, "checksum": None,
                     "payload": part.payload, "why_not_payload": part.why_not_payload,
                     "access": {"state": state, "rights": [], "conditions": [], "policy": None,
                                "requires_authorization": {"restricted": True, "open": False}.get(state)}})
    return rows


def _unknown() -> dict:
    """Return unknown access metadata."""
    return {"state": "unknown", "rights": [], "conditions": [], "policy": None, "requires_authorization": None}


def refresh_evidence(binding: dict, record) -> None:
    """Called when the record is sealed: statuses and compatibility are final only then."""
    binding["consumer"]["compatibility"] = record.compatibility
    binding["evidence"]["statuses"] = {name: getattr(record, name)["status"]
                                      for name in ("resolution", "validation", "compatibility", "delivery")}
    binding["evidence"]["steps"] = [{"id": s.id, "status": s.status, "detail": s.detail} for s in record.steps if s.status != "PASS"]
