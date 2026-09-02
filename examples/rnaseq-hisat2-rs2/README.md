# RNA-seq HISAT2 RS2

| Item | Value |
| --- | --- |
| Workflow | [`Nine-s/nextflow_RS2_hisat2`](https://github.com/Nine-s/nextflow_RS2_hisat2) |
| Source commit | [`68b9e62cd614cb901a45e9df8898203384e043ac`](https://github.com/Nine-s/nextflow_RS2_hisat2/commit/68b9e62cd614cb901a45e9df8898203384e043ac) |
| Run ID | `HISAT2-RS2-RUN06` |
| Date | 2026-08-29 |
| Result | 302/302 tasks succeeded; 301 cached and 1 completed |
| Duration | 37,207 s |
| CPU | 94,439.6727 CPU-s |
| Memory | 3.27696 GB average; 17.9244 GB peak |
| Energy | 1.000163 kWh; direct Kepler coverage for 245 pods |
| Carbon estimate | 0.098016 kg direct CO2 using 0.098 kg/kWh |

Tasks: 3 strandness checks, 3 FASTP tasks, 2 annotation helpers, 1 HISAT2
index, 3 FASTQ splits, 143 HISAT2 alignments, 143 Samtools conversions, 1
merged BAM, and 3 Cufflinks tasks. The merged BAM is 23,777,553,300 bytes.

The carbon factor is preliminary CO2Map DE data, not a finalized historical
value. Energy without direct Kepler coverage is marked as estimated.

## Required files

```text
/workspace/results/HISAT2-RS2-RUN06/trace-HISAT2-RS2-RUN06.txt
/workspace/results/HISAT2-RS2-RUN06/nextflow-HISAT2-RS2-RUN06.log
/workspace/results/HISAT2-RS2-RUN06/nextflow-debug-HISAT2-RS2-RUN06-combined.log
/workspace/rnaseq-hisat2-rs2/source/
```

- Keep the Kubernetes pod name in the trace `native_id` field.
- Combine the origin and resume debug logs without changing either original.
- `INCLUDE_CACHED_ORIGIN_METRICS=1` includes retained metrics from origin pods.
- `REQUIRE_SUCCEEDED=0` accepts a terminal mix of `COMPLETED` and `CACHED` rows.

## Configure

```bash
cp examples/rnaseq-hisat2-rs2/publisher.env.example config/publisher.env
cp examples/rnaseq-hisat2-rs2/input_datasets.json config/input_datasets.json
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
