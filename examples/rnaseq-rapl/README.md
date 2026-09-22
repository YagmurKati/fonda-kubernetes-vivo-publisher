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

python3 collector/collect_rnaseq_rapl_metadata.py \
  "$RUN_DIR/evidence/completed-run" --cluster "$RUN_DIR/evidence/cluster" \
  --output "$RUN_DIR/publication"
```

The collector checks task completion, outputs, node placement and RAPL coverage.
It writes `run.ttl`, `validation.json`, `checksums.json` and
`trace-archive.tar.gz` to the publication directory.

Review the metadata before publishing:

```bash
python3 examples/rnaseq-rapl/publish.py "$RUN_DIR/publication"
```

## 4. Publish

```bash
python3 examples/rnaseq-rapl/publish.py "$RUN_DIR/publication" --publish
```

Enter your VIVO publisher credentials when prompted, or add
`--credentials-secret vivo-publisher-credentials` to use an existing namespace
Secret. The command uploads the Turtle, saves a receipt and prints the VIVO link.
If publication fails, check the receipt and VIVO page before retrying.

## Notes

- RAPL measures **whole-node energy**, including other activity. CPU-package
  energy is published in kWh; DRAM is reported separately. No carbon estimate
  or average memory value is added.
- Trace types and formats describe the collected run records. The trace archive
  stays local, so no public archive URL is assigned.
- Sources and images are pinned. Salmon uses `--libType=A` for library detection;
  the original file, source diff and input checksums are retained with the evidence.
