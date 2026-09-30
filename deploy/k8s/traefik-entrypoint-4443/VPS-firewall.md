# Firewall VPS

Трафик идёт на **ноду k3s**, где слушают **kube-proxy / Traefik** (host network или NodePort/SVC — зависит от установки). Откройте входящие порты на VPS:

```bash
# ufw
sudo ufw allow 443/tcp comment 'Traefik HTTPS (UI, API, Keycloak auth.*)'
sudo ufw reload
```

Порт **4443** нужен только если вы явно используете второй HTTPS entrypoint Traefik (см. [README](README.md) в этом каталоге); для схемы с поддоменом Keycloak на **443** он не обязателен.

Проверка: снаружи `curl -vk https://wolfpack.robotics-rtuitlab.ru/` и `curl -vk https://auth.wolfpack.robotics-rtuitlab.ru/` (ожидаются TLS-ответы).
