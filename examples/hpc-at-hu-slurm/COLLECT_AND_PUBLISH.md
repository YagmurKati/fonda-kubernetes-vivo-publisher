# Collect and publish a run from HPC@HU

Requires the one-time setup in [Connect HPC@HU to VIVO](CONNECT_HPC_TO_VIVO.md).

The steps use the tested example: `nf-core/rangeland` 1.0.0 with its `test`
profile, on one node. [Other jobs](#other-jobs) differ only in steps 1 and 2.

Run everything on the login node. Start each session with:

```bash
export WORK=/lustre/GROUP/USER/fonda
module load python/3.12.9-gcc14.2.0
```

## 1. Describe the workflow

Write the settings file. Replace `REPLACE_ME` with your own VIVO person
identifier (the "run by" person).

```bash
cat > ~/.fonda-vivo/slurm.env <<EOF
WORKFLOW_URI="http://example.org/vivo-import/run-metadata/workflow/long-term-vegetation-dynamics-in-the-mediterranean-nf-core"
WORKFLOW_LABEL=""
RUN_LABEL="Long-term vegetation dynamics in the Mediterranean (nf-core)"
RUN_OPERATOR_URI="https://fonda.hu-berlin.de/?page_id=2066#REPLACE_ME"
RESPONSIBLE_RESEARCHER_URIS=""
CODE_REPO_URL="https://github.com/nf-core/rangeland"
GIT_COMMIT=""
LANGUAGE_URIS="http://example.org/vivo-import/run-metadata/language/c-cpp,http://example.org/vivo-import/run-metadata/language/r"
INPUT_DATA_URIS="http://example.org/vivo-import/run-metadata/dataset/nf-core-test-datasets-rangeland"
NEXTFLOW_LAUNCH_DIR="$WORK"
NEXTFLOW_TRACE_GLOB="$WORK/results-{JOB_ID}/pipeline_info/execution_trace_*.txt"
EOF
chmod 600 ~/.fonda-vivo/slurm.env
```

| Setting | Meaning |
|---|---|
| `WORKFLOW_URI` | VIVO workflow the run belongs to |
| `WORKFLOW_LABEL` | only for a workflow that is not in VIVO yet: its title |
| `RUN_LABEL` | first part of the run title, normally the workflow title |
| `RUN_OPERATOR_URI` | VIVO person who ran the job |
| `RESPONSIBLE_RESEARCHER_URIS` | VIVO persons responsible for the workflow, comma-separated |
| `CODE_REPO_URL` | source repository |
| `GIT_COMMIT` | source commit; empty = read from the Nextflow log |
| `LANGUAGE_URIS` | VIVO language records, comma-separated |
| `INPUT_DATA_URIS` | VIVO input dataset records, comma-separated |
| `NEXTFLOW_LAUNCH_DIR` | directory the job runs `nextflow` in (holds `.nextflow.log`) |
| `NEXTFLOW_TRACE_GLOB` | Nextflow trace file; `{JOB_ID}` becomes the Slurm job ID |

## 2. Create the job file

```bash
cd "$WORK/fonda-kubernetes-vivo-publisher"
sed "s#^WORK=.*#WORK=$WORK#" examples/hpc-at-hu-slurm/rangeland-test.sbatch.example > "$WORK/rangeland-test.sbatch"
```

Two things in the job file matter for the metadata:

```bash
export SAMPLE_INTERVAL=1
```

The node's IPMI power is read every second. Use `10` for jobs that run for
hours.

```bash
"$WORK/fonda-kubernetes-vivo-publisher/collector/slurm/run-with-node-sampler.sh" \
  "$HOME/vivo-evidence/$SLURM_JOB_ID" -- \
  nextflow run nf-core/rangeland -r 1.0.0 -profile test,apptainer --outdir "results-$SLURM_JOB_ID"
```

The job's command is wrapped with the sampler, which records the node's
hardware, CPU use and power while the command runs.

## 3. Run the job

```bash
cd "$WORK"
sbatch rangeland-test.sbatch
```

`sbatch` prints the job ID. Use it as `JOB_ID` below. Wait until the job has
left the queue:

```bash
squeue -u "$USER"
```

## 4. Check that the job succeeded

```bash
sacct -j JOB_ID --format=JobID,State,Elapsed,TotalCPU,MaxRSS,ConsumedEnergyRaw,NodeList
```

`State` must be `COMPLETED`. If not, read `slurm-JOB_ID.out`. For
`OUT_OF_MEMORY`, raise `#SBATCH --mem` in the job file and submit again.

## 5. Collect the metadata (dry run)

```bash
cd "$WORK/fonda-kubernetes-vivo-publisher"
examples/hpc-at-hu-slurm/publish-slurm-job.sh JOB_ID --dry-run
```

Nothing is sent to VIVO. Expected output:

```text
{
  "status": "Succeeded",
  "duration_seconds": 74.0,
  "cpu_seconds": 1426.794,
  "whole_node": true,
  "energy_basis": "sampled",
  "slurm_node_energy_joules": 36498.0,
  "sampled_node_energy_joules": 37154.2,
  "energy_kwh": 0.01032,
  "energy_measurement_coverage": "100% of the node (whole node, measured)",
  "run_uri": "http://example.org/vivo-import/run-metadata/run/hpc-at-hu-slurm-JOB_ID-..."
}
TTL: /home/.../vivo-evidence/JOB_ID/publication-.../run.ttl
TTL validated: ...
Run-owned resources replaced on publication: 14
```

This is the output of a published example run, which had the whole node:
`whole_node` is `true` and `energy_basis` is `sampled`, so the energy comes
from the IPMI power readings taken during the job, and
`slurm_node_energy_joules` is Slurm's own, coarser value for comparison.

With the example job file your job shares its node. Then `whole_node` is
`false`, `energy_basis` is `slurm`, `energy_measurement_coverage` is the job's
share of the node, for example `2.4% of the node (shared, estimate)`, and this
line is printed, which is expected:

```text
NOTE: the job shared its node, so its energy is an estimate (the job's CPU-time share of the node energy).
```

There must be no `WARNING` line:

| Warning | Cause |
|---|---|
| `RUN_OPERATOR_URI ... is empty`, `the run has no rm:runOperator` | `RUN_OPERATOR_URI` not set in `slurm.env` |
| `no carbon-intensity data matches` | Electricity Maps token missing or wrong |
| `no node-info.tsv` | the job was not wrapped with the sampler |
| `too few IPMI power readings` | the node's IPMI exporter (port 9290) did not answer during the job |
| `none of the given Nextflow logs/traces` | `NEXTFLOW_LAUNCH_DIR` or `NEXTFLOW_TRACE_GLOB` wrong |

## 6. Publish

```bash
examples/hpc-at-hu-slurm/publish-slurm-job.sh JOB_ID
```

Expected at the end:

```text
HTTP 200
Receipt: .../run.published.json
VIVO page: https://vivo-fonda.hu-berlin.de/vivo/individual?uri=...
```

Open the `VIVO page` link.

Running the same command again replaces the run in VIVO; it does not create a
second one.

## 7. Remove a published run (if needed)

```bash
examples/hpc-at-hu-slurm/remove-slurm-job.sh JOB_ID --dry-run
examples/hpc-at-hu-slurm/remove-slurm-job.sh JOB_ID
```

This removes the run, its date and its workflow stages from VIVO. The
workflow, cluster and dataset records and the local files stay.

## Other jobs

1. In `slurm.env`, set `WORKFLOW_URI`, `RUN_LABEL`, `CODE_REPO_URL`,
   `LANGUAGE_URIS` and `INPUT_DATA_URIS` for your workflow. For jobs without
   Nextflow, leave `NEXTFLOW_LAUNCH_DIR` and `NEXTFLOW_TRACE_GLOB` empty and
   set `GIT_COMMIT`.
2. In your own job file, set `SAMPLE_INTERVAL` and wrap the main command, as
   in [`job.sbatch.example`](job.sbatch.example). The job must use one node.

Steps 3 to 7 are the same.
