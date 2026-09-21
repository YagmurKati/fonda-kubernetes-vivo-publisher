# RNA-seq STAR RS2

Profile for
[`Nine-s/nextflow_RS2_star`](https://github.com/Nine-s/nextflow_RS2_star) on
Kubernetes. See a [published example in FONDA VIVO](https://vivo-fonda.hu-berlin.de/vivo/individual?uri=http%3A%2F%2Fexample.org%2Fvivo-import%2Frun-metadata%2Frun%2Fyagmur-rna-seq-analysis-workflow-star-rs2-5ff9e53d-bfa2-4fd8-88b2-c65ce9e371ac-2026-09-03t04-13-05-116000-00-00).

RS2 is the second read set of the A2 RNA-seq experiments. It uses the same
Drosophila inputs as the other RS2 profiles, and the same STAR toolchain as
[RNA-seq STAR RS1](../rnaseq-star-rs1/README.md).

## 1. Configure

```bash
cp examples/rnaseq-star-rs2/publisher.env.example config/publisher.env
cp examples/rnaseq-star-rs2/input_datasets.json config/input_datasets.json
```

Replace every `REPLACE_ME` value and confirm the trace, log, code, and input
paths. `DECLARED_CONTAINER_IMAGES` needs the digests your run used; the images
the workflow declares by tag at the pinned commit are listed in the template,
and the trace's `container` column records what actually ran.

Store the VIVO credentials:

```bash
./scripts/configure-secrets.sh
```

## 2. Keep the run evidence

The profile expects:

```text
/workspace/results/RUN_ID/trace-RUN_ID.txt
/workspace/results/RUN_ID/nextflow-RUN_ID.log
/workspace/results/RUN_ID/nextflow-debug-RUN_ID.log
CODE_PATH
```

Keep the Kubernetes Pod name in the trace `native_id` field. Archive
`.nextflow.log` under the run-specific debug-log name before the workflow
driver exits. `input-SHA256SUMS` in this directory records the checksums of
the read and reference inputs.

## 3. Validate

```bash
./scripts/publish-run.sh RUN_ID --dry-run
```

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
