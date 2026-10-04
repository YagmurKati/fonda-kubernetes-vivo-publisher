#!/usr/bin/env bash
# For the owner of the shared HU-Box folder: give uploaded trace archives a
# public link and add it to their runs in VIVO.
# Usage: link-shared-traces.sh [--dry-run] [--yes] [--relink ARCHIVE]
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
hu_config="${HU_BOX_CONFIG_FILE:-$ROOT_DIR/config/hu-box.env}"
if [[ -r "$hu_config" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$hu_config"
  set +a
fi
exec python3 "$ROOT_DIR/publisher/link_shared_traces.py" "$@"
