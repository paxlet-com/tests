# Ticket 009: Measure bounded cluster rejoin under transient catalog BUSY

- **ID**: ticket-009
- **Owner**: agent:codex
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-09-24

## Goal and scope

SESSION_EXECUTION_AUTHORIZATION: the user requested continued autonomy testing
and protected merging. A fresh three-node run on Taskand `f008a277` and Paxlet
PR #2 `aeac2ac` completed 9/10 cases: rejoin received four valid `503 BUSY`
catalog responses in the harness's 1.5-second scheduled retry window. The same
peer served `200` responses between those attempts. Preserve the failed run and
its cleanup receipt under
`~/.local/state/paxlet-tests/publication-recovery-20260924/cluster-after-taskand54`.

This tests-only slice extends the client's bounded retry window for explicit
BUSY responses and records elapsed time per attempt. It does not change gateway
capacity, promise production convergence or treat other failures as retryable.
The application work-start check admitted a new ticket with disjoint test paths;
the allocator created the canonical worktree and initial lease projection.

## Acceptance criteria

- [x] AC-01: At most seven calls and 5.25 seconds of scheduled backoff; only
  exact HTTP503 `BUSY` with `retryable=true` is retried.
- [x] AC-02: Preserve visible attempt count and elapsed time; return other
  failures immediately and retain persistent-BUSY failure after the bound.
- [ ] AC-03: Run focused regression and an isolated exact-source three-node
  test with complete cleanup, then managed governance and protected review.

## Tracking boundary

External checkpoint and delivery evidence belong under
`~/.local/state/paxlet-tests/cluster-rejoin-009/`. A green test with a wider
bound is evidence about transient rejoin behavior, not an improvement in
gateway throughput. The historical 9/10 run remains a valid failure.

## Validation

The local autonomy suite passes 25/25 using Taskand PR #56 commit `38d191c`.
The isolated three-node test against that exact Taskand commit, Paxlet PR #2
`aeac2ac` and nl-dsl-sh snapshot `2a75214` passes 10/10. The first rejoin
pull returned `200` on call 2 after one explicit `BUSY` (1,982.7 ms). The
second returned `200` on call 5 after four explicit `BUSY` responses
(7,355.9 ms). Container cleanup exited 0 with zero log collection failures.
Evidence is in `~/.local/state/paxlet-tests/cluster-rejoin-009/cluster-after-taskand56/`.
These observations show successful bounded rejoin in this run; they do not
show increased server throughput. The managed governance and protected review
are separate publication gates.
