# Ticket 006: Harden autonomy outcome tests and bounded live repair diagnostics

- **ID**: ticket-006
- **Owner**: antigravity
- **Status**: IN_PROGRESS
- **Workflow state**: PUBLICATION
- **Created**: 2026-09-24

## Goal and scope

Harden autonomy test suites by isolating cluster-specific integration tests with cluster container readiness gating, allowing local and offline runners to cleanly skip cluster tests when Docker mesh is offline while ensuring cluster test runner executes all suites.

## Acceptance criteria

- [x] AC-01: Local and offline test runners select explicit suites and gracefully skip cluster tests when 3-node cluster containers are offline (`test_cluster_replication.py`, `test_nl_paxlet_cluster_pipeline.py`, `test_autonomous_gossip.py`).
- [x] AC-02: Cluster runner `tests/run_cluster_test.sh` continues to run all 3 suites when cluster containers are up.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
