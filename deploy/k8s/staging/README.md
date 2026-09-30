# Staging Control API (load / e2e)

Ephemeral namespace **`wolfpackcloud-control-staging`**: поднимается на время тестов и **удаляется** после прогона (см. ниже). Production (`wolfpackcloud-control`) для k6 по умолчанию не используется.

## Автоматический lifecycle (рекомендуется)

Скрипты **`scripts/staging-up.sh`**, **`scripts/staging-down.sh`**, **`scripts/with-staging.sh`**:

| Команда | Поведение |
|---------|-----------|
| `./scripts/run-pytest-staging-postgres.sh` | down (если был) → up → pytest → **delete namespace** |
| `loadtests/run-load-staging.sh` | то же для k6 |
| `STAGING_KEEP=1 …` | не удалять NS после теста |
| `STAGING_SKIP_LIFECYCLE=1 …` | только тест, NS поднят вручную |

```bash
# Ручной цикл
./scripts/staging-down.sh || true
./scripts/staging-up.sh
# … тесты …
./scripts/staging-down.sh
```

## Ручное развёртывание (долгоживущий staging)

```bash
cd WolfpackCloud-control

# 1. Keycloak: staging realm (общий Keycloak в wolfpackcloud-auth)
kubectl apply -k deploy/k8s/keycloak/
# После рестарта Keycloak импортирует wolfpack-control-realm-staging.json (IGNORE_EXISTING).

# 2. Учётки load test (пароли не в git)
cp deploy/k8s/keycloak/loadtest-credentials.example.yaml deploy/k8s/keycloak/loadtest-credentials.yaml
# отредактируйте password / user-password
kubectl apply -f deploy/k8s/keycloak/loadtest-credentials.yaml
chmod +x scripts/keycloak-seed-staging-users.sh
./scripts/keycloak-seed-staging-users.sh

# 3. Staging stack
cp deploy/k8s/staging/control-infra-secrets-staging.example.yaml deploy/k8s/staging/control-infra-secrets-staging.yaml
cp deploy/k8s/staging/api-secret-staging.example.yaml deploy/k8s/staging/api-secret-staging.yaml
# согласуйте пароль Postgres в обоих файлах; INFLUXDB_TOKEN можно взять из prod api-secret
kubectl apply -f deploy/k8s/staging/control-infra-secrets-staging.yaml \
              -f deploy/k8s/staging/api-secret-staging.yaml
kubectl apply -k deploy/k8s/staging/
kubectl rollout status deployment/control-api -n wolfpackcloud-control-staging --timeout=300s
```

## Доступ к API

Только **port-forward** (публичного DNS/Ingress для staging нет):

```bash
kubectl port-forward -n wolfpackcloud-control-staging svc/control-api 18081:8000
# API: http://127.0.0.1:18081/api
export STAGING_BASE_URL=http://127.0.0.1:18081
```

`run-load-staging.sh` / pytest по умолчанию используют этот URL.

Staging `control-api` SA привязан к Role `control-zenoh-namespace` в **`wolfpackcloud-zenoh`** (`rbac-zenoh-binding.yaml` применяется **вне** kustomize — иначе binding уезжает в staging NS и `/api/cluster/*` отдаёт 502).

## Отличия от production

- Namespace `wolfpackcloud-control-staging`, БД `wolfpack_control_staging`, PVC 5Gi
- Keycloak realm `wolfpack-control-staging`, пользователи `loadtest-user` / `loadtest-admin` (Secret `loadtest-credentials`)
- Нет SPA (`control-client`) — только API; e2e UI нужен отдельный деплой клиента на staging host или prod UI с staging API (не рекомендуется)
- RBAC: тот же ClusterRole `wolfpackcloud-control-api-nodes-read`, отдельный binding для staging SA
- Zenoh namespace `wolfpackcloud-zenoh` общий (migrate load tests — read-only smoke на prod peers)

## Pytest (PostgreSQL)

Отдельная БД **`wolfpack_control_pytest`** на staging Postgres — не `wolfpack_control_staging`.  
Обёртка из корня репо сама поднимает/снимает namespace:

```bash
cd WolfpackCloud-control
./scripts/run-pytest-staging-postgres.sh
# только pytest без lifecycle:
# STAGING_SKIP_LIFECYCLE=1 ./server/api/scripts/run-pytest-staging-postgres.sh
```

## Load / e2e

```bash
cd loadtests
./run-load-staging.sh -e VUS_MAX=10
```

См. [`loadtests/README.md`](../../loadtests/README.md) и [`e2e/README.md`](../../e2e/README.md).
