/**
 * Нагрузка на публичный OpenAPI (без JWT) + опционально cluster с Bearer.
 * Для JWT: ACCESS_TOKEN или ./run-load.sh
 */
import http from "k6/http";
import { check, sleep } from "k6";

const vuMax = Math.min(100, Math.max(1, parseInt(__ENV.VUS_MAX || "40", 10)));
const hold = __ENV.HOLD_DURATION || "60s";
const ramp = __ENV.RAMP_DURATION || "15s";
const rampDown = __ENV.RAMPDOWN_DURATION || "10s";
const sleepSec = parseFloat(__ENV.SLEEP_SEC || "0.02");
const token = (__ENV.ACCESS_TOKEN || "").trim();
const base = (__ENV.BASE_URL || "").replace(/\/$/, "");

export const options = {
  scenarios: {
    hammer: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: ramp, target: vuMax },
        { duration: hold, target: vuMax },
        { duration: rampDown, target: 0 },
      ],
      gracefulRampDown: "15s",
    },
  },
  thresholds: {
    http_req_duration: ["p(95)<3000"],
    checks: ["rate>=0.99"],
  },
};

export default function () {
  const ah = token ? { headers: { Authorization: `Bearer ${token}` } } : {};

  const oa = http.get(`${base}/api/openapi.json`, ah);
  check(oa, { "openapi 200": (r) => r.status === 200 });

  if (token) {
    const batch = http.batch([
      ["GET", `${base}/api/cluster/orchestration`, null, ah],
      ["GET", `${base}/api/cluster/nodes`, null, ah],
      ["GET", `${base}/api/cluster/pods`, null, ah],
      ["GET", `${base}/api/auth/me`, null, ah],
    ]);
    check(batch[0], { "orchestration 200": (r) => r.status === 200 });
    check(batch[1], { "nodes 200": (r) => r.status === 200 });
    check(batch[2], { "pods 200": (r) => r.status === 200 });
    check(batch[3], { "auth_me 200": (r) => r.status === 200 });
  }

  sleep(sleepSec);
}
