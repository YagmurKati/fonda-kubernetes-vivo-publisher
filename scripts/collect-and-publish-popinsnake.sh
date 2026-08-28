#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export CONFIG_FILE="${CONFIG_FILE:-$ROOT_DIR/config/popinsnake.publisher.env}"

if (($# == 0)); then
  set -- popinsnake-example-20260828-02
fi

exec "$ROOT_DIR/scripts/publish-run.sh" "$@"
