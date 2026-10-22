"""Actual constructor/launch statements with fake IO, no ROS graph or plant."""
import ast
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from launch import LaunchContext
from rclpy.node import Node
from multi_robot_exploration import motion_safety as guard
from test_mr3_adapter_launch import configured_launch
from test_mr3_worker_bootstrap import WORKER


REACH_LAUNCH = {'execution_mode': 'adapter', 'mr3_stepped': 'true',
                'robot_count': '3', 'mr3_safety_contract': 'mr3-reach-v1'}


def fake_motion_constructor(monkeypatch, *, rule=None, supplied=True, contract='mr3-reach-v1'):
    records, created = [], []
    values = {'episode_epoch': 'cpu-epoch', 'stepped_mode': contract == 'mr3-reach-v1',
              'safety_contract': contract}
    if supplied:
        values['reach_geometry_rule'] = rule
    monkeypatch.setattr(Node, '__init__', lambda self, name: None)
    monkeypatch.setattr(guard.MotionSafety, 'declare_parameter',
                        lambda self, name, default: SimpleNamespace(value=values.get(name, default)))
    for method in ('create_publisher', 'create_subscription', 'create_timer'):
        monkeypatch.setattr(guard.MotionSafety, method,
            lambda self, *args, _method=method, **kwargs: created.append(_method) or SimpleNamespace())
    monkeypatch.setattr(guard, 'MotionControlPhase', lambda owner: SimpleNamespace())
    monkeypatch.setattr(guard.MotionSafety, 'record', lambda self, kind, payload:
                        records.append((kind, copy.deepcopy(payload))))
    node = guard.MotionSafety()
    return node, dict(records)['configuration'], created


def test_effective_v2_motion_configuration_constructs_all_three_real_trackers(monkeypatch):
    node, config, _ = fake_motion_constructor(monkeypatch, rule='cone-support-v2')
    assert set(node.reach) == {'tb1', 'tb2', 'tb3'}
    assert {tracker.reach_geometry_rule for tracker in node.reach.values()} == {'cone-support-v2'}
    assert config['reach_geometry_rule'] == 'cone-support-v2'
    assert config['safety_contract'] == 'mr3-reach-v1'


def test_default_motion_configuration_omits_field_and_equals_explicit_v1(monkeypatch):
    _, default, _ = fake_motion_constructor(monkeypatch, supplied=False)
    _, explicit, _ = fake_motion_constructor(monkeypatch, rule='binary-cone-v1')
    assert json.dumps(default, sort_keys=True) == json.dumps(explicit, sort_keys=True)
    assert 'reach_geometry_rule' not in default


@pytest.mark.parametrize('rule,contract', [
    (None, 'mr3-reach-v1'), (True, 'mr3-reach-v1'), ('unknown', 'mr3-reach-v1'),
    ('cone-support-v2', 'legacy'),
])
def test_motion_parameter_unknown_or_incompatible_profile_rejected(monkeypatch, rule, contract):
    with pytest.raises(ValueError):
        fake_motion_constructor(monkeypatch, rule=rule, contract=contract)


def test_real_launch_passes_v2_to_motion_guard_not_merely_adapter(monkeypatch):
    _, _, nodes, _ = configured_launch(monkeypatch, **REACH_LAUNCH,
                                      mr3_reach_geometry_rule='cone-support-v2')
    motion = [kwargs for _, kwargs in nodes if kwargs['executable'] == 'motion_safety']
    assert len(motion) == 1
    assert motion[0]['parameters'][0]['reach_geometry_rule'] == 'cone-support-v2'
    assert motion[0]['parameters'][0]['safety_contract'] == 'mr3-reach-v1'


def test_default_real_launch_motion_parameter_dictionary_omits_new_rule(monkeypatch):
    _, _, nodes, _ = configured_launch(monkeypatch, **REACH_LAUNCH)
    motion = next(kwargs for _, kwargs in nodes if kwargs['executable'] == 'motion_safety')
    assert 'reach_geometry_rule' not in motion['parameters'][0]


@pytest.mark.parametrize('value', ['unknown', 'None', 'true', 'cone-support-v1'])
def test_launch_rejects_unknown_rule(monkeypatch, value):
    with pytest.raises(ValueError, match='reach_geometry_rule'):
        configured_launch(monkeypatch, **REACH_LAUNCH, mr3_reach_geometry_rule=value)


def test_v2_launch_rejects_legacy_motion_profile(monkeypatch):
    with pytest.raises(ValueError, match='requires explicit'):
        configured_launch(monkeypatch, execution_mode='adapter', mr3_stepped='true',
                          mr3_reach_geometry_rule='cone-support-v2')


