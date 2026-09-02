# RNA-seq HISAT2 RS1 tested profile

This profile collects and publishes metadata for
[`Nine-s/nextflow_RS1_hisat2_new`](https://github.com/Nine-s/nextflow_RS1_hisat2_new)
on FONDA Kubernetes. It was verified with the uncached `HISAT2-RS1-RUN01`
execution at commit `6b7688c7cab3c0bdb39e0e228ceab2bac31e2caa`, run in
`mode = exon_splice_site` (splice-aware HISAT2 index built from the GTF exons and
splice sites, aligning FASTP-trimmed reads).

`HISAT2-RS1-RUN01` completed 18/18 tasks with no cache, failure, or abort in
34,078 seconds of wall-clock time: three strandedness checks, three FASTP tasks,
two annotation helpers, one HISAT2 index, three HISAT2 alignments, three Samtools
sort steps, and three Cufflinks quantifications. The collected audit reports
72,348.76 CPU seconds, 2.0284 GB average and 14.8994 GB peak concurrent memory,
and 0.80437 kWh of Kepler energy. Carbon is 0.34105 kg CO2e using the
Electricity Maps latest-available factor (0.424 kg/kWh) as a clearly labelled
collection-time proxy.

The profile published `HISAT2-RS1-RUN01` to FONDA VIVO with HTTP 200 on
2026-09-02. The
[public workflow-run record](https://vivo-fonda.hu-berlin.de/vivo/individual?uri=http%3A%2F%2Fexample.org%2Fvivo-import%2Frun-metadata%2Frun%2Fyagmur-rna-seq-analysis-workflow-hisat2-rs1-c0ece5b9-63ab-41ac-a0f5-1980d02b79dc-2026-09-01t11-38-23-240000-00-00)
shows the status, process groups, metrics, inputs, containers, and pinned source
commit. The exact [HTTP 200 receipt](HISAT2-RS1-RUN01-20260902T043353Z.published.json)
and the [published Turtle](HISAT2-RS1-RUN01-20260902T043353Z.ttl) are included
for audit; the task-level metrics JSON remains on the workflow PVC.

## Required PVC evidence

For a run ID such as `HISAT2-RS1-RUN01`, the profile expects:

```text
/workspace/results/HISAT2-RS1-RUN01/trace-HISAT2-RS1-RUN01.txt
/workspace/results/HISAT2-RS1-RUN01/nextflow-HISAT2-RS1-RUN01.log
/workspace/results/HISAT2-RS1-RUN01/nextflow-debug-HISAT2-RS1-RUN01.log
/workspace/rnaseq-hisat2-rs1/source/          pinned workflow checkout
```

Archive `.nextflow.log` under the run-specific debug-log name immediately after
Nextflow exits. This prevents a later run from rotating or replacing the session
evidence.

## Configure credentials once

Review `publisher.env.example`, especially namespace, PVC, service account,
person URIs, and the credential Secret name. The tested FONDA deployment can use
the profile directly. Other deployments should copy and edit it.

Store an approved non-admin VIVO publisher account in the configured Secret:

```bash
CONFIG_FILE=examples/rnaseq-hisat2-rs1/publisher.env.example \
  ./scripts/configure-secrets.sh
```

The credential values are stored only in Kubernetes; they are never committed or
printed.

## Validate without publishing

```bash
CONFIG_FILE=examples/rnaseq-hisat2-rs1/publisher.env.example \
  ./scripts/publish-run.sh HISAT2-RS1-RUN01 --dry-run
```

This deploys the shared collector, reads the run evidence from `rnaseq-pvc`,
queries Prometheus/Kepler and the carbon source, creates TTL plus a metrics
audit, and validates the VIVO update without contacting VIVO.

## Collect and send automatically to VIVO

After the workflow and run-specific debug-log copy succeed, one command
collects, validates, and publishes the metadata:

```bash
CONFIG_FILE=examples/rnaseq-hisat2-rs1/publisher.env.example \
  ./scripts/publish-run.sh HISAT2-RS1-RUN01
```

`REQUIRE_SUCCEEDED=1` makes the collector refuse publication unless every trace
row is `COMPLETED`; cached, failed, aborted, warning-bearing, or active runs do
not pass. Successful publication writes a `.published.json` receipt beside the
TTL and prevents accidental duplicate publication for the same run ID.

## Input provenance

`input_datasets.json` records all three ENA accessions (SRR1509507, SRR14197369,
SRR14404397) and all three Ensembl release-106 files (genome FASTA, cDNA FASTA,
GTF) as separate upstream URLs. This is the same shared A2 Drosophila RS1 read
set and BDGP6.32 reference used by the sibling RNA-seq RS1 profiles, so the two
input-dataset individuals are reused by URI. `input-SHA256SUMS` contains the
hashes of the exact staged bytes on `rnaseq-pvc`.

## Notes on this run

- **CPU time is from Prometheus.** The run's first attempt filled the PVC during
  the largest sort; after freeing space the run was resumed to a clean 18/18
  completion. Because the earlier attempt's evidence files still occupied the
  results directory, the trace was regenerated from the completed session's
  Nextflow history (`nextflow log`). The regenerated trace carries `peak_rss`
  (used for memory) and every other field but omits `%cpu`, so CPU time is taken
  from Prometheus `container_cpu_usage_seconds_total` — the collector's primary
  CPU source in any case.
- **Carbon uses the Electricity Maps latest proxy** rather than the A2 family's
  usual `co2map` factor, because CO2Map preliminary data did not yet cover the
  2026-09-01 run interval at collection time. The RDF and audit label the value
  explicitly as a collection-time proxy. Re-publishing with `co2map` once the
  preliminary factor lands is possible with `FORCE_REPUBLISH=1`.
