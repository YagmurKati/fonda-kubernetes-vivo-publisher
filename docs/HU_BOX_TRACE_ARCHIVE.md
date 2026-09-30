# HU-Box trace archive and VIVO link

This procedure preserves the raw execution evidence for **a selected run** in
HU-Box and adds the resulting public download link to that run's FONDA VIVO
page. Normal VIVO publication stores searchable metadata but
does not upload the raw Nextflow trace, logs, report, timeline, or DAG.

It is not recommended to run the archive command for every execution. Run it only for traces that
have been selected for long-term preservation.

The end-to-end command currently supports Nextflow profiles whose evidence is
retained on the configured Kubernetes PVC. The final section explains the
fallback for other workflow engines.

## What the command does

For one `RUN_ID`, `archive-publish-run.sh`:

1. creates a temporary Kubernetes reader Pod on `usedby=<NODE_USEDBY>`;
2. mounts the configured workflow PVC read-only;
3. copies only the selected run's available trace, console/debug logs, report,
   timeline, DAG, parameters, software versions, VIVO TTL, metrics audit, and
   publication receipt;
4. writes `MANIFEST.json`, `SHA256SUMS`, and `PRIVACY-SCAN.txt`;
5. creates a compressed archive and a checksum on the local computer;
6. uploads the archive to the selected HU-Box library;
7. creates a public, download-only HU-Box share link;
8. re-collects and replaces only that run's VIVO record with the exact archive
   link; and
9. removes the temporary reader Pod.

It does not rerun the scientific workflow, write to its PVC, upload scientific
result data, change another run, or add a trace link to the workflow-name page.

## Prerequisites

Complete these before starting:

- The workflow run has finished and has already been published successfully to
  VIVO with `scripts/publish-run.sh`.
- Its evidence and matching `.published.json` receipt are still on the PVC.
- Your current Kubernetes context can access your FONDA namespace, PVC, and
  service account.
- `config/publisher.env` is the same working configuration used to publish the
  run. Do not start with an unrelated profile.
- The publisher code and configuration have been deployed with
  `scripts/deploy.sh`.
- You have a HU-Box account and permission to write to the selected library.
- Your workstation has `curl`, `kubectl`, `python3`, `sed`, `shasum`, and `tar`.

Run all commands from the repository root:

```bash
git clone https://github.com/YagmurKati/fonda-kubernetes-vivo-publisher.git
cd fonda-kubernetes-vivo-publisher
```

For an existing checkout, preserve your private `config/*.env` files and update
the code with the normal Git workflow used by your project.

## Step 1: Confirm the publisher configuration

The archive command deliberately refuses to guess the workflow configuration.
Confirm that the private file exists:

```bash
test -r config/publisher.env && echo "publisher configuration found"
```

If it is missing, copy the example for your workflow and replace every
`REPLACE_ME` value as described in the workflow profile. Reuse the exact
namespace, PVC, service account, workflow URI, evidence paths, input metadata,
and VIVO settings used for the original publication.

For example only:

```bash
cp examples/rangeland-nfcore/publisher.env.example config/publisher.env
cp examples/rangeland-nfcore/input_datasets.json config/input_datasets.json
```

Do not overwrite a working `publisher.env` with the example. For automatic
archival, `WORKFLOW_ENGINE` must be `nextflow`. Each configured evidence path
must be a normalized absolute path below `/workspace`, which is the read-only
mount inside the temporary reader Pod.

Confirm access without printing any credential values:

```bash
source config/publisher.env
kubectl -n "$NS" get pvc "$PVC_NAME"
kubectl -n "$NS" get serviceaccount "$SERVICE_ACCOUNT"
kubectl -n "$NS" get secret "${VIVO_CREDENTIALS_SECRET:-fonda-vivo-credentials}"
```

If this checkout has not been deployed since its configuration or publisher
code changed, run:

```bash
./scripts/deploy.sh
```

Deployment does not run a workflow or publish a VIVO record.

## Step 2: Choose one run

