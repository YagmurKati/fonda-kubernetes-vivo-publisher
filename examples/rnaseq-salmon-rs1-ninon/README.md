# RNA-seq Salmon RS1 driven by rnaseq-ninon-experiments

Profile for [`Nine-s/nextflow_RS1_salmon`](https://github.com/Nine-s/nextflow_RS1_salmon)
run with the configurations in
[`CRC-FONDA/rnaseq-ninon-experiments`](https://github.com/CRC-FONDA/rnaseq-ninon-experiments).
See a [published example in FONDA VIVO](https://vivo-fonda.hu-berlin.de/vivo/individual?uri=http%3A%2F%2Fexample.org%2Fvivo-import%2Frun-metadata%2Frun%2Fyagmur-rna-seq-analysis-workflow-salmon-rs1-889cb6b3-521c-4c5f-9a26-472f77d5ac6a-2026-09-08t17-14-14-359000-00-00).

That repository is not a workflow. It holds one automation script and six
Nextflow configs that drive `nextflow_RS1_salmon` and `nextflow_RS2_salmon`
over three dataset sizes. The workflow is the same one covered by the
[RNA-seq Salmon RS1 profile](../rnaseq-salmon-rs1/README.md), so this profile
keeps the same `WORKFLOW_URI`: only the configuration and the input data
differ, and a run is told apart by its own record.

## 1. Configure

```bash
cp examples/rnaseq-salmon-rs1-ninon/publisher.env.example config/publisher.env
cp examples/rnaseq-salmon-rs1-ninon/input_datasets.json config/input_datasets.json
```

Replace every `REPLACE_ME` value and confirm the trace, log, and code paths.
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
/workspace/projects/Nine-s/nextflow_RS1_salmon
```

Keep the Kubernetes Pod name in the trace `native_id` field.

**Drop `script` and `env` from the config's `trace.fields`.** The upstream
configs list both, and each contains tab and newline characters, so the trace
stops being one row per task: a five-task run produced forty lines that a TSV
reader parsed as thirty-eight rows. The collector would then build task records
from the fragments instead of failing, so the field list has to be corrected
before the run, not after.

The upstream configs also target another cluster: namespace, storage claim and
kubeconfig context all need replacing, `docker.enabled` must be `false`
because the Kubernetes executor uses each process's container as the pod image,
and the `dag` filename needs an extension for Nextflow to infer the renderer.

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

## Input data

The configs read from a `small_droso`, `medium_droso` or large directory, which
the repository does not contain. Record which reads a run actually consumed in
`input_datasets.json`; the published example used the smallest of the three
available accessions for the D1 configuration.
