#!/usr/bin/env bash
# Archive the trace files of one published HPC@HU Slurm run in HU-Box and add
# the public download link to the run's VIVO page. Run on the login node.
#
# Usage: archive-slurm-job.sh JOB_ID [--package-only] [--shared-folder] [--no-vivo] [--allow-privacy-findings]
#
#   --package-only            build and check the bundle; no upload, VIVO unchanged
#   --shared-folder           upload to the shared FONDA folder (no HU-Box account needed);
#                             its owner makes the archive public and adds the link to VIVO
#   --no-vivo                 upload and share; VIVO unchanged
#   --allow-privacy-findings  continue although the privacy scan reported lines
#
# The run must already be published with publish-slurm-job.sh. Its metadata is
# not collected again: the published Turtle is reused and only the link is added.
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

JOB_ID="${1:-}"
shift || true
package_only=0
shared_folder=0
no_vivo=0
allow_privacy_findings=0
usage="Usage: $0 JOB_ID [--package-only] [--shared-folder] [--no-vivo] [--allow-privacy-findings]"
while (($#)); do
  case "$1" in
    --package-only) package_only=1 ;;
    --shared-folder) shared_folder=1 ;;
    --no-vivo) no_vivo=1 ;;
    --allow-privacy-findings) allow_privacy_findings=1 ;;
    *) die "$usage" ;;
  esac
  shift
done
[[ "$JOB_ID" =~ ^[0-9]+$ ]] || die "$usage"
for tool in curl python3 tar; do
  command -v "$tool" >/dev/null || die "Missing command: $tool"
done

CONFIG="${FONDA_SLURM_ENV:-$HOME/.fonda-vivo/slurm.env}"
# shellcheck disable=SC1090
[[ -r "$CONFIG" ]] && source "$CONFIG"
EVIDENCE_DIR="${EVIDENCE_ROOT:-$HOME/vivo-evidence}/$JOB_ID"
RECEIPT="$(ls -t "$EVIDENCE_DIR"/publication-*/run.published.json 2>/dev/null | head -1 || true)"
[[ -n "$RECEIPT" ]] || die "Job $JOB_ID has no publication receipt; publish it first with publish-slurm-job.sh"
PUBLICATION_DIR="$(dirname "$RECEIPT")"

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
artifact_dir="$EVIDENCE_DIR/trace-archive-$stamp"
bundle_dir="$artifact_dir/bundle"
umask 077
mkdir -p "$bundle_dir/slurm"

# Slurm accounting of the job (no user or account columns).
if command -v sacct >/dev/null; then
  sacct -j "$JOB_ID" --parsable2 \
    --format=JobID,JobName,State,Start,End,ElapsedRaw,TotalCPU,NCPUS,MaxRSS,ConsumedEnergyRaw,NodeList,NNodes,Partition,ExitCode,AllocTRES \
    > "$bundle_dir/slurm/sacct.txt"
fi

packaged="$(python3 - "$bundle_dir" "$EVIDENCE_DIR" "$PUBLICATION_DIR" "$JOB_ID" "${NEXTFLOW_LAUNCH_DIR:-}" <<'PY'
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

bundle, evidence, publication = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
job_id, launch_dir = sys.argv[4], sys.argv[5]

receipt = json.loads((publication / "run.published.json").read_text())
if receipt.get("removed_at"):
    sys.exit("ERROR: the latest publication of this job was removed from VIVO; publish it again first")
summary = json.loads((publication / "summary.json").read_text())
run_uri = summary["run_uri"]


def copy(source, target):
    source = Path(source)
    if source.is_file():
        (bundle / target).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, bundle / target)


for name in ("job-info.tsv", "node-info.tsv", "node-samples.tsv"):
    copy(evidence / name, f"slurm/{name}")
for directory in [launch_dir, "."]:
    if directory:
        copy(Path(directory) / f"slurm-{job_id}.out", f"slurm/slurm-{job_id}.out")
for name in ("run.ttl", "summary.json", "run.published.json"):
    copy(publication / name, f"vivo/{name}")

# The Nextflow files that were used for the publication, plus the report,
# timeline, DAG, parameters and software versions next to the trace.
log = (summary.get("nextflow_log") or {}).get("path")
if log:
    copy(log, "nextflow/nextflow.log")
trace = (summary.get("nextflow_trace") or {}).get("path")
if trace:
    info_dir = Path(trace).parent
    copy(trace, f"nextflow/{Path(trace).name}")
    for pattern in ("execution_report_*.html", "execution_timeline_*.html", "pipeline_dag_*.html",
                    "params_*.json", "*_software_mqc_versions.yml"):
        for path in sorted(info_dir.glob(pattern)):
            copy(path, f"nextflow/{path.name}")

