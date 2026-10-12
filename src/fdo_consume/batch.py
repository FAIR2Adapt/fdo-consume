"""Batch: many PIDs and collections, each through access()."""
from __future__ import annotations

from collections import OrderedDict
from collections.abc import Iterable, Iterator

from .core import DIMENSIONS, DIMENSION_STATUSES, OUTCOMES, record_hash
from .pipeline.access import _log, access


MEMO_SIZE = 1000


# sequential processing; resume is not supported
def iter_access(pids: Iterable[str], **options: object) -> Iterator[dict]:
    """One record dict per PID, in input order; a repeated PID is accessed once while it is among the last MEMO_SIZE."""
    if isinstance(pids, str):
        pids = [pids]
    done: OrderedDict = OrderedDict()
    for pid in pids:
        if not isinstance(pid, str):
            yield access(pid, **options).to_dict()
            continue
        asked = pid.strip()
        if asked not in done:
            done[asked] = access(asked, **options).to_dict()
            if len(done) > MEMO_SIZE:
                done.popitem(last=False)
        yield done[asked]


def access_many(pids: Iterable[str], **options: object) -> dict:
    """The records of `iter_access` as a list, with a summary."""
    records = list(iter_access(pids, **options))
    return {"records": records, "summary": _summary(records)}


def access_collection(pid: str, **options: object) -> dict:
    """Describe the collection at `pid`; access the members it lists, capped."""
    head = access(pid, **dict(options, depth="describe", log=None))
    members = []
    total = 0
    skipped = 0
    if head.descriptor is not None:
        members = head.descriptor["members"]
        total = head.descriptor["members_total"]
        skipped = head.descriptor["members_skipped"]
    if total > len(members):
        _stop_head(head, f"members capped at {len(members)} of {total} (limits.max_members)")
    if head.descriptor is not None and total == 0:
        _stop_head(head, "the object lists no members")
    _log(head, options.get("log"))
    batch = access_many(members, **options)
    summary = dict(batch["summary"], members_skipped=skipped)
    return {"collection": head.to_dict(), "records": batch["records"], "summary": summary}


def _stop_head(head: AccessRecord, reason: str) -> None:
    """Set the collection stop reason and recompute the record hash."""
    head.stopped = reason
    head.record_sha256 = record_hash(head.to_dict())


def _summary(records: list[dict]) -> dict:
    """Counts of the records by outcome and, per dimension, by status."""
    by_dimension = {name: {status: 0 for status in DIMENSION_STATUSES} for name in DIMENSIONS}
    by_outcome = {outcome: 0 for outcome in OUTCOMES}
    for record in records:
        for name in DIMENSIONS:
            by_dimension[name][record[name]["status"]] += 1
        by_outcome[record["outcome"]] += 1
    return {"total": len(records), "by_dimension": by_dimension, "by_outcome": by_outcome}
