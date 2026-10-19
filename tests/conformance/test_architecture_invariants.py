"""Architecture invariants: one snapshot per multi-contract call, no profile code in Python,
INDETERMINATE never reported as PASS, validation never blocks delivery, identity only by explicit rules."""
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from fdo_consume import consume, consume_for_contracts  # noqa: E402
from fdo_consume import registry  # noqa: E402
from fdo_consume.core import Located, judge, sha256_bytes  # noqa: E402
from fdo_consume.sources.recorded import locate_recorded  # noqa: E402
FIXTURE_CONTRACTS = str(Path(__file__).resolve().parents[2] / "fixtures" / "contracts")
FIXTURE_MAPS = str(Path(__file__).resolve().parents[2] / "fixtures" / "maps")

RECORDED = str(ROOT / "fixtures" / "cca-demo")
STAND = "https://example.org/stand-in/"
DATA = STAND + "hamburg-cca-profile-demo"
LOOM = STAND + "hamburg-loom-record"
LOOM_MAP = "knowledge-loom-0.1.0"
EXAMPLE = str(ROOT / "fixtures" / "example-profile")
MAPS = str(ROOT / "fixtures" / "example-profile" / "maps")
CONTRACTS = str(ROOT / "fixtures" / "example-profile" / "contracts")
FULL = "https://example.org/object/full"
NO_FINDINGS = "https://example.org/object/no-findings"
CONTEXT = "https://w3id.org/ro/crate/1.2/context"
COLLECTION = {"contract_id": "collection-test", "version": 1, "consumer": {"service": "test", "capability": "list the members of a collection"},
              "needs": [{"term": "title", "level": "must"}, {"term": "members", "level": "must"}]}


def recorded_folder(tmp: str, pid: str, root: dict) -> str:
    crate = {"@context": CONTEXT, "@graph": [
        {"@id": "ro-crate-metadata.json", "@type": "CreativeWork", "about": {"@id": "./"},
         "conformsTo": {"@id": "https://w3id.org/ro/crate/1.2"}},
        dict({"@id": "./", "@type": "Dataset"}, **root)]}
    (Path(tmp) / "objects" / "x").mkdir(parents=True)
    (Path(tmp) / "objects" / "x" / "ro-crate-metadata.json").write_text(json.dumps(crate))
    (Path(tmp) / "pids.json").write_text(json.dumps({pid: {"fixture": "x"}}))
    return tmp


