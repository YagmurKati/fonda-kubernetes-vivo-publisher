#!/usr/bin/env bash

set -euo pipefail
source "$(dirname "$0")/lib/common.sh"

need_command kubectl
need_command python3
load_config
require_namespace

kubectl -n "$NS" get pvc "$PVC_NAME" >/dev/null
kubectl -n "$NS" get serviceaccount "$SERVICE_ACCOUNT" >/dev/null
kubectl -n "$NS" get secret fonda-vivo-credentials >/dev/null
if [[ "$CARBON_SOURCE" == "electricity-maps-latest" ]]; then
  kubectl -n "$NS" get secret electricity-maps-api-token >/dev/null
fi

input_file="$(input_metadata_path)"
[[ -r "$input_file" ]] || die "Input metadata file is not readable: $input_file"
python3 -m json.tool "$input_file" >/dev/null
if grep -Eqi 'replace-me|Replace with' "$input_file"; then
  die "Replace all placeholders in $input_file or use an empty datasets list"
fi

kubectl -n "$NS" create configmap fonda-vivo-publisher-code \
  --from-file=collector.py="$ROOT_DIR/collector/collect_nextflow_run_metadata.py" \
  --from-file=publisher.py="$ROOT_DIR/publisher/publish_vivo.py" \
  --from-file=input_datasets.json="$input_file" \
  --dry-run=client -o yaml |
  kubectl -n "$NS" apply -f -

setting_names=(
  TRACE_PATH_TEMPLATE CONSOLE_LOG_PATH_TEMPLATE DEBUG_LOG_PATH CODE_PATH
  TRACE_TIMEZONE WORKFLOW_NAME WORKFLOW_URI WORKFLOW_REPO_URL CODE_URI
  GIT_COMMIT PUBLICATION_URI TRACE_ARCHIVE RESPONSIBLE_RESEARCHER_URIS
  SUBPROJECT_URIS LANGUAGE_URIS APPLICATION_DOMAIN_URI RUN_OPERATOR_URI
  BACKEND_URI CLUSTER_URI CLUSTER_LABEL ENGINE_URI PROM_URL CARBON_SOURCE
  CARBON_INTENSITY ELECTRICITY_MAPS_ZONE BASE_URI ONTOLOGY_URI
  VIVO_ENDPOINT VIVO_GRAPH
)
settings_args=()
for setting_name in "${setting_names[@]}"; do
  settings_args+=("--from-literal=${setting_name}=${!setting_name}")
done

kubectl -n "$NS" create configmap fonda-vivo-publisher-settings \
  "${settings_args[@]}" --dry-run=client -o yaml |
  kubectl -n "$NS" apply -f -

printf 'FONDA VIVO publisher deployed in namespace %s. No RDF was published.\n' "$NS"
