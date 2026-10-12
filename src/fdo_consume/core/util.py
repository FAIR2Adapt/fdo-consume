"""Small pure helpers: clipping, plain data, canonical JSON, hashes."""
from __future__ import annotations

import hashlib
import json
import re

from .failures import AccessError

SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f\u2028\u2029]")
CLIP = 200


def parse_crate(data: bytes) -> object:
    """Crate bytes as JSON data; bytes that do not decode or parse are object.not_json."""
    try:
        return json.loads(data.decode("utf-8-sig"))
    except (ValueError, RecursionError) as err:
        message = f"the crate is not JSON: {type(err).__name__}: {err}"
        raise AccessError("object.not_json", clip(message)) from None


def has_scheme(text: object) -> bool:
    """True for text that starts with a scheme, as a PID or an IRI does."""
    return isinstance(text, str) and SCHEME.match(text) is not None


def media_key(text: object) -> str | None:
    """A media type as it is compared: type/subtype, lower case, no parameters."""
    if not isinstance(text, str):
        return None
    return text.split(";")[0].strip().lower()


def clip(text: object) -> str:
    """Text for a step detail: control characters as spaces, at most 200 characters."""
    clean = CONTROL.sub(" ", str(text))
    if len(clean) > CLIP:
        return clean[:CLIP - 1] + "…"
    return clean


def plain(value: object) -> object:
    """A value as plain JSON data; a part JSON cannot carry is kept as its repr."""
    if value is None or isinstance(value, str):
        return value
    try:
        return json.loads(json.dumps(value, default=repr, skipkeys=True))
    except (TypeError, ValueError, RecursionError):
        return f"<{type(value).__name__}>"


def shown(value: object) -> str:
    """A value the caller gave, for a message: quoted, clipped, never raising."""
    return clip(repr(plain(value)))


def canonical(value: object) -> str:
    """Canonical JSON: sorted keys, compact, UTF-8 kept."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_of(value: object) -> str:
    """sha256 of the canonical JSON of a value."""
    return hashlib.sha256(bytes(canonical(value), "utf-8")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    """sha256 of bytes as they were located."""
    return hashlib.sha256(data).hexdigest()


TEXT_LIMIT = 2000


def clip_long(text: object, limit: int = TEXT_LIMIT) -> object:
    """Text from an object kept in a record: control characters as spaces, at most `limit` characters."""
    if not isinstance(text, str):
        return text
    clean = CONTROL.sub(" ", text)
    return clean if len(clean) <= limit else clean[:limit - 1] + "…"
