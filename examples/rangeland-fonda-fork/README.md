# nf-core/rangeland (FONDA fork)

Profile for
[`CRC-FONDA/nf-core-rangeland`](https://github.com/CRC-FONDA/nf-core-rangeland),
the FONDA-maintained fork of
[`nf-core/rangeland`](https://github.com/nf-core/rangeland).

This is the same workflow as the [nf-core/rangeland
profile](../rangeland-nfcore/README.md), run from a different code lineage: the
upstream profile runs release `1.0.0` at commit `7c5cb959`, this one the fork at
`bbb3da8d`, version `1.1.0dev`.

Both publish against the **same** workflow record in VIVO. A workflow record
names the pipeline, not one revision of it; which code a given execution used is
carried on the run through `CODE_URI` and `GIT_COMMIT`. The PopinSnake profile
records three revisions this way. Giving a revision its own workflow record
splits one pipeline's history across several pages for no gain.

## 1. Configure

```bash
cp examples/rangeland-fonda-fork/publisher.env.example config/publisher.env
cp examples/rangeland-fonda-fork/input_datasets.json config/input_datasets.json
```

Replace every `REPLACE_ME` value and confirm the trace, log and code paths.
Note that `CODE_PATH` follows `NXF_HOME`: if the run sets
`NXF_HOME=/workspace/nextflow-home`, the fetched pipeline is at
`/workspace/nextflow-home/assets/CRC-FONDA/nf-core-rangeland`, not under the
default `.nextflow/assets`.

`DECLARED_CONTAINER_IMAGES` needs the digests the run pulled. The pipeline
declares its images by tag only, so read them back from the task pods:

```bash
kubectl -n NAMESPACE get pods -l fonda.hu-berlin.de/run-id=RUN_ID \
  -o jsonpath='{range .items[*]}{.status.containerStatuses[*].imageID}{"\n"}{end}' \
  | sort -u
```

This works only while the task pods still exist. Set `k8s.cleanup = false` in
the run configuration, otherwise Nextflow deletes successful task pods and the
digests are lost.

Store the VIVO credentials:

```bash
./scripts/configure-secrets.sh
```

## 2. Keep the run evidence

The profile expects:

```text
/workspace/results/RUN_ID/trace-RUN_ID.txt
/workspace/results/RUN_ID/nextflow-RUN_ID.log
/workspace/results/RUN_ID/nextflow-debug-RUN_ID.log
CODE_PATH
```

Keep the Kubernetes Pod name in the trace `native_id` field, and include
`start` and `complete` in `trace.fields` so the collector records measured task
timings rather than deriving them from `submit`, `duration` and `realtime`.

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
