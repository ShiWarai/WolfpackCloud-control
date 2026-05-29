#!/usr/bin/env bash
# Сценарий с JWT + усиленный k6 (см. control-api-load.js).
#
# Обязательно:
#   BASE_URL           — например https://wolfpack.robotics-rtuitlab.ru
#   KEYCLOAK_USERNAME, KEYCLOAK_PASSWORD — см. fetch-keycloak-token.sh (если не задан ACCESS_TOKEN)
#
# Опционально заранее:
#   ACCESS_TOKEN       — если уже есть JWT, fetch-keycloak-token.sh не вызывается
#
# Доп. аргументы k6 и переменные сценария: см. заголовок control-api-load.js
#
# Пример:
#   export BASE_URL=https://wolfpack.robotics-rtuitlab.ru
#   export KEYCLOAK_USERNAME=wolfpack-operator
#   export KEYCLOAK_PASSWORD='***'
#   ./run-load.sh
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# shellcheck source=guard-prod-loadtest.sh
source "${SCRIPT_DIR}/guard-prod-loadtest.sh"

export BASE_URL="${BASE_URL:?Задайте BASE_URL (хост Ingress без завершающего /)}"
guard_prod_loadtest "$BASE_URL"

# Токен: либо уже в окружении (например выставили вручную), иначе Keycloak password grant.
if [[ -z "${ACCESS_TOKEN:-}" ]]; then
  export ACCESS_TOKEN="$("${SCRIPT_DIR}/fetch-keycloak-token.sh")"
fi
# Убираем CR/LF на случай странного окружения
ACCESS_TOKEN="$(printf '%s' "${ACCESS_TOKEN}" | tr -d '\r\n')"
export ACCESS_TOKEN
if [[ ${#ACCESS_TOKEN} -lt 50 ]]; then
  echo "run-load.sh: ACCESS_TOKEN пустой или подозрительно короткий после получения токена." >&2
  echo "Задайте KEYCLOAK_USERNAME / KEYCLOAK_PASSWORD (и при необходимости KEYCLOAK_ISSUER) или экспортируйте ACCESS_TOKEN сами." >&2
  exit 1
fi

exec k6 run "${SCRIPT_DIR}/control-api-load.js" \
  "$@" \
  -e BASE_URL="$BASE_URL" \
  -e ACCESS_TOKEN="$ACCESS_TOKEN"
