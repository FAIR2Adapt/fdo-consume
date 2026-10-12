"""Bounds on what one access reads, lists and visits."""
from __future__ import annotations

from dataclasses import dataclass

from .failures import AccessError


@dataclass(frozen=True)
class Limits:
    """Bounds on what one access reads, lists and visits."""

    max_members: int = 1000
    max_parts: int = 200
    max_crate_bytes: int = 50_000_000



def refuse_large_crate(size: int, limits: Limits) -> None:
    """Raise object.too_large for a crate over the byte limit."""
    if size > limits.max_crate_bytes:
        message = f"the crate is {size} bytes; the limit is {limits.max_crate_bytes}"
        raise AccessError("object.too_large", message)
