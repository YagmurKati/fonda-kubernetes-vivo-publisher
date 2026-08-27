#!/usr/bin/env bash

set -euo pipefail
source "$(dirname "$0")/lib/common.sh"

need_command kubectl
need_command base64
load_config
require_namespace

email=""
password=""
confirmation=""
token=""
email_b64=""
password_b64=""
token_b64=""
trap 'unset email password confirmation token email_b64 password_b64 token_b64' EXIT

printf 'VIVO publisher email: ' >&2
IFS= read -r email
printf 'VIVO publisher password: ' >&2
IFS= read -r -s password
printf '\nConfirm VIVO publisher password: ' >&2
IFS= read -r -s confirmation
printf '\n' >&2

[[ -n "$email" ]] || die "VIVO email cannot be empty"
[[ -n "$password" ]] || die "VIVO password cannot be empty"
[[ "$password" == "$confirmation" ]] || die "Passwords do not match"

email_b64="$(printf '%s' "$email" | base64 | tr -d '\r\n')"
password_b64="$(printf '%s' "$password" | base64 | tr -d '\r\n')"
printf '%s\n' \
  'apiVersion: v1' \
  'kind: Secret' \
  'metadata:' \
  "  name: $VIVO_CREDENTIALS_SECRET" \
  "  namespace: $NS" \
  'type: Opaque' \
  'data:' \
  "  email: $email_b64" \
  "  password: $password_b64" |
  kubectl apply -f -

unset email password confirmation email_b64 password_b64

if [[ "$CARBON_SOURCE" == "electricity-maps-latest" ]]; then
  printf 'Electricity Maps API token: ' >&2
  IFS= read -r -s token
  printf '\n' >&2
  [[ -n "$token" ]] || die "Electricity Maps token cannot be empty"
  token_b64="$(printf '%s' "$token" | base64 | tr -d '\r\n')"
  printf '%s\n' \
    'apiVersion: v1' \
    'kind: Secret' \
    'metadata:' \
    '  name: electricity-maps-api-token' \
    "  namespace: $NS" \
    'type: Opaque' \
    'data:' \
    "  token: $token_b64" |
    kubectl apply -f -
  unset token token_b64
fi

printf 'Publisher credentials are stored in Secret %s in namespace %s.\n' \
  "$VIVO_CREDENTIALS_SECRET" "$NS"
