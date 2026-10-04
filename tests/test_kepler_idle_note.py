import sys
import unittest
from pathlib import Path

from collector.collect_nextflow_run_metadata import (
    CarbonIntensityInfo,
    DEFAULT_CLUSTER_URI,
    FONDA_KEPLER_IDLE_NOTE,
    metric_methods,
)

COLLECTOR_DIR = Path(__file__).resolve().parents[1] / "collector"
sys.path.insert(0, str(COLLECTOR_DIR))

import collect_airflow_kubernetes_metadata as airflow  # noqa: E402


def summary(energy_pods: int) -> dict:
    return {
        "cpu_source": "prometheus",
        "cpu_pod_count": 3,
        "cpu_fallback_count": 0,
        "memory_source": "prometheus",
        "energy_pod_count": energy_pods,
        "energy_estimated": False,
    }


CARBON = CarbonIntensityInfo(kg_per_kwh=0.4, source="test")
START = "Energy is the sum of per-pod Kepler measurements for 2 of 3 pod(s)."


class NextflowEnergyMethodTests(unittest.TestCase):
    def test_fonda_cluster_run_says_idle_power_is_included(self) -> None:
        text = metric_methods(summary(2), 3, CARBON, cluster_uri=DEFAULT_CLUSTER_URI)["energy"]
        self.assertTrue(text.startswith(START))
        self.assertTrue(text.endswith(FONDA_KEPLER_IDLE_NOTE))
        self.assertIn("Idle power is included", text)
        self.assertIn("not independent of node temperature", text)

    def test_note_comes_after_the_other_notes(self) -> None:
        text = metric_methods(
            dict(summary(2), energy_estimated=True), 3, CARBON, True, cluster_uri=DEFAULT_CLUSTER_URI
        )["energy"]
        self.assertLess(text.index("short-lived pod"), text.index("Nextflow cache"))
        self.assertLess(text.index("Nextflow cache"), text.index("Idle power is included"))

    def test_no_note_without_measured_energy(self) -> None:
        text = metric_methods(summary(0), 3, CARBON, cluster_uri=DEFAULT_CLUSTER_URI)["energy"]
        self.assertEqual(text, "Energy is the sum of per-pod Kepler measurements for 0 of 3 pod(s).")

    def test_no_note_for_another_cluster(self) -> None:
        other = "http://example.org/vivo-import/run-metadata/cluster/other-cluster"
        self.assertEqual(metric_methods(summary(2), 3, CARBON, cluster_uri=other)["energy"], START)
        self.assertEqual(metric_methods(summary(2), 3, CARBON)["energy"], START)

    def test_other_method_texts_are_unchanged(self) -> None:
        with_note = metric_methods(summary(2), 3, CARBON, cluster_uri=DEFAULT_CLUSTER_URI)
        without = metric_methods(summary(2), 3, CARBON)
        for key in ("cpu", "memory", "carbon"):
            self.assertEqual(with_note[key], without[key])


class AirflowEnergyMethodTests(unittest.TestCase):
    def test_same_note_as_the_nextflow_collector(self) -> None:
        self.assertEqual(airflow.FONDA_KEPLER_IDLE_NOTE, FONDA_KEPLER_IDLE_NOTE)
        self.assertTrue(DEFAULT_CLUSTER_URI.endswith("/cluster/" + airflow.FONDA_CLUSTER_SLUG))

    def test_fonda_cluster_run_says_idle_power_is_included(self) -> None:
        queries = {"pod-a": "increase(x[60s])", "pod-b": None}
        text, fallback = airflow.summarize_energy_method(
            "kepler_container_joules_total", queries, cluster_slug="fonda-cluster"
        )
        self.assertFalse(fallback)
        self.assertTrue(text.startswith("Energy collected from Prometheus using Kepler metric"))
        self.assertTrue(text.endswith(FONDA_KEPLER_IDLE_NOTE))
        text, fallback = airflow.summarize_energy_method(
            "kepler_container_joules_total", {"pod-a": "avg_over_time(x[60s])"}, 1, 1, cluster_slug="fonda-cluster"
        )
        self.assertTrue(fallback)
        self.assertTrue(text.endswith(FONDA_KEPLER_IDLE_NOTE))

    def test_no_note_without_energy_or_for_another_cluster(self) -> None:
        text, _ = airflow.summarize_energy_method(None, {"pod-a": None}, cluster_slug="fonda-cluster")
        self.assertEqual(text, "Energy could not be derived from Prometheus/Kepler metrics.")
        for slug in ("other-cluster", None):
            text, _ = airflow.summarize_energy_method(
                "kepler_container_joules_total", {"pod-a": "increase(x[60s])"}, cluster_slug=slug
            )
            self.assertNotIn("Idle power", text)


if __name__ == "__main__":
    unittest.main()
