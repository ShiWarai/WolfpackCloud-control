# Browser E2E (Selenium)

Смок после деплоя UI + Keycloak: вход и страница оркестрации.

Для **staging API** (без публичного UI) используйте load/pytest и port-forward — см. [`deploy/k8s/staging/README.md`](../deploy/k8s/staging/README.md).  
Browser E2E ниже — обычно против **production** UI (`https://wolfpack.robotics-rtuitlab.ru`).

## Зависимости

```bash
cd WolfpackCloud-control/e2e
pip install -r requirements-e2e.txt
```

Нужен **Chrome/Chromium** в `PATH` (Selenium 4 подтягивает драйвер через Selenium Manager).

## Переменные окружения

| Переменная | Описание |
|------------|----------|
| `WPC_UI_BASE_URL` | Корень SPA (по умолчанию prod: `https://wolfpack.robotics-rtuitlab.ru`) |
| `KEYCLOAK_TEST_USER` | Логин; алиасы: `KEYCLOAK_USERNAME`, `LOADTEST_USERNAME` |
| `KEYCLOAK_TEST_PASSWORD` | Пароль; алиасы: `KEYCLOAK_PASSWORD`, `LOADTEST_PASSWORD` |
| `HEADLESS` | `1` (по умолчанию) или `0` для окна браузера |
| `WPC_E2E_SKIP` | Если установлено (любое значение) — скрипт завершается с кодом 0 без запуска браузера |

## Запуск (production UI)

```bash
export WPC_UI_BASE_URL=https://wolfpack.robotics-rtuitlab.ru
export KEYCLOAK_TEST_USER=wolfpack-operator
export KEYCLOAK_TEST_PASSWORD='…'
python smoke_orchestration.py
```

В клиенте добавлены стабильные селекторы: `data-testid="login-keycloak"`, `nav-orchestration`, `orchestration-heading`.

## CI

Отдельный job с prod URL и секретами в окружении. Таймаут и повторы при флаках — оболочкой CI.

## Запасной вариант

Если попап OAuth/Swagger нестабилен, рассмотрите **Playwright** (лучше работа с несколькими страницами).
