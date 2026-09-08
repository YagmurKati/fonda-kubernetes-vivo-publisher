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

Keep `results/COMPLETED`, `results/run.log`, `results/record-count.txt`,
`results/output.sha256`, `results/flagstat.txt`, `results/snakemake-stats.json`,
`results/compatibility.patch`, the source checkout including detached `.git/HEAD`,
and `data/MG3/mapped_reads/all_sorted.sam`. The adapter verifies the actual SAM
checksum and record count, the pinned workflow revision, and the Snakemake
version against the installation log. Retain all workflow-attempt pods until
collection finishes. The profile targets the documented pinned small-data run;
change and validate its evidence reader for other revisions or datasets.

This execution uses 64 bins, four haplotypes, 128000 single-end 150-base reads,
three errors per read, and a 1 GB IBF. Snakemake runs inside one eight-core
Kubernetes pod. The source simulation script does not apply `mix_bins`.
Historical cached dependency revisions are declared in the audit; their earlier
compilation cost is excluded. All seven execution attempts are included, so
status is **Succeeded with warnings**. Session duration includes gaps between
attempts and is not the final mapping duration.

The checked-in TTL and receipt record the already completed publication.
Do not republish the historical run merely to install this profile. The receipt
is retained on its original PVC under `vivo-outbox/a2-mg3-20260908.published.json`.
For new runs the standard wrapper writes timestamped artifacts and guards
against duplicate publication receipts.

Resource measurements are recorded in the published example. Carbon uses an
explicitly labelled Electricity Maps collection-time proxy.

## 5. Remove a publication

```bash
./scripts/remove-run.sh PUBLICATION_ID --dry-run
./scripts/remove-run.sh PUBLICATION_ID
```

The historical publication ID is `a2-mg3-20260908`. Removal uses its exact
receipt and asks for confirmation.
