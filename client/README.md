# WolfpackCloud Client

SPA для управления роботами, оркестрации workloads и просмотра ROS-логов. Часть [WolfpackCloud-control](../README.md).

## Технологии

- Vue 3 (Composition API) + TypeScript
- Vite 6
- Vue Router 4
- Pinia
- Axios
- **keycloak-js** (OIDC, PKCE, `check-sso`)
- Стили: глобальный [`src/style.css`](src/style.css) (терминальная тема; **Tailwind не используется**)

## Разработка

### Зависимости

```bash
npm ci
```

### Dev-сервер

```bash
npm run dev
```

По умолчанию: http://localhost:5173

С API и Keycloak через [`docker-compose.dev.yml`](../docker-compose.dev.yml) задайте (или `client/.env.development.local`):

| Переменная | Назначение |
|------------|------------|
| `VITE_API_BASE_URL` | Базовый URL API без `/api` на конце, напр. `http://localhost:9200` |
| `VITE_KEYCLOAK_URL` | Базовый URL Keycloak, напр. `http://localhost:8080` |
| `VITE_KEYCLOAK_REALM` | Realm, по умолчанию `wolfpack-control` |
| `VITE_KEYCLOAK_CLIENT_ID` | Публичный клиент, по умолчанию `wolfpack-control-web` |

Запросы к API идут на `{VITE_API_BASE_URL}/api/...` (см. [`src/api/client.ts`](src/api/client.ts)).

### Сборка и проверки

```bash
npm run build      # vue-tsc + vite → dist/
npm run preview    # превью production-сборки
npm run lint
npm run type-check
```

### Docker (production-образ)

```bash
docker build -t wolfpack-control-client .
docker run -p 8080:80 wolfpack-control-client
```

Build-args для prod (через BuildKit, см. корневой README): `VITE_API_URL`, `VITE_API_BASE_URL`, `VITE_KEYCLOAK_*`.

## Маршруты

| Путь | Компонент | Описание |
|------|-----------|----------|
| `/login` | LoginPage | Keycloak login |
| `/dashboard` | DashboardPage | Сводка |
| `/robots` | RobotsPage | Список роботов |
| `/robots/:id` | RobotDetailPage | Карточка, логи, метрики |
| `/pairing` | PairingPage | Подтверждение pairing-кода |
| `/orchestration` | OrchestrationPage | Кластер, drag-and-drop подов |
| `/journal` | JournalPage | ROS-логи (Influx) |
| `/account` | AccountPage | Профиль |

Guard: [`src/router/index.ts`](src/router/index.ts) — `requiresAuth` / Keycloak `check-sso`.

E2E-селекторы: `data-testid="login-keycloak"`, `nav-orchestration`, `orchestration-heading` (см. [e2e/README.md](../e2e/README.md)).

## Структура `src/`

```
src/
├── api/              # HTTP-клиент и модули (auth, robots, cluster, logs, …)
├── components/       # UI (orchestration/, LogScrollPanel, RobotCard, …)
├── composables/      # polling, drag-drop, log buffer
├── layouts/          # DefaultLayout
├── pages/            # маршруты SPA
├── router/
├── stores/           # Pinia (auth, robots)
├── keycloak.ts       # инициализация Keycloak
└── types/
```

## API-модули (клиент)

| Модуль | Backend |
|--------|---------|
| `auth.ts` | `/api/auth` |
| `robots.ts`, `pairing.ts` | `/api/robots`, `/api/pair` |
| `cluster.ts`, `workloads.ts` | `/api/cluster`, `/api/workloads` |
| `logs.ts`, `events.ts` | `/api/logs`, `/api/events` |
| `networks.ts`, `account.ts` | `/api/networks`, `/api/account` |

Авторизация: Bearer access token из Keycloak (`Authorization` в [`api/client.ts`](src/api/client.ts)).

## Внешние ссылки

Компонент [`ExternalLinks.vue`](src/components/ExternalLinks.vue) показывает только **Keycloak** (`VITE_KEYCLOAK_URL`). Grafana/Superset в текущей версии не подключены.

## Связанная документация

- [Корневой README](../README.md) — деплой, URL, Keycloak
- [API tests](../server/api/tests/README.md)
- [E2E](../e2e/README.md)
