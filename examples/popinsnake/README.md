# PopinSnake

Profile for the PopinSnake Snakemake workflow, which detects and genotypes DNA
insertions. Two sources have been published with this profile: the FONDA A6
revision in
[`gitlab.informatik.hu-berlin.de/fonda_a6/popinSnake`](https://gitlab.informatik.hu-berlin.de/fonda_a6/popinSnake)
and the upstream revision in
[`github.com/kehrlab/PopinSnake`](https://github.com/kehrlab/PopinSnake).

Each published example in FONDA VIVO below uses the same three example samples:

| Run | Source | Shape |
| --- | --- | --- |
| [2026-08-28](https://vivo-fonda.hu-berlin.de/vivo/individual?uri=http%3A%2F%2Fexample.org%2Fvivo-import%2Frun-metadata%2Frun%2Fyagmur-popinsnake-exploratory-workflow-for-genomic-insertion-detection-popinsnake-example-20260828-02-2026-08-28t08-03-05-00-00) | GitLab `359d941` | resumable session, six attempts |
| [2026-09-18 (GitLab)](https://vivo-fonda.hu-berlin.de/vivo/individual?uri=http%3A%2F%2Fexample.org%2Fvivo-import%2Frun-metadata%2Frun%2Fyagmur-popinsnake-exploratory-workflow-for-genomic-insertion-detection-popinsnake-gl-359d941-20260918-2026-09-18t19-57-50-00-00) | GitLab `359d941` | single timed run |
| [2026-09-18 (GitHub)](https://vivo-fonda.hu-berlin.de/vivo/individual?uri=http%3A%2F%2Fexample.org%2Fvivo-import%2Frun-metadata%2Frun%2Fyagmur-popinsnake-exploratory-workflow-for-genomic-insertion-detection-popinsnake-gh-dc940de-20260918-2026-09-18t15-37-14-00-00) | GitHub `dc940de` | single timed run |

## What the published duration measures

The collector derives a run's duration from the first container start to the
last container completion across **every Pod carrying the run's
`fonda.hu-berlin.de/run-id` label**. If the build, the environment creation and
several restarted attempts all carry that label, the published duration spans
all of them, including any idle time between attempts. The 2026-08-28 example
above reports 30,701 s and the first GitHub reproduction reported 93,129 s for
this reason; the workflow itself takes about ten minutes.

To publish the workflow's own cost, split the work into two Kubernetes Jobs:

- a **preparation** Job that clones or copies the source, builds the tools, and
  creates every rule environment with `snakemake --conda-create-envs-only`.
  Give it any label you like **except** `fonda.hu-berlin.de/run-id`, so the
  collector ignores it. Record its cost in `provenance/` if you want it kept.
- a **run** Job, labelled `fonda.hu-berlin.de/run-id=RUN_ID`, that only invokes
  Snakemake. Its Pod lifetime is then the workflow's execution time.

Set `JOB_NAME_REGEX` to match the run Job alone. Publishing the whole session
instead is a legitimate choice — it is the cost of reproducing the run from
nothing — but state which one you meant, because the two differ by a factor of
tens.

## 1. Configure

```bash
cp examples/popinsnake/publisher.env.example config/popinsnake.publisher.env
cp examples/popinsnake/input_datasets.json config/input_datasets.json
```

Replace every `REPLACE_ME` value. Set `RUN_ROOT` to the run directory on the
mounted PVC, and `WORKFLOW_REPO_URL` to the repository the run's commit
actually belongs to, so `rm:codeCommitLink` resolves. `CODE_URI` describes the
workflow rather than the run, so leave it alone when adding a run to an
existing workflow record.

Store the VIVO credentials:

```bash
CONFIG_FILE=config/popinsnake.publisher.env ./scripts/configure-secrets.sh
```

## 2. Keep the run evidence

Keep `RUN_STATUS` (which must read `COMPLETED`), the provenance directory, the
checksums, the final compressed VCF, and the Pods labelled with the run id
available until metadata collection finishes.

`provenance/result-SHA256SUMS` is looked up by path suffix, so its entry for the
final VCF must end in `/results/insertions_genotypes.vcf.gz`. Generate it with
absolute paths:

```bash
find "$RUN_ROOT/results" -maxdepth 1 -type f -print0 | sort -z | xargs -0 -r sha256sum \
  > "$RUN_ROOT/provenance/result-SHA256SUMS"
```

A manifest written with relative paths is rejected with
"Could not identify the SHA-256".

## 3. Validate

```bash
./scripts/collect-and-publish-popinsnake.sh RUN_ID --dry-run
```

## 4. Publish

```bash
./scripts/collect-and-publish-popinsnake.sh RUN_ID
```

Open the [FONDA VIVO Runs page](https://vivo-fonda.hu-berlin.de/vivo/runs) and
check the new record. The TTL, metrics audit, and receipt are stored under
`RUN_ROOT/vivo-outbox`.

## 5. Remove a publication

Use the publication ID from the `.published.json` filename:

```bash
CONFIG_FILE=config/popinsnake.publisher.env \
  ./scripts/remove-run.sh PUBLICATION_ID --dry-run
CONFIG_FILE=config/popinsnake.publisher.env \
  ./scripts/remove-run.sh PUBLICATION_ID
```

The second command asks for confirmation and removes only that published run's
metadata from VIVO.

## Reproducibility note

PopinSnake is not deterministic between runs. Three replicates of each revision
on identical inputs, with identical environments, gave:

| Revision | Duration (s) | Insertion records |
| --- | --- | --- |
| GitLab `359d941` | 584, 596, 572 | 380, 378, 380 |
| GitHub `dc940de` | 606, 597, 585 | 379, 382, 377 |

Both revisions average 379.3 records, and the difference in mean duration is
smaller than the spread within either revision. Contig identifiers are assigned
in a thread-dependent order, which shifts the inserted sequences in the VCF and
the contents of `locations.txt` between runs even when the assembly content is
unchanged. Compare revisions using replicates, not single runs.
