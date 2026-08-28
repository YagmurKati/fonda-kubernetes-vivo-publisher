#!/usr/bin/env bash

set -euo pipefail
source "$(dirname "$0")/lib/common.sh"

need_command kubectl
need_command sed
load_config

RUN_ID="${1:-}"
shift || true
dry_run="${DRY_RUN:-0}"
force_republish="${FORCE_REPUBLISH:-0}"
while (($#)); do
  case "$1" in
    --dry-run) dry_run=1 ;;
    *) die "Usage: $0 RUN_ID [--dry-run]" ;;
  esac
  shift
done

[[ "$RUN_ID" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] ||
  die "RUN_ID may contain only letters, digits, dot, underscore, and hyphen"
[[ ${#RUN_ID} -le 100 ]] || die "RUN_ID cannot exceed 100 characters"
[[ "$dry_run" == "0" || "$dry_run" == "1" ]] ||
  die "DRY_RUN must be 0 or 1"
[[ "$force_republish" == "0" || "$force_republish" == "1" ]] ||
  die "FORCE_REPUBLISH must be 0 or 1"

include_cached="${INCLUDE_CACHED_ORIGIN_METRICS:-0}"
[[ "$include_cached" == "0" || "$include_cached" == "1" ]] ||
  die "INCLUDE_CACHED_ORIGIN_METRICS must be 0 or 1"
if [[ "$WORKFLOW_ENGINE" != "nextflow" && "$include_cached" == "1" ]]; then
  die "INCLUDE_CACHED_ORIGIN_METRICS applies only to Nextflow profiles"
fi

"$ROOT_DIR/scripts/deploy.sh"

job_suffix="$(
  printf '%s' "$RUN_ID" |
    tr '[:upper:]_.' '[:lower:]--' |
    sed -E 's/[^a-z0-9-]+/-/g; s/^-+//; s/-+$//' |
    cut -c1-32
)"
[[ -n "$job_suffix" ]] || die "RUN_ID does not produce a valid Job name"
job_name="fonda-vivo-${job_suffix}-$(date +%s)"
run_label="$(printf '%s' "$job_suffix" | cut -c1-63)"
output_stamp="$(date -u +%Y%m%dT%H%M%SZ)"
if is_snakemake_engine; then
  job_template="$ROOT_DIR/k8s/snakemake-publisher-job.yaml"
else
  job_template="$ROOT_DIR/k8s/publisher-job.yaml"
fi

sed \
  -e "s/__JOB_NAME__/$job_name/g" \
  -e "s/__RUN_ID_LABEL__/$run_label/g" \
  -e "s/__RUN_ID__/$RUN_ID/g" \
  -e "s/__NAMESPACE__/$NS/g" \
  -e "s/__PVC_NAME__/$PVC_NAME/g" \
  -e "s/__SERVICE_ACCOUNT__/$SERVICE_ACCOUNT/g" \
  -e "s/__VIVO_SECRET__/$VIVO_CREDENTIALS_SECRET/g" \
  -e "s/__OUTPUT_STAMP__/$output_stamp/g" \
  -e "s/__INCLUDE_CACHED_ORIGIN_METRICS__/$include_cached/g" \
  -e "s/__DRY_RUN__/$dry_run/g" \
  -e "s/__FORCE_REPUBLISH__/$force_republish/g" \
  "$job_template" |
  kubectl -n "$NS" apply -f -

if [[ "$dry_run" == "1" ]]; then
  printf 'Started metadata validation Job: %s\n' "$job_name"
else
  printf 'Started metadata and VIVO publication Job: %s\n' "$job_name"
fi
timeout_seconds="${VIVO_JOB_TIMEOUT_SECONDS:-3600}"
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
    die "Publication Job $job_name failed; no TTL was published"
  fi
  if ((SECONDS >= deadline)); then
    kubectl -n "$NS" logs -l "job-name=$job_name" \
      --all-containers=true --prefix=true || true
    die "Publication Job $job_name exceeded ${timeout_seconds}s"
  fi
  sleep 5
done

kubectl -n "$NS" logs -l "job-name=$job_name" \
  --all-containers=true --prefix=true
artifact_base="${RUN_ID}-${output_stamp}"
if is_snakemake_engine; then
  output_dir="$RUN_ROOT/vivo-outbox"
else
  output_dir="/workspace/vivo-outbox"
fi
printf 'TTL on PVC: %s/%s.ttl\n' "$output_dir" "$artifact_base"
printf 'Metrics audit: %s/%s.metrics.json\n' "$output_dir" "$artifact_base"
if [[ "$dry_run" == "0" ]]; then
  printf 'Publication receipt: %s/%s.published.json\n' \
    "$output_dir" "$artifact_base"
  printf 'VIVO Runs: https://vivo-fonda.hu-berlin.de/vivo/runs\n'
fi
