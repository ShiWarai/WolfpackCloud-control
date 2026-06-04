#!/usr/bin/env bash
# Обёртка: поднять staging → команда → снести namespace (если не STAGING_KEEP=1).
#
#   ./scripts/with-staging.sh ./scripts/run-pytest-staging-postgres.sh -q
#   STAGING_KEEP=1 ./scripts/with-staging.sh …   # не удалять после прогона
#   STAGING_SKIP_UP=1 ./scripts/with-staging.sh … # NS уже поднят вручную
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEARDOWN=1
[[ "${STAGING_KEEP:-}" == "1" ]] && TEARDOWN=0

cleanup() {
  local code=$?
  if [[ "$TEARDOWN" == "1" ]]; then
    "${ROOT}/scripts/staging-down.sh" || true
  fi
  exit "$code"
}
trap cleanup EXIT

if [[ "${STAGING_KEEP:-}" != "1" && "${STAGING_SKIP_PREFLIGHT_DOWN:-}" != "1" ]]; then
  "${ROOT}/scripts/staging-down.sh" || true
fi

if [[ "${STAGING_SKIP_UP:-}" != "1" ]]; then
  "${ROOT}/scripts/staging-up.sh"
fi

if [[ $# -lt 1 ]]; then
  echo "with-staging: укажите команду" >&2
  exit 2
fi

"$@"
