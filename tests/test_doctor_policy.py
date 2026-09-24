import json
import os
import subprocess
import unittest
from doctor_policy import PEER_DOWN_INPUT, assert_peer_down_human
from test_autonomy_flow import TASKAND_ROOT


class DoctorPolicyTest(unittest.TestCase):
    def test_real_prescribe_routes_supplied_peer_failure_to_human(self):
        executable = TASKAND_ROOT / 'generated/doctor/prescribe/taskand.dev/v1/bin.mjs'
        result = subprocess.run(['node', str(executable)], input=json.dumps(PEER_DOWN_INPUT),
                                text=True, capture_output=True, timeout=10,
                                env={'PATH': os.environ['PATH']})
        self.assertEqual(result.returncode, 0, result.stderr)
        assert_peer_down_human(json.loads(result.stdout))

    def test_missing_failed_or_wrong_routing_is_rejected(self):
        for data in ({}, {'ok': False}, {'ok': True, 'prescriptions': []},
                     {'ok': True, 'prescriptions': [{'finding': {'code': 'PEER_DOWN'}, 'executor': 'organism'}]}):
            with self.subTest(data=data), self.assertRaises(AssertionError):
                assert_peer_down_human(data)
