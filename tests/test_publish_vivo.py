import importlib.util
import json
import sys
import tempfile
import unittest
import urllib.parse
from pathlib import Path
from unittest import mock


MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "publisher" / "publish_vivo.py"
)
SPEC = importlib.util.spec_from_file_location("publish_vivo", MODULE_PATH)
assert SPEC and SPEC.loader
publish_vivo = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = publish_vivo
SPEC.loader.exec_module(publish_vivo)


SAMPLE_TTL = """\
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix ex: <http://example.org/> .

<urn:fonda:test> rdfs:label "temporary test"@en ;
  ex:value "1" .
"""

RUN_TTL = """\
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix vivo: <http://vivoweb.org/ontology/core#> .
@prefix rm: <http://example.org/ontology/run-metadata#> .

<urn:fonda:shared-workflow>
  rm:hasRun <urn:fonda:run-1> .

<urn:fonda:run-1>
  rdf:type rm:RunMetadata ;
  vivo:dateTimeValue <urn:fonda:date-1> ;
  rm:hasWorkflowProcess <urn:fonda:process-1> .

<urn:fonda:date-1>
  rdf:type vivo:DateTimeValue .

<urn:fonda:process-1>
  rdf:type rm:WorkflowProcessRun ;
  rm:isWorkflowProcessOf <urn:fonda:run-1> .
"""


class TurtleUpdateTests(unittest.TestCase):
    def test_converts_collector_turtle_to_named_graph_insert(self):
        update = publish_vivo.turtle_to_insert_update(
            SAMPLE_TTL, publish_vivo.DEFAULT_GRAPH
        )
        self.assertIn(
            "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>", update
        )
        self.assertIn("INSERT DATA", update)
        self.assertIn(f"GRAPH <{publish_vivo.DEFAULT_GRAPH}>", update)
        self.assertIn('<urn:fonda:test> rdfs:label "temporary test"@en', update)

    def test_rejects_blank_nodes(self):
        turtle = SAMPLE_TTL + '\n_:generated rdfs:label "unsafe" .\n'
        with self.assertRaisesRegex(publish_vivo.PublishError, "blank nodes"):
            publish_vivo.turtle_to_insert_update(
                turtle, publish_vivo.DEFAULT_GRAPH
            )

    def test_rejects_empty_turtle(self):
        with self.assertRaisesRegex(publish_vivo.PublishError, "no @prefix"):
            publish_vivo.turtle_to_insert_update(
                "# no data\n", publish_vivo.DEFAULT_GRAPH
            )

    def test_builds_run_scoped_delete_without_shared_resource(self):
        update, run_iri, resource_count = (
            publish_vivo.turtle_to_run_delete_update(
                RUN_TTL, publish_vivo.DEFAULT_GRAPH
            )
        )

        self.assertEqual(run_iri, "urn:fonda:run-1")
        self.assertEqual(resource_count, 3)
        self.assertIn("DELETE", update)
        self.assertIn("<urn:fonda:run-1>", update)
        self.assertIn("<urn:fonda:date-1>", update)
        self.assertIn("<urn:fonda:process-1>", update)
        self.assertNotIn("<urn:fonda:shared-workflow>", update)
        self.assertIn("?object = ?target", update)

    def test_rejects_removal_turtle_without_one_run(self):
        with self.assertRaisesRegex(
            publish_vivo.PublishError, "exactly one rm:RunMetadata"
        ):
            publish_vivo.turtle_to_run_delete_update(
                SAMPLE_TTL, publish_vivo.DEFAULT_GRAPH
            )


class ReceiptTests(unittest.TestCase):
    def test_removed_receipt_does_not_block_republication(self):
        with tempfile.TemporaryDirectory() as directory:
            receipt_path = Path(directory) / "run.published.json"
            receipt_path.write_text(
                json.dumps(
                    {
                        "ttl_sha256": "abc",
                        "endpoint": publish_vivo.DEFAULT_ENDPOINT,
                        "graph": publish_vivo.DEFAULT_GRAPH,
                        "http_status": 200,
                        "removed_at": "2026-09-02T12:00:00+00:00",
                    }
                ),
                encoding="utf-8",
            )

            self.assertFalse(
                publish_vivo.receipt_matches(
                    receipt_path,
                    "abc",
                    publish_vivo.DEFAULT_ENDPOINT,
                    publish_vivo.DEFAULT_GRAPH,
                )
            )


class HttpPublicationTests(unittest.TestCase):
    def test_posts_expected_vivo_form_fields(self):
        response = mock.MagicMock()
        response.status = 200
        response.read.return_value = b"<H1>200 SPARQL update accepted.</H1>"
        response.__enter__.return_value = response

        with mock.patch.object(
            publish_vivo.urllib.request, "urlopen", return_value=response
        ) as urlopen:
            status, body = publish_vivo.post_update_once(
                publish_vivo.DEFAULT_ENDPOINT,
                "publisher@example.org",
                "not-logged-password",
                "INSERT DATA {}",
                30,
            )

        self.assertEqual(status, 200)
        self.assertIn("accepted", body)
        request = urlopen.call_args.args[0]
        form = urllib.parse.parse_qs(request.data.decode("utf-8"))
        self.assertEqual(form["email"], ["publisher@example.org"])
        self.assertEqual(form["password"], ["not-logged-password"])
        self.assertEqual(form["update"], ["INSERT DATA {}"])

    def test_retries_transient_http_status(self):
        with mock.patch.object(
            publish_vivo,
            "post_update_once",
            side_effect=[(503, "later"), (200, "accepted")],
        ), mock.patch.object(publish_vivo.time, "sleep"):
            status, _, attempts = publish_vivo.publish_with_retries(
                publish_vivo.DEFAULT_ENDPOINT,
                "publisher@example.org",
                "password",
                "INSERT DATA {}",
                max_attempts=2,
                retry_delay_seconds=0,
                timeout_seconds=30,
            )
        self.assertEqual(status, 200)
        self.assertEqual(attempts, 2)

    def test_does_not_retry_authorization_failure(self):
        with mock.patch.object(
            publish_vivo,
            "post_update_once",
            return_value=(403, "Account is not authorized"),
        ):
            with self.assertRaisesRegex(
                publish_vivo.PublishError, "HTTP 403"
            ):
                publish_vivo.publish_with_retries(
                    publish_vivo.DEFAULT_ENDPOINT,
                    "publisher@example.org",
                    "password",
                    "INSERT DATA {}",
                    max_attempts=5,
                    retry_delay_seconds=0,
                    timeout_seconds=30,
                )


if __name__ == "__main__":
    unittest.main()
