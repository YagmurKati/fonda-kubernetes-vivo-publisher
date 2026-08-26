# Geoflow tested profile

This profile targets the Kubernetes adaptation in
[YagmurKati/geoflow-kubernetes-vivo-metadata](https://github.com/YagmurKati/geoflow-kubernetes-vivo-metadata).
It was tested with Nextflow 25.04.8, the FONDA Kubernetes executor,
Prometheus, Kepler, and the `X0103_Y0103` FORCE input tile.

## Configure

From the generic publisher repository:

```bash
cp examples/geoflow/publisher.env.example config/publisher.env
cp examples/geoflow/input_datasets.json config/input_datasets.json
```

Edit `config/publisher.env`. Replace every `REPLACE_ME` value and check the PVC
and paths against the companion Geoflow repository.

Store the approved non-admin VIVO account and optional Electricity Maps token:

```bash
./scripts/configure-secrets.sh
```

## Publish a completed run

```bash
./scripts/publish-run.sh geoflow-run-01
```

For a resumed run:

```bash
INCLUDE_CACHED_ORIGIN_METRICS=1 \
  ./scripts/publish-run.sh geoflow-run-01-resume
```

This command collects the metadata and publishes the timestamped TTL. It does
not run or rerun Geoflow.
