# docker-nextflow-node echo workflow

Profile for the `test.nf` echo workflow from
[`rafaelmoczalla/docker-nextflow-node`](https://github.com/rafaelmoczalla/docker-nextflow-node),
executed on Kubernetes. See a
[published example in FONDA VIVO](https://vivo-fonda.hu-berlin.de/vivo/individual?uri=http%3A%2F%2Fexample.org%2Fvivo-import%2Frun-metadata%2Frun%2Fyagmur-synthetic-echo-workflow-for-cluster-execution-testing-34a93e41-cd57-4edc-ad3e-d2b47cb78f71-2026-09-08t06-31-54-892000-00-00).

The upstream project runs this workflow on a local Apache Ignite cluster built
from Docker containers. The Ignite executor was removed from Nextflow after the
22.x line, so the tested path here is the Kubernetes executor.

The workflow identity is deliberately executor-neutral. Engine, repository and
executor are already recorded as `rm:workflowEngine`, `rm:workflowCodeLink` and
`rm:backend`, and the executor is a property of a run rather than of the
workflow, so an Ignite run of the same `test.nf` belongs under this same
`WORKFLOW_URI` and is told apart by its backend.

## 1. Configure

```bash
cp examples/nextflow-node-echo/publisher.env.example config/publisher.env
cp examples/nextflow-node-echo/input_datasets.json config/input_datasets.json
```

Replace every `REPLACE_ME` value and confirm the trace, log, and code paths.
`WORKFLOW_DESCRIPTION` supplies the purpose shown on the workflow individual
in VIVO; it describes the workflow rather than any single run.
Store the VIVO credentials:

```bash
./scripts/configure-secrets.sh
```

`input_datasets.json` carries an empty `datasets` list on purpose: `test.nf`
generates its own values with `Channel.from(1..100)` and reads no input data.

## 2. Keep the run evidence

The profile expects:

```text
/workspace/results/RUN_ID/trace-RUN_ID.txt
/workspace/results/RUN_ID/nextflow-RUN_ID.log
/workspace/results/RUN_ID/nextflow-debug-RUN_ID.log
/workspace/source
```

Clone the upstream repository to `/workspace/source` so `CODE_PATH` resolves.
Keep the Kubernetes Pod name in the trace `native_id` field.

`test.nf` declares no container, which is fine under Ignite because tasks run
inside the node containers. The Kubernetes executor needs an image per task, so
set `process.container`. It must provide `bash`: the upstream `Dockerfile`
installs `bash` on top of Alpine for exactly this reason, and Nextflow's task
wrapper will not run without it.

## 3. Validate

```bash
./scripts/publish-run.sh RUN_ID --dry-run
```

## 4. Publish

```bash
./scripts/publish-run.sh RUN_ID
```

Open the [FONDA VIVO Runs page](https://vivo-fonda.hu-berlin.de/vivo/runs) and
check the new record. The TTL, metrics audit, and receipt are written to
`/workspace/vivo-outbox`.

## 5. Remove a publication

Use the publication ID from the `.published.json` filename:

```bash
./scripts/remove-run.sh PUBLICATION_ID --dry-run
./scripts/remove-run.sh PUBLICATION_ID
```

The second command asks for confirmation and removes only that published run's
metadata from VIVO.

## Notes

`test.nf` is DSL1 and the upstream `Dockerfile` pins `NXF_VER 20.10.0`. Run it
with that Nextflow version; current releases support neither DSL1 nor the
Ignite executor.

No application domain is set. The workflow is a synthetic echo benchmark rather
than a domain science pipeline, and the field is optional.
