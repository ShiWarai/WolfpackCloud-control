#!/usr/bin/env bash
# Fail-fast: блокирует нагрузку на prod Ingress без явного ALLOW_PROD_LOADTEST=1.
# Подключение: source "$(dirname "$0")/guard-prod-loadtest.sh"
guard_prod_loadtest() {
  local base="${1%/}"
  if [[ "${ALLOW_PROD_LOADTEST:-}" == "1" ]]; then
    return 0
  fi
  case "$base" in
    https://wolfpack.robotics-rtuitlab.ru | http://wolfpack.robotics-rtuitlab.ru)
      echo "guard-prod-loadtest: отказ — BASE_URL указывает на production (${base})." >&2
      echo "Используйте ./run-load-staging.sh или export ALLOW_PROD_LOADTEST=1 для явного prod-прогона." >&2
      exit 1
      ;;
  esac
}
