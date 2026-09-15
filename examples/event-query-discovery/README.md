# Event query discovery from Google cluster traces

Profile for the query discovery testbench in
[`kleemeis95/sfb-1404-fonda-querydiscovery-prototype`](https://gitlab.com/kleemeis95/sfb-1404-fonda-querydiscovery-prototype)
on Kubernetes. See a [published example in FONDA VIVO](https://vivo-fonda.hu-berlin.de/vivo/individual?uri=http%3A%2F%2Fexample.org%2Fvivo-import%2Frun-metadata%2Frun%2Fyagmur-event-query-discovery-from-google-cluster-traces-btw23-20260915-2026-09-14t21-17-54-00-00).

The testbench is a plain Python program with no workflow engine. It is run as
one Kubernetes Job per trace sample, and published through the pod-based
collector (`WORKFLOW_ENGINE="snakemake-kubernetes"`, `SNAKEMAKE_PROFILE="eqd"`):
that collector reads tasks from Kubernetes Pods, not from an engine trace, so
it fits any Job-per-task workload. The engine recorded in VIVO is `Python`.

## 1. Configure

```bash
cp examples/event-query-discovery/publisher.env.example config/publisher.env
cp examples/event-query-discovery/input_datasets.json config/input_datasets.json
```

Replace every `REPLACE_ME` value. Store the VIVO credentials:

```bash
./scripts/configure-secrets.sh
```

## 2. Keep the run evidence

Run the testbench as one Job per sample, all Jobs sharing a label selected by
`POD_LABEL_SELECTOR` and named to match `JOB_NAME_REGEX`. Keep the Pods after
completion: the collector reads each Job's start, end and exit code from its
Pod. Each Job writes one directory under `RUN_ROOT` whose name starts with
`EQD_RUN_DIR_PREFIX`:

```text
RUN_ROOT/<prefix>-<sample>/log.txt
RUN_ROOT/<prefix>-<sample>/plots/df_stats_compute_descr_swgquery_multidim
RUN_ROOT/<prefix>-<sample>/provenance/git-commit.txt
RUN_ROOT/<prefix>-<sample>/provenance/requirements.lock.txt
RUN_ROOT/source                       # checkout of the upstream commit
```

A directory whose log never reached `Simulation finished` belongs to a stopped
attempt; it is reported as superseded and its rows are not counted.

The upstream testbench writes its statistics CSV only when every discovery is
done, so a Job stopped by its deadline loses all of its work. The published run
applied a small runtime patch that checkpoints the CSV after each discovery,
guards plotting so a plot failure cannot discard the CSV, and lets a Job limit
itself to one sample. The patch is copied into each `provenance/` directory.

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
`RUN_ROOT/vivo-outbox`.

## 5. Remove a publication

Use the publication ID from the `.published.json` filename:

```bash
./scripts/remove-run.sh PUBLICATION_ID --dry-run
./scripts/remove-run.sh PUBLICATION_ID
```

The second command asks for confirmation and removes only that published run's
metadata from VIVO.

## Notes

The discovery cost is dominated by the `right_to_left` position strategy on
the largest sample: it took hours per discovery where the other strategies took
seconds to minutes. The published run excludes it for that one sample and keeps
the full strategy grid for the other two; the exclusion is recorded in the
sample's provenance directory.

No application domain is set, because none of the existing VIVO domains
describes event query discovery over cluster traces.
