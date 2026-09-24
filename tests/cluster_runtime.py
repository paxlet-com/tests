"""Disposable fixture controls and transport fault injection; never a product API."""
from __future__ import annotations

from collections import deque
import base64
import contextlib
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

SOURCE = Path('/workspace/taskand')
ROOT = Path('/tmp/cluster-node')
REGISTRY = 'proc://taskand.dev/registry/core/v1'
NAME = re.compile(r'[a-z][a-z0-9-]{0,48}')
HTTP = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def credential(node, role):
    if node not in ('a', 'b', 'c') or role not in ('admin', 'read', 'control'):
        raise ValueError('invalid fixture identity')
    return f'fixture-{role}-{node}'


def request(url, payload=None, token=None, timeout=8):
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    req = urllib.request.Request(url, data=None if payload is None else json.dumps(payload).encode(), headers=headers)
    try:
        response = HTTP.open(req, timeout=timeout)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        raw = response.read(32 * 1024 * 1024 + 1)
        if len(raw) > 32 * 1024 * 1024:
            raise ValueError('fixture response too large')
        return response.status, json.loads(raw)


def control(node, action, **data):
    status, result = request(f'http://node-{node}:8078/control',
                             {'action': action, **data}, credential(node, 'control'), timeout=20)
    if status != 200 or result.get('ok') is not True:
        raise AssertionError((node, action, status, result))
    return result


def wait_for(probe, *, seconds=30, description='condition'):
    deadline = time.monotonic() + seconds
    last = None
    while time.monotonic() < deadline:
        try:
            last = probe()
            if last:
                return last
        except (OSError, ValueError, AssertionError) as error:
            last = type(error).__name__
        time.sleep(0.15)
    raise AssertionError(f'{description} did not become true in {seconds}s (last={last!r})')


# The carrier invokes a transferred archive. It cannot regenerate the source plan.
INVOKE = r'''
import hashlib, json, os, sys, tempfile
from pathlib import Path
from paxlet.manifest import package_digest
from paxlet.store import put_package, materialize_package
from paxlet.runtime import run_action

try:
    data = json.load(sys.stdin)
    archive = Path(__file__).with_name('bundle.paxlet.zip')
    archive_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
    if archive_hash != data['archive_sha256']:
        raise ValueError('source archive pin mismatch')
    digest, _, stored = put_package(archive, expected_digest=data['digest'])
    executions = Path('/tmp/executions') / FIXTURE_NAME
    executions.mkdir(parents=True, exist_ok=True)
    parent = Path(tempfile.mkdtemp(dir=executions))
    execution = materialize_package(digest, parent / 'package')
    output, receipt, receipt_path = run_action(execution, 'run', {'stdin': ''}, expected_digest=data['digest'])
    print(json.dumps({'ok': receipt['exit_code'] == 0, 'archive_sha256': archive_hash,
        'digest': digest, 'store_digest': package_digest(stored), 'output': output, 'receipt': receipt,
        'receipt_path': str(receipt_path)}))
except Exception as error:
    print(json.dumps({'ok': False, 'error': type(error).__name__}))
'''


