# API tests (pytest)

## Быстрый прогон (SQLite, без k8s)

- **БД:** SQLite in-memory (`DATABASE_URL=sqlite+aiosqlite:///:memory:`)
- **Auth:** локальный RS256 JWT через `mint_access_token` / `make_access_token`; JWKS подменён в `conftest.py`
- **Keycloak не нужен** — пользователи создаются через `_seed_user()` или auto-sync из JWT в `app/deps.py`

```bash
cd server/api
pip install -r requirements.txt -r requirements-dev.txt
pytest tests/
```

## PostgreSQL (staging Postgres в k8s)

Отдельная БД **`wolfpack_control_pytest`** на том же Postgres, что и staging API (`wolfpack_control_staging` не трогается). Схема через **Alembic**; каждый тест в транзакции с rollback.

```bash
cd WolfpackCloud-control
chmod +x scripts/run-pytest-staging-postgres.sh
./scripts/run-pytest-staging-postgres.sh
# или один файл (путь относительно server/api/tests/):
./scripts/run-pytest-staging-postgres.sh tests/test_routers_crud.py -q
```

Нужны: `kubectl`, доступ к namespace `wolfpackcloud-control-staging`, Secret `control-postgres-secret`.

Переменные: `STAGING_NS`, `POSTGRES_LOCAL_PORT` (default 15432), `PYTEST_DATABASE_NAME`.

Фикстуры:

| Фикстура | Назначение |
|----------|------------|
| `make_access_token` | Произвольный JWT с нужными roles |
| `standard_user_token` | role `user` (аналог staging `loadtest-user`) |
| `admin_token` | roles `admin`, `user` (аналог staging `loadtest-admin`) |
| `async_client` | httpx ASGI client |

## Load / e2e (staging k8s)

HTTP-нагрузка и browser e2e требуют **настоящий JWT** от Keycloak:

- Namespace `wolfpackcloud-control-staging`
- Realm `wolfpack-control-staging`
- Secret `loadtest-credentials`

См. [`deploy/k8s/staging/README.md`](../../deploy/k8s/staging/README.md) и [`loadtests/README.md`](../../loadtests/README.md).

**Не смешивайте:** pytest SQLite — локально; pytest PostgreSQL — `scripts/run-pytest-staging-postgres.sh`; k6/e2e — staging API (prod load — `ALLOW_PROD_LOADTEST=1`).
