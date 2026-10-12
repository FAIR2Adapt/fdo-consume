"""Shared state of one access across the stages."""
from __future__ import annotations

from dataclasses import dataclass

from ..core import AccessRecord, CanonicalGraph, Descriptor, Limits, Located, Part


@dataclass
class Context:
    """The request, the contract, the record, and what each stage produced."""

    pid: str
    options: dict
    limits: Limits
    spec: dict | None
    record: AccessRecord
    located: Located | None = None
    canonical: CanonicalGraph | None = None
    descriptor: Descriptor | None = None
    selected: Part | None = None
    stopped: str | None = None
