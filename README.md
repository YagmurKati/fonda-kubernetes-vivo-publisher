# FONDA Kubernetes run publisher for VIVO

Publish metadata from a completed Nextflow run on the FONDA Kubernetes cluster
directly to [FONDA VIVO](https://vivo-fonda.hu-berlin.de/vivo/runs).

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
2. a completed Nextflow run whose trace/log files are on a shared PVC;
3. a personal or team **non-admin VIVO publisher account** provisioned by the
   VIVO administrator;
4. optionally, an Electricity Maps token for a latest-available carbon proxy.

Do not use or share the VIVO administrator account. See
[Administrator onboarding](docs/ADMIN_SETUP.md).

## Five-minute setup

```bash
git clone https://github.com/YagmurKati/fonda-kubernetes-vivo-publisher.git
cd fonda-kubernetes-vivo-publisher
cp config/publisher.env.example config/publisher.env
```

Edit `config/publisher.env`. At minimum replace:

- `NS`, `PVC_NAME`;
- `WORKFLOW_NAME`, `WORKFLOW_URI`;
- `WORKFLOW_REPO_URL`, `CODE_URI`;
- the trace, console-log, debug-log, and code paths when your layout differs.

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

## Add it after an existing workflow command

```bash
RUN_ID="my-run-01"
./your-existing-nextflow-run-command "$RUN_ID" && \
  ./scripts/publish-run.sh "$RUN_ID"
```

Publication starts only when the workflow command exits successfully. A VIVO
outage does not rerun the scientific workflow; rerun only `publish-run.sh`.

## Required Nextflow files

For one `RUN_ID`, the default configuration expects:

```text
/workspace/results/trace-RUN_ID.txt
/workspace/results/nextflow-RUN_ID.log
/workspace/workflow/.nextflow.log
/workspace/workflow/                  workflow source
```

The trace must include `task_id`, `hash`, `native_id`, `name`, `status`, and
`submit`. See [Adapting a Nextflow workflow](docs/ADAPT_NEXTFLOW.md).

## Output and verification

On success the command prints paths like:

```text
/workspace/vivo-outbox/my-run-01-20260825T144622Z.ttl
/workspace/vivo-outbox/my-run-01-20260825T144622Z.metrics.json
/workspace/vivo-outbox/my-run-01-20260825T144622Z.published.json
```

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

This release supports Nextflow with the Kubernetes executor. Other workflow
engines need a trace adapter but can reuse `publisher/publish_vivo.py`.

## License

[MIT](LICENSE)
