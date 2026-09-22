from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "examples/rnaseq-rapl"
sys.path.insert(0, str(ROOT / "collector"))
sys.path.insert(0, str(ROOT / "publisher"))
import collect_rnaseq_rapl_metadata as collector
from publish_vivo import run_owned_resource_iris, turtle_to_insert_update, DEFAULT_GRAPH


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


launcher = load("rapl_launcher", PROFILE / "run.py")
publisher = load("rapl_publisher", PROFILE / "publish.py")


class RaplCounterTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "counter.txt"
        self.start = datetime(2026, 9, 22, 0, 0, tzinfo=timezone.utc).timestamp()

    def integrate(self, content, maximum, begin, end, collector_start=None):
        self.path.write_text(content)
        return collector.integrate_counter(self.path, maximum,
            self.start if collector_start is None else collector_start,
            self.start + begin, self.start + end)

    def test_wrap_and_interpolated_boundaries(self):
        result = self.integrate("900000\n00:00:00\n100000\n00:00:01\n300000\n00:00:02\n", 1000000, .5, 1.5)
        self.assertAlmostEqual(result["energy_joules"], .2)
        self.assertEqual(result["counter_wraps"], 1)

    def test_midnight_rollover(self):
        self.path.write_text("100\n23:59:59\n200\n00:00:00\n300\n00:00:01\n")
        result = collector.integrate_counter(self.path, 1000, self.start - 1, self.start - .5, self.start + .5)
        self.assertAlmostEqual(result["energy_joules"], .0001)

    def test_first_sample_after_midnight(self):
        result = self.integrate("100\n00:00:00\n200\n00:00:01\n", 1000, 0, 1, self.start - .1)
        self.assertAlmostEqual(result["energy_joules"], .0001)

    def test_missing_coverage_gap_and_malformed_samples_fail(self):
        cases = ["100\n00:00:01\n200\n00:00:02\n", "100\n00:00:00\n200\n00:00:06\n",
                 "100\n00:00:00\n200\n", "100\n00:00:00\n200\n00:00:00\n",
                 "100\n00:00:00\n1000\n00:00:01\n"]
        for content in cases:
            with self.subTest(content=content), self.assertRaises(ValueError):
                self.integrate(content, 1000, 0, 1)

    def test_nextflow_cpu_percent_is_not_tenths(self):
        self.assertAlmostEqual(collector.cpu_seconds({"realtime": "209269", "%cpu": "101.9"}), 213.245111)
        with self.assertRaises(ValueError):
            collector.cpu_seconds({"realtime": "1000", "%cpu": "NaN"})


