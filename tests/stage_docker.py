"""Stage committed dependency inputs and explicit test sources, never host state."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile


def committed_source(source, destination, paths, *, snapshot_allowed=False):
    revision = subprocess.run(['git', '-C', str(source), 'rev-parse', 'HEAD'], capture_output=True, text=True)
    if revision.returncode and snapshot_allowed:
        # Distributed nl-dsl-sh source can lack Git metadata. Pin its exact
        # explicit package inventory and record that it is not a Git revision.
        files = []
        for name in paths:
            path = source / name
            files.extend(path.rglob('*') if path.is_dir() else [path])
        files = [p for p in files if '__pycache__' not in p.parts and not any(v.endswith('.egg-info') for v in p.parts)]
        if any(p.is_symlink() for p in files):
            raise ValueError('Source snapshot symlink is not allowed')
        files = sorted(p for p in files if p.is_file() and p.suffix != '.pyc')
        if any(p.suffix not in {'.py', '.json', '.txt', '.toml', '.md'} and p.name != 'py.typed' for p in files):
            raise ValueError('Unsupported file in explicit source snapshot')
        before = {str(p.relative_to(source)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
        destination.mkdir()
        for p in files:
            target = destination / p.relative_to(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(p, target)
        after = {name: hashlib.sha256((destination / name).read_bytes()).hexdigest() for name in before}
        current = {name: hashlib.sha256((source / name).read_bytes()).hexdigest() for name in before}
        if before != after or before != current:
            raise ValueError('Source snapshot changed while staging')
        return 'snapshot:sha256:' + hashlib.sha256(json.dumps(before, sort_keys=True).encode()).hexdigest()
    revision.check_returncode()
    head = revision.stdout.strip()
    subprocess.run(['git', '-C', str(source), 'diff', '--quiet', 'HEAD', '--', *paths], check=True)
    destination.mkdir()
    archive = destination.parent / (destination.name + '.tar')
    with archive.open('wb') as stream:
        subprocess.run(['git', '-C', str(source), 'archive', head, '--', *paths], stdout=stream, check=True, timeout=30)
    with tarfile.open(archive) as stream:
        stream.extractall(destination, filter='data')
    archive.unlink()
    return head


def tests_dirty(tests):
    return bool(subprocess.check_output(
        ['git', '-C', str(tests.parent), 'status', '--porcelain', '--', tests.name]))


def stage(out):
    tests = Path(__file__).resolve().parent
    heads = {}
    for env, name, paths in [('TASKAND_ROOT', 'taskand', ['.']),
                             ('PAXLET_ROOT', 'paxlet', ['pyproject.toml', 'README.md', 'paxlet']),
                             ('NL_DSL_SH_ROOT', 'nl-dsl-sh', ['pyproject.toml', 'README.md', 'src'])]:
        heads[name] = committed_source(Path(os.environ[env]), out / name, paths, snapshot_allowed=name == 'nl-dsl-sh')
    allowed = {'.py', '.sh', '.md', '.yml', '.yaml'}
    names = subprocess.check_output(['git', '-C', str(tests.parent), 'ls-files',
        '--cached', '--others', '--exclude-standard', '-z', '--', 'tests'], text=True).split('\0')
    for name in names:
        if not name:
            continue
        source = tests.parent / name
        if source.is_symlink():
            raise ValueError('Test source symlink is not allowed')
        if not source.is_file() or (source.suffix not in allowed and not source.name.startswith('Dockerfile')):
            continue
        target = out / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    heads['tests'] = subprocess.check_output(['git', '-C', str(tests), 'rev-parse', 'HEAD'], text=True).strip()
    files = {str(p.relative_to(out)): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in sorted(out.rglob('*')) if p.is_file()}
    report = {'schema': 'paxlet-tests.source-inventory/v1', 'heads': heads, 'files': files,
              'testsDirty': tests_dirty(tests)}
    (out / 'source-inventory.json').write_text(json.dumps(report, sort_keys=True) + '\n')
    print(json.dumps({'source_files': len(files), 'heads': heads,
                     'inventory_sha256': hashlib.sha256((out / 'source-inventory.json').read_bytes()).hexdigest()}))


if __name__ == '__main__':
    stage(Path(sys.argv[1]))
