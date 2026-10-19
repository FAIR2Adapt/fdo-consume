"""Example consumer with its own contract and profile map, read from folders next to this script."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from fdo_consume import consume

HERE = Path(__file__).resolve().parent
PID = "https://example.org/object/full"   # synthetic example object


def main() -> int:
    recorded = sys.argv[1] if len(sys.argv) > 1 else str(HERE.parents[1] / "fixtures" / "example-profile")
    maps = HERE / "maps"
    result = consume(PID, "my-map-panel-v1", recorded_dir=recorded, contracts=str(HERE / "contracts"),
                     profile_maps=str(maps))
    print(json.dumps({"is_usable": result.is_usable, "statuses": result.statuses, "diagnostics": result.diagnostics}, indent=1))
    return 0 if result.is_usable else 1


if __name__ == "__main__":
    raise SystemExit(main())
