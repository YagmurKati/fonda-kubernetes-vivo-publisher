# Publish a workflow that is not listed

A workflow without a profile in this repository can still be published.
Publishing its first run creates its workflow page in VIVO: you do not need
the administrator to create the page, and you do not need a profile from this
repository.

Whether settings are enough depends on the cluster and on how the workflow is
run.

## What works today

| Cluster | The workflow is run with | A new workflow needs | Tested with |
| --- | --- | --- | --- |
| HPC@HU (Slurm) | Nextflow, inside one Slurm job | settings only | nf-core/rangeland |
| HPC@HU (Slurm) | anything else inside one Slurm job: Python program, shell script, Snakemake | settings only; the run is recorded without stages and without a workflow engine | the collector's tests |
| FONDA Kubernetes | Nextflow | settings only | the Nextflow profiles in the [README](../README.md#tested-workflow-profiles) |
| FONDA Kubernetes | Apache Airflow, every task a `KubernetesPodOperator` pod | command options only | the FORCE DAG |
| FONDA Kubernetes | Snakemake | new collector code | MG-3, MG-4, PopinSnake |
| FONDA Kubernetes | Python or Java program or shell script, run as Kubernetes Jobs | new collector code | event query discovery (Python), Lotaru (Java) |
| FONDA Kubernetes | Apache Spark | new collector code | one word-count run |
| Another cluster | anything | [Connect another cluster to FONDA VIVO](../examples/other-cluster/README.md) | |

Why some need new code: on Kubernetes the collector must know how to find the
pods of a run and which files prove that it finished. For Nextflow this is the
same for every workflow (the trace file). For Snakemake and for programs run as
Kubernetes Jobs it differs per workflow, so each tested one has its own part in
`collector/collect_snakemake_kubernetes_metadata.py`. The collector of the
Spark run is not in this repository.

On HPC@HU the values come from Slurm and from the node, not from the workflow,
so any command works as long as the whole workflow runs inside one Slurm job
on one node. Tasks that a workflow system submits as separate Slurm jobs are
not included.

## The address and the page of the workflow

`WORKFLOW_URI` is the address of the workflow in VIVO (Airflow: see
[below](#fonda-kubernetes-cluster-with-apache-airflow)).

- **New workflow:** choose
  `http://example.org/vivo-import/run-metadata/workflow/SHORT-NAME`, with
  small letters, digits and hyphens in `SHORT-NAME`. Use the same address for
  every run of this workflow and never the address of another workflow.
- **Workflow that is already in VIVO**, also one that somebody else
  published: open its page from
  [VIVO Workflows](https://vivo-fonda.hu-berlin.de/vivo/workflows) and take
  the part of the browser address after `uri=`, reading `%3A` as `:` and `%2F`
  as `/`. Your run is added to that page. Do not give the page a second
  title: on HPC@HU leave `WORKFLOW_LABEL` empty, on the FONDA Kubernetes
  cluster set `WORKFLOW_NAME` to exactly the title of the page.

What the first published run writes on a new workflow page:

| On the workflow page | HPC@HU setting | FONDA Kubernetes setting (Nextflow) |
| --- | --- | --- |
| Title | `WORKFLOW_LABEL` | `WORKFLOW_NAME` |
| Compute cluster, list of runs | automatic | automatic |
| Responsible researchers | `RESPONSIBLE_RESEARCHER_URIS` | `RESPONSIBLE_RESEARCHER_URIS` |
| Workflow engine | not written | `ENGINE_URI` |
| Purpose | not written | `WORKFLOW_DESCRIPTION` |
| Code link | not written (the run has it) | `CODE_URI` |
| Subproject | not written | `SUBPROJECT_URIS` |
| Application domain | not written | `APPLICATION_DOMAIN_URI` |
| Publication | not written | `PUBLICATION_URI` |

Fields that are not written, and later changes of the page, are made by the
VIVO administrator: send an e-mail to
[yagmur.kati@hu-berlin.de](mailto:yagmur.kati@hu-berlin.de).

## HPC@HU (Slurm)

One-time setup: [Connect HPC@HU to VIVO](../examples/hpc-at-hu-slurm/CONNECT_HPC_TO_VIVO.md).

1. In `~/.fonda-vivo/slurm.env` set at least:

   ```bash
   WORKFLOW_URI="http://example.org/vivo-import/run-metadata/workflow/SHORT-NAME"
   WORKFLOW_LABEL="Title of the workflow"
   RUN_LABEL="Title of the workflow"
   RUN_OPERATOR_URI="https://fonda.hu-berlin.de/?page_id=2066#REPLACE_ME"
   CODE_REPO_URL="https://github.com/OWNER/REPOSITORY"
   ```

   Without Nextflow also set `GIT_COMMIT` and leave `NEXTFLOW_LAUNCH_DIR` and
   `NEXTFLOW_TRACE_GLOB` empty. All settings:
   [Describe the workflow](../examples/hpc-at-hu-slurm/COLLECT_AND_PUBLISH.md#1-describe-the-workflow).
2. Start the workflow through the job file, with its command wrapped as in
   [`job.sbatch.example`](../examples/hpc-at-hu-slurm/job.sbatch.example).
   The energy is read while the job runs, so a job that was started without
   this cannot be published with energy afterwards.
3. Continue with steps 3 to 6 of
   [Collect and publish a run](../examples/hpc-at-hu-slurm/COLLECT_AND_PUBLISH.md#3-run-the-job).
4. After the first published run, set `WORKFLOW_LABEL=""`: the page exists now.

What a run without Nextflow contains: start, end, duration, status, CPU time,
peak memory, energy, the carbon estimate, node hardware, run by, code link
and commit. It
has no workflow engine, no stages, no task count and no container images;
these are read from the Nextflow log and trace.

## FONDA Kubernetes cluster with Nextflow

1. Copy the general settings:

   ```bash
   cp config/publisher.env.example config/publisher.env
   cp config/input_datasets.json.example config/input_datasets.json
   ```

   The files of a similar [tested profile](../README.md#tested-workflow-profiles)
   are a good start as well. They stay on your computer; nothing has to be
   added to this repository.
2. Replace every `REPLACE_ME` value: `NS`, `PVC_NAME`, `WORKFLOW_NAME`,
   `WORKFLOW_URI`, `WORKFLOW_REPO_URL`, `CODE_URI`, and the paths of the trace
   and log files. The run must write a Nextflow trace to the shared PVC:
   [Adapting a Nextflow workflow](ADAPT_NEXTFLOW.md).
3. Continue with
   [Automatic collection and publication](../README.md#automatic-collection-and-publication).

## FONDA Kubernetes cluster with Apache Airflow

Follow section 4 of the [FORCE on Airflow profile](../examples/force-airflow/README.md#4-collect-and-publish-a-run)
with your own `DAG_ID` and `RUN_ID`, and set `CODE_NAME` to the title of the
workflow. This collector has no `WORKFLOW_URI`: it uses `CODE_NAME` as the
title of the workflow page and makes the address from it
(`.../workflow/` followed by the title in small letters with hyphens). Use
the same `CODE_NAME` for every run of the workflow.

The collector reads the pods that the tasks created, so every task must be a
`KubernetesPodOperator` task.

## Everything else on the FONDA Kubernetes cluster

Snakemake, Python or Java programs, shell scripts and Spark need a part of
their own in the collector. Send an e-mail to
[yagmur.kati@hu-berlin.de](mailto:yagmur.kati@hu-berlin.de) with:

- the link to the code;
- how you start the workflow (the command or the Kubernetes manifest);
- the files it leaves on the shared PVC when it has finished (results, logs).
