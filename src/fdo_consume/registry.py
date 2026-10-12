"""Adapters by kind and name: register, get, names, pick."""
from __future__ import annotations

from typing import Callable

KINDS = ("locator", "describer", "check", "loader")

_ADAPTERS: dict[str, dict[str, tuple]] = {kind: {} for kind in KINDS}


def register(kind: str, name: str, match: Callable | None = None) -> Callable:
    """Register a function as adapter `name` of `kind` (internal; not a public plugin API)."""
    if kind not in KINDS:
        raise ValueError(f"unknown adapter kind: {kind!r}; kinds are {KINDS}")

    def keep(function: Callable) -> Callable:
        """Register and return the function unchanged."""
        _ADAPTERS[kind][name] = (function, match)
        return function

    return keep


def get(kind: str, name: str) -> Callable:
    """Return the registered adapter; KeyError when absent."""
    if name not in _ADAPTERS[kind]:
        raise KeyError(f"no {kind} adapter named {name!r}")
    return _ADAPTERS[kind][name][0]


def names(kind: str) -> list[str]:
    """Sorted names of the adapters of one kind."""
    return sorted(_ADAPTERS[kind])


def pick(kind: str, *subject: object) -> Callable | None:
    """The adapter of `kind` whose `match` accepts the subject; the most recently registered wins."""
    for function, match in reversed(list(_ADAPTERS[kind].values())):
        if match is not None and match(*subject):
            return function
    return None
