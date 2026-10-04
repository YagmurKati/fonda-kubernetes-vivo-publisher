import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUIDE = ROOT / "docs" / "NEW_WORKFLOW.md"


def anchors(markdown: str) -> set:
    found = set()
    for title in re.findall(r"^#{1,6} (.+)$", markdown, re.M):
        slug = re.sub(r"[^a-z0-9 \-]", "", title.lower()).replace(" ", "-")
        found.add(slug)
    return found


class NewWorkflowGuideTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = GUIDE.read_text(encoding="utf-8")

    def test_links_point_to_existing_files_and_headings(self) -> None:
        for target in re.findall(r"\]\(([^)]+)\)", self.text):
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            path, _, anchor = target.partition("#")
            file = (GUIDE.parent / path).resolve() if path else GUIDE
            with self.subTest(link=target):
                self.assertTrue(file.exists(), target)
                if anchor:
                    self.assertIn(anchor, anchors(file.read_text(encoding="utf-8")))

    def test_readme_and_slurm_guide_link_to_the_page(self) -> None:
        self.assertIn("docs/NEW_WORKFLOW.md", (ROOT / "README.md").read_text(encoding="utf-8"))
        slurm = (ROOT / "examples/hpc-at-hu-slurm/COLLECT_AND_PUBLISH.md").read_text(encoding="utf-8")
        self.assertIn("../../docs/NEW_WORKFLOW.md#hpchu-slurm", slurm)
        self.assertIn("hpchu-slurm", anchors(self.text))

    def test_statements_match_the_code(self) -> None:
        # Kubernetes: Snakemake, Python and Java jobs are a fixed list in the collector.
        common = (ROOT / "scripts/lib/common.sh").read_text(encoding="utf-8")
        self.assertIn("SNAKEMAKE_PROFILE must be mg3, mg4, popinsnake, eqd or lotaru", common)
        self.assertIn("WORKFLOW_ENGINE must be nextflow or snakemake-kubernetes", common)
        # HPC@HU: one node, and the title of a new workflow creates its record.
        slurm = (ROOT / "collector/collect_slurm_job_metadata.py").read_text(encoding="utf-8")
        self.assertIn("Only single-node jobs are supported", slurm)
        self.assertIn("--workflow-label", slurm)
        # Airflow: the code name is the title and the address of the workflow.
        airflow = (ROOT / "collector/collect_airflow_kubernetes_metadata.py").read_text(encoding="utf-8")
        self.assertIn("public_workflow_name = args.code_name", airflow)
        # Settings named in the table exist.
        env = (ROOT / "config/publisher.env.example").read_text(encoding="utf-8")
        for name in ("WORKFLOW_NAME", "WORKFLOW_URI", "ENGINE_URI", "CODE_URI", "SUBPROJECT_URIS",
                     "APPLICATION_DOMAIN_URI", "PUBLICATION_URI", "RESPONSIBLE_RESEARCHER_URIS"):
            self.assertIn(name + "=", env)
        self.assertIn("WORKFLOW_DESCRIPTION", common)
        slurm_env = (ROOT / "examples/hpc-at-hu-slurm/slurm.env.example").read_text(encoding="utf-8")
        for name in ("WORKFLOW_URI", "WORKFLOW_LABEL", "RUN_LABEL", "RUN_OPERATOR_URI", "CODE_REPO_URL",
                     "GIT_COMMIT", "RESPONSIBLE_RESEARCHER_URIS", "NEXTFLOW_LAUNCH_DIR", "NEXTFLOW_TRACE_GLOB"):
            self.assertIn(name + "=", slurm_env)

    def test_no_exclusive_partition_line(self) -> None:
        self.assertNotIn("--partition", self.text)
        self.assertNotIn("--exclusive", self.text)


if __name__ == "__main__":
    unittest.main()
