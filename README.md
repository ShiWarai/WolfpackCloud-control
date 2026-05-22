# WolfpackCloud-control

Панель управления кластером WolfpackCloud: Vue SPA, Control API (FastAPI), PostgreSQL, **Keycloak (OIDC)**, оркестрация workloads в namespace **`wolfpackcloud-zenoh`** на нодах пула **`wolfpack.io/role`** (**`worker`** и **`dev`** на одном уровне). Ноды **master/control-plane** в UI не показываются (настройки API — **`env.vars.reference`**).

## Где работает production-сайт

**Всё в кластере k3s:** статический UI и API — поды в **`wolfpackcloud-control`**, Keycloak — в **`wolfpackcloud-auth`**, Ingress через **Traefik** на **HTTPS 443**. Локально не нужно «гонять» прод: достаточно собрать образы скриптом BuildKit и применить манифесты. Локальный **`docker-compose.dev.yml`** — опционально для разработки без кластера.

## URL (production)

| Компонент | URL |
|-----------|-----|
| UI + API | `https://wolfpack.robotics-rtuitlab.ru` — `/` UI, `/api` backend |
| OpenAPI / Swagger UI | `https://wolfpack.robotics-rtuitlab.ru/api/docs` (JSON схема: `/api/openapi.json`, альтернатива ReDoc: `/api/redoc`) |
| Keycloak | `https://auth.wolfpack.robotics-rtuitlab.ru` |

В Swagger UI: **Authorize** → **KeycloakOIDC** — вход через Keycloak (authorization code + PKCE; клиент по умолчанию `wolfpack-control-web`, см. `KEYCLOAK_SWAGGER_CLIENT_ID`). Redirect: `{origin}/api/docs/oauth2-redirect`. Если realm уже создан без нужных redirect URIs — добавьте их в Keycloak (в репозитории см. [wolfpack-control-realm.json](deploy/k8s/keycloak/wolfpack-control-realm.json)). записи на IP VPS/LB: основной хост и **`auth.wolfpack.robotics-rtuitlab.ru`**. Достаточно firewall **TCP 443**. Отдельный порт **4443** для Keycloak больше не используется (опциональный Traefik entrypoint см. [deploy/k8s/traefik-entrypoint-4443/](deploy/k8s/traefik-entrypoint-4443/) только если где-то ещё нужен).

## Быстрый старт (разработка)

```bash
# Переменные для api уже заданы в compose; при необходимости переопределите через export или свой compose override.
docker compose -f docker-compose.dev.yml up -d --build postgres api
# При необходимости смонтируйте kubeconfig в сервис api (см. compose override).

cd client && npm ci && npm run dev
```

## Деплой в k3s

### Сборка образов в cluster registry (BuildKit)

Выполняйте из **корня монорепозитория** WolfpackCloud-kubernetes — один общий скрипт **[`scripts/build-with-buildkit.sh`](../scripts/build-with-buildkit.sh)** (BuildKit в namespace `wolfpack-build`, push в **`10.43.50.10:5000`**).

```bash
# Манифесты по умолчанию тянут образы **:latest-arm64** и ставят поды только на ноды **kubernetes.io/arch=arm64**.
REG=10.43.50.10:5000
TAG=latest

build_client_opts=(
  --opt build-arg:VITE_API_URL=/api
  --opt build-arg:VITE_API_BASE_URL=https://wolfpack.robotics-rtuitlab.ru/api
  --opt build-arg:VITE_KEYCLOAK_URL=https://auth.wolfpack.robotics-rtuitlab.ru
  --opt build-arg:VITE_KEYCLOAK_REALM=wolfpack-control
  --opt build-arg:VITE_KEYCLOAK_CLIENT_ID=wolfpack-control-web
)

ARCH=arm64
S="${TAG}-${ARCH}"
./scripts/build-with-buildkit.sh "$ARCH" WolfpackCloud-control/server/api \
  "${REG}/wolfpack-control-api:${S}" --opt target=production
./scripts/build-with-buildkit.sh "$ARCH" WolfpackCloud-control/client \
  "${REG}/wolfpack-control-client:${S}" "${build_client_opts[@]}"
./scripts/build-with-buildkit.sh "$ARCH" WolfpackCloud-control/rosout-bridge \
  "${REG}/wolfpack-rosout-bridge:${S}"
./scripts/build-with-buildkit.sh "$ARCH" WolfpackCloud-control/robot-agent \
  "${REG}/wolfpack-control-robot-agent:${S}"
```

