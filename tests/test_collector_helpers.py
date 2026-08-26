import argparse
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from collector.collect_nextflow_run_metadata import (
    CarbonIntensityInfo,
    DEFAULT_WORKFLOW_REPO_URL,
    PodMetrics,
    TaskRecord,
    build_ttl,
    classify_stage,
    commit_url,
    derive_status,
    group_tasks,
    load_input_datasets,
    resolve_electricity_maps_latest_intensity,
    resolve_output_path,
)


def task_record(name: str, status: str, second: int) -> TaskRecord:
    submit = datetime(2026, 8, 25, 18, 0, second, tzinfo=timezone.utc)
    return TaskRecord(
        task_id=str(second),
        hash_value=f"aa/{second}",
        pod_name=f"nf-{second}",
        name=name,
        status=status,
        exit_code=0 if status == "COMPLETED" else 1,
        submit=submit,
        duration_seconds=1.0,
        realtime_seconds=1.0,
        end=submit + timedelta(seconds=1),
    )


class WorkflowStatusAndGroupingTests(unittest.TestCase):
    def test_retried_failure_is_a_success_with_warnings(self) -> None:
        tasks = [
            task_record("process (sample)", "FAILED", 1),
            task_record("process (sample)", "COMPLETED", 2),
        ]
        self.assertEqual(
            derive_status(tasks, True, workflow_succeeded=True),
            "Succeeded with warnings",
        )

    def test_terminal_workflow_failure_remains_failed(self) -> None:
        tasks = [task_record("process (sample)", "FAILED", 1)]
        self.assertEqual(derive_status(tasks, True), "Failed")

    def test_nextflow_tags_do_not_create_thousands_of_stages(self) -> None:
        tasks = [
            task_record("higherLevel:processPyramid (X0103_Y0101)", "FAILED", 1),
            task_record("higherLevel:processPyramid (X0111_Y0103)", "COMPLETED", 2),
        ]
        self.assertEqual(
            classify_stage(tasks[0].name),
            ("higherlevel-processpyramid", "HigherLevel / processPyramid"),
        )
        groups = group_tasks(tasks)
        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0]["tasks"]), 2)


class CommitUrlTests(unittest.TestCase):
    def test_github_url(self) -> None:
        self.assertEqual(
            commit_url(
                "https://github.com/CRC-FONDA/geoflow",
                "acd0d618d0451c65ecb12466a412abb65dda1a87",
            ),
            "https://github.com/CRC-FONDA/geoflow/commit/"
            "acd0d618d0451c65ecb12466a412abb65dda1a87",
        )

    def test_github_git_suffix_is_removed(self) -> None:
        self.assertEqual(
            commit_url("https://github.com/CRC-FONDA/geoflow.git", "abc123"),
            "https://github.com/CRC-FONDA/geoflow/commit/abc123",
        )

    def test_gitlab_url(self) -> None:
        self.assertEqual(
            commit_url("https://gitlab.example.org/group/project.git", "abc123"),
            "https://gitlab.example.org/group/project/-/commit/abc123",
        )

    def test_missing_or_unknown_repository_is_omitted(self) -> None:
        self.assertIsNone(commit_url(None, "abc123"))
        self.assertIsNone(commit_url(DEFAULT_WORKFLOW_REPO_URL, None))
        self.assertIsNone(commit_url("https://example.org/project", "abc123"))


