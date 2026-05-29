# Нагрузочное тестирование Control API

## Только Control API (без подов в кластере)

Нагрузка идёт с вашей машины через **k6**, в Kubernetes **ничего не деплоится**:

```bash
cd WolfpackCloud-control/loadtests
export BASE_URL=https://wolfpack.robotics-rtuitlab.ru
export KEYCLOAK_USERNAME='…'
export KEYCLOAK_PASSWORD='…'
./run-load.sh
# или явная обёртка без kubectl:
FULL_LOADTEST_HTTP_ONLY=1 ./full-loadtest-cycle.sh -e VUS_MAX=10
```

Смок без JWT (осторожнее с продом): `k6 run control-api-smoke.js -e BASE_URL=…`.

## Полный цикл (Zenoh peers + опционально Control API)

Скрипт **[`full-loadtest-cycle.sh`](full-loadtest-cycle.sh)** проводит сквозной прогон:

1. `kubectl apply -k deploy/k3s/zenoh/` (можно `FULL_LOADTEST_SKIP_ZENOH=1`)
2. Опционально `FULL_LOADTEST_SCALE_GAMMA_ZERO=1` — **gamma → 0**
3. `kubectl apply -k loadtests/k8s-zenoh-peers-loadtest/` — hammer **alpha↔beta**
4. **`kubectl delete pods`** для peer-подов на нодах с **`wolfpack.io/role=dev`** (можно `FULL_LOADTEST_SKIP_PURGE=1`)
5. Сразу **k6** (`./run-load.sh`) в **фоне** — параллельно **rollout** alpha/beta (реально одновременно HTTP и подъём ROS/Zenoh)
6. **Soak** (по умолчанию 90 с), k6 обычно всё ещё работает
7. **Ожидание конца k6**
8. Откат **`deploy/k3s/wolfpackcloud-control-peers/`** и **повторный purge** на тех же нодах

При Ctrl+C скрипт по возможности **убивает фоновый k6**.

Если в конце **`HTTP (k6): 0`** — **k6 не запускался**, таблицы метрик не будет: не выставлены **`BASE_URL`**, **`KEYCLOAK_USERNAME`**, **`KEYCLOAK_PASSWORD`** или задано **`FULL_LOADTEST_SKIP_HTTP=1`**. Скрипт теперь печатает **причину** в блоке «Итог».

Пример только инфраструктура peers + soak, без JWT:

```bash
cd WolfpackCloud-control/loadtests
export FULL_LOADTEST_SKIP_HTTP=1
export FULL_LOADTEST_PEER_REPLICAS=45
./full-loadtest-cycle.sh
```

С HTTP и масштабом по умолчанию из YAML hammer:

```bash
export BASE_URL=https://wolfpack.robotics-rtuitlab.ru
export KEYCLOAK_USERNAME=wolfpack-operator
export KEYCLOAK_PASSWORD='***'
./full-loadtest-cycle.sh -e VUS_MAX=25
```

Подробнее по переменным — комментарии в начале `full-loadtest-cycle.sh`. Манифесты hammer: [`k8s-zenoh-peers-loadtest/README.md`](k8s-zenoh-peers-loadtest/README.md).

Залипшие peer-поды (Terminating / Completed / Unknown): [`cleanup-stuck-peer-pods.sh`](cleanup-stuck-peer-pods.sh) в этом каталоге.

## Предпосылки

- Установлен [k6](https://k6.io/docs/getting-started/installation/).
- Для **сильной** нагрузки нужен пользователь realm `wolfpack-control` и включённый **Direct Access Grants** у клиента `wolfpack-control-web` (уже так в [`wolfpack-control-realm.json`](../deploy/k8s/keycloak/wolfpack-control-realm.json)).
- Развёрнут Control API; опционально peer-поды по [`deploy/k3s/wolfpackcloud-control-peers/README.md`](../../deploy/k3s/wolfpackcloud-control-peers/README.md).

## Сценарии

| Файл | Назначение |
|------|------------|
| [`control-api-smoke.js`](control-api-smoke.js) | Короткий смок, можно без JWT (cluster вернёт 401). |
| [`control-api-load.js`](control-api-load.js) | «Тяжёлый» прогон: **только с JWT**, много вызовов cluster + `/api/auth/me` + `/api/workloads` за итерацию. |

## Автоматический токен (password grant)

Скрипт [`fetch-keycloak-token.sh`](fetch-keycloak-token.sh) ходит в Keycloak `.../protocol/openid-connect/token` с `grant_type=password` и публичным `client_id=wolfpack-control-web`.

Обязательно в окружении при запуске:

| Переменная | Описание |
|------------|-----------|
| `KEYCLOAK_USERNAME` | Логин пользователя realm (не master-admin Keycloak) |
| `KEYCLOAK_PASSWORD` | Пароль |

Опционально: `KEYCLOAK_ISSUER` (по умолчанию `https://auth.wolfpack.robotics-rtuitlab.ru/realms/wolfpack-control`), `KEYCLOAK_CLIENT_ID`, `KEYCLOAK_TOKEN_URL`.

Одной строкой:

```bash
cd WolfpackCloud-control/loadtests
chmod +x fetch-keycloak-token.sh run-load.sh
export BASE_URL=https://wolfpack.robotics-rtuitlab.ru
export KEYCLOAK_USERNAME='your-operator-login'
export KEYCLOAK_PASSWORD='your-password'
./run-load.sh
```

Только получить токен в переменную:

```bash
export ACCESS_TOKEN="$(./fetch-keycloak-token.sh)"
k6 run control-api-load.js -e BASE_URL="$BASE_URL" -e ACCESS_TOKEN="$ACCESS_TOKEN"
```

Интенсивность (передаются как `-e` **после** `./run-load.sh`, попадают в k6):

```bash
./run-load.sh -e VUS_MAX=40 -e HOLD_DURATION=3m -e SLEEP_SEC=0.05
```

**Не коммитьте** пароли и `.token`; файл [`loadtests/.token`](../.gitignore) в `.gitignore` при желании храните только локально.

## Переменные смока (`control-api-smoke.js`)

| Переменная      | Описание |
|-----------------|----------|
| `BASE_URL`      | Хост Ingress без завершающего `/`. Сценарий ходит на `/api/openapi.json` и `/api/cluster/...`. |
| `ACCESS_TOKEN`  | JWT (опционально для смока; без него cluster допускает **401/403** в проверках) |
| `INGEST_TOKEN`  | Опционально; см. комментарий в `control-api-smoke.js` |

Пороги смока завязаны на **`checks`** и **p95 latency**, а не на `http_req_failed`, чтобы прогон без JWT не падал из‑за счётчика 401 в k6.

Ручная подстановка токена:

```bash
export ACCESS_TOKEN="eyJ..."
k6 run control-api-smoke.js -e BASE_URL=https://wolfpack.robotics-rtuitlab.ru -e ACCESS_TOKEN="$ACCESS_TOKEN"
```

Лёгкий смок без JWT:

```bash
cd WolfpackCloud-control/loadtests
k6 run control-api-smoke.js -e BASE_URL=http://localhost:8000
```

## Юнит- и интеграционные тесты API

```bash
cd WolfpackCloud-control/server/api
pip install -r requirements.txt -r requirements-dev.txt
pytest tests/
pytest tests/ --cov=app --cov-report=term-missing --cov-report=html
```
