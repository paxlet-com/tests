#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PRIMARY="$(git -C "$DIR" worktree list --porcelain | sed -n 's/^worktree //p' | head -1)"
WORKSPACE_ROOT="$(dirname "$PRIMARY")"
export TASKAND_ROOT="${TASKAND_ROOT:-$WORKSPACE_ROOT/taskand}"
export PAXLET_ROOT="${PAXLET_ROOT:-$WORKSPACE_ROOT/paxlet}"
export NL_DSL_SH_ROOT="${NL_DSL_SH_ROOT:-$WORKSPACE_ROOT/nl-dsl-sh}"
export PYTHONDONTWRITEBYTECODE=1
RUN_ID="paxlet-cluster-$(python3 -c 'import uuid; print(uuid.uuid4().hex[:12])')"
export CLUSTER_IMAGE="$RUN_ID:fixture"
COMPOSE=(docker compose -p "$RUN_ID" -f "$DIR/docker/compose.cluster.yml")
REPORT_DIR="${CLUSTER_REPORT_DIR:-$(mktemp -d /tmp/paxlet-cluster-report.XXXXXXXX)}"
mkdir -p "$REPORT_DIR"
[[ ! -e "$REPORT_DIR/run.json" ]] || { echo 'Use a fresh report directory.' >&2; exit 2; }
export AUTONOMY_BUILD_CONTEXT="$(mktemp -d)"
export RUN_ID REPORT_DIR
cleanup() {
  code=$?
  trap - EXIT INT TERM
  log_failures=0
  "${COMPOSE[@]}" logs --no-color > "$REPORT_DIR/containers.log" 2>&1 || log_failures=$((log_failures + 1))
  for node in node-a node-b node-c; do
    "${COMPOSE[@]}" exec -T "$node" python3 -c 'from pathlib import Path; p=Path("/tmp/cluster-node/log/gateway.log"); print(p.read_text()[-16384:] if p.exists() else "Gateway log absent")' > "$REPORT_DIR/$node-gateway.log" 2>&1 || log_failures=$((log_failures + 1))
  done
  cleanup_code=0
  "${COMPOSE[@]}" down --volumes --remove-orphans --timeout 10 > "$REPORT_DIR/cleanup.log" 2>&1 || cleanup_code=$?
  docker image rm "$CLUSTER_IMAGE" >> "$REPORT_DIR/cleanup.log" 2>&1 || code=1
  remaining="$(docker ps -aq --filter "label=com.docker.compose.project=$RUN_ID")" || code=1
  [[ "$cleanup_code" == 0 && -z "$remaining" ]] || code=1
  rm -rf -- "$AUTONOMY_BUILD_CONTEXT" || code=1
  python3 - "$code" "$cleanup_code" "$log_failures" <<'PY' || code=1
import json, os, sys
from pathlib import Path
p=Path(os.environ['REPORT_DIR'])
(p/'run.json').write_text(json.dumps({'project':os.environ['RUN_ID'],'exitCode':int(sys.argv[1]),
    'cleanupExitCode':int(sys.argv[2]),'logFailures':int(sys.argv[3]),
    'sources':'source-inventory.json','testLog':'tests.log'},indent=2)+'\n')
PY
  echo "Cluster report: $REPORT_DIR (exit $code)"
  exit "$code"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
python3 "$DIR/stage_docker.py" "$AUTONOMY_BUILD_CONTEXT"
cp "$AUTONOMY_BUILD_CONTEXT/source-inventory.json" "$REPORT_DIR/"
"${COMPOSE[@]}" config --quiet
"${COMPOSE[@]}" build node-a > "$REPORT_DIR/build.log" 2>&1
docker image inspect "$CLUSTER_IMAGE" --format '{{.Id}}' > "$REPORT_DIR/image-id.txt"
"${COMPOSE[@]}" up -d --no-build node-a node-b node-c
"${COMPOSE[@]}" run --rm --no-deps runner 2>&1 | tee "$REPORT_DIR/tests.log"
