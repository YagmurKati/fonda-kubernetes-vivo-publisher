#!/usr/bin/env bash
# Collect and publish one finished HPC@HU Slurm job. Run on the login node.
# Usage: publish-slurm-job.sh JOB_ID [--dry-run]
# Settings come from ~/.fonda-vivo/slurm.env (see README.md).
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
CONFIG="${FONDA_SLURM_ENV:-$HOME/.fonda-vivo/slurm.env}"
if [[ $# -lt 1 || $# -gt 2 || ( $# -eq 2 && "$2" != "--dry-run" ) ]]; then
  printf 'Usage: %s JOB_ID [--dry-run]\n' "$0" >&2
  exit 2
fi
JOB_ID="$1"
# shellcheck disable=SC1090
source "$CONFIG"
: "${WORKFLOW_URI:?set WORKFLOW_URI in $CONFIG}"
EVIDENCE_DIR="${EVIDENCE_ROOT:-$HOME/vivo-evidence}/$JOB_ID"
OUT_DIR="$EVIDENCE_DIR/publication-$(date -u +%Y%m%dT%H%M%SZ)"

collector_args=(--job-id "$JOB_ID" --evidence-dir "$EVIDENCE_DIR" --output-dir "$OUT_DIR"
                --workflow-uri "$WORKFLOW_URI" --run-operator-uri "${RUN_OPERATOR_URI:-}")
[[ -n "${WORKFLOW_LABEL:-}" ]] && collector_args+=(--workflow-label "$WORKFLOW_LABEL")
[[ -n "${RUN_LABEL:-}" ]] && collector_args+=(--run-label "$RUN_LABEL")
[[ -n "${CODE_REPO_URL:-}" ]] && collector_args+=(--code-repo-url "$CODE_REPO_URL")
[[ -n "${GIT_COMMIT:-}" ]] && collector_args+=(--git-commit "$GIT_COMMIT")
IFS=',' read -r -a languages <<< "${LANGUAGE_URIS:-}"
for l in "${languages[@]}"; do [[ -n "$l" ]] && collector_args+=(--language-uri "$l"); done
IFS=',' read -r -a datasets <<< "${INPUT_DATA_URIS:-}"
for d in "${datasets[@]}"; do [[ -n "$d" ]] && collector_args+=(--input-data-uri "$d"); done
IFS=',' read -r -a researchers <<< "${RESPONSIBLE_RESEARCHER_URIS:-}"
for r in "${researchers[@]}"; do [[ -n "$r" ]] && collector_args+=(--responsible-researcher-uri "$r"); done
# Trace archive link saved by archive-slurm-job.sh, if any.
if [[ -s "$EVIDENCE_DIR/trace-archive-url.txt" ]]; then
  collector_args+=(--trace-archive "$(tr -d '\r\n' < "$EVIDENCE_DIR/trace-archive-url.txt")")
fi
# Nextflow runs: candidate logs and traces; the collector uses the ones written during this job.
shopt -s nullglob
if [[ -n "${NEXTFLOW_LAUNCH_DIR:-}" ]]; then
  for f in "$NEXTFLOW_LAUNCH_DIR"/.nextflow.log*; do collector_args+=(--nextflow-log "$f"); done
fi
if [[ -n "${NEXTFLOW_TRACE_GLOB:-}" ]]; then
  for f in ${NEXTFLOW_TRACE_GLOB//\{JOB_ID\}/$JOB_ID}; do collector_args+=(--nextflow-trace "$f"); done
fi
shopt -u nullglob
TOKEN_FILE="$HOME/.fonda-vivo/electricity-maps-token"
if [[ -z "${ELECTRICITY_MAPS_API_TOKEN:-}" && -s "$TOKEN_FILE" ]]; then
  ELECTRICITY_MAPS_API_TOKEN="$(cat "$TOKEN_FILE")"
  export ELECTRICITY_MAPS_API_TOKEN
fi
python3 "$ROOT_DIR/collector/collect_slurm_job_metadata.py" "${collector_args[@]}"

publish_args=("$OUT_DIR/run.ttl" --receipt-file "$OUT_DIR/run.published.json")
if [[ "${2:-}" == "--dry-run" ]]; then
  publish_args+=(--dry-run)
else
  publish_args+=(--email-file "$HOME/.fonda-vivo/email" --password-file "$HOME/.fonda-vivo/password")
fi
python3 "$ROOT_DIR/publisher/publish_vivo.py" "${publish_args[@]}"
if [[ "${2:-}" != "--dry-run" ]]; then
  python3 -c 'import json, sys, urllib.parse
run = json.load(open(sys.argv[1]))["run_uri"]
print("VIVO page: https://vivo-fonda.hu-berlin.de/vivo/individual?uri=" + urllib.parse.quote(run, safe=""))' "$OUT_DIR/summary.json"
fi
