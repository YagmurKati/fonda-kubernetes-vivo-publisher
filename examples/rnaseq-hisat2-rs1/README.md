# RNA-seq HISAT2 RS1

| Item | Value |
| --- | --- |
| Workflow | [`Nine-s/nextflow_RS1_hisat2_new`](https://github.com/Nine-s/nextflow_RS1_hisat2_new) |
| Source commit | [`6b7688c7cab3c0bdb39e0e228ceab2bac31e2caa`](https://github.com/Nine-s/nextflow_RS1_hisat2_new/commit/6b7688c7cab3c0bdb39e0e228ceab2bac31e2caa) |
| Kubernetes reproduction | [`YagmurKati/rnaseq-hisat2-rs1-reproduction`](https://github.com/YagmurKati/rnaseq-hisat2-rs1-reproduction) |
| Run ID | `HISAT2-RS1-RUN01` |
| Date | 2026-09-01 |
| Mode | `exon_splice_site` |
| Result | 18/18 tasks succeeded |
| Duration | 34,078 s |
| CPU | 72,348.757 CPU-s; Prometheus coverage 16/18 pods |
| Memory | 2.0284489 GB average; 14.8994 GB peak; trace coverage 18/18 tasks |
| Energy | 0.80436839 kWh; Kepler coverage 16/18 pods |
| Carbon estimate | 0.3410522 kg CO2e using 0.424 kg CO2e/kWh |
| VIVO record | [Open run](https://vivo-fonda.hu-berlin.de/vivo/individual?uri=http%3A%2F%2Fexample.org%2Fvivo-import%2Frun-metadata%2Frun%2Fyagmur-rna-seq-analysis-workflow-hisat2-rs1-c0ece5b9-63ab-41ac-a0f5-1980d02b79dc-2026-09-01t11-38-23-240000-00-00) |

Processes: CHECK_STRANDNESS, FASTP, EXTRACT_EXONS, EXTRACT_SPLICE_SITES,
HISAT2_INDEX_REFERENCE, HISAT2_ALIGN, SAMTOOLS, and CUFFLINKS.

The carbon factor is the latest Electricity Maps value available when the
metadata was collected, not a historical value for the run interval.

## Required files

```text
/workspace/results/HISAT2-RS1-RUN01/trace-HISAT2-RS1-RUN01.txt
/workspace/results/HISAT2-RS1-RUN01/nextflow-HISAT2-RS1-RUN01.log
/workspace/results/HISAT2-RS1-RUN01/nextflow-debug-HISAT2-RS1-RUN01.log
/workspace/rnaseq-hisat2-rs1/source/
```

- Keep the Kubernetes pod name in the trace `native_id` field.
- Archive `.nextflow.log` before the workflow driver exits.
- `INCLUDE_CACHED_ORIGIN_METRICS=1` includes retained metrics from origin pods
  after a resumed run.
- `REQUIRE_SUCCEEDED=0` accepts a terminal mix of `COMPLETED` and `CACHED` rows.

## Configure

Copy the profile and input metadata:

```bash
cp examples/rnaseq-hisat2-rs1/publisher.env.example config/publisher.env
cp examples/rnaseq-hisat2-rs1/input_datasets.json config/input_datasets.json
```

Edit `config/publisher.env` for the workflow namespace, PVC, evidence paths,
and VIVO links. Store the VIVO credentials once:

```bash
./scripts/configure-secrets.sh
```

## Validate

```bash
./scripts/publish-run.sh RUN_ID --dry-run
```

## Publish

```bash
./scripts/publish-run.sh RUN_ID
```

The Turtle, metrics audit, and publication receipt are written to
`/workspace/vivo-outbox`. `input-SHA256SUMS` contains the checksums for the
three paired-end ENA datasets and the Ensembl BDGP6.32 release-106 reference
files.
