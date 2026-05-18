#!/bin/bash
set -e

echo "=== WolfpackCloud Control API ==="

echo "Ожидание PostgreSQL..."
max_attempts=30
attempt=0
while [ $attempt -lt $max_attempts ]; do
    if python -c "
import asyncio
import asyncpg
import os

async def check():
    try:
        url = os.environ.get('DATABASE_URL', '')
        url = url.replace('postgresql+asyncpg://', 'postgresql://')
        conn = await asyncpg.connect(url)
        await conn.close()
        return True
    except Exception:
        return False

exit(0 if asyncio.run(check()) else 1)
" 2>/dev/null; then
        echo "PostgreSQL готов"
        break
    fi
    attempt=$((attempt + 1))
    echo "Попытка $attempt/$max_attempts..."
    sleep 2
done

echo "Запуск миграций..."
alembic upgrade head || echo "WARN: alembic upgrade failed"

echo "Запуск приложения..."
exec "$@"
