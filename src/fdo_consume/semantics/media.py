"""Media types: declared by the object, or inferred from a URL suffix (data in media-suffixes.yaml)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

import yaml

MEDIA_FILE = Path(__file__).resolve().parent / "data" / "media-suffixes.yaml"
DECLARED = "declared"
INFERRED = "inferred from the URL suffix"


@lru_cache(maxsize=1)
def _table() -> dict:
    """The suffix table, read once."""
    return yaml.safe_load(MEDIA_FILE.read_text(encoding="utf-8"))


def from_suffix(url: str | None) -> str | None:
    """A media type for the last suffix of the URL path, when it is a known one."""
    if not url:
        return None
    try:
        path = urlsplit(url).path.lower()
    except ValueError:
        return None
    dot = path.rfind(".")
    if dot < path.rfind("/"):
        return None
    return _table()["suffixes"].get(path[dot:])


def is_generic(media_type: str | None) -> bool:
    """True for a declared type that says nothing about the format (text/plain, application/octet-stream)."""
    return (media_type or "").split(";")[0].strip().lower() in _table()["generic_declared"]


def decide(url: str | None, declared: str | None, infer: bool) -> tuple[str | None, str | None]:
    """(media type, how): the declared type when it is specific; else the suffix when inference is allowed."""
    if declared and not is_generic(declared):
        return declared, DECLARED
    inferred = from_suffix(url) if infer else None
    if inferred:
        return inferred, INFERRED
    return declared, DECLARED if declared else None
