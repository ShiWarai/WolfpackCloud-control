# rosout-bridge (namespace `wolfpackcloud-zenoh`)

ROS 2 `/rosout` → InfluxDB (`ros_logs`) и fallback ingest в control-api. Образ: `WolfpackCloud-control/rosout-bridge/`.

## Планирование

- **nodeAffinity:** `wolfpack.io/role=worker`, `kubernetes.io/arch=arm64` — при падении ноды под переносится на другой Ready worker (без `nodeName`).
- **RollingUpdate** `maxSurge: 1` — новый под может подняться, пока старый снимается с недоступной ноды.
- **tolerationSeconds: 60** на `not-ready` / `unreachable`.

Нужен хотя бы один запасной arm64 worker (несколько Orange Pi с меткой `worker`).

## Apply

```bash
cd WolfpackCloud-control
cp deploy/k8s/rosout-bridge/rosout-bridge-secret.example.yaml deploy/k8s/rosout-bridge/rosout-bridge-secret.yaml
# ingest-token = ROSOUT_INGEST_TOKEN в api-secret; influxdb-token = INFLUXDB_TOKEN control-api
kubectl apply -f deploy/k8s/rosout-bridge/rosout-bridge-secret.yaml
kubectl apply -k deploy/k8s/rosout-bridge/
kubectl -n wolfpackcloud-zenoh rollout status deploy/rosout-bridge
```

Zenoh router: `deploy/k3s/zenoh/` в репозитории **WolfpackCloud-kubernetes** (отдельно от этого kustomize).
