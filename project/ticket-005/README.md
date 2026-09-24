# Ticket 005: Validate autonomous background gossip and continuous replication across 3 nodes

- **ID**: ticket-005
- **Owner**: antigravity
- **Status**: IN_PROGRESS
- **Workflow state**: PUBLICATION
- **Created**: 2026-09-24

## Goal and scope

Validate autonomous background gossip and continuous registry replication across a 3-node Taskand Docker Compose cluster without requiring any manual `pull` or `cluster/monitor` triggers. Ensure all nodes continuously discover peers, replicate new procedures, and auto-approve them for immediate cluster execution.

## Acceptance criteria

- [x] AC-01: Docker Compose cluster configured with `TASKAND_GOSSIP_ENABLED=1`, `TASKAND_GOSSIP_INTERVAL=2`, and `TASKAND_PEERS` (`tests/docker/compose.cluster.yml`).
- [x] AC-02: Integration test suite `tests/test_autonomous_gossip.py` validating 4 stages:
  1. Real-time gossip health and worker state across all 3 nodes (`GET /api/cluster/gossip`).
  2. Local authoring and registration of a cluster beacon procedure on Node 1.
  3. Fully autonomous background discovery, pulling, and auto-approval by Node 2 and Node 3.
  4. Execution of the replicated procedure on Node 2 and Node 3 with node identity assertions.
- [x] AC-03: Cluster test runner `tests/run_cluster_test.sh` updated to run all 3 suites.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
