import copy
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from benchmark_autonomy import TASKS
from benchmark_live import URN, run_trial, verify_outcome
from live_observation import ObservedClient, RepeatedResponse, unwrap_response
from nl_dsl_sh import Engine, LLMConfig
from paxlet.receipt import value_digest


class PeerBackpressureTest(unittest.TestCase):
    def test_explicit_busy_recovers_with_visible_attempts(self):
        from cluster_runtime import retry_catalog_busy
        busy = {'ok': False, 'errorType': 'BUSY', 'retryable': True}
        done = {'ok': True, 'report': [{'result': 'same'}]}
        operation = Mock(side_effect=[(503, busy), (200, done)])
        with patch('cluster_runtime.time.sleep') as sleep:
            status, result, attempts = retry_catalog_busy(operation)
        self.assertEqual((status, result), (200, done))
        self.assertEqual([a['status'] for a in attempts], [503, 200])
        self.assertTrue(all(a['elapsed_ms'] >= 0 for a in attempts))
        self.assertEqual(operation.call_count, 2)
        sleep.assert_called_once_with(0.25)

    def test_persistent_busy_is_bounded_and_other_failures_are_not_retried(self):
        from cluster_runtime import retry_catalog_busy
        busy = {'ok': False, 'errorType': 'BUSY', 'retryable': True}
        operation = Mock(return_value=(503, busy))
        with patch('cluster_runtime.time.sleep') as sleep:
            status, result, attempts = retry_catalog_busy(operation)
        self.assertEqual((status, result), (503, busy))
        self.assertEqual(len(attempts), 7)
        self.assertEqual(operation.call_count, 7)
        self.assertEqual([call.args[0] for call in sleep.call_args_list],
                         [0.25, 0.5, 0.75, 1.0, 1.25, 1.5])
        for response in [(502, {'ok': False, 'errorType': 'REGISTRY_ERROR'}),
                         (503, {'ok': False, 'errorType': 'BUSY'}),
                         (403, busy), (504, {'ok': False, 'errorType': 'OUTCOME_UNKNOWN'}),
                         (200, {'ok': True, 'report': [{'result': 'rejected'}]})]:
            with self.subTest(response=response), patch('cluster_runtime.time.sleep') as sleep:
                operation = Mock(return_value=response)
                status, result, attempts = retry_catalog_busy(operation)
                self.assertEqual((status, result), response)
                operation.assert_called_once()
                sleep.assert_not_called()


class CleanupPolicyTest(unittest.TestCase):
    def test_cleanup_preserves_failure_and_checks_resource_removal(self):
        text = Path(__file__).with_name('run_cluster_test.sh').read_text()
        cleanup = 'cleanup() {' + text.split('cleanup() {', 1)[1].split('\ntrap cleanup EXIT', 1)[0]
        cases = [(0, '', '', 0), (7, '', '', 7), (7, 'compose logs', '', 7),
                 (0, 'compose logs', '', 0), (0, 'compose down', '', 1),
                 (0, 'image rm', '', 1), (0, 'ps -aq', '', 1), (0, '', 'remaining', 1)]
        for initial, failure, remaining, expected in cases:
            with self.subTest(initial=initial, failure=failure, remaining=remaining), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                report = root / 'report'
                report.mkdir()
                context = root / 'context'
                context.mkdir()
                fake = root / 'docker'
                fake.write_text('''#!/usr/bin/env python3
import os, sys
from pathlib import Path
command = ' '.join(sys.argv[1:3])
with Path(os.environ['CALL_LOG']).open('a') as log:
    log.write(command + '\\n')
if command == os.environ['FAIL_COMMAND']:
    sys.exit(9)
if command == 'ps -aq':
    print(os.environ['REMAINING'])
''')
                fake.chmod(0o700)
                env = {**os.environ, 'PATH': str(root) + os.pathsep + os.environ['PATH'],
                       'REPORT_DIR': str(report), 'AUTONOMY_BUILD_CONTEXT': str(context),
                       'CALL_LOG': str(root / 'calls'), 'FAIL_COMMAND': failure,
                       'REMAINING': remaining}
                script = ('set -euo pipefail\nCOMPOSE=(docker compose)\n'
                          'CLUSTER_IMAGE=fixture\nRUN_ID=cleanup-policy\nexport RUN_ID REPORT_DIR\n'
                          + cleanup + '\ntrap cleanup EXIT\nexit ' + str(initial))
                result = subprocess.run(['bash', '-c', script], env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, expected, result.stderr)
                receipt = json.loads((report / 'run.json').read_text())
                self.assertEqual(receipt['exitCode'], expected)
                self.assertEqual(receipt['cleanupExitCode'], 9 if failure == 'compose down' else 0)
                self.assertIn('compose down', (root / 'calls').read_text())
                self.assertIn('image rm', (root / 'calls').read_text())
                self.assertFalse(context.exists())

