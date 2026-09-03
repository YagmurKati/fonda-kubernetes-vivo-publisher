# FONDA_trends European grasslands

Profile for
[`erfea/FONDA_trends-nf`](https://github.com/erfea/FONDA_trends-nf)
on Kubernetes. See a [published example in FONDA VIVO](https://vivo-fonda.hu-berlin.de/vivo/individual?uri=http%3A%2F%2Fexample.org%2Fvivo-import%2Frun-metadata%2Frun%2Fyagmur-trends-in-european-grasslands-test-site-study-2e7a5fcb-44d1-44ea-b3ad-79d2bdab52d8-2026-09-02t20-24-23-057000-00-00).

The run covers the full pipeline on a single test-site tile (`X0067_Y0042`),
executed with the Nextflow Kubernetes executor:
`FORCE_HIGHER_LEVEL` (per endmember gv, npv, soil, shade) →
`PHENOLOGY_SOS_EOS` → `FOLD_AND_FILL` → `CEF` → `AR` → `GLS`.
FORCE runs in `davidfrantz/force:3.10.04`, the Python steps in
`pangeo/pangeo-notebook`, and the R trend analyses (`AR`, `GLS`) in
`friedricht/nf-trends:v5`.

## Wiring the FORCE hand-off

The Kubernetes port needed two adjustments to run end to end, applied to the
workflow copy before launch:

- FORCE must write into the shared results tree the downstream steps read.
  Point its `DIR_HIGHER` at `/data/level3/<endmember>` instead of the task
  work directory, and create that directory in the task script.
- The mask input is optional for this tile. Pass a placeholder file named
  `null` for `maskDir` so the FORCE module resolves it as `DIR_MASK = NULL`.

Provide `/data/level3` as a **writable** volume shared by every task Pod (for
example a subpath of the run's work PVC). The FORCE input datacube stays mounted
read-only at `/data`, so the shared inputs are never modified. FORCE writes
`level3/<endmember>/<tile>/`, phenology adds the SoS/EoS day-of-year layers,
fold-and-fill writes `*_FnF.tif`, and CEF writes `level3/cef/<tile>/`, which
`AR` and `GLS` consume.

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
/workspace/out/trace-full.txt
/workspace/out/console-full.log
/workspace/out/nextflow-full.log
/workspace/wf
```

Keep the Kubernetes Pod name in the trace `native_id` field. Archive
`.nextflow.log` under the `nextflow-full.log` name before the workflow driver
exits. Because `/data` is mounted read-only, the run outputs and the Nextflow
work directory must live on a separate writable PVC.

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
