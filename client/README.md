# WolfpackCloud Client

Веб-приложение для управления роботами на Vue 3.

## Технологии

- Vue 3 + Composition API
- TypeScript
- Vite
- Vue Router
- Pinia
- Axios
- Tailwind CSS

## Разработка

### Установка зависимостей

```bash
npm install
```

### Запуск dev-сервера

```bash
npm run dev
```

Откроется на http://localhost:5173

### Сборка

```bash
npm run build
```

Результат в `dist/`

### Линтинг

```bash
npm run lint
```

## Docker

```bash
# Сборка образа
docker build -t wpc-client .

# Запуск
docker run -p 9101:80 wpc-client
```

## Переменные окружения

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| VITE_API_URL | URL API | /api |
| VITE_GRAFANA_URL | URL Grafana | http://localhost:9200 |
| VITE_SUPERSET_URL | URL Superset | http://localhost:9300 |

## Структура

```
src/
├── api/           # Axios client, API services
├── components/    # Vue компоненты
├── layouts/       # Layout компоненты
├── pages/         # Страницы (views)
├── router/        # Vue Router
├── stores/        # Pinia stores
└── types/         # TypeScript типы
```

## Функционал

- Аутентификация (JWT)
- Dashboard со статистикой
- Список роботов с фильтрацией
- Привязка роботов по коду
- Ссылки на Grafana/Superset
