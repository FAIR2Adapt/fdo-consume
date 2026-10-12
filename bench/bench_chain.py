"""Benchmark chain performance with synthetic crates of increasing size and batch count."""
from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Callable

REPOSITORY = Path(__file__).resolve().parents[1]
BASE = "https://example.org/fdo/synthetic/bench/"
CRATE_SIZES = (10, 1_000, 10_000, 100_000)
BATCH_SIZES = (10, 100, 1_000, 5_000)


def crate(pid: str, parts: int) -> dict:
    """One synthetic crate with `parts` File entities."""
    files = []
    for number in range(parts):
        files.append({
            "@id": f"f{number}.csv", "@type": "File", "name": f"f{number}.csv",
            "encodingFormat": "text/csv", "contentSize": 1000 + number,
            "contentUrl": f"https://example.org/payload/synthetic/f{number}.csv",
        })
    root = {
        "@id": "./", "@type": "Dataset", "identifier": pid, "name": "bench",
        "description": "Synthetic test object used for software validation.",
        "license": {"@id": "https://creativecommons.org/licenses/by/4.0/"},
        "datePublished": "2026-01-01", "additionalType": "dataset",
    }
    about = {"@id": "ro-crate-metadata.json", "@type": "CreativeWork", "about": {"@id": "./"}}
    return {"@context": "https://w3id.org/ro/crate/1.1/context", "@graph": [about, root, *files]}


def build(root: Path, objects: int, parts: int) -> list[str]:
    """Write a fixture folder; return its PIDs."""
    index = {"_note": "SYNTHETIC benchmark fixtures"}
    for number in range(objects):
        pid = f"{BASE}{root.name}/o{number}"
        folder = root / "objects" / f"o{number}"
        folder.mkdir(parents=True)
        (folder / "ro-crate-metadata.json").write_text(json.dumps(crate(pid, parts)))
        index[pid] = {"fixture": f"o{number}"}
    (root / "pids.json").write_text(json.dumps(index))
    return [pid for pid in index if pid != "_note"]


def seconds(call: Callable) -> float:
    """Wall time of one call."""
    start = time.perf_counter()
    call()
    return time.perf_counter() - start


def main() -> None:
    """Print both tables."""
    sys.path.insert(0, str(REPOSITORY / "src"))
    from fdo_consume.batch import access_many
    from fdo_consume.pipeline.access import access
    with tempfile.TemporaryDirectory() as tmp:
        print("one object, growing crate")
        for parts in CRATE_SIZES:
            root = Path(tmp) / f"crate{parts}"
            pids = build(root, 1, parts)
            took = seconds(lambda: access(pids[0], contract="card", fixtures=str(root)))
            print(f"  entities {parts:>7}   {took * 1000:8.1f} ms")
        print("batch of small objects (10 parts each)")
        for objects in BATCH_SIZES:
            root = Path(tmp) / f"batch{objects}"
            pids = build(root, objects, 10)
            took = seconds(lambda: access_many(pids, contract="card", fixtures=str(root)))
            each = took / objects * 1000
            print(f"  objects {objects:>6}   {took * 1000:8.1f} ms   {each:6.3f} ms each")


if __name__ == "__main__":
    main()
