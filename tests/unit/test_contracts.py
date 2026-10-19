"""Tests of consumer contracts: named consumer, a source for every need, and matching."""
from __future__ import annotations

import copy
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
os.environ["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + os.environ.get("PYTHONPATH", "")

from fdo_consume import contracts  # noqa: E402
from fdo_consume.pipeline.access import access  # noqa: E402
from fdo_consume.contracts import loader  # noqa: E402
FIXTURE_CONTRACTS = str(Path(__file__).resolve().parents[2] / "fixtures" / "contracts")
FIXTURE_MAPS = str(Path(__file__).resolve().parents[2] / "fixtures" / "maps")

RECORDED = str(ROOT / "fixtures" / "cca-demo")
OBJECT = "https://example.org/stand-in/hamburg-cca-profile-demo"
DEMO = str(Path(__file__).resolve().parents[2] / "fixtures" / "cca-demo")
STAND_IN = "https://example.org/stand-in/"
DATA = STAND_IN + "hamburg-cca-profile-demo"
EXAMPLE = str(ROOT / "fixtures" / "example-profile")
MAPS = str(ROOT / "fixtures" / "example-profile" / "maps")
CONTRACTS = str(ROOT / "fixtures" / "example-profile" / "contracts")
FULL = "https://example.org/object/full"
NO_IDENTIFIER = "https://example.org/object/no-identifier"  # the full example object without an identifier
LOOM = STAND_IN + "hamburg-loom-record"

GOOD = {
    "contract_id": "toy-v1", "version": 1,
    "consumer": {"service": "a toy view", "capability": "show a title"},
    "source": {"repository": "fdo-consume", "path": "tests", "reviewed": "2026-10-12"},
    "needs": [{"term": "title", "level": "must", "source": "document, section 1", "reason": "the view shows it"}],
}


def variant(**changes) -> dict:
    """The good contract with changes; a key set to None is removed."""
    spec = copy.deepcopy(GOOD)
    for key, value in changes.items():
        if value is None:
            spec.pop(key, None)
        else:
            spec[key] = value
    return spec


def need(**changes) -> dict:
    """One need with changes."""
    base = dict(GOOD["needs"][0])
    base.update(changes)
    return base


class ConsumerContractsTest(unittest.TestCase):
    """The consumer contracts used by the tests: needs-form contracts carry their consumer and a reason per need."""

    def needs_form(self):
        import yaml
        return sorted(p.stem for p in Path(FIXTURE_CONTRACTS).glob("*.yaml")
                      if "needs" in yaml.safe_load(p.read_text(encoding="utf-8")))

    def test_the_fixture_folder_holds_the_dashboard_and_record_contracts(self):
        self.assertEqual(self.needs_form(), ["composer-object-v1", "cs3-claims-v1", "cs3-evidence-v1", "cs3-map-v1", "cs3-metadata-v1",
                                             "dashboard-composition-v1", "knowledge-record-v1", "plugin-description-v1"])

    def test_every_contract_loads_with_the_maps_it_names(self):
        for name in self.needs_form():
            with self.subTest(contract=name):
                spec = contracts.load_contract(name, folder=FIXTURE_CONTRACTS, profile_maps=FIXTURE_MAPS)
                self.assertEqual(spec["contract_id"], name)

    def test_a_contract_that_names_the_overlay_needs_the_map_folder_that_holds_it(self):
        with self.assertRaises(Exception):
            contracts.load_contract("dashboard-composition-v1", folder=FIXTURE_CONTRACTS)

    def test_every_contract_names_its_consumer_and_a_reason_per_need(self):
        import yaml
        for name in self.needs_form():
            spec = yaml.safe_load((Path(FIXTURE_CONTRACTS) / f"{name}.yaml").read_text(encoding="utf-8"))
            with self.subTest(contract=name):
                self.assertTrue(spec["consumer"]["service"] and spec["consumer"]["capability"])
                for item in spec["needs"]:
                    self.assertTrue(item["reason"].strip(), item["term"])

    def test_a_production_contract_loads_by_name_as_must_and_should_lists(self):
        spec = contracts.load_contract("map-panel-v1", CONTRACTS)
        self.assertEqual(spec["must"], ["resources", "Variable"])
        self.assertEqual(spec["should"], [])
        self.assertIn("map panel", spec["consumer"])
        self.assertNotIn("profile_additions", spec)   # profile interpretation is chosen by the caller, not the contract

    def test_the_list_form_contracts_still_load(self):
        self.assertEqual(contracts.load_contract("card", folder=FIXTURE_CONTRACTS)["contract_id"], "card-v1")

    def test_no_contract_asks_for_a_term_no_profile_defines(self):
        for name in self.needs_form():
            spec = contracts.load_contract(name, folder=FIXTURE_CONTRACTS, profile_maps=FIXTURE_MAPS)
            self.assertNotIn("resource_type", spec["must"] + spec["should"])


class ConsumerOwnedContractsTest(unittest.TestCase):
    """A consumer passes its own contract folder; it is searched before the package contracts."""

    def folder(self, **changes):
        import yaml
        tmp = tempfile.TemporaryDirectory()
        spec = variant(contract_id="mine-v1", **changes)
        (Path(tmp.name) / "mine.yaml").write_text(yaml.safe_dump(spec), encoding="utf-8")
        return tmp

    def test_a_contract_is_found_in_the_consumers_folder_first(self):
        with self.folder() as tmp:
            record = access(OBJECT, fixtures=DEMO, contract="mine", contracts=tmp)
        self.assertEqual((record.outcome, record.contract_id), ("ok", "mine-v1"))

    def test_the_folder_may_shadow_a_reference_contract(self):
        import yaml
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "cs3-map-v1.yaml").write_text(yaml.safe_dump(variant(contract_id="cs3-map-v1-mine")), encoding="utf-8")
            record = access(DATA, fixtures=RECORDED, overlay="cca-dashboard-additions", contract="cs3-map-v1", contracts=tmp, profile_maps=FIXTURE_MAPS)
        self.assertEqual(record.contract_id, "cs3-map-v1-mine")

    def test_a_contract_in_the_folder_follows_the_same_rules(self):
        with self.folder(consumer=None) as tmp:
            record = access(OBJECT, fixtures=DEMO, contract="mine", contracts=tmp)
        self.assertEqual(record.error["code"], "request.bad_contract")

    def test_a_folder_that_does_not_exist_is_a_request_error(self):
        record = access(OBJECT, fixtures=DEMO, contract="mine", contracts="/nonexistent-folder")
        self.assertEqual(record.error["code"], "request.bad_contract")

    def test_a_name_that_is_a_path_is_still_refused(self):
        with self.folder() as tmp:
            record = access(OBJECT, fixtures=DEMO, contract=str(Path(tmp) / "mine.yaml"), contracts=tmp)
        self.assertEqual(record.error["code"], "request.bad_contract")


