/**
 * Нагрузочный смок Control API (k6).
 *
 * Переменные окружения:
 *   BASE_URL      — корень API, например https://control.example.com или http://localhost:8000
 *   ACCESS_TOKEN  — Bearer JWT Keycloak (опционально для защищённых маршрутов)
 *   INGEST_TOKEN  — токен rosout ingest (опционально; включите блок ниже при необходимости)
 *
 * Живость API: GET `${BASE_URL}/api/openapi.json` (подходит под Ingress с префиксом `/api`).
 *
 * Пример:
 *   k6 run control-api-smoke.js -e BASE_URL=https://wolfpack.robotics-rtuitlab.ru -e ACCESS_TOKEN="$(cat .token)"
 *
 * Фон: включённые compute-peer по
 *   deploy/k3s/wolfpackcloud-control-peers/README.md
 */

import http from "k6/http";
import { check, sleep } from "k6";

export const options = {
  stages: [
    { duration: "10s", target: 5 },
    { duration: "30s", target: 10 },
    { duration: "10s", target: 0 },
  ],
  thresholds: {
    checks: ["rate>=0.95"],
    // Под VU и через Ingress p95 часто >2s на cluster/* — смок про корректность, не SLA.
    http_req_duration: ["p(95)<8000"],
  },
};

const base = (__ENV.BASE_URL || "http://localhost:8000").replace(/\/$/, "");
const token = (__ENV.ACCESS_TOKEN || "").trim();
const authHeaders = token ? { Authorization: `Bearer ${token}` } : {};

export default function () {
  // Снаружи через Ingress API под префиксом /api; «/health» на том же хосте может отдавать не JSON API.
  let res = http.get(`${base}/api/openapi.json`);
  check(res, {
    "openapi status 200": (r) => r.status === 200,
    "openapi json looks valid": (r) => {
      try {
        const b = r.json();
        return !!(b && b.openapi && b.info && b.info.title);
      } catch {
        return false;
      }
    },
  });

  res = http.get(`${base}/api/cluster/nodes`, { headers: authHeaders });
  check(res, {
    "nodes auth or ok": (r) =>
      r.status === 200 || r.status === 401 || r.status === 403,
  });

  res = http.get(`${base}/api/cluster/orchestration`, { headers: authHeaders });
  check(res, {
    "orchestration auth or ok": (r) =>
      r.status === 200 || r.status === 401 || r.status === 403,
  });

  // Раскомментируйте при настройке INGEST_TOKEN и нужном пути ingest в Postman/роутере.
  // const ingest = (__ENV.INGEST_TOKEN || "").trim();
  // if (ingest) {
  //   res = http.post(`${base}/api/logs/rosout`, JSON.stringify({}), {
  //     headers: { ...authHeaders, "Content-Type": "application/json", "X-Ingest-Token": ingest },
  //   });
  //   check(res, { "ingest accepted": (r) => r.status < 500 });
  // }

  sleep(1);
}
