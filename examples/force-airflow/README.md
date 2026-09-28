# FORCE on Apache Airflow

Profile for the FORCE remote-sensing workflow expressed as an Apache Airflow
DAG in
[`CRC-FONDA/fonda-airflow-dags`](https://github.com/CRC-FONDA/fonda-airflow-dags),
at `dags/s1/force/workflow.py`. Every task is a `KubernetesPodOperator` pod, so
a run's evidence is the Airflow task history together with the Kubernetes pods
those tasks created.

This is the same science as the [FORCE2NXF profile](../force2nxf/README.md) and
the [nf-core/rangeland profile](../rangeland-nfcore/README.md) under a different
workflow engine. Each engine has its own workflow record in VIVO, so the three
can be compared without overwriting one another.

A published example in FONDA VIVO is linked from the profile table in the
repository README.

## 1. Published record

The [workflow](https://vivo-fonda.hu-berlin.de/vivo/individual?uri=http%3A%2F%2Fexample.org%2Fvivo-import%2Frun-metadata%2Fworkflow%2Flong-term-vegetation-dynamics-in-the-mediterranean)
and its [run](https://vivo-fonda.hu-berlin.de/vivo/individual?uri=http%3A%2F%2Fexample.org%2Fvivo-import%2Frun-metadata%2Frun%2Fdefault-long-term-vegetation-dynamics-in-the-mediterranean-manual-2026-05-06t08-55-57-785616-00-00-2026-05-06t09-38-03-582823-00-00)
are already in VIVO. The record aggregates every task pod of one Airflow DAG
run into a single workflow run and links the publication that describes the
work.

Unlike the Nextflow and Snakemake profiles, this one is not a selectable engine
in `scripts/publish-run.sh`. Its evidence comes from the Airflow scheduler
rather than a trace file on a PVC, so it uses a dedicated collector:
[`collector/collect_airflow_kubernetes_metadata.py`](../../collector/collect_airflow_kubernetes_metadata.py),
with shared helpers in
[`collector/collect_public_metadata.py`](../../collector/collect_public_metadata.py).

## 2. Evidence the collector reads

The collector runs where `kubectl` can reach both the Airflow deployment and
the namespace the task pods ran in. For one DAG run it reads:

- the run record from `airflow dags list-runs`, executed inside the scheduler
  pod;
- per-task states from `airflow tasks states-for-dag-run`;
- each task's log under `/opt/airflow/logs/dag_id=.../run_id=.../task_id=...`;
- the Kubernetes pod objects the tasks created;
- Prometheus and Kepler series for CPU, memory, energy, and carbon.

Keep the Airflow metadata database, the task logs, and the task pods available
until collection finishes. Once Airflow rotates its logs or the pods are
cleaned up, the run can no longer be collected.

Before starting, install `git`, `python3`, and `kubectl`; connect `kubectl` to
the FONDA cluster; and obtain a non-admin VIVO publisher email and password
from the VIVO administrator. Prometheus must be reachable at the collector's
`--prom-url` (default: `http://localhost:9090`).

## 3. Start from the repository root

Complete [Step 1 in the main publishing guide](../../README.md#1-download-this-repository).
Run every command below from that repository root. The relevant files are:

- `collector/collect_airflow_kubernetes_metadata.py`
- `publisher/publish_vivo.py`
- `scripts/publish-local.sh`

Do not change into the `publisher` directory before using these paths.

## 4. Collect and publish a run

### 4.1 Set the run information

Replace every example value with the information for the completed run:

```bash
export AIRFLOW_NAMESPACE="airflow"
export TASK_POD_NAMESPACE="YOUR_NAMESPACE"
export DAG_ID="YOUR_DAG_ID"
export RUN_ID="YOUR_AIRFLOW_RUN_ID"
export CODE_NAME="workflow.py"
export CODE_PATH="/absolute/path/to/your/workflow.py"
export OUTPUT_TTL="$PWD/force-airflow-${RUN_ID}-$(date -u +%Y%m%dT%H%M%SZ).ttl"
```

`CODE_PATH` is the path to the workflow code on the computer where the
collector runs. `TASK_POD_NAMESPACE` is the Kubernetes namespace where the
Airflow task pods ran.

### 4.2 Collect the metadata and optional carbon information

```bash
python3 collector/collect_airflow_kubernetes_metadata.py \
  --airflow-namespace "$AIRFLOW_NAMESPACE" \
  --namespace "$TASK_POD_NAMESPACE" \
  --dag-id "$DAG_ID" \
  --run-id "$RUN_ID" \
  --code-name "$CODE_NAME" \
  --code-path "$CODE_PATH" \
  --output-file "$OUTPUT_TTL"
```

The collector automatically looks for the Kubernetes Secret
`electricity-maps-api-token` in `TASK_POD_NAMESPACE`. It never prints or saves
the token. When the token provides usable data, the collector writes the
carbon intensity and calculated carbon emissions into the TTL.

If the Secret is absent, unreadable, or the API returns no usable value,
collection still succeeds. In that case the TTL omits carbon intensity,
carbon-emission, and carbon-calculation properties; all other available run
metadata is kept. No invented fallback carbon value is published.

The collector first requests an average for the execution interval. If the
account cannot access historical data, it requests the latest available value
as a collection-time proxy.

Confirm the unique, timestamped TTL was created:

```bash
ls -lh "$OUTPUT_TTL"
```

`--run-id` may be omitted to select the newest run for the DAG.
`python3 collector/collect_airflow_kubernetes_metadata.py --help` lists the
remaining options.

### 4.3 Validate and publish

Continue with [Steps 3–5 in the main publishing guide](../../README.md#3-validate-the-ttl).
Those steps validate this TTL, publish it with the generic
`scripts/publish-local.sh` wrapper, and show where to check the VIVO record.

## 5. Remove a publication

The generic `./scripts/remove-run.sh PUBLICATION_ID --dry-run` and
`./scripts/remove-run.sh PUBLICATION_ID` commands expect a receipt in the
publisher outbox on a mounted PVC. This profile writes its Turtle locally
instead, so a removal needs the exact Turtle that was accepted. Keep it beside
the run's other evidence, and do not remove a published record without
deliberate authorization.

## Running the DAGs

`CRC-FONDA/fonda-airflow-dags` ships a local development environment under
`kind/` that deploys Airflow into a Kubernetes-in-Docker cluster on your own
machine. Prefer it for DAG development: it touches no shared infrastructure.

Before running any DAG of that repository on a shared cluster, check two
things in the DAG file. The benchmark DAGs under `dags/s1/benchmark_workflow/`
carry a `nodeAffinity` that pins them to another group's nodes, and the DAGs
set `namespace = "default"`. Both must be changed to your own namespace and to
nodes you are entitled to use.
