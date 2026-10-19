"""Source "recorded": PIDs resolved from a folder of recorded objects (pids.json + objects/)."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from ..core import (
    AccessError, Limits, Located, parse_crate, refuse_large_crate, sha256_bytes,
)
from ..registry import register

DEFAULT_FIXTURES: Path | None = None   # an embedding application may set a folder used when none is passed
CRATE_FILE = "ro-crate-metadata.json"


@register("locator", "recorded")
def locate_recorded(pid: str, options: dict, limits: Limits) -> Located:
    """The recorded crate of `pid`; an unknown PID is not resolved."""
    fixtures = options.get("fixtures")
    root = Path(fixtures) if fixtures else DEFAULT_FIXTURES
    if not fixtures and (root is None or not root.is_dir()):
        raise AccessError("request.bad_fixtures", "the recorded source needs a fixture folder: pass fixtures=DIR (--fixtures DIR)")
    index = _read_index(root)

    entry = index.get(pid)
    if entry is None:
        entry = index.get(pid.rstrip("/"))
    if not isinstance(entry, dict):
        raise AccessError("resolution.not_recorded", "no recorded copy of this PID")

    name = str(entry.get("fixture"))
    path = f"objects/{name}/{CRATE_FILE}"
    file = root / path
    if ".." in Path(name).parts or Path(name).is_absolute():
        raise AccessError("request.bad_fixtures", f"pids.json leaves the fixture folder: {path}")
    if not file.is_file():
        raise AccessError("request.bad_fixtures", f"pids.json names no file: {path}")
    if any(p.is_symlink() for p in (file, file.parent)) or root.resolve() not in file.resolve().parents:
        raise AccessError("request.bad_fixtures", f"the recorded object is a link outside the fixture folder: {path}")
    refuse_large_crate(file.stat().st_size, limits)

    data = file.read_bytes()
    crate = parse_crate(data)
    return Located(pid, crate, [pid, f"recorded: {path}"], sha256_bytes(data), len(data))


def _read_index(root: Path) -> dict:
    """The mapping in pids.json; a file that is absent or no mapping is refused."""
    index_file = root / "pids.json"
    if not index_file.is_file():
        raise AccessError("request.bad_fixtures", f"no pids.json in {root}")
    try:
        index = _index(str(index_file), index_file.stat().st_mtime_ns)
    except (ValueError, RecursionError):
        raise AccessError("request.bad_fixtures", f"pids.json in {root} is not JSON") from None
    if not isinstance(index, dict):
        raise AccessError("request.bad_fixtures", f"pids.json in {root} is not a mapping")
    return index


@lru_cache(maxsize=8)
def _index(path: str, changed: int) -> object:
    """pids.json, parsed once until the file changes."""
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))
