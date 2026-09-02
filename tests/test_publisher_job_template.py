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


if __name__ == "__main__":
    unittest.main()
