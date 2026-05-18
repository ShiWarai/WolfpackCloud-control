#!/usr/bin/env bash
# Полный цикл нагрузочного теста:
#   1) Zenoh (kustomize)
#   2) Peer hammer + очистка peer-подов на запрещённых нодах (Сбер, телефон, …)
#   3) Сразу в фоне: k6 (HTTP), если есть JWT — параллельно с rollout peers
#   4) rollout alpha/beta
#   5) soak (k6 обычно ещё идёт)
#   6) дождаться конца k6
#   7) restore базовых peers + снова purge на запрещённых нодах
#
# Переменные окружения:
#   FULL_LOADTEST_SKIP_ZENOH=1
#   FULL_LOADTEST_SKIP_HTTP=1
#   FULL_LOADTEST_REQUIRE_HTTP=1
#   FULL_LOADTEST_SKIP_RESTORE=1
#   FULL_LOADTEST_PEER_REPLICAS=N
#   FULL_LOADTEST_SOAK_SEC=25           — пауза после rollout пока идёт k6 (по умолчанию 25)
#   FULL_LOADTEST_ROLLOUT_TIMEOUT=600
#   FULL_LOADTEST_SCALE_GAMMA_ZERO=1   — до старта hammer выставить gamma в 0
#   FULL_LOADTEST_SKIP_PURGE=1        — не удалять поды на запрещённых нодах
#   FULL_LOADTEST_PURGE_NODES="sber alphie-phone-1" — hostname(s), пробел-разделитель
#   FULL_LOADTEST_HTTP_ONLY=1 — только k6 на Control API (./run-load.sh), без kubectl и без подов Zenoh/peers
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
NS="${FULL_LOADTEST_NAMESPACE:-wolfpackcloud-zenoh}"

ZENOH_K="$REPO_ROOT/deploy/k3s/zenoh"
PEERS_BASE_K="$REPO_ROOT/deploy/k3s/wolfpackcloud-control-peers"
PEERS_HAMMER_K="$SCRIPT_DIR/k8s-zenoh-peers-loadtest"

SOAK_SEC="${FULL_LOADTEST_SOAK_SEC:-25}"
ROLL_TIMEOUT="${FULL_LOADTEST_ROLLOUT_TIMEOUT:-600}"
PURGE_NODES="${FULL_LOADTEST_PURGE_NODES:-sber alphie-phone-1}"

K6_PID=""
stop_k6_on_signal() {
  if [[ -n "${K6_PID}" ]] && kill -0 "${K6_PID}" 2>/dev/null; then
    echo "full-loadtest-cycle: прерывание — останавливаю k6 (PID ${K6_PID})" >&2
    kill "${K6_PID}" 2>/dev/null || true
    wait "${K6_PID}" 2>/dev/null || true
  fi
}
trap stop_k6_on_signal INT TERM

die() {
  echo "full-loadtest-cycle: $*" >&2
  exit 1
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "нужна команда: $1"
}

phase() {
  echo ""
  echo "=== $* ==="
}

# Удаляет peer-поды на указанных нодах (после смены affinity они пересоздадутся не там).
purge_peer_pods_on_forbidden_nodes() {
  if [[ "${FULL_LOADTEST_SKIP_PURGE:-}" == "1" ]]; then
    phase "Пропуск purge (FULL_LOADTEST_SKIP_PURGE=1)"
    return 0
  fi
  phase "Purge peer-подов на нодах: ${PURGE_NODES}"
  local nod
  for nod in ${PURGE_NODES}; do
    [[ -z "${nod}" ]] && continue
    kubectl delete pods -n "${NS}" \
      -l app.kubernetes.io/component=wolfpackcloud-compute-instance-peer \
      --field-selector="spec.nodeName=${nod}" \
      --wait=false 2>/dev/null || true
  done
}

if [[ "${FULL_LOADTEST_HTTP_ONLY:-}" == "1" ]]; then
  need_cmd k6
  phase "Только HTTP/k6 (FULL_LOADTEST_HTTP_ONLY=1) — кластерные Zenoh/peers не трогаем"
  cd "$SCRIPT_DIR" || die "cd loadtests"
  exec ./run-load.sh "$@"
fi

need_cmd kubectl

for path in "$ZENOH_K" "$PEERS_BASE_K" "$PEERS_HAMMER_K"; do
  [[ -d "$path" ]] || die "нет каталога: $path"
done

phase "Проверка контекста kubectl"
kubectl cluster-info >/dev/null || die "kubectl не видит кластер"

if [[ "${FULL_LOADTEST_SKIP_ZENOH:-}" != "1" ]]; then
  phase "Применить Zenoh ($ZENOH_K)"
  kubectl apply -k "$ZENOH_K"
else
  phase "Пропуск Zenoh (FULL_LOADTEST_SKIP_ZENOH=1)"
fi

if [[ "${FULL_LOADTEST_SCALE_GAMMA_ZERO:-}" == "1" ]]; then
  phase "Gamma → 0 реплик (если объект есть)"
  kubectl -n "$NS" scale deployment/compute-peer-gamma --replicas=0 2>/dev/null || true
