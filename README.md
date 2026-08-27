# FONDA Kubernetes workflow-run publisher for VIVO

Publish metadata from supported workflow runs on the FONDA Kubernetes cluster
directly to [FONDA VIVO](https://vivo-fonda.hu-berlin.de/vivo/runs). Tested
adapters are included for Nextflow and the Snakemake-based A2 MG-4
reproduction.

The toolkit collects:

- workflow identity, source revision, containers, tasks, status, and duration;
- CPU time, average/peak memory, and Kepler energy from Prometheus;
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

| Workflow | Workflow engine | Tested result | Profile |
| --- | --- | --- | --- |
| Geoflow annual land-cover mapping | Nextflow | Successful Kubernetes run and VIVO publication | [Geoflow profile](examples/geoflow/README.md) |
| FORCE2NXF rangeland workflow | Nextflow | Successful resumed run: 3,092 trace rows, 2,796 cached tasks, and 32 retry attempts | [FORCE2NXF profile](examples/force2nxf/README.md) |
| A2 MG-4 metagenomic read mapping | Snakemake | Successful reproduction: six resumable Kubernetes attempts and HTTP 200 VIVO publication | [A2 MG-4 profile](examples/a2-mg4/README.md) |

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

# OR: A2 MG-4 (Snakemake)
cp examples/a2-mg4/publisher.env.example config/publisher.env
cp examples/a2-mg4/input_datasets.json config/input_datasets.json
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

### Snakemake MG-4 profile

The MG-4 profile discovers terminal workflow-attempt Pods through the read-only
Kubernetes API and verifies the run marker, provenance, checksum, and final SAM
output on the PVC. See the
[A2 MG-4 profile](examples/a2-mg4/README.md).

## Output and verification

For the Nextflow profiles, a successful command prints paths like:

```text
/workspace/vivo-outbox/my-run-01-20260825T144622Z.ttl
/workspace/vivo-outbox/my-run-01-20260825T144622Z.metrics.json
/workspace/vivo-outbox/my-run-01-20260825T144622Z.published.json
```

The MG-4 profile writes the same three artifact types under
`RUN_ROOT/vivo-outbox`.

It also prints `HTTP 200`. Then open the
[VIVO Runs page](https://vivo-fonda.hu-berlin.de/vivo/runs); allow a few seconds
for its list to load.

The carbon factor from `electricity-maps-latest` is the newest value available
when metadata is collected. It is explicitly stored as a collection-time proxy,
not as an exact historical value for the run interval.

## Documentation

- [User guide](docs/USER_GUIDE.md)
- [Administrator onboarding](docs/ADMIN_SETUP.md)
- [Adapting a Nextflow workflow](docs/ADAPT_NEXTFLOW.md)
- [Security](SECURITY.md)

## Scope

This release supports Nextflow with the Kubernetes executor and the tested A2
MG-4 Snakemake/Kubernetes layout. Other workflow engines or Snakemake layouts
need a trace adapter but can reuse the RDF builder and
`publisher/publish_vivo.py`.

## License

[MIT](LICENSE)
