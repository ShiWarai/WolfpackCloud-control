#!/usr/bin/env bash
# Сносит «залипшие» peer/zenoh поды в wolfpackcloud-zenoh (Terminating, Completed, Unknown,
# часть Failed). Не трогает zenoh-router, если не передать --with-router.
#
# Использование:
#   ./cleanup-stuck-peer-pods.sh
#   ./cleanup-stuck-peer-pods.sh --with-router   # в т.ч. перезапуск router (осторожно)
#
set -euo pipefail

NS="${FULL_LOADTEST_NAMESPACE:-wolfpackcloud-zenoh}"
WITH_ROUTER=0
[[ "${1:-}" == "--with-router" ]] && WITH_ROUTER=1

need_cmd() { command -v "$1" >/dev/null 2>&1 || { echo "нужна команда: $1" >&2; exit 1; }; }
need_cmd kubectl

echo "=== Namespace: $NS — принудительное удаление зависших подов ==="

# Terminating / финальные фазы по имени compute-peer / compute-peer-gamma
while read -r name ready status rest; do
  [[ -z "${name:-}" ]] && continue
  if [[ "${WITH_ROUTER}" == "0" ]] && [[ "${name}" == zenoh-router-* ]]; then
    continue
  fi
  case "${status}" in
    Terminating|Completed|Succeeded|Failed|Unknown|ContainerStatusUnknown)
      echo "force-delete: ${name} (${status})"
      kubectl delete pod -n "${NS}" "${name}" --ignore-not-found=true --force --grace-period=0 2>/dev/null || true
      ;;
  esac
done < <(kubectl get pods -n "${NS}" --no-headers 2>/dev/null || true)

echo "=== Оставшиеся поды ==="
kubectl get pods -n "${NS}" -o wide || true
