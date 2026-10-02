import importlib.util
import io
import json
import math
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "collector"))
sys.path.insert(0, str(ROOT / "publisher"))
import collect_slurm_job_metadata as slurm  # noqa: E402
import rapl_carbon  # noqa: E402
from publish_vivo import run_has_operator, run_owned_resource_iris  # noqa: E402

TZ = ZoneInfo("Europe/Berlin")
WORKFLOW = "http://example.org/vivo-import/run-metadata/workflow/test-slurm"
OPERATOR = "https://fonda.hu-berlin.de/?page_id=2066#YagmurKati"
# Values reported by HPC@HU for job 1595874 (2026-10-01).
SACCT = """\
1595874|D025h01|COMPLETED|2026-10-01T17:35:39|2026-10-01T17:45:40|601|10:00.284|2|||hpc-cms01-008|1|standard|0:0|billing=8,cpu=8,mem=32G,node=1
1595874.batch|batch|COMPLETED|2026-10-01T17:35:39|2026-10-01T17:45:40|601|10:00.284|2|71992K|640719|hpc-cms01-008|1||0:0|billing=8,cpu=8,mem=32G,node=1
1595874.extern|extern|COMPLETED|2026-10-01T17:35:39|2026-10-01T17:45:40|601|00:00.001|2|0|640700|hpc-cms01-008|1||0:0|billing=8,cpu=8,mem=32G,node=1
"""
TRACE = """\
task_id\thash\tnative_id\tname\tstatus\texit\tsubmit\tduration\trealtime\t%cpu\tpeak_rss\tpeak_vmem\trchar\twchar
4\t93/86d1df\t2585886\tNFCORE_RANGELAND:RANGELAND:UNTAR_WVDB (wvdb.tar.gz)\tCOMPLETED\t0\t2026-10-01 17:36:41.916\t529ms\t77ms\t70.4%\t3.2 MB\t4.3 MB\t204 KB\t41.9 KB
2\t7a/b8f6b1\t2585899\tNFCORE_RANGELAND:RANGELAND:UNTAR_DEM (dem.tar.gz)\tCOMPLETED\t0\t2026-10-01 17:36:41.939\t691ms\t124ms\t86.9%\t3 MB\t4.3 MB\t11.8 MB\t9.3 MB
5\taa/bbbbbb\t2585900\tNFCORE_RANGELAND:RANGELAND:HIGHER_LEVEL:FORCE_HIGHER_LEVEL (X0001_Y0001)\tCOMPLETED\t0\t2026-10-01 17:37:00.000\t1m 2s\t1m 1s\t200.0%\t1.5 GB\t2 GB\t1 GB\t1 GB
6\taa/cccccc\t2585901\tNFCORE_RANGELAND:RANGELAND:HIGHER_LEVEL:FORCE_HIGHER_LEVEL (X0002_Y0001)\tFAILED\t1\t2026-10-01 17:38:00.000\t10s\t9s\t100.0%\t1 GB\t2 GB\t1 GB\t1 GB
"""
NF_LOG = """\
Oct-01 17:35:45.994 [main] DEBUG nextflow.cli.CmdRun - N E X T F L O W  ~  version 24.10.5
Oct-01 17:35:46.100 [main] INFO  nextflow.cli.CmdRun - Launching `https://github.com/nf-core/rangeland` [mad_curie] DSL2 - revision: 8a6a9fa1c4 [1.0.0]
Oct-01 17:35:46.200 [main] DEBUG nextflow.Session - Session UUID: 0f6a3a1e-1111-2222-3333-444455556666
Oct-01 17:36:00.000 [main] INFO  nextflow.container - Pulling Apptainer image docker://docker.io/davidfrantz/force:3.7.10 [cache x]
Oct-01 17:36:01.000 [main] INFO  nextflow.container - Pulling Apptainer image docker://quay.io/nf-core/ubuntu:22.04 [cache y]
"""
NODE_INFO = ("hostname\thpc-cms01-008\ncpu_model\tAMD EPYC 7713 64-Core Processor\nnode_cpus\t256\nsockets\t2\n"
             "threads_per_core\t2\narchitecture\tx86_64\nmemory_total_bytes\t1081236000000\n"
             "os\topenSUSE Leap 16.0\nkernel\t6.12.0\n")
