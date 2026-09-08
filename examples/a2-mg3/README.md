# A2 MG-3

Profile for the small simulated-data MG-3 Snakemake workflow from
[CRC-FONDA/A2-metagenome-snakemake](https://github.com/CRC-FONDA/A2-metagenome-snakemake).
[published example in FONDA VIVO](https://vivo-fonda.hu-berlin.de/vivo/individual?uri=http%3A%2F%2Fexample.org%2Fvivo-import%2Frun-metadata%2Frun%2Fyagmur-metagenomic-read-mapping-across-computational-architectures-a2-mg3-20260908-2026-09-08t06-34-48-00-00).
The [reproduction repository](https://github.com/YagmurKati/a2-mg3-reproduction-example)
contains the runner and compatibility fixes (private, like the MG-4 example).

## Configure

```bash
cp examples/a2-mg3/publisher.env.example config/publisher.env
cp examples/a2-mg3/input_datasets.json config/input_datasets.json
```

Replace every `REPLACE_ME`. `RUN_ROOT` is the PVC root as mounted in the
publisher pod (`/workspace` for this run); `CODE_PATH` is `/workspace/source`.
Use `WORKFLOW_ENGINE=snakemake-kubernetes` and `SNAKEMAKE_PROFILE=mg3`.
New runs should carry `fonda.hu-berlin.de/run-id=RUN_ID` on their workflow pods.
For the recorded legacy run use `FALLBACK_RUN_ID=a2-mg3-20260908`,
`POD_LABEL_SELECTOR=batch.kubernetes.io/job-name` and
`JOB_NAME_REGEX=a2-mg3-run-20260908(?:-v[2-7])?`.
The tested PVC is `a2-mg3-run-20260908` in namespace `yagmur`.

```bash
./scripts/configure-secrets.sh
./scripts/publish-run.sh RUN_ID --dry-run
./scripts/publish-run.sh RUN_ID
```

## Evidence and scope

The [reproduction runner](https://github.com/YagmurKati/a2-mg3-reproduction-example)
now separates reusable launch scripts from the verified run from 8 September 2026.
For a new run, its dedicated PVC is mounted at `/workspace` by this publisher;
use the same run ID that was supplied to the runner. The default selector is
`app.kubernetes.io/name=a2-mg3`, and its pod run-id label selects the correct run.

Keep `results/COMPLETED`, `results/record-count.txt`, `results/output.sha256`,
`results/flagstat.txt`, `results/snakemake-stats.json`,
`results/compatibility.patch`, the source checkout including detached `.git/HEAD`,
and `data/MG3/mapped_reads/all_sorted.sam`. New runs also write
`results/provenance.json` and `results/snakemake-version.txt`.

The version-1 provenance manifest contains `run_id`, `workflow_commit`,
`snakemake`, `snakemake_cores`, `simulator_commit`, `dream_yara_commit`,
`dependency_mode` (`built` or `cache`), `dependency_provenance_scope`, and a
non-empty `tool_sha256` mapping. Additional fields are retained in the audit.
The collector compares the source revision and Snakemake version with their
independent files, verifies the actual SAM checksum/count, and matches the
completion marker to a successful selected workflow pod. The run ID in the
manifest must equal the requested ID.

The historical run lacks this runtime manifest. Its compatibility path checks
the pinned detached revision and the successful Snakemake installation log.
It does not invent dependency revisions or core counts absent from that legacy
evidence. The exact earlier published record remains unchanged in this profile.

Descriptions use actual counts and recorded provenance instead of copying the
historical dataset size or eight-core setting into every new run. All selected
workflow-attempt pods are included in resource accounting. Tools built within
those pods are included; a declared external cache excludes its prior build.
Retain all workflow pods until collection finishes.

The checked-in TTL and receipt record the already completed publication.
Do not republish the historical run merely to install this profile. The receipt
is retained on its original PVC under `vivo-outbox/a2-mg3-20260908.published.json`.
The standard wrapper guards both the historical plain receipt and new
timestamped receipts against accidental repeat publication.

Resource measurements are recorded in the published example. Carbon uses an
explicitly labelled Electricity Maps collection-time proxy.

## 5. Remove a publication

```bash
./scripts/remove-run.sh PUBLICATION_ID --dry-run
./scripts/remove-run.sh PUBLICATION_ID
```

The historical publication ID is `a2-mg3-20260908`. Removal uses its exact
receipt and asks for confirmation.
