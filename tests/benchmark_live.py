"""Explicit live outcome probe with bounded repair and offline Docker execution."""
import argparse
import dataclasses
import hashlib
import json
from pathlib import Path
import subprocess
import time
import uuid

from benchmark_autonomy import TASKS, source_identity
from live_observation import ObservedClient, RepeatedResponse
from nl_dsl_sh import Engine, LLMConfig
from paxlet.receipt import value_digest

URN = 'urn:paxlet:benchmark:live'
RECEIVER = '''import json, sys, tempfile
from pathlib import Path
from app.shell_workflow import export_package, run_package, verify_package
with tempfile.TemporaryDirectory() as tmp:
    package = Path(tmp) / 'pkg'
    exported = export_package(json.load(sys.stdin), package, urn='urn:paxlet:benchmark:live', permissions={})
    verified = verify_package(package)
    result = run_package(package, expected_digest=exported['digest'], timeout=5)
    result['expected_digest'] = exported['digest']
    result['verified_digest'] = verified['digest']
    print(json.dumps(result))
'''


def verify_outcome(name, expected, result):
    output, receipt = result['output'], result['receipt']
    try:
        correct = json.loads(output['stdout']) == [2, 2, 7, 9] if name == 'sort' else output['stdout'] == expected
    except json.JSONDecodeError:
        correct = False
    return {
        'task_result': correct,
        'process_exit': type(output['exit_code']) is int and output['exit_code'] == 0,
        'receipt_exit': type(receipt['exit_code']) is int and receipt['exit_code'] == 0,
        'receipt_action': receipt['action'] == 'run',
        'receipt_identity': receipt['identity']['urn'] == URN,
        'package_digest': result['expected_digest'] == result['verified_digest'] == receipt['package_digest'],
        'input_digest': receipt['input_digest'] == value_digest({'stdin': ''}),
        'output_digest': receipt['output_digest'] == value_digest(output),
    }


