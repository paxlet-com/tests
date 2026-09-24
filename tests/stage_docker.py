"""Stage explicit source inputs only; never mount a host checkout into the runner."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

out = Path(sys.argv[1])
tests = Path(__file__).resolve().parent
taskand = Path(os.environ['TASKAND_ROOT'])
# The production checkout may contain credentials and runtime state. Only Git's
# committed tree is eligible, never its untracked files or .git directory.
archive = out / 'taskand.tar'
with archive.open('wb') as stream:
    subprocess.run(['git', '-C', str(taskand), 'archive', 'HEAD'], stdout=stream, check=True, timeout=30)
(out / 'taskand').mkdir()
with tarfile.open(archive) as stream:
    stream.extractall(out / 'taskand', filter='data')
archive.unlink()
for env, directory, package in [('PAXLET_ROOT', 'paxlet', 'paxlet'), ('NL_DSL_SH_ROOT', 'nl-dsl-sh', 'src')]:
    source = Path(os.environ[env])
    destination = out / directory
    destination.mkdir()
    for name in ('pyproject.toml', 'README.md'):
        shutil.copyfile(source / name, destination / name)
    shutil.copytree(source / package, destination / package, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.egg-info'))
shutil.copytree(tests, out / 'tests', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
files = {str(p.relative_to(out)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.rglob('*')) if p.is_file()}
(out / 'source-inventory.json').write_text(json.dumps(files, sort_keys=True) + '\n')
print(json.dumps({'source_files': len(files), 'inventory_sha256': hashlib.sha256((out / 'source-inventory.json').read_bytes()).hexdigest()}))
