# A2 MG-4

Profile for the Snakemake workflow in
[`CRC-FONDA/A2-job-granularity`](https://github.com/CRC-FONDA/A2-job-granularity).
See a [published example in FONDA VIVO](https://vivo-fonda.hu-berlin.de/vivo/individual?uri=http%3A%2F%2Fexample.org%2Fvivo-import%2Frun-metadata%2Frun%2Fyagmur-metagenomic-read-mapping-with-customizable-job-granularity-a2-mg4-smoke-20260826-2026-08-26t11-10-52-00-00).

## 1. Configure

```bash
cp examples/a2-mg4/publisher.env.example config/publisher.env
cp examples/a2-mg4/input_datasets.json config/input_datasets.json
```

Replace every `REPLACE_ME` value in `config/publisher.env`. Set `RUN_ROOT` to
the run directory on the mounted PVC. New workflow Pods must carry the label
`fonda.hu-berlin.de/run-id=RUN_ID`.

Store the VIVO credentials:

```bash
./scripts/configure-secrets.sh
```

## 2. Keep the run evidence

Keep the final SAM, run marker, provenance, checksum, and workflow-attempt Pods
available until metadata collection finishes.

## 3. Validate

```bash
./scripts/publish-run.sh RUN_ID --dry-run
```

## 4. Publish

```bash
./scripts/publish-run.sh RUN_ID
```

Open the [FONDA VIVO Runs page](https://vivo-fonda.hu-berlin.de/vivo/runs) and
check the new record. The TTL, metrics audit, and receipt are stored under
`RUN_ROOT/vivo-outbox`.

## 5. Remove a publication

Use the publication ID from the `.published.json` filename:

```bash
./scripts/remove-run.sh PUBLICATION_ID --dry-run
./scripts/remove-run.sh PUBLICATION_ID
```

The second command asks for confirmation and removes only that published run's
metadata from VIVO.
