# Adapting a Nextflow workflow

## Required trace

Nextflow must write a tab-separated trace to the shared PVC. This command is
sufficient with current Nextflow releases:

```bash
nextflow run main.nf \
  -with-trace "/workspace/results/trace-${RUN_ID}.txt" \
  2>&1 | tee "/workspace/results/nextflow-${RUN_ID}.log"
```

Confirm the header contains:

```text
task_id  hash  native_id  name  status  submit
```

`native_id` must contain the Kubernetes pod name so Prometheus and Kepler
measurements can be matched to each task. `exit`, `duration`, and `realtime`
are optional but recommended.

Nextflow also writes `.nextflow.log`; set `DEBUG_LOG_PATH` to its PVC path.

## Shared PVC layout

The publisher Job mounts `PVC_NAME` at `/workspace`. Therefore all configured
trace, log, code, and output paths must be visible under `/workspace` from a
new pod. Files that exist only in a finished pod's ephemeral filesystem cannot
be collected.

## Service account

Set `SERVICE_ACCOUNT` to an existing service account in the same namespace.
It must be allowed to run a Job and read the mounted PVC. Node read permission
is optional.

## Stable RDF identity

Use one stable `WORKFLOW_URI` for a workflow across runs. Use a different URI
when the workflow is scientifically or operationally distinct. Do not use the
run ID as the workflow URI.

Set `GIT_COMMIT` to the exact 40-character source commit when the code copied to
the PVC has no `.git` directory. `WORKFLOW_REPO_URL` plus this commit produces a
clickable source link in VIVO.

## Automatic invocation

Call the publisher only after the workflow command succeeds:

```bash
RUN_ID="experiment-2026-08-25-01"
./run-nextflow.sh "$RUN_ID" && \
  /path/to/fonda-kubernetes-vivo-publisher/scripts/publish-run.sh "$RUN_ID"
```

For resumed Nextflow runs, set this before publication so metrics from cached
origin pods are included when retained by Prometheus:

```bash
INCLUDE_CACHED_ORIGIN_METRICS=1 ./scripts/publish-run.sh "$RUN_ID"
```
