# FONDA Spark filesystem word count

Published-artifact profile for the PySpark filesystem word-count example from
[`CRC-FONDA/s1-spark-examples`](https://github.com/CRC-FONDA/s1-spark-examples)
at source commit
[`98518a04e9b6deb916fefce536f4de67afd5ce7a`](https://github.com/CRC-FONDA/s1-spark-examples/commit/98518a04e9b6deb916fefce536f4de67afd5ce7a).
See the [published example in FONDA VIVO](https://vivo-fonda.hu-berlin.de/vivo/individual?uri=http%3A%2F%2Fexample.org%2Fvivo-import%2Frun-metadata%2Frun%2Fspark-wordcount-fs-20260914-01-spark-3bc712cac1f64dc894ea7c4fa5184ff9).

## 1. Published record

The run used Spark's native Kubernetes backend because the Spark Operator was
not installed. One driver and four executors completed the workflow, and the
result was independently compared with the source corpus before metadata was
generated. The publication identifies Soeren Becker as the responsible
researcher and S1: Testbeds and Repositories as the owning subproject. No run
operator is asserted.

The checked-in audit artifact is
[`publication-summary.json`](publication-summary.json). It records the public
VIVO URLs, source revision, immutable image, validation checksums, aggregate
measurements, attribution, publication status, and SHA-256 of the exact Turtle
accepted by VIVO.

The exact Turtle, receipt, collector, and full execution audit remain with the
workflow artifacts. They are not copied here because they contain internal
infrastructure identifiers. Raw pod snapshots, addresses, Prometheus queries,
node identifiers, and logs are likewise excluded from this public repository.

## 2. Evidence retained with the run

The retained private evidence bundle contains `validation.json`,
`prometheus-metrics.json`, the completed Spark event log, Kubernetes object and
log snapshots, source checksums, original output files, the exact evidence-to-
RDF collector, the published Turtle, and its HTTP 200 receipt.

The Spark collector is the exact adapter for the recorded run, not yet a
selectable engine in `scripts/publish-run.sh`.

## 3. Validate

Validate the public-safe summary and attribution safeguards:

```bash
python3 -m unittest tests.test_spark_wordcount_profile
```

The repository tests confirm the successful publication state, source
revision, responsible researcher, absence of a run operator, and absence of
internal infrastructure addresses in the public profile.

## 4. Publication

The historical record is already published. Do not publish it again when
installing this repository. Open the [workflow](https://vivo-fonda.hu-berlin.de/vivo/individual?uri=http%3A%2F%2Fexample.org%2Fvivo-import%2Frun-metadata%2Fworkflow%2Ffonda-spark-filesystem-word-count)
or the [workflow run](https://vivo-fonda.hu-berlin.de/vivo/individual?uri=http%3A%2F%2Fexample.org%2Fvivo-import%2Frun-metadata%2Frun%2Fspark-wordcount-fs-20260914-01-spark-3bc712cac1f64dc894ea7c4fa5184ff9)
in VIVO to inspect it.

## 5. Remove a publication

The usual `./scripts/remove-run.sh PUBLICATION_ID --dry-run` and
`./scripts/remove-run.sh PUBLICATION_ID` commands expect the generic publisher
outbox and therefore do not target this historical Spark artifact. Its exact
private Turtle and receipt are required for a validated removal. Do not remove
the record without deliberate authorization.
