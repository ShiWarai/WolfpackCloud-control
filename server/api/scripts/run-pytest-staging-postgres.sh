#!/usr/bin/env bash
# Pytest против PostgreSQL на staging (отдельная БД wolfpack_control_pytest).
#
# Не трогает wolfpack_control_staging (данные staging API). Нужны kubectl и port-forward до postgres.
#
# Пример:
#   ./scripts/run-pytest-staging-postgres.sh
#   ./scripts/run-pytest-staging-postgres.sh tests/test_routers_crud.py -q
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
NS="${STAGING_NS:-wolfpackcloud-control-staging}"
SECRET="${POSTGRES_SECRET:-control-postgres-secret}"
LOCAL_PORT="${POSTGRES_LOCAL_PORT:-15432}"
DB_NAME="${PYTEST_DATABASE_NAME:-wolfpack_control_pytest}"

die() {
  echo "run-pytest-staging-postgres: $*" >&2
  exit 1
}

command -v kubectl >/dev/null || die "kubectl не найден"
command -v python3 >/dev/null || die "python3 не найден"

kubectl get secret "$SECRET" -n "$NS" >/dev/null 2>&1 \
  || die "Secret ${SECRET} не найден в ${NS} — поднимите staging (deploy/k8s/staging/)"

export _PG_USER="$(
  kubectl get secret "$SECRET" -n "$NS" -o jsonpath='{.data.username}' | base64 -d
)"
export _PG_PASS="$(
  kubectl get secret "$SECRET" -n "$NS" -o jsonpath='{.data.password}' | base64 -d
)"
export _PG_PORT="$LOCAL_PORT"
export _PG_DB="$DB_NAME"

PF_PID=""
cleanup() {
  if [[ -n "${PF_PID}" ]] && kill -0 "${PF_PID}" 2>/dev/null; then
    kill "${PF_PID}" 2>/dev/null || true
    wait "${PF_PID}" 2>/dev/null || true
  fi
}
trap cleanup EXIT

kubectl port-forward -n "$NS" "svc/postgres" "${LOCAL_PORT}:5432" >/dev/null 2>&1 &
PF_PID=$!

python3 <<'PY'
import asyncio
import os
import re
import sys

import asyncpg

host = "127.0.0.1"
port = int(os.environ["_PG_PORT"])
user = os.environ["_PG_USER"]
password = os.environ["_PG_PASS"]
db = os.environ["_PG_DB"]

if not re.fullmatch(r"[a-z][a-z0-9_]*", db):
    sys.exit("invalid database name")


async def wait_postgres() -> None:
    for _ in range(30):
        try:
            conn = await asyncpg.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                database="postgres",
                timeout=2,
            )
            await conn.close()
            return
        except Exception:
            await asyncio.sleep(1)
    sys.exit("postgres port-forward did not become ready")


async def ensure_db() -> None:
    await wait_postgres()
    conn = await asyncpg.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database="postgres",
    )
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", db)
        if not exists:
            await conn.execute(f'CREATE DATABASE "{db}"')
            print(f"Created database {db}", file=sys.stderr)
    finally:
        await conn.close()


asyncio.run(ensure_db())
PY

ENC_PASS="$(python3 -c "import os, urllib.parse; print(urllib.parse.quote(os.environ['_PG_PASS'], safe=''))")"
export DATABASE_URL="postgresql+asyncpg://${_PG_USER}:${ENC_PASS}@127.0.0.1:${LOCAL_PORT}/${DB_NAME}"
export TESTING_POSTGRES=1
export INFLUXDB_URL=""
export INFLUXDB_TOKEN=""

echo "run-pytest-staging-postgres: DATABASE_URL → ${DB_NAME} @ 127.0.0.1:${LOCAL_PORT}" >&2

cd "${API_ROOT}"
if [[ $# -eq 0 ]]; then
  exec python3 -m pytest tests/
else
  exec python3 -m pytest "$@"
fi
