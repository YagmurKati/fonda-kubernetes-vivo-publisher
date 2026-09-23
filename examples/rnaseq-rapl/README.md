# RNA-seq with RAPL energy measurement

Profile for [`nextflow-io/rnaseq-nf`](https://github.com/nextflow-io/rnaseq-nf/tree/5c89d3859abbe54893d4e1ae0f21115dcebd9d1d)
with energy collection adapted from
[`CRC-FONDA/RAPL_measurement_workflows`](https://github.com/CRC-FONDA/RAPL_measurement_workflows/tree/8786ab77fe4761fefb150957050d862c02c3dde8).
It runs FastQC, Salmon and MultiQC on the full **SRR16287545** paired-end sample
using the Ensembl 106 Drosophila cDNA reference.

See the [published example in FONDA VIVO](https://vivo-fonda.hu-berlin.de/vivo/individual?uri=http%3A%2F%2Fexample.org%2Fvivo-import%2Frun-metadata%2Frun%2Ffonda-rnaseq-rapl-srr16287545-20260922-074112)
and [publication summary](publication-summary.json). FONDA responsible researcher
for the RAPL method: [Philipp Thamm](https://fonda.hu-berlin.de/?page_id=2066#PhilippThamm).
This profile uses the RAPL measurement method; it does not reproduce the paper's
original experiment.

## 1. Configure

Use Python 3.12+, Bash, `kubectl`, cluster access and a VIVO publisher account.
Run the commands below from the repository root, in the same terminal.

The profile requires a fresh **50 GiB CephFS PVC** and read-only access to
`/sys/devices/virtual/powercap`. Tasks run sequentially with **2 CPUs and 8 GiB**
each. All pods stay on the selected node, which must have `usedby=prototyping`.
Allowed nodes are `hu-worker-c34`, `hu-worker-c39` and `hu-worker-c41`;
`hu-worker-c34` is the tested default.

```bash
RUN_ID="rapl-rnaseq-$(date -u +%Y%m%dt%H%M%sz)"
RUN_DIR="$HOME/rapl-runs/$RUN_ID"
NS=yagmur

python3 examples/rnaseq-rapl/run.py prepare "$RUN_DIR" \
  --run-id "$RUN_ID" --namespace "$NS" --node hu-worker-c34
```

## 2. Run

```bash
python3 examples/rnaseq-rapl/run.py start "$RUN_DIR"
kubectl -n "$NS" wait --for=condition=complete "job/$RUN_ID" --timeout=4h
```

Continue only after the Job completes successfully. Keep its pods and PVC for
collection. Use a new run ID and directory for each attempt.

## 3. Collect and validate

Create a read-only reader and export the run's outputs, logs and counters:

```bash
kubectl -n "$NS" create -f "$RUN_DIR/manifests/evidence.job.json"
kubectl -n "$NS" wait --for=condition=Ready pod \
  -l "job-name=$RUN_ID-evidence" --timeout=120s
READER_POD=$(kubectl -n "$NS" get pods -l "job-name=$RUN_ID-evidence" \
  -o jsonpath='{.items[0].metadata.name}')
python3 examples/rnaseq-rapl/run.py capture "$RUN_DIR" --reader-pod "$READER_POD"
```

Collect the metadata and check it without uploading:

```bash
./scripts/collect-and-publish-rnaseq-rapl.sh "$RUN_DIR" --dry-run
```

The collector validates the run, fetches hourly carbon intensity for its execution
period, and calculates emissions from the measured energy in each hour. It uses
Germany data from Electricity Maps, then CO₂Map if matching data is unavailable.
The existing `electricity-maps-api-token` namespace Secret is read automatically;
`ELECTRICITY_MAPS_API_TOKEN` can also supply the token.

If no source covers the complete run, collection stops and saves the reason.
Retry the command when matching data becomes available; keep the run evidence.
Annual averages and values from a different time are never substituted.

## 4. Publish

```bash
./scripts/collect-and-publish-rnaseq-rapl.sh "$RUN_DIR"
```

This command collects, calculates and publishes the metadata. Enter your VIVO
publisher credentials when prompted, or set
`VIVO_CREDENTIALS_SECRET=vivo-publisher-credentials` to use the existing Secret.
It saves the Turtle, carbon source data, trace archive, validation and receipt in
a new publication directory and prints the VIVO link.

## Notes

- RAPL measures **whole-node energy**, including other activity. CPU-package
  energy and its calculated emissions are published; DRAM is reported separately.
  Electricity Maps supplies lifecycle CO₂e; CO₂Map supplies direct CO₂. The source,
  emissions basis and time coverage are recorded. Average memory is omitted.
- Trace types and formats describe the collected run records. The trace archive
  stays local, so no public archive URL is assigned.
- Sources and images are pinned. Salmon uses `--libType=A` for library detection;
  the original file, source diff and input checksums are retained with the evidence.
