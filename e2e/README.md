# Browser E2E (Selenium)

Смок после деплоя UI + Keycloak: вход и страница оркестрации.

Рекомендуется **staging**: realm `wolfpack-control-staging`, пользователи из Secret `loadtest-credentials` (см. [`deploy/k8s/staging/README.md`](../deploy/k8s/staging/README.md)).

## Зависимости

```bash
cd WolfpackCloud-control/e2e
pip install -r requirements-e2e.txt
```

Нужен **Chrome/Chromium** в `PATH` (Selenium 4 подтягивает драйвер через Selenium Manager).

## Переменные окружения

| Переменная | Описание |
|------------|----------|
| `WPC_UI_BASE_URL` | Корень SPA (staging: `https://staging.wolfpack.robotics-rtuitlab.ru` когда задеплоен client) |
| `KEYCLOAK_TEST_USER` | Логин; алиасы: `KEYCLOAK_USERNAME`, `LOADTEST_USERNAME` |
| `KEYCLOAK_TEST_PASSWORD` | Пароль; алиасы: `KEYCLOAK_PASSWORD`, `LOADTEST_PASSWORD` |
| `HEADLESS` | `1` (по умолчанию) или `0` для окна браузера |
| `WPC_E2E_SKIP` | Если установлено (любое значение) — скрипт завершается с кодом 0 без запуска браузера |

Staging defaults (после `./scripts/keycloak-seed-staging-users.sh`):

- `loadtest-admin` — admin + user (orchestration)
- `loadtest-user` — user only

Пароли — в Secret `loadtest-credentials` (`kubectl get secret loadtest-credentials -n wolfpackcloud-control-staging -o yaml`).

## Запуск (staging)

```bash
export WPC_UI_BASE_URL=https://staging.wolfpack.robotics-rtuitlab.ru
export KEYCLOAK_TEST_USER=loadtest-admin
export KEYCLOAK_TEST_PASSWORD='…'   # из loadtest-credentials Secret
python smoke_orchestration.py
```

Или те же переменные, что и load tests:

```bash
export WPC_UI_BASE_URL=https://staging.wolfpack.robotics-rtuitlab.ru
export KEYCLOAK_USERNAME=loadtest-admin
export KEYCLOAK_PASSWORD='…'
python smoke_orchestration.py
```

В клиенте добавлены стабильные селекторы: `data-testid="login-keycloak"`, `nav-orchestration`, `orchestration-heading`.

## CI

Вынесите в отдельный job после деплоя на staging; передайте секреты через переменные окружения. Таймаут и повторы при флаках настройте оболочкой CI.

## Запасной вариант

Если попап OAuth/Swagger нестабилен, рассмотрите **Playwright** (лучше работа с несколькими страницами).
