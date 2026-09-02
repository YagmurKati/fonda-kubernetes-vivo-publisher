import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
PROFILE_NAMES = (
    "a2-mg4",
    "force2nxf",
    "geoflow",
    "popinsnake",
    "rnaseq-hisat2-rs1",
    "rnaseq-hisat2-rs2",
    "rnaseq-salmon-rs1",
    "rnaseq-star-rs1",
)


class ProfileGuideTests(unittest.TestCase):
    def test_every_profile_links_vivo_and_documents_removal(self) -> None:
        for profile_name in PROFILE_NAMES:
            with self.subTest(profile=profile_name):
                readme = (EXAMPLES / profile_name / "README.md").read_text(
                    encoding="utf-8"
                )
                self.assertIn("published example in FONDA VIVO", readme)
                self.assertIn("## 5. Remove a publication", readme)
                self.assertIn("remove-run.sh PUBLICATION_ID --dry-run", readme)
                self.assertIn("remove-run.sh PUBLICATION_ID", readme)

    def test_profiles_do_not_report_example_run_statistics(self) -> None:
        forbidden = re.compile(
            r"kg CO2e|[0-9][0-9,.]* kWh|CPU-seconds|"
            r"completed on 2026|\| Date \||## Tested run|## Verified",
            re.IGNORECASE,
        )
        for profile_name in PROFILE_NAMES:
            with self.subTest(profile=profile_name):
                readme = (EXAMPLES / profile_name / "README.md").read_text(
                    encoding="utf-8"
                )
                self.assertIsNone(forbidden.search(readme))

    def test_profile_templates_do_not_use_one_users_runtime_identity(self) -> None:
        for profile_name in PROFILE_NAMES:
            with self.subTest(profile=profile_name):
                env = (
                    EXAMPLES / profile_name / "publisher.env.example"
                ).read_text(encoding="utf-8")
                self.assertNotIn('NS="yagmur"', env)
                self.assertNotRegex(env, r'RUN_OPERATOR_URI="[^"]*Yagmur')

    def test_main_table_links_all_published_examples(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertEqual(readme.count("[Open in VIVO]"), len(PROFILE_NAMES))


if __name__ == "__main__":
    unittest.main()
