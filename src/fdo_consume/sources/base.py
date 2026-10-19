"""Source protocol: resolves a PID to a Located object."""
from __future__ import annotations

from typing import Protocol

from ..core import Limits, Located


class Source(Protocol):
    """A function (pid, options, limits) that returns a Located object or raises AccessError."""

    def __call__(self, pid: str, options: dict, limits: Limits) -> Located: ...
