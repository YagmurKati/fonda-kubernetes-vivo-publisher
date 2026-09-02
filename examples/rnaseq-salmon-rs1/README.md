# RNA-seq Salmon RS1

Profile for
[`Nine-s/nextflow_RS1_salmon`](https://github.com/Nine-s/nextflow_RS1_salmon)
on Kubernetes. See a [published example in FONDA VIVO](https://vivo-fonda.hu-berlin.de/vivo/individual?uri=http%3A%2F%2Fexample.org%2Fvivo-import%2Frun-metadata%2Frun%2Fyagmur-rna-seq-analysis-workflow-salmon-rs1-9347febf-9033-4c8f-8eb2-f699de6b3479-2026-08-28t18-35-04-684000-00-00).

## 1. Configure

```bash
cp examples/rnaseq-salmon-rs1/publisher.env.example config/publisher.env
cp examples/rnaseq-salmon-rs1/input_datasets.json config/input_datasets.json
```

Replace every `REPLACE_ME` value and confirm the trace, log, code, and input
paths. Store the VIVO credentials:

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
driver exits.

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
