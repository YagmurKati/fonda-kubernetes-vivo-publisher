import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "examples" / "spark-wordcount-fs"
SUMMARY_PATH = PROFILE / "publication-summary.json"


class SparkWordCountProfileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))

    def test_records_successful_publication_and_source(self) -> None:
        self.assertEqual(self.summary["publication"]["http_status"], 200)
        self.assertEqual(self.summary["publication"]["attempts"], 1)
        self.assertRegex(self.summary["publication"]["ttl_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(
            self.summary["source"]["commit"],
            "98518a04e9b6deb916fefce536f4de67afd5ce7a",
        )

    def test_run_operator_is_not_asserted(self) -> None:
        attribution = self.summary["attribution"]
        self.assertFalse(attribution["run_operator_asserted"])
        self.assertEqual(attribution["responsible_researcher"]["name"], "Soeren Becker")

    def test_public_profile_excludes_private_infrastructure(self) -> None:
        public_text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted(PROFILE.iterdir())
            if path.is_file()
        )
        self.assertNotIn("Yagmur", public_text)
        self.assertNotIn("runOperator", public_text)
        self.assertIsNone(re.search(r"\b(?:10|141|172)\.(?:\d{1,3}\.){2}\d{1,3}\b", public_text))


if __name__ == "__main__":
    unittest.main()
