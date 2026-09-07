import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "examples" / "rnaseq-salmon-rs2"


class RnaSeqSalmonRs2ProfileTests(unittest.TestCase):
    def test_profile_pins_source_images_and_defaults_to_a_fresh_run(self) -> None:
        env = (PROFILE / "publisher.env.example").read_text(encoding="utf-8")

        self.assertIn(
            'WORKFLOW_REPO_URL="https://github.com/Nine-s/nextflow_RS2_salmon"',
            env,
        )
        self.assertIn(
            'GIT_COMMIT="2728711d295a2533d1c973dfe010b2adc080655a"',
            env,
        )
        self.assertEqual(env.count("@sha256:"), 4)
        self.assertIn('NS="REPLACE_ME"', env)
        self.assertIn('PVC_NAME="REPLACE_ME"', env)
        self.assertIn('SERVICE_ACCOUNT="REPLACE_ME"', env)
        self.assertIn('CODE_PATH="REPLACE_ME"', env)
        self.assertIn('RUN_OPERATOR_URI="REPLACE_ME"', env)
        self.assertIn('INCLUDE_CACHED_ORIGIN_METRICS="0"', env)
        self.assertIn('REQUIRE_SUCCEEDED="1"', env)
        self.assertIn('CARBON_SOURCE="electricity-maps-latest"', env)

    def test_readme_links_run_and_records_runtime_provenance(self) -> None:
        readme = (PROFILE / "README.md").read_text(encoding="utf-8")

        self.assertIn("published example in FONDA VIVO", readme)
        self.assertIn("sample-qualified", readme)
        self.assertIn("task.cpus", readme)
        self.assertIn("summary.energy_pod_count", readme)
        self.assertNotIn("| Date |", readme)

    def test_input_metadata_and_checksums_cover_the_published_inputs(self) -> None:
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

        checksums = (PROFILE / "input-SHA256SUMS").read_text(encoding="utf-8")
        self.assertEqual(len(checksums.strip().splitlines()), 9)

    def test_publication_receipt_matches_the_published_turtle(self) -> None:
        receipt = json.loads(
            (
                PROFILE
                / "SALMON-RS2-RUN01-20260907T211344Z.published.json"
            ).read_text(encoding="utf-8")
        )

        self.assertEqual(receipt["http_status"], 200)
        self.assertEqual(receipt["attempts"], 1)
        self.assertEqual(
            receipt["ttl_sha256"],
            "12905212ac156a814a5987d20a4cae19e3aeb3a109b0804fc75899ef19c9e6c8",
        )


if __name__ == "__main__":
    unittest.main()
