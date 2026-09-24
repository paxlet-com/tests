#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TESTS_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
COMPOSE_FILE="${TESTS_ROOT}/tests/docker/compose.cluster.yml"

echo "=== [1/3] Starting Taskand 3-Node Cluster ==="
docker compose -f "${COMPOSE_FILE}" up -d --build

echo "=== [2/3] Waiting for Cluster Nodes to Settle ==="
sleep 5

echo "=== [3/3] Running Cluster Mesh and Replication Test Suite ==="
python3 "${TESTS_ROOT}/tests/test_cluster_replication.py"

echo "=== Cluster Replication Test Suite: PASSED ==="
