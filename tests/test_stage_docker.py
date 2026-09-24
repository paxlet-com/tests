"""Regression tests for stage_docker source-inventory metadata."""
import subprocess
import tempfile
from pathlib import Path
import unittest

from stage_docker import tests_dirty


def make_repo(tmp):
    subprocess.run(['git', 'init', '-q'], cwd=tmp, check=True)
    subprocess.run(['git', '-C', tmp, 'config', 'user.email', 'test@example.invalid'], check=True)
    subprocess.run(['git', '-C', tmp, 'config', 'user.name', 'test'], check=True)
    tests = Path(tmp) / 'tests'
    tests.mkdir()
    (tests / 'sample.py').write_text('x = 1\n', encoding='utf-8')
    subprocess.run(['git', '-C', tmp, 'add', 'tests/sample.py'], check=True)
    subprocess.run(['git', '-C', tmp, 'commit', '-qm', 'init'], check=True)
    return tests


class TestsDirtyTest(unittest.TestCase):
    """testsDirty must observe the tests tree relative to the repository root."""

    def test_clean_tests_tree_is_not_dirty(self):
        with tempfile.TemporaryDirectory(prefix='stage-docker-clean-') as tmp:
            tests = make_repo(tmp)
            self.assertFalse(tests_dirty(tests))

    def test_untracked_file_in_tests_is_dirty(self):
        with tempfile.TemporaryDirectory(prefix='stage-docker-untracked-') as tmp:
            tests = make_repo(tmp)
            (tests / 'new.py').write_text('y = 2\n', encoding='utf-8')
            self.assertTrue(tests_dirty(tests))

    def test_modified_file_in_tests_is_dirty(self):
        with tempfile.TemporaryDirectory(prefix='stage-docker-modified-') as tmp:
            tests = make_repo(tmp)
            (tests / 'sample.py').write_text('x = 2\n', encoding='utf-8')
            self.assertTrue(tests_dirty(tests))

    def test_dirt_outside_tests_does_not_set_tests_dirty(self):
        with tempfile.TemporaryDirectory(prefix='stage-docker-outside-') as tmp:
            tests = make_repo(tmp)
            (Path(tmp) / 'other.py').write_text('z = 3\n', encoding='utf-8')
            self.assertFalse(tests_dirty(tests))


if __name__ == '__main__':
    unittest.main()