contents = ["Slurm accounting, node hardware, node CPU and IPMI power samples and the job's console output",
            "VIVO Turtle, collection summary and publication receipt"]
if log or trace:
    contents.insert(1, "Nextflow log, task trace, report, timeline, DAG, run parameters and software versions when present")
manifest = {
    "schema_version": 1,
    "created_at": datetime.now(timezone.utc).isoformat(),
    "slurm_job_id": job_id,
    "vivo_run_uri": run_uri,
    "archive_scope": "one workflow run",
    "contents": "; ".join(contents) + ". Scientific result data are deliberately excluded.",
    "wta_note": ("Native evidence bundle for later Workflow Trace Archive conversion; "
                 "not represented as a WTA-format deposit."),
}
(bundle / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")

credential_patterns = [
    re.compile(r"(?i)authorization\s*:\s*(?:token|bearer)\s+\S+"),
    re.compile(r"(?i)(?:api[_-]?token|auth[_-]?token|password|passwd|secret)\s*[=:]\s*[\"']?[A-Za-z0-9_./+=-]{8,}"),
]
findings = []
text_suffixes = {".html", ".json", ".log", ".out", ".tsv", ".txt", ".ttl", ".yaml", ".yml"}
for path in sorted(bundle.rglob("*")):
    if not path.is_file() or path.suffix.lower() not in text_suffixes:
        continue
    for number, line in enumerate(path.read_text(errors="ignore").splitlines(), 1):
        if any(pattern.search(line) for pattern in credential_patterns):
            findings.append(f"{path.relative_to(bundle)}:{number}")
(bundle / "PRIVACY-SCAN.txt").write_text(
    "No credential-shaped values detected.\n" if not findings else
    "Review these credential-shaped values before publication:\n" + "\n".join(findings) + "\n")

checksums = []
for path in sorted(bundle.rglob("*")):
    if path.is_file() and path.name != "SHA256SUMS":
        checksums.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(bundle)}")