class RaplLauncherTests(unittest.TestCase):
    def test_all_pods_use_only_selected_allowed_node_and_fresh_resources(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "run"
            launcher.prepare(path, "rapl-test-01", "yagmur", "hu-worker-c34")
            base = json.loads((path / "manifests/base.resources.json").read_text())
            config = (path / "runtime/nextflow.config").read_text()
            self.assertIn("values: ['hu-worker-c34']", config)
            self.assertIn("cleanup = false", config)
            self.assertIn("executor.queueSize = 1", config)
            for filename in ("workflow.job.json", "evidence.job.json"):
                obj = json.loads((path / "manifests" / filename).read_text())
                pod = obj["spec"]["template"]["spec"]
                self.assertEqual(pod["nodeSelector"], {"usedby": "prototyping", "kubernetes.io/hostname": "hu-worker-c34"})
                self.assertNotIn("priorityClassName", pod)
                self.assertNotIn("preemptionPolicy", pod)
            role = next(o for o in base["items"] if o["kind"] == "Role")
            self.assertTrue(all(not {"delete", "patch", "update", "*"}.intersection(r["verbs"]) for r in role["rules"]))
            with self.assertRaises(FileExistsError):
                launcher.prepare(path, "rapl-test-01", "yagmur", "hu-worker-c34")
            with self.assertRaises(ValueError):
                launcher.prepare(Path(temporary) / "other", "rapl-test-02", "yagmur", "hu-worker-c50")

    def test_runtime_and_helpers_compile(self):
        for path in list(PROFILE.glob("*.py")) + list((PROFILE / "runtime").glob("*.py")):
            compile(path.read_text(), str(path), "exec")
        for path in (PROFILE / "runtime").glob("*.sh"):
            subprocess.run(["bash", "-n", str(path)], check=True)


class RaplClusterTests(unittest.TestCase):
    def setUp(self):
        self.rows = [{"native_id": "task-" + str(i)} for i in range(4)]
        def pod(name, containers):
            return {"metadata": {"name": name, "namespace": "yagmur", "labels": {
                        "fonda.hu-berlin.de/run-id": "test", "job-name": "driver"}},
                    "spec": {"nodeName": "hu-worker-c34", "nodeSelector": {"usedby": "prototyping"},
                             "containers": [{"name": c, "resources": {"limits": {"cpu": "2"}}} for c in containers]},
                    "status": {"phase": "Succeeded", "containerStatuses": [
                        {"name": c, "imageID": "image@sha256:test", "state": {"terminated": {"exitCode": 0}}} for c in containers]}}
        self.pods = [pod(r["native_id"], ["task"]) for r in self.rows] + [pod("driver", ["nextflow", "rapl-monitor"])]
        self.jobs = [{"metadata": {"name": "driver"}, "status": {"conditions": [{"type": "Complete", "status": "True"}]}}]

    def validate(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / "pods.json").write_text(json.dumps({"items": self.pods}))
            (directory / "jobs.json").write_text(json.dumps({"items": self.jobs}))
            return collector.validate_cluster(directory, self.rows, "hu-worker-c34")

    def test_success_needs_job_and_all_container_exits(self):
        self.assertEqual(self.validate()["job"], "driver")
        self.pods[-1]["status"]["containerStatuses"][-1]["state"]["terminated"]["exitCode"] = 1
        with self.assertRaises(ValueError):
            self.validate()

    def test_wrong_node_rejected(self):
        self.pods[0]["spec"]["nodeName"] = "hu-worker-c50"
        with self.assertRaises(ValueError):
            self.validate()

    def test_different_run_rejected(self):
        self.pods[0]["metadata"]["labels"]["fonda.hu-berlin.de/run-id"] = "someone-else"
        with self.assertRaises(ValueError):
            self.validate()

    def test_missing_container_status_rejected(self):
        self.pods[-1]["status"]["containerStatuses"].pop()
        with self.assertRaises(ValueError):
            self.validate()

    def test_incomplete_job_rejected(self):
        self.jobs[0]["status"]["conditions"][0]["status"] = "False"
        with self.assertRaises(ValueError):
            self.validate()


class RaplMetadataTests(unittest.TestCase):
    def test_run_fields_are_evidence_scoped_and_existing_workflow_is_preserved(self):
        public = json.loads((PROFILE / "publication-summary.json").read_text())
        summary = dict(public, session_id=public["nextflow_session_id"], memory_peak_gb=.486,
                       energy_kwh=public["cpu_package_energy_kwh"], node="hu-worker-c34", job="test",
                       image_ids=[], source_change={"new_sha256": "a" * 64})
        rows = [dict(process=n, realtime="1000", **{"%cpu": "100"}, peak_rss="1024",
                     submit="1790062873000", complete="1790062874000") for n in ("FASTQC", "INDEX", "QUANT", "MULTIQC")]
        ttl, run = collector.build_ttl(summary, rows, [], "b" * 64)
        self.assertEqual(run_owned_resource_iris(ttl)[0], run)
        self.assertEqual(len(run_owned_resource_iris(ttl)), 6)
        update = turtle_to_insert_update(ttl, DEFAULT_GRAPH)
        self.assertNotIn("DELETE", update)
        self.assertNotIn("rm:traceArchive", ttl)
        self.assertNotIn("rm:memoryAvgGB", ttl)
        self.assertNotIn("rm:carbonEmission", ttl)
        workflow_block = next(b for b in ttl.split("\n\n") if b.startswith("<" + collector.WORKFLOW + ">"))
        self.assertNotIn("rm:traceTypes", workflow_block)
        self.assertNotIn("rdfs:label", workflow_block)
        self.assertIn(collector.RESEARCHER, workflow_block)

    def test_existing_page_prevents_publication(self):
        response = mock.MagicMock()
        response.__enter__.return_value.status = 200
        with mock.patch.object(publisher.urllib.request, "urlopen", return_value=response), self.assertRaises(RuntimeError):
            publisher.check_absent("https://example.com/existing")

    def test_publication_summary_is_successful_and_public(self):
        summary = json.loads((PROFILE / "publication-summary.json").read_text())
        self.assertEqual(summary["publication"]["http_status"], 200)
        self.assertEqual(summary["completed_task_count"], 4)
        self.assertIsNone(summary["trace_archive"]["public_url"])
        self.assertAlmostEqual(summary["duration_seconds"], 522.7189569473267)
        self.assertEqual(summary["researcher_uri"], collector.RESEARCHER)
        for path in PROFILE.rglob("*"):
            if path.is_file() and path.suffix in {".json", ".py", ".md", ".sh", ".config"}:
                self.assertNotRegex(path.read_text(), r"\b(?:10|172|192)\.(?:\d{1,3}\.){2}\d{1,3}\b")


if __name__ == "__main__":
    unittest.main()
