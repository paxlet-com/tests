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

Optional live probe (three paid provider calls maximum, no repair retries):

```bash
PYTHONPATH="$TASKAND_ROOT:tests" "$TASKAND_SHELL_PYTHON" tests/benchmark_live.py \
  --env-file /path/to/operator.env \
  --image paxlet-autonomy-002-autonomy-e2e-runner \
  --output /tmp/autonomy-live.json
```

The image must first be built by the Docker runner. The live probe resolves its
immutable ID, plans on the host and runs each generated plan in a separate
restricted container without provider credentials. It reports provider usage
when available, latency, and independently checked outputs. Three simple
prompts do not establish general reliability or capacity.

Paxlet permission fields are declarations, not an OS sandbox. Receipts contain
input/output hashes; these tests do not claim signatures or immutability.
Local mode runs only fixed test-authored programs; use Docker for isolation.