class RejectedContractsTest(unittest.TestCase):
    """A contract that is wrong is a request error before any object is touched."""

    def refused(self, spec: dict, text: str):
        record = access(OBJECT, fixtures=DEMO, contract=spec)
        self.assertEqual(record.error["code"], "request.bad_contract")
        self.assertIn(text, record.error["message"])
        self.assertEqual(record.steps, [])
        self.assertEqual(record.outcome, "error")

    def test_the_good_contract_is_accepted(self):
        self.assertEqual(access(OBJECT, fixtures=DEMO, contract=GOOD).outcome, "ok")

    def test_no_consumer(self):
        self.refused(variant(consumer=None), "no consumer")

    def test_a_consumer_without_a_capability(self):
        self.refused(variant(consumer={"service": "x"}), "service and capability")

    def test_a_source_that_is_not_a_mapping_of_text(self):
        self.refused(variant(source="urban-pfr-dashboard"), "mapping of text")
        self.refused(variant(source={"reviewed": 2026}), "mapping of text")

    def test_source_and_reason_are_optional(self):
        self.assertEqual(access(OBJECT, fixtures=DEMO, contract=variant(source=None)).outcome, "ok")
        bare = {k: v for k, v in need().items() if k not in ("source", "reason")}
        self.assertEqual(access(OBJECT, fixtures=DEMO, contract=variant(needs=[bare])).outcome, "ok")

    def test_a_reason_that_is_not_text(self):
        self.refused(variant(needs=[need(reason=["r"])]), "is not text")

    def test_an_undefined_resource_type_requirement(self):
        self.refused(variant(needs=[need(term="resource_type")]), "no profile map defines")

    def test_a_bad_level(self):
        self.refused(variant(needs=[need(level="shall")]), "level")

    def test_a_contract_that_everything_satisfies(self):
        self.refused(variant(needs=[]), "defines no requirements")

    def test_a_contract_with_a_media_type_that_is_none(self):
        self.refused(variant(accepts=["not a media type"]), "invalid media type")

    def test_the_same_term_twice(self):
        self.refused(variant(needs=[need(), need(level="should")]), "twice")

    def test_an_unknown_key(self):
        self.refused(variant(selector="open-first"), "unknown key")

    def test_a_file_that_breaks_the_rules_is_refused_by_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            import yaml
            (Path(tmp) / "bad.yaml").write_text(yaml.safe_dump(variant(consumer=None)), encoding="utf-8")
            loader._parsed.cache_clear()
            record = access(OBJECT, fixtures=DEMO, contract="bad", contracts=tmp)
        loader._parsed.cache_clear()
        self.assertEqual(record.error["code"], "request.bad_contract")