def run_trial(task, config, image, completion, *, repair_attempts=0, allow_fence=False, artifacts=None):
    name, prompt, _, expected = task
    if name == 'sort':
        prompt += ' Format wyniku: tablica JSON liczb.'
    prompt += ' Wypisz tylko wynik, bez opisu. Użyj Python i biblioteki standardowej.'
    client = ObservedClient(config, completion, artifacts=artifacts,
                            max_calls=repair_attempts + 1, allow_fence=allow_fence)
    row = {'task': name, 'passed': False, 'stage': 'planning', 'repair_attempts': repair_attempts,
           'prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest()}
    started = time.perf_counter()
    container = 'paxlet-autonomy-live-' + uuid.uuid4().hex[:12]
    container_started = False
    try:
        plan = Engine(llm=client, repair_attempts=repair_attempts).plan(prompt, language='python')
        row['planning_ms'] = (time.perf_counter() - started) * 1000
        row['plan_sha256'] = plan.sha256
        row['stage'] = 'container-execution'
        run_start = time.perf_counter()
        command = ['docker', 'run', '--rm', '-i', '--name', container, '--network=none', '--read-only',
                   '--user=65534:65534', '--cap-drop=ALL', '--security-opt=no-new-privileges',
                   '--pids-limit=64', '--memory=256m', '--cpus=1',
                   '--tmpfs=/tmp:rw,nosuid,nodev,size=32m,mode=1777', '-w', '/tmp',
                   '-e', 'HOME=/tmp', image, '-c', RECEIVER]
        container_started = True
        completed = subprocess.run(command, input=plan.model_dump_json(), text=True, capture_output=True, timeout=12)
        row['container_execution_ms'] = (time.perf_counter() - run_start) * 1000
        row['container_exit_code'] = completed.returncode
        if completed.returncode == 0:
            row['stage'] = 'output-verification'
            result = json.loads(completed.stdout)
            output, receipt = result['output'], result['receipt']
            row['stdout_preview'] = output['stdout'][:256]
            row['receipt_package_digest'] = receipt['package_digest']
            row['output_sha256'] = hashlib.sha256(output['stdout'].encode()).hexdigest()
            row['checks'] = verify_outcome(name, expected, result)
            row['passed'] = all(row['checks'].values())
            if not row['passed']:
                row['error_code'] = 'OUTCOME_NOT_VERIFIED'
        else:
            row['error_code'] = 'CONTAINER_EXECUTION_FAILED'
    except Exception as error:
        row['error_type'] = type(error).__name__
        if isinstance(error, RepeatedResponse):
            row['error_code'] = 'REPEATED_MODEL_RESPONSE'
        elif isinstance(error, ValueError) and str(error).startswith('Plan validation failed'):
            row['error_code'] = 'PLAN_VALIDATION_FAILED'
        elif isinstance(error, ValueError) and str(error).startswith('Incomplete LLM output'):
            row['error_code'] = 'INCOMPLETE_MODEL_RESPONSE'
        # Raw provider exception text is intentionally excluded.
    finally:
        if container_started:
            try:
                cleanup = subprocess.run(['docker', 'rm', '-f', container], capture_output=True, timeout=10)
                if cleanup.returncode and b'No such container' not in cleanup.stderr:
                    row['cleanup_failed'] = True
                    row['passed'] = False
            except Exception as error:
                row['cleanup_failed'] = True
                row['cleanup_error_type'] = type(error).__name__
                row['passed'] = False
    row.update(model_calls=len(client.attempts), attempts=client.attempts,
               usage=client.usage_summary(), total_ms=(time.perf_counter() - started) * 1000)
    if row['stage'] == 'planning':
        row['planning_ms'] = row['total_ms']
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', required=True)
    parser.add_argument('--image', required=True, help='Existing offline image, resolved to immutable ID')
    parser.add_argument('--output', type=Path, required=True, help='New report path; existing files are preserved')
    parser.add_argument('--task', choices=[task[0] for task in TASKS])
    parser.add_argument('--repair-attempts', type=int, choices=(0, 1, 2), default=0)
    parser.add_argument('--json-mode', choices=('from-env', 'on', 'off'), default='from-env')
    parser.add_argument('--response-envelope', choices=('json-only', 'json-fence'), default='json-only')
    parser.add_argument('--artifacts-dir', type=Path, help='Explicit opt-in to private model-output artifacts for reproduction')
    args = parser.parse_args()
    image = subprocess.check_output(['docker', 'image', 'inspect', '--format', '{{.Id}}', args.image], text=True, timeout=10).strip()
    config = dataclasses.replace(LLMConfig.from_env(args.env_file), timeout=35, max_tokens=3000)
    if args.json_mode != 'from-env':
        config = dataclasses.replace(config, json_mode=args.json_mode == 'on')
    selected = [task for task in TASKS if not args.task or task[0] == args.task]
    if args.artifacts_dir:
        args.artifacts_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
    report = {'schema': 'paxlet-tests.live-benchmark/v2', 'model': config.model, 'image': image,
              'source': source_identity(), 'repair_attempts': args.repair_attempts,
              'json_mode': config.json_mode, 'response_envelope': args.response_envelope,
              'max_model_calls': len(selected) * (args.repair_attempts + 1), 'trials': [],
              'limitations': ['Small fixed workload, no statistical generalization.',
                              'Host plans only; Paxlet execution in offline resource-limited Docker.',
                              'Tests the shell pipeline, not the full planner/orchestrator.',
                              'Known token totals exclude attempts without provider usage.']}
    with args.output.open('x') as stream:
        json.dump(report, stream, indent=2)
    from litellm import completion
    for task in selected:
        artifacts = args.artifacts_dir / task[0] if args.artifacts_dir else None
        row = run_trial(task, config, image, completion, repair_attempts=args.repair_attempts,
                        allow_fence=args.response_envelope == 'json-fence', artifacts=artifacts)
        report['trials'].append(row)
        report['model_calls'] = sum(trial['model_calls'] for trial in report['trials'])
        report['known_total_tokens'] = sum(trial['usage']['known_tokens']['total_tokens'] for trial in report['trials'])
        report['usage_complete'] = all(trial['usage']['complete'] for trial in report['trials'])
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
        print(json.dumps({key: row.get(key) for key in ('task', 'passed', 'stage', 'error_code', 'model_calls', 'usage', 'total_ms')}), flush=True)
    return 0 if all(row['passed'] for row in report['trials']) else 1


if __name__ == '__main__':
    raise SystemExit(main())
