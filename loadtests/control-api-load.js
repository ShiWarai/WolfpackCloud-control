/**
 * Нагрузка HTTP на Control API (JWT). Порогов k6 нет — смотрите метрики и выводите свои выводы.
 *
 * BASE_URL, ACCESS_TOKEN — или ./run-load.sh
 *
 * Интенсивность (k6 -e): VUS_MAX, RAMP_DURATION, HOLD_DURATION, RAMPDOWN_DURATION, SLEEP_SEC.
 * USE_BATCH=1 — параллельные GET внутри итерации (жёстче по одновременным запросам).
 */

import http from "k6/http";
import { check, sleep } from "k6";

export function setup() {
  const t = (__ENV.ACCESS_TOKEN || "").trim();
  if (!t) {
    throw new Error(
      "ACCESS_TOKEN пустой: получите токен (./fetch-keycloak-token.sh или ./run-load.sh)",
    );
  }
}

const vuMax = Math.min(200, Math.max(1, parseInt(__ENV.VUS_MAX || "15", 10)));
const ramp = __ENV.RAMP_DURATION || "8s";
const hold = __ENV.HOLD_DURATION || "18s";
const rampDown = __ENV.RAMPDOWN_DURATION || "5s";
const sleepSec = parseFloat(__ENV.SLEEP_SEC || "0.08");
const useBatch = (__ENV.USE_BATCH || "").trim() === "1";

export const options = {
  scenarios: {
    cluster_hammer: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: ramp, target: vuMax },
        { duration: hold, target: vuMax },
        { duration: rampDown, target: 0 },
      ],
      gracefulRampDown: "12s",
    },
  },
};

const base = (__ENV.BASE_URL || "").replace(/\/$/, "");
const authHeaders = () => ({
  headers: { Authorization: `Bearer ${(__ENV.ACCESS_TOKEN || "").trim()}` },
});

function must200(res, name) {
  check(res, {
    [`${name} status 200`]: (r) => r.status === 200,
  });
}

const clusterGets = [
  ["/api/cluster/nodes", "nodes"],
  ["/api/cluster/deployments", "deployments"],
  ["/api/cluster/pods", "pods"],
  ["/api/cluster/orchestration", "orchestration"],
  ["/api/cluster/compute-presets", "presets"],
];

export default function () {
  const ah = authHeaders();

  let res = http.get(`${base}/api/openapi.json`, ah);
  must200(res, "openapi");

  if (useBatch) {
    const clusterBatch = clusterGets.map(([path]) => ["GET", `${base}${path}`, null, ah]);
    const clusterResponses = http.batch(clusterBatch);
    clusterGets.forEach(([, label], i) => must200(clusterResponses[i], label));

    const tailResponses = http.batch([
      ["GET", `${base}/api/auth/me`, null, ah],
      ["GET", `${base}/api/workloads`, null, ah],
    ]);
    must200(tailResponses[0], "auth_me");
    must200(tailResponses[1], "workloads");
  } else {
    for (const [path, label] of clusterGets) {
      res = http.get(`${base}${path}`, ah);
      must200(res, label);
    }

    res = http.get(`${base}/api/auth/me`, ah);
    must200(res, "auth_me");

    res = http.get(`${base}/api/workloads`, ah);
    must200(res, "workloads");
  }

  sleep(sleepSec);
}
