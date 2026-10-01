import unittest
from pathlib import Path


class PublisherJobTemplateTests(unittest.TestCase):
    def test_run_id_is_replaced_globally_in_all_evidence_paths(self) -> None:
        template = (
            Path(__file__).resolve().parents[1]
            / "k8s"
            / "publisher-job.yaml"
        ).read_text(encoding="utf-8")

        for variable in (
            "TRACE_PATH_TEMPLATE",
            "CONSOLE_LOG_PATH_TEMPLATE",
            "DEBUG_LOG_PATH",
        ):
            self.assertIn(
                "${" + variable + "//\\{run_id\\}/${RUN_ID}}",
                template,
            )

    def test_declared_container_images_reach_the_collector(self) -> None:
        template = (
            Path(__file__).resolve().parents[1]
            / "k8s"
            / "publisher-job.yaml"
        ).read_text(encoding="utf-8")

        self.assertIn('<<< "$DECLARED_CONTAINER_IMAGES"', template)
        self.assertIn('--container-image "$image"', template)

    def test_workflow_and_run_trace_links_are_separate(self) -> None:
        template = (
            Path(__file__).resolve().parents[1]
            / "k8s"
            / "publisher-job.yaml"
        ).read_text(encoding="utf-8")

        self.assertIn(
            '--workflow-trace-repository "$WORKFLOW_TRACE_REPOSITORY"',
            template,
        )
        self.assertIn(
            '--run-trace-archive "$effective_run_trace_archive"',
            template,
        )
        self.assertIn('value: "__RUN_TRACE_ARCHIVE__"', template)

    def test_incomplete_node_metadata_stops_before_publication(self) -> None:
        for name in ("publisher-job.yaml", "snakemake-publisher-job.yaml"):
            template = (
                Path(__file__).resolve().parents[1] / "k8s" / name
            ).read_text(encoding="utf-8")
            with self.subTest(template=name):
                warning_gate = template.index(
                    "FONDA_NODE_METADATA_CONFIRMATION_REQUIRED"
                )
                publisher = template.index("publisher_args=(")
                self.assertLess(warning_gate, publisher)
                self.assertIn("ALLOW_INCOMPLETE_NODE_METADATA", template)
                self.assertIn("raise SystemExit(42)", template)

    def test_publish_script_prompts_after_hardware_warning(self) -> None:
        script = (
            Path(__file__).resolve().parents[1]
            / "scripts"
            / "publish-run.sh"
        ).read_text(encoding="utf-8")

        self.assertIn('[[ "$exit_code" == "42"', script)
        self.assertIn("Publish this run anyway?", script)
        self.assertIn('[[ "$confirmation" == "PUBLISH" ]]', script)
        self.assertIn("ALLOW_INCOMPLETE_NODE_METADATA=1", script)

    def test_removal_job_uses_preserved_ttl_and_receipt(self) -> None:
        template = (
            Path(__file__).resolve().parents[1]
            / "k8s"
            / "remove-run-job.yaml"
        ).read_text(encoding="utf-8")

        self.assertIn('${PUBLICATION_ID}.ttl', template)
        self.assertIn('${PUBLICATION_ID}.published.json', template)
        self.assertIn("--remove", template)
        self.assertIn("--confirm-removal", template)

    def test_every_job_template_pins_pods_to_the_configured_nodes(self) -> None:
        for name in ("publisher-job.yaml", "snakemake-publisher-job.yaml", "remove-run-job.yaml"):
            template = (Path(__file__).resolve().parents[1] / "k8s" / name).read_text(encoding="utf-8")
            with self.subTest(template=name):
                self.assertIn('usedby: "__NODE_USEDBY__"', template)

if __name__ == "__main__":
    unittest.main()
