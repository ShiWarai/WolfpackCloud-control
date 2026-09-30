# WolfpackCloud Control API

FastAPI-приложение: Keycloak JWT, PostgreSQL (SQLAlchemy async), Kubernetes client, InfluxDB для логов и событий деплоя.

## Локальный запуск

```bash
cd server/api
pip install -r requirements.txt -r requirements-dev.txt
export DATABASE_URL=postgresql+asyncpg://wolfpack_control:wolfpack_control@localhost:5433/wolfpack_control
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Удобнее через [docker-compose.dev.yml](../../docker-compose.dev.yml) (Postgres на порту **5433**).

- Swagger: http://localhost:8000/api/docs  
- Health: http://localhost:8000/health  

Переменные — [env.vars.reference](../../env.vars.reference), prod — Secret `control-api-env`.

## Миграции (Alembic)

```bash
alembic upgrade head
alembic revision --autogenerate -m "описание"   # при изменении models.py
```

Версии в `alembic/versions/` (в т.ч. `004` — удаление `ros_log_entries`, логи только в Influx).

## Тесты

См. [tests/README.md](tests/README.md).

```bash
pytest tests/
```

Staging Postgres: [scripts/run-pytest-staging-postgres.sh](../../scripts/run-pytest-staging-postgres.sh).

## Структура `app/`

| Модуль | Назначение |
|--------|------------|
| `main.py` | FastAPI app, CORS, lifespan, health |
| `config.py` | Pydantic Settings |
| `deps.py` | JWT, admin, DB session |
| `models.py`, `schemas.py` | ORM и API-схемы |
| `routers/` | HTTP-маршруты (`/api/...`) |
| `services/` | k8s, Keycloak JWT, Influx, orchestration, presets |
| `tasks.py` | APScheduler (фоновые задачи) |
| `openapi_keycloak.py` | OAuth2 в OpenAPI для Swagger |

## Деплой

Образ: `server/api/Dockerfile` (targets `development` / `production`).  
k8s: [deploy/k8s/control/api.yaml](../../deploy/k8s/control/api.yaml).

Общая документация проекта: [README.md](../../README.md).
