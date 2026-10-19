"""Public API: consume one object, several contracts, or a collection; results carry the binding and the record."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from . import registry
from .core import DIMENSIONS, AccessError, AccessRecord, Limits, refuse_large_crate
from .pipeline.access import access

@dataclass
class ConsumptionResult:
    """One object read for one contract: the record and the binding (None when not usable)."""

    record: AccessRecord
    binding: dict | None

    @property
    def is_usable(self) -> bool:
        """Resolved, compatible with the contract (PASS or PARTIAL) and a binding delivered; an object whose terms could
        not be expanded (resolution INDETERMINATE) is not usable, whatever the fallback reader found in its raw keys."""
        return (self.record.outcome == "ok" and self.record.resolution["status"] in ("PASS", "PARTIAL")
                and self.record.compatibility["status"] in ("PASS", "PARTIAL") and self.binding is not None)

    @property
    def statuses(self) -> dict:
        """Status of resolution, validation, compatibility and delivery."""
        return {name: getattr(self.record, name)["status"] for name in DIMENSIONS}

    @property
    def diagnostics(self) -> list[dict]:
        """Every FAIL, PARTIAL or INDETERMINATE step and any error that ended the run."""
        return [{"stage": d["stage"], "code": d["code"], "status": d["status"], "message": d["detail"]}
                for d in self.record.diagnostics]

    @property
    def notes(self) -> list[dict]:
        """Structured notes of passed steps, e.g. a should-term the profile does not define."""
        return [dict(note, stage=s.stage, step=s.id) for s in self.record.steps for note in s.notes]

    def summary(self) -> dict:
        """Plain dict for logs or a UI: contract, usability, statuses, diagnostics, notes, hashes."""
        return {"contract": self.record.contract_id, "is_usable": self.is_usable, "outcome": self.record.outcome,
                "stopped": self.record.stopped, "error": self.record.error, "statuses": self.statuses,
                "diagnostics": self.diagnostics, "notes": self.notes, "record_sha256": self.record.record_sha256,
                "contract_sha256": self.record.contract_sha256, "package_version": self.record.package_version}


@dataclass
class CollectionConsumptionResult:
    """A collection read for one contract: the collection's own record and one result per member."""

    collection_record: AccessRecord
    members: dict = field(default_factory=dict)

    @property
    def member_ids(self) -> list[str]:
        """Member PIDs the collection states, in its order, within the limits."""
        return list(self.members)

    @property
    def usable_member_ids(self) -> list[str]:
        """Members the contract accepts."""
        return [pid for pid, c in self.members.items() if c.is_usable]

    def summary(self) -> dict:
        """The collection's statuses and, per member, its summary."""
        own = {name: getattr(self.collection_record, name)["status"] for name in DIMENSIONS}
        return {"collection": self.collection_record.request["pid"], "stopped": self.collection_record.stopped,
                "statuses": own, "members_total": (self.collection_record.descriptor or {}).get("members_total", 0),
                "members": {pid: c.summary() for pid, c in self.members.items()}}


def consume(pid: str, contract: str | Mapping, *, contracts: str | None = None, profile_maps: str | None = None,
            source: str = "recorded", recorded_dir: str | None = None, profile_overlay: str | None = None,
            limits: Limits | None = None, log_path: str | None = None, infer_media_type: bool = True,
            profile: str | None = None, **internal: object) -> ConsumptionResult:
    """Read the object at `pid` for the consumer described by `contract`."""
    snapshot = internal.pop("_snapshot", None)          # a Located shared by consume_for_contracts
    if internal:
        raise TypeError(f"consume() got unexpected keyword arguments: {sorted(internal)}")
    record = access(pid, contract=contract, depth="load", want="binding", source=source, fixtures=recorded_dir,
                    contracts=contracts, profile_maps=profile_maps, overlay=profile_overlay, limits=limits,
                    log=log_path, infer_media=infer_media_type, profile=profile, snapshot=snapshot)
    return ConsumptionResult(record, record.value if isinstance(record.value, dict) else None)


def describe(pid: str, *, source: str = "recorded", recorded_dir: str | None = None, profile_maps: str | None = None,
             profile_overlay: str | None = None, profile: str | None = None, limits: Limits | None = None,
             infer_media_type: bool = True, log_path: str | None = None) -> AccessRecord:
    """Read the object at `pid` through its profile map, without a consumer contract. The record's descriptor holds the
    root fields, the entities and the declared resources; resolution and validation are judged, compatibility is not."""
    return access(pid, depth="describe", source=source, fixtures=recorded_dir, profile_maps=profile_maps, overlay=profile_overlay,
                  limits=limits, log=log_path, infer_media=infer_media_type, profile=profile)


def _snapshot(pid: str, options: dict):
    """Locate `pid` once; None when the locator raises (each contract then reports the error)."""
    if not isinstance(pid, str):
        return None
    try:
        locator = registry.get("locator", options.get("source", "recorded"))
        located = locator(pid.strip(), {"fixtures": options.get("recorded_dir")}, options.get("limits") or Limits())
        refuse_large_crate(located.size, options.get("limits") or Limits())
        return located
    except (AccessError, KeyError):
        return None


def consume_for_contracts(pid: str, contracts_wanted: Sequence[str | Mapping], **options: object) -> dict:
    """One object, located once, against several contracts: {contract id: ConsumptionResult}, in order."""
    pinned = _snapshot(pid, options) if isinstance(pid, str) else None
    found = {}
    for contract in contracts_wanted:
        key = contract if isinstance(contract, str) else str(contract.get("contract_id", len(found)))
        found[key] = consume(pid, contract, **options, **({"_snapshot": pinned} if pinned is not None else {}))
    return found


def consume_collection(pid: str, contract: str | Mapping, **options: object) -> CollectionConsumptionResult:
    """The collection at `pid` and every member it lists, each consumed for `contract`."""
    low = {"recorded_dir": "fixtures", "profile_overlay": "overlay", "infer_media_type": "infer_media"}
    own_options = {low.get(k, k): v for k, v in options.items()
                   if k in ("source", "recorded_dir", "profile_maps", "limits", "profile_overlay", "infer_media_type",
                            "profile")}
    own = access(pid, depth="describe", **own_options)
    members = {}
    if own.descriptor is not None:
        listed = own.descriptor["members"]
        if own.descriptor["members_total"] > len(listed):
            own.stopped = f"members capped at {len(listed)} of {own.descriptor['members_total']} (limits.max_members)"
        elif own.descriptor["members_total"] == 0:
            own.stopped = "the object lists no members"
        for member in listed:
            members[member] = consume(member, contract, **options)
    return CollectionConsumptionResult(own, members)
