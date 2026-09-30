#!/usr/bin/env bash
# k6 на staging: поднимает wolfpackcloud-control-staging, гоняет load, удаляет NS.
#
# STAGING_KEEP=1 — не удалять namespace после прогона.
# STAGING_SKIP_LIFECYCLE=1 — только k6 (как раньше, NS вручную).
#
# Перед k6 (если NS уже поднят): port-forward на 18081, см. deploy/k8s/staging/README.md
# Пример: ./run-load-staging.sh -e VUS_MAX=25
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

if [[ "${STAGING_SKIP_LIFECYCLE:-}" == "1" ]]; then
  exec "${SCRIPT_DIR}/run-load-staging-inner.sh" "$@"
fi

exec "${REPO_ROOT}/scripts/with-staging.sh" "${SCRIPT_DIR}/run-load-staging-inner.sh" "$@"
