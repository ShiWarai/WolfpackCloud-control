# Для сборки в кластере: --opt build-arg:NODE_IMAGE=10.43.50.10:5000/library/node:22-alpine
ARG NODE_IMAGE=node:22-alpine
ARG NGINX_IMAGE=nginx:alpine

# Build stage
FROM ${NODE_IMAGE} AS build

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

ARG VITE_API_URL=/api
ARG VITE_API_BASE_URL=/api
ARG VITE_KEYCLOAK_URL=https://auth.wolfpack.robotics-rtuitlab.ru
ARG VITE_KEYCLOAK_REALM=wolfpack-control
ARG VITE_KEYCLOAK_CLIENT_ID=wolfpack-control-web

ENV VITE_API_URL=${VITE_API_URL}
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
ENV VITE_KEYCLOAK_URL=${VITE_KEYCLOAK_URL}
ENV VITE_KEYCLOAK_REALM=${VITE_KEYCLOAK_REALM}
ENV VITE_KEYCLOAK_CLIENT_ID=${VITE_KEYCLOAK_CLIENT_ID}

RUN npm run build

FROM ${NGINX_IMAGE}

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
