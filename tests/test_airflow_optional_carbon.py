import base64
import sys
import unittest
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock


COLLECTOR_DIR = Path(__file__).resolve().parents[1] / "collector"
sys.path.insert(0, str(COLLECTOR_DIR))

from collect_airflow_kubernetes_metadata import (  # noqa: E402
    electricitymap_token_from_secret,
    fetch_carbon_intensity_kg,
    summarize_carbon_method,
)


class OptionalAirflowCarbonTests(unittest.TestCase):
    @mock.patch("collect_airflow_kubernetes_metadata.kubectl_json")
    def test_token_is_decoded_from_namespace_secret(self, kubectl_json) -> None:
        kubectl_json.return_value = {
            "data": {"token": base64.b64encode(b"test-token").decode("ascii")}
        }

        token = electricitymap_token_from_secret("researcher", "carbon-secret")

        self.assertEqual(token, "test-token")
        kubectl_json.assert_called_once_with(
            ["get", "secret", "carbon-secret", "-n", "researcher"]
        )

    @mock.patch("collect_airflow_kubernetes_metadata.kubectl_json")
    def test_missing_secret_means_no_token(self, kubectl_json) -> None:
        kubectl_json.side_effect = RuntimeError("not found")
        self.assertIsNone(
            electricitymap_token_from_secret("researcher", "carbon-secret")
        )

    def test_no_intensity_means_no_carbon_method(self) -> None:
        self.assertIsNone(summarize_carbon_method(None, has_energy_value=True))

    @mock.patch("collect_airflow_kubernetes_metadata._em_request")
    def test_free_tier_falls_back_to_latest_value(self, em_request) -> None:
        unauthorized = urllib.error.HTTPError(
            "https://example.invalid/past-range", 401, "unauthorized", {}, None
        )
        self.addCleanup(unauthorized.close)
        em_request.side_effect = [
            unauthorized,
            {"zone": "DE", "carbonIntensity": 269},
        ]
        start = datetime(2026, 8, 25, 14, 0, tzinfo=timezone.utc)

        intensity, source = fetch_carbon_intensity_kg(
            "DE", "test-token", start, start + timedelta(minutes=10)
        )

        self.assertEqual(intensity, 0.269)
        self.assertIn("collection-time proxy", source)
        self.assertIn("api.electricitymaps.com/v4", em_request.call_args_list[0].args[0])


if __name__ == "__main__":
    unittest.main()
