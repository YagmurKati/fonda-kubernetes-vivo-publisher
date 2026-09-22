# RNA-seq workflow with RAPL energy measurement

Run the complete public **SRR16287545** paired-end RNA-seq sample with FastQC,
Salmon indexing/quantification and MultiQC, measure CPU-package and DRAM energy,
and publish validated run metadata to VIVO.

- [Published longer run](https://vivo-fonda.hu-berlin.de/vivo/individual?uri=http%3A%2F%2Fexample.org%2Fvivo-import%2Frun-metadata%2Frun%2Ffonda-rnaseq-rapl-srr16287545-20260922-074112)
- [Existing workflow record](https://vivo-fonda.hu-berlin.de/vivo/individual?uri=http%3A%2F%2Fexample.org%2Fvivo-import%2Frun-metadata%2Fworkflow%2Fsmall-rna-seq-rapl-energy-measurement)
- [Verified publication summary](publication-summary.json)

The September 22 run completed all four tasks in **522.719 seconds (8m 43s)**,
processing **25,024,930 read pairs**. Task CPU time was **738.679 CPU-seconds**;
largest task peak RSS was **0.486 GB**. Whole-node CPU-package energy was
**39,026.641 J (0.010840734 kWh)**; DRAM was **5,760.155 J**, reported separately.
The historical run is already published: do not submit or publish it again.
The publisher refuses that known session. New runs receive a stable identity
from their own Nextflow session UUID.

The workflow display name has no “Small” qualifier. Its older resource URI is
retained so existing links and the earlier run continue to work.

## Sources and scope

| Component | Pinned source |
| --- | --- |
| Executed workflow | [nextflow-io/rnaseq-nf, 5c89d385](https://github.com/nextflow-io/rnaseq-nf/tree/5c89d3859abbe54893d4e1ae0f21115dcebd9d1d) |
| Energy collection method | [CRC-FONDA/RAPL_measurement_workflows, 8786ab77](https://github.com/CRC-FONDA/RAPL_measurement_workflows/tree/8786ab77fe4761fefb150957050d862c02c3dde8) |
| Reads | [ENA SRR16287545](https://www.ebi.ac.uk/ena/browser/view/SRR16287545), full paired-end sample, about 2.37 GB compressed |
| Reference | [Ensembl 106 BDGP6.32 Drosophila cDNA](https://ftp.ensembl.org/pub/release-106/fasta/drosophila_melanogaster/cdna/), 31,089 input entries |

This combines `rnaseq-nf` with the RAPL measurement method. It **does not reproduce
the original RAPL paper experiment**, whose referenced RNA-seq modules are absent
from that repository. FONDA responsible researcher: [Philipp Thamm](https://fonda.hu-berlin.de/?page_id=2066#PhilippThamm)
for the RAPL method (repository authors Philipp Thamm and Ulf Leser).

The only scientific source edit is Salmon `--libType=U` → `--libType=A` for paired
library detection. Preparation preserves the original file, verifies its SHA-256,
and saves the diff and both hashes on the dedicated PVC. Export retains them
locally. Input downloads are checked against ENA MD5/size and the reference's
checksum and SHA-256. Preparation is outside the measured workflow interval.

## 1. Requirements

Use Python **3.12+**, Bash, `kubectl`, your existing cluster kubeconfig and VPN,
and a VIVO publisher account. All commands below run from the repository root.
The account needs permission to create this run's PVC, ConfigMap, ServiceAccount,
Role, RoleBinding and Jobs in its namespace, and to read its pods/logs and execute
the read-only evidence reader. Node inspection is read-only.

The tested node is **hu-worker-c34**. `--node` accepts only **hu-worker-c34,
hu-worker-c39, hu-worker-c41**, and the selected node must also have
`usedby=prototyping`. Every driver, task and reader stays on that one selected node.
The other two nodes have not been validated for this profile. The monitor refuses
to proceed unless the expected `package-0` and `dram` counters are readable.

The namespace must allow a **read-only** host mount of
`/sys/devices/virtual/powercap`. The monitor runs as root without added
capabilities or privilege escalation; the other containers use UID/GID 57439.
The profile does not install drivers, change node permissions or use a GPU.
If RAPL access is denied, stop and ask the cluster administrator about access;
do not broaden the pod's privileges or switch to another node automatically.

Storage: a fresh **50 GiB CephFS RWX PVC**. Scientific tasks run sequentially with
**2 CPUs, 8 GiB** each. Driver limit: 1 CPU/1536 MiB; monitor: 0.1 CPU/128 MiB.
The workload Job has a four-hour deadline, tasks have a one-hour limit, and no
retries or cleanup are enabled. No higher scheduling priority is requested.
All images and source revisions are pinned in the supplied files.

## 2. Prepare and start a new run

```bash
RUN_ID="rapl-rnaseq-$(date -u +%Y%m%dt%H%M%sz)"
RUN_DIR="$HOME/rapl-runs/$RUN_ID"
NS=yagmur

python3 examples/rnaseq-rapl/run.py prepare "$RUN_DIR" \
  --run-id "$RUN_ID" --namespace "$NS" --node hu-worker-c34

# Inspect the generated files, then submit only these fresh resources.
python3 examples/rnaseq-rapl/run.py start "$RUN_DIR"
kubectl -n "$NS" get pods -l "fonda.hu-berlin.de/run-id=$RUN_ID" -w
```

Press Ctrl-C to stop watching; this does not stop the workflow. `start` uses
`kubectl create`, so existing resources are never updated. It checks that the
chosen node is Ready and labelled for prototyping. The service account cannot
delete or patch pods. No other run's resources are selected or modified.

Use a new run ID, local directory and PVC for each attempt. A failed submission
may leave newly created resources; they are deliberately retained. Do not reuse
or overwrite them. The original rejected `preemptionPolicy: Never` setting is
omitted, matching the successful run on this cluster.

Check completion and driver logs:

```bash
kubectl -n "$NS" get job "$RUN_ID" -o jsonpath='{.status.conditions}'
kubectl -n "$NS" logs "job/$RUN_ID" -c nextflow --tail=30
kubectl -n "$NS" logs "job/$RUN_ID" -c rapl-monitor --tail=20
```

Proceed only when the Job condition is **Complete=True**. `0/2 Completed` is a
normal finished pod display; the collector additionally checks every exit code,
all four tasks, output contents, counter coverage and placement before publication.

## 3. Export and validate the evidence

Create the bounded reader only after successful completion. Its PVC mount is
read-only; it exits after 20 minutes.

```bash
kubectl -n "$NS" create -f "$RUN_DIR/manifests/evidence.job.json"
kubectl -n "$NS" wait --for=condition=Ready pod \
  -l "job-name=$RUN_ID-evidence" --timeout=120s
READER_POD=$(kubectl -n "$NS" get pods -l "job-name=$RUN_ID-evidence" \
  -o jsonpath='{.items[0].metadata.name}')
python3 examples/rnaseq-rapl/run.py capture "$RUN_DIR" --reader-pod "$READER_POD"

python3 collector/collect_rnaseq_rapl_metadata.py \
  "$RUN_DIR/evidence/completed-run" --cluster "$RUN_DIR/evidence/cluster" \
  --output "$RUN_DIR/publication"
```

Optionally add `--backend-uri 'EXISTING_VIVO_BACKEND_RESOURCE_URI'` to the
collector if your VIVO curator supplies a backend link. No private server address
is embedded in this profile. The workflow, researcher, cluster, engine and input
links reuse existing FONDA VIVO resources.

The collector writes `run.ttl`, `validation.json`, `checksums.json` and
`trace-archive.tar.gz` in the new publication directory. It verifies each packaged
file after archiving. An existing output directory is never overwritten.
Kubernetes snapshots and full logs stay local and should be reviewed before any
separate public sharing. Retain the run PVC and local archive; this profile
performs no resource or file deletion.

## 4. Review and publish to VIVO

```bash
# Local validation and review; no upload or credentials needed.
python3 examples/rnaseq-rapl/publish.py "$RUN_DIR/publication"

# Upload the reviewed Turtle; credentials are prompted without saving them.
python3 examples/rnaseq-rapl/publish.py "$RUN_DIR/publication" --publish

# Alternatively use your existing namespace Secret (email/password keys):
# python3 examples/rnaseq-rapl/publish.py "$RUN_DIR/publication" --publish \
#   --credentials-secret vivo-publisher-credentials
```

Use this dedicated collector/publisher path for RAPL, rather than the general
Kepler-based `scripts/publish-run.sh`. The helper uses the repository's shared
VIVO transport, sends only Turtle metadata, and refuses existing run resources.
It adds run links to the existing workflow without replacing its labels or
purpose. It saves a publication attempt, HTTP receipt and page verification.
If the response is uncertain or verification fails, inspect these and the VIVO
page before retrying; the attempt marker deliberately prevents an automatic
second write.

## What the fields mean

- CPU time: `sum(realtime_ms × percent_cpu / 100000)` from the Nextflow TSV.
  Internal `.command.trace` CPU percentages are in tenths; the collector checks
  both representations to prevent a factor-of-ten error.
- Memory: largest observed task peak RSS, in decimal GB; average memory is omitted.
- Energy: cumulative `energy_uj` differences, corrected for wrapping and
  interpolated at execution boundaries, then divided by 1,000,000 for joules.
  Package joules / 3,600,000 gives the VIVO kWh field. DRAM stays separate.
  Samples must cover the whole interval, with no gaps over five seconds. At the
  approximately one-second cadence, the calculation assumes at most one wrap
  per sample interval. The counters include other activity on the shared node;
  no per-task energy, idle subtraction or carbon estimate is asserted.
- Trace types/formats describe **records retained for that run** and appear on
  the run page. No public trace-archive URL is invented; the archive stays local.
- Successful output validation means the expected reports and quantification
  are complete and internally consistent, not that every biological QC flag passes.

The launcher is adapted from the successful run's manifests. The collector has
been replayed against its saved evidence, reproducing the published duration,
CPU time and energy. Repository tests cover counter wrapping, midnight, missing
coverage, CPU units, placement, failed containers and overwrite protection.
