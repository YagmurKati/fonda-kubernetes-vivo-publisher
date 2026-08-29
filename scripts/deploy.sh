#!/usr/bin/env bash

set -euo pipefail
source "$(dirname "$0")/lib/common.sh"

need_command kubectl
need_command python3
load_config
require_namespace

if is_snakemake_engine; then
  sed \
    -e "s/__NAMESPACE__/$NS/g" \
    -e "s/__SERVICE_ACCOUNT__/$SERVICE_ACCOUNT/g" \
    "$ROOT_DIR/k8s/snakemake-reader-rbac.yaml" |
    kubectl apply -f -
fi

kubectl -n "$NS" get pvc "$PVC_NAME" >/dev/null
kubectl -n "$NS" get serviceaccount "$SERVICE_ACCOUNT" >/dev/null
kubectl -n "$NS" get secret "$VIVO_CREDENTIALS_SECRET" >/dev/null
if [[ "$CARBON_SOURCE" == "electricity-maps-latest" ]]; then
  kubectl -n "$NS" get secret electricity-maps-api-token >/dev/null
fi

input_file="$(input_metadata_path)"
[[ -r "$input_file" ]] || die "Input metadata file is not readable: $input_file"
python3 -m json.tool "$input_file" >/dev/null
if grep -Eqi 'replace-me|Replace with' "$input_file"; then
  die "Replace all placeholders in $input_file or use an empty datasets list"
fi

code_args=(
  --from-file=publisher.py="$ROOT_DIR/publisher/publish_vivo.py"
  --from-file=input_datasets.json="$input_file"
)
if is_snakemake_engine; then
  code_args+=(
    --from-file=collector.py="$ROOT_DIR/collector/collect_snakemake_kubernetes_metadata.py"
    --from-file=collector_core.py="$ROOT_DIR/collector/collect_nextflow_run_metadata.py"
  )
else
  code_args+=(
    --from-file=collector.py="$ROOT_DIR/collector/collect_nextflow_run_metadata.py"
  )
fi

kubectl -n "$NS" create configmap fonda-vivo-publisher-code \
  "${code_args[@]}" --dry-run=client -o yaml |
  kubectl -n "$NS" apply -f -

if is_snakemake_engine; then
  setting_names=(
    SNAKEMAKE_PROFILE RUN_ROOT CODE_PATH POD_LABEL_SELECTOR FALLBACK_RUN_ID
    JOB_NAME_REGEX WORKFLOW_NAME WORKFLOW_URI WORKFLOW_REPO_URL CODE_URI
    PUBLICATION_URI TRACE_ARCHIVE
    RESPONSIBLE_RESEARCHER_URIS SUBPROJECT_URIS LANGUAGE_URIS
    APPLICATION_DOMAIN_URI RUN_OPERATOR_URI BACKEND_URI CLUSTER_URI
    CLUSTER_LABEL ENGINE_URI PROM_URL CARBON_SOURCE CARBON_INTENSITY
    ELECTRICITY_MAPS_ZONE CO2MAP_STATE CO2MAP_COUNTRY CO2MAP_DATA_STATUS
    ALLOW_MISSING_METRICS REQUIRE_SUCCEEDED BASE_URI ONTOLOGY_URI VIVO_ENDPOINT
    VIVO_GRAPH
  )
else
  setting_names=(
    TRACE_PATH_TEMPLATE CONSOLE_LOG_PATH_TEMPLATE DEBUG_LOG_PATH CODE_PATH
    TRACE_TIMEZONE WORKFLOW_NAME WORKFLOW_URI WORKFLOW_REPO_URL CODE_URI
    GIT_COMMIT PUBLICATION_URI TRACE_ARCHIVE RESPONSIBLE_RESEARCHER_URIS
    SUBPROJECT_URIS LANGUAGE_URIS APPLICATION_DOMAIN_URI RUN_OPERATOR_URI
    BACKEND_URI CLUSTER_URI CLUSTER_LABEL ENGINE_URI PROM_URL CARBON_SOURCE
    CARBON_INTENSITY ELECTRICITY_MAPS_ZONE CO2MAP_STATE CO2MAP_COUNTRY
    CO2MAP_DATA_STATUS ALLOW_MISSING_METRICS REQUIRE_SUCCEEDED BASE_URI
    ONTOLOGY_URI VIVO_ENDPOINT VIVO_GRAPH
  )
fi
settings_args=()
for setting_name in "${setting_names[@]}"; do
  settings_args+=("--from-literal=${setting_name}=${!setting_name}")
done

kubectl -n "$NS" create configmap fonda-vivo-publisher-settings \
  "${settings_args[@]}" --dry-run=client -o yaml |
  kubectl -n "$NS" apply -f -

printf 'FONDA VIVO publisher deployed in namespace %s. No RDF was published.\n' "$NS"
