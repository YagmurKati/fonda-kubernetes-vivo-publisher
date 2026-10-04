import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "examples" / "other-slurm-cluster"


def stub(directory: Path, name: str, body: str) -> None:
    path = directory / name
    path.write_text("#!/bin/bash\n" + body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


class OtherSlurmClusterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        # no network in tests: every curl call "fails to connect"
        stub(self.bin, "curl", 'printf "000"\nexit 7\n')
        self.env = dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}", HOME=str(self.root))

    def tearDown(self):
        self.tmp.cleanup()

    def test_shell_files_are_valid(self):
        for name in ("check-cluster.sh", "submit-with-publish.sh", "publish-after.sbatch.example"):
            result = subprocess.run(["bash", "-n", str(FOLDER / name)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, name + ": " + result.stderr)

    def test_guide_names_only_files_that_exist(self):
        guide = (FOLDER / "README.md").read_text()
        for name in ("check-cluster.sh", "publish-after.sbatch.example", "submit-with-publish.sh"):
            self.assertIn(name, guide)
            self.assertTrue((FOLDER / name).exists(), name)
        for target in ("../hpc-at-hu-slurm/README.md", "../hpc-at-hu-slurm/COLLECT_AND_PUBLISH.md",
                       "../../docs/ADMIN_SETUP.md"):
            self.assertIn(target, guide)
            self.assertTrue((FOLDER / target).resolve().exists(), target)

    def test_every_cluster_keeps_its_own_collector(self):
        # the HPC@HU collector stays specific to HPC@HU
        collector = (ROOT / "collector" / "collect_slurm_job_metadata.py").read_text()
        self.assertIn('"hpc-at-hu-slurm-"', collector)
        self.assertNotIn("cluster-key", collector)
        guide = (FOLDER / "README.md").read_text()
        self.assertIn("Every cluster gets its own collector", guide)
        self.assertIn("collector/collect_<cluster>_slurm_job_metadata.py", guide)

    def test_guide_and_examples_do_not_name_a_partition(self):
        for path in FOLDER.iterdir():
            text = path.read_text()
            self.assertNotIn("--exclusive", text, path.name)
            self.assertNotRegex(text, r"(?m)^#SBATCH\s+--partition", path.name)

    def test_check_reports_a_cluster(self):
        stub(self.bin, "scontrol", "cat <<'X'\nAcctGatherEnergyType    = acct_gather_energy/rapl\n"
                                   "ClusterName             = testcluster\nSlurmctldHost[0]        = controller-name\nX\n")
        stub(self.bin, "sinfo", 'if [ "$1" = "--version" ]; then echo "slurm 23.11.4"; else echo "standard*|up|1-00:00:00|4|96|384000|(null)|NO"; fi\n')
        stub(self.bin, "sacct", "printf '1001|00:10:00|1|52000\\n'\n")
        # stand-in for srun: run the piped checks here and record the options
        stub(self.bin, "srun", f'echo "$@" > "{self.root}/srun-options"\nwhile [ $# -gt 0 ] && [ "$1" != "bash" ]; do shift; done\n'
                               'SLURM_CPUS_ON_NODE=1 "$@"\n')
        result = subprocess.run(["bash", str(FOLDER / "check-cluster.sh"), "--partition=short"],
                                cwd=self.root, env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        reports = list(self.root.glob("vivo-cluster-check-*.txt"))
        self.assertEqual(len(reports), 1)
        report = reports[0].read_text()
        for expected in ("acct_gather_energy/rapl", "slurm 23.11.4", "1001|00:10:00|1|52000", "standard*|up",
                         "VIVO reachable from the login node: HTTP 000", "VIVO reachable from the node: HTTP 000",
                         "node_exporter at http://localhost:9100/metrics: HTTP 000",
                         "ipmi_exporter at http://localhost:9290/metrics: HTTP 000",
                         "RAPL energy counters:", "tool python3: yes", "kernel:", "End of report."):
            self.assertIn(expected, report)
        self.assertNotIn("controller-name", report)
        self.assertIn("--partition=short", (self.root / "srun-options").read_text())
        self.assertIn("--time=2", (self.root / "srun-options").read_text())

    def test_check_works_without_slurm(self):
        env = dict(self.env, PATH=f"{self.bin}:/usr/bin:/bin")
        result = subprocess.run(["bash", str(FOLDER / "check-cluster.sh")], cwd=self.root, env=env,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("(scontrol is not available)", result.stdout)
        self.assertIn("(srun is not available)", result.stdout)
        self.assertIn("End of report.", result.stdout)

    def test_submit_queues_the_publishing_job_behind_the_run(self):
        stub(self.bin, "sbatch", f'echo "$@" >> "{self.root}/sbatch-calls"\n'
                                 'case "$*" in *dependency*) echo "4712;cluster" ;; *) echo "4711;cluster" ;; esac\n')
        result = subprocess.run(["bash", str(FOLDER / "submit-with-publish.sh"), "run.sbatch", "publish.sbatch"],
                                cwd=self.root, env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = (self.root / "sbatch-calls").read_text().splitlines()
        self.assertEqual(calls[0], "--parsable run.sbatch")
        self.assertEqual(calls[1], "--parsable --dependency=afterany:4711 --export=ALL,RUN_JOB_ID=4711 publish.sbatch")
        self.assertIn("Run job 4711 submitted.", result.stdout)
        self.assertIn("slurm-4712.out", result.stdout)
        usage = subprocess.run(["bash", str(FOLDER / "submit-with-publish.sh"), "only-one"], env=self.env,
                               capture_output=True, text=True)
        self.assertEqual(usage.returncode, 2)

    def test_publishing_job_calls_the_clusters_publish_script(self):
        stub(self.bin, "sacct", 'echo "COMPLETED"\n')
        stub(self.bin, "module", "exit 0\n")
        stub(self.bin, "publish-this-cluster.sh", f'echo "$@" > "{self.root}/publish-call"\n')
        job = self.root / "publish-after.sbatch"
        text = (FOLDER / "publish-after.sbatch.example").read_text()
        line = next(l for l in text.splitlines() if l.startswith("PUBLISH_SCRIPT="))
        job.write_text(text.replace(line, f'PUBLISH_SCRIPT="{self.bin}/publish-this-cluster.sh"'))
        result = subprocess.run(["bash", str(job)], env=dict(self.env, RUN_JOB_ID="4711"), capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root / "publish-call").read_text().strip(), "4711")
        missing = subprocess.run(["bash", str(job)], env=self.env, capture_output=True, text=True)
        self.assertNotEqual(missing.returncode, 0)
        self.assertIn("submit-with-publish.sh", missing.stderr)


if __name__ == "__main__":
    unittest.main()
