import argparse
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from collector import check_kubernetes_node_use as checker
from collector.collect_nextflow_run_metadata import (
    CarbonIntensityInfo,
    PodMetrics,
    TaskRecord,
    build_ttl,
    kubernetes_node_use,
    node_use_text,
)

START = datetime(2026, 9, 29, 22, 40, 0, tzinfo=timezone.utc)
END = START + timedelta(seconds=1000)
NODES = ["hu-worker-c34", "hu-worker-c39"]


def pod(namespace, name, node, kind="Job"):
    return {"metric": {"namespace": namespace, "pod": name, "node": node, "created_by_kind": kind}, "value": [0, "1"]}


def cpu(namespace, name, seconds):
    return {"metric": {"namespace": namespace, "pod": name}, "value": [0, str(seconds)]}


def prometheus(pods, usage):
    """Stand-in for prom_query: pod records for kube_pod_info, CPU seconds otherwise."""
    queries = []

    def answer(_url, query):
        queries.append(query)
        return pods if "kube_pod_info" in query else usage

    return answer, queries


class NodeUseTests(unittest.TestCase):
    def node_use(self, pods, usage, own=("nf-1", "nf-2", "nextflow-driver"), **kwargs):
        answer, queries = prometheus(pods, usage)
        with mock.patch("collector.collect_nextflow_run_metadata.prom_query", side_effect=answer):
            return kubernetes_node_use("http://prom", NODES, own, START, END, **kwargs), queries

    def test_idle_nodes_are_exclusive_and_daemons_do_not_count(self) -> None:
        pods = [pod("yagmur", "nf-1", NODES[0]), pod("yagmur", "nf-2", NODES[1]),
                pod("yagmur", "nextflow-driver", NODES[0], "<none>"),
                pod("monitoring", "kepler-abc", NODES[0], "DaemonSet"),
                pod("kube-system", "kube-proxy-c34", NODES[0], "Node"),
                pod("felix", "idle-notebook", NODES[1], "StatefulSet")]
        usage = [cpu("yagmur", "nf-1", 4000), cpu("yagmur", "nf-2", 2000), cpu("yagmur", "nextflow-driver", 100),
                 cpu("monitoring", "kepler-abc", 900), cpu("kube-system", "kube-proxy-c34", 50),
                 cpu("felix", "idle-notebook", 20), cpu("other", "pod-on-another-node", 99999)]
        result, queries = self.node_use(pods, usage)
        self.assertTrue(result["exclusive"])
        self.assertEqual(result["text"],
                         "exclusive (other workloads used 0.02 CPUs on average on the run's 2 nodes)")
        self.assertAlmostEqual(result["run_cpus"], 6.1)
        self.assertAlmostEqual(result["node_daemon_cpus"], 0.95)
        self.assertAlmostEqual(result["other_cpus"], 0.02)
        self.assertEqual(result["run_pods_found"], 3)
        self.assertEqual(result["other_cpu_seconds_by_namespace"], {"felix": 20.0})
        self.assertIn('node=~"hu-worker-c34|hu-worker-c39"', queries[0])
        self.assertIn(f"[1000s] @ {int(END.timestamp())}", queries[0])
        self.assertIn(f"[1000s] @ {int(END.timestamp())}", queries[1])

    def test_another_workload_makes_the_run_non_exclusive(self) -> None:
        pods = [pod("yagmur", "nf-1", NODES[0]), pod("felix", "train-1", NODES[0]), pod("felix", "train-2", NODES[1])]
        usage = [cpu("yagmur", "nf-1", 4000), cpu("felix", "train-1", 8000), cpu("felix", "train-2", 4400)]
        result, _ = self.node_use(pods, usage)
        self.assertFalse(result["exclusive"])
        self.assertEqual(result["text"],
                         "non-exclusive (other workloads used 12.40 CPUs on average on the run's 2 nodes)")

    def test_limit_can_be_changed(self) -> None:
        pods = [pod("yagmur", "nf-1", NODES[0]), pod("felix", "small", NODES[0])]
        usage = [cpu("yagmur", "nf-1", 4000), cpu("felix", "small", 800)]
        self.assertFalse(self.node_use(pods, usage)[0]["exclusive"])
        self.assertTrue(self.node_use(pods, usage, max_other_cpus=1.0)[0]["exclusive"])

    def test_a_second_run_of_the_same_person_counts_as_other_workload(self) -> None:
        pods = [pod("yagmur", "nf-1", NODES[0]), pod("yagmur", "nf-other-run", NODES[0])]
        usage = [cpu("yagmur", "nf-1", 4000), cpu("yagmur", "nf-other-run", 3000)]
        self.assertFalse(self.node_use(pods, usage)[0]["exclusive"])
        # without pod names the whole namespace is the run
        by_namespace, _ = self.node_use(pods, usage, own=None, own_namespace="yagmur")
        self.assertTrue(by_namespace["exclusive"])
        self.assertEqual(by_namespace["run_pods_found"], 2)

    def test_no_pod_records_means_unknown(self) -> None:
        self.assertIsNone(self.node_use([], [cpu("yagmur", "nf-1", 10)])[0])
        answer, queries = prometheus([], [])
        with mock.patch("collector.collect_nextflow_run_metadata.prom_query", side_effect=answer):
            self.assertIsNone(kubernetes_node_use("http://prom", [], ["nf-1"], START, END))
        self.assertEqual(queries, [])

    def test_one_node_wording_and_dots_in_node_names(self) -> None:
        self.assertEqual(node_use_text(True, 0.0, 1),
                         "exclusive (other workloads used 0.00 CPUs on average on the run's node)")
        answer, queries = prometheus([pod("yagmur", "nf-1", "node1.example.org")], [])
        with mock.patch("collector.collect_nextflow_run_metadata.prom_query", side_effect=answer):
            kubernetes_node_use("http://prom", ["node1.example.org"], ["nf-1"], START, END)
        self.assertIn('node=~"node1[.]example[.]org"', queries[0])


