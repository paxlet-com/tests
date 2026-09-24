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

## Cluster continuation — 2026-09-24

SESSION_EXECUTION_AUTHORIZATION: user requested continuation and tests after
the assessment of missing peer credentials, incorrect activation assumptions and
destination-side package regeneration. Managed admission returned REUSE_EXISTING.
The previous owner cancelled its real controller lease (revision 4/fence 14);
the checkpoint and clean HEAD b98da04 were verified before resuming. No trusted
review exists for that head. Retain its commit and PR history; obtain fresh
exact-head review after this bounded tests-only extension.

- [x] AC-05: Stage exact committed Paxlet/Taskand inputs (and a digest-pinned
  nl-dsl-sh distribution when its Git metadata is absent); use unique disposable Compose
  resources and an internal network, with cleanup limited to this run.
- [x] AC-06: Test three real gateways with peer-scoped read grants, default
  candidates, explicit activation, and transfer of a source-pinned Paxlet archive
  into verified stores/materialized execution copies without destination rebuild.
- [x] AC-07: Verify offline/rejoin, interrupted import, conflicts and idempotent
  retries; rerun local regressions and governance, retaining exact reports.

The cluster slice now belongs to this ticket. Production gossip deployment and
true live-model three-node evaluation remain outside this continuation. The known
publication blockers (unavailable wellman==0.20.43 in hosted CI; absent protected
local Validator repository profile) remain external prerequisites, not bypasses.

## Cluster validation evidence

- Three-node integration: 10/10 in 64.471 s; final inventory/receipt checks:
  10/10 in 60.209 s. Every case executed; no skipped cluster tests.
- Local regressions: 22/22 in 3.603 s. The same final cluster image ran the
  explicit offline regression suite: 22/22 in 5.462 s, with network disabled.
- Inputs: Taskand 9489d912857b1f5cb35d156e9518ead361b352fe, Paxlet
  48e7203410d43a56473e81bdc3783fd09adaddaf; nl-dsl-sh source snapshot
  2a75214aa3f68dde0faeb6dd30676a86b7e92e1365c6d5c614a1d197e8bcc32d.
  The runner also checked installed Python files against the input inventory.
- Changed-path governance: PASS; no errors or warnings. Both disposable cluster
  projects and their containers/networks were removed after execution.
- No production source/configuration, provider credentials or live node data was
  changed. No paid model call was made in this continuation. This verifies the
  transitional Taskand carrier transport, not a native shared Paxlet catalog.
- External reports/checkpoints: ~/.local/state/paxlet-tests/ticket-007-cluster/.
  Preserve the known protected-CI/runtime/profile blockers for the updated HEAD;
  local results are not review or merge approval.
