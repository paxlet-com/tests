"""Mandatory assertions for deterministic doctor prescription evidence."""
PEER_DOWN_INPUT = {'diagnosis': {'healthy': False, 'findings': [
    {'code': 'PEER_DOWN', 'subject': 'http://unreachable.invalid:8077'}]}}


def assert_peer_down_human(data):
    if data.get('ok') is not True:
        raise AssertionError('Prescription call did not succeed')
    prescriptions = data.get('prescriptions')
    if not isinstance(prescriptions, list):
        raise AssertionError('Missing prescriptions list')
    matches = [p for p in prescriptions if p.get('finding', {}).get('code') == 'PEER_DOWN']
    if not matches:
        raise AssertionError('Missing PEER_DOWN prescription')
    if any(p.get('executor') != 'human' for p in matches):
        raise AssertionError('PEER_DOWN must be assigned to human executor')
