import unittest
from pathlib import Path


class ArchivePublishScriptTests(unittest.TestCase):
    def setUp(self) -> None:
        scripts = Path(__file__).resolve().parents[1] / "scripts"
        self.script = (scripts / "archive-publish-run.sh").read_text(
            encoding="utf-8"
        )
        self.configure = (scripts / "configure-hu-box.sh").read_text(
            encoding="utf-8"
        )

    def test_reader_mounts_source_pvc_read_only(self) -> None:
        self.assertIn("readOnly: true", self.script)
        self.assertIn("claimName: $PVC_NAME", self.script)

    def test_upload_creates_public_link_then_republishes_run(self) -> None:
        self.assertIn("/api/v2.1/share-links/", self.script)
        self.assertIn('--run-trace-archive "$share_url"', self.script)
        self.assertIn("FORCE_REPUBLISH=1", self.script)

    def test_bundle_has_manifest_checksums_and_privacy_scan(self) -> None:
        self.assertIn('root / "MANIFEST.json"', self.script)
        self.assertIn('root / "SHA256SUMS"', self.script)
        self.assertIn('root / "PRIVACY-SCAN.txt"', self.script)
        self.assertNotIn('"${run_dir#/}"', self.script)
        self.assertIn('"${trace_file#/}"', self.script)

    def test_configuration_keeps_token_and_settings_private(self) -> None:
        self.assertIn('chmod 600 "$token_file"', self.configure)
        self.assertIn('chmod 600 "$hu_config"', self.configure)
        self.assertIn("Select destination library number", self.configure)


if __name__ == "__main__":
    unittest.main()
