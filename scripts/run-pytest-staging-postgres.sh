#!/usr/bin/env bash
# Обёртка: pytest на staging PostgreSQL (см. server/api/scripts/run-pytest-staging-postgres.sh).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec "${ROOT}/server/api/scripts/run-pytest-staging-postgres.sh" "$@"