CONFIG = LLMConfig(model='test/model', api_key='placeholder_autonomy_test')


def plan(code="import json\nprint(json.dumps([2,2,7,9]))\n"):
    return json.dumps({'steps': [{'id': 'sort', 'kind': 'generate', 'language': 'python', 'code': code}]})


def response(content, tokens=10, reason='stop', usage=True):
    value = {'choices': [{'finish_reason': reason, 'message': {'content': content}}]}
    if usage:
        value['usage'] = {'prompt_tokens': tokens, 'completion_tokens': 2, 'total_tokens': tokens + 2}
    return value


def outcome(stdout='[2, 2, 7, 9]\n'):
    output = {'stdout': stdout, 'stderr': '', 'exit_code': 0}
    return {'output': output, 'expected_digest': 'sha256:' + '1' * 64,
            'verified_digest': 'sha256:' + '1' * 64,
            'receipt': {'identity': {'urn': URN}, 'action': 'run', 'exit_code': 0,
                        'package_digest': 'sha256:' + '1' * 64,
                        'input_digest': value_digest({'stdin': ''}), 'output_digest': value_digest(output)}}


class LiveBenchmarkTest(unittest.TestCase):
    def test_fence_preserves_json_identifiers_and_code_byte_for_byte(self):
        raw = plan()
        fenced = '```json\n' + raw + '\n```'
        self.assertEqual(unwrap_response(fenced), fenced)
        decoded = json.loads(unwrap_response(fenced, allow_fence=True))
        self.assertEqual(decoded, json.loads(raw))
        self.assertIn('import json', decoded['steps'][0]['code'])
        self.assertIn('json.dumps', decoded['steps'][0]['code'])
        for raw_input in (raw, ' \n' + raw + '\n ', '```\n' + raw + '\n```'):
            self.assertEqual(json.loads(unwrap_response(raw_input, allow_fence=True)), decoded)

    def test_extra_text_multiple_fences_and_wrong_language_cannot_plan(self):
        raw = plan()
        for content in ('Here is JSON:\n' + raw, '```python\n' + raw + '\n```',
                        '```json\n' + raw + '\n```\nextra', '```json\n' + raw,
                        '```json\n{}\n```\n```json\n' + raw + '\n```'):
            with self.subTest(content=content):
                client = ObservedClient(CONFIG, Mock(return_value=response(content)), allow_fence=True)
                with self.assertRaises(ValueError):
                    Engine(llm=client, repair_attempts=0).plan('sort', language='python')
                self.assertEqual(len(client.attempts), 1)

    def test_syntax_invalid_code_is_still_rejected_inside_valid_envelope(self):
        code = 'import \nprint(.dumps([2,2,7,9]))\n'
        client = ObservedClient(CONFIG, Mock(return_value=response('```json\n' + plan(code) + '\n```')), allow_fence=True)
        with self.assertRaises(ValueError):
            Engine(llm=client, repair_attempts=0).plan('sort', language='python')
        check = client.attempts[0]['syntax'][0]
        self.assertEqual(check['status'], 'failed')
        self.assertEqual(check['line'], 1)
        self.assertEqual(client.attempts[0]['validation'], 'schema-valid')

    def test_repair_usage_sums_every_attempt(self):
        completion = Mock(side_effect=[response('invalid JSON', 10), response(plan(), 20)])
        client = ObservedClient(CONFIG, completion, max_calls=2)
        Engine(llm=client, repair_attempts=1).plan('sort', language='python')
        self.assertEqual(completion.call_count, 2)
        self.assertEqual(client.usage_summary()['known_tokens'],
                         {'prompt_tokens': 30, 'completion_tokens': 4, 'total_tokens': 34})
        self.assertTrue(client.usage_summary()['complete'])

    def test_repeated_invalid_response_stops_before_third_request(self):
        completion = Mock(return_value=response(plan('import \n')))
        client = ObservedClient(CONFIG, completion, max_calls=3)
        with self.assertRaises(RepeatedResponse):
            Engine(llm=client, repair_attempts=2).plan('sort', language='python')
        self.assertEqual(completion.call_count, 2)
        self.assertTrue(client.attempts[-1]['repeated_response'])
        self.assertEqual(client.usage_summary()['known_tokens']['total_tokens'], 24)

    def test_missing_usage_is_unknown_and_budget_is_not_silent_retry(self):
        completion = Mock(side_effect=[response('bad', usage=False), response(plan(), 20)])
        client = ObservedClient(CONFIG, completion, max_calls=2)
        Engine(llm=client, repair_attempts=1).plan('sort', language='python')
        self.assertFalse(client.usage_summary()['complete'])
        self.assertEqual(client.usage_summary()['attempts_missing_usage'], [1])
        self.assertEqual(client.usage_summary()['known_tokens']['total_tokens'], 22)
        with self.assertRaisesRegex(ValueError, 'BUDGET_EXHAUSTED'):
            client.complete([])
        self.assertEqual(completion.call_count, 2)

    def test_provider_error_keeps_no_credentials_and_never_starts_container(self):
        completion = Mock(side_effect=RuntimeError('SECRET_VALUE from provider URL'))
        with patch('benchmark_live.subprocess.run') as docker:
            row = run_trial(TASKS[1], CONFIG, 'sha256:test', completion)
        docker.assert_not_called()
        self.assertFalse(row['passed'])
        self.assertEqual(row['model_calls'], 1)
        self.assertEqual(row['error_type'], 'RuntimeError')
        self.assertNotIn('SECRET_VALUE', json.dumps(row))
        self.assertNotIn(CONFIG.api_key, json.dumps(row))
        self.assertFalse(row['usage']['complete'])

    def test_truncation_records_usage_and_does_not_execute(self):
        completion = Mock(return_value=response(plan(), reason='length'))
        with patch('benchmark_live.subprocess.run') as docker:
            row = run_trial(TASKS[1], CONFIG, 'sha256:test', completion)
        docker.assert_not_called()
        self.assertEqual(row['error_code'], 'INCOMPLETE_MODEL_RESPONSE')
        self.assertEqual(row['usage']['known_tokens']['total_tokens'], 12)

    def test_wrong_result_fails_even_with_self_consistent_receipt(self):
        data = outcome('[2, 7, 9]\n')
        checks = verify_outcome('sort', '', data)
        self.assertFalse(checks['task_result'])
        self.assertTrue(checks['output_digest'])
        with patch('benchmark_live.subprocess.run', side_effect=[
            subprocess.CompletedProcess([], 0, json.dumps(data), ''),
            subprocess.CompletedProcess([], 0, b'', b'')]):
            row = run_trial(TASKS[1], CONFIG, 'sha256:test', Mock(return_value=response(plan())))
        self.assertFalse(row['passed'])
        self.assertEqual(row['error_code'], 'OUTCOME_NOT_VERIFIED')

    def test_each_receipt_binding_is_required(self):
        data = outcome()
        self.assertTrue(all(verify_outcome('sort', '', data).values()))
        for path, value in [(('receipt', 'input_digest'), 'bad'), (('receipt', 'output_digest'), 'bad'),
                            (('receipt', 'package_digest'), 'bad'), (('receipt', 'exit_code'), 7),
                            (('receipt', 'action'), 'other'), (('verified_digest',), 'bad'),
                            (('receipt', 'identity', 'urn'), 'urn:paxlet:other')]:
            changed = copy.deepcopy(data)
            cursor = changed
            for key in path[:-1]:
                cursor = cursor[key]
            cursor[path[-1]] = value
            with self.subTest(path=path):
                self.assertFalse(all(verify_outcome('sort', '', changed).values()))

    def test_execution_timeout_still_cleans_up_container(self):
        with patch('benchmark_live.subprocess.run', side_effect=[
            subprocess.TimeoutExpired('docker', 12), subprocess.CompletedProcess([], 0, b'', b'')]) as docker:
            row = run_trial(TASKS[1], CONFIG, 'sha256:test', Mock(return_value=response(plan())))
        self.assertFalse(row['passed'])
        self.assertEqual(row['error_type'], 'TimeoutExpired')
        self.assertEqual(docker.call_count, 2)
        self.assertEqual(docker.call_args_list[1].args[0][:3], ['docker', 'rm', '-f'])

    def test_artifacts_are_explicit_private_and_original(self):
        raw = '```json\n' + plan() + '\n```'
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / 'artifacts'
            client = ObservedClient(CONFIG, Mock(return_value=response(raw)), artifacts=directory, allow_fence=True)
            json.loads(client.complete([]))
            artifact = directory / 'response-1.txt'
            self.assertEqual(artifact.read_text(), raw)
            self.assertEqual(stat.S_IMODE(artifact.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)

    def test_local_suite_has_no_cluster_tests_or_discovery(self):
        import run_local
        def ids(suite):
            for case in suite:
                if isinstance(case, unittest.TestSuite):
                    yield from ids(case)
                else:
                    yield case.id()
        with patch.object(unittest.defaultTestLoader, 'discover', side_effect=AssertionError('implicit discovery')):
            names = list(ids(run_local.suite()))
        self.assertGreater(len(names), 10)
        self.assertFalse(any('cluster' in name.lower() or 'gossip' in name.lower() for name in names if not name.endswith('test_local_suite_has_no_cluster_tests_or_discovery')))
