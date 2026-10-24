import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from mr3_actual_nav2_parameters_v4 import (
    EXPECTED, TYPE_FIELDS, decode_parameters, validate_parameters, validate_status,
)


def responses(kind):
    return [SimpleNamespace(type=tag, **{TYPE_FIELDS[tag]: copy.deepcopy(value)})
            for tag, value in EXPECTED[kind].values()]


class ParameterRuleTests(unittest.TestCase):
    def test_all_three_actual_node_typed_parameter_sets(self):
        for kind, expected in EXPECTED.items():
            validate_parameters(kind, decode_parameters(list(expected), responses(kind)))

    def test_old_angular_cap_wrong_types_missing_and_nonfinite_rejected(self):
        for fault in ("old_cap", "wrong_type", "missing", "nonfinite", "wrong_smoother"):
            kind = "velocity_smoother" if fault == "wrong_smoother" else "controller_server"
            names, values = list(EXPECTED[kind]), responses(kind)
            if fault == "old_cap":
                values[0].double_value = 1.
            elif fault == "wrong_type":
                values[0] = SimpleNamespace(type=2, integer_value=0)
            elif fault == "missing":
                values.pop()
            elif fault == "nonfinite":
                values[0].double_value = float("nan")
            else:
                values[0].double_array_value[2] = 1.
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                validate_parameters(kind, decode_parameters(names, values))

    def test_status_epoch_ready_exact_clock_and_completion_scope(self):
        status = {"schema": "mr3-motion-safety-status-v1", "epoch": "fixture", "clock_ns": 100,
                  "ready": True, "completion_scope": "publication_and_local_topic_receipt",
                  "decision_sequences": {"tb1": 1, "tb2": 1, "tb3": 1}}
        validate_status(status, "fixture", 100)
        for field, value in (("epoch", "other"), ("clock_ns", 101), ("ready", False),
                             ("completion_scope", "publication_only")):
            changed = copy.deepcopy(status)
            changed[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_status(changed, "fixture", 100)


if __name__ == "__main__":
    unittest.main(verbosity=2)
