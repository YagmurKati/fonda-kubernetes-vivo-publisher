# nf-core/rangeland workflow

Profile for [`nf-core/rangeland`](https://github.com/nf-core/rangeland) on
Kubernetes. This is the nf-core port of the Mediterranean vegetation-dynamics
workflow and has its own VIVO workflow individual, separate from the
[FORCE2NXF profile](../force2nxf/README.md). See a
[published example in FONDA VIVO](https://vivo-fonda.hu-berlin.de/vivo/individual?uri=http%3A%2F%2Fexample.org%2Fvivo-import%2Frun-metadata%2Frun%2Fyagmur-long-term-vegetation-dynamics-in-the-mediterranean-nf-core-efd0ee83-ae64-451e-ad2a-efd52b206ad7-2026-09-07t21-42-29-001000-00-00).

## 1. Configure

```bash
cp examples/rangeland-nfcore/publisher.env.example config/publisher.env
cp examples/rangeland-nfcore/input_datasets.json config/input_datasets.json
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
/workspace/.nextflow/assets/nf-core/rangeland
```

nf-core writes the trace to `results/pipeline_info/execution_trace_*.txt` and
the debug log to the launch directory, so copy both into the layout above after
the run. Keep the Kubernetes Pod name in the trace `native_id` field.

Set `DECLARED_CONTAINER_IMAGES` for this profile. Nextflow's `k8s.cleanup`
deletes successful task pods, so Kubernetes and Prometheus discovery alone can
omit containers. The digests in the template are the ones used by pipeline
release `1.0.0`; re-resolve them for a different revision.

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

## Notes on running the pipeline

The Kubernetes executor needs `process.shell` overridden. The nf-core template
sets it as a multi-line string, which Nextflow 25.04 splices verbatim into
`nxf_launch()` in the task wrapper; the result calls the non-executable
`.command.run` directly and every task exits 126 with `Permission denied`.
Add this to the executor config:

```groovy
process.shell = ['/bin/bash', '-C', '-e', '-u', '-o', 'pipefail']
```

The pipeline's `test` profile finishes most tasks in under a second, so
kube-state-metrics and Kepler observe only a minority of pods. The collector
falls back to the Nextflow trace for CPU and memory and records the coverage in
`rm:cpuTimeCalculationMethod` and `rm:energyCalculationMethod`. Energy has no
trace fallback, so for such runs it covers only the observed pods and
understates the run; a `test_full`-sized run gives Kepler pods long enough to
measure.
