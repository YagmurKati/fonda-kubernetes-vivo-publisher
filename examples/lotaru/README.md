# Lotaru

Profile for [`CRC-FONDA/Lotaru`](https://github.com/CRC-FONDA/Lotaru), the code
behind the Lotaru papers. It predicts the runtime of scientific workflow tasks
on heterogeneous cluster nodes from measurements taken on one local machine.

Lotaru is **not** a workflow-engine run. It is a Java program executed as a
single Kubernetes Job, which reads the execution traces bundled in its own
repository and writes one prediction CSV per target machine. The collector
profile is `lotaru` and `ENGINE_URI` names Java rather than a workflow engine.
A published example in FONDA VIVO is linked from the profile table in the
repository README.

## What the published duration measures

The collector derives a run's duration from the Pods carrying the run's
`fonda.hu-berlin.de/run-id` label. This profile uses one Job for both the
dependency build and the prediction program, so the published duration includes
the build. The program's own duration and the build duration are recorded
separately in `provenance/run-duration-seconds.txt` and
`provenance/build-duration-seconds.txt`, and both appear in the run
description. If you want the published duration to exclude the build, split the
work into two Jobs and label only the second.

## 1. Configure

```bash
cp examples/lotaru/publisher.env.example config/lotaru.publisher.env
cp examples/lotaru/input_datasets.json config/input_datasets.json
```

Replace every `REPLACE_ME` value. Set `RUN_ROOT` to the run directory on the
mounted PVC and `JOB_NAME_REGEX` to match the run's Job.

Store the VIVO credentials:

```bash
CONFIG_FILE=config/lotaru.publisher.env ./scripts/configure-secrets.sh
```

## 2. Keep the run evidence

Keep `RUN_STATUS` (which must read `COMPLETED`), the provenance directory, the
prediction CSVs under `results/`, and the Pod labelled with the run id
available until metadata collection finishes.

The run must record its upstream commit in `provenance/workflow-commit.txt` as
a full 40-character SHA, and a `provenance/result-SHA256SUMS` manifest covering
the prediction CSVs. Lotaru produces no single final artifact, so the collector
hashes the sorted per-file digests from that manifest to identify the result
set.

## 3. Validate

```bash
./scripts/collect-and-publish-lotaru.sh RUN_ID --dry-run
```

## 4. Publish

```bash
./scripts/collect-and-publish-lotaru.sh RUN_ID
```

Open the [FONDA VIVO Runs page](https://vivo-fonda.hu-berlin.de/vivo/runs) and
check the new record. The TTL, metrics audit, and receipt are stored under
`RUN_ROOT/vivo-outbox`.

## 5. Remove a publication

Use the publication ID from the `.published.json` filename:

```bash
CONFIG_FILE=config/lotaru.publisher.env \
  ./scripts/remove-run.sh PUBLICATION_ID --dry-run
CONFIG_FILE=config/lotaru.publisher.env \
  ./scripts/remove-run.sh PUBLICATION_ID
```

The second command asks for confirmation and removes only that published run's
metadata from VIVO.
