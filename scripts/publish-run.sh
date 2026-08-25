#!/usr/bin/env bash

set -euo pipefail
source "$(dirname "$0")/lib/common.sh"

need_command kubectl
need_command sed
load_config

RUN_ID="${1:-}"
[[ "$RUN_ID" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] ||
  die "Usage: $0 RUN_ID (letters, digits, dot, underscore, hyphen)"
[[ ${#RUN_ID} -le 100 ]] || die "RUN_ID cannot exceed 100 characters"

include_cached="${INCLUDE_CACHED_ORIGIN_METRICS:-0}"
[[ "$include_cached" == "0" || "$include_cached" == "1" ]] ||
  die "INCLUDE_CACHED_ORIGIN_METRICS must be 0 or 1"

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

sed \
  -e "s/__JOB_NAME__/$job_name/g" \
  -e "s/__RUN_ID_LABEL__/$run_label/g" \
  -e "s/__RUN_ID__/$RUN_ID/g" \
  -e "s/__NAMESPACE__/$NS/g" \
  -e "s/__PVC_NAME__/$PVC_NAME/g" \
  -e "s/__SERVICE_ACCOUNT__/$SERVICE_ACCOUNT/g" \
  -e "s/__OUTPUT_STAMP__/$output_stamp/g" \
  -e "s/__INCLUDE_CACHED_ORIGIN_METRICS__/$include_cached/g" \
  "$ROOT_DIR/k8s/publisher-job.yaml" |
  kubectl -n "$NS" apply -f -

printf 'Started metadata and VIVO publication Job: %s\n' "$job_name"
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
printf 'TTL on PVC: /workspace/vivo-outbox/%s.ttl\n' "$artifact_base"
printf 'Metrics audit: /workspace/vivo-outbox/%s.metrics.json\n' "$artifact_base"
printf 'Publication receipt: /workspace/vivo-outbox/%s.published.json\n' "$artifact_base"
printf 'VIVO Runs: https://vivo-fonda.hu-berlin.de/vivo/runs\n'
