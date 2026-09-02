import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "examples" / "rnaseq-hisat2-rs2"


class RnaSeqHisat2Rs2ProfileTests(unittest.TestCase):
    def test_profile_is_a_clean_run_template(self) -> None:
        env = (PROFILE / "publisher.env.example").read_text(encoding="utf-8")

        self.assertIn('NS="REPLACE_ME"', env)
        self.assertIn('PVC_NAME="REPLACE_ME"', env)
        self.assertIn('SERVICE_ACCOUNT="REPLACE_ME"', env)
        self.assertIn('CODE_PATH="REPLACE_ME"', env)
        self.assertIn('RUN_OPERATOR_URI="REPLACE_ME"', env)
        self.assertIn('INCLUDE_CACHED_ORIGIN_METRICS="0"', env)
        self.assertIn('REQUIRE_SUCCEEDED="1"', env)
        self.assertIn('INPUT_METADATA_FILE="config/input_datasets.json"', env)

    def test_readme_links_the_published_run_and_checks_energy_coverage(self) -> None:
        readme = (PROFILE / "README.md").read_text(encoding="utf-8")

        self.assertIn("published example in FONDA VIVO", readme)
        self.assertIn("summary.energy_pod_count", readme)
        self.assertIn("summary.energy_estimated", readme)
        self.assertNotIn("| Date |", readme)
        self.assertNotIn("0.098", readme)


if __name__ == "__main__":
    unittest.main()
