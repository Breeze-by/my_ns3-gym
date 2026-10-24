"""Metadata-only classification regression using V44's actual CPU receipts.

No preflight main, source mutation, native input, model or simulator is run.
The only artificial inputs are Git-inventory membership and in-memory bytes.
"""

import copy
import importlib
from pathlib import Path

import pytest


preparing = importlib.import_module(
    'report.assets.20261022_mr3_p2a_v45_preparation_classification.prepare_plan_v1')
historical = importlib.import_module(
    'report.assets.20261022_mr3_p2a_v44_support_native.prepare_plan_v1')

ROS_TEST_PREFIX = (
    'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/')
NEW_ROS_TESTS = frozenset(ROS_TEST_PREFIX + name for name in (
    'test_mr3_reach_support.py',
    'test_mr3_reach_support_runtime.py',
    'test_mr3_reach_support_wiring.py',
))
SUPPORT_SOURCE = (
    'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/'
    'multi_robot_exploration/mr3_reach_support.py')


@pytest.fixture(scope='module')
def inventories():
    """Only the three newly committed tests differ; all actual bytes stay put."""
    current = preparing.preparation.source_inventory(preparing.ROOT)
    return set(current) - NEW_ROS_TESTS, set(current) | NEW_ROS_TESTS


def verify_with_inventory(module, inventory, monkeypatch, *, inputs=None):
    # source_inventory supplies classification only. All original Inputs,
    # receipt hashes, recovery bytes and current-source checks still execute.
    with monkeypatch.context() as patch:
        patch.setattr(module.preparation, 'source_inventory',
                      lambda root: set(inventory))
        return module.verify_preparation_evidence(inputs=inputs)


def test_v45_whole_proof_and_read_bindings_are_independent_of_git_test_membership(
        inventories, monkeypatch):
    assert preparing.CPU_INPUTS == historical.CPU_INPUTS
    before, after = inventories
    before_proof, before_inputs = verify_with_inventory(preparing, before, monkeypatch)
    after_proof, after_inputs = verify_with_inventory(preparing, after, monkeypatch)
    assert before_proof == after_proof
    assert before_inputs.proofs == after_inputs.proofs
    assert before_proof['current_runtime_and_test_sources_checked'] == 271
    assert {row['id'] for row in before_proof['entries']} == set(historical.CPU_INPUTS)
    assert len(before_proof['entries']) == 5
    assert before_proof['passed'] is True
    assert before_proof['scientific_pass_claimed'] is False
    assert before_proof['native_admission'] is False
    assert before_proof['native_or_qualification_credit'] is False
    assert before_proof['fresh_full_native_qualification_required'] is True
    assert NEW_ROS_TESTS <= before_inputs.proofs.keys()

    # The regression uses the retained V44 original receipts, including their
    # explicit source bindings for all three tests before they were tracked.
    original_sources = set()
    for wait_path, _ in historical.CPU_INPUTS.values():
        wait = historical.decode(Path(wait_path).read_bytes())
        original_sources.update(
            str(Path(row['path']).resolve().relative_to(preparing.ROOT))
            for row in wait['source_before'])
    assert NEW_ROS_TESTS <= original_sources


def test_original_v44_difference_is_exactly_the_retained_268_to_271_count(
        inventories, monkeypatch):
    before, after = inventories
    original, _ = verify_with_inventory(historical, before, monkeypatch)
    committed, _ = verify_with_inventory(historical, after, monkeypatch)
    sealed = historical.decode(historical.PLAN.read_bytes())[
        'prospective_preparation_requirement']
    assert original == sealed
    assert original['current_runtime_and_test_sources_checked'] == 268
    assert committed['current_runtime_and_test_sources_checked'] == 271
    expected = copy.deepcopy(original)
    expected['current_runtime_and_test_sources_checked'] += len(NEW_ROS_TESTS)
    assert committed == expected


@pytest.mark.parametrize('relative', sorted(NEW_ROS_TESTS) + [SUPPORT_SOURCE])
def test_untracked_classification_cannot_hide_changed_current_test_or_runtime_bytes(
        relative, inventories, monkeypatch):
    class ChangedMemoryInputs(preparing.Inputs):
        changed = False

        def read(self, path):
            raw = super().read(path)
            if Path(path).resolve() == preparing.ROOT / relative:
                self.changed = True
                return raw + b'\n# artificial in-memory byte mismatch\n'
            return raw

    inputs = ChangedMemoryInputs()
    before, _ = inventories
    # Also remove the new runtime helper. Both explicit unions must keep
    # their real current-source SHA gate regardless of tracked membership.
    with pytest.raises(ValueError, match=(
            'tested runtime/test source differs from current preparation: ' + relative)):
        verify_with_inventory(preparing, before - {SUPPORT_SOURCE}, monkeypatch,
                              inputs=inputs)
    assert inputs.changed is True
