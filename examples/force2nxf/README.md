# FORCE2NXF rangeland workflow

Profile for
[`CRC-FONDA/FORCE2NXF-Rangeland`](https://github.com/CRC-FONDA/FORCE2NXF-Rangeland)
on Kubernetes. See a [published example in FONDA VIVO](https://vivo-fonda.hu-berlin.de/vivo/individual?uri=http%3A%2F%2Fexample.org%2Fvivo-import%2Frun-metadata%2Frun%2Fdefault-long-term-vegetation-dynamics-in-the-mediterranean-force2nxf-e5295c77-62e8-4773-afc5-706750fb1a33-2026-08-25t18-25-43-637000-00-00).

## 1. Configure

```bash
cp examples/force2nxf/publisher.env.example config/publisher.env
cp examples/force2nxf/input_datasets.json config/input_datasets.json
```

Replace every `REPLACE_ME` value and confirm the trace, log, and code paths.
Store the VIVO credentials:

```bash
./scripts/configure-secrets.sh
```

## 2. Keep the run evidence

The profile expects:

```text
/workspace/rangeland/results/trace-RUN_ID.txt
/workspace/rangeland/results/nextflow-RUN_ID.log
/workspace/rangeland/FORCE2NXF-Rangeland/nextflowWF/.nextflow.log
/workspace/rangeland/FORCE2NXF-Rangeland/
```

Keep the Kubernetes Pod name in the trace `native_id` field.

## 3. Validate

```bash
./scripts/publish-run.sh RUN_ID --dry-run
```

For a reviewed resumed run, set `INCLUDE_CACHED_ORIGIN_METRICS=1` and
`REQUIRE_SUCCEEDED=0` in `config/publisher.env` before validation.

## 4. Publish

```bash
./scripts/publish-run.sh RUN_ID
```

Open the [FONDA VIVO Runs page](https://vivo-fonda.hu-berlin.de/vivo/runs) and
check the new record. The TTL, metrics audit, and receipt are written to
`/workspace/vivo-outbox`.

## 5. Remove a publication

Use the publication ID from the `.published.json` filename:

```bash
./scripts/remove-run.sh PUBLICATION_ID --dry-run
./scripts/remove-run.sh PUBLICATION_ID
```

The second command asks for confirmation and removes only that published run's
metadata from VIVO.
