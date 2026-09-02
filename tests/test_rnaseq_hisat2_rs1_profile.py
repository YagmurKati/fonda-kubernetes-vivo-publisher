import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "examples" / "rnaseq-hisat2-rs1"


class RnaSeqHisat2Rs1ProfileTests(unittest.TestCase):
    def test_profile_pins_source_images_and_resume_policy(self) -> None:
        env = (PROFILE / "publisher.env.example").read_text(encoding="utf-8")

        self.assertIn(
            'WORKFLOW_REPO_URL="https://github.com/Nine-s/nextflow_RS1_hisat2_new"',
            env,
        )
        self.assertIn(
            'WORKFLOW_NAME="RNA-seq analysis workflow (Hisat2, RS1)"', env
        )
        self.assertIn(
            'GIT_COMMIT="6b7688c7cab3c0bdb39e0e228ceab2bac31e2caa"',
            env,
        )
        self.assertEqual(env.count("@sha256:"), 5)
        self.assertIn('INCLUDE_CACHED_ORIGIN_METRICS="1"', env)
        self.assertIn('REQUIRE_SUCCEEDED="0"', env)
        self.assertIn('CARBON_SOURCE="electricity-maps-latest"', env)

    def test_profile_uses_reproduction_evidence_layout(self) -> None:
        env = (PROFILE / "publisher.env.example").read_text(encoding="utf-8")

        self.assertIn(
            'TRACE_PATH_TEMPLATE="/workspace/results/{run_id}/trace-{run_id}.txt"',
            env,
        )
        self.assertIn(
            'CONSOLE_LOG_PATH_TEMPLATE="/workspace/results/{run_id}/nextflow-{run_id}.log"',
            env,
        )
        self.assertIn(
            'DEBUG_LOG_PATH="/workspace/results/{run_id}/nextflow-debug-{run_id}.log"',
            env,
        )
        self.assertIn(
            'CODE_PATH="/workspace/rnaseq-hisat2-rs1/source"', env
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

    def test_checksum_manifest_matches_the_reproduction_repository(self) -> None:
        profile_checksums = (PROFILE / "input-SHA256SUMS").read_text(
            encoding="utf-8"
        )
        self.assertEqual(len(profile_checksums.strip().splitlines()), 9)
        self.assertIn(
            "0fbc916c746e1a71252d619505cde1d89824a179245492e5c41f598c50b6e10a",
            profile_checksums,
        )


if __name__ == "__main__":
    unittest.main()