class ArchitectureInvariantsTest(unittest.TestCase):

    def test_loom_record_supports_claims_not_map_without_data_evidence(self):
        claims = consume(LOOM, "cs3-claims-v1", recorded_dir=RECORDED, profile=LOOM_MAP, contracts=FIXTURE_CONTRACTS)
        layer = consume(LOOM, "map-panel-v1", recorded_dir=RECORDED, profile=LOOM_MAP, contracts=CONTRACTS)
        self.assertTrue(claims.is_usable, claims.diagnostics)
        self.assertEqual((layer.record.outcome, layer.record.error), ("ok", None))   # a valid request, not a contract error
        self.assertIn(layer.statuses["compatibility"], ("FAIL", "INDETERMINATE"))
        self.assertTrue(any(d["code"].startswith("A7") for d in layer.diagnostics), layer.diagnostics)
        self.assertFalse(layer.is_usable)
        self.assertIsNone(layer.binding)

    def test_the_package_ships_no_contract_and_every_fixture_contract_loads(self):
        from fdo_consume.contracts import load_contract
        import fdo_consume
        self.assertEqual(list(Path(fdo_consume.__file__).parent.rglob("contracts/**/*.yaml")), [])
        names = sorted(p.stem for p in Path(FIXTURE_CONTRACTS).glob("*.yaml"))
        self.assertTrue(names)
        for name in names:
            with self.subTest(contract=name):
                self.assertTrue(load_contract(name, folder=FIXTURE_CONTRACTS, profile_maps=FIXTURE_MAPS))

    def test_same_object_multiple_contracts_uses_one_snapshot(self):
        calls = []

        @registry.register("locator", "counted-recorded")
        def counted(pid, options, limits):
            calls.append(pid)
            return locate_recorded(pid, options, limits)

        results = consume_for_contracts(FULL, ["metadata-panel-v1", "claims-panel-v1", "map-panel-v1"],
                                        recorded_dir=EXAMPLE, profile_maps=MAPS, contracts=CONTRACTS, source="counted-recorded")
        self.assertEqual(calls, [FULL])
        hashes = {r.record.crate_sha256 for r in results.values()}
        self.assertEqual(len(hashes), 1)
        self.assertTrue(all("snapshot reused" in r.record.steps[1].detail for r in results.values()))

    def test_a_changing_source_still_gives_one_snapshot(self):
        versions = iter(range(100))

        @registry.register("locator", "changing")
        def changing(pid, options, limits):
            crate = {"@context": CONTEXT, "@graph": [
                {"@id": "ro-crate-metadata.json", "@type": "CreativeWork", "about": {"@id": "./"}},
                {"@id": "./", "@type": "Dataset", "identifier": pid, "name": f"version {next(versions)}"}]}
            data = bytes(json.dumps(crate), "utf-8")
            return Located(pid, crate, [pid], sha256_bytes(data), len(data))

        pid = "https://example.org/synthetic/changing"
        results = consume_for_contracts(pid, ["card", "map-layer"], source="changing", contracts=FIXTURE_CONTRACTS)
        self.assertEqual(len({r.record.crate_sha256 for r in results.values()}), 1)

    def test_indeterminate_never_becomes_pass(self):
        self.assertEqual(judge(["PASS", "INDETERMINATE", "PASS"]), "INDETERMINATE")
        self.assertEqual(judge(["PARTIAL", "INDETERMINATE"]), "INDETERMINATE")
        result = consume(LOOM, "map-panel-v1", recorded_dir=RECORDED, contracts=CONTRACTS)
        a7 = [s for s in result.record.steps if s.id == "A7"][0]
        self.assertEqual(a7.status, "INDETERMINATE")
        self.assertIn(result.statuses["compatibility"], ("INDETERMINATE", "FAIL"))   # FAIL ranks above INDETERMINATE
        self.assertFalse(result.is_usable)

    def test_new_consumer_requires_no_core_change(self):
        import yaml
        contract = {"contract_id": "new-consumer-v1", "version": 1,
                    "consumer": {"service": "a new consumer", "capability": "show a title"},
                    "source": {"repository": "new-consumer", "path": "app.py", "reviewed": "2026-10-12"},
                    "needs": [{"term": "title", "level": "must", "source": "app.py header", "reason": "the page has a heading"}]}
        before = {p: p.read_bytes() for p in (ROOT / "src").rglob("*") if p.is_file() and "__pycache__" not in p.parts}
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "new-consumer-v1.yaml").write_text(yaml.safe_dump(contract), encoding="utf-8")
            result = consume(DATA, "new-consumer-v1", recorded_dir=RECORDED, contracts=tmp)
        self.assertTrue(result.is_usable, result.diagnostics)
        after = {p: p.read_bytes() for p in (ROOT / "src").rglob("*") if p.is_file() and "__pycache__" not in p.parts}
        self.assertEqual(before, after)

    def test_profile_mapping_contains_no_profile_specific_python(self):
        specific = re.compile(r"cc-crate|cca-crate|knowledge-?loom|knowledgeloom", re.I)
        hits = [f"{p.relative_to(ROOT)}:{n}" for p in (ROOT / "src").rglob("*.py")
                for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1) if specific.search(line)]
        self.assertEqual(hits, [])

    def test_validation_fail_does_not_block_delivery(self):
        pid = "https://example.org/synthetic/no-description"
        with tempfile.TemporaryDirectory() as tmp:
            folder = recorded_folder(tmp, pid, {"identifier": pid, "name": "Synthetic, no description",
                                                "conformsTo": {"@id": "https://w3id.org/cca-crate-profile/0.9"}})
            result = consume(pid, "cs3-metadata-v1", recorded_dir=folder, contracts=FIXTURE_CONTRACTS)
        self.assertEqual(result.statuses["validation"], "FAIL")
        self.assertIn(result.statuses["compatibility"], ("PASS", "PARTIAL"))
        self.assertEqual(result.statuses["delivery"], "PASS")
        self.assertTrue(result.is_usable)

    def test_compatibility_fail_blocks_delivery(self):
        result = consume(DATA, COLLECTION, recorded_dir=RECORDED)
        self.assertEqual(result.statuses["compatibility"], "FAIL")
        self.assertIsNone(result.binding)
        self.assertIn("compatibility", result.record.stopped)

    def test_identity_needs_an_explicit_rule(self):
        uuid = "0a1b2c3d-0000-4000-8000-00000000abcd"
        cases = {
            "http://example.org/a": "https://example.org/a",
            "https://site-a.example/object/" + uuid: "https://site-b.example/object/" + uuid,
        }
        for asked, stated in cases.items():
            with self.subTest(asked=asked), tempfile.TemporaryDirectory() as tmp:
                result = consume(asked, "card", recorded_dir=recorded_folder(tmp, asked, {"identifier": stated, "name": "x"}), contracts=FIXTURE_CONTRACTS)
                o1 = [s for s in result.record.steps if s.id == "O1"][0]
                self.assertEqual(o1.status, "INDETERMINATE")
                self.assertNotEqual(result.statuses["resolution"], "PASS")
        with tempfile.TemporaryDirectory() as tmp:
            asked = "https://doi.org/10.1234/ABC"
            result = consume(asked, "card", recorded_dir=recorded_folder(tmp, asked, {"identifier": "doi:10.1234/abc", "name": "x"}), contracts=FIXTURE_CONTRACTS)
            self.assertEqual([s for s in result.record.steps if s.id == "O1"][0].status, "PASS")


