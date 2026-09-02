# PopinSnake

Profile for the Snakemake workflow in
[`FONDA A6 PopinSnake`](https://gitlab.informatik.hu-berlin.de/fonda_a6/popinSnake).
See a [published example in FONDA VIVO](https://vivo-fonda.hu-berlin.de/vivo/individual?uri=http%3A%2F%2Fexample.org%2Fvivo-import%2Frun-metadata%2Frun%2Fyagmur-popinsnake-exploratory-workflow-for-genomic-insertion-detection-popinsnake-example-20260828-02-2026-08-28t08-03-05-00-00).

## 1. Configure

```bash
cp examples/popinsnake/publisher.env.example config/popinsnake.publisher.env
cp examples/popinsnake/input_datasets.json config/input_datasets.json
```

Replace every `REPLACE_ME` value. Set `RUN_ROOT` to the run directory on the
mounted PVC. New workflow Pods must carry the label
`fonda.hu-berlin.de/run-id=RUN_ID`.

Store the VIVO credentials:

```bash
CONFIG_FILE=config/popinsnake.publisher.env ./scripts/configure-secrets.sh
```

## 2. Keep the run evidence

Keep `RUN_STATUS`, the provenance directory, the checksums, the final compressed
VCF, and the workflow-attempt Pods available until metadata collection
finishes.

## 3. Validate

```bash
./scripts/collect-and-publish-popinsnake.sh RUN_ID --dry-run
```

## 4. Publish

```bash
./scripts/collect-and-publish-popinsnake.sh RUN_ID
```

Open the [FONDA VIVO Runs page](https://vivo-fonda.hu-berlin.de/vivo/runs) and
check the new record. The TTL, metrics audit, and receipt are stored under
`RUN_ROOT/vivo-outbox`.

## 5. Remove a publication

Use the publication ID from the `.published.json` filename:

```bash
CONFIG_FILE=config/popinsnake.publisher.env \
  ./scripts/remove-run.sh PUBLICATION_ID --dry-run
CONFIG_FILE=config/popinsnake.publisher.env \
  ./scripts/remove-run.sh PUBLICATION_ID
```

The second command asks for confirmation and removes only that published run's
metadata from VIVO.
