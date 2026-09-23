#!/usr/bin/env bash
# Collect time-matched energy/carbon metadata, then publish the validated record.
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
if [[ $# -lt 1 || $# -gt 2 || ( $# -eq 2 && "$2" != "--dry-run" ) ]]; then
  printf 'Usage: %s RUN_DIRECTORY [--dry-run]\n' "$0" >&2
  exit 2
fi
RUN_DIR="$(cd "$1" && pwd)"
PUBLICATION_DIR="$RUN_DIR/publication-$(date -u +%Y%m%dT%H%M%SZ)-$$"
python3 "$ROOT_DIR/collector/collect_rnaseq_rapl_metadata.py" \
  "$RUN_DIR/evidence/completed-run" --cluster "$RUN_DIR/evidence/cluster" \
  --output "$PUBLICATION_DIR"
args=("$PUBLICATION_DIR")
if [[ "${2:-}" != "--dry-run" ]]; then
  args+=(--publish)
fi
if [[ -n "${VIVO_CREDENTIALS_SECRET:-}" ]]; then
  args+=(--credentials-secret "$VIVO_CREDENTIALS_SECRET")
fi
python3 "$ROOT_DIR/examples/rnaseq-rapl/publish.py" "${args[@]}"
printf 'Publication files: %s\n' "$PUBLICATION_DIR"
