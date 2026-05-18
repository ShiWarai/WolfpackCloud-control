# Traefik: HTTPS на порту **4443** (legacy / опционально)

**Текущая схема WolfpackCloud-control:** Keycloak на поддомене **`auth.wolfpack.robotics-rtuitlab.ru`** через обычный entrypoint **websecure (443)** — отдельный порт **4443** не нужен.

Этот каталог оставлен для кластеров, где по-прежнему хотят второй HTTPS-порт или старые Ingress с `router.entrypoints: websecure4443`.

## Зачем (если всё же используете)

Ingress с аннотацией `traefik.ingress.kubernetes.io/router.entrypoints: websecure4443` требует объявить entryPoint у Traefik и слушать **4443** на ноде.

## Применение

Из каталога `WolfpackCloud-control`:

```bash
kubectl apply -k deploy/k8s/traefik-entrypoint-4443/
```

После применения под Traefik в `kube-system` перезапустится (helm upgrade). Откройте **TCP 4443** на VPS — см. [VPS-firewall.md](VPS-firewall.md).

## Важно: уже есть свой HelmChartConfig `traefik`

Ресурс **`HelmChartConfig/traefik`** один на кластер. `kubectl apply` **заменит** `spec` целиком. Если у вас уже настроены другие `valuesContent`, **слейте** их с файлом [helmchartconfig-traefik-websecure4443.yaml](helmchartconfig-traefik-websecure4443.yaml) вручную (добавьте блок `ports.websecure4443` и строку `entryPoints.websecure4443` в `additionalArguments`), затем примените объединённый манифест.

См. также: [Traefik static configuration](https://doc.traefik.io/traefik/reference/install-configuration/configuration-options/).
