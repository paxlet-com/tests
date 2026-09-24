# Verified live shell outcomes — 2026-09-24

Ticket-007, based on tests `d70b630`. This measures a live model → nl-dsl-sh
plan/compile → Taskand shell workflow → Paxlet export/verify/run → independent
output and receipt checks. Generated code executes in isolated, offline Docker.

## Results

| Task | Outcome | Model calls | Total tokens | End-to-end seconds |
| --- | --- | ---: | ---: | ---: |
| sum | PASS | 1 | 1395 | 10.988 |
| sort | PASS | 1 | 1406 | 10.974 |
| unicode | PASS | 1 | 1318 | 11.258 |

Three of three passed on the first attempt, with 3 calls and 4119 reported
tokens. Median end-to-end latency was 10.988 s.
Every task passed expected-result, process/receipt exit, receipt action/identity,
package-digest and input/output-digest checks. Two responses were plain JSON;
the Unicode response used one outer JSON fence. Removing only that fence
preserved the code. One repair was allowed per task; none was used.

- Model: `openai/glm-5.3`; `json_mode=false`, envelope `json-fence`.
- Limits: six model calls, 35 s and 3000 output tokens per call; 12 s container
  command timeout, 5 s program timeout, network disabled, unprivileged UID,
  read-only filesystem, CPU/memory/PID limits and explicit container cleanup.
- Python 3.13.12; Paxlet 0.1.4;
  nl-dsl-sh 0.2.0.
- Image: `sha256:33e7ae3798cbf6d4d2e8ebc715663835827f8cbd658063a05a734f0e5f4d5475`.
- Report SHA-256: `ff4d1027eb9c58337d27e3ac00be67c4be2b01aa5229eec7cfd59a771e0da7b8`.
- Operator evidence: `~/.local/state/paxlet-tests/ticket-007/live.json`,
  `live-artifacts/` (private original responses), `replay.json`, `docker.log`.
  The JSON report also records source hashes, prompt/response/plan hashes and
  per-attempt usage. These local artifacts are not committed or remotely hosted.

## Regression evidence

Local suite: 22/22 in 2.248 s. Offline Docker suite: 22/22 in 5.178 s.
Governance passed. Negative checks cover extra prose/multiple fences, invalid
Python, incomplete model output, repeated repair responses, unknown usage,
provider failure, wrong answers despite self-consistent receipts, altered receipt
bindings and container cleanup after timeout. A deterministic PEER_DOWN input
must produce human routing. Local runners explicitly exclude cluster suites.

Replaying the preserved ticket-006 fenced sorting response through this adapter
and the real offline container passed all eight outcome checks in 1.350 s,
with zero additional provider calls. Replay is not a new live success sample.

Earlier failed JSON-mode-on responses remain preserved in ticket-006 evidence;
they contained invalid Python (`import` without its name and `.dumps(...)`).
This run changes JSON mode and envelope handling together and is not a controlled
A/B comparison. It does not establish the cause of the earlier malformed code.

## Limits and follow-up

Three simple fixed tasks are not a general reliability estimate. These are
benchmark adapter changes; the production gateway and upstream nl-dsl-sh are
unchanged. Receipts bind hashes but are unsigned. The full Taskand
planner/validator/orchestrator, live NL-to-three-node execution, failure/restart
recovery and concurrent workloads need separate evaluation. Cluster suites
were not run by this ticket. Production gossip rollout on 8084 and independent
CI/merge approval remain separate delivery work.
