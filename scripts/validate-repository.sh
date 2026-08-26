#!/usr/bin/env bash

set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

python3 -m json.tool config/input_datasets.json >/dev/null
python3 -m json.tool config/input_datasets.json.example >/dev/null
for input_file in examples/*/input_datasets.json; do
  python3 -m json.tool "$input_file" >/dev/null
done
python3 -m unittest discover -s tests -p 'test_*.py'
python3 -m py_compile collector/*.py publisher/*.py
bash -n scripts/*.sh scripts/lib/*.sh

python3 publisher/publish_vivo.py \
  examples/force2nxf/force2nxf-vivo-20260825-01-resume-20260826T085029Z.ttl \
  --dry-run >/dev/null

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
