#!/usr/bin/env bash

set -euo pipefail
source "$(dirname "$0")/lib/common.sh"

need_command curl
need_command python3

server_url="${HU_BOX_SERVER_URL:-https://box.hu-berlin.de}"
token_file="${HU_BOX_API_TOKEN_FILE:-$HOME/.config/fonda/hu-box-api-token}"

printf 'HU-Box username: '
IFS= read -r username
[[ -n "$username" ]] || die "HU-Box username cannot be empty"
printf 'HU-Box password: '
IFS= read -rs password
printf '\nOptional two-factor code (press Return if unused): '
IFS= read -r otp

curl_args=(
  --fail --silent --show-error
  --data-urlencode "username=$username"
  --data-urlencode "password=$password"
)
[[ -z "$otp" ]] || curl_args+=(--header "X-SEAFILE-OTP: $otp")

response="$(curl "${curl_args[@]}" "$server_url/api2/auth-token/")"
unset password otp
token="$(
  python3 -c \
    'import json,sys; print(json.load(sys.stdin).get("token", ""))' \
    <<< "$response"
)"
[[ -n "$token" ]] || die "HU-Box did not return an API token"

umask 077
mkdir -p "$(dirname "$token_file")"
printf '%s\n' "$token" > "$token_file"
chmod 600 "$token_file"

printf 'Stored HU-Box API token in %s\n' "$token_file"
printf 'Available HU-Box libraries (copy the required id to HU_BOX_REPOSITORY_ID):\n'
curl --fail --silent --show-error \
  --header "Authorization: Token $token" \
  "$server_url/api2/repos/" |
  python3 -c '
import json, sys
for repo in json.load(sys.stdin):
    print("{}\t{}".format(repo.get("id", ""), repo.get("name", "")))
'
