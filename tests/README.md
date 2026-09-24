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

Docker stages committed Taskand/Paxlet files and records their Git revisions.
A Git-backed nl-dsl-sh source is also pinned to its commit; a distributed source
without Git uses an explicit package inventory pinned by SHA-256. Test sources
include the reviewable working diff and have a separate file inventory. It never mounts whole checkouts or
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

Use source checkouts containing bounded Taskand gossip and the immutable Paxlet
store. Their versions are development revisions; the report records exact input
commits and content inventory rather than inferring support from a version label.

```bash
TASKAND_ROOT=/path/to/taskand-checkout \
PAXLET_ROOT=/path/to/paxlet-checkout \
NL_DSL_SH_ROOT=/path/to/nl-dsl-sh \
CLUSTER_REPORT_DIR=/tmp/new-cluster-report \
  bash tests/run_cluster_test.sh
```

Each invocation creates a unique Compose project and an internal Docker network,
three real Taskand gateways and a test runner. No ports, host directories, Docker
socket, SSH keys or persistent volumes are shared. Nodes run without root or
capabilities, with read-only image filesystems and bounded temporary storage.
The runner removes only its own project resources on success or failure. Image
building requires network access; the cluster network has no external routing.

The fixtures use distinct synthetic admin, peer-read and controller credentials.
B accepts packages as candidates, C explicitly opts into automatic approval.
Tests verify that a peer's read grant cannot trigger sync, approve or execute a
package. Health/catalog probes have no bearer; only the configured source receives
its read credential. Advertised endpoints remain observations.

One source node compiles a fixed test-authored plan into a Paxlet archive. The
archive travels unchanged inside the current flat Taskand carrier package. The
runner retains its original archive hash and Paxlet digest, verifies them on each
node, explicitly activates B, then verifies outputs and receipt bindings. No
recipient regenerates the plan. A mismatch must fail before execution. Each call
uses a verified Paxlet store and an independent writable execution copy.

Other cases exercise gateway stop/restart with retained state, idempotent retries,
truncated HTTP bodies, changed archive bytes, redirects, immutable URI conflicts,
serialized sync requests and concurrent executions. A test-only transport proxy
injects faults; the actual gateway, grant checks, worker, registry and Paxlet
runtime remain production code. Fixture controls exist only inside this private
network and do not grant any production capability.

Reports preserve dependency revisions or snapshot digests, test-source hashes,
image ID, test output, container logs and cleanup status. An existing run.json
cannot be overwritten. No paid live-model calls occur in this suite. It does not
establish a Paxlet-native Taskand catalog, revision/tombstone convergence, signed
receipts or exactly-once execution after uncertain outcomes.

The older test_autonomous_gossip.py and test_nl_paxlet_cluster_pipeline.py scripts
are legacy fixtures and are no longer selected by the cluster runner. Their fixed
container assumptions and destination regeneration are superseded by
ClusterReplicationTests. Offline local selection remains unchanged.
