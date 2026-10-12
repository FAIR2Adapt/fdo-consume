"""Source interface: a PID in, a Located object out."""
from __future__ import annotations

from typing import Protocol

from ..core import Limits, LocatedObject


class Source(Protocol):
    """A function (pid, options, limits) that returns a LocatedObject or raises AccessError."""

    def __call__(self, pid: str, options: dict, limits: Limits) -> LocatedObject: ...
