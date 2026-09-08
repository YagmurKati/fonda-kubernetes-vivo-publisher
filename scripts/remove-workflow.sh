#!/usr/bin/env bash

set -euo pipefail
source "$(dirname "$0")/lib/common.sh"

need_command kubectl
need_command sed
load_config

workflow_iri="${1:-}"
shift || true
dry_run=0
while (($#)); do
  case "$1" in
    --dry-run) dry_run=1 ;;
    *) die "Usage: $0 WORKFLOW_IRI [--dry-run]" ;;
  esac
  shift
done

[[ -n "$workflow_iri" ]] || die "Usage: $0 WORKFLOW_IRI [--dry-run]"
require_http_uri "$workflow_iri" "WORKFLOW_IRI"
[[ ${#workflow_iri} -le 500 ]] ||
  die "WORKFLOW_IRI cannot exceed 500 characters"
[[ "$workflow_iri" != *'|'* ]] ||
  die "WORKFLOW_IRI cannot contain a pipe character"

if [[ "$workflow_iri" == "$WORKFLOW_URI" ]]; then
  die "Refusing to remove WORKFLOW_URI from the active profile: $workflow_iri"
fi

if [[ "$dry_run" == "0" ]]; then
  printf 'Remove workflow %s from VIVO?\n' "$workflow_iri"
  printf 'Only a workflow with no runs is removed; published runs are kept.\n'
  read -r -p 'Type REMOVE to continue: ' confirmation
  [[ "$confirmation" == "REMOVE" ]] || die "Removal cancelled"
fi

"$ROOT_DIR/scripts/deploy.sh"

job_suffix="$(
  printf '%s' "$workflow_iri" |
    sed -E 's#^https?://##' |
    tr '[:upper:]_.' '[:lower:]--' |
    sed -E 's/[^a-z0-9-]+/-/g; s/^-+//; s/-+$//' |
    tail -c 33
)"
job_suffix="${job_suffix#-}"
[[ -n "$job_suffix" ]] || die "WORKFLOW_IRI does not produce a valid Job name"
job_name="fonda-vivo-rmwf-${job_suffix}-$(date +%s)"

sed \
  -e "s|__JOB_NAME__|$job_name|g" \
  -e "s|__WORKFLOW_IRI__|$workflow_iri|g" \
  -e "s|__NAMESPACE__|$NS|g" \
  -e "s|__SERVICE_ACCOUNT__|$SERVICE_ACCOUNT|g" \
  -e "s|__VIVO_SECRET__|$VIVO_CREDENTIALS_SECRET|g" \
  -e "s|__DRY_RUN__|$dry_run|g" \
  "$ROOT_DIR/k8s/remove-workflow-job.yaml" |
  kubectl -n "$NS" apply -f -

if [[ "$dry_run" == "1" ]]; then
  printf 'Started workflow removal validation Job: %s\n' "$job_name"
else
  printf 'Started workflow removal Job: %s\n' "$job_name"
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
    die "Workflow removal Job $job_name failed; nothing was removed"
  fi
  if ((SECONDS >= deadline)); then
    kubectl -n "$NS" logs -l "job-name=$job_name" \
      --all-containers=true --prefix=true || true
    die "Workflow removal Job $job_name exceeded ${timeout_seconds}s"
  fi
  sleep 5
done

kubectl -n "$NS" logs -l "job-name=$job_name" \
  --all-containers=true --prefix=true
printf 'VIVO Workflows: https://vivo-fonda.hu-berlin.de/vivo/workflows\n'
