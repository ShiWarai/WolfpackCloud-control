# k8s: Zenoh peer hammer (много реплик alpha ↔ beta)

Лежит в **`loadtests/`**, чтобы не смешивать с боевым `deploy/k3s/wolfpackcloud-control-peers/`.

Цель — нагрузить **обмен `/topic_a` ↔ `/topic_b`**, не Control API.

## Отличия от базового деплоя peers

| | База `deploy/k3s/wolfpackcloud-control-peers/` | этот каталог |
|---|------|------|
| Реплики alpha / beta | 1 | **40** (YAML или `kubectl scale`, можно **50+**) |
| `peer_shard` | 1 и 2 | **0** → shard из hostname пода |
| Нода | `hostname` в базе | **только `arm64`**, не **`sber`** и не **`alphie-phone-1`** (`nodeAffinity`) |
| Образ alpha/beta | amd64 / arm64 | оба **`humble-arm64`** |
| Стратегия | Recreate | RollingUpdate |
| Запросы ресурсов | выше | **100m / 128Mi** для упаковки |
| gamma | есть в базе | здесь **нет** |

## Применение

Из корня репозитория:

```bash
kubectl apply -k deploy/k3s/zenoh/
kubectl apply -k WolfpackCloud-control/loadtests/k8s-zenoh-peers-loadtest/
kubectl -n wolfpackcloud-zenoh scale deployment/compute-peer-alpha deployment/compute-peer-beta --replicas=50
```

Автоматический **полный цикл** (Zenoh → hammer → **k6 параллельно soak** → откат): [`../full-loadtest-cycle.sh`](../full-loadtest-cycle.sh).

Вернуть обычный демо-режим (одна реплика и hostname-селекторы из git):

```bash
kubectl apply -k deploy/k3s/wolfpackcloud-control-peers/
```

## Имена нод

Исключения по **`kubernetes.io/hostname`** (`NotIn`): **`sber`**, **`alphie-phone-1`**. Другой hostname — поправьте **`values`** в обоих `deployment-peer-*.yaml`.

Только **arm64** и образ **`humble-arm64`** для alpha и beta.