def test_duplicate_reach_geometry_launch_arguments_rejected(monkeypatch):
    original = LaunchContext.__init__

    def initialize(self, *args, **kwargs):
        kwargs['argv'] = ['mr3_reach_geometry_rule:=cone-support-v2',
                          'mr3_reach_geometry_rule:=cone-support-v2']
        original(self, *args, **kwargs)

    monkeypatch.setattr(LaunchContext, '__init__', initialize)
    with pytest.raises(ValueError, match='duplicate mr3_reach_geometry_rule'):
        configured_launch(monkeypatch, **REACH_LAUNCH, mr3_reach_geometry_rule='cone-support-v2')


@pytest.mark.parametrize('value', [None, True, 1, 'unknown'])
def test_worker_rejects_invalid_reset_rule_before_any_node_or_process(tmp_path, monkeypatch, value):
    monkeypatch.setattr(WORKER, 'protocol_version', lambda value:
                        (_ for _ in ()).throw(AssertionError('passed early rule validation')))
    request = {'epoch': 'cpu-epoch', 'scene': 'open', 'seed': 101,
               'safety_contract': 'mr3-reach-v1', 'reach_geometry_rule': value}
    with pytest.raises(ValueError, match='reach_geometry_rule'):
        WORKER.Worker(tmp_path, request)
    assert list(tmp_path.iterdir()) == []


def worker_launch_tail(tmp_path, monkeypatch, rule):
    """Execute the original __init__ command+metadata statements, not a copy.

    Preceding ROS/thread setup and following log-open/Popen are excluded. The
    only actual write is synthetic metadata under this pytest tmp_path.
    """
    path = Path(WORKER.__file__)
    tree = ast.parse(path.read_text())
    worker = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'Worker')
    init = next(node for node in worker.body if isinstance(node, ast.FunctionDef) and node.name == '__init__')
    start = next(i for i, node in enumerate(init.body) if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Attribute) and target.attr == 'command' for target in node.targets))
    end = next(i for i, node in enumerate(init.body[start:], start) if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == 'output' for target in node.targets))
    tail = ast.Module(body=copy.deepcopy(init.body[start:end]), type_ignores=[])
    ast.fix_missing_locations(tail)
    owner = SimpleNamespace(epoch='cpu-epoch', scene='open', seed=101,
        safety_contract='mr3-reach-v1', reach_geometry_rule=rule,
        seed_rule='exact-point-bridge-v2', start_graph_rule='point-attachment-3x3-v1',
        terminal_probe=False, plant_stimulus_arm=None, plant_stimulus_work_deadline_ns=None,
        transport_environment={}, control_version=2)
    monkeypatch.setattr(WORKER.subprocess, 'check_output', lambda *args, **kwargs: 'f'*40)
    namespace = dict(vars(WORKER), self=owner, directory=tmp_path)
    exec(compile(tail, str(path), 'exec'), namespace)
    return owner, json.loads((tmp_path/'metadata.json').read_text())


def test_actual_worker_command_and_metadata_both_bind_v2_once(tmp_path, monkeypatch):
    owner, metadata = worker_launch_tail(tmp_path, monkeypatch, 'cone-support-v2')
    assert owner.command.count('mr3_reach_geometry_rule:=cone-support-v2') == 1
    assert metadata['reach_geometry_rule'] == 'cone-support-v2'
    assert metadata['command'] == owner.command
    assert metadata['safety_contract'] == 'mr3-reach-v1'


def test_actual_worker_default_command_and_metadata_omit_new_field(tmp_path, monkeypatch):
    owner, metadata = worker_launch_tail(tmp_path, monkeypatch, 'binary-cone-v1')
    assert not any(value.startswith('mr3_reach_geometry_rule:=') for value in owner.command)
    assert 'reach_geometry_rule' not in metadata


@pytest.mark.parametrize('rule', ['binary-cone-v1', 'cone-support-v2'])
def test_worker_validates_and_keeps_exact_reset_selection_before_io(tmp_path, monkeypatch, rule):
    class BeforeIO(Exception):
        pass
    monkeypatch.setattr(WORKER, 'protocol_version', lambda value:
                        (_ for _ in ()).throw(BeforeIO()))
    owner = WORKER.Worker.__new__(WORKER.Worker)
    with pytest.raises(BeforeIO):
        WORKER.Worker.__init__(owner, tmp_path, {'epoch':'cpu-epoch','scene':'open','seed':101,
            'safety_contract':'mr3-reach-v1','reach_geometry_rule':rule})
    assert owner.reach_geometry_rule == rule
    assert list(tmp_path.iterdir()) == []


def test_old_reset_without_rule_keeps_binary_default_before_io(tmp_path, monkeypatch):
    class BeforeIO(Exception):
        pass
    monkeypatch.setattr(WORKER, 'protocol_version', lambda value:
                        (_ for _ in ()).throw(BeforeIO()))
    owner = WORKER.Worker.__new__(WORKER.Worker)
    with pytest.raises(BeforeIO):
        WORKER.Worker.__init__(owner, tmp_path, {'epoch':'cpu-epoch','scene':'open','seed':101,
                                               'safety_contract':'mr3-reach-v1'})
    assert owner.reach_geometry_rule == 'binary-cone-v1'
