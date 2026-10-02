import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "collector"))
sys.path.insert(0, str(ROOT / "tests"))
import collect_slurm_job_metadata as slurm  # noqa: E402
import test_slurm_collector as fixtures  # noqa: E402

SCRIPT = ROOT / "examples" / "hpc-at-hu-slurm" / "archive-slurm-job.sh"
REPO_ID = "12345678-1234-1234-1234-123456789abc"
JOB_ID = "1595874"


class FakeHuBox(BaseHTTPRequestHandler):
    """Answers the four HU-Box (Seafile) calls the archive script makes."""

    requests = []

    def log_message(self, *args):
        pass

    def _send(self, body, status=200):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        FakeHuBox.requests.append(("GET", self.path, self.headers.get("Authorization"), b""))
        base = f"http://127.0.0.1:{self.server.server_port}"
        if self.path.startswith(f"/api2/repos/{REPO_ID}/upload-link/"):
            self._send(f"{base}/upload/abc")
        elif self.path == "/f/share123/":
            self._send(b"archive")
        else:
            self._send({"error": "not found"}, 404)

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        FakeHuBox.requests.append(("POST", self.path, self.headers.get("Authorization"), body))
        base = f"http://127.0.0.1:{self.server.server_port}"
        if self.path.startswith("/upload/abc"):
            self._send([{"name": "ok"}])
        elif self.path == "/api/v2.1/share-links/":
            self._send({"link": f"{base}/f/share123/"})
        else:
            self._send({"error": "not found"}, 404)


class ArchiveSlurmJobTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.work = Path(self.tmp.name) / "work"
        self.evidence = self.home / "vivo-evidence" / JOB_ID
        fixtures.write_evidence(self.evidence)
        (self.evidence / "node-info.tsv").write_text(fixtures.NODE_INFO)
        info = self.work / f"results-{JOB_ID}" / "pipeline_info"
        info.mkdir(parents=True)
        (self.work / ".nextflow.log").write_text(fixtures.NF_LOG)
        (self.work / f"slurm-{JOB_ID}.out").write_text("N E X T F L O W\n")
        (info / "execution_trace_2026-10-01_17-35-45.txt").write_text(fixtures.TRACE)
        (info / "execution_report_2026-10-01_17-35-45.html").write_text("<html>report</html>")
        (info / "params_2026-10-01_17-35-50.json").write_text("{}")
        (self.work / f"results-{JOB_ID}" / "result.tif").write_text("scientific result")
        sacct = Path(self.tmp.name) / "sacct.txt"
        sacct.write_text(fixtures.SACCT)
        self.publication = self.evidence / "publication-20261001T160000Z"
        with mock.patch("sys.stdout", io.StringIO()):
            slurm.main(["--job-id", JOB_ID, "--evidence-dir", str(self.evidence),
                        "--output-dir", str(self.publication), "--sacct-file", str(sacct),
                        "--workflow-uri", fixtures.WORKFLOW, "--run-operator-uri", fixtures.OPERATOR,
                        "--nextflow-log", str(self.work / ".nextflow.log"),
                        "--nextflow-trace", str(info / "execution_trace_2026-10-01_17-35-45.txt"),
                        "--no-carbon"])
        ttl = (self.publication / "run.ttl").read_bytes()
        (self.publication / "run.published.json").write_text(json.dumps({
            "ttl_sha256": hashlib.sha256(ttl).hexdigest(), "http_status": 200}))
        (self.home / ".fonda-vivo").mkdir()
        (self.home / ".fonda-vivo" / "slurm.env").write_text(f'NEXTFLOW_LAUNCH_DIR="{self.work}"\n')

        FakeHuBox.requests = []
        self.server = HTTPServer(("127.0.0.1", 0), FakeHuBox)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        token = self.home / "hu-box-token"
        token.write_text("box-token\n")
        self.hu_config = self.home / "hu-box.env"
        self.hu_config.write_text(
            f"HU_BOX_SERVER_URL=http://127.0.0.1:{self.server.server_port}\n"
            f"HU_BOX_REPOSITORY_ID={REPO_ID}\nHU_BOX_PARENT_DIR=/\n"
            f"HU_BOX_TRACE_PREFIX=fonda-workflow-traces/hpc\nHU_BOX_API_TOKEN_FILE={token}\n")

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def run_script(self, *args):
        env = dict(os.environ, HOME=str(self.home), HU_BOX_CONFIG_FILE=str(self.hu_config))
        env.pop("FONDA_SLURM_ENV", None)
        env.pop("EVIDENCE_ROOT", None)
        return subprocess.run([str(SCRIPT), JOB_ID, *args], env=env, cwd=self.tmp.name,
                              capture_output=True, text=True, timeout=60)

    def bundle(self):
        return sorted(self.evidence.glob("trace-archive-*/bundle"))[-1]

    def test_package_only_builds_a_checked_bundle_without_network(self):
        result = self.run_script("--package-only")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Package-only mode", result.stdout)
        self.assertEqual(FakeHuBox.requests, [])
        bundle = self.bundle()
        names = sorted(str(p.relative_to(bundle)) for p in bundle.rglob("*") if p.is_file())
        for expected in ("MANIFEST.json", "PRIVACY-SCAN.txt", "SHA256SUMS", "nextflow/nextflow.log",
                         "nextflow/execution_trace_2026-10-01_17-35-45.txt",
                         "nextflow/execution_report_2026-10-01_17-35-45.html",
                         "nextflow/params_2026-10-01_17-35-50.json", "slurm/job-info.tsv",
                         "slurm/node-info.tsv", "slurm/node-samples.tsv", f"slurm/slurm-{JOB_ID}.out",
                         "vivo/run.ttl", "vivo/summary.json", "vivo/run.published.json"):
            self.assertIn(expected, names)
        self.assertFalse(any("result.tif" in name for name in names))
        self.assertIn("No credential-shaped values", (bundle / "PRIVACY-SCAN.txt").read_text())
        manifest = json.loads((bundle / "MANIFEST.json").read_text())
        self.assertTrue(manifest["vivo_run_uri"].endswith("hpc-at-hu-slurm-1595874-20261001t153539"))
        for line in (bundle / "SHA256SUMS").read_text().splitlines():
            digest, name = line.split("  ", 1)
            self.assertEqual(hashlib.sha256((bundle / name).read_bytes()).hexdigest(), digest)
        archive = next(bundle.parent.glob("*.tar.gz"))
        with tarfile.open(archive) as tar:
            self.assertIn("./vivo/run.ttl", tar.getnames())
        self.assertFalse((self.evidence / "trace-archive-url.txt").exists())

    def test_credential_shaped_values_stop_the_upload(self):
        (self.work / ".nextflow.log").write_text(fixtures.NF_LOG + "password = hunter2hunter2\n")
        result = self.run_script("--no-vivo")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Privacy scan found 1", result.stderr)
        self.assertEqual(FakeHuBox.requests, [])
        self.assertIn("nextflow/nextflow.log:", (self.bundle() / "PRIVACY-SCAN.txt").read_text())

    def test_upload_creates_a_share_link_and_keeps_it_for_later_publications(self):
        result = self.run_script("--no-vivo")
        self.assertEqual(result.returncode, 0, result.stderr)
        link = f"http://127.0.0.1:{self.server.server_port}/f/share123/"
        self.assertIn(f"Public HU-Box trace link: {link}", result.stdout)
        self.assertEqual((self.evidence / "trace-archive-url.txt").read_text().strip(), link)
        methods = [(method, path.split("?")[0]) for method, path, _, _ in FakeHuBox.requests]
        self.assertEqual(methods, [("GET", f"/api2/repos/{REPO_ID}/upload-link/"), ("POST", "/upload/abc"),
                                   ("POST", "/api/v2.1/share-links/"), ("GET", "/f/share123/")])
        self.assertEqual(FakeHuBox.requests[0][2], "Token box-token")
        upload = FakeHuBox.requests[1][3]
        self.assertIn(b"fonda-workflow-traces/hpc/hpc-at-hu-slurm-1595874-20261001t153539", upload)
        share = json.loads(FakeHuBox.requests[2][3])
        self.assertEqual(share["permissions"], {"can_edit": False, "can_download": True})
        self.assertTrue(share["path"].startswith(
            "/fonda-workflow-traces/hpc/hpc-at-hu-slurm-1595874-20261001t153539/"))

    def test_an_unpublished_or_removed_job_is_refused(self):
        receipt = self.publication / "run.published.json"
        data = json.loads(receipt.read_text())
        receipt.write_text(json.dumps(dict(data, removed_at="2026-10-02T00:00:00+00:00")))
        result = self.run_script("--package-only")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("removed from VIVO", result.stderr)
        receipt.unlink()
        result = self.run_script("--package-only")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no publication receipt", result.stderr)

    def test_collector_adds_the_saved_link(self):
        with mock.patch("sys.stdout", io.StringIO()):
            slurm.main(["--job-id", JOB_ID, "--evidence-dir", str(self.evidence),
                        "--output-dir", str(self.evidence / "publication-again"),
                        "--sacct-file", str(Path(self.tmp.name) / "sacct.txt"),
                        "--workflow-uri", fixtures.WORKFLOW, "--run-operator-uri", fixtures.OPERATOR,
                        "--no-carbon", "--trace-archive", "https://box.hu-berlin.de/f/abc/"])
        ttl = (self.evidence / "publication-again" / "run.ttl").read_text()
        self.assertIn('rm:traceArchive "https://box.hu-berlin.de/f/abc/"^^xsd:anyURI', ttl)


if __name__ == "__main__":
    unittest.main()
