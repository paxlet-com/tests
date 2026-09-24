# Ticket 003: Validate Taskand cluster mesh SSH and registry replication across 3 nodes

- **ID**: ticket-003
- **Owner**: Tom Softreck
- **Status**: IN_PROGRESS
- **Workflow state**: PUBLICATION
- **Created**: 2026-09-24

## Goal and scope

Establish a 3-node Docker Compose cluster environment (`tests/docker/compose.cluster.yml`, `tests/docker/Dockerfile.cluster`) with preconfigured SSH keys and HTTP gateway federation. Investigate and validate:
1. Whether Taskand performs autonomous SSH replication (verifying that SSH node provisioning is strictly operator-driven with `occupy --run` and dry-run by default, with `PEER_DOWN` requiring human intervention).
2. Autonomous inter-node peer discovery, health monitoring, and cryptographic package replication into `generated/` folders across the mesh.

## Acceptance criteria

- [x] AC-01: Build and configure a 3-node Taskand cluster with passwordless SSH and isolated data volumes.
- [x] AC-02: Implement `tests/test_cluster_replication.py` validating SSH connectivity and operator-only `occupy` policy.
- [x] AC-03: Validate that nodes discover peers and monitor cluster health (`cluster/monitor`).
- [x] AC-04: Validate autonomous package transfer over HTTP, SHA-256 verification, and `generated/` folder update into candidate/active status.
- [x] AC-05: Provide automated execution script `tests/run_cluster_test.sh` and update documentation.
- [x] AC-06: Governance checks pass cleanly with 0 errors and 0 warnings.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
