#!/usr/bin/env bash

set -euo pipefail
source "$(dirname "$0")/lib/common.sh"

need_command curl
need_command kubectl
need_command python3
need_command sed
need_command shasum
need_command tar
load_config
hu_config="${HU_BOX_CONFIG_FILE:-$ROOT_DIR/config/hu-box.env}"
if [[ -r "$hu_config" ]]; then
  # shellcheck disable=SC1090
  source "$hu_config"
fi

RUN_ID="${1:-}"
shift || true
package_only=0
no_vivo=0
allow_privacy_findings=0
while (($#)); do
  case "$1" in
    --package-only) package_only=1 ;;
    --no-vivo) no_vivo=1 ;;
    --allow-privacy-findings) allow_privacy_findings=1 ;;
    *)
      die "Usage: $0 RUN_ID [--package-only] [--no-vivo] [--allow-privacy-findings]"
      ;;
  esac
  shift
done

[[ "$WORKFLOW_ENGINE" == "nextflow" ]] ||
  die "Automated trace packaging currently supports Nextflow profiles"
[[ "$RUN_ID" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] ||
  die "RUN_ID may contain only letters, digits, dot, underscore, and hyphen"
[[ ${#RUN_ID} -le 100 ]] || die "RUN_ID cannot exceed 100 characters"

trace_file="${TRACE_PATH_TEMPLATE//\{run_id\}/$RUN_ID}"
console_log="${CONSOLE_LOG_PATH_TEMPLATE//\{run_id\}/$RUN_ID}"
debug_log="${DEBUG_LOG_PATH//\{run_id\}/$RUN_ID}"
run_dir="$(dirname "$trace_file")"
[[ "$run_dir" == /workspace/results/* ]] ||
  die "The run directory must be below /workspace/results: $run_dir"

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
safe_id="$(
  printf '%s' "$RUN_ID" |
    tr '[:upper:]_.' '[:lower:]--' |
    sed -E 's/[^a-z0-9-]+/-/g; s/^-+//; s/-+$//' |
    cut -c1-30
)"
[[ -n "$safe_id" ]] || die "RUN_ID does not produce a valid Pod name"
lower_stamp="$(printf '%s' "$stamp" | tr '[:upper:]' '[:lower:]')"
reader_pod="fonda-trace-reader-${safe_id}-${lower_stamp}"
reader_pod="${reader_pod:0:63}"
artifact_dir="$ROOT_DIR/artifacts/trace-archives/$RUN_ID/$stamp"
bundle_dir="$artifact_dir/bundle"
archive="$artifact_dir/${RUN_ID}-trace-bundle-${stamp}.tar.gz"
mkdir -p "$bundle_dir"
umask 077

reader_created=0
cleanup_reader() {
  if [[ "$reader_created" == "1" ]]; then
    kubectl -n "$NS" delete pod "$reader_pod" \
      --ignore-not-found --wait=true >/dev/null 2>&1 || true
  fi
}
trap cleanup_reader EXIT

reader_image="${TRACE_ARCHIVE_READER_IMAGE:-quay.io/nf-core/ubuntu@sha256:bd1487129c4e01470664c3f3c9a25ce01f73ff3df75ffa7eb3388d3d4b945369}"
kubectl -n "$NS" apply -f - >/dev/null <<YAML
apiVersion: v1
kind: Pod
metadata:
  name: $reader_pod
  labels:
    app.kubernetes.io/name: fonda-trace-reader
    fonda.hu-berlin.de/run-id: "$safe_id"
spec:
  activeDeadlineSeconds: 900
  restartPolicy: Never
  serviceAccountName: $SERVICE_ACCOUNT
  nodeSelector:
    usedby: "$NODE_USEDBY"
  containers:
    - name: reader
      image: $reader_image
      imagePullPolicy: IfNotPresent
      command: ["/bin/bash", "-lc", "sleep 900"]
      volumeMounts:
        - name: workspace
          mountPath: /workspace
          readOnly: true
  volumes:
    - name: workspace
      persistentVolumeClaim:
        claimName: $PVC_NAME
        readOnly: true
YAML
reader_created=1
kubectl -n "$NS" wait --for=condition=Ready "pod/$reader_pod" --timeout=180s >/dev/null

kubectl -n "$NS" exec -i "$reader_pod" -- bash -s -- \
  "$RUN_ID" "$run_dir" "$trace_file" "$console_log" "$debug_log" <<'REMOTE' |
set -euo pipefail
run_id="$1"
run_dir="$2"
trace_file="$3"
console_log="$4"
debug_log="$5"

test -d "$run_dir"
test -r "$trace_file"
test -r "$console_log"
test -r "$debug_log"

shopt -s nullglob
receipts=(/workspace/vivo-outbox/"$run_id"-*.published.json)
((${#receipts[@]} > 0)) || {
  printf 'No publication receipt found for %s\n' "$run_id" >&2
  exit 4
}
receipt="$(printf '%s\n' "${receipts[@]}" | sort | tail -n 1)"
base="${receipt%.published.json}"
test -r "$base.ttl"
test -r "$base.metrics.json"

paths=(
  "${trace_file#/}"
  "${console_log#/}"
  "${debug_log#/}"
  "${base#/}.ttl"
  "${base#/}.metrics.json"
  "${receipt#/}"
)

optional_files=(
  "$run_dir/report-$run_id.html"
  "$run_dir/timeline-$run_id.html"
  "$run_dir/dag-$run_id.html"
  "$run_dir/driver-exit-code.txt"
  "$run_dir/nextflow-version.txt"
  "$run_dir/workflow-commit.txt"
  "$run_dir/outputs/preparation/tile_allow.txt"
)
for path in "${optional_files[@]}"; do
  [[ -r "$path" ]] && paths+=("${path#/}")
done
for path in \
  "$run_dir"/outputs/pipeline_info/params_*.json \
  "$run_dir"/outputs/pipeline_info/*_software_mqc_versions.yml; do
  [[ -r "$path" ]] && paths+=("${path#/}")
done
tar -C / -cf - "${paths[@]}"
REMOTE
  tar -C "$bundle_dir" -xf -
cleanup_reader
reader_created=0

privacy_count="$(python3 - "$bundle_dir" "$RUN_ID" "$WORKFLOW_URI" <<'PY'
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

root = Path(sys.argv[1])
run_id = sys.argv[2]
workflow_uri = sys.argv[3]
metric_files = sorted(root.rglob(f"{run_id}-*.metrics.json"))
run_uri = ""
if metric_files:
    try:
        run_uri = json.loads(metric_files[-1].read_text()).get("run_uri", "")
    except (OSError, json.JSONDecodeError):
        pass

manifest = {
    "schema_version": 1,
    "created_at": datetime.now(timezone.utc).isoformat(),
    "run_id": run_id,
    "vivo_run_uri": run_uri,
    "vivo_workflow_uri": workflow_uri,
    "archive_scope": "one workflow run",
    "contents": (
        "Native Nextflow trace, console and debug logs, report, timeline, DAG, "
        "run parameters and software versions when present; VIVO Turtle, "
        "metrics audit and publication receipt. Scientific result rasters are "
        "deliberately excluded."
    ),
    "wta_note": (
        "Native evidence bundle for later Workflow Trace Archive conversion; "
        "not represented as a WTA-format deposit."
    ),
}
(root / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")

credential_patterns = [
    re.compile(r"(?i)authorization\s*:\s*(?:token|bearer)\s+\S+"),
    re.compile(
        r"(?i)(?:api[_-]?token|password|passwd|secret)\s*[=:]\s*"
        r"[\"']?[A-Za-z0-9_./+=-]{8,}"
    ),
]
findings = []
text_suffixes = {".html", ".json", ".log", ".txt", ".ttl", ".yaml", ".yml"}
for path in sorted(root.rglob("*")):
    if not path.is_file() or path.suffix.lower() not in text_suffixes:
        continue
    text = path.read_text(errors="ignore")
    for line_number, line in enumerate(text.splitlines(), 1):
        if any(pattern.search(line) for pattern in credential_patterns):
            findings.append(f"{path.relative_to(root)}:{line_number}")

(root / "PRIVACY-SCAN.txt").write_text(
    ("No credential-shaped values detected.\n" if not findings else
     "Review these credential-shaped values before publication:\n" +
     "\n".join(findings) + "\n")
)

checksums = []
for path in sorted(root.rglob("*")):
    if path.is_file() and path.name != "SHA256SUMS":
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        checksums.append(f"{digest}  {path.relative_to(root)}")
(root / "SHA256SUMS").write_text("\n".join(checksums) + "\n")
print(len(findings))
PY
)"

if [[ "$privacy_count" != "0" && "$allow_privacy_findings" != "1" ]]; then
  printf 'Bundle retained for review: %s\n' "$bundle_dir"
  die "Privacy scan found $privacy_count credential-shaped value(s); inspect PRIVACY-SCAN.txt"
fi

tar -C "$bundle_dir" -czf "$archive" .
archive_sha="$(shasum -a 256 "$archive" | awk '{print $1}')"
printf '%s  %s\n' "$archive_sha" "$(basename "$archive")" > "$archive.sha256"
printf 'Prepared trace archive: %s\n' "$archive"
printf 'Archive SHA-256: %s\n' "$archive_sha"

if [[ "$package_only" == "1" ]]; then
  printf 'Package-only mode: no HU-Box upload and no VIVO update.\n'
  exit 0
fi

server_url="${HU_BOX_SERVER_URL:-https://box.hu-berlin.de}"
repo_id="${HU_BOX_REPOSITORY_ID:-}"
parent_dir="${HU_BOX_PARENT_DIR:-/}"
trace_prefix="${HU_BOX_TRACE_PREFIX:-fonda-workflow-traces}"
token_file="${HU_BOX_API_TOKEN_FILE:-$HOME/.config/fonda/hu-box-api-token}"
[[ "$repo_id" =~ ^[0-9a-fA-F-]{36}$ ]] ||
  die "Set HU_BOX_REPOSITORY_ID to the destination HU-Box library id"
[[ -r "$token_file" ]] ||
  die "Missing HU-Box token file $token_file; run scripts/configure-hu-box.sh"
token="$(tr -d '\r\n' < "$token_file")"
[[ -n "$token" ]] || die "HU-Box token file is empty"
require_http_uri "$server_url" "HU_BOX_SERVER_URL"
[[ "$parent_dir" == /* ]] || die "HU_BOX_PARENT_DIR must start with /"

encoded_parent="$(python3 -c 'import sys,urllib.parse; print(urllib.parse.quote(sys.argv[1], safe="/"))' "$parent_dir")"
upload_response="$(
  curl --fail --silent --show-error \
    --header "Authorization: Token $token" \
    "$server_url/api2/repos/$repo_id/upload-link/?p=$encoded_parent"
)"
upload_url="$(
  python3 -c 'import json,sys; print(json.load(sys.stdin))' <<< "$upload_response"
)"
require_http_uri "$upload_url" "HU-Box upload URL"

relative_dir="$trace_prefix/$RUN_ID"
curl --fail --silent --show-error \
  --form "file=@$archive" \
  --form "parent_dir=$parent_dir" \
  --form "relative_path=$relative_dir" \
  --form "replace=0" \
  "$upload_url?ret-json=1" >/dev/null

share_path="$(python3 - "$parent_dir" "$relative_dir" "$(basename "$archive")" <<'PY'
import posixpath, sys
print(posixpath.join(sys.argv[1], sys.argv[2], sys.argv[3]))
PY
)"
share_payload="$(python3 - "$repo_id" "$share_path" <<'PY'
import json, sys
print(json.dumps({
    "repo_id": sys.argv[1],
    "path": sys.argv[2],
    "permissions": {"can_edit": False, "can_download": True},
}))
PY
)"
share_response="$(
  curl --fail --silent --show-error \
    --header "Authorization: Token $token" \
    --header "Content-Type: application/json" \
    --data "$share_payload" \
    "$server_url/api/v2.1/share-links/"
)"
share_url="$(
  python3 -c 'import json,sys; print(json.load(sys.stdin).get("link", ""))' \
    <<< "$share_response"
)"
require_http_uri "$share_url" "HU-Box public share link"
curl --fail --location --silent --show-error --max-time 30 \
  --output /dev/null "$share_url"
printf 'Public HU-Box trace link: %s\n' "$share_url"

if [[ "$no_vivo" == "1" ]]; then
  printf 'No-VIVO mode: archive uploaded and shared, VIVO unchanged.\n'
  exit 0
fi

FORCE_REPUBLISH=1 "$ROOT_DIR/scripts/publish-run.sh" "$RUN_ID" \
  --run-trace-archive "$share_url"
printf 'Archived and republished run %s with its exact trace link.\n' "$RUN_ID"
