#!/usr/bin/env bash
set -euo pipefail

workers="${UVICORN_WORKERS:-3}"
exec uvicorn app.main:app --host "0.0.0.0" --port "8000" --workers "${workers}"
