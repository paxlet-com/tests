# Ticket 010: Fix stage_docker testsDirty repo-relative status pathspec

- **ID**: ticket-010
- **Owner**: unresolved:human
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-09-24

SESSION_EXECUTION_AUTHORIZATION: the user requested continued work with
protected merge ("kontynuuj, scal, testuj").

## Goal and scope

`tests/stage_docker.py` records `testsDirty` in `source-inventory.json` by
running `git -C <repo>/tests status --porcelain -- tests`. The `tests`
pathspec is resolved relative to the working directory (`<repo>/tests`), so it
matches only the nonexistent `<repo>/tests/tests` and the report always reads
`testsDirty=false`, even for a dirty tests tree. Observed during the
ticket-009 cluster run; the per-file inventory hashes still proved the exact
staged bytes.

## Acceptance criteria

- [x] AC-01: `testsDirty` is computed with a status pathspec resolved from the
  repository root, so untracked and modified files under `tests/` report true.
- [x] AC-02: Changes outside `tests/` do not set `testsDirty`.
- [x] AC-03: Regression coverage runs in the offline `run_local.py` suite.

## Validation

`python3 -m unittest tests.test_stage_docker` (4 tests) and the offline suite
`tests/run_local.py` (29 tests) pass. `./project/governance-check.sh --base
origin/main --head HEAD` passes.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