class InputDatasetTests(unittest.TestCase):
    def test_repository_configuration_loads(self) -> None:
        path = (
            Path(__file__).resolve().parents[1]
            / "config"
            / "input_datasets.json.example"
        )
        datasets = load_input_datasets(str(path))
        self.assertEqual(len(datasets), 1)
        self.assertEqual(
            datasets[0].uri,
            "https://example.org/dataset/replace-me",
        )
        self.assertTrue(datasets[0].link_to_workflow)
        self.assertTrue(datasets[0].link_to_run)

    def test_empty_path_omits_input_metadata(self) -> None:
        self.assertEqual(load_input_datasets(""), [])

    def test_unknown_fields_are_rejected(self) -> None:
        payload = (
            '{"schema_version": 1, "datasets": ['
            '{"uri": "https://example.org/input", "label": "Input", '
            '"unexpected": true}]}'
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.json"
            path.write_text(payload, encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "unknown fields"):
                load_input_datasets(str(path))

    def test_collector_emits_input_and_commit_links(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        datasets = load_input_datasets(
            str(repository_root / "config" / "input_datasets.json.example")
        )
        start = datetime(2026, 7, 19, 19, 48, tzinfo=timezone.utc)
        end = start + timedelta(seconds=2)
        task = TaskRecord(
            task_id="1",
            hash_value="aa/bb",
            pod_name="nf-test",
            name="test (1)",
            status="COMPLETED",
            exit_code=0,
            submit=start,
            duration_seconds=2.0,
            realtime_seconds=1.0,
            end=end,
        )
        args = argparse.Namespace(
            application_domain_uri="https://example.org/domain",
            backend_uri="https://example.org/backend",
            base_uri="http://example.org/vivo-import/run-metadata/",
            cluster_label="Fonda Cluster",
            cluster_uri="https://example.org/cluster",
            code_uri=(
                "https://github.com/YagmurKati/"
                "geoflow-kubernetes-vivo-metadata"
            ),
            engine_uri="https://example.org/engine/nextflow",
            include_cached_origin_metrics=False,
            namespace="test",
            ontology_uri="http://example.org/ontology/run-metadata#",
            prom_url="http://127.0.0.1:19090",
            publication_uri="",
            run_operator_uri="",
            trace_archive="https://example.org/traces",
            trace_data_format="TSV",
            trace_types="Nextflow trace",
            workflow_name="Geoflow test",
            workflow_repo_url="https://github.com/CRC-FONDA/geoflow",
            workflow_uri="https://example.org/workflow/geoflow",
        )
        ttl_text, audit = build_ttl(
            args=args,
            tasks=[task],
            stages=[{"slug": "test", "label": "Test", "tasks": [task]}],
            pod_metrics={
                "nf-test": PodMetrics(
                    pod_name="nf-test",
                    cpu_seconds=1.0,
                    energy_joules=3600.0,
                )
            },
            run_start=start,
            run_end=end,
            run_status="Succeeded",
            log_metadata={
                "session_id": "session-1",
                "run_name": "test-run",
                "nextflow_version": "25.04.8",
                "failure_reason": None,
            },
            code_version="abc123",
            git_commit="acd0d618d0451c65ecb12466a412abb65dda1a87",
            git_dirty=True,
            energy_metric="kepler_container_joules_total",
            carbon_info=CarbonIntensityInfo(kg_per_kwh=0.3, source="test"),
            node_infos=[],
            images=[],
            responsible_researchers=[],
            responsible_researcher_uris=[],
            subproject_uris=[],
            language_uris=[],
            input_datasets=datasets,
        )
        self.assertIn("rm:hasUsedInputData", ttl_text)
        self.assertIn("rm:inputData", ttl_text)
        self.assertIn("rm:inputDataOfWorkflow", ttl_text)
        self.assertIn("rm:usedByWorkflowRun", ttl_text)
        self.assertIn("rm:codeCommitLink", ttl_text)
        self.assertNotIn("rm:nodeName", ttl_text)
        self.assertNotIn("rm:carbonIntensityKgCO2ePerKWh", ttl_text)
        self.assertNotIn("rm:codeModified", ttl_text)
        self.assertEqual(len(audit["input_datasets"]), 1)


class ElectricityMapsLatestTests(unittest.TestCase):
    def test_latest_value_is_recorded_as_collection_time_proxy(self) -> None:
        args = argparse.Namespace(
            electricity_maps_latest_api_url=(
                "https://api.electricitymaps.com/v4/carbon-intensity/latest"
            ),
            electricity_maps_zone="DE",
        )
        payload = {
            "carbonIntensity": 275,
            "datetime": "2026-08-25T14:00:00.000Z",
            "emissionFactorType": "lifecycle",
            "flowTraced": True,
            "isEstimated": True,
            "temporalGranularity": "hourly",
            "zone": "DE",
        }
        with mock.patch(
            "collector.collect_nextflow_run_metadata.http_get_json",
            return_value=payload,
        ) as http_get_json:
            info = resolve_electricity_maps_latest_intensity(args, "token")

        self.assertEqual(info.kg_per_kwh, 0.275)
        self.assertEqual(info.zone, "DE")
        self.assertTrue(info.includes_estimates)
        self.assertEqual(info.start, "2026-08-25T14:00:00Z")
        self.assertEqual(info.end, "2026-08-25T15:00:00Z")
        self.assertIn("collection-time proxy", info.source)
        self.assertIn("not guaranteed", info.method_note or "")
        http_get_json.assert_called_once_with(
            args.electricity_maps_latest_api_url,
            {"zone": "DE"},
            {"auth-token": "token"},
        )


class OutputPathTests(unittest.TestCase):
    def test_explicit_output_file_does_not_create_default_output_dir(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            blocked_mount = root / "read-only-configmap"
            blocked_mount.write_text("not a directory", encoding="utf-8")
            expected = root / "vivo-outbox" / "run-stamped.ttl"
            args = argparse.Namespace(
                output_dir=str(blocked_mount / "metadata" / "generated"),
                output_file=str(expected),
                output_stamp=None,
            )

            actual = resolve_output_path(
                args,
                datetime(2026, 8, 25, 14, 0, tzinfo=timezone.utc),
            )

            self.assertEqual(actual, expected.resolve())
            self.assertTrue(expected.parent.is_dir())


if __name__ == "__main__":
    unittest.main()
