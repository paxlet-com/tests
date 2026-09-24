"""Exact-source three-node integration, explicitly selected by the cluster runner."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import time
import unittest
import uuid

from cluster_runtime import control, credential, request, retry_catalog_busy, wait_for, REGISTRY

SEED = 'http://node-a:8079'


def canonical_digest(value):
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    return 'sha256:' + hashlib.sha256(data).hexdigest()


def api(node, path, body=None, role='admin'):
    token = credential(node, role) if role else None
    return request(f'http://node-{node}:8077' + path, body, token, timeout=35)


def registry(node, action, role='admin', **data):
    status, response = api(node, '/api/registry', {'action': action, **data}, role)
    return status, response.get('result', response)


class ClusterReplicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get('CLUSTER_TEST_RUN') != '1':
            raise RuntimeError('Use tests/run_cluster_test.sh; shared/live clusters are never selected.')
        for node in ('a', 'b', 'c'):
            wait_for(lambda: control(node, 'ready')['gateway_running'], seconds=45, description=node + ' controller')
            wait_for(lambda: api(node, '/healthz', role=None)[0] == 200, seconds=20, description=node + ' gateway')
        inventory = json.loads(Path('/workspace/source-inventory.json').read_text())
        # Verify the image actually contains the inventoried source, including
        # installed Python modules used by subprocesses rather than another checkout.
        import paxlet
        import nl_dsl_sh
        mappings = [('taskand/', Path('/workspace/taskand')), ('tests/', Path('/workspace/tests')),
                    ('paxlet/paxlet/', Path(paxlet.__file__).parent),
                    ('nl-dsl-sh/src/nl_dsl_sh/', Path(nl_dsl_sh.__file__).parent)]
        for prefix, directory in mappings:
            for name, expected in inventory['files'].items():
                if name.startswith(prefix) and (prefix in ('taskand/', 'tests/') or name.endswith('.py')):
                    observed = hashlib.sha256((directory / name[len(prefix):]).read_bytes()).hexdigest()
                    if observed != expected:
                        raise AssertionError('Source inventory mismatch: ' + name)
        print('CLUSTER_SOURCE_HEADS ' + json.dumps(inventory['heads']), flush=True)

    def setUp(self):
        self.name = 'artifact-' + uuid.uuid4().hex[:12]
        control('a', 'fault', mode='pass')
        control('b', 'start')
        self.addCleanup(control, 'a', 'fault', mode='pass')
        self.addCleanup(control, 'b', 'start')

    def publish(self, node='a', **kwargs):
        return control(node, 'publish', name=self.name, **kwargs)

    def observation(self, node):
        return control(node, 'inspect', name=self.name)

    def arrived(self, node, status=None):
        def probe():
            value = self.observation(node)
            entry = value['entry']
            return value if entry and (status is None or entry['status'] == status) else None
        return wait_for(probe, description=f'{self.name} on {node}, status={status}')

    def invoke(self, node, source, **overrides):
        data = {'digest': source['digest'], 'archive_sha256': source['archive_sha256'], **overrides}
        return api(node, '/api/proc/call', {'uri': source['uri'], 'data': data})

    def test_01_real_grants_and_default_activation_policy(self):
        for node in ('a', 'b', 'c'):
            self.assertEqual(api(node, '/api/cluster/gossip', role=None)[0], 401)
            self.assertEqual(api(node, '/api/cluster/gossip', {}, role='read')[0], 403)
            self.assertEqual(registry(node, 'approve', role='read', uri=REGISTRY)[0], 403)
            self.assertEqual(api(node, '/api/proc/call', {'uri': REGISTRY}, role='read')[0], 403)
            status, response = api(node, '/api/cluster/gossip', role='read')
            self.assertEqual(status, 200)
            self.assertEqual(response['auto_approve'], node == 'c')
            self.assertEqual(api(node, '/api/cluster/gossip', {'auto_approve': True})[0], 400)
        self.assertTrue(control('a', 'policy')['ok'])

    def test_02_source_pinned_archive_candidates_and_verified_execution(self):
        source = self.publish()
        for node in ('b', 'c'):
            observed = self.arrived(node, 'candidate' if node == 'b' else 'active')
            self.assertEqual(observed['archive_sha256'], source['archive_sha256'])
            self.assertEqual(observed['entry']['hash'], source['hash'])
            self.assertEqual(observed['markers'], 0)
            self.assertEqual(observed['receipts'], 0)
            self.assertFalse(observed['authored'], 'Destination must not regenerate the Paxlet package')
        self.assertEqual(self.observation('a')['markers'], 0)
        status, rejected = self.invoke('b', source)
        self.assertEqual(status, 403, rejected)
        self.assertEqual(self.observation('b')['markers'], 0)
        self.assertEqual(registry('b', 'resolve', uri=source['uri'])[0], 403)
        self.assertEqual(self.observation('b')['markers'], 0)
        status, approved = registry('b', 'approve', uri=source['uri'])
        self.assertEqual(status, 200)
        self.assertTrue(approved['ok'])
        self.assertEqual(registry('b', 'resolve', uri=source['uri'])[0], 200)
        self.assertEqual(self.observation('b')['markers'], 0)
        # A pin from the origin is mandatory even after explicit activation.
        status, wrong_pin = self.invoke('b', source, digest='sha256:' + '0' * 64)
        self.assertFalse(wrong_pin['result']['ok'], wrong_pin)
        self.assertEqual(self.observation('b')['markers'], 0)
        for node in ('a', 'b', 'c'):
            status, response = self.invoke(node, source)
            self.assertEqual(status, 200, response)
            result = response['result']
            self.assertTrue(result['ok'], response)
            self.assertEqual(result['archive_sha256'], source['archive_sha256'])
            self.assertEqual(result['digest'], source['digest'])
            self.assertEqual(result['store_digest'], source['digest'])
            outcome = json.loads(result['output']['stdout'])
            self.assertEqual(outcome, {'node': 'node-' + node, 'answer': 42, 'variant': 'original'})
            receipt = result['receipt']
            self.assertEqual(receipt['package_digest'], source['digest'])
            self.assertEqual(receipt['identity']['urn'], source['urn'])
            self.assertEqual(receipt['action'], 'run')
            self.assertEqual(receipt['exit_code'], 0)
            self.assertEqual(receipt['input_digest'], canonical_digest({'stdin': ''}))
            self.assertEqual(receipt['output_digest'], canonical_digest(result['output']))
            self.assertEqual(self.observation(node)['markers'], 1)

    def test_03_only_peer_read_credentials_leave_the_node(self):
        self.publish()
        self.arrived('b')
        observed = control('a', 'requests')['requests']
        packages = [r for r in observed if r['path'] == '/api/registry']
        self.assertTrue(packages)
        self.assertTrue(all(r['credential'] == 'read' for r in packages))
        for row in observed:
            if row['path'] in ('/healthz', '/.well-known/catalog.json'):
                self.assertEqual(row['credential'], 'none')
            self.assertNotIn(row['credential'], ('admin', 'control', 'other'))

    def test_04_offline_rejoin_and_idempotent_retry_preserve_bytes(self):
        control('b', 'stop')
        source = self.publish()
        self.assertIsNone(self.observation('b')['entry'])
        control('b', 'start')
        before = self.arrived('b', 'candidate')
        self.assertEqual(before['archive_sha256'], source['archive_sha256'])
        test_read_credential = credential('a', 'read')
        for _ in range(2):
            status, pulled, attempts = retry_catalog_busy(lambda: registry(
                'b', 'pull', peer=SEED, token=test_read_credential,
                uris=[source['uri']], expected={source['uri']: source['hash']}))
            print('CLUSTER_REJOIN_ATTEMPTS ' + json.dumps(attempts), flush=True)
            if status != 200:
                pulled = {'response': pulled, 'peer_requests': control('a', 'requests')['requests'][-10:]}
            self.assertEqual(status, 200, pulled)
            self.assertEqual(pulled['report'][0]['result'], 'same')
        after = self.observation('b')
        self.assertEqual(after['mtime_ns'], before['mtime_ns'])
        self.assertEqual(after['markers'], 0)
        self.assertEqual(after['entry']['status'], 'candidate')

    def fault_case(self, mode):
        control('a', 'fault', mode=mode)
        source = self.publish()
        def failed():
            status, state = api('b', '/api/cluster/gossip', role='read')
            peer = state.get('peers', {}).get(SEED, {})
            return status == 200 and source['uri'] in peer.get('missing_processes', []) and peer.get('error')
        wait_for(failed, description=mode + ' is reported')
        observed = self.observation('b')
        self.assertIsNone(observed['entry'])
        self.assertFalse(observed['exists'])
        self.assertEqual(observed['markers'], 0)
        wait_for(lambda: self.observation('b')['stages'] == 0, description='private stages removed')
        control('a', 'fault', mode='pass')
        fixed = self.arrived('b', 'candidate')
        self.assertEqual(fixed['archive_sha256'], source['archive_sha256'])
        self.assertEqual(fixed['markers'], 0)

    def test_05_interrupted_transport_then_retry(self):
        self.fault_case('truncated')

    def test_06_tampered_archive_then_retry(self):
        self.fault_case('tampered')

    def test_07_redirect_cannot_forward_peer_credentials(self):
        self.fault_case('redirect')
        self.assertFalse(any(r['path'] == '/redirect-capture' for r in control('c', 'requests')['requests']))

    def test_08_content_conflict_preserves_local_package(self):
        local = self.publish(node='b', variant='local')
        before = self.observation('b')
        remote = self.publish(variant='remote')
        self.assertNotEqual(local['hash'], remote['hash'])
        def conflict():
            _, state = api('b', '/api/cluster/gossip', role='read')
            return remote['uri'] in state.get('peers', {}).get(SEED, {}).get('conflicts', [])
        wait_for(conflict, description='immutable URI conflict')
        after = self.observation('b')
        self.assertEqual(after['archive_sha256'], before['archive_sha256'])
        self.assertEqual(after['mtime_ns'], before['mtime_ns'])
        self.assertEqual(after['markers'], 0)

    def test_09_serialized_rounds_and_independent_concurrent_execution(self):
        source = self.publish()
        self.arrived('b', 'candidate')
        self.assertTrue(registry('b', 'approve', uri=source['uri'])[1]['ok'])
        control('a', 'fault', mode='slow')
        with ThreadPoolExecutor(max_workers=6) as pool:
            responses = list(pool.map(lambda _: api('b', '/api/cluster/gossip', {}), range(6)))
        self.assertIn(409, [r[0] for r in responses])
        self.assertTrue(all(r[0] in (200, 409, 503) for r in responses), responses)
        control('a', 'fault', mode='pass')
        with ThreadPoolExecutor(max_workers=2) as pool:
            executions = list(pool.map(lambda _: self.invoke('b', source), range(2)))
        self.assertTrue(all(code == 200 and result['result']['ok'] for code, result in executions), executions)
        self.assertEqual(self.observation('b')['markers'], 2)
        self.assertTrue(all(result['result']['store_digest'] == source['digest'] for _, result in executions))
        self.assertEqual(self.observation('b')['receipts'], 2)
        receipts = [result['result']['receipt_path'] for _, result in executions]
        self.assertEqual(len(set(receipts)), 2)

    def test_10_discovered_peers_are_observations_only(self):
        control('a', 'advertise')
        def discovered():
            _, state = api('b', '/api/cluster/gossip', role='read')
            return 'http://unpaired:8077' in state.get('peers', {}).get(SEED, {}).get('discovered_peers', [])
        wait_for(discovered, description='unpaired endpoint observed')
        for node in ('b', 'c'):
            _, state = api(node, '/api/cluster/gossip', role='read')
            self.assertEqual(set(state['peers']), {SEED})
            self.assertEqual(registry(node, 'peers')[1]['peers'], [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
