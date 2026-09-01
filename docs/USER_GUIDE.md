# User guide

## 1. Request VIVO publishing access

Send the VIVO administrator:

- your name and institutional email;
- your FONDA Kubernetes namespace;
- your workflow title and repository URL;
- the VIVO person and FONDA subproject pages that should be linked.

The administrator provides or enables a non-admin publisher account. Never ask
for the site administrator password.

## 2. Clone and configure

```bash
git clone https://github.com/YagmurKati/fonda-kubernetes-vivo-publisher.git
cd fonda-kubernetes-vivo-publisher
```

Select the profile for the workflow:

```bash
# Geoflow
cp examples/geoflow/publisher.env.example config/publisher.env
cp examples/geoflow/input_datasets.json config/input_datasets.json

# OR: FORCE2NXF
cp examples/force2nxf/publisher.env.example config/publisher.env
cp examples/force2nxf/input_datasets.json config/input_datasets.json

# OR: RNA-seq Salmon RS1
cp examples/rnaseq-salmon-rs1/publisher.env.example config/publisher.env
cp examples/rnaseq-salmon-rs1/input_datasets.json config/input_datasets.json

# OR: RNA-seq STAR RS1
cp examples/rnaseq-star-rs1/publisher.env.example config/publisher.env
cp examples/rnaseq-star-rs1/input_datasets.json config/input_datasets.json

# OR: RNA-seq HISAT2 RS2
cp examples/rnaseq-hisat2-rs2/publisher.env.example config/publisher.env
cp examples/rnaseq-hisat2-rs2/input_datasets.json config/input_datasets.json

# OR: A2 MG-4 (Snakemake)
cp examples/a2-mg4/publisher.env.example config/publisher.env
cp examples/a2-mg4/input_datasets.json config/input_datasets.json

# OR: PopinSnake (Snakemake)
cp examples/popinsnake/publisher.env.example config/popinsnake.publisher.env
```

Edit `config/publisher.env` and replace every `REPLACE_ME` value. Values ending
in `URIS` are comma-separated lists without spaces. Use underlying stable
resource URIs, not a copied HTML label. Review every path even when starting
from a tested profile, because the PVC layout can differ between users.

If the workflow uses a known input dataset, copy
`config/input_datasets.json.example` over `config/input_datasets.json`, replace
all placeholders, and link to a checksum manifest for the exact input version.
Otherwise leave the provided empty dataset list unchanged.

Use `upstream_source_urls` when one logical input dataset combines several
source files or accessions. Each URL is validated and emitted separately;
`upstream_source_url` remains supported for older single-source profiles.

## 3. Store credentials in your Kubernetes namespace

```bash
./scripts/configure-secrets.sh
```

The script prompts for VIVO email, VIVO password, password confirmation, and—if
configured—an Electricity Maps token. Input is stored in Kubernetes Secrets;
it is not written to this repository or printed.

Confirm only the Secret names and keys:

```bash
source config/publisher.env
kubectl -n "$NS" get secret "$VIVO_CREDENTIALS_SECRET"
kubectl -n "$NS" get secret electricity-maps-api-token
```

Do not decode or paste Secret values into support messages.

## 4. Deploy and preflight

```bash
./scripts/deploy.sh
```

This checks the namespace, PVC, service account, configuration, JSON input
metadata, and Secrets. It creates namespace-scoped ConfigMaps. The Snakemake
profiles also apply publisher-owned, read-only Pod/Job RBAC. It does not run
the workflow or publish RDF.

## 5. Run and publish

Run your workflow normally, using a unique run ID and the configured file
paths. When it succeeds:

```bash
./scripts/publish-run.sh RUN_ID
```

Wait for all pod metrics to be collected. Success ends with:

```text
Published TTL to VIVO: ...
HTTP 200
Receipt: ...published.json
```

No additional upload is needed.

Validate collection and RDF generation without contacting VIVO:

```bash
./scripts/publish-run.sh RUN_ID --dry-run
```

For a resumed Nextflow run, include cached-origin metrics when Prometheus still
retains them:

```bash
INCLUDE_CACHED_ORIGIN_METRICS=1 ./scripts/publish-run.sh RUN_ID
```

The published RDF reports a successful workflow with historical retry attempts
as `Succeeded with warnings`; a recovered task attempt does not turn the whole
workflow into a failed run.

## 6. Verify

Open <https://vivo-fonda.hu-berlin.de/vivo/runs>, wait several seconds, and
search for the workflow title and run time. Keep the three timestamped files on
the PVC together.

## Retry rules

- Missing trace/log: correct the paths in `config/publisher.env`, then rerun
  `publish-run.sh`.
- VIVO or network failure: rerun `publish-run.sh`; do not rerun the workflow.
- A run ID with an existing successful receipt is not sent twice unless
  `FORCE_REPUBLISH=1` is deliberately set after reviewing the VIVO record.
- A dry run gets a new timestamped TTL and audit but no receipt or VIVO write.

VIVO stores RDF triples, not the source filename. Removal must be performed by
the VIVO administrator using the exact preserved TTL/audit and a run-scoped RDF
deletion; do not use the entire TTL as a removal file because it also describes
shared workflow and infrastructure resources.
