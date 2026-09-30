#!/usr/bin/env bash
# Внутренний k6 против staging (вызывается из run-load-staging.sh / with-staging).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=guard-prod-loadtest.sh
source "${SCRIPT_DIR}/guard-prod-loadtest.sh"

if [[ -f "${SCRIPT_DIR}/.env.staging" ]]; then
  # shellcheck disable=SC1091
  set -a
  source "${SCRIPT_DIR}/.env.staging"
  set +a
fi

export BASE_URL="${STAGING_BASE_URL:-http://127.0.0.1:18081}"
export KEYCLOAK_ISSUER="${KEYCLOAK_ISSUER:-https://auth.wolfpack.robotics-rtuitlab.ru/realms/wolfpack-control-staging}"
CRED_NS="${LOADTEST_CREDENTIALS_NS:-wolfpackcloud-control-staging}"
CRED_SECRET="${LOADTEST_CREDENTIALS_SECRET:-loadtest-credentials}"

if command -v kubectl >/dev/null 2>&1 && kubectl get secret "$CRED_SECRET" -n "$CRED_NS" >/dev/null 2>&1; then
  export KEYCLOAK_USERNAME="$(
    kubectl get secret "$CRED_SECRET" -n "$CRED_NS" -o jsonpath='{.data.username}' | base64 -d
  )"
  export KEYCLOAK_PASSWORD="$(
    kubectl get secret "$CRED_SECRET" -n "$CRED_NS" -o jsonpath='{.data.password}' | base64 -d
  )"
  echo "run-load-staging: credentials из Secret ${CRED_SECRET}/${CRED_NS}" >&2
elif [[ -z "${KEYCLOAK_USERNAME:-}" || -z "${KEYCLOAK_PASSWORD:-}" ]]; then
  echo "run-load-staging: задайте KEYCLOAK_USERNAME/PASSWORD или Secret ${CRED_SECRET} в ${CRED_NS}" >&2
  exit 1
fi

guard_prod_loadtest "$BASE_URL"
exec "${SCRIPT_DIR}/run-load.sh" "$@"
