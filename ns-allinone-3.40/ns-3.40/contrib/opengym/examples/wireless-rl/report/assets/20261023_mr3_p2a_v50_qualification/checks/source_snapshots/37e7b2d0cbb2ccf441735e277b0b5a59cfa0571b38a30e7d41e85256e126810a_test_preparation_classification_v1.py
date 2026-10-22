"""Prospective V50 classification and actual module-help CPU fixtures.

Not executed during template preparation. Tests consume CPU metadata only;
no native trace, model, preflight main, World or policy execution occurs.
"""
import importlib
from pathlib import Path
import subprocess
import sys

import pytest

PACKAGE = 'report.assets.20261023_mr3_p2a_v50_qualification.'
preparing = importlib.import_module(PACKAGE + 'prepare_plan_v1')
ROS_TESTS = frozenset(str(path.relative_to(preparing.ROOT)) for path in
    (preparing.ROS / 'src/multi_robot_exploration/test').glob('test_*.py'))
W_TESTS = frozenset(str(path.relative_to(preparing.ROOT)) for path in
    (preparing.W / 'mr3_learning/tests').glob('test_*.py'))
ALL_TESTS = ROS_TESTS | W_TESTS


def verify_inventory(inventory, monkeypatch, inputs=None):
    with monkeypatch.context() as patch:
        patch.setattr(preparing.preparation, 'source_inventory', lambda root: set(inventory))
        return preparing.verify_preparation_evidence(inputs=inputs)


def test_whole_proof_and_bindings_do_not_depend_on_git_test_membership(monkeypatch):
    inventory = preparing.preparation.source_inventory(preparing.ROOT)
    before, before_inputs = verify_inventory(inventory - ALL_TESTS, monkeypatch)
    after, after_inputs = verify_inventory(inventory | ALL_TESTS, monkeypatch)
    assert before == after
    assert before_inputs.proofs == after_inputs.proofs
    assert {row['id'] for row in before['entries']} == set(preparing.CPU_INPUTS) | {preparing.FRESH_CPU_GROUP}
    assert before['new_v50_orchestration_executed_by_these_receipts'] is False
    assert before['native_or_qualification_credit'] is False
    # No fragile fixed count is derived from whether a test was Git-added.
    assert before['current_runtime_and_test_sources_checked'] > 0


@pytest.mark.parametrize('relative', [
    'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_mr3_worker_startup_readiness.py',
    'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/motion_safety.py',
    'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/mr3_learning/ppo.py',
])
def test_untracked_status_cannot_hide_mutated_current_runtime_or_test(relative, monkeypatch):
    class Changed(preparing.Inputs):
        def read(self, path):
            raw = super().read(path)
            if Path(path).resolve() == preparing.ROOT / relative:
                return raw + b'\n# artificial memory-only mismatch\n'
            return raw
    inventory = preparing.preparation.source_inventory(preparing.ROOT) - ALL_TESTS - {relative}
    with pytest.raises(ValueError, match='(exact current bytes|tested runtime/test source differs)'):
        verify_inventory(inventory, monkeypatch, Changed())


@pytest.mark.parametrize('name', ['prepare_plan_v1', 'preflight_v1', 'execute_chain_v1'])
def test_new_orchestration_actual_module_help_imports(name):
    # This real subprocess only imports definitions and parses --help. Its
    # completed wait is CPU evidence, never execution of the native main path.
    result = subprocess.run([sys.executable, '-B', '-m', PACKAGE + name, '--help'],
                            cwd=preparing.W, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert 'usage:' in result.stdout


def test_pilot_finite_prefix_is_declared_prefix_with_original_episode_upper_bound():
    original = preparing.decode((preparing.PRIOR / 'predeclared_plan_v1.json').read_bytes())
    registry = preparing.policy_registry(original)
    argv = registry['pilot']['argv']
    assert preparing.preparation.argument(argv, '--decisions') == str(preparing.PILOT_REQUESTED_DECISIONS)
    assert preparing.preparation.argument(argv, '--episode-steps') == '64'
    assert preparing.preparation.argument(argv, '--workers') == '2'
    remaining, count = preparing.PILOT_REQUESTED_DECISIONS, 2
    caps = [min(64, remaining // count + (i < remaining % count)) for i in range(count)]
    assert caps == [32, 32]
    assert registry['pilot']['external_finalize_reserve_seconds'] == '300'
    assert registry['validation']['argv'][registry['validation']['argv'].index('--schedule')+1] == 'open:401,open:402,open:403'
