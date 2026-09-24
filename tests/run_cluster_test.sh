#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TESTS_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
COMPOSE_FILE="${TESTS_ROOT}/tests/docker/compose.cluster.yml"

GIT_COMMON="$(git rev-parse --git-common-dir 2>/dev/null || echo "")"
if [ -n "${GIT_COMMON}" ]; then
    ECOSYSTEM_ROOT="$(cd "$(dirname "${GIT_COMMON}")/.." && pwd)"
else
    ECOSYSTEM_ROOT="$(cd "${TESTS_ROOT}/../.." && pwd)"
fi

export TASKAND_SOURCE_DIR="${TASKAND_SOURCE_DIR:-${ECOSYSTEM_ROOT}/taskand}"
export PAXLET_SOURCE_DIR="${PAXLET_SOURCE_DIR:-${ECOSYSTEM_ROOT}/paxlet}"
export NL_DSL_SH_SOURCE_DIR="${NL_DSL_SH_SOURCE_DIR:-${ECOSYSTEM_ROOT}/nl-dsl-sh}"

echo "=== [1/4] Starting Taskand 3-Node Cluster (Pristine Volumes) ==="
docker compose -f "${COMPOSE_FILE}" down -v >/dev/null 2>&1 || true
docker compose -f "${COMPOSE_FILE}" up -d --build

echo "=== [2/4] Waiting for Cluster Gateways to be Healthy ==="
for port in 8071 8072 8073; do
    echo -n "Waiting for node on port ${port}..."
    READY=0
    for i in $(seq 1 30); do
        if curl -s -f "http://127.0.0.1:${port}/healthz" >/dev/null 2>&1; then
            READY=1
            echo " OK"
            break
        fi
        sleep 1
    done
    if [ "${READY}" -ne 1 ]; then
        echo " FAILED (timeout)"
        exit 1
    fi
done

echo "=== [3/4] Running Cluster Mesh and Replication Test Suite ==="
python3 "${TESTS_ROOT}/tests/test_cluster_replication.py"

echo "=== [4/4] Running End-to-End NL to Paxlet Cluster Pipeline Test Suite ==="
python3 "${TESTS_ROOT}/tests/test_nl_paxlet_cluster_pipeline.py"

echo "=== All Cluster Test Suites: PASSED ==="