NODE_BUSY_PER_SECOND = 40.0  # 40 of 128 node CPUs busy on average


def write_evidence(directory, samples=61, step=10.0, job_id="1595874"):
    directory.mkdir(parents=True)
    start = datetime(2026, 10, 1, 17, 35, 40, tzinfo=TZ).timestamp()
    lines = []
    for i in range(samples):
        t = start + i * step
        lines.append(f"{t:.3f}\t{1000 + NODE_BUSY_PER_SECOND * i * step:.3f}\t128\t{950 + (i % 3) * 10}")
    (directory / "node-samples.tsv").write_text("\n".join(lines) + "\n")
    (directory / "job-info.tsv").write_text(
        f"slurm_job_id\t{job_id}\nhostname\thpc-cms01-008\nsample_interval_seconds\t{step:g}\n")


class SlurmCollectorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "sacct.txt").write_text(SACCT)

    def tearDown(self):
        self.tmp.cleanup()

    def run_collector(self, *extra, evidence=None):
        evidence = evidence or self.root / "evidence"
        if not evidence.exists():
            write_evidence(evidence)
        out = self.root / "out"
        argv = ["--job-id", "1595874", "--evidence-dir", str(evidence), "--output-dir", str(out),
                "--sacct-file", str(self.root / "sacct.txt"), "--workflow-uri", WORKFLOW,
                "--workflow-label", "Test Slurm workflow", "--run-operator-uri", OPERATOR, *extra]
        with mock.patch("sys.stdout", io.StringIO()):
            slurm.main(argv)
        return (out / "run.ttl").read_text(), json.loads((out / "summary.json").read_text())

    def test_nextflow_and_node_details(self):
        evidence = self.root / "evidence"
        write_evidence(evidence)
        (evidence / "node-info.tsv").write_text(NODE_INFO)
        (self.root / "trace.txt").write_text(TRACE)
        (self.root / "old-trace.txt").write_text(TRACE.replace("2026-10-01 17:3", "2026-09-30 10:3"))
        (self.root / ".nextflow.log").write_text(NF_LOG)
        (self.root / ".nextflow.log.1").write_text(NF_LOG.replace("Oct-01", "Sep-30"))
        ttl, summary = self.run_collector(
            "--no-carbon", "--code-repo-url", "https://github.com/nf-core/rangeland",
            "--language-uri", "http://example.org/vivo-import/run-metadata/language/shell",
            "--input-data-uri", "http://example.org/vivo-import/run-metadata/input-dataset/test",
            "--nextflow-log", str(self.root / ".nextflow.log.1"), "--nextflow-log", str(self.root / ".nextflow.log"),
            "--nextflow-trace", str(self.root / "old-trace.txt"), "--nextflow-trace", str(self.root / "trace.txt"),
            evidence=evidence)
        self.assertIn('rm:architecture "x86_64; 2 x AMD EPYC 7713 64-Core Processor; 256 hardware threads"', ttl)
        self.assertIn('rm:osImage "openSUSE Leap 16.0"', ttl)
        self.assertIn("rm:language <http://example.org/vivo-import/run-metadata/language/shell>", ttl)
        self.assertIn("rm:inputData <http://example.org/vivo-import/run-metadata/input-dataset/test>", ttl)
        self.assertIn('rm:workflowCodeLink "https://github.com/nf-core/rangeland"^^xsd:anyURI', ttl)
        self.assertIn('rm:nextflowVersion "24.10.5"', ttl)
        self.assertIn("rm:workflowEngine <http://example.org/vivo-import/run-metadata/engine/nextflow>", ttl)
        self.assertIn('rm:containerImage "docker.io/davidfrantz/force:3.7.10"', ttl)
        self.assertIn('rm:codeVersion "1.0.0"', ttl)
        self.assertIn('rm:gitCommit "8a6a9fa1c4"', ttl)
        self.assertIn('rm:gpuRequested "false"^^xsd:boolean', ttl)
        self.assertIn('rm:taskCount "4"^^xsd:integer', ttl)
        self.assertIn('rm:failedTaskCount "1"^^xsd:integer', ttl)
        self.assertIn('rdfs:label "FORCE_HIGHER_LEVEL"@en', ttl)
        self.assertEqual(summary["nextflow_trace"]["path"], str(self.root / "trace.txt"))
        higher = next(p for p in summary["nextflow_trace"]["processes"] if p["name"] == "FORCE_HIGHER_LEVEL")
        self.assertAlmostEqual(higher["cpu"], 61 * 2 + 9 * 1)
        self.assertEqual(higher["rss"], 1.5 * 1024 ** 3)
        owned = run_owned_resource_iris(ttl)
        self.assertEqual(len(owned), 2 + 3)

    def test_node_info_from_another_node_is_rejected(self):
        evidence = self.root / "evidence"
        write_evidence(evidence)
        (evidence / "node-info.tsv").write_text(NODE_INFO.replace("hpc-cms01-008", "hpc-cms01-001"))
        with self.assertRaisesRegex(ValueError, "another node"):
            self.run_collector("--no-carbon", evidence=evidence)

    def test_cpu_time_formats(self):
        self.assertAlmostEqual(slurm.parse_cpu_time("10:00.284"), 600.284)
        self.assertEqual(slurm.parse_cpu_time("01:02:03"), 3723)
        self.assertEqual(slurm.parse_cpu_time("1-00:00:01"), 86401)

    def test_run_period_names_cet_and_cest(self):
        self.assertEqual(slurm.run_period("2026-10-01T16:42:08+00:00", "2026-10-01T16:57:23+00:00", TZ),
                         "2026-10-01 18:42–18:57 CEST")
        self.assertEqual(slurm.run_period("2026-12-01T16:42:08+00:00", "2026-12-01T16:57:23+00:00", TZ),
                         "2026-12-01 17:42–17:57 CET")
        self.assertEqual(slurm.run_period("2026-10-25T00:30:00+00:00", "2026-10-25T01:30:00+00:00", TZ),
                         "2026-10-25 02:30 CEST–02:30 CET")
        self.assertEqual(slurm.run_period("2026-12-01T22:30:00+00:00", "2026-12-02T00:30:00+00:00", TZ),
                         "2026-12-01 23:30–2026-12-02 01:30 CET")

    def test_trace_durations(self):
        self.assertAlmostEqual(slurm.parse_duration("529ms"), 0.529)
        self.assertEqual(slurm.parse_duration("1h 2m 3s"), 3723)
        self.assertEqual(slurm.parse_duration("1d 1s"), 86401)
        self.assertEqual(slurm.process_name("A:B:C_D (tag 1)"), "C_D")

    def test_energy_is_cpu_share_of_node_energy(self):
        ttl, summary = self.run_collector("--no-carbon")
        node_busy = NODE_BUSY_PER_SECOND * 601
        share = 600.284 / node_busy
        self.assertAlmostEqual(summary["cpu_share"], share, places=9)
        self.assertAlmostEqual(summary["energy_kwh"], 640719 * share / 3_600_000, places=12)
        self.assertEqual(summary["status"], "Succeeded")
        self.assertAlmostEqual(summary["memory_peak_gb"], 71992 * 1024 / 1e9)
        self.assertIn("rm:runOperator <" + OPERATOR + ">", ttl)
        self.assertIn("rm:computeCluster <http://example.org/vivo-import/run-metadata/cluster/hpc-hu-cluster>", ttl)
        self.assertNotIn("rdf:type rm:ComputeCluster", ttl)
        self.assertIn("rm:backend <http://172.28.33.178:8080/vivo/individual/n6167>", ttl)
        self.assertNotIn("rm:memoryAvgGB", ttl)
        self.assertIn('rdfs:label "D025h01 · run 2026-10-01 17:35–17:45 CEST"@en', ttl)
        self.assertNotIn("rm:carbonEmissionKgCO2e", ttl)
        self.assertTrue(run_has_operator(ttl))
        owned = run_owned_resource_iris(ttl)
        self.assertEqual(len(owned), 2)
        self.assertTrue(owned[0].endswith("hpc-at-hu-slurm-1595874-20261001t153539"))

    def test_share_never_exceeds_one(self):
        evidence = self.root / "idle"
        evidence.mkdir()
        start = datetime(2026, 10, 1, 17, 35, 40, tzinfo=TZ).timestamp()
        (evidence / "node-samples.tsv").write_text(f"{start}\t0\t128\t900\n{start + 600}\t300\t128\t900\n")
        (evidence / "job-info.tsv").write_text("slurm_job_id\t1595874\nsample_interval_seconds\t10\n")
        _, summary = self.run_collector("--no-carbon", evidence=evidence)
        self.assertEqual(summary["cpu_share"], 1.0)

    def test_short_sampling_is_rejected(self):
        evidence = self.root / "short"
        write_evidence(evidence, samples=20)
        with self.assertRaisesRegex(ValueError, "cover only"):
            self.run_collector("--no-carbon", evidence=evidence)

    def test_multi_node_and_unfinished_jobs_are_rejected(self):
        (self.root / "sacct.txt").write_text(SACCT.replace("|hpc-cms01-008|1|standard", "|hpc-cms01-[008-009]|2|standard"))
        with self.assertRaisesRegex(ValueError, "single-node"):
            self.run_collector("--no-carbon")
        (self.root / "sacct.txt").write_text(SACCT.replace("COMPLETED", "RUNNING", 1))
        with self.assertRaisesRegex(ValueError, "not finished"):
            self.run_collector("--no-carbon", evidence=self.root / "evidence2")

    def test_evidence_of_another_job_is_rejected(self):
        evidence = self.root / "other"
        write_evidence(evidence, job_id="999")
        with self.assertRaisesRegex(ValueError, "another Slurm job"):
            self.run_collector("--no-carbon", evidence=evidence)

    def test_power_fractions_partition_the_job(self):
        samples = [(0.0, 0, 128, 900.0), (10.0, 0, 128, 1100.0), (20.0, 0, 128, 900.0)]
        fraction, count = slurm.power_profile(samples, 2.0, 18.0)
        self.assertEqual(count, 3)
        parts = [fraction(a, a + 1.0) for a in range(2, 18)]
        self.assertTrue(math.isclose(sum(parts), 1.0, rel_tol=1e-12))
        self.assertGreater(fraction(9, 11), fraction(2, 4))

    def test_carbon_is_time_matched_when_available(self):
        payload = {"state": "DE", "country": "DE", "unit": "g/kWh",
                   "Consumption-based Intensity (test)": [["2026-10-01T15:00:00+00:00", 400.0]]}

        class Response(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        def urlopen(request, timeout=0):
            return Response(json.dumps(payload).encode())

        with mock.patch.dict(os.environ, {"ELECTRICITY_MAPS_API_TOKEN": ""}), \
                mock.patch.object(rapl_carbon.subprocess, "run", side_effect=OSError), \
                mock.patch.object(rapl_carbon.urllib.request, "urlopen", side_effect=urlopen):
            ttl, summary = self.run_collector()
        self.assertAlmostEqual(summary["carbon"]["package_kg"], summary["energy_kwh"] * 0.4, places=12)
        self.assertIn("rm:carbonEmissionKgCO2e", ttl)

    def test_missing_carbon_data_publishes_without_it(self):
        with mock.patch.object(rapl_carbon, "fetch_carbon",
                               side_effect=rapl_carbon.CarbonUnavailable("none", [])), \
                mock.patch("sys.stderr", io.StringIO()):
            ttl, summary = self.run_collector()
        self.assertIsNone(summary["carbon"])
        self.assertNotIn("rm:carbonEmissionKgCO2e", ttl)


# Whole-node job on HPC@HU (job 1598432, 2026-10-02): Slurm accounting and the
# 72 IPMI power readings (watts) taken one second apart while it ran.
WHOLE_NODE_SACCT = """\
1598432|rangeland-test|COMPLETED|2026-10-02T21:04:19|2026-10-02T21:05:33|74|23:46.794|256|||hpc-cms01-005|1|standard|0:0|billing=256,cpu=256,mem=32G,node=1
1598432.batch|batch|COMPLETED|2026-10-02T21:04:19|2026-10-02T21:05:33|74|23:46.794|256||36498|hpc-cms01-005|1||0:0|billing=256,cpu=256,mem=32G,node=1
"""
WHOLE_NODE_WATTS = [
    412, 374, 402, 427, 453, 492, 405, 476, 449, 449, 471, 475, 420, 420, 426, 295, 294, 350, 481, 541, 541, 514,
    464, 712, 437, 412, 612, 687, 719, 756, 647, 460, 445, 445, 423, 539, 467, 525, 462, 484, 480, 457, 483, 504,
    504, 434, 536, 469, 453, 545, 556, 446, 502, 498, 538, 538, 516, 507, 462, 445, 575, 770, 665, 730, 758, 767,
    471, 471, 438, 444, 444, 434]


class WholeNodeEnergyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "sacct.txt").write_text(WHOLE_NODE_SACCT)
        self.start = datetime(2026, 10, 2, 21, 4, 20, tzinfo=TZ).timestamp()

    def tearDown(self):
        self.tmp.cleanup()

    def collect(self, watts, node_cpus=256):
        evidence = self.root / "evidence"
        evidence.mkdir()
        times = [self.start + i for i in range(len(watts) - 1)] + [self.start + len(watts) - 2 + 1.49]
        (evidence / "node-samples.tsv").write_text("".join(
            f"{t:.3f}\t{1000 + 20 * i:.3f}\t{node_cpus}\t{w}\n" for i, (t, w) in enumerate(zip(times, watts))))
        (evidence / "job-info.tsv").write_text(
            "slurm_job_id\t1598432\nhostname\thpc-cms01-005\nsample_interval_seconds\t1\n")
        stderr = io.StringIO()
        with mock.patch("sys.stdout", io.StringIO()), mock.patch("sys.stderr", stderr):
            slurm.main(["--job-id", "1598432", "--evidence-dir", str(evidence), "--output-dir", str(self.root / "out"),
                        "--sacct-file", str(self.root / "sacct.txt"), "--workflow-uri", WORKFLOW,
                        "--run-operator-uri", OPERATOR, "--no-carbon"])
        summary = json.loads((self.root / "out" / "summary.json").read_text())
        return (self.root / "out" / "run.ttl").read_text(), summary, stderr.getvalue(), times

    def test_whole_node_job_uses_the_sampled_ipmi_power(self):
        ttl, summary, stderr, times = self.collect(WHOLE_NODE_WATTS)
        window = times[-1] - times[0]
        expected = sum((a + b) / 2 * (t1 - t0) for a, b, t0, t1 in zip(
            WHOLE_NODE_WATTS, WHOLE_NODE_WATTS[1:], times, times[1:])) * 74 / window
        self.assertTrue(summary["whole_node"])
        self.assertEqual(summary["energy_basis"], "sampled")
        self.assertEqual(summary["cpu_share"], 1.0)
        self.assertAlmostEqual(summary["energy_joules"], expected, places=6)
        self.assertAlmostEqual(summary["energy_joules"], 37154, delta=40)  # value published for this job
        self.assertEqual(summary["slurm_node_energy_joules"], 36498.0)
        self.assertIn("read about every 1.0 s while the job ran (72 readings, 294 to 770 W", ttl)
        self.assertIn("Slurm accounting (acct_gather_energy/ipmi) reports 36498 J", ttl)
        self.assertIn("The whole node was allocated to this job", ttl)
        self.assertNotIn("CPU-time share", ttl)
        self.assertNotIn("the job shared its node", stderr)

    def test_whole_node_job_without_power_readings_uses_the_slurm_energy(self):
        ttl, summary, stderr, _ = self.collect(["NA"] * 72)
        self.assertEqual(summary["energy_basis"], "slurm")
        self.assertEqual(summary["energy_joules"], 36498.0)
        self.assertIn("too few IPMI power readings", stderr)
        self.assertIn("Slurm acct_gather_energy/ipmi ConsumedEnergyRaw, 36498 J", ttl)

    def test_job_on_a_shared_node_is_an_estimate_and_says_so(self):
        ttl, summary, stderr, _ = self.collect(WHOLE_NODE_WATTS, node_cpus=512)
        self.assertFalse(summary["whole_node"])
        self.assertEqual(summary["energy_basis"], "slurm")
        self.assertIn("NOTE: the job shared its node", stderr)
        self.assertIn("Energy is an estimate", ttl)


