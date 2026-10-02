# HPC@HU (Slurm)

Publishes a finished single-node Slurm job from HPC@HU as a run in
[FONDA VIVO](https://vivo-fonda.hu-berlin.de/vivo/runs). This is separate from
the Kubernetes profiles: it reads Slurm accounting instead of Kubernetes and
Prometheus.

## Guides

1. [Connect HPC@HU to VIVO](CONNECT_HPC_TO_VIVO.md): one-time setup.
2. [Collect and publish a run](COLLECT_AND_PUBLISH.md): for every run.
3. [Archive a run's traces in HU-Box](ARCHIVE_TRACES.md): optional, for selected runs.

Published example:
[nf-core/rangeland 1.0.0 test profile, 2026-10-01](https://vivo-fonda.hu-berlin.de/vivo/individual?uri=http%3A%2F%2Fexample.org%2Fvivo-import%2Frun-metadata%2Frun%2Fhpc-at-hu-slurm-1596378-20261001t164208).

## What is recorded

| VIVO field | Source |
|---|---|
| Start, end, duration, status | `sacct` Start, End, ElapsedRaw, State |
| CPU time | `sacct` TotalCPU |
| Peak memory | largest `sacct` MaxRSS of any job step |
| GPU requested | `sacct` AllocTRES |
| Energy | Slurm IPMI node energy and node CPU samples, see below |
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

HPC@HU measures power per node (IPMI), not per job, and nodes are shared. The
job gets its CPU-time share of the node energy:

```text
job energy = node energy x job CPU time / CPU time of all processes on the node
```

- node energy: `sacct` ConsumedEnergyRaw (Slurm `acct_gather_energy/ipmi`);
- job CPU time: `sacct` TotalCPU;
- CPU time of all processes on the node: the node's `node_exporter`
  (port 9100), sampled every 10 seconds while the job runs.

The value is an estimate. The full calculation with its numbers is stored in
the run's energy calculation method field.

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
- The job command must be wrapped with the sampler. A job that ran without it
  cannot be published.