class NodeUseInTurtleTests(unittest.TestCase):
    def ttl(self, node_use):
        task = TaskRecord(task_id="1", hash_value="aa/1", pod_name="nf-test", name="test", status="COMPLETED",
                          exit_code=0, submit=START, duration_seconds=2.0, realtime_seconds=1.0, end=END)
        args = argparse.Namespace(
            application_domain_uri="", backend_uri="", base_uri="http://example.org/vivo-import/run-metadata/",
            cluster_label="Fonda Cluster", cluster_uri="https://example.org/cluster", code_uri="",
            engine_uri="", include_cached_origin_metrics=False, namespace="test",
            ontology_uri="http://example.org/ontology/run-metadata#", prom_url="http://127.0.0.1:19090",
            publication_uri="", run_identity_scope="fonda", run_operator_uri="", trace_archive="",
            workflow_trace_repository="", run_trace_archive="", trace_data_format="TSV",
            trace_types="Nextflow trace", workflow_name="Node use test", workflow_repo_url="",
            workflow_uri="https://example.org/workflow/test")
        return build_ttl(
            args=args, tasks=[task], stages=[{"slug": "test", "label": "Test", "tasks": [task]}],
            pod_metrics={"nf-test": PodMetrics(pod_name="nf-test", cpu_seconds=1.0, energy_joules=3600.0)},
            run_start=START, run_end=END, run_status="Succeeded",
            log_metadata={"session_id": "s", "run_name": "r", "nextflow_version": "25.04.8", "failure_reason": None},
            code_version="abc", git_commit=None, git_dirty=None, energy_metric="kepler_container_joules_total",
            carbon_info=CarbonIntensityInfo(kg_per_kwh=0.3, source="test"), node_infos=[], images=[],
            responsible_researchers=[], responsible_researcher_uris=[], subproject_uris=[], language_uris=[],
            input_datasets=[], **({"node_use": node_use} if node_use is not None else {}))

    def test_node_use_is_published_and_recorded(self) -> None:
        use = {"exclusive": True, "text": node_use_text(True, 0.02, 3)}
        ttl_text, audit = self.ttl(use)
        self.assertIn('rm:nodeUse "exclusive (other workloads used 0.02 CPUs on average on the run\'s 3 nodes)"',
                      ttl_text)
        self.assertEqual(audit["node_use"], use)

    def test_no_node_use_no_statement(self) -> None:
        ttl_text, audit = self.ttl(None)
        self.assertNotIn("rm:nodeUse", ttl_text)
        self.assertIsNone(audit["node_use"])


