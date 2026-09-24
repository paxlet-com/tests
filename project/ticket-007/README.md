# Ticket 007: Complete isolated autonomy tests and verified live outcomes

- **ID**: ticket-007
- **Owner**: session:user
- **Status**: IN_PROGRESS
- **Workflow state**: PUBLICATION
- **Created**: 2026-09-24

## Goal and scope

SESSION_EXECUTION_AUTHORIZATION: user confirmed Antigravity has finished and Codex is the sole writer. Continue the unfinished testing scope of merged ticket-006 after its worktree was removed. Existing lease was cancelled, not reclaimed. Improve measured natural-language task outcomes using explicit local suite selection, mandatory PEER_DOWN assertions and a live benchmark that supports one whole-response JSON fence without altering embedded code. Keep provider JSON mode explicit, bound repair, detect repeated responses, sum usage, verify receipts and preserve failures. This is test/benchmark tooling; production gateway and upstream nl-dsl-sh remain separate delivery scopes.

## Acceptance criteria

- [x] AC-01: Local and offline Docker runners cannot discover mutating cluster suites implicitly.
- [x] AC-02: A deterministic PEER_DOWN fixture is mandatory; missing or incorrect routing fails.
- [x] AC-03: Strict optional outer-fence handling preserves code and rejects extra text; every model attempt and total known usage is recorded, with missing usage explicit and repeated repairs stopped.
- [x] AC-04: Regression tests, isolated Docker tests, bounded live probe and governance pass or preserve precise outcome failures in the report.

## Remaining work

True live NL-to-three-node evaluation, fault/restart/concurrency measurements, independently provisioned CI runtime and production gossip rollout remain distinct subsequent slices. Do not weaken protected review or substitute local test success for approval.

## Evidence and delivery

See [measured outcomes](../../tests/RESULTS-2026-09-24-outcomes.md): 22/22 local and 22/22 offline Docker; 3/3 live verified outcomes, 4119 tokens, no repair; governance passed. Original responses and checkpoints are in the external ticket-007 state directory. Source publication proceeds through a PR; trusted review and protected CI remain required before merge.
