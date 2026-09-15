#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PROFILE_DIR="$ROOT_DIR/examples/nextflow-locality-demo"
NS="yagmur"
RUN_ID="NFL-DSL2-DEMO-RUN01"
JOB_NAME="nextflow-locality-demo-publish-run01"
SELECTOR="fonda.hu-berlin.de/run-id=$RUN_ID,app.kubernetes.io/component=metadata-publisher"

nodes_json="$(kubectl get nodes -l usedby=prototyping -o json)"
[[ "$(jq '.items | length' <<< "$nodes_json")" == "3" ]]
jq -e '
  all(.items[];
    (.spec.unschedulable // false) == false and
    any(.status.conditions[]; .type == "Ready" and .status == "True")
  )
' <<< "$nodes_json" >/dev/null

kubectl -n "$NS" get pvc nextflow-locality-demo-workspace >/dev/null
kubectl -n "$NS" get serviceaccount nextflow-sa >/dev/null
kubectl -n "$NS" get secret vivo-publisher-credentials >/dev/null
if kubectl -n "$NS" get job "$JOB_NAME" >/dev/null 2>&1; then
  printf 'Refusing to overwrite existing job/%s.\n' "$JOB_NAME" >&2
  exit 1
fi
if kubectl -n "$NS" get configmap nextflow-locality-demo-publisher-code >/dev/null 2>&1; then
  printf 'Refusing to overwrite existing publisher code ConfigMap.\n' >&2
  exit 1
fi
if kubectl -n "$NS" get configmap nextflow-locality-demo-publisher-settings >/dev/null 2>&1; then
  printf 'Refusing to overwrite existing publisher settings ConfigMap.\n' >&2
  exit 1
fi

kubectl -n "$NS" create configmap nextflow-locality-demo-publisher-code \
  --from-file=collector.py="$ROOT_DIR/collector/collect_nextflow_run_metadata.py" \
  --from-file=publisher.py="$ROOT_DIR/publisher/publish_vivo.py" \
  --from-file=input_datasets.json="$PROFILE_DIR/input_datasets.json"
kubectl apply -f "$PROFILE_DIR/k8s-publish.yaml"

deadline=$((SECONDS + 1800))
while ((SECONDS < deadline)); do
  while IFS=$'\t' read -r pod node; do
    [[ -n "$pod" && -n "$node" ]] || continue
    usedby="$(kubectl get node "$node" -o jsonpath='{.metadata.labels.usedby}')"
    printf 'placement pod=%s node=%s usedby=%s\n' "$pod" "$node" "$usedby"
    if [[ "$usedby" != "prototyping" ]]; then
      kubectl -n "$NS" delete job "$JOB_NAME" --ignore-not-found --wait=false
      exit 1
    fi
  done < <(
    kubectl -n "$NS" get pods -l "$SELECTOR" \
      -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.nodeName}{"\n"}{end}'
  )
  status="$(kubectl -n "$NS" get job "$JOB_NAME" -o jsonpath='{.status.succeeded}{"|"}{.status.conditions[?(@.type=="Failed")].status}')"
  [[ "$status" == 1\|* ]] && break
  [[ "$status" == *\|True ]] && {
    kubectl -n "$NS" logs job/"$JOB_NAME" || true
    exit 1
  }
  sleep 2
done

[[ "$(kubectl -n "$NS" get job "$JOB_NAME" -o jsonpath='{.status.succeeded}')" == "1" ]]
kubectl -n "$NS" logs job/"$JOB_NAME"
