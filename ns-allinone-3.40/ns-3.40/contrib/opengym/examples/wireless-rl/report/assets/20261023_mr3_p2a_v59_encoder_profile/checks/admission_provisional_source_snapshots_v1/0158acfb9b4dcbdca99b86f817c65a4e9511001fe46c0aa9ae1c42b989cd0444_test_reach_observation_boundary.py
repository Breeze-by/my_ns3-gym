"""CPU fixed tensor projection has no safety-sidecar input channels."""
import copy
import unittest
import numpy as np

from mr3_learning.observation import encode_snapshot
from mr3_learning.tests.test_observation import fixture, seal


class ReachObservationBoundaryTests(unittest.TestCase):
    def test_all_fixed_tensors_ignore_execution_promises_while_position_remains_observed(self):
        source = fixture()
        expected = encode_snapshot(source)
        changed = copy.deepcopy(source)
        for index, row in enumerate(changed['robots']):
            row['safety'] = {'intent': {'role': 'N', 'intent_sequence': index+100,
                                      'admitted_signs': [-1]},
                             'calibration': {'coefficient_c': .25, 'coefficient_s': .75}}
        actual = encode_snapshot(seal(changed))
        self.assertEqual(set(actual), set(expected))
        for key in expected:
            np.testing.assert_array_equal(actual[key], expected[key])
        changed['robots'][0]['x'] += .5
        self.assertFalse(np.array_equal(encode_snapshot(seal(changed))['robots'], expected['robots']))
