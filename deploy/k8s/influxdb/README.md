# InfluxDB (WolfpackCloud Control)

Time-series хранилище для ROS-логов (`ros_logs`) и событий деплоя (`deployment_events`).

Org InfluxDB: **`wolfpackcloud_influxdb`**. Service в k8s: **`wolfpackcloud-influxdb`**.

## Секреты

```bash
cp influxdb-secrets.example.yaml influxdb-secrets.yaml
# Задайте admin-password и admin-token (≥32 символов)
kubectl apply -f influxdb-secrets.yaml
```

Тот же `admin-token` добавьте в `control-api-env` как `INFLUXDB_TOKEN`.

## Деплой

```bash
kubectl apply -k WolfpackCloud-control/deploy/k8s/influxdb/
kubectl -n wolfpackcloud-control rollout status deployment/wolfpackcloud-influxdb --timeout=300s
kubectl -n wolfpackcloud-control wait --for=condition=complete job/wolfpackcloud-influxdb-init-buckets --timeout=300s
```

Service: `http://wolfpackcloud-influxdb.wolfpackcloud-control.svc.cluster.local:8086`
