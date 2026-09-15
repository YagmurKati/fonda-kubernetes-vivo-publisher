import hashlib
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "examples" / "nextflow-locality-demo"
SUMMARY_PATH = PROFILE / "publication-summary.json"


class NextflowLocalityDemoProfileTests(unittest.TestCase):
    def test_source_copy_matches_reviewed_commit_blob(self) -> None:
        digest = hashlib.sha256((PROFILE / "demo-dsl2.nf").read_bytes()).hexdigest()
        self.assertEqual(
            digest,
            "f8e077dadb374bea484564aef5a96b4c7acb1ad2f13ff7b9393ae9a27d0e93c9",
        )

    def test_input_dataset_list_is_intentionally_empty(self) -> None:
        value = json.loads((PROFILE / "input_datasets.json").read_text())
        self.assertEqual(value, {"schema_version": 1, "datasets": []})

    def test_driver_and_tasks_have_hard_prototyping_placement(self) -> None:
        manifest = (PROFILE / "k8s-run.yaml").read_text()
        publisher_manifest = (PROFILE / "k8s-publish.yaml").read_text()
        reader_manifest = (PROFILE / "k8s-evidence-reader.yaml").read_text()
        config = (PROFILE / "nextflow.config").read_text()
        self.assertIn("nodeSelector:\n        usedby: prototyping", manifest)
        self.assertIn("requiredDuringSchedulingIgnoredDuringExecution", manifest)
        self.assertIn("nodeSelector: 'usedby=prototyping'", config)
        self.assertIn("requiredDuringSchedulingIgnoredDuringExecution", config)
        self.assertIn(
            "nodeSelector:\n        usedby: prototyping", publisher_manifest
        )
        self.assertIn(
            "requiredDuringSchedulingIgnoredDuringExecution", publisher_manifest
        )
        self.assertIn("nodeSelector:\n    usedby: prototyping", reader_manifest)
        self.assertIn(
            "requiredDuringSchedulingIgnoredDuringExecution", reader_manifest
        )
        self.assertIn("readOnly: true", reader_manifest)
        self.assertNotIn(
            "usedby=yagmur", manifest + config + publisher_manifest + reader_manifest
        )

    def test_public_attribution_has_two_researchers_and_no_operator(self) -> None:
        settings = (PROFILE / "publisher.env.example").read_text()
        match = re.search(r'^RESPONSIBLE_RESEARCHER_URIS="([^"]+)"$', settings, re.M)
        self.assertIsNotNone(match)
        self.assertEqual(len(match.group(1).split(",")), 2)
        self.assertIn("#FabianLehmann", match.group(1))
        self.assertIn("friedrich-tschirpke", match.group(1))
        self.assertIn('RUN_OPERATOR_URI=""', settings)
        self.assertIn('RUN_IDENTITY_SCOPE="fonda"', settings)
        self.assertNotIn("YagmurKati", settings)

        publisher_manifest = (PROFILE / "k8s-publish.yaml").read_text()
        self.assertIn("RUN_OPERATOR_URI: \"\"", publisher_manifest)
        self.assertIn("RUN_IDENTITY_SCOPE: fonda", publisher_manifest)
        self.assertIn("grep -c 'rm:responsibleResearcher'", publisher_manifest)
        self.assertRegex(publisher_manifest, r"rm:runOperator\|yagmur")

    def test_successful_publication_summary_is_privacy_clean(self) -> None:
        summary = json.loads(SUMMARY_PATH.read_text())
        receipts = sorted(PROFILE.glob("*.published.json"))
        self.assertEqual(len(receipts), 1)
        receipt = json.loads(receipts[0].read_text())
        self.assertEqual(summary["execution"]["status"], "Succeeded")
        self.assertEqual(summary["execution"]["task_count"], 5)
        self.assertEqual(summary["publication"]["http_status"], 200)
        self.assertEqual(receipt["http_status"], 200)
        self.assertEqual(receipt["ttl_sha256"], summary["publication"]["ttl_sha256"])
        self.assertRegex(summary["publication"]["ttl_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(
            [item["name"] for item in summary["attribution"]["responsible_researchers"]],
            ["Fabian Lehmann", "Friedrich Tschirpke"],
        )
        self.assertFalse(summary["attribution"]["run_operator_asserted"])
        self.assertFalse(summary["privacy"]["operational_namespace_in_public_ttl"])
        self.assertTrue(summary["placement"]["all_recorded_pods_constrained"])
        self.assertEqual(summary["placement"]["allowed_node_count"], 3)


if __name__ == "__main__":
    unittest.main()
