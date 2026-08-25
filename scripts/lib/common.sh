#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CONFIG_FILE="${CONFIG_FILE:-$ROOT_DIR/config/publisher.env}"

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

need_command() {
  command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

validate_dns_name() {
  local value="$1"
  local label="$2"
  [[ "$value" =~ ^[a-z0-9]([-a-z0-9.]*[a-z0-9])?$ ]] ||
    die "$label is not a valid Kubernetes DNS name: $value"
}

require_http_uri() {
  local value="$1"
  local label="$2"
  [[ "$value" =~ ^https?://[^[:space:]]+$ ]] ||
    die "$label must be an absolute HTTP(S) URI"
}

optional_http_uri() {
  local value="$1"
  local label="$2"
  [[ -z "$value" ]] || require_http_uri "$value" "$label"
}

validate_uri_list() {
  local values="$1"
  local label="$2"
  local uri=""
  local entries=()
  IFS=',' read -r -a entries <<< "$values"
  for uri in "${entries[@]}"; do
    [[ -z "$uri" ]] || require_http_uri "$uri" "$label"
  done
}

load_config() {
  [[ -r "$CONFIG_FILE" ]] ||
    die "Missing $CONFIG_FILE; copy config/publisher.env.example first"

  # The configuration is a local Bash assignment file owned by the user.
  # shellcheck disable=SC1090
  source "$CONFIG_FILE"

  : "${NS:?Set NS in config/publisher.env}"
  : "${PVC_NAME:?Set PVC_NAME in config/publisher.env}"
  : "${SERVICE_ACCOUNT:?Set SERVICE_ACCOUNT in config/publisher.env}"
  : "${TRACE_PATH_TEMPLATE:?Set TRACE_PATH_TEMPLATE}"
  : "${CONSOLE_LOG_PATH_TEMPLATE:?Set CONSOLE_LOG_PATH_TEMPLATE}"
  : "${DEBUG_LOG_PATH:?Set DEBUG_LOG_PATH}"
  : "${CODE_PATH:?Set CODE_PATH}"
  : "${WORKFLOW_NAME:?Set WORKFLOW_NAME}"
  : "${WORKFLOW_URI:?Set WORKFLOW_URI}"
  : "${CLUSTER_URI:?Set CLUSTER_URI}"
  : "${ENGINE_URI:?Set ENGINE_URI}"
  : "${PROM_URL:?Set PROM_URL}"
  : "${CARBON_SOURCE:?Set CARBON_SOURCE}"
  : "${INPUT_METADATA_FILE:?Set INPUT_METADATA_FILE}"
  : "${BASE_URI:?Set BASE_URI}"
  : "${ONTOLOGY_URI:?Set ONTOLOGY_URI}"
  : "${VIVO_ENDPOINT:?Set VIVO_ENDPOINT}"
  : "${VIVO_GRAPH:?Set VIVO_GRAPH}"

  TRACE_TIMEZONE="${TRACE_TIMEZONE:-UTC}"
  WORKFLOW_REPO_URL="${WORKFLOW_REPO_URL:-}"
  CODE_URI="${CODE_URI:-}"
  GIT_COMMIT="${GIT_COMMIT:-}"
  PUBLICATION_URI="${PUBLICATION_URI:-}"
  TRACE_ARCHIVE="${TRACE_ARCHIVE:-}"
  RESPONSIBLE_RESEARCHER_URIS="${RESPONSIBLE_RESEARCHER_URIS:-}"
  SUBPROJECT_URIS="${SUBPROJECT_URIS:-}"
  LANGUAGE_URIS="${LANGUAGE_URIS:-}"
  APPLICATION_DOMAIN_URI="${APPLICATION_DOMAIN_URI:-}"
  RUN_OPERATOR_URI="${RUN_OPERATOR_URI:-}"
  BACKEND_URI="${BACKEND_URI:-}"
  CLUSTER_LABEL="${CLUSTER_LABEL:-FONDA Kubernetes Cluster}"
  CARBON_INTENSITY="${CARBON_INTENSITY:-0.4}"
  ELECTRICITY_MAPS_ZONE="${ELECTRICITY_MAPS_ZONE:-DE}"

  validate_dns_name "$NS" "NS"
  validate_dns_name "$PVC_NAME" "PVC_NAME"
  validate_dns_name "$SERVICE_ACCOUNT" "SERVICE_ACCOUNT"
  [[ "$TRACE_PATH_TEMPLATE" == *'{run_id}'* ]] ||
    die "TRACE_PATH_TEMPLATE must contain {run_id}"
  [[ "$CONSOLE_LOG_PATH_TEMPLATE" == *'{run_id}'* ]] ||
    die "CONSOLE_LOG_PATH_TEMPLATE must contain {run_id}"
  [[ "$WORKFLOW_NAME" != *REPLACE_ME* ]] || die "Replace WORKFLOW_NAME"
  [[ "$NS" != *REPLACE_ME* ]] || die "Replace NS"
  [[ "$PVC_NAME" != *REPLACE_ME* ]] || die "Replace PVC_NAME"

  require_http_uri "$WORKFLOW_URI" "WORKFLOW_URI"
  require_http_uri "$CLUSTER_URI" "CLUSTER_URI"
  require_http_uri "$ENGINE_URI" "ENGINE_URI"
  require_http_uri "$PROM_URL" "PROM_URL"
  require_http_uri "$BASE_URI" "BASE_URI"
  require_http_uri "$ONTOLOGY_URI" "ONTOLOGY_URI"
  require_http_uri "$VIVO_ENDPOINT" "VIVO_ENDPOINT"
  require_http_uri "$VIVO_GRAPH" "VIVO_GRAPH"
  optional_http_uri "$WORKFLOW_REPO_URL" "WORKFLOW_REPO_URL"
  optional_http_uri "$CODE_URI" "CODE_URI"
  optional_http_uri "$PUBLICATION_URI" "PUBLICATION_URI"
  optional_http_uri "$TRACE_ARCHIVE" "TRACE_ARCHIVE"
  optional_http_uri "$APPLICATION_DOMAIN_URI" "APPLICATION_DOMAIN_URI"
  optional_http_uri "$RUN_OPERATOR_URI" "RUN_OPERATOR_URI"
  optional_http_uri "$BACKEND_URI" "BACKEND_URI"
  validate_uri_list "$RESPONSIBLE_RESEARCHER_URIS" "RESPONSIBLE_RESEARCHER_URIS"
  validate_uri_list "$SUBPROJECT_URIS" "SUBPROJECT_URIS"
  validate_uri_list "$LANGUAGE_URIS" "LANGUAGE_URIS"
  if grep -q 'REPLACE_ME' "$CONFIG_FILE"; then
    die "Replace every REPLACE_ME value in $CONFIG_FILE"
  fi
  [[ "$CARBON_SOURCE" == "electricity-maps-latest" ||
     "$CARBON_SOURCE" == "fixed" ]] ||
    die "CARBON_SOURCE must be electricity-maps-latest or fixed"
  [[ -z "$GIT_COMMIT" || "$GIT_COMMIT" =~ ^[0-9a-fA-F]{40}$ ]] ||
    die "GIT_COMMIT must be empty or a 40-character commit SHA"
}

require_namespace() {
  kubectl get namespace "$NS" >/dev/null 2>&1 ||
    die "Kubernetes namespace '$NS' does not exist or is not accessible"
}

input_metadata_path() {
  if [[ "$INPUT_METADATA_FILE" = /* ]]; then
    printf '%s\n' "$INPUT_METADATA_FILE"
  else
    printf '%s\n' "$ROOT_DIR/$INPUT_METADATA_FILE"
  fi
}
