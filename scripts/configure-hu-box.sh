#!/usr/bin/env bash

set -euo pipefail
source "$(dirname "$0")/lib/common.sh"

need_command curl
need_command python3

server_url="${HU_BOX_SERVER_URL:-https://box.hu-berlin.de}"
token_file="${HU_BOX_API_TOKEN_FILE:-$HOME/.config/fonda/hu-box-api-token}"
hu_config="${HU_BOX_CONFIG_FILE:-$ROOT_DIR/config/hu-box.env}"

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
unset username password otp curl_args
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
repos_response="$(curl --fail --silent --show-error \
  --header "Authorization: Token $token" \
  "$server_url/api2/repos/")"
printf 'Available HU-Box libraries:\n'
python3 -c '
import json, sys
for index, repo in enumerate(json.load(sys.stdin), 1):
    print("{}. {} ({})".format(index, repo.get("name", ""), repo.get("id", "")))
' <<< "$repos_response"
printf 'Select destination library number: '
IFS= read -r selection
[[ "$selection" =~ ^[1-9][0-9]*$ ]] || die "Select a positive library number"
repo_id="$(python3 -c '
import json, sys
repos = json.load(sys.stdin)
index = int(sys.argv[1]) - 1
if index < 0 or index >= len(repos):
    raise SystemExit(2)
print(repos[index].get("id", ""))
' "$selection" <<< "$repos_response")" || die "Library selection is out of range"
[[ "$repo_id" =~ ^[0-9a-fA-F-]{36}$ ]] || die "Selected library has no valid id"

printf 'Parent directory inside the library [/]: '
IFS= read -r parent_dir
parent_dir="${parent_dir:-/}"
[[ "$parent_dir" == /* ]] || die "Parent directory must start with /"
printf 'Trace directory prefix [fonda-workflow-traces]: '
IFS= read -r trace_prefix
trace_prefix="${trace_prefix:-fonda-workflow-traces}"
[[ "$trace_prefix" != /* && "$trace_prefix" != *..* ]] ||
  die "Trace directory prefix must be a safe relative path"

umask 077
mkdir -p "$(dirname "$hu_config")"
{
  printf 'HU_BOX_SERVER_URL=%q\n' "$server_url"
  printf 'HU_BOX_REPOSITORY_ID=%q\n' "$repo_id"
  printf 'HU_BOX_PARENT_DIR=%q\n' "$parent_dir"
  printf 'HU_BOX_TRACE_PREFIX=%q\n' "$trace_prefix"
  printf 'HU_BOX_API_TOKEN_FILE=%q\n' "$token_file"
} > "$hu_config"
chmod 600 "$hu_config"
printf 'Stored private HU-Box settings in %s\n' "$hu_config"