class CheckerTests(unittest.TestCase):
    PODS = [pod("yagmur", "nf-1", NODES[0]), pod("monitoring", "kepler-abc", NODES[0], "DaemonSet")]
    USAGE = [cpu("yagmur", "nf-1", 4000), cpu("monitoring", "kepler-abc", 900)]

    def run_checker(self, argv, pods=None):
        answer, queries = prometheus(self.PODS if pods is None else pods, self.USAGE)

        def by_node(url, query):   # hosts outside Kubernetes have no pod records
            if "kube_pod_info" in query and "hpc-cms01" in query:
                return []
            return answer(url, query)

        output = io.StringIO()
        with mock.patch("collector.collect_nextflow_run_metadata.prom_query", side_effect=by_node), \
                mock.patch("collector.collect_nextflow_run_metadata.ensure_prometheus_reachable"), \
                redirect_stdout(output):
            checker.main(argv)
        return output.getvalue(), queries

    def test_runs_exported_from_vivo(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            table, out = Path(directory) / "runs.csv", Path(directory) / "node-use.ttl"
            table.write_text(
                "run,start,end,hosts\n"
                "http://example.org/run/k8s-1,2026-09-30T00:40:00,2026-09-30T00:56:40,hu-worker-c34 hu-worker-c39\n"
                "http://example.org/run/k8s-2,2026-09-29T22:40:00+00:00,2026-09-29T22:56:40Z,hu-worker-c34\n"
                "http://example.org/run/slurm-1,2026-10-02T11:32:10+02:00,2026-10-02T11:40:00+02:00,hpc-cms01-007\n")
            text, queries = self.run_checker(["--runs", str(table), "--namespace", "yagmur", "--output", str(out)])
            ttl = out.read_text()
        self.assertIn("exclusive      k8s-1", text)
        self.assertIn("no data        slurm-1", text)
        self.assertIn("2 of 3 run(s) written", text)
        self.assertEqual(ttl.count("rm:nodeUse"), 2)
        self.assertIn("<http://example.org/run/k8s-1> rm:nodeUse \"exclusive (other workloads used 0.00 CPUs", ttl)
        self.assertNotIn("slurm-1", ttl)
        # a time without offset is Berlin time: 00:56:40 CEST = 22:56:40 UTC, the same instant as run k8s-2
        self.assertIn(f"@ {int(END.timestamp())}", queries[0])
        self.assertIn(f"@ {int(END.timestamp())}", queries[2])

    def test_tab_separated_export_with_typed_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            table, out = Path(directory) / "runs.tsv", Path(directory) / "out.ttl"
            table.write_text(
                "?run\t?start\t?end\t?hosts\n"
                "<http://example.org/run/k8s-1>\t\"2026-09-30T00:40:00\"^^<http://www.w3.org/2001/XMLSchema#dateTime>\t"
                "\"2026-09-30T00:56:40\"^^<http://www.w3.org/2001/XMLSchema#dateTime>\t\"hu-worker-c34\"\n")
            text, _ = self.run_checker(["--runs", str(table), "--namespace", "yagmur", "--output", str(out)])
            self.assertIn("<http://example.org/run/k8s-1> rm:nodeUse", out.read_text())

    def test_metrics_file_names_the_pods(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            metrics, out = Path(directory) / "run.metrics.json", Path(directory) / "out.ttl"
            metrics.write_text(json.dumps({
                "run_uri": "http://example.org/run/k8s-3",
                "resource_accounting_start_utc": START.isoformat(), "resource_accounting_end_utc": END.isoformat(),
                "pod_metrics": {"nf-1": {"node_name": "hu-worker-c34"}, "nf-2": {"node_name": None}}}))
            pods = self.PODS + [pod("yagmur", "nf-of-another-run", NODES[0])]
            usage_before = list(self.USAGE)
            self.USAGE.append(cpu("yagmur", "nf-of-another-run", 3000))
            try:
                text, _ = self.run_checker([str(metrics), "--output", str(out)], pods)
            finally:
                self.USAGE[:] = usage_before
            self.assertIn("non-exclusive  k8s-3", text)
            self.assertIn("other workloads 3.00 CPUs (yagmur 3.00)", text)
            self.assertIn('"non-exclusive (other workloads used 3.00 CPUs on average on the run\'s node)"',
                          out.read_text())

    def test_nothing_written_when_no_run_has_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            table, out = Path(directory) / "runs.csv", Path(directory) / "out.ttl"
            table.write_text("run,start,end,hosts\nhttp://example.org/run/old,2026-08-01T10:00:00,2026-08-01T10:10:00,hu-worker-c34\n")
            text, _ = self.run_checker(["--runs", str(table), "--namespace", "yagmur", "--output", str(out)], pods=[])
            self.assertIn("No run could be checked", text)
            self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
