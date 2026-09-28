import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "publish-local.sh"
SAMPLE_TTL = REPO_ROOT / "examples" / "a2-mg3" / "a2-mg3-20260908.ttl"


class PublishLocalScriptTests(unittest.TestCase):
    def run_script(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(SCRIPT), *arguments],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_dry_run_validates_sample_ttl(self) -> None:
        result = self.run_script(str(SAMPLE_TTL), "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("TTL validated", result.stdout)

    def test_missing_ttl_is_rejected(self) -> None:
        result = self.run_script("does-not-exist.ttl", "--dry-run")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("TTL file is not readable", result.stderr)

    def test_unknown_option_is_rejected(self) -> None:
        result = self.run_script(str(SAMPLE_TTL), "--unknown")
        self.assertEqual(result.returncode, 2)
        self.assertIn("unknown option", result.stderr)


if __name__ == "__main__":
    unittest.main()
