# Archive a run's traces in HU-Box

Optional. Uploads the trace files of one published run to HU-Box and adds the
public download link to the run's VIVO page ("trace archive").

Requires a run that is already published with
[Collect and publish a run](COLLECT_AND_PUBLISH.md).

Run everything on the login node. Start each session with:

```bash
export WORK=/lustre/GROUP/USER/fonda
module load python/3.12.9-gcc14.2.0
cd "$WORK/fonda-kubernetes-vivo-publisher"
```

## 1. Check that the cluster reaches HU-Box

```bash
curl -s https://box.hu-berlin.de/api2/ping/; echo
```

Must print `"pong"`.

## 2. Set a separate HU-Box password (once)

In the HU-Box web interface open the account settings, find **WebDAV Access**
and set a WebDAV password. Do not use the main HU account password.

## 3. Configure HU-Box (once)

```bash
./scripts/configure-hu-box.sh
```

Answer the prompts:

| Prompt | Answer |
|---|---|
| HU-Box username | your HU-Box account name, normally the HU email address |
| HU-Box password | the WebDAV password from step 2 (not displayed) |
| Two-factor code | the current code, or Return if unused |
| Destination library | the number of the library, normally `My Library` |
| Parent directory | Return (`/`) |
| Trace directory prefix | for example `fonda-workflow-traces/hpc-at-hu` |

The script stores an access token in `~/.config/fonda/hu-box-api-token` and
the settings in `config/hu-box.env`. Both are private and ignored by Git.

## 4. Package and review

```bash
examples/hpc-at-hu-slurm/archive-slurm-job.sh JOB_ID --package-only
```

Nothing is uploaded. The command prints the bundle directory. Review it:

```bash
BUNDLE="$(ls -dt ~/vivo-evidence/JOB_ID/trace-archive-*/bundle | head -1)"
find "$BUNDLE" -type f | sort
cat "$BUNDLE/PRIVACY-SCAN.txt"
```

The bundle contains:

| Directory | Files |
|---|---|
| `slurm/` | Slurm accounting, node hardware, node CPU and power samples, the job's console output |
| `nextflow/` | Nextflow log, task trace, report, timeline, DAG, parameters, software versions |
| `vivo/` | the published Turtle, the collection summary, the publication receipt |

Scientific result data are not included.

The archive will be public. The Nextflow log and the console output contain
your user name, node names and file paths. Read them before uploading. The
automatic scan only looks for values shaped like passwords or tokens; if it
reports lines, the upload stops until you have checked them.

## 5. Upload and add the link to VIVO

```bash
examples/hpc-at-hu-slurm/archive-slurm-job.sh JOB_ID
```

Expected at the end:

```text
Public HU-Box trace link: https://box.hu-berlin.de/f/...
HTTP 200
VIVO page: https://vivo-fonda.hu-berlin.de/vivo/individual?uri=...
Archived job JOB_ID and added its trace link to VIVO.
```

The run's metadata is not collected again: the published record is reused
and only the link is added.

## 6. Verify

1. Open the `Public HU-Box trace link` in a private browser window. The
   archive must download without a login.
2. Open the `VIVO page` link. **trace archive** must show the HU-Box link.

Moving, deleting or unsharing the file in HU-Box breaks the link in VIVO.

## Options

| Option | Effect |
|---|---|
| `--package-only` | build and check the bundle; no upload, VIVO unchanged |
| `--no-vivo` | upload and share; VIVO unchanged. `publish-slurm-job.sh JOB_ID` adds the link later |
| `--allow-privacy-findings` | continue after you have confirmed every reported line is harmless |

The link is saved in `~/vivo-evidence/JOB_ID/trace-archive-url.txt`, so
publishing the same job again keeps it.
