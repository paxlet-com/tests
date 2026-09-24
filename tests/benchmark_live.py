"""Explicit opt-in: at most three provider calls; generated plans run in offline Docker."""
import argparse
import dataclasses
import hashlib
import json
from pathlib import Path
import subprocess
import time
import uuid

from benchmark_autonomy import TASKS, source_identity
from nl_dsl_sh import Engine, LLMConfig, LiteLLMClient

RECEIVER = '''import json, sys, tempfile
from pathlib import Path
from app.shell_workflow import export_package, run_package
with tempfile.TemporaryDirectory() as tmp:
    package = Path(tmp) / 'pkg'
    exported = export_package(json.load(sys.stdin), package, urn='urn:paxlet:benchmark:live', permissions={})
    result = run_package(package, expected_digest=exported['digest'], timeout=5)
    print(json.dumps(result))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', required=True)
    parser.add_argument('--image', required=True, help='Image from run_e2e.sh docker; resolved to immutable ID')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--task', choices=[task[0] for task in TASKS])
    args = parser.parse_args()
    image = subprocess.check_output(['docker', 'image', 'inspect', '--format', '{{.Id}}', args.image], text=True, timeout=10).strip()
    config = dataclasses.replace(LLMConfig.from_env(args.env_file), timeout=35, max_tokens=3000)
    rows = []
    from litellm import completion
    for name, prompt, _, expected in TASKS:
        if args.task and name != args.task:
            continue
        if name == 'sort':
            prompt += ' Format wyniku: tablica JSON liczb.'
        row = {'task': name, 'passed': False, 'model_calls': 0, 'usage': None, 'stage': 'planning'}
        def measured_completion(**kwargs):
            row['model_calls'] += 1
            response = completion(**kwargs)
            usage = response.usage
            if usage:
                row['usage'] = {key: getattr(usage, key, None) for key in ('prompt_tokens', 'completion_tokens', 'total_tokens')}
            return response
        start = time.perf_counter()
        container = 'paxlet-autonomy-live-' + uuid.uuid4().hex[:12]
        try:
            engine = Engine(llm=LiteLLMClient(config, completion=measured_completion), repair_attempts=0)
            plan = engine.plan(prompt + ' Wypisz tylko wynik, bez opisu. Użyj Python i biblioteki standardowej.', language='python')
            row['planning_ms'] = (time.perf_counter() - start) * 1000
            row['plan_sha256'] = plan.sha256
            row['stage'] = 'container-execution'
            run_start = time.perf_counter()
            command = ['docker', 'run', '--rm', '-i', '--name', container, '--network=none', '--read-only',
                       '--user=65534:65534', '--cap-drop=ALL', '--security-opt=no-new-privileges',
                       '--pids-limit=64', '--memory=256m', '--cpus=1',
                       '--tmpfs=/tmp:rw,nosuid,nodev,size=32m,mode=1777', '-w', '/tmp',
                       '-e', 'HOME=/tmp', image, '-c', RECEIVER]
            completed = subprocess.run(command, input=plan.model_dump_json(), text=True, capture_output=True, timeout=12)
            row['container_execution_ms'] = (time.perf_counter() - run_start) * 1000
            row['container_exit_code'] = completed.returncode
            if completed.returncode == 0:
                row['stage'] = 'output-verification'
                result = json.loads(completed.stdout)
                from paxlet.receipt import value_digest
                output, receipt = result['output'], result['receipt']
                row['stdout_preview'] = output['stdout'][:256]
                row['receipt_package_digest'] = receipt['package_digest']
                row['output_sha256'] = hashlib.sha256(output['stdout'].encode()).hexdigest()
                # Sorting whitespace may differ while the semantic result remains correct.
                correct = json.loads(output['stdout']) == [2, 2, 7, 9] if name == 'sort' else output['stdout'] == expected
                row['passed'] = correct and output['exit_code'] == 0 and receipt['output_digest'] == value_digest(output)
            else:
                row['error_type'] = 'container_execution_failed'
        except Exception as error:
            # Provider errors can include credentials or request contents.
            row['error_type'] = type(error).__name__
            if isinstance(error, ValueError) and str(error).startswith('Plan validation failed'):
                row['error_code'] = 'PLAN_VALIDATION_FAILED'
            elif isinstance(error, ValueError) and str(error).startswith('Incomplete LLM output'):
                row['error_code'] = 'INCOMPLETE_MODEL_RESPONSE'
        finally:
            subprocess.run(['docker', 'rm', '-f', container], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        row['total_ms'] = (time.perf_counter() - start) * 1000
        rows.append(row)
        args.output.write_text(json.dumps({'schema': 'paxlet-tests.live-benchmark/v1', 'model': config.model,
            'image': image, 'source': source_identity(), 'trials': rows,
            'limitations': ['Three simple prompts, no statistical generalization.',
                            'No repairs enabled; at most three model requests.',
                            'Host plans only; Paxlet execution in offline resource-limited Docker.',
                            'Tests the shell pipeline, not the full planner/orchestrator.']}, indent=2) + '\n')
        print(json.dumps(row), flush=True)
    return 0 if all(row['passed'] for row in rows) else 1

if __name__ == '__main__':
    raise SystemExit(main())
