"""Shared paths for the tests of the CCA dashboard-profile map (synthetic objects in fixtures/cca-dashboard)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECORDED = str(ROOT / "fixtures" / "cca-dashboard")
