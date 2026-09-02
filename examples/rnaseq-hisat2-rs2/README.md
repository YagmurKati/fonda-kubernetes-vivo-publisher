# RNA-seq HISAT2 RS2

Publisher profile for
[`Nine-s/nextflow_RS2_hisat2`](https://github.com/Nine-s/nextflow_RS2_hisat2).
See the [published example in FONDA VIVO](https://vivo-fonda.hu-berlin.de/vivo/individual?uri=http%3A%2F%2Fexample.org%2Fvivo-import%2Frun-metadata%2Frun%2Fyagmur-rna-seq-analysis-workflow-hisat2-rs2-c1dacdb1-7d0f-4c61-9fac-941acded044b-2026-08-29t10-07-47-138000-00-00).

## 1. Configure

```bash
cp examples/rnaseq-hisat2-rs2/publisher.env.example config/publisher.env
cp examples/rnaseq-hisat2-rs2/input_datasets.json config/input_datasets.json
```

Edit `config/publisher.env`:

- set the namespace, PVC, service account, code path, and run operator URI;
- confirm the trace and log paths;
- set `GIT_COMMIT` to the workflow revision used for the run;
- update the input metadata if different datasets were used.

Store the VIVO credentials and deploy:

```bash
./scripts/configure-secrets.sh
./scripts/deploy.sh
```

## 2. Keep the run evidence

The default paths are:

```text
/workspace/results/RUN_ID/trace-RUN_ID.txt
/workspace/results/RUN_ID/nextflow-RUN_ID.log
/workspace/results/RUN_ID/nextflow-debug-RUN_ID.log
/workspace/rnaseq-hisat2-rs2/source/
```

The trace must keep the Kubernetes pod name in `native_id`. Collect metadata
soon after the run, before Prometheus and Kepler data expire.

For a fresh run, keep `INCLUDE_CACHED_ORIGIN_METRICS=0`. Set it to `1` only
after a Nextflow resume, while metrics from the original pods are still
available.

## 3. Validate

```bash
./scripts/publish-run.sh RUN_ID --dry-run
```

Open the generated `*.metrics.json` and confirm:

- `summary.energy_pod_count` equals `pod_count`;
- `summary.energy_estimated` is `false`.

If either check fails, the energy value is incomplete or estimated and should
not be reported as the measured energy of the whole workflow.

## 4. Publish

```bash
./scripts/publish-run.sh RUN_ID
```

The Turtle, metrics audit, and publication receipt are written to
`/workspace/vivo-outbox`. Open the [FONDA VIVO Runs page](https://vivo-fonda.hu-berlin.de/vivo/runs)
to verify the new record.
