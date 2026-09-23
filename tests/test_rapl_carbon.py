"""Synthetic carbon fixtures only; no fixture represents the published run."""
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "collector"))
import rapl_carbon as carbon
import collect_rnaseq_rapl_metadata as collector


class CarbonTests(unittest.TestCase):
    def setUp(self):
        self.start = carbon.stamp("2026-09-22T07:30:00Z")
        self.end = carbon.stamp("2026-09-22T08:30:00Z")
        self.points = [dict(datetime="2026-09-22T07:00:00Z", g_per_kwh=100),
                       dict(datetime="2026-09-22T08:00:00Z", g_per_kwh=300)]
        self.summary = dict(start_utc=carbon.iso(self.start), end_utc=carbon.iso(self.end),
                            namespace="test", energy_kwh=1)

    def test_hour_boundaries_are_energy_weighted(self):
        intervals = carbon.covered_intervals(self.points, self.start, self.end)
        def energy(begin, end):
            return {"package": 3_600_000 * (.25 if begin == self.start else .75), "dram": 360000}
        result = carbon.calculate(intervals, energy)
        self.assertAlmostEqual(result["package_kg"], .25)
        self.assertAlmostEqual(result["dram_kg"], .04)
        self.assertAlmostEqual(result["intensity_kg_per_kwh"], .25)
        self.assertNotAlmostEqual(result["intensity_kg_per_kwh"], .2)

    def test_missing_hour_latest_only_and_duplicates_are_rejected(self):
        for points in ([self.points[0]], [self.points[1]], self.points + [self.points[0]],
                       [dict(datetime="2026-09-23T07:00:00Z", g_per_kwh=200)]):
            with self.subTest(points=points), self.assertRaises(ValueError):
                carbon.covered_intervals(points, self.start, self.end)

    def test_zero_is_valid_but_null_negative_and_nonfinite_are_rejected(self):
        for value in (None, True, -1, float("nan"), float("inf")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                carbon.covered_intervals([dict(self.points[0], g_per_kwh=value), self.points[1]], self.start, self.end)
        points = [dict(p, g_per_kwh=0) for p in self.points]
        self.assertEqual(carbon.calculate(carbon.covered_intervals(points, self.start, self.end),
                          lambda *_: {"package": 1000, "dram": 10})["package_kg"], 0)

    def test_timezone_conversion_and_naive_rejection(self):
        self.assertEqual(carbon.stamp("2026-09-22T09:30:00+02:00"), self.start)
        with self.assertRaises(ValueError):
            carbon.stamp("2026-09-22T09:30:00")

    def test_provider_basis_and_units_are_checked(self):
        with self.assertRaises(ValueError):
            carbon.co2map_points(dict(state="DE", country="DE", unit="kg/kWh"))
        with self.assertRaises(ValueError):
            carbon.electricity_points(dict(zone="FR", temporalGranularity="hourly", history=[]))
        with self.assertRaises(ValueError):
            carbon.electricity_points(dict(zone="DE", temporalGranularity="hourly", history=[{
                "datetime": "2026-09-22T07:00:00Z", "emissionFactorType": "direct", "flowTraced": True}]))

    def test_history_response_is_checked_and_calculated_automatically(self):
        payload = dict(zone="DE", temporalGranularity="hourly", history=[{
            "datetime": p["datetime"], "carbonIntensity": p["g_per_kwh"], "emissionFactorType": "lifecycle",
            "flowTraced": True, "isEstimated": False} for p in self.points])
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(payload).encode()
        with mock.patch.object(carbon, "api_token", return_value="test-only"), \
             mock.patch.object(carbon.urllib.request, "urlopen", return_value=response):
            result = carbon.fetch_carbon(self.summary, lambda *_: {"package": 1800000, "dram": 180000})
        self.assertAlmostEqual(result["package_kg"], .2)
        self.assertEqual(result["basis"], "lifecycle CO2e")
        self.assertNotIn("test-only", json.dumps(result))

    def test_no_data_never_becomes_an_annual_average(self):
        payload = dict(state="DE", country="DE", unit="g/kWh", **{"Consumption-based Intensity (preliminary)": None})
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(payload).encode()
        with mock.patch.object(carbon, "api_token", return_value=""), \
             mock.patch.object(carbon.urllib.request, "urlopen", return_value=response), self.assertRaises(carbon.CarbonUnavailable):
            carbon.fetch_carbon(self.summary, mock.Mock())

    def test_publisher_blocks_old_metadata_without_carbon(self):
        with self.assertRaises(ValueError):
            carbon.require_carbon(self.summary)
        summary = dict(self.summary, carbon=dict(status="time-matched", start_utc="2026-09-23T07:00:00Z", end_utc=self.summary["end_utc"]))
        with self.assertRaises(ValueError):
            carbon.require_carbon(summary)

    def test_collection_failure_saves_reason_but_no_publishable_turtle(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            evidence = root / "evidence"
            (evidence / "rapl").mkdir(parents=True)
            (evidence / "rapl/metadata.json").write_text(json.dumps({"domains": []}))
            (evidence / "rapl/collector-start.txt").write_text(self.summary["start_utc"])
            output = root / "publication"
            with mock.patch.object(sys, "argv", ["collector", str(evidence), "--cluster", str(root / "cluster"), "--output", str(output)]), \
                 mock.patch.object(collector, "validate", return_value=(self.summary, [], [])), \
                 mock.patch.object(collector, "fetch_carbon", side_effect=carbon.CarbonUnavailable("No matching data", [])), self.assertRaises(SystemExit):
                collector.main()
            self.assertTrue((output / "carbon-unavailable.json").exists())
            self.assertFalse((output / "run.ttl").exists())

    def test_wrapper_stops_before_publishing_when_collection_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fake = root / "python3"
            log = root / "calls.txt"
            fake.write_text('#!/bin/bash\nprintf "%s\\n" "$1" >> "$TEST_CALL_LOG"\nexit 1\n')
            fake.chmod(0o755)
            import os
            process = subprocess.run(["bash", str(ROOT / "scripts/collect-and-publish-rnaseq-rapl.sh"), str(root)],
                env={**os.environ, "PATH": str(root) + os.pathsep + os.environ["PATH"], "TEST_CALL_LOG": str(log)}, capture_output=True)
            self.assertNotEqual(process.returncode, 0)
            calls = log.read_text().splitlines()
            self.assertEqual(len(calls), 1)
            self.assertTrue(calls[0].endswith("collect_rnaseq_rapl_metadata.py"))


if __name__ == "__main__":
    unittest.main()
