# Ticket 002: Measure autonomy effectiveness and harden E2E evidence

- **ID**: ticket-002
- **Owner**: session:user
- **Status**: IN_PROGRESS
- **Workflow state**: PUBLICATION
- **Created**: 2026-09-24

## Goal and scope

SESSION_EXECUTION_AUTHORIZATION: user requested continued testing and investigation of autonomy effectiveness. Harden the existing E2E suite, provide an isolated Docker runner and reproducible offline benchmark measuring verified task outcomes, latency and model calls. Use scripted model failures explicitly as simulations, not evidence of live model quality. Persist measured results externally. No production gateway changes. Publication follows protected review.

## Acceptance criteria

- [x] AC-01: Tampering and workspace confinement assertions actually execute; subprocess calls are bounded.
- [x] AC-02: Docker tests run without host ports, credentials or whole-checkout mounts, with bounded resources and no runtime network.
- [x] AC-03: Repeatable benchmark records independently checked outcomes, stage timings, model calls, repair and refusal scenarios, source identities and limitations.
- [x] AC-04: Local and Docker suites plus governance checks pass; findings and remaining work are recorded.

## Continuity

Taskand ticket-030 and ticket-049 remain in publication with PRs 49 and 48. This disjoint testing ticket builds on tests PR 1, observed merged at main 5cdb289. The allocation claim belongs to this session and is handed off to the local cooperative controller before implementation. No other claim is reclaimed.

## Evidence and remaining publication

See tests/RESULTS-2026-09-24.md and external receipt:tests/ticket-002/reviewed. Live failures are preserved findings, not waived checks. Publication requires exact-head independent approval; the deployed direct-PR registry currently has no paxlet-com/tests profile.
