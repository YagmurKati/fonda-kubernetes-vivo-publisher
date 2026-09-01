import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "examples" / "rnaseq-star-rs1"


class RnaSeqStarProfileTests(unittest.TestCase):
    def test_profile_pins_upstream_source_and_all_runtime_images(self) -> None:
        env = (PROFILE / "publisher.env.example").read_text(encoding="utf-8")

        self.assertIn(
            'WORKFLOW_REPO_URL="https://github.com/Nine-s/nextflow_RS1_star"',
            env,
        )
        self.assertIn(
            'GIT_COMMIT="8265c835d8fd76c9bad7b1e2499304929069050b"',
            env,
        )
        self.assertEqual(env.count("@sha256:"), 5)
        self.assertIn('REQUIRE_SUCCEEDED="1"', env)
        self.assertIn('CARBON_SOURCE="fixed"', env)

    def test_profile_uses_per_run_archived_evidence(self) -> None:
        env = (PROFILE / "publisher.env.example").read_text(encoding="utf-8")

        self.assertIn(
            'TRACE_PATH_TEMPLATE="/workspace/results/{run_id}/trace.txt"', env
        )
        self.assertIn(
            'CONSOLE_LOG_PATH_TEMPLATE="/workspace/results/{run_id}/nextflow.log"',
            env,
        )
        self.assertIn(
            'DEBUG_LOG_PATH="/workspace/results/{run_id}/nextflow-debug.log"',
            env,
        )

    def test_input_metadata_names_the_tested_ena_accessions(self) -> None:
        metadata = json.loads(
            (PROFILE / "input_datasets.json").read_text(encoding="utf-8")
        )
        source_urls = {
            url
            for dataset in metadata["datasets"]
            for url in dataset.get("upstream_source_urls", [])
        }

        for accession in ("SRR1509507", "SRR14197369", "SRR14404397"):
            self.assertIn(
                f"https://www.ebi.ac.uk/ena/browser/view/{accession}", source_urls
            )


if __name__ == "__main__":
    unittest.main()
