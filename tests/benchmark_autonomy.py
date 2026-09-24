"""Offline mechanism benchmark: scripted responses do not measure live LLM quality."""
from __future__ import annotations
import argparse
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import platform
import statistics
import sys
import tempfile
import time

from test_autonomy_flow import TASKAND_ROOT
sys.path.insert(0, str(TASKAND_ROOT))
from app.shell_workflow import run_package, verify_package
from nl_dsl_sh import Catalog, Engine
from nl_dsl_sh.engine import ClarificationRequired
from nl_dsl_sh.interop import export_paxlet
from paxlet.receipt import value_digest

TASKS = [
    ('sum', 'Oblicz sumę liczb od 1 do 100.', "print(sum(range(1, 101)))\n", '5050\n'),
    ('sort', 'Posortuj liczby 7, 2, 9, 2 rosnąco.', "import json\nprint(json.dumps(sorted([7,2,9,2])))\n", '[2, 2, 7, 9]\n'),
    ('unicode', 'Wypisz polskie słowo zażółć wielkimi literami.', "print('zażółć'.upper())\n", 'ZAŻÓŁĆ\n'),
]

class ScriptedModel:
    def __init__(self, responses):
        self.responses = responses
        self.calls = 0
    def complete(self, messages):
        value = self.responses[min(self.calls, len(self.responses) - 1)]
        self.calls += 1
        return value


def plan_json(code):
    return json.dumps({'schema_version': '0.1', 'name': 'benchmark', 'steps': [
        {'id': 'compute', 'kind': 'generate', 'language': 'python', 'code': code}]})


def trial(route, task):
    name, prompt, code, expected = task
    model = ScriptedModel((['not JSON'] if route == 'scripted-repair' else []) + [plan_json(code)])
    timings = {}
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix='autonomy-benchmark-') as tmp:
        root = Path(tmp)
        catalog = Catalog()
        if route == 'catalog':
            source = root / 'source.py'
            source.write_text(code)
            catalog.import_script(source, script_id='urn:nl-dsl-sh:benchmark:' + name,
                                  description=prompt, language='python', aliases=[prompt])
        engine = Engine(catalog=catalog, llm=model, repair_attempts=2)
        def stage(key, operation):
            before = time.perf_counter()
            result = operation()
            timings[key] = (time.perf_counter() - before) * 1000
            return result
        plan = stage('plan', lambda: engine.plan(prompt, language='python'))
        artifact = stage('compile', lambda: engine.compile(plan, format='python'))
        package = stage('export', lambda: export_paxlet(artifact, root / 'pkg', urn='urn:paxlet:benchmark:' + name, permissions={}))
        verified = stage('verify', lambda: verify_package(package))
        result = stage('run', lambda: run_package(package, expected_digest=verified['digest'], timeout=5))
        output, receipt = result['output'], result['receipt']
        passed = (output['stdout'] == expected and output['exit_code'] == 0
                  and receipt['package_digest'] == verified['digest']
                  and receipt['input_digest'] == value_digest({'stdin': ''})
                  and receipt['output_digest'] == value_digest(output)
                  and json.loads(Path(result['receipt_path']).read_text()) == receipt)
        return {'route': route, 'task': name, 'passed': passed, 'model_calls': model.calls,
                'artifact_sha256': artifact.sha256, 'stage_ms': timings,
                'total_ms': (time.perf_counter() - started) * 1000}


def refusals():
    good = plan_json("print('should not execute')\n")
    bad_dag = json.loads(good)
    bad_dag['steps'][0]['needs'] = ['missing']
    cases = [('missing-alias', None, False, 0, ValueError),
             ('repair-exhausted', ['not JSON'], False, 3, ValueError),
             ('clarification', ['{"clarification":"Which file?"}'], False, 1, ClarificationRequired),
             ('reuse-only', [good], True, 3, ValueError),
             ('broken-dag', [json.dumps(bad_dag)], False, 3, ValueError)]
    results = []
    for name, responses, reuse, expected_calls, exception in cases:
        model = ScriptedModel(responses) if responses else None
        start = time.perf_counter()
        rejected = False
        try:
            Engine(llm=model, repair_attempts=2).plan('unknown goal', language='python', reuse_only=reuse)
        except exception:
            rejected = True
        calls = model.calls if model else 0
        results.append({'case': name, 'passed': rejected and calls == expected_calls,
                        'model_calls': calls, 'total_ms': (time.perf_counter() - start) * 1000})
    return results


def source_identity():
    identity = {'python': platform.python_version(), 'packages': {name: importlib.metadata.version(name) for name in ('paxlet', 'nl-dsl-sh')}}
    identity['taskand_shell_sha256'] = hashlib.sha256((TASKAND_ROOT / 'app/shell_workflow.py').read_bytes()).hexdigest()
    inventory = Path('/workspace/source-inventory.json')
    if inventory.is_file():
        identity['docker_source_inventory_sha256'] = hashlib.sha256(inventory.read_bytes()).hexdigest()
    else:
        import nl_dsl_sh, paxlet
        for name, module in [('nl_dsl_sh', nl_dsl_sh), ('paxlet', paxlet)]:
            root = Path(module.__file__).parent
            identity[name + '_files'] = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc'}
    return identity


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repetitions', type=int, default=5)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if not 1 <= args.repetitions <= 30:
        parser.error('repetitions must be 1..30')
    rows = []
    # Alternate routes to reduce systematic warm-cache/order bias. No retries of failures.
    routes = ['catalog', 'scripted-generation', 'scripted-repair']
    for repetition in range(args.repetitions):
        for task in TASKS:
            for route in routes[repetition % 3:] + routes[:repetition % 3]:
                try:
                    rows.append(trial(route, task))
                except Exception as error:
                    rows.append({'route': route, 'task': task[0], 'passed': False, 'error_type': type(error).__name__})
    controls = refusals()
    summary = {}
    for route in routes:
        group = [row for row in rows if row['route'] == route]
        latency = sorted(row['total_ms'] for row in group if 'total_ms' in row)
        summary[route] = {'passed': sum(row['passed'] for row in group), 'total': len(group),
                          'model_calls': sum(row.get('model_calls', 0) for row in group),
                          'median_ms': statistics.median(latency) if latency else None,
                          'p95_ms': latency[math.ceil(.95 * len(latency)) - 1] if latency else None}
    report = {'schema': 'paxlet-tests.autonomy-benchmark/v1', 'source': source_identity(),
              'repetitions': args.repetitions, 'summary': summary, 'refusals': controls, 'trials': rows,
              'limitations': ['Offline scripted models: not live LLM accuracy, latency, tokens or cost.',
                              'Component pipeline, not the Taskand planner/orchestrator or production gateway.',
                              'Paxlet permissions are declarations; OS isolation comes from Docker only.',
                              'Receipt hashes checked, no signature or immutability claim.',
                              'Small deterministic workloads; p95 is descriptive, not a capacity estimate.']}
    rendered = json.dumps(report, indent=2, ensure_ascii=False) + '\n'
    if args.output:
        args.output.write_text(rendered)
    else:
        print(rendered, end='')
    return 0 if all(row['passed'] for row in rows + controls) else 1

if __name__ == '__main__':
    raise SystemExit(main())
