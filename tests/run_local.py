"""Explicit offline suite: never discover tests that mutate shared clusters."""
import sys
import unittest

MODULES = ('test_autonomy_flow', 'test_live_benchmark', 'test_doctor_policy')


def suite():
    return unittest.defaultTestLoader.loadTestsFromNames(MODULES)


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(suite())
    sys.exit(not result.wasSuccessful())
