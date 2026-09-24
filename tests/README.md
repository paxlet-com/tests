# Taskand shell autonomy measurements

The suite covers `nl-dsl-sh` planning/compilation, Paxlet export, digest checks,
execution receipts, Taskand CLI routing and build/run separation. It does not
exercise the complete Taskand planner/validator/orchestrator loop.

```bash
bash tests/run_e2e.sh local
bash tests/run_e2e.sh benchmark --repetitions 5 --output /tmp/autonomy.json
bash tests/run_e2e.sh docker
bash tests/run_e2e.sh docker tests/benchmark_autonomy.py --repetitions 5
```

Local and offline Docker runs explicitly select `test_autonomy_flow`,
`test_live_benchmark`, and `test_doctor_policy`; they do not discover cluster
suites, even when cluster containers happen to be running. The doctor check
supplies a deterministic `PEER_DOWN` finding to the real prescription procedure
and fails if human routing is missing.

Local tests need Taskand's installed shell Python. Sibling repository paths are
resolved from the registered primary checkout; overrides are `TASKAND_ROOT`,
`PAXLET_ROOT`, `NL_DSL_SH_ROOT`, and `TASKAND_SHELL_PYTHON`.

Docker stages committed Taskand files and explicit local Paxlet/nl-dsl-sh package
sources, recording their SHA-256 inventory. It never mounts whole checkouts or
publishes ports. Dependency installation uses the network during the build;
runtime uses no network, an unprivileged user, a read-only filesystem, temporary
storage, dropped capabilities and CPU/memory/PID limits. Transitive dependency
versions are not locked; retain the resulting image ID with each measurement.

The offline benchmark rotates three routes over three fixed tasks. It checks
expected outputs and receipt hashes, records stage latency, model call counts,
median and nearest-rank p95. `catalog` must use zero calls. `scripted-generation`
and `scripted-repair` use test doubles; their timings measure local mechanisms,
not a real LLM. Five refusal controls cover missing aliases, exhausted repairs,
clarification, reuse-only violations and invalid DAGs. Failures affect exit status.

Optional live probe (default: at most three model calls, no repair retries):

```bash
PYTHONPATH="$TASKAND_ROOT:tests" "$TASKAND_SHELL_PYTHON" tests/benchmark_live.py \
  --env-file /path/to/operator.env \
  --image paxlet-autonomy-002-autonomy-e2e-runner \
  --output /tmp/autonomy-live.json
```

The image must first be built by the Docker runner. The live probe resolves its
immutable ID, plans on the host and runs each generated plan in a separate
restricted container without provider credentials. It reports provider usage
for every attempt, latency, and independently checked outputs. Unknown usage
is explicit and excluded from known token totals. Repeating a normalized
response stops repair. A self-consistent receipt cannot make an incorrect
answer pass: the output must match an independent expected result, and receipt
identity, action, exit codes and input/output/package digests must agree.

For providers that respond with a Markdown JSON block, opt in explicitly:

```bash
# Add these options to the command above (at most six calls across three tasks):
--json-mode off --response-envelope json-fence --repair-attempts 1
```

This accepts exactly one whole-response JSON fence, preserves embedded code,
and rejects extra prose or multiple fences. The default remains strict JSON.
These options affect benchmark tooling, not the deployed gateway or upstream
`nl-dsl-sh`. `--task sort` limits a probe to one task; `--repair-attempts` accepts
0, 1 or 2. Reports require a fresh output path to preserve earlier failures.
`--artifacts-dir /private/new-directory` explicitly retains original responses
in new directories with mode 0700 and files with mode 0600; artifacts are absent
by default. Provider exception messages and credentials are excluded from reports.

Three simple prompts do not establish general reliability or capacity.

Paxlet permission fields are declarations, not an OS sandbox. Receipts contain
input/output hashes; these tests do not claim signatures or immutability.
Local mode runs only fixed test-authored programs; use Docker for isolation.

## Explicit three-node cluster tests

`bash tests/run_cluster_test.sh` provisions the named cluster fixture and runs
its suites. It rebuilds containers and removes fixture volumes; reserve that
fixture before invoking it. Local/offline runs above do not invoke this script.

The cluster tests cover dry-run SSH provisioning, peer monitoring, package
transfer and execution. `PEER_DOWN` requires human prescription in the supplied
fixture; this is a routing assertion, not a proof against every replication path.
The multi-node Paxlet test starts from a test-authored intermediate plan and
executes on nodes sequentially. It does not measure live natural-language
planning, concurrent execution, signed receipts or recovery under failure.

Background gossip tests exercise discovery and replication under their configured
test policy. Automatic approval depends on that configuration. Production rollout,
convergence under faults, restarts and concurrent tasks require separate evidence.
