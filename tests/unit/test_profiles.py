"""Tests of profile maps, profile selection and the CCA profile read through its map."""
from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
os.environ["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + os.environ.get("PYTHONPATH", "")

from fdo_consume.pipeline.access import access  # noqa: E402
from fdo_consume.core import AccessError, spellings  # noqa: E402
from fdo_consume.profiles import load_maps, select_profile  # noqa: E402
FIXTURE_CONTRACTS = str(Path(__file__).resolve().parents[2] / "fixtures" / "contracts")
FIXTURE_MAPS = str(Path(__file__).resolve().parents[2] / "fixtures" / "maps")

RECORDED = str(ROOT / "fixtures" / "cca-demo")
STAND_IN = "https://example.org/stand-in/"
DATA = STAND_IN + "hamburg-cca-profile-demo"
SPELLING_B = STAND_IN + "hamburg-cca-spelling-b"
CC = "https://w3id.org/cc-crate-profile/0.9"
CCA = "https://w3id.org/cca-crate-profile/0.9"
OVERLAY = "cca-dashboard-additions"
LOOM_RECORD_PROFILE = "https://knowledgeloom.science/profile/record/0.1.0"


def run(pid=DATA, **options):
    """One access on the recorded test objects."""
    return access(pid, fixtures=RECORDED, **{"contracts": FIXTURE_CONTRACTS, "profile_maps": FIXTURE_MAPS, **options})


class MapsTest(unittest.TestCase):
    """The map files are data with a source and valid levels."""

    def test_every_map_has_an_id_a_source_and_valid_levels(self):
        maps = load_maps()
        self.assertEqual(sorted(maps), ["cca-crate-0.9", "knowledge-loom-0.1.0", "ro-crate"])
        for spec in maps.values():
            self.assertTrue(spec["source"])

    def test_the_published_map_selects_on_both_spellings_of_the_profile_iri(self):
        self.assertEqual(sorted(load_maps()["cca-crate-0.9"]["selects"]), sorted([CC, CCA]))

    def test_the_package_bundles_no_overlay_and_a_consumer_folder_adds_one(self):
        self.assertEqual([name for name, spec in load_maps().items() if spec.get("overlay")], [])
        self.assertEqual([name for name, spec in load_maps(FIXTURE_MAPS).items() if spec.get("overlay")], ["cca-dashboard-additions"])

    def test_no_python_file_names_a_profile(self):
        pattern = re.compile(r"cca|loom|knowledgeloom|cc-crate", re.IGNORECASE)
        hits = []
        for path in (ROOT / "src").rglob("*.py"):
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if pattern.search(line):
                    hits.append(f"{path.relative_to(ROOT)}:{number}")
        self.assertEqual(hits, [])


class SelectionTest(unittest.TestCase):
    """Which map reads an object: the rule is deterministic and recorded."""

    MAPS = {"ro-crate": {"id": "ro-crate", "selects": []},
            "a": {"id": "a", "selects": ["https://x/a/1"]},
            "b": {"id": "b", "selects": ["https://x/b/1", "https://x/b/alias"]}}

    def test_one_declared_profile_with_a_map(self):
        out = select_profile(["https://x/a/1"], self.MAPS)
        self.assertEqual((out.selected, out.ambiguous, out.unknown), ("a", False, []))

    def test_either_spelling_of_one_profile_selects_the_same_map(self):
        for iri in ("https://x/b/1", "https://x/b/alias/"):
            self.assertEqual(select_profile([iri], self.MAPS).selected, "b")

    def test_two_declared_profiles_with_maps_are_ambiguous_and_none_is_taken(self):
        out = select_profile(["https://x/b/1", "https://x/a/1"], self.MAPS)
        self.assertTrue(out.ambiguous)
        self.assertEqual(out.candidates, ["a", "b"])
        self.assertEqual(out.selected, "ro-crate")

    def test_an_unknown_profile_uses_the_default_map_and_is_listed(self):
        out = select_profile(["https://x/other"], self.MAPS)
        self.assertEqual((out.selected, out.unknown), ("ro-crate", ["https://x/other"]))

    def test_no_declared_profile_uses_the_default_map(self):
        self.assertEqual(select_profile([], self.MAPS).selected, "ro-crate")

    def test_a_requested_map_wins_and_an_unknown_request_is_an_error(self):
        self.assertEqual(select_profile(["https://x/a/1"], self.MAPS, "b").selected, "b")
        with self.assertRaises(KeyError):
            select_profile([], self.MAPS, "nope")

    def test_one_known_and_one_unknown_profile_choose_the_known_and_list_the_other(self):
        out = select_profile(["https://x/a/1", "https://x/zzz"], self.MAPS)
        self.assertEqual((out.selected, out.unknown, out.ambiguous), ("a", ["https://x/zzz"], False))


class SpellingTest(unittest.TestCase):
    """schema.org is written with either scheme."""

    def test_the_other_spelling_is_offered_for_schema_org_only(self):
        self.assertEqual(spellings("http://schema.org/name"), ["http://schema.org/name", "https://schema.org/name"])
        self.assertEqual(spellings("https://schema.org/name"), ["https://schema.org/name", "http://schema.org/name"])
        self.assertEqual(spellings("http://purl.org/dc/terms/conformsTo"), ["http://purl.org/dc/terms/conformsTo"])


class CcaThroughItsMapTest(unittest.TestCase):
    """The Hamburg Data FDO, written in the shape of the CCA profile."""

    def test_the_crate_is_read_by_the_published_map_and_the_record_says_why(self):
        record = run(contract="card")
        self.assertEqual(record.descriptor["map_used"], "cca-crate-0.9")
        profile = record.semantics["profile"]
        self.assertEqual((profile["selected"], profile["spelling"], profile["ambiguous"]), ("cca-crate-0.9", CC, False))
        p2 = [s for s in record.steps if s.id == "P2"][0]
        self.assertIn("cca-crate-0.9", p2.detail)

    def test_the_other_spelling_of_the_profile_iri_gives_the_same_map(self):
        record = run(SPELLING_B, contract="card")
        self.assertEqual(record.descriptor["map_used"], "cca-crate-0.9")
        self.assertEqual(record.semantics["profile"]["spelling"], CCA)

    def test_root_fields_are_read_through_the_map_not_by_field_name(self):
        record = run(contract="card")
        d = record.descriptor
        self.assertEqual(d["name"], "Hamburg urban pluvial flood risk and social vulnerability: HEALPix cell products (demo)")
        self.assertEqual(d["license"], "https://creativecommons.org/licenses/by/4.0/")
        self.assertEqual(d["date"], "2026-10-07")
        self.assertEqual(d["profiles"], [CC])

    def test_without_the_overlay_only_the_published_profile_is_read(self):
        record = run(contract="card")
        self.assertEqual(record.descriptor["parts"], [])
        self.assertEqual([e for e in record.descriptor["extra"]["entities"] if e["type"] == "Variable"], [])
        v0 = [s for s in record.steps if s.id == "V0"][0]
        self.assertEqual(v0.status, "PARTIAL")
        self.assertIn("Dataset", v0.detail)
        self.assertEqual(record.validation["status"], "PARTIAL")
        self.assertEqual(record.validation["evidence"], ["V0"])

    def test_an_unknown_overlay_is_a_request_error(self):
        record = run(contract="card", overlay="no-such-overlay")
        self.assertEqual(record.error["code"], "request.bad_option")
        self.assertEqual(record.outcome, "error")

    def test_a_profile_map_cannot_be_used_as_an_overlay(self):
        self.assertEqual(run(contract="card", overlay="cca-crate-0.9").error["code"], "request.bad_option")



def in_temp(crate: dict, pid: str = STAND_IN + "temp-record"):
    """A fixture folder with one crate; returns (folder object, pid)."""
    import json
    import tempfile
    folder = tempfile.TemporaryDirectory()
    target = Path(folder.name) / "objects" / "one"
    target.mkdir(parents=True)
    (target / "ro-crate-metadata.json").write_text(json.dumps(crate), encoding="utf-8")
    (Path(folder.name) / "pids.json").write_text(json.dumps({pid: {"fixture": "one"}}), encoding="utf-8")
    return folder, pid


def loom_record() -> dict:
    """The migrated Hamburg Loom record as data."""
    import json
    return json.loads((ROOT / "fixtures" / "cca-demo" / "objects" / "hamburg-loom-record" / "ro-crate-metadata.json")
                      .read_text(encoding="utf-8"))


def read(crate: dict, **options):
    """One access of a crate held in a temporary folder."""
    folder, pid = in_temp(crate)
    with folder:
        return access(pid, fixtures=folder.name, contract="knowledge-record-v1", **options, contracts=FIXTURE_CONTRACTS)


def root_of(crate: dict) -> dict:
    """The root entity of a crate as data."""
    return [e for e in crate["@graph"] if e["@id"] == "./"][0]


class LoomThroughItsMapTest(unittest.TestCase):
    """The Knowledge Loom record profile 0.1.0 read through its map: must-level terms decide FAIL by presence."""

    def test_the_record_has_no_overall_status_and_keeps_validation_indeterminate(self):
        record = access(STAND_IN + "hamburg-loom-record", fixtures=RECORDED, contract="knowledge-record-v1", contracts=FIXTURE_CONTRACTS)
        self.assertEqual((record.compatibility["status"], record.validation["status"]), ("PASS", "INDETERMINATE"))
        self.assertNotIn("status", record.to_dict())

    def test_the_validation_answer_does_not_depend_on_the_consumer(self):
        one = access(STAND_IN + "hamburg-loom-record", fixtures=RECORDED, contract="knowledge-record-v1", contracts=FIXTURE_CONTRACTS)
        two = access(STAND_IN + "hamburg-loom-record", fixtures=RECORDED, contract="map-panel-v1", contracts=str(ROOT / "fixtures" / "example-profile" / "contracts"))
        self.assertEqual((one.validation["status"], one.validation["evidence"]), (two.validation["status"], two.validation["evidence"]))
        self.assertEqual(one.validation["validator"], {"ran": False, "reason": "no authoritative profile validator is configured"})

    def test_the_migrated_hamburg_record_is_read_by_the_loom_map(self):
        record = access(STAND_IN + "hamburg-loom-record", fixtures=RECORDED, contract="knowledge-record", contracts=FIXTURE_CONTRACTS)
        self.assertEqual(record.descriptor["map_used"], "knowledge-loom-0.1.0")
        o1 = [s for s in record.steps if s.id == "O1"][0]
        self.assertEqual((o1.status, "deposit" in o1.detail), ("PASS", True))
        self.assertEqual(record.validation["status"], "INDETERMINATE")
        self.assertIn("no profile validator ran", record.validation["note"])
        self.assertEqual(sum(e["type"] == "Statement" for e in record.descriptor["extra"]["entities"]), 3)

    def test_the_legacy_export_does_not_declare_the_profile_so_the_default_map_reads_it(self):
        record = access(STAND_IN + "hamburg-legacy-loom", fixtures=RECORDED, contract="knowledge-record", contracts=FIXTURE_CONTRACTS)
        self.assertIsNone(record.descriptor["map_used"])

    def test_a_missing_must_term_is_a_validation_fail_that_names_it(self):
        crate = loom_record()
        root_of(crate).pop("license")
        record = read(crate)
        v0 = [s for s in record.steps if s.id == "V0"][0]
        self.assertEqual(v0.status, "FAIL")
        self.assertIn("licence", v0.detail)
        self.assertEqual(record.validation["status"], "FAIL")

    def test_a_whitespace_only_required_text_counts_as_absent(self):
        crate = loom_record()
        root_of(crate)["description"] = "   "
        self.assertIn("description", [s for s in read(crate).steps if s.id == "V0"][0].detail)

    def test_a_published_record_without_statements_breaks_the_lifecycle_rule(self):
        crate = loom_record()
        root_of(crate)["status"] = "published"
        crate["@graph"] = [e for e in crate["@graph"] if e.get("@type") != ["loom:Statement"]]
        v0 = [s for s in read(crate).steps if s.id == "V0"][0]
        self.assertEqual(v0.status, "FAIL")
        self.assertIn("5.1", v0.detail)

    def test_an_unpublished_record_may_have_no_statement(self):
        crate = loom_record()
        crate["@graph"] = [e for e in crate["@graph"] if e.get("@type") != ["loom:Statement"]]
        self.assertEqual([s for s in read(crate).steps if s.id == "V0"][0].status, "PASS")

    def test_a_statement_without_a_label_fails_the_statement_level(self):
        crate = loom_record()
        for e in crate["@graph"]:
            if e.get("@type") == ["loom:Statement"]:
                e.pop("rdfs:label")
                break
        self.assertIn("Statement", [s for s in read(crate).steps if s.id == "V0"][0].detail)

    def test_validation_and_compatibility_are_separate_for_a_loom_record(self):
        crate = loom_record()
        root_of(crate).pop("isBasedOn")
        record = read(crate)
        self.assertEqual(record.validation["status"], "FAIL")
        self.assertNotEqual(record.compatibility["status"], "FAIL")


EXAMPLES = Path(os.environ.get("LOOM_EXAMPLES", "/nonexistent"))


@unittest.skipUnless(EXAMPLES.is_dir(), "set LOOM_EXAMPLES to the examples folder of the Knowledge Loom profile repository to run this")
class LoomExamplesTest(unittest.TestCase):
    """The examples of the Loom profile repository, read locally and never copied into this repository."""

    def statuses_of(self, folder: str) -> dict:
        import json
        out = {}
        for path in sorted((EXAMPLES / folder).glob("*.json")):
            crate = json.loads(path.read_text(encoding="utf-8"))
            record = read(crate)
            step = [s for s in record.steps if s.id == "V0"]
            out[path.name] = (record.descriptor["map_used"] if record.descriptor else None,
                              step[0].status if step else "no V0")
        return out

    def test_every_valid_example_is_compatible_with_the_record_view(self):
        import json
        found = {}
        for path in sorted((EXAMPLES / "valid").glob("*.json")):
            record = read(json.loads(path.read_text(encoding="utf-8")))
            found[path.name] = (record.compatibility["status"], record.validation["status"])
        self.assertEqual(len(found), 17)
        self.assertEqual({v[0] for v in found.values()}, {"PASS"})
        self.assertEqual({v[1] for v in found.values()}, {"INDETERMINATE"})

    def test_no_valid_example_fails_by_levels(self):
        found = self.statuses_of("valid")
        self.assertEqual(len(found), 17)
        bad = {k: v for k, v in found.items() if v[1] == "FAIL"}
        self.assertEqual(bad, {})

    def test_the_number_of_invalid_examples_caught_by_levels_alone_is_pinned(self):
        found = self.statuses_of("invalid")
        caught = [k for k, v in found.items() if v[1] == "FAIL"]
        print(f"\nLoom invalid examples: {len(found)}; caught by levels alone: {len(caught)}")
        self.assertGreater(len(found), 40)
        self.assertEqual(len(caught), 13)


if __name__ == "__main__":
    unittest.main()
