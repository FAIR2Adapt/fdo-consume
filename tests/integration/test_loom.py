"""The current Knowledge Loom format (no profile declared on the root), read through the Loom map on request."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
os.environ["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + os.environ.get("PYTHONPATH", "")

from fdo_consume import consume  # noqa: E402
FIXTURE_CONTRACTS = str(Path(__file__).resolve().parents[2] / "fixtures" / "contracts")
FIXTURE_MAPS = str(Path(__file__).resolve().parents[2] / "fixtures" / "maps")

PID = "https://example.org/synthetic/loom-current-format"
CRATE = {"@context": ["https://w3id.org/ro/crate/1.1/context", {"skos": "http://www.w3.org/2004/02/skos/core#"},
                      {"rdfs": "http://www.w3.org/2000/01/rdf-schema#"}, {"loom": "https://knowledgeloom.science/"},
                      {"Statement": "loom:Statement", "concepts": "loom:concepts", "notation": "loom:notation",
                       "rdfs:label": "http://www.w3.org/2000/01/rdf-schema#label", "skos:Concept": "http://www.w3.org/2004/02/skos/core#Concept"}],
         "@graph": [
             {"@id": "ro-crate-metadata.json", "@type": "CreativeWork", "about": {"@id": "./"}, "conformsTo": {"@id": "https://w3id.org/ro/crate/1.1"}},
             {"@id": "./", "@type": "Dataset", "name": "Synthetic record", "description": "SYNTHETIC test record in the current Loom format.",
              "author": [{"@id": "#p1"}], "datePublished": "2026-10-11T10:00:00+00:00", "isBasedOn": [{"@id": "#src"}],
              "license": {"@id": "https://creativecommons.org/licenses/by/4.0/"}, "status": "published", "about": ["Climate adaptation"],
              "hasPart": [{"@id": "out.geojson"}]},
             {"@id": "#p1", "@type": "Person", "name": "Synthetic Author"},
             {"@id": "#src", "@type": "Dataset", "name": "Synthetic source"},
             {"@id": "out.geojson", "@type": "File", "name": "an output", "encodingFormat": "application/geo+json"},
             {"@id": "#c1", "@type": ["skos:Concept"], "rdfs:label": "Pluvial flooding"},
             {"@id": "#s1", "@type": ["Statement"], "rdfs:label": "A synthetic statement.", "notation": "LinguisticStatement", "concepts": [{"@id": "#c1"}]},
         ]}


class CurrentLoomFormatTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        (Path(self.tmp.name) / "objects" / "r").mkdir(parents=True)
        (Path(self.tmp.name) / "objects" / "r" / "ro-crate-metadata.json").write_text(json.dumps(CRATE))
        (Path(self.tmp.name) / "pids.json").write_text(json.dumps({PID: {"fixture": "r"}}))

    def tearDown(self):
        self.tmp.cleanup()

    def test_without_being_told_the_record_is_read_by_the_default_map_and_has_no_statements(self):
        result = consume(PID, "knowledge-record-v1", recorded_dir=self.tmp.name, contracts=FIXTURE_CONTRACTS)
        self.assertIsNone(result.record.descriptor["map_used"])  # fallback describer, no map
        # without profile= the statements are not read
        self.assertEqual([e for e in result.binding["entities"] if e["type"] == "Statement"], [])

    def test_told_to_read_it_as_a_loom_record_it_gives_statements_author_names_and_files(self):
        result = consume(PID, "knowledge-record-v1", recorded_dir=self.tmp.name, profile="knowledge-loom-0.1.0", contracts=FIXTURE_CONTRACTS)
        self.assertTrue(result.is_usable, result.diagnostics)
        self.assertEqual(result.statuses["validation"], "INDETERMINATE")  # presence check passed
        fields = result.binding["object"]["fields"]
        self.assertEqual(fields["author_name"], ["Synthetic Author"])
        self.assertEqual(fields["status"], "published")
        self.assertEqual([e["fields"]["label"] for e in result.binding["entities"] if e["type"] == "Statement"], ["A synthetic statement."])
        self.assertEqual([r["id"] for r in result.binding["resources"]], ["out.geojson"])
        self.assertTrue(any("profile_selected" in s.name or s.id == "P2" for s in result.record.steps))


if __name__ == "__main__":
    unittest.main()