class MatchingTest(unittest.TestCase):
    """Usability depends on the contract: one object, two contracts, two results."""

    def test_the_example_object_is_compatible_with_the_map_panel(self):
        record = access(FULL, fixtures=EXAMPLE, profile_maps=MAPS, contracts=CONTRACTS, contract="map-panel-v1", depth="select")
        self.assertEqual(record.compatibility["status"], "PASS")
        self.assertEqual(record.contract_id, "map-panel-v1")
        self.assertEqual(record.descriptor["map_used"], "example-panels-1.0")

    def test_the_same_object_gets_another_answer_from_another_consumer(self):
        loom = access(LOOM, fixtures=RECORDED, contract="knowledge-record-v1", contracts=FIXTURE_CONTRACTS)
        as_map = access(LOOM, fixtures=RECORDED, contract="map-panel-v1", contracts=CONTRACTS)
        self.assertEqual(loom.compatibility["status"], "PASS")
        self.assertNotEqual(as_map.compatibility["status"], "PASS")
        self.assertEqual(loom.validation["status"], as_map.validation["status"])

    def test_the_loom_record_is_compatible_with_the_record_view(self):
        record = access(LOOM, fixtures=RECORDED, contract="knowledge-record-v1", contracts=FIXTURE_CONTRACTS)
        self.assertEqual(record.compatibility["status"], "PASS")
        self.assertEqual(record.resolution["status"], "PASS")

    def test_a_contract_given_as_a_mapping_must_ask_for_something(self):
        for spec in ({"contract_id": "empty"}, {"must": [], "should": []}):
            with self.subTest(spec=spec):
                self.assertEqual(access(OBJECT, fixtures=DEMO, contract=spec).error["code"], "request.bad_contract")

    def test_a_mapping_contract_with_a_non_media_type_is_refused(self):
        record = access(OBJECT, fixtures=DEMO, contract={"accepts": ["not a media type"]})
        self.assertEqual(record.error["code"], "request.bad_contract")

    def test_a_must_term_the_profile_does_not_define_is_indeterminate_not_fail(self):
        spec = variant(needs=[need(term="Statement", level="must")])
        record = access(DATA, fixtures=RECORDED, contract=spec)
        self.assertEqual([s for s in record.steps if s.id == "A7"][0].status, "INDETERMINATE")
        self.assertEqual(record.compatibility["status"], "INDETERMINATE")

    def test_every_partial_names_the_missing_should_term(self):
        spec = variant(needs=[need(), need(term="date", level="should"), need(term="identifier", level="should")])
        record = access(NO_IDENTIFIER, fixtures=EXAMPLE, profile_maps=MAPS, contracts=CONTRACTS, contract=spec)
        a7 = [s for s in record.steps if s.id == "A7"][0]
        self.assertEqual(a7.status, "PARTIAL")
        self.assertIn("should absent: identifier", a7.detail)

    def test_a_must_absent_is_fail_and_validation_is_untouched(self):
        spec = variant(needs=[need(term="identifier")])
        record = access(NO_IDENTIFIER, fixtures=EXAMPLE, profile_maps=MAPS, contracts=CONTRACTS, contract=spec)
        self.assertEqual(record.compatibility["status"], "FAIL")
        other = access(NO_IDENTIFIER, fixtures=EXAMPLE, profile_maps=MAPS, contracts=CONTRACTS, contract=variant())
        self.assertEqual(record.validation, other.validation)   # the contract does not change validation


if __name__ == "__main__":
    unittest.main()
