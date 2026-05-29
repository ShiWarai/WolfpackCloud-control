# Staging Control API (load / e2e)

Отдельный namespace **`wolfpackcloud-control-staging`**: свой Postgres, API на realm **`wolfpack-control-staging`**. Production (`wolfpackcloud-control`) для k6 по умолчанию не используется.

## Порядок развёртывания

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

| Способ | URL |
|--------|-----|
| Ingress (рекомендуется) | `https://staging.wolfpack.robotics-rtuitlab.ru/api` |
| Port-forward | `kubectl port-forward -n wolfpackcloud-control-staging svc/control-api 18081:8000` → `http://127.0.0.1:18081/api` |

DNS для `staging.wolfpack.robotics-rtuitlab.ru` должен указывать на тот же Ingress, что и prod (A/CNAME на тот же IP, что `wolfpack.robotics-rtuitlab.ru`, например `77.232.130.196`). Без записи cert-manager HTTP-01 и HTTPS не заработают; до появления DNS используйте port-forward (см. таблицу выше).

Staging `control-api` SA привязан к Role `control-zenoh-namespace` в `wolfpackcloud-zenoh` (`rbac-zenoh-binding.yaml`) — иначе `/api/cluster/deployments` и `/api/cluster/pods` отдают 502.

## Отличия от production

- Namespace `wolfpackcloud-control-staging`, БД `wolfpack_control_staging`, PVC 5Gi
- Keycloak realm `wolfpack-control-staging`, пользователи `loadtest-user` / `loadtest-admin` (Secret `loadtest-credentials`)
- Нет SPA (`control-client`) — только API; e2e UI нужен отдельный деплой клиента на staging host или prod UI с staging API (не рекомендуется)
- RBAC: тот же ClusterRole `wolfpackcloud-control-api-nodes-read`, отдельный binding для staging SA
- Zenoh namespace `wolfpackcloud-zenoh` общий (migrate load tests — read-only smoke на prod peers)

## Pytest (PostgreSQL)

Отдельная БД **`wolfpack_control_pytest`** на staging Postgres — не `wolfpack_control_staging`:

```bash
cd WolfpackCloud-control
./scripts/run-pytest-staging-postgres.sh
# или из server/api:
# ./server/api/scripts/run-pytest-staging-postgres.sh
```

## Load / e2e

```bash
cd loadtests
./run-load-staging.sh -e VUS_MAX=10
```

См. [`loadtests/README.md`](../../loadtests/README.md) и [`e2e/README.md`](../../e2e/README.md).
