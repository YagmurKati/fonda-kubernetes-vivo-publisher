# RNA-seq STAR RS1 tested profile

This profile collects and publishes VIVO run metadata for the scientific
workflow in
[`Nine-s/nextflow_RS1_star`](https://github.com/Nine-s/nextflow_RS1_star).
That upstream repository is the canonical workflow source and should be cited
for the workflow. This repository supplies only the FONDA Kubernetes metadata
and VIVO publication adapter.

The tested source revision is upstream commit
[`8265c835d8fd76c9bad7b1e2499304929069050b`](https://github.com/Nine-s/nextflow_RS1_star/commit/8265c835d8fd76c9bad7b1e2499304929069050b).
The companion
[`YagmurKati/fonda-nextflow-rs1-star-runner`](https://github.com/YagmurKati/fonda-nextflow-rs1-star-runner)
documents the complete Kubernetes launch and calls this publisher after a
successful Job. It downloads the pinned upstream revision at deployment time;
it does not vendor or replace the upstream scientific code.

## Tested run

`STAR-RS1-RUN01` completed on 2026-08-31 with 16/16 successful tasks and no
cached, failed, or aborted task. The six process groups were CHECK_STRANDNESS,
FASTP, STAR_INDEX_REFERENCE, STAR_ALIGN, SAMTOOLS, and CUFFLINKS.

The Nextflow interval was 07:25:43.891–15:36:27.634 UTC (29,444 seconds).
Complete trace accounting reported 116,982.655 CPU-seconds, 5.06733 GB
time-weighted average memory, and 11.7043 GB peak concurrent RSS. Kepler
reported 1.0725910286763725 kWh for all 16 pods without an energy fallback.
CO2Map did not yet have finite values for the run window, so the published RDF
explicitly uses the configured fixed factor of 0.4 kg CO2e/kWh, producing
0.429036411470549 kg CO2e.

The published run is visible in
[FONDA VIVO](https://vivo-fonda.hu-berlin.de/vivo/individual?uri=http%3A%2F%2Fexample.org%2Fvivo-import%2Frun-metadata%2Frun%2Fyagmur-rna-seq-analysis-workflow-star-rs1-3afdb2f4-9abc-4fbc-86f2-c66e81b672ed-2026-08-31t07-25-43-891000-00-00).

## Evidence layout

For a run ID such as `STAR-RS1-RUN01`, the profile expects the workflow PVC to
contain:

```text
/workspace/results/STAR-RS1-RUN01/trace.txt
/workspace/results/STAR-RS1-RUN01/nextflow.log
/workspace/results/STAR-RS1-RUN01/nextflow-debug.log
/workspace/source/                         pinned upstream checkout
```

The trace must retain the Kubernetes pod name in `native_id`. The companion
runner archives `.nextflow.log` as `nextflow-debug.log` before the workflow Job
exits, which preserves the Nextflow session UUID and definitive completion
timestamp for later collection.

## Validate without publishing

```bash
CONFIG_FILE=examples/rnaseq-star-rs1/publisher.env.example \
  ./scripts/publish-run.sh STAR-RS1-RUN01 --dry-run
```

This deploys the collector, reads the completed trace and logs, retrieves
Prometheus CPU plus Kepler energy, creates Turtle and an audit JSON, and runs
the VIVO publisher validation without contacting VIVO.

## Collect and publish automatically

Store an approved non-admin VIVO publisher account once through hidden
prompts:

```bash
CONFIG_FILE=examples/rnaseq-star-rs1/publisher.env.example \
  ./scripts/configure-secrets.sh
```

After the Kubernetes workflow Job succeeds, one command collects, validates,
and sends the Turtle to VIVO:

```bash
CONFIG_FILE=examples/rnaseq-star-rs1/publisher.env.example \
  ./scripts/publish-run.sh STAR-RS1-RUN01
```

Only the Turtle is sent. The Turtle, detailed metrics audit, and HTTP-200
publication receipt remain under `/workspace/vivo-outbox` on
`rnaseq-star-rs1-pvc`. Existing receipts prevent accidental duplicate
publication unless `FORCE_REPUBLISH=1` is deliberately set.

For workflow launch plus automatic publication in one guarded operation, use
the companion runner's `scripts/run-and-publish.sh`. It invokes the command
above only after Kubernetes reports the scientific Job complete.

## Reproducibility

- The source revision is pinned to the upstream commit above.
- The five scientific container tags are resolved to immutable Docker registry
  digests in `publisher.env.example`.
- `input-SHA256SUMS` identifies the exact three paired-end ENA datasets and the
  Ensembl BDGP6.32 release-106 reference files used by the tested run.
- `REQUIRE_SUCCEEDED=1` prevents publication of active, cached,
  warning-bearing, failed, or aborted traces for this profile.
