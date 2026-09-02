#!/usr/bin/env bash

set -euo pipefail
source "$(dirname "$0")/lib/common.sh"

need_command kubectl
need_command sed
load_config

publication_id="${1:-}"
shift || true
dry_run=0
while (($#)); do
  case "$1" in
    --dry-run) dry_run=1 ;;
    *) die "Usage: $0 PUBLICATION_ID [--dry-run]" ;;
  esac
  shift
done

[[ "$publication_id" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] ||
  die "PUBLICATION_ID may contain only letters, digits, dot, underscore, and hyphen"
[[ ${#publication_id} -le 140 ]] ||
  die "PUBLICATION_ID cannot exceed 140 characters"

if is_snakemake_engine; then
  output_dir="${RUN_ROOT}/vivo-outbox"
else
  output_dir="/workspace/vivo-outbox"
fi
[[ "$output_dir" =~ ^/[A-Za-z0-9._/-]+$ ]] ||
  die "The VIVO outbox path contains unsupported characters"

if [[ "$dry_run" == "0" ]]; then
  printf 'Remove publication %s from VIVO?\n' "$publication_id"
  printf 'The workflow results and local audit files will be kept.\n'
  read -r -p 'Type REMOVE to continue: ' confirmation
  [[ "$confirmation" == "REMOVE" ]] || die "Removal cancelled"
fi

"$ROOT_DIR/scripts/deploy.sh"

job_suffix="$(
  printf '%s' "$publication_id" |
    tr '[:upper:]_.' '[:lower:]--' |
    sed -E 's/[^a-z0-9-]+/-/g; s/^-+//; s/-+$//' |
    cut -c1-32
)"
[[ -n "$job_suffix" ]] || die "PUBLICATION_ID does not produce a valid Job name"
job_name="fonda-vivo-remove-${job_suffix}-$(date +%s)"

sed \
  -e "s|__JOB_NAME__|$job_name|g" \
  -e "s|__PUBLICATION_ID__|$publication_id|g" \
  -e "s|__NAMESPACE__|$NS|g" \
  -e "s|__PVC_NAME__|$PVC_NAME|g" \
  -e "s|__SERVICE_ACCOUNT__|$SERVICE_ACCOUNT|g" \
  -e "s|__VIVO_SECRET__|$VIVO_CREDENTIALS_SECRET|g" \
  -e "s|__OUTPUT_DIR__|$output_dir|g" \
  -e "s|__DRY_RUN__|$dry_run|g" \
  "$ROOT_DIR/k8s/remove-run-job.yaml" |
  kubectl -n "$NS" apply -f -

if [[ "$dry_run" == "1" ]]; then
  printf 'Started VIVO removal validation Job: %s\n' "$job_name"
else
  printf 'Started VIVO removal Job: %s\n' "$job_name"
fi

timeout_seconds="${VIVO_JOB_TIMEOUT_SECONDS:-600}"
[[ "$timeout_seconds" =~ ^[1-9][0-9]*$ ]] ||
  die "VIVO_JOB_TIMEOUT_SECONDS must be a positive integer"
deadline=$((SECONDS + timeout_seconds))

while true; do
  status="$(kubectl -n "$NS" get "job/$job_name" \
    -o jsonpath='{.status.succeeded}{"|"}{.status.conditions[?(@.type=="Failed")].status}')"
  if [[ "$status" == 1\|* ]]; then
    break
  fi
  if [[ "$status" == *\|True ]]; then
    kubectl -n "$NS" logs -l "job-name=$job_name" \
      --all-containers=true --prefix=true || true
    die "VIVO removal Job $job_name failed"
  fi
  if ((SECONDS >= deadline)); then
    kubectl -n "$NS" logs -l "job-name=$job_name" \
      --all-containers=true --prefix=true || true
    die "VIVO removal Job $job_name exceeded ${timeout_seconds}s"
  fi
  sleep 5
done

kubectl -n "$NS" logs -l "job-name=$job_name" \
  --all-containers=true --prefix=true
if [[ "$dry_run" == "0" ]]; then
  printf 'Verify removal: https://vivo-fonda.hu-berlin.de/vivo/runs\n'
fi
