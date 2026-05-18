#!/usr/bin/env bash
# Получение access_token через OAuth2 Resource Owner Password (Direct Access Grants).
# Требует: включённый direct grant у клиента wolfpack-control-web (есть в realm-import).
#
# Обязательно в окружении:
#   KEYCLOAK_USERNAME  — пользователь realm wolfpack-control
#   KEYCLOAK_PASSWORD
#
# Опционально:
#   KEYCLOAK_ISSUER    — по умолчанию прод-кластер из манифестов Control API
#   KEYCLOAK_TOKEN_URL — полный URL /protocol/openid-connect/token (иначе из issuer)
#   KEYCLOAK_CLIENT_ID — по умолчанию wolfpack-control-web
#
# Вывод: только JWT на stdout (для export ACCESS_TOKEN="$(...)").
set -euo pipefail

ISSUER="${KEYCLOAK_ISSUER:-https://auth.wolfpack.robotics-rtuitlab.ru/realms/wolfpack-control}"
ISSUER="${ISSUER%/}"
TOKEN_URL="${KEYCLOAK_TOKEN_URL:-$ISSUER/protocol/openid-connect/token}"
CLIENT_ID="${KEYCLOAK_CLIENT_ID:-wolfpack-control-web}"
USERNAME="${KEYCLOAK_USERNAME:?Укажите KEYCLOAK_USERNAME (realm-пользователь)}"
PASSWORD="${KEYCLOAK_PASSWORD:?Укажите KEYCLOAK_PASSWORD}"

TMP="$(mktemp)"
trap 'rm -f "${TMP}"' EXIT

set +e
HTTP_CODE="$(curl -sS --connect-timeout 12 --max-time 35 -o "${TMP}" -w '%{http_code}' -X POST "$TOKEN_URL" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "grant_type=password" \
  --data-urlencode "client_id=$CLIENT_ID" \
  --data-urlencode "username=$USERNAME" \
  --data-urlencode "password=$PASSWORD" \
  --data-urlencode "scope=openid")"
RC=$?
set -e

if [[ "$RC" != "0" ]]; then
  echo "Keycloak: curl ошибка (код ${RC}), URL: ${TOKEN_URL}" >&2
  [[ -s "${TMP}" ]] && head -c 1500 "${TMP}" >&2
  exit 1
fi

if [[ "${HTTP_CODE}" != "200" ]]; then
  echo "Keycloak: HTTP ${HTTP_CODE} (ожидался 200), URL: ${TOKEN_URL}" >&2
  echo "Часто 503 + «no available server»: Ingress/прокси не видит под Keycloak или сервис недоступен из этой сети." >&2
  head -c 2000 "${TMP}" >&2 || true
  echo >&2
  exit 1
fi

RESP="$(cat "${TMP}")"

echo "$RESP" | python3 -c '
import json, sys
raw = sys.stdin.read()
try:
    d = json.loads(raw)
except json.JSONDecodeError:
    sys.stderr.write("Keycloak: ответ не JSON (URL был задан выше). Частые причины: нет маршрута с этой ноды до Keycloak, Ingress без endpoints, прокси «no available server».\n")
    sys.stderr.write("Тело ответа:\n" + raw[:2000] + "\n")
    sys.exit(1)
tok = d.get("access_token")
if not tok:
    sys.stderr.write(json.dumps(d, indent=2, ensure_ascii=False) + "\n")
    sys.exit(1)
print(tok, end="")
'