class AssertionConceptTest(unittest.TestCase):
    """A claims panel needs one assertion; an example Finding and a Loom Statement both provide Assertion."""

    def test_claims_contract_names_only_the_canonical_concept(self):
        import yaml
        for name in ("cs3-claims-v1",):
            spec = yaml.safe_load((Path(FIXTURE_CONTRACTS) / f"{name}.yaml").read_text())
            with self.subTest(contract=name):
                self.assertEqual([n["term"] for n in spec["needs"]], ["Assertion"])
                self.assertNotIn("profile_additions", spec)

    def test_example_finding_alone_satisfies_the_claims_contract(self):
        result = consume(FULL, "claims-panel-v1", recorded_dir=EXAMPLE, profile_maps=MAPS, contracts=CONTRACTS)
        a7 = [s for s in result.record.steps if s.id == "A7"][0]
        self.assertEqual((a7.status, result.notes), ("PASS", []))
        self.assertTrue(result.is_usable)

    def test_loom_statement_alone_satisfies_the_claims_contract(self):
        result = consume(LOOM, "cs3-claims-v1", recorded_dir=RECORDED, profile=LOOM_MAP, contracts=FIXTURE_CONTRACTS)
        a7 = [s for s in result.record.steps if s.id == "A7"][0]
        self.assertEqual((a7.status, result.notes), ("PASS", []))
        self.assertTrue(result.is_usable)

    def test_one_representation_is_enough_when_a_map_defines_both(self):
        import yaml
        both = {"id": "both-assertions", "status": "test", "overlay": True, "source": "test", "selects": [],
                "extends": "example-panels-1.0",
                "entities": {"Remark": {"type": "https://example.org/terms/Remark", "provides": ["Assertion"],
                                        "fields": {"text": {"iri": "https://example.org/terms/text", "level": "should"}}}}}
        with tempfile.TemporaryDirectory() as tmp:
            for f in Path(MAPS).glob("*.yaml"):
                (Path(tmp) / f.name).write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
            (Path(tmp) / "both.yaml").write_text(yaml.safe_dump(both), encoding="utf-8")
            result = consume(FULL, "claims-panel-v1", recorded_dir=EXAMPLE, profile_maps=tmp, contracts=CONTRACTS, profile_overlay="both-assertions")
        a7 = [s for s in result.record.steps if s.id == "A7"][0]
        self.assertEqual(a7.status, "PASS", a7.detail)

    def test_no_assertion_fails_the_claims_contract(self):
        result = consume(NO_FINDINGS, "claims-panel-v1", recorded_dir=EXAMPLE, profile_maps=MAPS, contracts=CONTRACTS)
        self.assertEqual(result.statuses["compatibility"], "FAIL")
        self.assertFalse(result.is_usable)

    def test_without_a_map_that_provides_assertion_the_result_is_indeterminate(self):
        result = consume(DATA, "cs3-claims-v1", recorded_dir=RECORDED, contracts=FIXTURE_CONTRACTS)
        self.assertEqual(result.statuses["compatibility"], "INDETERMINATE")


if __name__ == "__main__":
    unittest.main()