class Node:
    def __init__(self):
        self.node = os.environ['CLUSTER_NODE']
        credential(self.node, 'control')
        ROOT.mkdir()
        for name in ('gateway', 'app', 'generated', 'bin', 'operations'):
            shutil.copytree(SOURCE / name, ROOT / name, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        shutil.copyfile(SOURCE / 'gateway.py', ROOT / 'gateway.py')
        (ROOT / 'log').mkdir()
        (ROOT / 'genome.yaml').write_text('peers: []\npolicy:\n  peers: auto\norganisms:\n')
        (ROOT / 'grants.yaml').write_text(
            'users:\n  peer:\n    token: ' + credential(self.node, 'read') +
            '\n    role: user\n    allowed_uris:\n      - ' + REGISTRY +
            '\n      - proc://taskand.dev/cluster/*\n    allowed_actions:\n      - read\n')
        self.env = {'PATH': os.environ['PATH'], 'HOME': '/tmp', 'PYTHONPATH': str(ROOT),
                    'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONUNBUFFERED': '1',
                    'TASKAND_NODE': 'node-' + self.node,
                    'TASKAND_BIND': '0.0.0.0', 'TASKAND_AUTH_TOKEN': credential(self.node, 'admin'),
                    'TASKAND_GOSSIP_ENABLED': '1', 'TASKAND_GOSSIP_INTERVAL': '0.4',
                    'TASKAND_GOSSIP_AUTO_APPROVE': os.environ.get('CLUSTER_AUTO_APPROVE', '0'),
                    'TASKAND_PEERS': '' if self.node == 'a' else 'http://node-a:8079',
                    'TASKAND_GOSSIP_PEER_TOKENS': json.dumps({'http://node-a:8079': credential('a', 'read')}),
                    'PAXLET_STORE_DIR': '/tmp/paxlet-store'}
        self.process = None
        self.process_lock = threading.Lock()
        self.mode = 'pass'
        self.requests = deque(maxlen=256)
        self.start()

    def registry(self, action, **data):
        proc = subprocess.run(['node', str(ROOT / 'generated/registry/core/taskand.dev/v1/bin.mjs')],
                              input=json.dumps({'action': action, **data}), text=True, capture_output=True,
                              env=self.env, cwd=ROOT, timeout=15)
        if proc.returncode:
            raise ValueError('fixture registry process failed')
        return json.loads(proc.stdout)

    def start(self):
        with self.process_lock:
            if self.process is not None and self.process.poll() is None:
                return
            with (ROOT / 'log/gateway.log').open('ab') as log:
                self.process = subprocess.Popen([sys.executable, str(ROOT / 'gateway.py')], cwd=ROOT,
                    env=self.env, stdout=log, stderr=log, start_new_session=True)

    def stop(self):
        with self.process_lock:
            if self.process is not None and self.process.poll() is None:
                os.killpg(self.process.pid, signal.SIGTERM)
                try:
                    self.process.wait(5)
                except subprocess.TimeoutExpired:
                    os.killpg(self.process.pid, signal.SIGKILL)
                    self.process.wait(5)

    @staticmethod
    def location(name):
        if not isinstance(name, str) or not NAME.fullmatch(name):
            raise ValueError('invalid fixture name')
        uri = f'proc://taskand.dev/cluster/{name}/v1'
        return uri, ROOT / 'generated/cluster' / name / 'taskand.dev/v1'

    def publish(self, name, variant='original'):
        from app.shell_workflow import export_package
        from paxlet.packing import pack
        uri, package = self.location(name)
        source = Path('/tmp/authored') / name
        source.parent.mkdir(exist_ok=True)
        urn = f'urn:paxlet:cluster:{name}'
        code = ("import json, platform\nfrom pathlib import Path\n"
                "Path('executed').write_text('yes')\n"
                "print(json.dumps({'node': platform.node(), 'answer': 42, 'variant': " + repr(variant) + "}))\n")
        plan = {'schema_version': '0.1', 'name': name, 'steps': [
            {'id': 'report', 'kind': 'generate', 'language': 'python', 'code': code}]}
        exported = export_package(plan, source, urn=urn, permissions={'fs': ['read', 'write']})
        package.mkdir(parents=True)
        archive = pack(source, package / 'bundle.paxlet.zip')
        (package / 'invoke.py').write_text('FIXTURE_NAME = ' + repr(name) + '\n' + INVOKE)
        (package / 'proc.yaml').write_text(f'uri: {uri}\nkind: task\norigin: builtin\nenv: [PAXLET_STORE_DIR]\n')
        (package / 'bin.mjs').write_text(
            "import {spawnSync} from 'node:child_process';\n"
            "import {readFileSync} from 'node:fs';\n"
            "import {fileURLToPath} from 'node:url';\n"
            "const r=spawnSync('python3',[fileURLToPath(new URL('./invoke.py',import.meta.url))],"
            "{input:readFileSync(0),encoding:'utf8',env:process.env,timeout:15000});\n"
            "process.stdout.write(r.stdout || JSON.stringify({ok:false,error:'INVOKE_FAILED'}));\n")
        registered = self.registry('register', uri=uri, origin='builtin')
        if not registered.get('ok'):
            raise ValueError('fixture package registration failed')
        return {'ok': True, 'uri': uri, 'urn': urn, 'digest': exported['digest'],
                'hash': registered['entry']['hash'], 'archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest()}

    def inspect(self, name):
        uri, directory = self.location(name)
        archive = directory / 'bundle.paxlet.zip'
        entries = self.registry('list')['processes']
        entry = next((e for e in entries if e['uri'] == uri), None)
        executions = Path('/tmp/executions') / name
        return {'ok': True, 'entry': entry, 'exists': directory.exists(),
                'archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest() if archive.exists() else None,
                'mtime_ns': archive.stat().st_mtime_ns if archive.exists() else None,
                'markers': len(list(executions.glob('*/package/executed'))) if executions.exists() else 0,
                'receipts': len(list(executions.glob('*/package/.paxlet/receipts/*'))) if executions.exists() else 0,
                'authored': (Path('/tmp/authored') / name).exists(),
                'stages': len(list((ROOT / 'generated/cluster').glob('*/taskand.dev/.incoming-*')))}

    def command(self, body):
        action = body['action']
        if action == 'ready':
            return {'ok': True, 'node': self.node, 'gateway_running': self.process.poll() is None}
        if action == 'publish':
            return self.publish(body['name'], body.get('variant', 'original'))
        if action == 'inspect':
            return self.inspect(body['name'])
        if action == 'stop':
            self.stop()
        elif action == 'start':
            self.start()
        elif action == 'fault':
            if body['mode'] not in ('pass', 'truncated', 'tampered', 'redirect', 'slow'):
                raise ValueError('unknown fault')
            self.mode = body['mode']
        elif action == 'requests':
            return {'ok': True, 'requests': list(self.requests)}
        elif action == 'advertise':
            result = self.registry('peer_add', url='http://unpaired:8077')
            if not result.get('ok'):
                raise ValueError('could not configure observed peer')
        elif action == 'policy':
            from doctor_policy import PEER_DOWN_INPUT, assert_peer_down_human
            proc = subprocess.run(['node', str(ROOT / 'generated/doctor/prescribe/taskand.dev/v1/bin.mjs')],
                input=json.dumps(PEER_DOWN_INPUT), capture_output=True, text=True, env=self.env, timeout=10)
            assert_peer_down_human(json.loads(proc.stdout))
        else:
            raise ValueError('unsupported control action')
        return {'ok': True}


def serve():
    node = Node()

    class Control(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            if self.path != '/control' or self.headers.get('Authorization') != 'Bearer ' + credential(node.node, 'control'):
                self.send_error(403)
                return
            try:
                size = int(self.headers.get('Content-Length', 0))
                if not 0 < size <= 8192:
                    raise ValueError('invalid request size')
                response = node.command(json.loads(self.rfile.read(size)))
                status = 200
            except Exception as error:
                response, status = {'ok': False, 'error': type(error).__name__, 'detail': str(error)[:200]}, 500
            data = json.dumps(response).encode()
            self.send_response(status)
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    class Proxy(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def forward(self):
            bearer = self.headers.get('Authorization')
            role = 'none' if bearer is None else next((role for role in ('admin', 'read', 'control')
                if bearer == 'Bearer ' + credential(node.node, role)), 'other')
            observed = {'method': self.command, 'path': self.path, 'credential': role}
            node.requests.append(observed)
            size = int(self.headers.get('Content-Length', 0))
            if size > 262144:
                observed['status'] = 413
                self.send_error(413)
                return
            body = self.rfile.read(size) if self.command == 'POST' else None
            mode = node.mode
            package = self.path == '/api/registry' and body and json.loads(body).get('action') == 'package'
            if mode == 'slow':
                time.sleep(0.5)
            if package and mode == 'redirect':
                observed['status'] = 302
                self.send_response(302)
                self.send_header('Location', 'http://node-c:8079/redirect-capture')
                self.send_header('Content-Length', '0')
                self.end_headers()
                return
            try:
                req = urllib.request.Request('http://127.0.0.1:8077' + self.path, data=body,
                    headers={'Content-Type': 'application/json', **({'Authorization': bearer} if bearer else {})})
                try:
                    response = HTTP.open(req, timeout=6)
                except urllib.error.HTTPError as error:
                    response = error
                with response:
                    status, data = response.status, response.read(32 * 1024 * 1024)
            except OSError:
                status, data = 502, b'{"ok":false}'
            observed['status'] = status
            if package and mode == 'tampered' and status == 200:
                value = json.loads(data)
                value['result']['files']['bundle.paxlet.zip'] = base64.b64encode(b'changed archive').decode()
                data = json.dumps(value).encode()
            self.send_response(status)
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            if package and mode == 'truncated':
                data = data[:len(data)//2]
            with contextlib.suppress(BrokenPipeError, ConnectionResetError):
                self.wfile.write(data)
            self.close_connection = True

        do_GET = forward
        do_POST = forward

    control_server = ThreadingHTTPServer(('0.0.0.0', 8078), Control)
    proxy_server = ThreadingHTTPServer(('0.0.0.0', 8079), Proxy)
    threading.Thread(target=proxy_server.serve_forever, daemon=True).start()
    try:
        control_server.serve_forever()
    finally:
        node.stop()
        proxy_server.shutdown()
        proxy_server.server_close()
        control_server.server_close()


if __name__ == '__main__':
    if sys.argv[1:] != ['serve']:
        raise SystemExit('Use the isolated cluster runner.')
    serve()