Для **amd64** поменяйте `ARCH=amd64`, образ `:latest-amd64` и в YAML уберите/измените affinity на `arm64` и тег образа.

Почему в Lens «как будто два устройства»: при стратегии **RollingUpdate** при обновлении Deployment на короткое время может быть **два пода** на **разных нодах**. У **control-api** и **control-client** включён **`Recreate`** и тег **`:latest-arm64`**, чтобы не смешивать архитектуры и не держать пару подов при выкладке.

Дальше по порядку (из каталога **`WolfpackCloud-control`**, либо поправьте пути):

1. **DNS:** `auth.wolfpack.robotics-rtuitlab.ru` → тот же адрес, что и основной сайт (LB/VPS).
2. **Keycloak** — см. раздел [ниже](#keycloak-clean-deploy). Кратко: `keycloak-secrets.yaml` → `kubectl apply -k deploy/k8s/keycloak/` → namespace **`wolfpackcloud-auth`**. Realm OIDC **`wolfpack-control`**; клиенты и роли — из импорта [wolfpack-control-realm.json](deploy/k8s/keycloak/wolfpack-control-realm.json).
3. Если realm **уже был импортирован раньше**, стратегия импорта `IGNORE_EXISTING` не обновит клиента: в **Keycloak Admin** → realm **wolfpack-control** → **Clients** → **wolfpack-control-web** проверьте **Web origins**: должны быть `https://wolfpack.robotics-rtuitlab.ru` и `https://auth.wolfpack.robotics-rtuitlab.ru` (без старого `:4443`).
4. **Роли и доступ API:** роль **`admin`** — **realm role** или client role у **`wolfpack-control-web`**; оба варианта учитываются API. Либо **`CONTROL_ADMIN_USERNAMES`** у API (через запятую: `preferred_username` или email).
5. **Control stack:** обновите **`control-api-env`** (`KEYCLOAK_ISSUER`, `KEYCLOAK_JWKS_URL` на новый хост auth), затем `kubectl apply -k deploy/k8s/control/` (namespace **`wolfpackcloud-control`**, Postgres PVC **10Gi**).
6. **InfluxDB** (ROS-логи и события деплоя): см. [deploy/k8s/influxdb/README.md](deploy/k8s/influxdb/README.md). Кратко: `influxdb-secrets.yaml` → `kubectl apply -k deploy/k8s/influxdb/` → тот же admin-token в **`control-api-env`** как `INFLUXDB_TOKEN` (и `INFLUXDB_URL=http://wolfpackcloud-influxdb.wolfpackcloud-control.svc.cluster.local:8086`, `INFLUXDB_ORG=wolfpackcloud_influxdb`).
7. **Rosout-bridge:** Secret **`rosout-bridge-secret`** в **`wolfpackcloud-zenoh`** (`ingest-token` = `ROSOUT_INGEST_TOKEN` у API, `influxdb-token` = `INFLUXDB_TOKEN` у API), затем `kubectl apply -k deploy/k8s/rosout-bridge/`. Bridge пишет `/rosout` **напрямо в InfluxDB** (bucket `ros_logs`); API ingest остаётся только для fallback/отладки.
8. После деплоя API с Influx-only логами выполните миграцию **`004`** (drop `ros_log_entries` в PostgreSQL): `kubectl exec -n wolfpackcloud-control deploy/control-api -- alembic upgrade head`.

<a id="keycloak-clean-deploy"></a>

### Keycloak: чистый деплой и первый пользователь

Импорт realm создаёт клиентов и роли, **но не учётки людей** в `wolfpack-control` — их задаёте вы (пароли в git не храним).

**Деплой с нуля**

```bash
cd WolfpackCloud-control
# Шаблон: cp deploy/k8s/keycloak/keycloak-secrets.example.yaml deploy/k8s/keycloak/keycloak-secrets.yaml
kubectl apply -f deploy/k8s/keycloak/keycloak-secrets.yaml
kubectl apply -k deploy/k8s/keycloak/
kubectl rollout status deployment/keycloak -n wolfpackcloud-auth --timeout=600s
```

Подождите, пока Ingress и TLS для `auth.wolfpack…` станут доступны.

**Создать пользователя realm (UI или Postman / Password Grant)**

1. Откройте **Keycloak Admin Console**: `https://auth.wolfpack.robotics-rtuitlab.ru/admin` (или ваш хост).
2. Войдите как **bootstrap admin** master realm: логин **`admin`**, пароль — значение **`admin-password`** из Secret **`keycloak-admin-secret`** (namespace **`wolfpackcloud-auth`**). Это **не** пользователь для API/UI приложения — только админка.
3. В верхнем левом углу переключите **realm** с **master** на **`wolfpack-control`**.
4. **Users** → **Create new user**: задайте **Username**; заполните **Email** и включите **Email verified** (при включённом «Login with email» иначе токены могут вести себя непредсказуемо).
5. Вкладка **Credentials** → **Set password** → снимите **Temporary** (временный пароль блокирует нормальный вход).
6. Вкладка **Role mapping** → **Assign role** → выберите фильтр **Filter by realm roles** и назначьте **`user`**; для оркестрации и админских эндпоинтов добавьте **`admin`**.
7. В Postman / OAuth: клиент **`wolfpack-control-web`**, grant **Authorization Code (PKCE)** или **Password** — логин и пароль **этого** пользователя realm (не master **`admin`**).

**Полный сброс Keycloak в кластере** (данные Postgres Keycloak и импорт realm пропадут): удалите namespace **`wolfpackcloud-auth`**, затем снова `kubectl apply` секреты и `kubectl apply -k deploy/k8s/keycloak/`, после старта повторите шаги создания пользователя.

## Smoke-test

1. Откройте UI → редирект на **auth.** поддомен → вход.
2. `curl -sS -H "Authorization: Bearer $ACCESS_TOKEN" https://wolfpack.robotics-rtuitlab.ru/api/cluster/orchestration` (или `/api/cluster/nodes`, если есть в роутере).
3. На странице «Ресурсы кластера» перетащите workload на другую ноду пула (worker/dev) → для произвольных deployment нужна роль realm **`admin`** в Keycloak.
4. Проверка ingest (с master/VPS): `curl -sS -o /dev/null -w "%{http_code}" -X POST https://wolfpack.robotics-rtuitlab.ru/api/internal/rosout/one -H "Content-Type: application/json" -H "X-Ingest-Token: $ROSOUT_INGEST_TOKEN" -d '{"message":"smoke","level":"20"}'` → ожидается **204**.
5. Вкладка логов робота и **Журнал → ROS-логи**: polling `GET /api/logs`; статус bridge/Influx — `GET /api/logs/status`.

## Переменные

В **k3s**: секреты не коммитить — скопируйте [deploy/k8s/control/api-secret.example.yaml](deploy/k8s/control/api-secret.example.yaml) → `api-secret.yaml` и остальные `*.example.yaml` из `deploy/k8s/*/`. Шаблоны в git; заполненные файлы перечислены в [.gitignore](.gitignore). Переменные: [env.vars.reference](env.vars.reference).

## Лицензия

См. [LICENSE](LICENSE).
