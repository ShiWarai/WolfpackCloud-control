# Нагрузочное тестирование Control API

## Предпосылки

- Установлен [k6](https://k6.io/docs/getting-started/installation/).
- Развёрнут Control API и при необходимости peer-поды по [`deploy/k3s/wolfpackcloud-control-peers/README.md`](../../deploy/k3s/wolfpackcloud-control-peers/README.md).

## Переменные

| Переменная      | Описание |
|-----------------|----------|
| `BASE_URL`      | Базовый URL API (без завершающего `/`). Пример: `https://control.example.com` |
| `ACCESS_TOKEN`  | JWT Keycloak для вызовов `/api/cluster/*` (иначе ожидайте 401) |
| `INGEST_TOKEN`  | Опционально; см. закомментированный блок в `control-api-smoke.js` |

Получить токен можно через Keycloak (password grant в тестовой среде), из браузера (Network после входа в SPA) или временным клиентом — **не коммитьте** токены и пароли.

## Запуск

```bash
cd WolfpackCloud-control/loadtests
k6 run control-api-smoke.js -e BASE_URL=http://localhost:8000
```

С JWT:

```bash
export ACCESS_TOKEN="eyJ..."
k6 run control-api-smoke.js -e BASE_URL=https://api.example.com -e ACCESS_TOKEN="$ACCESS_TOKEN"
```

## Юнит- и интеграционные тесты API

```bash
cd WolfpackCloud-control/server/api
pip install -r requirements.txt -r requirements-dev.txt
pytest tests/
pytest tests/ --cov=app --cov-report=term-missing --cov-report=html
```
