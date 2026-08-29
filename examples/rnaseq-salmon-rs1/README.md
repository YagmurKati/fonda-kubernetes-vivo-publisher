# RNA-seq Salmon RS1 tested profile

This profile collects and publishes metadata for
[`Nine-s/nextflow_RS1_salmon`](https://github.com/Nine-s/nextflow_RS1_salmon)
on FONDA Kubernetes. It was verified with the uncached `RUN02` execution at
commit `c071811dce8878de67148b0825f1e7fa5c96d982`.

RUN02 completed 11/11 tasks with no cache, failure, or abort in 1,420 seconds.
The collected audit reports 15,928.091725 CPU seconds, 9.7526 GB peak
concurrent memory, 0.071642243 kWh, and 0.022710591 kg CO2e using the
preliminary CO2Map DE factor for the run hour.

The profile published RUN02 to FONDA VIVO with HTTP 200 on 2026-08-29. The
[public workflow-run record](https://vivo-fonda.hu-berlin.de/vivo/individual?uri=http%3A%2F%2Fexample.org%2Fvivo-import%2Frun-metadata%2Frun%2Fyagmur-rna-seq-analysis-workflow-salmon-rs1-9347febf-9033-4c8f-8eb2-f699de6b3479-2026-08-28t18-35-04-684000-00-00)
shows the status, process groups, metrics, inputs, containers, and pinned source
commit. The exact [HTTP 200 receipt](RUN02-20260829T075926Z.published.json) is
included for audit; the task-level metrics JSON remains on the workflow PVC.

## Required PVC evidence

For a run ID such as `RUN02`, the profile expects:

```text
/workspace/results/RUN02/trace-RUN02.txt
/workspace/results/RUN02/nextflow-RUN02.log
/workspace/results/RUN02/nextflow-debug-RUN02.log
/workspace/rnaseq/                         pinned workflow checkout
```

Archive `.nextflow.log` under the run-specific debug-log name immediately
after Nextflow exits. This prevents a later run from rotating or replacing the
session evidence.

## Configure credentials once

Review `publisher.env.example`, especially namespace, PVC, service account,
person URIs, and the credential Secret name. The tested FONDA deployment can
use the profile directly. Other deployments should copy and edit it.

Store an approved non-admin VIVO publisher account in the configured Secret:

```bash
CONFIG_FILE=examples/rnaseq-salmon-rs1/publisher.env.example \
  ./scripts/configure-secrets.sh
```

The credential values are stored only in Kubernetes; they are never committed
or printed.

## Validate without publishing

```bash
CONFIG_FILE=examples/rnaseq-salmon-rs1/publisher.env.example \
  ./scripts/publish-run.sh RUN02 --dry-run
```

This deploys the shared collector, reads the run evidence from `rnaseq-pvc`,
queries Prometheus/Kepler and CO2Map, creates TTL plus a metrics audit, and
validates the VIVO update without contacting VIVO.

## Collect and send automatically to VIVO

After the workflow and run-specific debug-log copy succeed, one command
collects, validates, and publishes the metadata:

```bash
CONFIG_FILE=examples/rnaseq-salmon-rs1/publisher.env.example \
  ./scripts/publish-run.sh RUN02
```

For integration into a workflow launcher, make publication conditional on the
scientific run and evidence capture succeeding:

```bash
run_rnaseq_command && \
  archive_run_specific_debug_log && \
  CONFIG_FILE=examples/rnaseq-salmon-rs1/publisher.env.example \
    ./scripts/publish-run.sh "$RUN_ID"
```

`REQUIRE_SUCCEEDED=1` makes the collector refuse publication unless every
trace row is `COMPLETED`; cached, failed, aborted, warning-bearing, or active
runs do not pass. Successful publication writes a `.published.json` receipt
beside the TTL and prevents accidental duplicate publication for the same run
ID.

## Input provenance

`input_datasets.json` records all three ENA accessions and all three Ensembl
release-106 files as separate upstream URLs. `input-SHA256SUMS` contains the
hashes of the exact staged RUN02 bytes.

One 495 ms task ended between Prometheus/Kepler scrapes. CPU and memory still
cover all 11 tasks through Nextflow `%cpu` and `peak_rss`; energy is honestly
available for 10/11 pods, with no value invented for the missing task.
