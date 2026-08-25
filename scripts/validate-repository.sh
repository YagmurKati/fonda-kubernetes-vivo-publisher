#!/usr/bin/env bash

set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

python3 -m json.tool config/input_datasets.json >/dev/null
python3 -m json.tool config/input_datasets.json.example >/dev/null
python3 -m unittest discover -s tests -p 'test_*.py'
python3 -m py_compile collector/*.py publisher/*.py
bash -n scripts/*.sh scripts/lib/*.sh

if find . -type f \( -name 'wg0.conf' -o -name '*.pem' -o -name '*.key' \) \
  -not -path './.git/*' | grep -q .; then
  printf 'ERROR: private network or key file found in repository tree\n' >&2
  exit 1
fi

if grep -RIl --exclude-dir=.git --exclude='*.example' \
  -E -- '-----BEGIN (RSA |OPENSSH |EC )?PRIVATE KEY-----' . |
  grep -q .; then
  printf 'ERROR: possible credential material found\n' >&2
  exit 1
fi

printf 'Repository validation passed.\n'
