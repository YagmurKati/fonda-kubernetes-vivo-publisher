# HPC@HU (Slurm)

Publishes a finished single-node Slurm job from HPC@HU as a run in
[FONDA VIVO](https://vivo-fonda.hu-berlin.de/vivo/runs). This is separate from
the Kubernetes profiles: it reads Slurm accounting instead of Kubernetes and
Prometheus.

## Guides

1. [Connect HPC@HU to VIVO](CONNECT_HPC_TO_VIVO.md): one-time setup.
2. [Collect and publish a run](COLLECT_AND_PUBLISH.md): for every run.
3. [Archive a run's traces in HU-Box](ARCHIVE_TRACES.md): optional, for selected runs.

This collector is built for HPC@HU only. Another Slurm cluster gets its own:
see [Connect another Slurm cluster to FONDA VIVO](../other-slurm-cluster/README.md).

Published example (nf-core/rangeland 1.0.0, test profile, with trace archive):
[run 2026-10-02 11:32](https://vivo-fonda.hu-berlin.de/vivo/individual?uri=http%3A%2F%2Fexample.org%2Fvivo-import%2Frun-metadata%2Frun%2Fhpc-at-hu-slurm-1597982-20261002t093223).

## What is recorded

| VIVO field | Source |
|---|---|
| Start, end, duration, status | `sacct` Start, End, ElapsedRaw, State |
| CPU time | `sacct` TotalCPU |
| Peak memory | largest `sacct` MaxRSS of any job step |
| GPU requested | `sacct` AllocTRES |
| Energy | IPMI power of the node, read while the job runs, see below |
| Energy measurement coverage | the job's share of its node, see below |
| Carbon emission and intensity | hourly German grid intensity matched to the run time |
| Execution host, CPU model, CPUs, memory, OS, kernel | recorded on the node at job start |
| Compute cluster, backend | HPC@HU cluster and Slurm records in VIVO |
| Run by, language, input data, code link | `~/.fonda-vivo/slurm.env` |
| Workflow engine, Nextflow version, code version, commit | `.nextflow.log` (Nextflow jobs) |
| Container images | Apptainer images named in `.nextflow.log` (Nextflow jobs) |
| Task count, workflow stages | Nextflow execution trace (Nextflow jobs) |
| Trace archive | public HU-Box link, added by `archive-slurm-job.sh` (optional) |

Not recorded: average memory. Slurm does not record memory use over time.

## Energy

HPC@HU measures power per node (IPMI), not per job. How the job's energy is
obtained depends on whether the job has the node to itself.

### Shared node: estimate

This is the normal case and what the example job files give. The node's
power also covers other jobs, so the job gets its CPU-time share of Slurm's
node energy:

```text
job energy = node energy x job CPU time / CPU time of all processes on the node
```

This is an estimate. It depends on what the other jobs on the node do, and
the collector prints a note saying so.

### Whole node: measured

The published example run had the whole node to itself. Reserving a whole
node is not recommended for other users of the cluster, and the example job
files do not request it.

When a job has all of the node's CPUs, the collector uses the node's IPMI
power, which the sampler reads every 10 seconds while the job runs, and
integrates it over the job's duration:

```text
job energy = node power, integrated over the time the job ran
```

This is a measurement of the whole node and includes its idle power. Cooling
and network are not included.

Slurm's own value (`sacct` ConsumedEnergyRaw) is stated next to it for
comparison. Slurm reads the power only every 30 seconds, which is coarse for
short jobs: in two 75-second test jobs it differed from the measured value by
18% and by 2%.

In both cases the calculation with its numbers is stored in the run's energy
calculation method field.

### Energy measurement coverage

The run's energy measurement coverage field says how much of the measured node
the job had:

| Value | Meaning |
|---|---|
| `100% of the node (whole node, measured)` | the job had the whole node; its energy is measured |
| `2.4% of the node (shared, estimate)` | the job's CPU time was 2.4% of all CPU time on the node; its energy is that share of the node energy |

The lower the value, the more the energy depends on the CPU-time assumption,
and the smaller the part of the node's idle power that is counted for the job.
Runs with very different values are not comparable in energy.

For Kubernetes runs the same field gives the share of pods whose energy was
measured, for example `14.3% (40 of 280 pods)`.

## Files

| File | Purpose |
|---|---|
| `collector/slurm/run-with-node-sampler.sh` | wraps the job command; samples node CPU use and power |
| `collector/slurm/node-info.sh` | records the node hardware |
| `collector/collect_slurm_job_metadata.py` | builds the run metadata (Turtle) |
| `publish-slurm-job.sh` | collects and publishes one job |
| `remove-slurm-job.sh` | removes one published job from VIVO |
| `archive-slurm-job.sh` | uploads one job's traces to HU-Box and adds the link to VIVO |
| `slurm.env.example` | settings template |
| `rangeland-test.sbatch.example` | tested nf-core/rangeland job |
| `job.sbatch.example` | minimal job for other workflows |

## Limits

- One node per job.
- Energy is measured only when the job has the whole node; otherwise it is
  an estimate.
- The job command must be wrapped with the sampler. A job that ran without it
  cannot be published.
