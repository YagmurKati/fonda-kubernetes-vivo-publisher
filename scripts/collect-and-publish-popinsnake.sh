#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export CONFIG_FILE="${CONFIG_FILE:-$ROOT_DIR/config/popinsnake.publisher.env}"

if (($# == 0)); then
  printf 'Usage: %s RUN_ID [--dry-run]\n' "$0" >&2
  exit 2
fi

exec "$ROOT_DIR/scripts/publish-run.sh" "$@"
