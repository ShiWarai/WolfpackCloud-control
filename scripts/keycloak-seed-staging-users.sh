#!/usr/bin/env bash
# Idempotent: создаёт loadtest-user и loadtest-admin в realm wolfpack-control-staging.
#
# Требует: kubectl, curl, python3; Keycloak доступен (Ingress или port-forward).
#
# Переменные (или Secret loadtest-credentials в wolfpackcloud-control-staging):
#   LOADTEST_CREDENTIALS_SECRET  — default loadtest-credentials
#   LOADTEST_CREDENTIALS_NS      — default wolfpackcloud-control-staging
#   KEYCLOAK_ADMIN_URL           — default https://auth.wolfpack.robotics-rtuitlab.ru
#   KEYCLOAK_REALM               — default wolfpack-control-staging
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

CRED_SECRET="${LOADTEST_CREDENTIALS_SECRET:-loadtest-credentials}"
CRED_NS="${LOADTEST_CREDENTIALS_NS:-wolfpackcloud-control-staging}"
KC_ADMIN_URL="${KEYCLOAK_ADMIN_URL:-https://auth.wolfpack.robotics-rtuitlab.ru}"
KC_REALM="${KEYCLOAK_REALM:-wolfpack-control-staging}"
KC_AUTH_NS="${KEYCLOAK_AUTH_NS:-wolfpackcloud-auth}"

read_secret() {
  local key="$1"
  kubectl get secret "$CRED_SECRET" -n "$CRED_NS" -o "jsonpath={.data.${key}}" 2>/dev/null | base64 -d
}

ADMIN_USER="${KEYCLOAK_ADMIN_USER:-admin}"
ADMIN_PASS="$(kubectl get secret keycloak-admin-secret -n "$KC_AUTH_NS" -o jsonpath='{.data.admin-password}' | base64 -d)"
ADMIN_USER_PASS="${LOADTEST_ADMIN_PASSWORD:-$(read_secret password)}"
ADMIN_USERNAME="${LOADTEST_ADMIN_USERNAME:-$(read_secret username)}"
USER_PASS="${LOADTEST_USER_PASSWORD:-$(read_secret user-password)}"
USER_USERNAME="${LOADTEST_USER_USERNAME:-$(read_secret user-username)}"

if [[ -z "$ADMIN_PASS" || -z "$ADMIN_USER_PASS" || -z "$USER_PASS" ]]; then
  echo "Задайте Secret $CRED_SECRET в $CRED_NS (см. deploy/k8s/keycloak/loadtest-credentials.example.yaml)" >&2
  exit 1
fi

TOKEN="$(
  curl -sS --connect-timeout 15 --max-time 45 -X POST \
    "${KC_ADMIN_URL}/realms/master/protocol/openid-connect/token" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    --data-urlencode "grant_type=password" \
    --data-urlencode "client_id=admin-cli" \
    --data-urlencode "username=${ADMIN_USER}" \
    --data-urlencode "password=${ADMIN_PASS}" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])'
)"

ensure_user() {
  local username="$1"
  local password="$2"
  local email="$3"
  shift 3
  local roles=("$@")

  local uid
  uid="$(curl -sS -G "${KC_ADMIN_URL}/admin/realms/${KC_REALM}/users" \
    -H "Authorization: Bearer ${TOKEN}" \
    --data-urlencode "username=${username}" \
    | python3 -c 'import json,sys; u=json.load(sys.stdin); print(u[0]["id"] if u else "")')"

  if [[ -z "$uid" ]]; then
    uid="$(curl -sS -X POST "${KC_ADMIN_URL}/admin/realms/${KC_REALM}/users" \
      -H "Authorization: Bearer ${TOKEN}" \
      -H "Content-Type: application/json" \
      -d "{\"username\":\"${username}\",\"email\":\"${email}\",\"firstName\":\"Load\",\"lastName\":\"Test\",\"emailVerified\":true,\"enabled\":true,\"requiredActions\":[]}" \
      -w '%{http_code}' -o /dev/null)"
    if [[ "$uid" != "201" ]]; then
      echo "Не удалось создать пользователя ${username} (HTTP ${uid})" >&2
      exit 1
    fi
    uid="$(curl -sS -G "${KC_ADMIN_URL}/admin/realms/${KC_REALM}/users" \
      -H "Authorization: Bearer ${TOKEN}" \
      --data-urlencode "username=${username}" \
      | python3 -c 'import json,sys; print(json.load(sys.stdin)[0]["id"])')"
    echo "Создан пользователь ${username}"
  else
    echo "Пользователь ${username} уже существует"
  fi

  curl -sS -X PUT "${KC_ADMIN_URL}/admin/realms/${KC_REALM}/users/${uid}/reset-password" \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "Content-Type: application/json" \
    -d "{\"type\":\"password\",\"value\":\"${password}\",\"temporary\":false}" \
    -o /dev/null

  curl -sS -X PUT "${KC_ADMIN_URL}/admin/realms/${KC_REALM}/users/${uid}" \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "Content-Type: application/json" \
    -d "{\"firstName\":\"Load\",\"lastName\":\"Test\",\"emailVerified\":true,\"enabled\":true,\"requiredActions\":[]}" \
    -o /dev/null

  for role in "${roles[@]}"; do
    local rid
    rid="$(curl -sS "${KC_ADMIN_URL}/admin/realms/${KC_REALM}/roles/${role}" \
      -H "Authorization: Bearer ${TOKEN}" \
      | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')"
    curl -sS -X POST "${KC_ADMIN_URL}/admin/realms/${KC_REALM}/users/${uid}/role-mappings/realm" \
      -H "Authorization: Bearer ${TOKEN}" \
      -H "Content-Type: application/json" \
      -d "[{\"id\":\"${rid}\",\"name\":\"${role}\"}]" \
      -o /dev/null
  done
}

echo "Seed Keycloak realm ${KC_REALM} @ ${KC_ADMIN_URL}"
ensure_user "$USER_USERNAME" "$USER_PASS" "${USER_USERNAME}@staging.local" user
ensure_user "$ADMIN_USERNAME" "$ADMIN_USER_PASS" "${ADMIN_USERNAME}@staging.local" admin user
echo "Готово."