Copy the exact run ID used during workflow execution and VIVO publication:

```bash
RUN_ID="my-run-01"
```

Do not use a workflow title, VIVO URI, Kubernetes Job name, or a different run
ID. The selected run must have a publication receipt on the PVC. If it has not
been published yet, publish and verify it first:

```bash
./scripts/publish-run.sh "$RUN_ID"
```

## Step 3: Set a separate HU-Box password

In the HU-Box web interface, open the account settings and find **WebDAV
Access**. If it says `WebDAV password: not set`, create a separate HU-Box/WebDAV
password. Do not use, paste, or share the primary HU account password.

The password is entered only into the hidden terminal prompt in the next step.
Do not place it in `publisher.env`, `hu-box.env`, a command line, Git, an issue,
or a support message.

## Step 4: Configure HU-Box once

Run:

```bash
./scripts/configure-hu-box.sh
```

Answer the prompts in this order:

1. **HU-Box username:** enter the HU-Box account name, normally the HU email
   address.
2. **HU-Box password:** enter the separate HU-Box/WebDAV password. It is not
   displayed.
3. **Optional two-factor code:** enter the current code only when two-factor
   authentication is enabled; otherwise press Return.
4. **Destination library:** enter the number printed beside the intended
   library. Use `My Library` unless an authorized FONDA team library has been
   agreed. Never select another group's library merely because it appears in
   the list.
5. **Parent directory:** `/` is the safest default and always exists. A
   non-root value must begin with `/` and must already exist in that library.
6. **Trace directory prefix:** enter a relative, workflow-specific path such as
   `fonda-workflow-traces/my-workflow`. Do not start it with `/` and do not use
   `..`.

With parent `/`, prefix `fonda-workflow-traces/my-workflow`, and run ID
`my-run-01`, the archive is stored below:

```text
/fonda-workflow-traces/my-workflow/my-run-01/
```

Successful setup reports these private files:

```text
~/.config/fonda/hu-box-api-token
config/hu-box.env
```

Both are written with owner-only permissions, and repository configuration
files are ignored by Git. Never commit, print, or send the token. Rerun
`configure-hu-box.sh` to select another authorized library/path or to replace
an expired or revoked token.

## Step 5: Package and review before uploading

First create a local bundle without contacting HU-Box or changing VIVO:

```bash
./scripts/archive-publish-run.sh "$RUN_ID" --package-only
```

The source PVC is mounted read-only. The output is written below:

```text
artifacts/trace-archives/<RUN_ID>/<UTC timestamp>/
```

Locate the newest package and inspect it:

```bash
ARTIFACT_DIR="$(find "artifacts/trace-archives/$RUN_ID" \
  -mindepth 1 -maxdepth 1 -type d -print | sort | tail -n 1)"
printf 'Reviewing: %s\n' "$ARTIFACT_DIR"
find "$ARTIFACT_DIR/bundle" -type f -print | sort
cat "$ARTIFACT_DIR/bundle/PRIVACY-SCAN.txt"
(cd "$ARTIFACT_DIR/bundle" && shasum -a 256 -c SHA256SUMS)
tar -tzf "$ARTIFACT_DIR"/*.tar.gz
```

Review the actual trace and logs as well as the automated scan. Check for
passwords, tokens, private URLs, personal data, unnecessary absolute paths, or
confidential scientific data. The scanner detects credential-shaped values;
it cannot decide whether all content is suitable for public release.

If the scan reports a real secret or sensitive value, do not upload the
bundle. Correct the source/configuration or prepare an approved sanitized
archive. Use `--allow-privacy-findings` only after confirming every reported
item is a harmless false positive.

## Step 6: Upload and update VIVO

After the review, run the end-to-end command:

```bash
./scripts/archive-publish-run.sh "$RUN_ID"
```

For reviewed false positives only:

```bash
./scripts/archive-publish-run.sh "$RUN_ID" --allow-privacy-findings
```