(bundle / "SHA256SUMS").write_text("\n".join(checksums) + "\n")
print(len(findings), run_uri.rstrip("/").rsplit("/", 1)[-1])
PY
)"
privacy_count="${packaged%% *}"
run_key="${packaged#* }"
[[ "$run_key" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] || die "Unexpected run identifier: $run_key"

if [[ "$privacy_count" != "0" && "$allow_privacy_findings" != "1" ]]; then
  printf 'Bundle retained for review: %s\n' "$bundle_dir"
  die "Privacy scan found $privacy_count credential-shaped value(s); inspect PRIVACY-SCAN.txt"
fi

archive="$artifact_dir/${run_key}-trace-bundle-${stamp}.tar.gz"
tar -C "$bundle_dir" -czf "$archive" .
archive_sha="$(python3 -c 'import hashlib, sys; print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())' "$archive")"
printf '%s  %s\n' "$archive_sha" "$(basename "$archive")" > "$archive.sha256"
printf 'Bundle: %s\n' "$bundle_dir"
printf 'Prepared trace archive: %s\n' "$archive"
printf 'Archive SHA-256: %s\n' "$archive_sha"

if [[ "$package_only" == "1" ]]; then
  printf 'Package-only mode: no HU-Box upload and no VIVO update.\n'
  exit 0
fi

if [[ "$shared_folder" == "1" ]]; then
  python3 "$ROOT_DIR/publisher/upload_trace_archive.py" "$archive"
  exit 0
fi

hu_config="${HU_BOX_CONFIG_FILE:-$ROOT_DIR/config/hu-box.env}"
[[ -r "$hu_config" ]] || die "Missing $hu_config; run scripts/configure-hu-box.sh"
# shellcheck disable=SC1090
source "$hu_config"
server_url="${HU_BOX_SERVER_URL:-https://box.hu-berlin.de}"
repo_id="${HU_BOX_REPOSITORY_ID:-}"
parent_dir="${HU_BOX_PARENT_DIR:-/}"
trace_prefix="${HU_BOX_TRACE_PREFIX:-fonda-workflow-traces}"
token_file="${HU_BOX_API_TOKEN_FILE:-$HOME/.config/fonda/hu-box-api-token}"
[[ "$repo_id" =~ ^[0-9a-fA-F-]{36}$ ]] || die "HU_BOX_REPOSITORY_ID is not set; run scripts/configure-hu-box.sh"
[[ -r "$token_file" ]] || die "Missing HU-Box token file $token_file; run scripts/configure-hu-box.sh"
token="$(tr -d '\r\n' < "$token_file")"
[[ -n "$token" ]] || die "HU-Box token file is empty"
[[ "$server_url" =~ ^https?://[^[:space:]]+$ ]] || die "HU_BOX_SERVER_URL must be an http(s) URL"
[[ "$parent_dir" == /* ]] || die "HU_BOX_PARENT_DIR must start with /"

encoded_parent="$(python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1], safe="/"))' "$parent_dir")"
upload_response="$(curl --fail --silent --show-error --header "Authorization: Token $token" \
  "$server_url/api2/repos/$repo_id/upload-link/?p=$encoded_parent")"
upload_url="$(python3 -c 'import json, sys; print(json.load(sys.stdin))' <<< "$upload_response")"
[[ "$upload_url" =~ ^https?://[^[:space:]]+$ ]] || die "HU-Box returned no upload URL"

relative_dir="$trace_prefix/$run_key"
curl --fail --silent --show-error \
  --form "file=@$archive" \
  --form "parent_dir=$parent_dir" \
  --form "relative_path=$relative_dir" \
  --form "replace=0" \
  "$upload_url?ret-json=1" >/dev/null

share_payload="$(python3 - "$repo_id" "$parent_dir" "$relative_dir" "$(basename "$archive")" <<'PY'
import json, posixpath, sys
print(json.dumps({"repo_id": sys.argv[1], "path": posixpath.join(sys.argv[2], sys.argv[3], sys.argv[4]),
                  "permissions": {"can_edit": False, "can_download": True}}))
PY
)"
share_response="$(curl --fail --silent --show-error \
  --header "Authorization: Token $token" --header "Content-Type: application/json" \
  --data "$share_payload" "$server_url/api/v2.1/share-links/")"
share_url="$(python3 -c 'import json, sys; print(json.load(sys.stdin).get("link", ""))' <<< "$share_response")"
[[ "$share_url" =~ ^https?://[^[:space:]\"\<\>]+$ ]] || die "HU-Box returned no public share link"
curl --fail --location --silent --show-error --max-time 30 --output /dev/null "$share_url"
printf 'Public HU-Box trace link: %s\n' "$share_url"
# Kept so that a later publish-slurm-job.sh keeps the link.
printf '%s\n' "$share_url" > "$EVIDENCE_DIR/trace-archive-url.txt"

if [[ "$no_vivo" == "1" ]]; then
  printf 'No-VIVO mode: archive uploaded and shared, VIVO unchanged.\n'
  printf 'Add the link later with: examples/hpc-at-hu-slurm/publish-slurm-job.sh %s\n' "$JOB_ID"
  exit 0
fi

# Republish the same Turtle with the link added; nothing is collected again.
new_publication="$EVIDENCE_DIR/publication-$stamp-trace-archive"
mkdir "$new_publication"
cp "$PUBLICATION_DIR/summary.json" "$new_publication/summary.json"
python3 - "$PUBLICATION_DIR/run.ttl" "$new_publication/run.ttl" "$share_url" <<'PY'
import sys
source, target, url = sys.argv[1:]
lines = [line for line in open(source).read().splitlines() if not line.lstrip().startswith("rm:traceArchive ")]
marker = "  rdf:type rm:RunMetadata ;"
if lines.count(marker) != 1:
    sys.exit("ERROR: the published Turtle has no single run record")
index = lines.index(marker)
lines.insert(index + 1, f'  rm:traceArchive "{url}"^^xsd:anyURI ;')
open(target, "w").write("\n".join(lines) + "\n")
PY
publish_args=("$new_publication/run.ttl" --receipt-file "$new_publication/run.published.json"
              --email-file "$HOME/.fonda-vivo/email" --password-file "$HOME/.fonda-vivo/password")
[[ -n "${VIVO_ENDPOINT:-}" ]] && publish_args+=(--endpoint "$VIVO_ENDPOINT")
python3 "$ROOT_DIR/publisher/publish_vivo.py" "${publish_args[@]}"
python3 -c 'import json, sys, urllib.parse
run = json.load(open(sys.argv[1]))["run_uri"]
print("VIVO page: https://vivo-fonda.hu-berlin.de/vivo/individual?uri=" + urllib.parse.quote(run, safe=""))' \
  "$new_publication/summary.json"
printf 'Archived job %s and added its trace link to VIVO.\n' "$JOB_ID"
