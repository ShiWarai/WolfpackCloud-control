# Browser E2E (Selenium)

Смок после деплоя UI + Keycloak: вход и страница оркестрации.

## Зависимости

```bash
cd WolfpackCloud-control/e2e
pip install -r requirements-e2e.txt
```

Нужен **Chrome/Chromium** в `PATH` (Selenium 4 подтягивает драйвер через Selenium Manager).

## Переменные окружения

| Переменная | Описание |
|------------|----------|
| `WPC_UI_BASE_URL` | Корень SPA (например `https://control.example.com`) |
| `KEYCLOAK_TEST_USER` | Логин тестового пользователя Keycloak |
| `KEYCLOAK_TEST_PASSWORD` | Пароль |
| `HEADLESS` | `1` (по умолчанию) или `0` для окна браузера |
| `WPC_E2E_SKIP` | Если установлено (любое значение) — скрипт завершается с кодом 0 без запуска браузера |

## Запуск

```bash
export WPC_UI_BASE_URL=https://staging.example.com
export KEYCLOAK_TEST_USER=testuser
export KEYCLOAK_TEST_PASSWORD=...
python smoke_orchestration.py
```

В клиенте добавлены стабильные селекторы: `data-testid="login-keycloak"`, `nav-orchestration`, `orchestration-heading`.

## CI

Вынесите в отдельный job после деплоя на staging; передайте секреты через переменные окружения. Таймаут и повторы при флаках настройте оболочкой CI.

## Запасной вариант

Если попап OAuth/Swagger нестабилен, рассмотрите **Playwright** (лучше работа с несколькими страницами).