The command creates a fresh timestamped bundle, uploads it, checks that the
public link is reachable, and runs a forced replacement publication for the
same run identity. It does not create a second VIVO run. Because publication
re-collects the retained evidence, review any profile that uses a changing
external source before proceeding.

Success ends with output similar to:

```text
Public HU-Box trace link: https://box.hu-berlin.de/...
Archived and republished run my-run-01 with its exact trace link.
```

Keep this output until verification is complete.

## Step 7: Verify HU-Box and VIVO

1. Open the printed HU-Box link in a private browser window and confirm the
   archive downloads without authentication.
2. In HU-Box, confirm the archive is under the selected library, prefix, and
   run-ID directory.
3. Open the selected run on the
   [FONDA VIVO Runs page](https://vivo-fonda.hu-berlin.de/vivo/runs).
4. Open its **Traces** or **View All** tab and confirm that **trace archive**
   points to the exact HU-Box bundle.
5. Confirm that the workflow-name page was not given this run-specific link and
   that unrelated run pages were unchanged.

The VIVO page stores the link and extracted metadata, not the archive bytes.
Moving, deleting, or unsharing the HU-Box file will break the VIVO link.

## Optional modes

Create and review a local bundle only:

```bash
./scripts/archive-publish-run.sh "$RUN_ID" --package-only
```

Upload and create a public HU-Box link without changing VIVO:

```bash
./scripts/archive-publish-run.sh "$RUN_ID" --no-vivo
```

After `--no-vivo`, attach the printed URL later with:

```bash
./scripts/publish-run.sh "$RUN_ID" \
  --run-trace-archive "https://box.hu-berlin.de/REPLACE_WITH_EXACT_LINK"
```

`WORKFLOW_TRACE_REPOSITORY` has a different purpose: it may identify one
collection or repository page that applies to the workflow as a whole.
`--run-trace-archive` identifies the exact evidence bundle for one execution.
Do not put one run's bundle on the workflow-name page, and do not set
`RUN_TRACE_ARCHIVE` globally unless every publication should intentionally use
the same URL.

## Troubleshooting and safe retry rules

### `Missing .../config/publisher.env`

Restore or copy the exact working profile as described in Step 1. Do not invent
PVC paths or use another workflow's configuration.

### Run directory or evidence file is rejected or missing

Update to the current repository version. Confirm that the configured paths are
normalized absolute paths below `/workspace` and point to retained files for
the selected run. Do not move or delete another user's PVC content.

### No publication receipt is found

Publish the run normally first. The receipt proves which VIVO publication and
TTL belong in the archive.

### HU-Box authentication returns 401/403

Confirm the separate HU-Box/WebDAV password and any two-factor code, then rerun
`configure-hu-box.sh`. Do not substitute the primary HU account password.

### HU-Box rejects the parent directory

Rerun `configure-hu-box.sh`, select the same authorized library, use `/` as the
parent, and put the desired hierarchy in the relative trace prefix.

### Privacy scan stops publication

Read `PRIVACY-SCAN.txt` and inspect the named files. Do not bypass a real
finding. The local bundle is retained for review; HU-Box and VIVO are unchanged.

### Upload succeeds but VIVO publication fails

Do not upload another copy immediately. Copy the already printed `Public
HU-Box trace link` and retry only the VIVO step:

```bash
./scripts/publish-run.sh "$RUN_ID" \
  --run-trace-archive "PASTE_THE_PRINTED_HU_BOX_LINK"
```

### The public link was moved, revoked, or deleted

Create a new share link and republish the same run with
`--run-trace-archive`. VIVO cannot preserve or recover HU-Box files.

## Other workflow engines

The automatic PVC packager currently supports Nextflow. For another engine,
use that profile's documented evidence package, upload the reviewed archive to
an approved repository, create a public download-only URL, and attach the exact
URL to one run with:

```bash
./scripts/publish-run.sh "$RUN_ID" --run-trace-archive "$PUBLIC_URL"
```

Do not claim an archive is complete unless it retains the engine's execution
log and enough workflow/task structure to interpret its resource and energy
measurements.
