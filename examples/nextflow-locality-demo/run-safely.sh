#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NS="yagmur"
RUN_ID="NFL-DSL2-DEMO-RUN01"
JOB_NAME="nextflow-locality-demo-run01"
SELECTOR="fonda.hu-berlin.de/run-id=$RUN_ID"

need() {
  command -v "$1" >/dev/null 2>&1 || {
    printf 'Required command not found: %s\n' "$1" >&2
    exit 1
  }
}

abort_our_run() {
  printf 'Placement guard failed; stopping only resources labelled %s.\n' "$SELECTOR" >&2
  kubectl -n "$NS" delete job "$JOB_NAME" --ignore-not-found --wait=false
  kubectl -n "$NS" delete pod -l "$SELECTOR" --ignore-not-found --wait=false
  exit 1
}

verify_scheduled_pods() {
  local pod node usedby
  while IFS=$'\t' read -r pod node; do
    [[ -n "$pod" && -n "$node" ]] || continue
    usedby="$(kubectl get node "$node" -o jsonpath='{.metadata.labels.usedby}')"
    printf 'placement pod=%s node=%s usedby=%s\n' "$pod" "$node" "$usedby"
    [[ "$usedby" == "prototyping" ]] || abort_our_run
  done < <(
    kubectl -n "$NS" get pods -l "$SELECTOR" \
      -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.nodeName}{"\n"}{end}'
  )
}

need kubectl
need jq

nodes_json="$(kubectl get nodes -l usedby=prototyping -o json)"
node_count="$(jq '.items | length' <<< "$nodes_json")"
[[ "$node_count" == "3" ]] || {
  printf 'Refusing to launch: expected exactly 3 prototyping nodes, found %s.\n' "$node_count" >&2
  exit 1
}
jq -e '
  all(.items[];
    (.spec.unschedulable // false) == false and
    any(.status.conditions[]; .type == "Ready" and .status == "True")
  )
' <<< "$nodes_json" >/dev/null || {
  printf 'Refusing to launch: one or more prototyping nodes are not Ready/schedulable.\n' >&2
  exit 1
}

kubectl -n "$NS" get serviceaccount nextflow-sa >/dev/null
kubectl get storageclass cephfs >/dev/null
if kubectl -n "$NS" get job "$JOB_NAME" >/dev/null 2>&1; then
  printf 'Refusing to overwrite existing job/%s.\n' "$JOB_NAME" >&2
  exit 1
fi
if kubectl -n "$NS" get pvc nextflow-locality-demo-workspace >/dev/null 2>&1; then
  printf 'Refusing to reuse existing pvc/nextflow-locality-demo-workspace.\n' >&2
  exit 1
fi
if kubectl -n "$NS" get configmap nextflow-locality-demo-run01 >/dev/null 2>&1; then
  printf 'Refusing to overwrite existing configmap/nextflow-locality-demo-run01.\n' >&2
  exit 1
fi

printf 'Allowed prototyping nodes:\n'
jq -r '.items[].metadata.name' <<< "$nodes_json"
kubectl apply -f "$ROOT_DIR/k8s-run.yaml"

deadline=$((SECONDS + 1200))
while ((SECONDS < deadline)); do
  verify_scheduled_pods
  status="$(kubectl -n "$NS" get job "$JOB_NAME" -o jsonpath='{.status.succeeded}{"|"}{.status.conditions[?(@.type=="Failed")].status}')"
  [[ "$status" == 1\|* ]] && break
  [[ "$status" == *\|True ]] && {
    kubectl -n "$NS" logs job/"$JOB_NAME" || true
    exit 1
  }
  sleep 2
done

[[ "$(kubectl -n "$NS" get job "$JOB_NAME" -o jsonpath='{.status.succeeded}')" == "1" ]] || {
  printf 'Workflow job did not complete within 1200 seconds.\n' >&2
  abort_our_run
}
verify_scheduled_pods
kubectl -n "$NS" logs job/"$JOB_NAME"