class NodeSamplerScriptTests(unittest.TestCase):
    def test_sampler_records_node_metrics_and_keeps_exit_status(self):
        script = ROOT / "collector" / "slurm" / "run-with-node-sampler.sh"
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "node.prom").write_text(
                '# HELP x\nnode_cpu_seconds_total{cpu="0",mode="idle"} 100\n'
                'node_cpu_seconds_total{cpu="0",mode="user"} 7.5\n'
                'node_cpu_seconds_total{cpu="1",mode="system"} 2.5\n'
                'node_cpu_seconds_total{cpu="1",mode="iowait"} 9\n')
            (tmp / "ipmi.prom").write_text('ipmi_dcmi_power_consumption_watts 952\n'
                                           'ipmi_power_watts{id="43",name="Pwr Consumption"} 957\n')
            env = dict(os.environ, NODE_EXPORTER_URL="file://" + str(tmp / "node.prom"),
                       IPMI_EXPORTER_URL="file://" + str(tmp / "ipmi.prom"),
                       SAMPLE_INTERVAL="1", SLURM_JOB_ID="42")
            result = subprocess.run([str(script), str(tmp / "ev"), "--", "bash", "-c", "sleep 1.5; exit 3"],
                                    env=env, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 3, result.stderr)
            rows = [line.split("\t") for line in (tmp / "ev" / "node-samples.tsv").read_text().splitlines()]
            self.assertGreaterEqual(len(rows), 2)
            self.assertEqual(rows[0][1:], ["10.000", "2", "952"])
            info = (tmp / "ev" / "job-info.tsv").read_text()
            self.assertIn("slurm_job_id\t42", info)
            self.assertIn("command_exit_status\t3", info)
            node = (tmp / "ev" / "node-info.tsv").read_text()
            self.assertIn("architecture\t", node)
            self.assertIn("node_cpus\t", node)
            fast = subprocess.run([str(script), str(tmp / "fast"), "--", "sleep", "1.6"],
                                  env=dict(env, SAMPLE_INTERVAL="0.3"), capture_output=True, text=True, timeout=30)
            self.assertEqual(fast.returncode, 0, fast.stderr)
            stamps = [float(line.split("\t")[0]) for line in
                      (tmp / "fast" / "node-samples.tsv").read_text().splitlines()]
            gaps = [b - a for a, b in zip(stamps, stamps[1:])][:-1]
            self.assertGreaterEqual(len(stamps), 5)
            self.assertTrue(all(abs(gap - 0.3) < 0.15 for gap in gaps), gaps)
            for bad in ("0", "-1", "abc"):
                refused = subprocess.run([str(script), str(tmp / ("bad" + bad)), "--", "true"],
                                         env=dict(env, SAMPLE_INTERVAL=bad), capture_output=True, text=True, timeout=30)
                self.assertEqual(refused.returncode, 2)
                self.assertIn("SAMPLE_INTERVAL", refused.stderr)
            again = subprocess.run([str(script), str(tmp / "ev"), "--", "true"], env=env,
                                   capture_output=True, text=True, timeout=30)
            self.assertEqual(again.returncode, 2)


if __name__ == "__main__":
    unittest.main()
