"""Execution promises must not change exploration candidates or actor snapshots."""
import copy

from test_mr3_observation import robots, snapshot


def test_execution_sidecar_is_absent_from_entire_observation_candidate_mask_and_digest():
    original = robots()
    expected = snapshot(states=original)
    for role in ('HOLD', 'D', 'X', 'N', 'STOP'):
        changed = copy.deepcopy(original)
        for index, row in enumerate(changed):
            row['safety'] = {'intent': {'role': role, 'intent_sequence': 100+index,
                                      'admitted_signs': [-1, 1], 'private_marker': role},
                             'calibration': {'coefficient_c': .75, 'coefficient_s': .25}}
        assert snapshot(states=changed) == expected
    physical_change = copy.deepcopy(original)
    physical_change[0]['x'] += .5
    assert snapshot(states=physical_change) != expected
