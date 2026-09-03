# FONDA Kubernetes workflow-run publisher for VIVO

Publish metadata from supported workflow runs on the FONDA Kubernetes cluster
directly to [FONDA VIVO](https://vivo-fonda.hu-berlin.de/vivo/runs). Tested
adapters are included for Nextflow and tested Snakemake/Kubernetes
reproductions.

The toolkit collects:

- workflow identity, source revision, declared digest-pinned and
  Kubernetes-discovered containers, tasks, status, and duration;
- CPU time and average/peak memory from the complete Nextflow trace when its
  `%cpu` and `peak_rss` fields are present, with Prometheus retained for an
  independent comparison, plus Kepler energy from Prometheus;
- a clearly labelled carbon estimate;
- workflow, researcher, subproject, input, infrastructure, and provenance links.

It writes a timestamped Turtle file, a metrics audit, and a VIVO publication
receipt to the workflow PVC. Only the Turtle RDF is sent to VIVO.

## Who can use it?

You do **not** need to be a VIVO administrator. You need:

1. access to your FONDA Kubernetes namespace;
2. a completed supported workflow run whose evidence is on a shared PVC;
3. a personal or team **non-admin VIVO publisher account** provisioned by the
   VIVO administrator;
4. optionally, an Electricity Maps token for a latest-available carbon proxy.

Do not use or share the VIVO administrator account. See
[Administrator onboarding](docs/ADMIN_SETUP.md).

## Tested workflow profiles

The collector and publisher code is shared. Each workflow has a separate
configuration profile because its workflow engine, execution-evidence paths,
source repository, input data, and VIVO links differ.

| Workflow | Workflow engine | Published example | Profile |
| --- | --- | --- | --- |
| Geoflow annual land-cover mapping | Nextflow | [Open in VIVO](https://vivo-fonda.hu-berlin.de/vivo/individual?uri=http%3A%2F%2Fexample.org%2Fvivo-import%2Frun-metadata%2Frun%2Fyagmur-geoflow-annual-land-cover-mapping-across-germany-b65ef87a-3b53-4ea0-9d31-fcd67c75a7e3-2026-08-25t14-11-24-351000-00-00) | [Geoflow profile](examples/geoflow/README.md) |
| FORCE2NXF rangeland workflow | Nextflow | [Open in VIVO](https://vivo-fonda.hu-berlin.de/vivo/individual?uri=http%3A%2F%2Fexample.org%2Fvivo-import%2Frun-metadata%2Frun%2Fdefault-long-term-vegetation-dynamics-in-the-mediterranean-force2nxf-e5295c77-62e8-4773-afc5-706750fb1a33-2026-08-25t18-25-43-637000-00-00) | [FORCE2NXF profile](examples/force2nxf/README.md) |
| Trends in European Grasslands (test-site study) | Nextflow | [Open in VIVO](https://vivo-fonda.hu-berlin.de/vivo/individual?uri=http%3A%2F%2Fexample.org%2Fvivo-import%2Frun-metadata%2Frun%2Fyagmur-trends-in-european-grasslands-test-site-study-2e7a5fcb-44d1-44ea-b3ad-79d2bdab52d8-2026-09-02t20-24-23-057000-00-00) | [FONDA_trends profile](examples/fonda-trends/README.md) |
| RNA-seq analysis (Salmon, RS1) | Nextflow | [Open in VIVO](https://vivo-fonda.hu-berlin.de/vivo/individual?uri=http%3A%2F%2Fexample.org%2Fvivo-import%2Frun-metadata%2Frun%2Fyagmur-rna-seq-analysis-workflow-salmon-rs1-9347febf-9033-4c8f-8eb2-f699de6b3479-2026-08-28t18-35-04-684000-00-00) | [RNA-seq Salmon RS1 profile](examples/rnaseq-salmon-rs1/README.md) |
| RNA-seq analysis (STAR, RS1) | Nextflow | [Open in VIVO](https://vivo-fonda.hu-berlin.de/vivo/individual?uri=http%3A%2F%2Fexample.org%2Fvivo-import%2Frun-metadata%2Frun%2Fyagmur-rna-seq-analysis-workflow-star-rs1-3afdb2f4-9abc-4fbc-86f2-c66e81b672ed-2026-08-31t07-25-43-891000-00-00) | [RNA-seq STAR RS1 profile](examples/rnaseq-star-rs1/README.md) |
| RNA-seq analysis (HISAT2, RS1) | Nextflow | [Open in VIVO](https://vivo-fonda.hu-berlin.de/vivo/individual?uri=http%3A%2F%2Fexample.org%2Fvivo-import%2Frun-metadata%2Frun%2Fyagmur-rna-seq-analysis-workflow-hisat2-rs1-c0ece5b9-63ab-41ac-a0f5-1980d02b79dc-2026-09-01t11-38-23-240000-00-00) | [RNA-seq HISAT2 RS1 profile](examples/rnaseq-hisat2-rs1/README.md) |
| RNA-seq analysis (HISAT2, RS2) | Nextflow | [Open in VIVO](https://vivo-fonda.hu-berlin.de/vivo/individual?uri=http%3A%2F%2Fexample.org%2Fvivo-import%2Frun-metadata%2Frun%2Fyagmur-rna-seq-analysis-workflow-hisat2-rs2-c1dacdb1-7d0f-4c61-9fac-941acded044b-2026-08-29t10-07-47-138000-00-00) | [RNA-seq HISAT2 RS2 profile](examples/rnaseq-hisat2-rs2/README.md) |
| A2 MG-4 metagenomic read mapping | Snakemake | [Open in VIVO](https://vivo-fonda.hu-berlin.de/vivo/individual?uri=http%3A%2F%2Fexample.org%2Fvivo-import%2Frun-metadata%2Frun%2Fyagmur-metagenomic-read-mapping-with-customizable-job-granularity-a2-mg4-smoke-20260826-2026-08-26t11-10-52-00-00) | [A2 MG-4 profile](examples/a2-mg4/README.md) |
| PopinSnake genomic insertion detection | Snakemake | [Open in VIVO](https://vivo-fonda.hu-berlin.de/vivo/individual?uri=http%3A%2F%2Fexample.org%2Fvivo-import%2Frun-metadata%2Frun%2Fyagmur-popinsnake-exploratory-workflow-for-genomic-insertion-detection-popinsnake-example-20260828-02-2026-08-28t08-03-05-00-00) | [PopinSnake profile](examples/popinsnake/README.md) |

For the Nextflow profiles, task tags such as tile or sample identifiers are
aggregated under the real process name. This keeps large FORCE2NXF RDF files
compact while the metrics audit retains the task-level evidence.

## Five-minute setup

```bash
git clone https://github.com/YagmurKati/fonda-kubernetes-vivo-publisher.git
cd fonda-kubernetes-vivo-publisher
```

Choose one profile:

```bash
# Geoflow
cp examples/geoflow/publisher.env.example config/publisher.env
cp examples/geoflow/input_datasets.json config/input_datasets.json

# OR: FORCE2NXF
cp examples/force2nxf/publisher.env.example config/publisher.env
cp examples/force2nxf/input_datasets.json config/input_datasets.json

# OR: FONDA_trends European grasslands
cp examples/fonda-trends/publisher.env.example config/publisher.env
cp examples/fonda-trends/input_datasets.json config/input_datasets.json

# OR: RNA-seq Salmon RS1
cp examples/rnaseq-salmon-rs1/publisher.env.example config/publisher.env
cp examples/rnaseq-salmon-rs1/input_datasets.json config/input_datasets.json

# OR: RNA-seq STAR RS1
cp examples/rnaseq-star-rs1/publisher.env.example config/publisher.env
cp examples/rnaseq-star-rs1/input_datasets.json config/input_datasets.json

# OR: RNA-seq HISAT2 RS1
cp examples/rnaseq-hisat2-rs1/publisher.env.example config/publisher.env
cp examples/rnaseq-hisat2-rs1/input_datasets.json config/input_datasets.json

# OR: RNA-seq HISAT2 RS2
cp examples/rnaseq-hisat2-rs2/publisher.env.example config/publisher.env
cp examples/rnaseq-hisat2-rs2/input_datasets.json config/input_datasets.json

# OR: A2 MG-4 (Snakemake)
cp examples/a2-mg4/publisher.env.example config/publisher.env
cp examples/a2-mg4/input_datasets.json config/input_datasets.json

# OR: PopinSnake (Snakemake)
cp examples/popinsnake/publisher.env.example config/popinsnake.publisher.env
cp examples/popinsnake/input_datasets.json config/input_datasets.json
```

Edit `config/publisher.env` and replace every `REPLACE_ME` value. At minimum
confirm:

- `NS`, `PVC_NAME`;
- `WORKFLOW_NAME`, `WORKFLOW_URI`;
- `WORKFLOW_REPO_URL`, `CODE_URI`;
- the engine-specific evidence paths and selectors documented by the selected
  profile.

Store credentials with hidden terminal prompts:

```bash
./scripts/configure-secrets.sh
```

Deploy the reusable code and settings into your namespace:

```bash
./scripts/deploy.sh
```

After run `my-run-01` has finished successfully:

```bash
./scripts/publish-run.sh my-run-01
```

The last command collects the metadata and uploads it to VIVO automatically.
No browser upload and no second command are required.

Validate collection and RDF generation without contacting VIVO:

```bash
./scripts/publish-run.sh my-run-01 --dry-run
```

Publication is idempotency-guarded by receipts on the PVC. A repeated
non-dry-run publication for the same run ID is refused unless
`FORCE_REPUBLISH=1` is deliberately set after reviewing the existing VIVO
record.

For a resumed Nextflow run, include metrics from the original pods of cached
tasks when those metrics are still retained:

```bash
INCLUDE_CACHED_ORIGIN_METRICS=1 ./scripts/publish-run.sh my-run-01-resume
```

## Add it after an existing workflow command

```bash
RUN_ID="my-run-01"
./your-existing-workflow-command "$RUN_ID" && \
  ./scripts/publish-run.sh "$RUN_ID"
```

Publication starts only when the workflow command exits successfully. A VIVO
outage does not rerun the scientific workflow; rerun only `publish-run.sh`.

## Engine-specific execution evidence

### Nextflow profiles

For one `RUN_ID`, the default configuration expects:

```text
/workspace/results/trace-RUN_ID.txt
/workspace/results/nextflow-RUN_ID.log
/workspace/workflow/.nextflow.log
/workspace/workflow/                  workflow source
```

The trace must include `task_id`, `hash`, `native_id`, `name`, `status`, and
`submit`. See [Adapting a Nextflow workflow](docs/ADAPT_NEXTFLOW.md).

### Snakemake profiles

The Snakemake adapter discovers terminal workflow-attempt Pods through the
read-only Kubernetes API, then uses a profile-specific evidence reader. MG-4
verifies its run marker, provenance, checksum, and final SAM; PopinSnake
verifies `RUN_STATUS`, provenance, checksums, and the final compressed VCF. See
the [A2 MG-4 profile](examples/a2-mg4/README.md) and
[PopinSnake profile](examples/popinsnake/README.md).

## Output and verification

For the Nextflow profiles, a successful command prints paths like:

```text
/workspace/vivo-outbox/my-run-01-20260825T144622Z.ttl
/workspace/vivo-outbox/my-run-01-20260825T144622Z.metrics.json
/workspace/vivo-outbox/my-run-01-20260825T144622Z.published.json
```

The Snakemake profiles write the same three artifact types under
`RUN_ROOT/vivo-outbox`.

It also prints `HTTP 200`. Then open the
[VIVO Runs page](https://vivo-fonda.hu-berlin.de/vivo/runs); allow a few seconds
for its list to load.

To remove a published run, use the publication ID from the receipt filename:

```bash
./scripts/remove-run.sh my-run-01-20260825T144622Z --dry-run
./scripts/remove-run.sh my-run-01-20260825T144622Z
```

The second command asks for confirmation and uses the same non-admin VIVO
account. It removes only that run's metadata and keeps the local workflow and
audit files. See [Remove a published run](docs/USER_GUIDE.md#7-remove-a-published-run).

## Documentation

- [User guide](docs/USER_GUIDE.md)
- [Administrator onboarding](docs/ADMIN_SETUP.md)
- [Adapting a Nextflow workflow](docs/ADAPT_NEXTFLOW.md)
- [Security](SECURITY.md)

## Scope

This release supports Nextflow with the Kubernetes executor and the tested A2
MG-4 and PopinSnake Snakemake/Kubernetes layouts. Other workflow engines or
Snakemake layouts need an evidence adapter but can reuse the RDF builder and
`publisher/publish_vivo.py`.

## License

[MIT](LICENSE)
