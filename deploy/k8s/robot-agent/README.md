# Control robot-agent (pairing + heartbeat)

Демо-робот в кластере: регистрация через `POST /api/pair`, ожидание подтверждения в UI (**Control → Привязка**), затем Telegraf шлёт heartbeat на `POST /api/metrics`.

## Сборка

Из корня `WolfpackCloud-kubernetes`:

```bash
REG=10.43.50.10:5000
ARCH=arm64

./scripts/build-with-buildkit.sh "$ARCH" WolfpackCloud-control/robot-agent \
  "${REG}/wolfpack-control-robot-agent:latest-${ARCH}"
```

## Деплой

```bash
kubectl apply -k WolfpackCloud-control/deploy/k8s/robot-agent/
kubectl -n wolfpackcloud-control rollout status deployment/control-robot-agent --timeout=180s
```

Код привязки — в логах:

```bash
kubectl -n wolfpackcloud-control logs deployment/control-robot-agent -f
```

После подтверждения в UI pod продолжит работу и будет обновлять `last_seen_at` робота.

## Переменные (env в deployment.yaml)

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `WPC_SERVER_URL` | `http://control-api:8000` (тот же namespace) | Control API |
| `WPC_METRICS_URL` | `{SERVER}/api/metrics` | endpoint heartbeat |
| `WPC_ROBOT_NAME` | `demo-robot-k8s` | имя в UI |
| `WPC_ARCH` | авто из `uname` | `arm64` / `amd64` / `armhf` |

Токен и конфиг Telegraf хранятся в `emptyDir` пода; при удалении pod потребуется новая привязка.
