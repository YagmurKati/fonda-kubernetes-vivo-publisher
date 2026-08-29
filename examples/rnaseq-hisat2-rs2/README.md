# RNA-seq HISAT2 RS2 tested profile

This profile collects metadata for
[`Nine-s/nextflow_RS2_hisat2`](https://github.com/Nine-s/nextflow_RS2_hisat2)
on FONDA Kubernetes at commit
`68b9e62cd614cb901a45e9df8898203384e043ac`.

The verified `HISAT2-RS2-RUN06` session completed on 2026-08-29 with 302/302
successful trace rows: 301 cached origin executions and one newly completed
Cufflinks execution. The trace contains three strandness checks, three FASTP
tasks, two annotation helpers, one HISAT2 index, three FASTQ splits, 143 HISAT2
alignments, 143 Samtools conversions, one 23,777,553,300-byte merged BAM, and
three Cufflinks entries. No trace row has a non-zero exit code.

The validated metadata covers the full 37,207-second origin-plus-resume
interval and reports 94,439.6727 CPU-seconds, 3.27696 GB average memory,
17.9244 GB peak memory, and 1.000163 kWh. Kepler energy was directly available
for 245 pods; the audit explicitly marks fallback energy as estimated. The
preliminary CO2Map DE direct-CO2 factor (0.098 kg/kWh) produces a 0.098016 kg
estimate and is recorded as a model-based preliminary value, not a finalized
historical measurement.

The upstream graph sends three per-sample strandness values to Cufflinks even
though all three are `firststrand`; each task analyzes the same merged BAM and
publishes `transcripts.gtf`. The tested run preserves every task under
`cufflinks_by_task/` before publication-name collision can hide it. The two
independently executed 47,338,490-byte GTFs have different SHA-256 values, so
both are retained as distinct evidence. A proposed run-level-channel fix is
kept with the run handoff but was not used in this exact upstream-graph run.

The final dry run completed without contacting VIVO and generated validated
Turtle with SHA-256
`4a50ec131107de1350f5e6dfadda3ef91cdcec7ff6f3323bb67b8b951589e99c`.
The profile declares all six scientific containers by immutable digest. The
collector merges those declarations with Kubernetes-discovered names and
runtime image IDs, retaining complete container provenance even after
successful task pods are deleted.

## Required PVC evidence

For `HISAT2-RS2-RUN06`, this profile expects:

```text
/workspace/results/HISAT2-RS2-RUN06/trace-HISAT2-RS2-RUN06.txt
/workspace/results/HISAT2-RS2-RUN06/nextflow-HISAT2-RS2-RUN06.log
/workspace/results/HISAT2-RS2-RUN06/nextflow-debug-HISAT2-RS2-RUN06-combined.log
/workspace/rnaseq-hisat2-rs2/source/              pinned workflow checkout
```

The combined debug log concatenates the preserved RUN03 origin log and RUN06
resume log without changing either original. This lets the collector report
the complete session interval rather than only the final resume interval.

## Validate without publishing

The tested profile already points to namespace `yagmur`, PVC `rnaseq-pvc`, and
the run evidence above. The command below deploys the shared collector, reads
the trace and retained Prometheus/Kepler series, creates Turtle plus a metrics
audit, and validates the VIVO update without contacting VIVO:

```bash
CONFIG_FILE=examples/rnaseq-hisat2-rs2/publisher.env.example \
  ./scripts/publish-run.sh HISAT2-RS2-RUN06 --dry-run
```

`INCLUDE_CACHED_ORIGIN_METRICS=1` is set in the profile because RUN06 resumes
the same Nextflow session. `REQUIRE_SUCCEEDED=0` accepts a terminal mix of
`COMPLETED` and `CACHED`; failures, aborts, non-zero exits, or an incomplete
trace still do not become successful metadata.

## Collect and send automatically to VIVO

Store an approved non-admin VIVO publisher account once, using hidden prompts:

```bash
CONFIG_FILE=examples/rnaseq-hisat2-rs2/publisher.env.example \
  ./scripts/configure-secrets.sh
```

After a workflow run and its debug-log archive succeed, one command collects,
validates, and uploads the generated RDF automatically:

```bash
CONFIG_FILE=examples/rnaseq-hisat2-rs2/publisher.env.example \
  ./scripts/publish-run.sh HISAT2-RS2-RUN06
```

Only the Turtle RDF is sent to VIVO. The timestamped Turtle, task metrics JSON,
and publication receipt remain in `/workspace/vivo-outbox` on the PVC.
Publication is receipt-guarded against accidental duplicate upload.

For a launcher, keep publication conditional on successful workflow and
evidence capture:

```bash
run_hisat2_rs2 && archive_combined_debug_log && \
  CONFIG_FILE=examples/rnaseq-hisat2-rs2/publisher.env.example \
    ./scripts/publish-run.sh "$RUN_ID"
```

## Input provenance

`input_datasets.json` records the three ENA accessions and Ensembl release-106
genome, cDNA, and annotation sources. `input-SHA256SUMS` contains the hashes of
the exact bytes staged on the shared PVC.
