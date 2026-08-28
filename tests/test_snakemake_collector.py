import argparse
import gzip
import hashlib
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from collector import collect_nextflow_run_metadata as core
from collector import collect_snakemake_kubernetes_metadata as adapter


def sample_pod(version: int, exit_code: int, minute: int):
    started = datetime(2026, 8, 26, 13, minute, tzinfo=timezone.utc)
    finished = started + timedelta(seconds=30)
    name = f"example-a2-mg4-smoke-v{version}"
    return {
        "metadata": {
            "name": f"{name}-pod",
            "uid": f"uid-{version}",
            "labels": {"batch.kubernetes.io/job-name": name},
        },
        "spec": {"nodeName": "hu-worker-test"},
        "status": {
            "containerStatuses": [
                {
                    "name": "workflow",
                    "imageID": "docker.io/library/ubuntu@sha256:test",
                    "state": {
                        "terminated": {
                            "exitCode": exit_code,
                            "startedAt": started.isoformat().replace(
                                "+00:00", "Z"
                            ),
                            "finishedAt": finished.isoformat().replace(
                                "+00:00", "Z"
                            ),
                        }
                    },
                }
            ]
        },
    }


class AdapterTests(unittest.TestCase):
    def test_attempt_pods_become_ordered_tasks(self):
        tasks, pods = adapter.build_tasks(
            [sample_pod(2, 0, 5), sample_pod(1, 1, 1)]
        )
        self.assertEqual(
            [task.name for task in tasks],
            ["example-a2-mg4-smoke-v1", "example-a2-mg4-smoke-v2"],
        )
        self.assertEqual(
            [task.status for task in tasks], ["FAILED", "COMPLETED"]
        )
        self.assertEqual(tasks[0].duration_seconds, 30.0)
        self.assertEqual(len(pods), 2)

    def test_legacy_regex_cannot_be_reused_for_a_new_run_id(self):
        payload = {"items": [sample_pod(1, 0, 1)]}
        env = {
            "POD_LABEL_SELECTOR": "app.kubernetes.io/name=a2-mg4",
            "FALLBACK_RUN_ID": "a2-mg4-smoke-20260826",
            "JOB_NAME_REGEX": "example-a2-mg4-smoke-v[1-6]",
        }
        with mock.patch.object(
            adapter, "in_cluster_get", return_value=payload
        ), mock.patch.dict(adapter.os.environ, env, clear=False):
            with self.assertRaisesRegex(
                RuntimeError, "legacy fallback is restricted"
            ):
                adapter.select_attempt_pods("test-namespace", "new-run")

    def test_reads_completed_popinsnake_vcf_and_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            run_root = Path(directory)
            results = run_root / "results"
            provenance = run_root / "provenance"
            results.mkdir()
            provenance.mkdir()
            (run_root / "RUN_STATUS").write_text(
                "COMPLETED\n", encoding="utf-8"
            )
            vcf = results / "insertions_genotypes.vcf.gz"
            with gzip.open(vcf, "wt", encoding="utf-8") as handle:
                handle.write("##fileformat=VCFv4.2\n")
                handle.write(
                    "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT"
                    "\tS0001\tS0002\tS0003\n"
                )
                handle.write("chr21\t42\t.\tN\t<INS>\t.\tPASS\t.\tGT\t0/1\t0/0\t1/1\n")
            digest = hashlib.sha256(vcf.read_bytes()).hexdigest()
            (provenance / "result-SHA256SUMS").write_text(
                f"{digest}  {vcf}\n", encoding="utf-8"
            )
            (provenance / "workflow-commit.txt").write_text(
                "359d94165dcd086adf0511598bf21102c7cf0e0c\n",
                encoding="utf-8",
            )
            (provenance / "snakemake-version.txt").write_text(
                "7.32.4\n", encoding="utf-8"
            )
            (provenance / "completed-at.txt").write_text(
                "2026-08-28T16:34:46+00:00\n", encoding="utf-8"
            )

            result = adapter.read_popinsnake_result_metadata(run_root)

            self.assertEqual(result["variant_record_count"], 1)
            self.assertEqual(result["samples"], ["S0001", "S0002", "S0003"])
            self.assertEqual(result["output_sha256"], digest)
            self.assertEqual(result["provenance"]["snakemake"], "7.32.4")

    def test_snakemake_ttl_has_no_nextflow_identity(self):
        start = datetime(2026, 8, 26, 13, 0, tzinfo=timezone.utc)
        end = start + timedelta(seconds=30)
        task = core.TaskRecord(
            task_id="v1",
            hash_value="uid-v1",
            pod_name="mg4-v1-pod",
            name="example-a2-mg4-smoke-v1",
            status="COMPLETED",
            exit_code=0,
            submit=start,
            duration_seconds=30.0,
            realtime_seconds=30.0,
            end=end,
        )
        args = argparse.Namespace(
            application_domain_uri="https://example.org/domain/metagenomics",
            backend_uri="https://example.org/backend/kubernetes",
            base_uri="http://example.org/vivo-import/run-metadata/",
            cluster_label="FONDA Kubernetes Cluster",
            cluster_uri="https://example.org/cluster/fonda",
            code_uri="https://github.com/CRC-FONDA/A2-job-granularity",
            duration_calculation_method="Kubernetes container timestamps.",
            engine_label="Snakemake",
            engine_uri="https://example.org/engine/snakemake",
            include_cached_origin_metrics=False,
            namespace="test-namespace",
            ontology_uri="http://example.org/ontology/run-metadata#",
            parallelism_note="One Kubernetes Job attempt.",
            prom_url="http://prometheus.example.org",
            publication_uri="",
            resource_accounting_scope="All workflow attempt Pods.",
            run_description="A deterministic smoke reproduction.",
            run_operator_uri="https://example.org/person/operator",
            trace_archive="",
            trace_data_format="Kubernetes JSON",
            trace_types="Kubernetes Pod status",
            workflow_description="",
            workflow_name=(
                "Metagenomic read mapping with customizable job granularity"
            ),
            workflow_repo_url=(
                "https://github.com/CRC-FONDA/A2-job-granularity"
            ),
            workflow_uri="https://example.org/workflow/mg4",
        )
        ttl, audit = core.build_ttl(
            args=args,
            tasks=[task],
            stages=[
                {
                    "slug": "attempt-1",
                    "label": "MG-4 attempt 1",
                    "tasks": [task],
                }
            ],
            pod_metrics={
                "mg4-v1-pod": core.PodMetrics(
                    pod_name="mg4-v1-pod",
                    cpu_seconds=5.0,
                    energy_joules=3600.0,
                )
            },
            run_start=start,
            run_end=end,
            run_status="Succeeded",
            log_metadata={
                "run_id": "mg4-test",
                "session_id": None,
                "run_name": "mg4-test",
                "engine_version": "7.32.4",
                "nextflow_version": None,
                "failure_reason": None,
            },
            code_version="abc123",
            git_commit="f10646a89fa96c1ffcfcf1a8056fc353dd10367f",
            git_dirty=True,
            energy_metric="kepler_container_joules_total",
            carbon_info=core.CarbonIntensityInfo(
                kg_per_kwh=0.3, source="test"
            ),
            node_infos=[],
            images=["ubuntu:22.04"],
            responsible_researchers=[],
            responsible_researcher_uris=[],
            subproject_uris=[],
            language_uris=[],
            input_datasets=[],
        )
        self.assertIn('rdfs:label "Snakemake"@en', ttl)
        self.assertNotIn('rdfs:label "Nextflow"@en', ttl)
        self.assertNotIn("rm:nextflowSessionId", ttl)
        self.assertIn("A deterministic smoke reproduction", ttl)
        self.assertEqual(audit["engine"]["label"], "Snakemake")
        self.assertEqual(audit["engine"]["version"], "7.32.4")

    def test_failed_attempt_stage_is_failed(self):
        start = datetime(2026, 8, 26, 13, 0, tzinfo=timezone.utc)
        failed = core.TaskRecord(
            task_id="v1",
            hash_value="uid-v1",
            pod_name="mg4-v1-pod",
            name="example-a2-mg4-smoke-v1",
            status="FAILED",
            exit_code=1,
            submit=start,
            duration_seconds=30.0,
            realtime_seconds=30.0,
            end=start + timedelta(seconds=30),
        )
        self.assertEqual(core.derive_status([failed], True, False), "Failed")


if __name__ == "__main__":
    unittest.main()
