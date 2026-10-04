import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "examples" / "other-cluster"


def stub(directory: Path, name: str, body: str) -> None:
    path = directory / name
    path.write_text("#!/bin/bash\n" + body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


class OtherClusterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        # no network in tests: every curl call "fails to connect"
        stub(self.bin, "curl", 'printf "000"\nexit 7\n')
        # the test job does not wait in tests
        self.env = dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}", HOME=str(self.root),
                        VIVO_CHECK_SECONDS="0")

    def tearDown(self):
        self.tmp.cleanup()

    def test_shell_files_are_valid(self):
        result = subprocess.run(["bash", "-n", str(FOLDER / "check-cluster.sh")], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_guide_names_only_files_that_exist(self):
        guide = (FOLDER / "README.md").read_text()
        self.assertIn("check-cluster.sh", guide)
        self.assertEqual(sorted(path.name for path in FOLDER.iterdir()), ["README.md", "check-cluster.sh"])
        for target in ("../hpc-at-hu-slurm/README.md", "../../docs/ADMIN_SETUP.md"):
            self.assertIn(target, guide)
            self.assertTrue((FOLDER / target).resolve().exists(), target)

    def test_users_send_only_the_cluster_name_and_the_check_file(self):
        guide = (FOLDER / "README.md").read_text()
        start = guide.index("### 3. Send the report")
        step = guide[start:guide.index("### 4.", start)]
        self.assertIn("yagmur.kati@hu-berlin.de", step)
        items = [line for line in step.splitlines() if line.startswith("- ")]
        self.assertEqual(len(items), 2)
        self.assertIn("cluster name", items[0])
        self.assertIn("vivo-cluster-check-", items[1])

    def test_no_measuring_method_is_assumed(self):
        guide = (FOLDER / "README.md").read_text()
        self.assertIn("is not assumed for yours", guide)
        self.assertNotRegex(guide, r"(?i)public documentation|web page")
        # two rounds: which sources exist, then commands written for that cluster
        self.assertIn("## A. First check: which scheduler and which sources", guide)
        self.assertIn("## B. Second check: read the sources that were found", guide)
        self.assertIn("not in a loop", guide)
        for text in (guide, (FOLDER / "check-cluster.sh").read_text()):
            self.assertNotIn("ipmi_exporter", text)
            self.assertNotIn("SAMPLE_INTERVAL", text)
            self.assertNotRegex(text, r"(?i)every second|automatic")

    def test_hpc_examples_do_not_sample_every_second(self):
        for path in (ROOT / "examples" / "hpc-at-hu-slurm").iterdir():
            if path.is_file():
                text = path.read_text()
                self.assertNotRegex(text, r"(?i)every second|each second", path.name)
                self.assertNotIn("SAMPLE_INTERVAL=1", text, path.name)

    def test_every_cluster_keeps_its_own_collector(self):
        # the HPC@HU collector stays specific to HPC@HU
        collector = (ROOT / "collector" / "collect_slurm_job_metadata.py").read_text()
        self.assertIn('"hpc-at-hu-slurm-"', collector)
        self.assertNotIn("cluster-key", collector)
        guide = (FOLDER / "README.md").read_text()
        self.assertIn("Every cluster gets its own collector", guide)
        self.assertIn("collector/collect_<cluster>_<scheduler>_job_metadata.py", guide)
        self.assertNotIn("other-slurm-cluster", guide + (ROOT / "README.md").read_text()
                         + (ROOT / "examples" / "hpc-at-hu-slurm" / "README.md").read_text())

    def test_guide_and_examples_do_not_name_a_partition(self):
        for path in FOLDER.iterdir():
            text = path.read_text()
            self.assertNotIn("--exclusive", text, path.name)
            self.assertNotRegex(text, r"(?m)^#SBATCH\s+--partition", path.name)

    def test_check_reports_a_cluster(self):
        stub(self.bin, "scontrol", "cat <<'X'\nAcctGatherEnergyType    = acct_gather_energy/rapl\n"
                                   "ClusterName             = testcluster\nSlurmctldHost[0]        = controller-name\nX\n")
        stub(self.bin, "sinfo", 'if [ "$1" = "--version" ]; then echo "slurm 23.11.4"; else echo "standard*|up|1-00:00:00|4|96|384000|(null)|NO"; fi\n')
        stub(self.bin, "sacct", 'case "$*" in\n'
                                '  *--helpformat*) echo "JobID State ConsumedEnergyRaw TRESUsageInTot" ;;\n'
                                f'  *"-j 4242"*) echo "$@" > "{self.root}/sacct-test-job"; echo "4242|COMPLETED|60|1|31000" ;;\n'
                                '  *) echo "1001|00:10:00|1|52000" ;;\nesac\n')
        stub(self.bin, "sstat", 'echo "4242.0|00:00:01|3000K|900"\n')
        stub(self.bin, "squeue", 'printf "4242\\n4100\\n"\n')
        # stand-in for srun: run the piped checks here and record the options
        stub(self.bin, "srun", f'echo "$@" > "{self.root}/srun-options"\nwhile [ $# -gt 0 ] && [ "$1" != "bash" ]; do shift; done\n'
                               'SLURM_CPUS_ON_NODE=1 SLURM_JOB_ID=4242 "$@"\n')
        result = subprocess.run(["bash", str(FOLDER / "check-cluster.sh"), "--partition=short"],
                                cwd=self.root, env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        reports = list(self.root.glob("vivo-cluster-check-*.txt"))
        self.assertEqual(len(reports), 1)
        report = reports[0].read_text()
        for expected in ("found: Slurm (slurm 23.11.4)", "acct_gather_energy/rapl", "1001|00:10:00|1|52000", "standard*|up",
                         "== 1. Scheduler", "== 2. Where you submit jobs", "== 3. Job reports",
                         "== 4. Slurm: accounting", "== 5. Slurm: partitions", "== 6. Slurm: your last finished jobs",
                         "== 7. Compute node (test job: srun --partition=short)",
                         "VIVO reachable from here: HTTP 000", "VIVO reachable from this node: HTTP 000",
                         "port 9100: HTTP 000", "monitoring services running on the node",
                         "RAPL energy counters:", "IPMI device present:", "python3: yes", "kernel:",
                         "JobID State ConsumedEnergyRaw TRESUsageInTot", "test job ID: 4242",
                         "jobs on this node that you can see (number only, this test job included): 2",
                         "readings when the test job is 0 seconds old", "4242.0|00:00:01|3000K|900",
                         "== 8. Slurm: what was recorded for the test job", "4242|COMPLETED|60|1|31000", "End of report."):
            self.assertIn(expected, report)
        self.assertNotIn("controller-name", report)
        self.assertNotIn("4100", report)  # other jobs are counted, not listed
        self.assertIn("ConsumedEnergyRaw", (self.root / "sacct-test-job").read_text())
        self.assertIn("--partition=short", (self.root / "srun-options").read_text())
        self.assertIn("--time=2", (self.root / "srun-options").read_text())

    def run_check(self):
        # only the stand-in commands and the system's basic tools
        env = dict(self.env, PATH=f"{self.bin}:/usr/bin:/bin")
        result = subprocess.run(["bash", str(FOLDER / "check-cluster.sh")], cwd=self.root, env=env,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("End of report.", result.stdout)
        return result.stdout

    def test_check_without_a_known_scheduler(self):
        report = self.run_check()
        self.assertIn("found: none of Slurm, PBS, Torque, Grid Engine, LSF, HTCondor, Kubernetes.", report)
        self.assertIn("Write in your e-mail how you submit jobs on this cluster.", report)
        self.assertIn("There is no ready check for this scheduler yet.", report)
        self.assertIn("== 5. This node (the login node; compute nodes can differ)", report)
        self.assertIn("RAPL energy counters:", report)
        self.assertNotIn("Slurm:", report)

    def test_check_on_a_pbs_cluster_reports_scheduler_and_login_node(self):
        stub(self.bin, "qstat", 'echo "pbs_version = 2022.1.1"\n')
        stub(self.bin, "pbsnodes", f'touch "{self.root}/pbsnodes-called"\n')
        stub(self.bin, "qsub", f'touch "{self.root}/job-submitted"\n')
        report = self.run_check()
        self.assertIn("found: PBS or Torque (pbs_version = 2022.1.1)", report)
        for expected in ("qsub: yes", "pbsnodes: yes", "bsub: no", "There is no ready check for this scheduler yet.",
                         "== 5. This node (the login node; compute nodes can differ)", "kernel:"):
            self.assertIn(expected, report)
        self.assertNotIn("Slurm:", report)
        # no job is submitted and the nodes are not queried
        self.assertFalse((self.root / "job-submitted").exists())
        self.assertFalse((self.root / "pbsnodes-called").exists())

    def test_check_on_kubernetes_reports_rights_and_monitoring_services(self):
        stub(self.bin, "kubectl", f'echo "$@" >> "{self.root}/kubectl-calls"\ncase "$*" in\n'
                                  '  version*) echo "Client Version: v1.30.1"; echo "Server Version: v1.29.4" ;;\n'
                                  '  "auth can-i list nodes"*) echo no ;;\n'
                                  '  "auth can-i"*) echo yes ;;\n'
                                  '  "get services"*) printf "monitoring prometheus-server\\nmonitoring kepler\\nshop frontend\\n" ;;\n'
                                  'esac\n')
        report = self.run_check()
        for expected in ("found: Kubernetes", "Server Version: v1.29.4", "may list nodes: no", "may list pods: yes",
                         "monitoring/prometheus-server", "monitoring/kepler"):
            self.assertIn(expected, report)
        self.assertNotIn("frontend", report)       # only monitoring services are named
        self.assertNotIn("This node", report)      # the computer with kubectl is not part of the cluster
        calls = (self.root / "kubectl-calls").read_text()
        self.assertNotRegex(calls, r"(?m)^(create|apply|delete|run|exec|patch|edit)\b")

    def test_a_cluster_with_slurm_and_kubectl_gets_the_slurm_check(self):
        stub(self.bin, "kubectl", 'echo "Client Version: v1.30.1"\n')
        stub(self.bin, "sinfo", 'echo "slurm 23.11.4"\n')
        report = self.run_check()
        self.assertIn("found: Slurm (slurm 23.11.4)", report)
        self.assertIn("found: Kubernetes", report)
        self.assertIn("== 4. Slurm: accounting", report)
        self.assertIn("(srun is not available)", report)
        self.assertIn("(no test job to look up)", report)


if __name__ == "__main__":
    unittest.main()
