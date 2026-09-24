"""Pytest configuration and fixtures for Paxlet & Taskand E2E tests."""

import os
import shutil
import tempfile
from pathlib import Path
import pytest

# Well-known paths to sibling checkouts
WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
TASKAND_ROOT = WORKSPACE_ROOT / "taskand"
PAXLET_ROOT = WORKSPACE_ROOT / "paxlet"
NL_DSL_SH_ROOT = WORKSPACE_ROOT / "nl-dsl-sh"

SHELL_VENV_PYTHON = TASKAND_ROOT / ".subactor/cache/shell-venv/bin/python"


@pytest.fixture
def temp_workspace():
    """Create an isolated temporary workspace for E2E tasks."""
    tmp = tempfile.mkdtemp(prefix="paxlet-tests-e2e-")
    yield Path(tmp)
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture
def shell_python():
    """Return the configured Python interpreter with paxlet and nl-dsl-sh installed."""
    if SHELL_VENV_PYTHON.is_file() and os.access(SHELL_VENV_PYTHON, os.X_OK):
        return str(SHELL_VENV_PYTHON)
    return os.environ.get("TASKAND_SHELL_PYTHON", "python3")
