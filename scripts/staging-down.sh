#!/usr/bin/env bash
# Снять ephemeral staging: namespace + cluster RBAC, оставшиеся после NS.
set -euo pipefail

NS="${STAGING_NS:-wolfpackcloud-control-staging}"
TIMEOUT="${STAGING_DELETE_TIMEOUT:-180s}"

echo "staging-down: namespace ${NS} (timeout ${TIMEOUT})" >&2

if kubectl get namespace "$NS" >/dev/null 2>&1; then
  kubectl delete namespace "$NS" --ignore-not-found --wait=true --timeout="${TIMEOUT}" 2>/dev/null \
    || kubectl delete namespace "$NS" --ignore-not-found --wait=false
fi

kubectl delete clusterrolebinding wolfpackcloud-control-staging-api-nodes-read --ignore-not-found
# binding мог оказаться в staging NS из-за старых apply через kustomize — чистим оба
kubectl delete rolebinding control-api-staging-zenoh -n wolfpackcloud-zenoh --ignore-not-found
kubectl delete rolebinding control-api-staging-zenoh -n wolfpackcloud-control-staging --ignore-not-found

echo "staging-down: готово" >&2
