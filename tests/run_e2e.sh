#!/usr/bin/env bash
# Runner for Paxlet & Taskand autonomy E2E test suite.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Resolve workspace root reliably whether in primary checkout or worktree
if [[ -d "$DIR/../../taskand" ]]; then
  WORKSPACE_ROOT="$(cd "$DIR/../.." && pwd)"
elif [[ -d "$DIR/../../../taskand" ]]; then
  WORKSPACE_ROOT="$(cd "$DIR/../../.." && pwd)"
else
  WORKSPACE_ROOT="/home/tom/github/paxlet-com"
fi

mode="${1:-local}"

export TASKAND_ROOT="${TASKAND_ROOT:-$WORKSPACE_ROOT/taskand}"
export PAXLET_ROOT="${PAXLET_ROOT:-$WORKSPACE_ROOT/paxlet}"
export NL_DSL_SH_ROOT="${NL_DSL_SH_ROOT:-$WORKSPACE_ROOT/nl-dsl-sh}"

if [[ "$mode" == "docker" ]]; then
  echo "==> Running Autonomy E2E tests in Docker Compose..."
  docker compose -f "$DIR/docker/compose.e2e.yml" up --build --abort-on-container-exit --exit-code-from autonomy-e2e-runner
else
  echo "==> Running Autonomy E2E tests locally..."
  SHELL_PYTHON="${TASKAND_SHELL_PYTHON:-$TASKAND_ROOT/.subactor/cache/shell-venv/bin/python}"
  if [[ -x "$SHELL_PYTHON" ]]; then
    PYTHON_EXEC="$SHELL_PYTHON"
  else
    PYTHON_EXEC="python3"
  fi
  PYTHONPATH="$DIR:$TASKAND_ROOT:$PAXLET_ROOT:$NL_DSL_SH_ROOT" \
    "$PYTHON_EXEC" -m unittest discover -s "$DIR" -p "test_*.py" -v
fi
