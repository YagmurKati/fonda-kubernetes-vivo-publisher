# FONDA workflow-run publisher for VIVO

Publishes the metadata of finished workflow runs to
[FONDA VIVO](https://vivo-fonda.hu-berlin.de/vivo/runs).

## Start here

| Your cluster | Guide |
| --- | --- |
| FONDA Kubernetes cluster | this page |
| HPC@HU (Slurm) | [HPC@HU guides](examples/hpc-at-hu-slurm/README.md) |
| Any other cluster | [Connect another cluster to FONDA VIVO](examples/other-cluster/README.md) |

FONDA members without a VIVO account: send an e-mail to
[yagmur.kati@hu-berlin.de](mailto:yagmur.kati@hu-berlin.de).

## What is published

For each run:

- workflow, code version, containers, tasks, status and duration;
- CPU time, average and peak memory, energy;
- a carbon estimate, labelled as an estimate;
- links to the workflow, researcher, subproject, input data and
  infrastructure.

On the FONDA Kubernetes cluster, CPU time and memory come from the complete
Nextflow trace when it has the `%cpu` and `peak_rss` fields (Prometheus is
kept for comparison), and energy comes from Kepler through Prometheus.

The collector writes three files to the workflow PVC: the run as Turtle
(`.ttl`), a metrics audit and a publication receipt. Only the Turtle file is
sent to VIVO.

## What you need on the FONDA Kubernetes cluster

1. access to your FONDA Kubernetes namespace;
2. a finished run of a [tested workflow](#tested-workflow-profiles), with its
   evidence on a shared PVC;
3. a VIVO account that may publish runs. The VIVO administrator gives this
   right: same e-mail address as above;
4. optional: an Electricity Maps token, for the carbon estimate;
5. optional: a HU-Box account, to keep selected raw traces.

## Publish a workflow run on the FONDA Kubernetes cluster

### 1. Download this repository

```bash
git clone https://github.com/YagmurKati/fonda-kubernetes-vivo-publisher.git
cd fonda-kubernetes-vivo-publisher
```

Run the remaining commands from this directory.

### 2. Create the TTL file

Find your workflow in [Tested workflow profiles](#tested-workflow-profiles)
and open its **Profile** link.

- The profile uses `scripts/publish-run.sh`: go to
  [Automatic collection and publication](#automatic-collection-and-publication).
- The profile creates a local `.ttl` file: run every collection command of
  that profile, including `export OUTPUT_TTL=...`. Stay in the same terminal
  and continue with step 3.

Carbon information is optional. A collector adds it when an Electricity Maps
token is available. A TTL without it can still be validated and published.

Confirm the path of the file:

```bash
printf 'TTL file: %s\n' "$OUTPUT_TTL"
ls -lh "$OUTPUT_TTL"
```

The second command must show the TTL file. Leave the file where it is:
`publish-local.sh` takes the full path.

### 3. Validate the TTL

```bash
./scripts/publish-local.sh "$OUTPUT_TTL" --dry-run
```

This does not contact VIVO.

### 4. Publish to VIVO

```bash
./scripts/publish-local.sh "$OUTPUT_TTL"
```

Enter your VIVO e-mail and password. The password is hidden and is not saved.

### 5. Check the result

Success is reported as `HTTP 200`. Open the
[VIVO Runs page](https://vivo-fonda.hu-berlin.de/vivo/runs) and check the new
record. Keep the TTL and the `.published.json` receipt created beside it.

### 6. Publish the trace archive to HU-Box (optional)

For a Nextflow profile whose trace files are still on the shared PVC, replace
`RUN_ID`:

```bash
./scripts/configure-hu-box.sh
./scripts/archive-publish-run.sh RUN_ID --package-only
./scripts/archive-publish-run.sh RUN_ID
```

The first command is needed once per computer. Review the bundle made by
`--package-only` before the last command, which uploads the archive and adds
its public link to the run's VIVO page. Setup, privacy checks and error
recovery: [HU-Box trace archive guide](docs/HU_BOX_TRACE_ARCHIVE.md).

## Automatic collection and publication

Only for profiles of the FONDA Kubernetes cluster that use
`scripts/publish-run.sh`.

Copy the two files of your profile, as step 1 of its guide shows. For example,
Geoflow:

```bash
cp examples/geoflow/publisher.env.example config/publisher.env
cp examples/geoflow/input_datasets.json config/input_datasets.json
```

Edit the copied settings file and replace every `REPLACE_ME` value. At least
confirm:

- `NS`, `PVC_NAME`;
- `WORKFLOW_NAME`, `WORKFLOW_URI`;
- `WORKFLOW_REPO_URL`, `CODE_URI`;
- the evidence paths and selectors named in the profile.

Store your VIVO login (hidden prompts):

```bash
./scripts/configure-secrets.sh
```

Deploy the code and settings into your namespace:

```bash
./scripts/deploy.sh
```

After run `my-run-01` has finished successfully, test without contacting
VIVO:

```bash
./scripts/publish-run.sh my-run-01 --dry-run
```

Then collect the metadata and send it to VIVO:

```bash
./scripts/publish-run.sh my-run-01
```

**Node hardware.** It is read from the Kubernetes API. If your namespace may
not read Node objects, the collector uses the `kube_node_info` and
`kube_node_status_allocatable` metrics in Prometheus instead. If required
fields are still missing, the script lists them and asks you to type
`PUBLISH` before it sends the incomplete record. For a reviewed run without
this question, set `ALLOW_INCOMPLETE_NODE_METADATA=1`.

**Publishing again.** The same run ID is refused a second time unless
`FORCE_REPUBLISH=1` is set. Then the run is collected again and replaces its
record in VIVO (the run, its date node and its workflow processes), so values
that change between collections, such as the live carbon intensity, are not
listed twice.

**Resumed Nextflow run.** To include the metrics of the original pods of
cached tasks, while they are still kept:

```bash
INCLUDE_CACHED_ORIGIN_METRICS=1 ./scripts/publish-run.sh my-run-01-resume
```

**Right after the workflow.** Publication starts only when the workflow
command succeeds:

```bash
RUN_ID="my-run-01"
./your-existing-workflow-command "$RUN_ID" && \
  ./scripts/publish-run.sh "$RUN_ID"
```

If VIVO is not reachable, run only `publish-run.sh` again, not the workflow.

## Tested workflow profiles

All profiles are for the FONDA Kubernetes cluster. The collector and publisher
code is shared. Each workflow has its own profile because its engine, evidence
paths, source repository, input data and VIVO links differ.

| Workflow | Workflow engine | Published example | Profile |
| --- | --- | --- | --- |
| Geoflow annual land-cover mapping | Nextflow | [Open in VIVO](https://vivo-fonda.hu-berlin.de/vivo/individual?uri=http%3A%2F%2Fexample.org%2Fvivo-import%2Frun-metadata%2Frun%2Fyagmur-geoflow-annual-land-cover-mapping-across-germany-b65ef87a-3b53-4ea0-9d31-fcd67c75a7e3-2026-08-25t14-11-24-351000-00-00) | [Geoflow profile](examples/geoflow/README.md) |
| FORCE2NXF rangeland workflow | Nextflow | [Open in VIVO](https://vivo-fonda.hu-berlin.de/vivo/individual?uri=http%3A%2F%2Fexample.org%2Fvivo-import%2Frun-metadata%2Frun%2Fdefault-long-term-vegetation-dynamics-in-the-mediterranean-force2nxf-e5295c77-62e8-4773-afc5-706750fb1a33-2026-08-25t18-25-43-637000-00-00) | [FORCE2NXF profile](examples/force2nxf/README.md) |
| nf-core/rangeland Mediterranean vegetation dynamics | Nextflow | [Open in VIVO](https://vivo-fonda.hu-berlin.de/vivo/individual?uri=http%3A%2F%2Fexample.org%2Fvivo-import%2Frun-metadata%2Frun%2Fyagmur-long-term-vegetation-dynamics-in-the-mediterranean-nf-core-efd0ee83-ae64-451e-ad2a-efd52b206ad7-2026-09-07t21-42-29-001000-00-00) | [nf-core/rangeland profile](examples/rangeland-nfcore/README.md) |
| Synthetic echo workflow for cluster execution testing | Nextflow | [Open in VIVO](https://vivo-fonda.hu-berlin.de/vivo/individual?uri=http%3A%2F%2Fexample.org%2Fvivo-import%2Frun-metadata%2Frun%2Fyagmur-synthetic-echo-workflow-for-cluster-execution-testing-34a93e41-cd57-4edc-ad3e-d2b47cb78f71-2026-09-08t06-31-54-892000-00-00) | [docker-nextflow-node profile](examples/nextflow-node-echo/README.md) |
| FONDA Spark filesystem word count | Apache Spark | [Open in VIVO](https://vivo-fonda.hu-berlin.de/vivo/individual?uri=http%3A%2F%2Fexample.org%2Fvivo-import%2Frun-metadata%2Frun%2Fspark-wordcount-fs-20260914-01-spark-3bc712cac1f64dc894ea7c4fa5184ff9) | [Spark word-count profile](examples/spark-wordcount-fs/README.md) |
| Trends in European Grasslands (test-site study) | Nextflow | [Open in VIVO](https://vivo-fonda.hu-berlin.de/vivo/individual?uri=http%3A%2F%2Fexample.org%2Fvivo-import%2Frun-metadata%2Frun%2Fyagmur-trends-in-european-grasslands-test-site-study-2e7a5fcb-44d1-44ea-b3ad-79d2bdab52d8-2026-09-02t20-24-23-057000-00-00) | [FONDA_trends profile](examples/fonda-trends/README.md) |
| RNA-seq analysis (Salmon, RS1) | Nextflow | [Open in VIVO](https://vivo-fonda.hu-berlin.de/vivo/individual?uri=http%3A%2F%2Fexample.org%2Fvivo-import%2Frun-metadata%2Frun%2Fyagmur-rna-seq-analysis-workflow-salmon-rs1-9347febf-9033-4c8f-8eb2-f699de6b3479-2026-08-28t18-35-04-684000-00-00) | [RNA-seq Salmon RS1 profile](examples/rnaseq-salmon-rs1/README.md) |
| RNA-seq analysis (Salmon, RS1, ninon experiment configs) | Nextflow | [Open in VIVO](https://vivo-fonda.hu-berlin.de/vivo/individual?uri=http%3A%2F%2Fexample.org%2Fvivo-import%2Frun-metadata%2Frun%2Fyagmur-rna-seq-analysis-workflow-salmon-rs1-889cb6b3-521c-4c5f-9a26-472f77d5ac6a-2026-09-08t17-14-14-359000-00-00) | [RNA-seq Salmon RS1 ninon profile](examples/rnaseq-salmon-rs1-ninon/README.md) |
| RNA-seq analysis (Salmon, RS2) | Nextflow | [Open in VIVO](https://vivo-fonda.hu-berlin.de/vivo/individual?uri=http%3A%2F%2Fexample.org%2Fvivo-import%2Frun-metadata%2Frun%2Fyagmur-rna-seq-analysis-workflow-salmon-rs2-e007ad6a-80b7-4133-ac2d-f9c3e4e625e8-2026-09-07t20-29-52-808000-00-00) | [RNA-seq Salmon RS2 profile](examples/rnaseq-salmon-rs2/README.md) |
| RNA-seq analysis (STAR, RS1) | Nextflow | [Open in VIVO](https://vivo-fonda.hu-berlin.de/vivo/individual?uri=http%3A%2F%2Fexample.org%2Fvivo-import%2Frun-metadata%2Frun%2Fyagmur-rna-seq-analysis-workflow-star-rs1-3afdb2f4-9abc-4fbc-86f2-c66e81b672ed-2026-08-31t07-25-43-891000-00-00) | [RNA-seq STAR RS1 profile](examples/rnaseq-star-rs1/README.md) |
| RNA-seq analysis (STAR, RS2) | Nextflow | [Open in VIVO](https://vivo-fonda.hu-berlin.de/vivo/individual?uri=http%3A%2F%2Fexample.org%2Fvivo-import%2Frun-metadata%2Frun%2Fyagmur-rna-seq-analysis-workflow-star-rs2-5ff9e53d-bfa2-4fd8-88b2-c65ce9e371ac-2026-09-03t04-13-05-116000-00-00) | [RNA-seq STAR RS2 profile](examples/rnaseq-star-rs2/README.md) |
| RNA-seq analysis (HISAT2, RS1) | Nextflow | [Open in VIVO](https://vivo-fonda.hu-berlin.de/vivo/individual?uri=http%3A%2F%2Fexample.org%2Fvivo-import%2Frun-metadata%2Frun%2Fyagmur-rna-seq-analysis-workflow-hisat2-rs1-c0ece5b9-63ab-41ac-a0f5-1980d02b79dc-2026-09-01t11-38-23-240000-00-00) | [RNA-seq HISAT2 RS1 profile](examples/rnaseq-hisat2-rs1/README.md) |
| RNA-seq analysis (HISAT2, RS2) | Nextflow | [Open in VIVO](https://vivo-fonda.hu-berlin.de/vivo/individual?uri=http%3A%2F%2Fexample.org%2Fvivo-import%2Frun-metadata%2Frun%2Fyagmur-rna-seq-analysis-workflow-hisat2-rs2-c1dacdb1-7d0f-4c61-9fac-941acded044b-2026-08-29t10-07-47-138000-00-00) | [RNA-seq HISAT2 RS2 profile](examples/rnaseq-hisat2-rs2/README.md) |
| A2 MG-3 metagenomic read mapping | Snakemake | [Open in VIVO](https://vivo-fonda.hu-berlin.de/vivo/individual?uri=http%3A%2F%2Fexample.org%2Fvivo-import%2Frun-metadata%2Frun%2Fyagmur-metagenomic-read-mapping-across-computational-architectures-a2-mg3-20260908-2026-09-08t06-34-48-00-00) | [A2 MG-3 profile](examples/a2-mg3/README.md) |
| A2 MG-4 metagenomic read mapping | Snakemake | [Open in VIVO](https://vivo-fonda.hu-berlin.de/vivo/individual?uri=http%3A%2F%2Fexample.org%2Fvivo-import%2Frun-metadata%2Frun%2Fyagmur-metagenomic-read-mapping-with-customizable-job-granularity-a2-mg4-smoke-20260826-2026-08-26t11-10-52-00-00) | [A2 MG-4 profile](examples/a2-mg4/README.md) |
| PopinSnake genomic insertion detection | Snakemake | [Open in VIVO](https://vivo-fonda.hu-berlin.de/vivo/individual?uri=http%3A%2F%2Fexample.org%2Fvivo-import%2Frun-metadata%2Frun%2Fyagmur-popinsnake-exploratory-workflow-for-genomic-insertion-detection-popinsnake-example-20260828-02-2026-08-28t08-03-05-00-00) | [PopinSnake profile](examples/popinsnake/README.md) |
| RNA-seq with RAPL CPU energy measurement (SRR16287545) | Nextflow + RAPL | [Open in VIVO](https://vivo-fonda.hu-berlin.de/vivo/individual?uri=http%3A%2F%2Fexample.org%2Fvivo-import%2Frun-metadata%2Frun%2Ffonda-rnaseq-rapl-srr16287545-20260922-074112) | [RNA-seq/RAPL run, collect and publish guide](examples/rnaseq-rapl/README.md) |
| Event query discovery from Google cluster traces | Python (Kubernetes Jobs) | [Open in VIVO](https://vivo-fonda.hu-berlin.de/vivo/individual?uri=http%3A%2F%2Fexample.org%2Fvivo-import%2Frun-metadata%2Frun%2Fyagmur-event-query-discovery-from-google-cluster-traces-btw23-20260915-2026-09-14t21-17-54-00-00) | [Event query discovery profile](examples/event-query-discovery/README.md) |
| Lotaru runtime prediction for scientific workflow tasks | Java (Kubernetes Job) | [Open in VIVO](https://vivo-fonda.hu-berlin.de/vivo/individual?uri=http%3A%2F%2Fexample.org%2Fvivo-import%2Frun-metadata%2Frun%2Fyagmur-lotaru-local-runtime-prediction-for-scientific-workflow-tasks-lotaru-2b07b18-20260920-2026-09-20t12-36-28-00-00) | [Lotaru profile](examples/lotaru/README.md) |
| Long-term vegetation dynamics in the Mediterranean (Airflow) | Apache Airflow | [Open in VIVO](https://vivo-fonda.hu-berlin.de/vivo/individual?uri=http%3A%2F%2Fexample.org%2Fvivo-import%2Frun-metadata%2Frun%2Fdefault-long-term-vegetation-dynamics-in-the-mediterranean-manual-2026-05-06t08-55-57-785616-00-00-2026-05-06t09-38-03-582823-00-00) | [FORCE on Airflow profile](examples/force-airflow/README.md) |

Nextflow profiles: task tags such as tile or sample identifiers are grouped
under the process name. This keeps large RDF files compact; the metrics audit
keeps the values of every task.

A workflow that is not listed needs its own profile, and another workflow
engine needs its own collector. Both reuse the RDF model and
`publisher/publish_vivo.py`. See
[Adapting a Nextflow workflow](docs/ADAPT_NEXTFLOW.md).

## Engine-specific execution evidence

### Nextflow

For one `RUN_ID`, the default configuration expects:

```text
/workspace/results/trace-RUN_ID.txt
/workspace/results/nextflow-RUN_ID.log
/workspace/workflow/.nextflow.log
/workspace/workflow/                  workflow source
```

The trace must include `task_id`, `hash`, `native_id`, `name`, `status`, and
`submit`. See [Adapting a Nextflow workflow](docs/ADAPT_NEXTFLOW.md).

### Snakemake

The collector finds the finished pods of the workflow through the read-only
Kubernetes API and then checks the evidence of the profile:

- [MG-3](examples/a2-mg3/README.md): checksum and count of the final SAM;
- [MG-4](examples/a2-mg4/README.md): run marker, provenance, checksum and
  final SAM;
- [PopinSnake](examples/popinsnake/README.md): `RUN_STATUS`, provenance,
  checksums and the final compressed VCF.

### Apache Spark and Apache Airflow

Each has its own collector and is not an engine of `publish-run.sh`. Follow
the profile:

- [Spark filesystem word count](examples/spark-wordcount-fs/README.md): reads
  the Spark event log and the Prometheus and Kepler measurements of a finished
  Spark-on-Kubernetes run.
- [FORCE on Airflow](examples/force-airflow/README.md): reads the run and task
  history from the Airflow scheduler, the task logs and the pods of the
  `KubernetesPodOperator` tasks.

## Output and verification

For the Nextflow profiles, a successful command prints paths like:

```text
/workspace/vivo-outbox/my-run-01-20260825T144622Z.ttl
/workspace/vivo-outbox/my-run-01-20260825T144622Z.metrics.json
/workspace/vivo-outbox/my-run-01-20260825T144622Z.published.json
```

The Snakemake profiles write the same three files under
`RUN_ROOT/vivo-outbox`.

It also prints `HTTP 200`. Then open the
[VIVO Runs page](https://vivo-fonda.hu-berlin.de/vivo/runs); its list takes a
few seconds to load.

To remove a published run, use the publication ID from the receipt filename:

```bash
./scripts/remove-run.sh my-run-01-20260825T144622Z --dry-run
./scripts/remove-run.sh my-run-01-20260825T144622Z
```

The second command asks for confirmation and uses your VIVO account. It
removes only that run's metadata from VIVO and keeps the local workflow and
audit files. See [Remove a published run](docs/USER_GUIDE.md#8-remove-a-published-run).

## Documentation

- [User guide](docs/USER_GUIDE.md)
- [Administrator onboarding](docs/ADMIN_SETUP.md)
- [Adapting a Nextflow workflow](docs/ADAPT_NEXTFLOW.md)
- [Node use of a run: exclusive or non-exclusive](docs/NODE_USE.md)
- [HU-Box trace archive](docs/HU_BOX_TRACE_ARCHIVE.md)
- [HPC@HU (Slurm)](examples/hpc-at-hu-slurm/README.md)
- [Connect another cluster to FONDA VIVO](examples/other-cluster/README.md)
- [Security](SECURITY.md)

## License

[MIT](LICENSE)
