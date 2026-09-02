# FONDA_trends European grasslands

Profile for
[`erfea/FONDA_trends-nf`](https://github.com/erfea/FONDA_trends-nf)
on Kubernetes. See a [published example in FONDA VIVO](https://vivo-fonda.hu-berlin.de/vivo/individual?uri=http%3A%2F%2Fexample.org%2Fvivo-import%2Frun-metadata%2Frun%2Fyagmur-trends-in-european-grasslands-test-site-study-a2c234fa-6afc-47d0-abe3-15564ba58b2a-2026-09-02t15-28-30-259000-00-00).

The tested run covers the FORCE `force-higher-level` Time Series Analysis /
Spectral Mixture Analysis stage on a single test-site tile (`X0067_Y0042`,
`davidfrantz/force:3.10.04`), executed with the Nextflow Kubernetes executor.

> **Scope: FORCE stage only — this is not a full pipeline run.**
> The published metadata describes the FORCE stage only. The downstream stages
> (phenology SOS/EOS, fold-and-fill, cumulative endmember fractions, and the AR
> and GLS trend analyses) are **not** included: in the Kubernetes port the
> FORCE output (`./trend` in the task work directory) is not yet wired to the
> `/data/level3/<endmember>` location the downstream steps read from, so the
> pipeline stops after FORCE. Completing that FORCE → `/data/level3` hand-off is
> a prerequisite before this profile can publish a full end-to-end run.

## 1. Configure

```bash
cp examples/fonda-trends/publisher.env.example config/publisher.env
cp examples/fonda-trends/input_datasets.json config/input_datasets.json
```

Replace every `REPLACE_ME` value and confirm the trace, log, code, and input
paths. Store the VIVO credentials:

```bash
./scripts/configure-secrets.sh
```

## 2. Keep the run evidence

The profile expects:

```text
/workspace/out/trace-force.txt
/workspace/out/console-force.log
/workspace/out/nextflow-force.log
/workspace/wf
```

Keep the Kubernetes Pod name in the trace `native_id` field. Archive
`.nextflow.log` under the `nextflow-force.log` name before the workflow driver
exits. The FORCE input datacube is mounted read-only at `/data`, so run outputs
and the Nextflow work directory must live on a separate writable PVC.

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
