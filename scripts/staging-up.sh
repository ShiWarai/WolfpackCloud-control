#!/usr/bin/env bash
# Поднять wolfpackcloud-control-staging (Postgres + API + ingress).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NS="${STAGING_NS:-wolfpackcloud-control-staging}"
STAGING_K="${ROOT}/deploy/k8s/staging"
KC_DIR="${ROOT}/deploy/k8s/keycloak"
WAIT="${STAGING_ROLLOUT_TIMEOUT:-300s}"

die() { echo "staging-up: $*" >&2; exit 1; }

command -v kubectl >/dev/null || die "kubectl не найден"

infra="${STAGING_INFRA_SECRETS:-${STAGING_K}/control-infra-secrets-staging.yaml}"
api_sec="${STAGING_API_SECRETS:-${STAGING_K}/api-secret-staging.yaml}"
loadtest="${STAGING_LOADTEST_SECRETS:-${KC_DIR}/loadtest-credentials.yaml}"

[[ -f "$infra" ]] || die "нет ${infra} (cp control-infra-secrets-staging.example.yaml)"
[[ -f "$api_sec" ]] || die "нет ${api_sec} (cp api-secret-staging.example.yaml)"

echo "staging-up: namespace → secrets → manifests (${NS})" >&2
kubectl apply -f "${STAGING_K}/namespace.yaml"
kubectl apply -f "$infra" -f "$api_sec"
if [[ -f "$loadtest" ]]; then
  kubectl apply -f "$loadtest"
else
  echo "staging-up: пропуск loadtest-credentials (нет ${loadtest})" >&2
fi

kubectl apply -k "$STAGING_K"
kubectl apply -f "${STAGING_K}/rbac-zenoh-binding.yaml"

echo "staging-up: ожидание postgres" >&2
kubectl rollout status deployment/postgres -n "$NS" --timeout="${WAIT}"

echo "staging-up: ожидание control-api" >&2
kubectl rollout status deployment/control-api -n "$NS" --timeout="${WAIT}"

if [[ "${STAGING_SEED_KEYCLOAK:-1}" == "1" ]] && [[ -x "${ROOT}/scripts/keycloak-seed-staging-users.sh" ]]; then
  if [[ -f "$loadtest" ]]; then
    "${ROOT}/scripts/keycloak-seed-staging-users.sh" || echo "staging-up: keycloak seed пропущен (ошибка)" >&2
  fi
fi

kubectl get pods -n "$NS" -o wide
echo "staging-up: готово" >&2
