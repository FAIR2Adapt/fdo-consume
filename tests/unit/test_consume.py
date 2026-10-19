"""Public API: names, structured diagnostics and notes, no overall status, CLI."""
import contextlib
import io
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import fdo_consume  # noqa: E402
from fdo_consume import cli, consume, consume_collection, consume_for_contracts  # noqa: E402
from fdo_consume.consume import CollectionConsumptionResult, ConsumptionResult  # noqa: E402
FIXTURE_CONTRACTS = str(Path(__file__).resolve().parents[2] / "fixtures" / "contracts")
FIXTURE_MAPS = str(Path(__file__).resolve().parents[2] / "fixtures" / "maps")

RECORDED = str(ROOT / "fixtures" / "cca-demo")
EXAMPLE = str(ROOT / "fixtures" / "example-profile")
MAPS = str(ROOT / "fixtures" / "example-profile" / "maps")
CONTRACTS = str(ROOT / "fixtures" / "example-profile" / "contracts")
LOOM = "https://example.org/stand-in/hamburg-loom-record"
FULL = "https://example.org/object/full"
COLLECTION = "https://example.org/object/collection"


class SurfaceTest(unittest.TestCase):

    def test_top_level_exports_only_the_public_api_and_its_types(self):
        self.assertEqual(sorted(fdo_consume.__all__), sorted([
            "describe", "consume", "consume_for_contracts", "consume_collection", "ConsumptionResult",
            "CollectionConsumptionResult", "AccessRecord", "AccessError", "Limits"]))


class ResultTest(unittest.TestCase):

    def test_result_fields(self):
        result = consume(FULL, "map-panel-v1", recorded_dir=EXAMPLE, profile_maps=MAPS, contracts=CONTRACTS)
        self.assertIsInstance(result, ConsumptionResult)
        self.assertIs(result.is_usable, True)
        self.assertEqual(set(result.statuses), {"resolution", "validation", "compatibility", "delivery"})
        for d in result.diagnostics:
            self.assertEqual(set(d), {"stage", "code", "status", "message"})
            self.assertIn(d["status"], ("PARTIAL", "FAIL", "INDETERMINATE"))
        self.assertEqual(set(result.summary()), {"contract", "is_usable", "outcome", "stopped", "error", "statuses",
                                                 "diagnostics", "notes", "record_sha256", "contract_sha256",
                                                 "package_version"})

    def test_the_record_has_no_overall_status(self):
        record = consume(FULL, "map-panel-v1", recorded_dir=EXAMPLE, profile_maps=MAPS, contracts=CONTRACTS).record
        self.assertFalse(hasattr(record, "status"))
        self.assertNotIn("status", record.to_dict())
        self.assertNotIn("failures", record.to_dict())

    def test_diagnostics_keep_partial_and_indeterminate_with_their_status(self):
        record = consume(FULL, "map-panel-v1", recorded_dir=EXAMPLE, profile_maps=MAPS, contracts=CONTRACTS).record
        self.assertEqual({(d["code"], d["status"]) for d in record.diagnostics},
                         {(f"{s.id}.{s.name}", s.status) for s in record.steps if s.status != "PASS"})

    def test_notes_come_from_step_data_not_from_the_message_text(self):
        undefined_should = {"contract_id": "needs-a-statement", "version": 1, "consumer": {"service": "test", "capability": "test"},
                    "source": {"repository": "fdo-consume", "path": "tests", "reviewed": "2026-10-12"},
                    "needs": [{"term": "title", "level": "must", "source": "s", "reason": "r"},
                              {"term": "Statement", "level": "should", "source": "s", "reason": "r"}]}
        result = consume(FULL, undefined_should, recorded_dir=EXAMPLE, profile_maps=MAPS, contracts=CONTRACTS)
        a7 = [s for s in result.record.steps if s.id == "A7"][0]
        a7.detail = "reworded"
        self.assertEqual([n["code"] for n in result.notes], ["profile.term_undefined"])
        self.assertIn("Statement", result.notes[0]["terms"])

    def test_validator_reason_has_no_version(self):
        reason = consume(LOOM, "knowledge-record-v1", recorded_dir=RECORDED, contracts=FIXTURE_CONTRACTS).record.validation["validator"]["reason"]
        self.assertEqual(reason, "no authoritative profile validator is configured")

    def test_binding_carries_statuses_and_schema_4(self):
        binding = consume(FULL, "map-panel-v1", recorded_dir=EXAMPLE, profile_maps=MAPS, contracts=CONTRACTS).binding
        self.assertEqual(binding["schema"], "fdo-consume-binding/5")
        self.assertIn("statuses", binding["evidence"])
        self.assertNotIn("answers", binding["evidence"])

    def test_several_contracts(self):
        results = consume_for_contracts(FULL, ["metadata-panel-v1", "map-panel-v1"], recorded_dir=EXAMPLE, profile_maps=MAPS, contracts=CONTRACTS)
        self.assertEqual(list(results), ["metadata-panel-v1", "map-panel-v1"])
        self.assertTrue(results["map-panel-v1"].is_usable)

    def test_collection_names(self):
        found = consume_collection(COLLECTION, "metadata-panel-v1", recorded_dir=EXAMPLE, profile_maps=MAPS, contracts=CONTRACTS)
        self.assertIsInstance(found, CollectionConsumptionResult)
        self.assertEqual(found.collection_record.request["pid"], COLLECTION)
        self.assertIsInstance(found.usable_member_ids, list)
        self.assertLessEqual(set(found.usable_member_ids), set(found.member_ids))
        self.assertFalse(hasattr(found, "usable"))


