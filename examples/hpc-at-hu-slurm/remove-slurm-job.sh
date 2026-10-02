#!/usr/bin/env bash
# Remove one published HPC@HU Slurm run from VIVO. Run on the login node.
# Usage: remove-slurm-job.sh JOB_ID [--dry-run]
# Removes the run, its date and its workflow stages; workflow, cluster and
# dataset records stay. Local evidence files are kept.
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
if [[ $# -lt 1 || $# -gt 2 || ( $# -eq 2 && "$2" != "--dry-run" ) ]]; then
  printf 'Usage: %s JOB_ID [--dry-run]\n' "$0" >&2
  exit 2
fi
EVIDENCE_DIR="${EVIDENCE_ROOT:-$HOME/vivo-evidence}/$1"
RECEIPT="$(ls -t "$EVIDENCE_DIR"/publication-*/run.published.json 2>/dev/null | head -1 || true)"
if [[ -z "$RECEIPT" ]]; then
  printf 'ERROR: no publication receipt under %s\n' "$EVIDENCE_DIR" >&2
  exit 1
fi
TTL="$(dirname "$RECEIPT")/run.ttl"
if [[ "${2:-}" == "--dry-run" ]]; then
  python3 "$ROOT_DIR/publisher/publish_vivo.py" "$TTL" --remove --dry-run --receipt-file "$RECEIPT"
else
  python3 "$ROOT_DIR/publisher/publish_vivo.py" "$TTL" --remove --confirm-removal \
    --email-file "$HOME/.fonda-vivo/email" --password-file "$HOME/.fonda-vivo/password" \
    --receipt-file "$RECEIPT"
fi
