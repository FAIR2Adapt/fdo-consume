"""The CCA Data FDO read with the draft overlay."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from profile_support import RECORDED  # noqa: E402
from fdo_consume.pipeline.access import access  # noqa: E402
FIXTURE_CONTRACTS = str(Path(__file__).resolve().parents[2] / "fixtures" / "contracts")
FIXTURE_MAPS = str(Path(__file__).resolve().parents[2] / "fixtures" / "maps")

STAND_IN = "https://example.org/stand-in/"
DATA = STAND_IN + "hamburg-cca-profile-demo"
OVERLAY = "cca-dashboard-additions"
LOOM_RECORD_PROFILE = "https://knowledgeloom.science/profile/record/0.1.0"


def run(pid=DATA, **options):
    return access(pid, fixtures=RECORDED, **{"contracts": FIXTURE_CONTRACTS, "profile_maps": FIXTURE_MAPS, **options})


class CcaWithDraftOverlayTest(unittest.TestCase):

    def test_with_the_overlay_variables_distributions_and_claims_are_read(self):
        d = run(contract="card", overlay=OVERLAY).descriptor
        kinds = {}
        for e in d["extra"]["entities"]:
            kinds[e["type"]] = kinds.get(e["type"], 0) + 1
        self.assertEqual(kinds, {"Dataset": 3, "Variable": 10, "Claim": 3, "Property": 4})
        self.assertEqual(len(d["parts"]), 4)
        self.assertTrue(all(p["in_crate"] and p["payload"] for p in d["parts"]))
        self.assertEqual(sorted(p["media_type"] for p in d["parts"]),
                         ["application/flatgeobuf", "application/flatgeobuf",
                          "application/vnd.pmtiles", "application/vnd.pmtiles"])
        claims = [e for e in d["extra"]["entities"] if e["type"] == "Claim"]
        self.assertEqual({tuple(c["fields"]["record_profiles"]) for c in claims}, {(LOOM_RECORD_PROFILE,)})

    def test_a_crate_local_part_is_a_payload_of_the_map_layer_contract(self):
        record = run(contract="map-layer", depth="select", overlay=OVERLAY)
        a4 = [s for s in record.steps if s.id == "A4"][0]
        self.assertEqual(a4.status, "PASS")
        self.assertEqual(record.selected["url"], "in-crate:public/risk_healpix.fgb")
        self.assertTrue(record.selected["in_crate"])

    def test_the_restricted_product_is_reported_with_no_distribution(self):
        d = run(contract="card", overlay=OVERLAY).descriptor
        restricted = [e for e in d["extra"]["entities"] if e["type"] == "Dataset" and e["access"]["state"] == "restricted"]
        self.assertEqual(len(restricted), 1)
        self.assertEqual([r for r in d["extra"]["resources"] if restricted[0]["id"] in r["holders"]], [])
        self.assertTrue(restricted[0]["access"]["conditions"])

    def test_bremen_is_read_by_the_same_maps_and_contract_as_hamburg(self):
        record = access(STAND_IN + "bremen-cca-profile-demo", fixtures=RECORDED, contract="cs3-map-v1", overlay=OVERLAY,
                        depth="load", want="binding", contracts=FIXTURE_CONTRACTS, profile_maps=FIXTURE_MAPS)
        self.assertEqual(record.descriptor["map_used"], "cca-crate-0.9")
        self.assertEqual((record.resolution["status"], record.compatibility["status"], record.delivery["status"]), ("PASS", "PASS", "PASS"))
        self.assertLessEqual({"Dataset", "Variable", "Claim"}, {e["type"] for e in record.value["entities"]})

    def test_both_knowledge_loom_records_are_read_by_the_loom_map(self):
        for city in ("hamburg", "bremen"):
            with self.subTest(city=city):
                record = access(STAND_IN + f"{city}-loom-record", fixtures=RECORDED, contract="cs3-evidence-v1", depth="load",
                                want="binding", contracts=FIXTURE_CONTRACTS, profile_maps=FIXTURE_MAPS, profile="knowledge-loom-0.1.0")
                self.assertEqual(record.descriptor["map_used"], "knowledge-loom-0.1.0")
                self.assertEqual(record.compatibility["status"], "PASS")
                self.assertTrue([e for e in record.value["entities"] if e["type"] == "Statement"])


if __name__ == "__main__":
    unittest.main()
