#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PRIMARY="$(git -C "$DIR" worktree list --porcelain | sed -n 's/^worktree //p' | head -1)"
WORKSPACE_ROOT="$(dirname "$PRIMARY")"
export TASKAND_ROOT="${TASKAND_ROOT:-$WORKSPACE_ROOT/taskand}"
export PAXLET_ROOT="${PAXLET_ROOT:-$WORKSPACE_ROOT/paxlet}"
export NL_DSL_SH_ROOT="${NL_DSL_SH_ROOT:-$WORKSPACE_ROOT/nl-dsl-sh}"
export PYTHONDONTWRITEBYTECODE=1
mode="${1:-local}"
shift "$(( $# > 0 ? 1 : 0 ))"
case "$mode" in
  local|benchmark)
    PYTHON_EXEC="${TASKAND_SHELL_PYTHON:-$TASKAND_ROOT/.subactor/cache/shell-venv/bin/python}"
    [[ -x "$PYTHON_EXEC" ]] || { echo 'Install the Taskand shell environment first.' >&2; exit 2; }
    export PYTHONPATH="$DIR:$TASKAND_ROOT:$PAXLET_ROOT:$NL_DSL_SH_ROOT/src"
    if [[ "$mode" == benchmark ]]; then
      exec "$PYTHON_EXEC" "$DIR/benchmark_autonomy.py" "$@"
    fi
    exec "$PYTHON_EXEC" -m unittest discover -s "$DIR" -p 'test_*.py' -v
    ;;
  docker)
    export AUTONOMY_BUILD_CONTEXT="$(mktemp -d)"
    trap 'rm -rf -- "$AUTONOMY_BUILD_CONTEXT"' EXIT
    python3 "$DIR/stage_docker.py" "$AUTONOMY_BUILD_CONTEXT"
    docker compose -p paxlet-autonomy-002 -f "$DIR/docker/compose.e2e.yml" build
    docker compose -p paxlet-autonomy-002 -f "$DIR/docker/compose.e2e.yml" run --rm --no-deps autonomy-e2e-runner "$@"
    ;;
  *) echo 'Usage: run_e2e.sh local|benchmark|docker [arguments]' >&2; exit 2 ;;
esac
