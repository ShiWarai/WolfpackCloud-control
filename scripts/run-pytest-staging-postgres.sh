#!/usr/bin/env bash
# Pytest на staging Postgres: поднимает NS, прогон, удаляет NS (см. scripts/with-staging.sh).
# STAGING_KEEP=1 — оставить namespace; STAGING_SKIP_LIFECYCLE=1 — только pytest (NS уже есть).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ "${STAGING_SKIP_LIFECYCLE:-}" == "1" ]]; then
  exec "${ROOT}/server/api/scripts/run-pytest-staging-postgres.sh" "$@"
fi
exec "${ROOT}/scripts/with-staging.sh" "${ROOT}/server/api/scripts/run-pytest-staging-postgres.sh" "$@"
