"""Loader "reference": where a part is."""
from __future__ import annotations

from ..core import Loaded, Part
from ..registry import register


def wants_reference(part: Part, want: str) -> bool:
    """True when the consumer asked for a reference."""
    return want == "reference"


# TODO: lazy loaders for large data
@register("loader", "reference", match=wants_reference)
def load_reference(part: Part) -> Loaded:
    """The part as a reference; a restricted part needs a grant."""
    if part.restricted:
        note = "restricted: authorisation is needed before reading; not read"
    elif part.size is None:
        note = "size not declared; not read"
    else:
        note = f"{part.size} bytes declared; not read"
    return Loaded("reference", part.url, part.media_type, part.restricted, note)
