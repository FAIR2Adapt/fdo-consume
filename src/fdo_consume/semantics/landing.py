"""Landing pages: URLs that answer with a web page about a file, never the file."""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

import yaml

LANDING_FILE = Path(__file__).resolve().parent / "data" / "landing-pages.yaml"


@lru_cache(maxsize=1)
def _rules() -> dict:
    """The landing-page rules, read once."""
    return yaml.safe_load(LANDING_FILE.read_text(encoding="utf-8"))


def landing_reason(url: str) -> str | None:
    """Why this URL is a landing page; None when the rules do not say so."""
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").rstrip(".").lower()
    except ValueError:
        return None
    rules = _rules()
    for entry in rules["hosts"]:
        if host == entry["host"]:
            return entry["reason"]
    for entry in rules["host_paths"]:
        if host == entry["host"] and re.search(entry["path_regex"], parsed.path):
            return entry["reason"]
    return None
