#!/usr/bin/env bash
set -euo pipefail

DATA_DIR="${WPC_DATA_DIR:-/var/lib/wpc-agent}"
TOKEN_FILE="${DATA_DIR}/.robot_token"
CONF_FILE="${DATA_DIR}/telegraf.conf"
SERVER_URL="${WPC_SERVER_URL:-http://control-api.wolfpackcloud-control.svc.cluster.local:8000}"
METRICS_URL="${WPC_METRICS_URL:-${SERVER_URL%/}/api/metrics}"
ROBOT_NAME="${WPC_ROBOT_NAME:-${HOSTNAME:-demo-robot}}"
POLL_SEC="${WPC_PAIR_POLL_SEC:-5}"
TIMEOUT_SEC="${WPC_PAIR_TIMEOUT_SEC:-900}"

mkdir -p "${DATA_DIR}"

log() {
  echo "[robot-agent] $*"
}

detect_arch() {
  if [[ -n "${WPC_ARCH:-}" ]]; then
    echo "${WPC_ARCH}"
    return
  fi
  case "$(uname -m)" in
    x86_64) echo "amd64" ;;
    aarch64 | arm64) echo "arm64" ;;
    armv7l | armhf) echo "armhf" ;;
    *) log "Неподдерживаемая архитектура: $(uname -m)"; exit 1 ;;
  esac
}

get_ip_address() {
  if [[ -n "${POD_IP:-}" ]]; then
    echo "${POD_IP}"
    return
  fi
  hostname -i 2>/dev/null | awk '{print $1}' || echo "unknown"
}

generate_pair_code() {
  local chars="ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
  local code="" i idx
  for i in $(seq 1 8); do
    idx=$((RANDOM % ${#chars}))
    code="${code}${chars:idx:1}"
  done
  echo "${code}"
}

write_telegraf_conf() {
  local robot_token="$1"
  local robot_name="$2"
  local arch="$3"

  cat >"${CONF_FILE}" <<EOF
# WolfpackCloud Control robot-agent (generated $(date -Iseconds))

[global_tags]
  robot = "${robot_name}"
  hostname = "${HOSTNAME:-${robot_name}}"
  arch = "${arch}"

[agent]
  interval = "10s"
  round_interval = true
  metric_batch_size = 1000
  metric_buffer_limit = 10000
  flush_interval = "10s"
  omit_hostname = false

[[outputs.http]]
  url = "${METRICS_URL}"
  method = "POST"
  data_format = "influx"
  timeout = "10s"
  content_encoding = "gzip"
  [outputs.http.headers]
    Authorization = "Bearer ${robot_token}"
    Content-Type = "text/plain; charset=utf-8"

[[inputs.cpu]]
  percpu = true
  totalcpu = true

[[inputs.mem]]
[[inputs.disk]]
  ignore_fs = ["tmpfs", "devtmpfs", "devfs", "iso9660", "overlay", "aufs", "squashfs"]
[[inputs.diskio]]
[[inputs.net]]
[[inputs.system]]
[[inputs.processes]]
[[inputs.kernel]]
EOF
}

register_and_wait() {
  local hostname arch ip pair_code elapsed=0 response status robot_token

  hostname="${HOSTNAME:-${ROBOT_NAME}}"
  arch="$(detect_arch)"
  ip="$(get_ip_address)"
  pair_code="$(generate_pair_code)"

  log "Регистрация робота name=${ROBOT_NAME} hostname=${hostname} arch=${arch} ip=${ip}"
  response="$(
    curl -fsSL -X POST "${SERVER_URL%/}/api/pair" \
      -H "Content-Type: application/json" \
      -d "$(jq -n \
        --arg hostname "${hostname}" \
        --arg name "${ROBOT_NAME}" \
        --arg ip "${ip}" \
        --arg arch "${arch}" \
        --arg code "${pair_code}" \
        '{hostname: $hostname, name: $name, ip_address: $ip, architecture: $arch, pair_code: $code}')"
  )" || {
    log "Не удалось зарегистрировать робота на ${SERVER_URL}"
    exit 1
  }

  log "Код привязки: ${pair_code} (подтвердите в Control → /pairing, TTL ~15 мин)"
  echo ""
  echo "╔══════════════════════════════════════════════════════════════════╗"
  echo "║  Код привязки: ${pair_code}                                      "
  echo "║  Подтвердите в UI: Control → Привязка                            ║"
  echo "╚══════════════════════════════════════════════════════════════════╝"
  echo ""

  while [[ "${elapsed}" -lt "${TIMEOUT_SEC}" ]]; do
    response="$(curl -sfL "${SERVER_URL%/}/api/pair/${pair_code}/status" 2>/dev/null || echo "")"
    if [[ -z "${response}" ]]; then
      log "API недоступен, повтор через ${POLL_SEC}s..."
      sleep "${POLL_SEC}"
      elapsed=$((elapsed + POLL_SEC))
      continue
    fi

    status="$(echo "${response}" | jq -r '.status // empty')"
    case "${status}" in
      confirmed)
        robot_token="$(echo "${response}" | jq -r '.robot_token // empty')"
        if [[ -z "${robot_token}" ]]; then
          log "Подтверждено, но robot_token пуст — проверьте API"
          exit 1
        fi
        echo "${robot_token}" >"${TOKEN_FILE}"
        chmod 600 "${TOKEN_FILE}"
        write_telegraf_conf "${robot_token}" "${ROBOT_NAME}" "${arch}"
        log "Привязка подтверждена, запуск Telegraf"
        return 0
        ;;
      expired)
        log "Код ${pair_code} истёк — перезапустите pod"
        exit 1
        ;;
      pending)
        printf "."
        ;;
      *)
        log "Неожиданный статус: ${status}"
        ;;
    esac

    sleep "${POLL_SEC}"
    elapsed=$((elapsed + POLL_SEC))
  done

  echo ""
  log "Таймаут ожидания подтверждения (${TIMEOUT_SEC}s)"
  exit 1
}

start_telegraf() {
  exec telegraf --config "${CONF_FILE}"
}

if [[ -f "${TOKEN_FILE}" && -f "${CONF_FILE}" ]]; then
  log "Найден сохранённый токен — запуск Telegraf без повторной регистрации"
  start_telegraf
fi

register_and_wait
start_telegraf