fi

phase "Применить peer hammer ($PEERS_HAMMER_K)"
kubectl apply -k "$PEERS_HAMMER_K"

if [[ -n "${FULL_LOADTEST_PEER_REPLICAS:-}" ]]; then
  phase "Масштабирование alpha/beta → ${FULL_LOADTEST_PEER_REPLICAS} реплик"
  kubectl -n "$NS" scale deployment/compute-peer-alpha deployment/compute-peer-beta \
    --replicas="${FULL_LOADTEST_PEER_REPLICAS}"
fi

purge_peer_pods_on_forbidden_nodes

HTTP_RAN=0
HTTP_SKIP_REASON=""

# Фоновый subshell наследует только экспортированные переменные: явно export учётки Keycloak / BASE_URL.
export_http_env_for_child() {
  local __v
  for __v in BASE_URL KEYCLOAK_USERNAME KEYCLOAK_PASSWORD KEYCLOAK_ISSUER KEYCLOAK_TOKEN_URL KEYCLOAK_CLIENT_ID ACCESS_TOKEN; do
    if [[ -n "${!__v:-}" ]]; then
      export "${__v}"
    fi
  done
}

if [[ "${FULL_LOADTEST_SKIP_HTTP:-}" != "1" ]]; then
  if [[ -n "${BASE_URL:-}" && -n "${KEYCLOAK_USERNAME:-}" && -n "${KEYCLOAK_PASSWORD:-}" ]]; then
    need_cmd k6
    export_http_env_for_child
    phase "Старт k6 в фоне — параллельно rollout peers (HTTP + ROS одновременно)"
    (cd "$SCRIPT_DIR" && ./run-load.sh "$@") &
    K6_PID=$!
  else
    HTTP_SKIP_REASON="не заданы BASE_URL и/или KEYCLOAK_USERNAME и/или KEYCLOAK_PASSWORD (в этом shell нет учётки для fetch-keycloak-token)"
    if [[ "${FULL_LOADTEST_REQUIRE_HTTP:-}" == "1" ]]; then
      die "FULL_LOADTEST_REQUIRE_HTTP=1, но ${HTTP_SKIP_REASON}"
    fi
    phase "HTTP/k6 пропущен: ${HTTP_SKIP_REASON}"
  fi
else
  HTTP_SKIP_REASON="FULL_LOADTEST_SKIP_HTTP=1"
  phase "HTTP/k6 отключён (${HTTP_SKIP_REASON})"
fi

phase "Rollout alpha/beta (${ROLL_TIMEOUT}s) — пока идёт k6 в фоне"
kubectl -n "$NS" rollout status deployment/compute-peer-alpha --timeout="${ROLL_TIMEOUT}s"
kubectl -n "$NS" rollout status deployment/compute-peer-beta --timeout="${ROLL_TIMEOUT}s"

phase "Сводка подов ($NS)"
kubectl -n "$NS" get pods -l app.kubernetes.io/component=wolfpackcloud-compute-instance-peer -o wide || true

if [[ -n "${K6_PID}" ]]; then
  phase "Soak ${SOAK_SEC}s — Zenoh peers и k6 одновременно"
  sleep "${SOAK_SEC}"
  phase "Дождаться завершения k6 (PID ${K6_PID})"
  wait "${K6_PID}" || true
  HTTP_RAN=1
else
  phase "Soak ${SOAK_SEC}s (только peers)"
  sleep "${SOAK_SEC}"
fi

if [[ "${FULL_LOADTEST_SKIP_RESTORE:-}" == "1" ]]; then
  phase "Пропуск восстановления базовых peers (FULL_LOADTEST_SKIP_RESTORE=1)"
else
  phase "Восстановление базового деплоя peers ($PEERS_BASE_K)"
  kubectl apply -k "$PEERS_BASE_K"
  purge_peer_pods_on_forbidden_nodes
  kubectl -n "$NS" rollout status deployment/compute-peer-alpha --timeout="${ROLL_TIMEOUT}s" || true
  kubectl -n "$NS" rollout status deployment/compute-peer-beta --timeout="${ROLL_TIMEOUT}s" || true
  kubectl -n "$NS" rollout status deployment/compute-peer-gamma --timeout="${ROLL_TIMEOUT}s" || true
fi

phase "Готово"
echo ""
echo "--- Итог full-loadtest-cycle ---"
echo "  HTTP (k6): ${HTTP_RAN}  (1 = был запуск и дошли до wait k6)"
if [[ "${HTTP_RAN}" == "0" ]]; then
  echo "  Причина без k6: ${HTTP_SKIP_REASON:-неизвестно}"
  echo "  Чтобы увидеть таблицу метрик k6: export BASE_URL KEYCLOAK_USERNAME KEYCLOAK_PASSWORD и без FULL_LOADTEST_SKIP_HTTP."
fi
echo "  soak: ${SOAK_SEC}s | purge nodes: ${PURGE_NODES} | ns: ${NS}"
echo "  ROS/Zenoh: смотрите логи подов compute-peer-* и zenoh-router (kubectl logs)."
echo "--------------------------------"