class CommandLineTest(unittest.TestCase):

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_prog_name(self):
        self.assertEqual(cli.build_parser().prog, "fdo-consume")

    def test_consume_delivers_a_binding(self):
        code, out, _ = self.run_cli("consume", FULL, "--contract", "map-panel-v1", "--recorded-dir", EXAMPLE, "--profile-maps", MAPS, "--contracts", CONTRACTS)
        record = json.loads(out)
        self.assertEqual((code, record["request"]["depth"], record["request"]["want"]), (0, "load", "binding"))

    def test_inspect_stops_at_the_requested_depth(self):
        code, out, _ = self.run_cli("inspect", FULL, "--depth", "describe", "--recorded-dir", EXAMPLE, "--profile-maps", MAPS, "--contracts", CONTRACTS)
        self.assertEqual((code, json.loads(out)["reached"]), (0, "describe"))

    def test_there_is_no_access_command(self):
        with self.assertRaises(SystemExit):
            self.run_cli("access", FULL, "--recorded-dir", EXAMPLE)

class DescribeTest(unittest.TestCase):
    """Reading without a contract: the description and the profile-related statuses; nothing is judged for a consumer."""

    def test_a_record_is_described_by_its_profile_map(self):
        from fdo_consume import describe
        record = describe("https://example.org/stand-in/hamburg-loom-record",
                          recorded_dir=str(Path(__file__).resolve().parents[2] / "fixtures" / "cca-demo"))
        self.assertEqual((record.outcome, record.reached), ("ok", "describe"))
        self.assertEqual(record.descriptor["map_used"], "knowledge-loom-0.1.0")
        self.assertTrue(record.descriptor["name"])
        self.assertEqual(record.resolution["status"], "PASS")
        self.assertEqual((record.compatibility["status"], record.delivery["status"]), ("NOT_ATTEMPTED", "NOT_ATTEMPTED"))

    def test_an_unknown_pid_is_an_error_in_the_record(self):
        from fdo_consume import describe
        record = describe("https://example.org/stand-in/no-such-object",
                          recorded_dir=str(Path(__file__).resolve().parents[2] / "fixtures" / "cca-demo"))
        self.assertNotEqual(record.outcome, "ok")


if __name__ == "__main__":
    unittest.main()
