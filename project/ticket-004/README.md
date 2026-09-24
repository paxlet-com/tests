# Ticket 004: Validate end-to-end NL to Paxlet cluster execution pipeline across 3 nodes

- **ID**: ticket-004
- **Owner**: Tom Softreck
- **Status**: IN_PROGRESS
- **Workflow state**: PUBLICATION
- **Created**: 2026-09-24

## Goal and scope

SESSION_EXECUTION_AUTHORIZATION: user requested end-to-end execution of the autonomous pipeline across the 3-node cluster. Validate the full workflow:
1. Natural language / intermediate plan compilation and packaging into a cryptographically verified Paxlet package (`urn:paxlet:...`) with manifest and digest computation.
2. Embedding into a Taskand cluster procedure and catalog export.
3. Autonomous mesh replication and verification across Node 2 and Node 3 (`proc://taskand.dev/cluster/monitor/v1` with `{ "pull": true }`).
4. Multi-node distributed execution with node-specific output verification and Paxlet execution receipt generation.

## Acceptance criteria

- [x] AC-01: Update cluster container environment (`Dockerfile.cluster`, `compose.cluster.yml`) with Paxlet and NL-DSL-SH dependencies.
- [x] AC-02: Implement integration test suite (`tests/test_nl_paxlet_cluster_pipeline.py`) covering the complete 4-stage pipeline.
- [x] AC-03: Update cluster test runner (`tests/run_cluster_test.sh`) to run both cluster suites.
- [x] AC-04: Full test suite passes against 3-node Docker Compose cluster and governance checks pass with 0 errors and 0 warnings.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
