"""Artificial startup ordering/receipt/deadline checks; no Node or World."""
import copy
import io
import json
from types import SimpleNamespace

import pytest

from test_mr3_worker_bootstrap import WORKER, acknowledgement


class Clock:
    ns = 100_000_000_000

    def monotonic_ns(self):
        return self.ns

    def monotonic(self):
        return self.ns / 1e9


class Condition:
    def __init__(self, clock):
        self.clock = clock

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def wait(self, seconds):
        self.clock.ns += round(seconds * 1e9)


def fixture(monkeypatch, *, reach=True):
    clock = Clock()
    monkeypatch.setattr(WORKER.time, 'monotonic_ns', clock.monotonic_ns)
    monkeypatch.setattr(WORKER.time, 'monotonic', clock.monotonic)
    worker = WORKER.Worker.__new__(WORKER.Worker)
    worker.epoch, worker.scene, worker.seed = 'current', 'rooms', 101
    worker.safety_contract = 'mr3-reach-v1' if reach else 'legacy'
    worker.control_version = 2 if reach else 1
    worker.startup_readiness_protocol = WORKER.STARTUP_READINESS_PROTOCOL if reach else None
    worker.startup_deadline_ns = clock.ns + 420_000_000_000 if reach else None
    worker.startup_wait_deadline_ns = clock.ns + 355_000_000_000 if reach else None
    worker.startup_active, worker.startup_stage = reach, 'constructing'
    worker.startup_callback_fields, worker.startup_failure_receipts = set(), []
    worker.startup_readiness_file = io.StringIO() if reach else None
    worker.condition = Condition(clock)
    worker.monitor_ready, worker.motion_ready, worker.odometry_recorder_ready = True, False, True
    worker.initial_inputs_ready = acknowledgement()
    worker.clock_ns = worker.physical_ns = 10_000_000_000
    worker.callback_error, worker.failures = None, []
    worker.cleanup_mode, worker.finished = False, False
    worker.controlled, worker.stopping = False, False
    worker.snapshot = None
    worker.launch = SimpleNamespace(poll=lambda: None)
    worker.last_native_check = float('inf')  # No launch-log read is needed for this unit.
    worker.events = []
    return worker, clock


def journal(worker):
    return [json.loads(line) for line in worker.startup_readiness_file.getvalue().splitlines()]


def test_pause_occurs_only_after_all_three_actual_upstream_inputs(monkeypatch):
    for missing in ('monitor_ready', 'initial_inputs_ready', 'odometry_recorder_ready'):
        worker, _ = fixture(monkeypatch)
        setattr(worker, missing, None if missing == 'initial_inputs_ready' else False)
        called = []
        worker._start_step_helper = lambda: called.append('helper')

        def wait(predicate, timeout, label):
            assert not predicate()
            raise TimeoutError(label)

        worker._wait = wait
        with pytest.raises(TimeoutError, match='delivered-input startup'):
            worker._pause_and_drain_startup()
        assert called == []


def test_real_pause_precedes_motion_ready_but_false_motion_cannot_reach_topology(monkeypatch):
    worker, _ = fixture(monkeypatch)
    events = []
    worker._start_step_helper = lambda: events.append('helper')
    worker._physics = lambda steps, wait_clock=False: (
        events.append(('physics', steps, wait_clock)) or {'end_time_ns': worker.physical_ns})
    worker._align_initial_clock = lambda: events.append('align')
    worker.verify_motion_output_topology = lambda: pytest.fail('motion False cannot pass topology')
    worker.verify_drive_topology = lambda: pytest.fail('motion False cannot pass topology')

    def wait(predicate, timeout, label):
        if 'paused three-robot' in label:
            assert events == ['helper', ('physics', 0, False), 'align']
            assert not predicate()
            raise TimeoutError(label)
        assert predicate()

    worker._wait = wait
    with pytest.raises(TimeoutError, match='paused three-robot'):
        worker._pause_and_drain_startup()
    assert not hasattr(worker, 'start_ns')


def complete_fixture(monkeypatch, *, reach=True, missing_storage=False):
    worker, clock = fixture(monkeypatch, reach=reach)
    events = []
    worker.started_wall = clock.monotonic()
    worker.control_phase = WORKER.ControlPhaseClient(worker.epoch, safety_contract=worker.safety_contract)
    worker.drive_phase = WORKER.DrivePhaseClient(worker.epoch)
    worker.consumed_drive_phase = None
    worker.motion_status, worker.stop_status = None, None
    worker.control_publishers = {name: name for name in ('motion', 'state', 'peer')}
    worker.motion_phase_file = io.StringIO()
    worker.control_phase_file = io.StringIO()
    worker.drive_phase_file = io.StringIO()
    worker.transition_file = io.StringIO()
    worker.watermarks, worker.safety_intents = {}, {}
    worker.bootstrap_intent_refs = None
    refs = {name: {'intent_sequence': 1, 'payload_sha256': 'a'*64}
            for name in ('tb1', 'tb2', 'tb3')}

    def status(sequence):
        value = {'schema': f'mr3-motion-safety-status-v{worker.control_version}',
            'epoch': worker.epoch, 'clock_ns': worker.physical_ns, 'ready': True,
            'completion_scope': 'publication_and_local_topic_receipt',
            'outputs': {name: {'linear_x': 0., 'angular_z': 0.} for name in refs},
            'decision_sequences': dict.fromkeys(refs, sequence)}
        if reach:
            value.update(safety_contract=worker.safety_contract, intent_refs=copy.deepcopy(refs),
                         safety_table_sha256=None)
        return value

    def publish(component, request):
        events.append('takeover_' + component)
        ack = {'schema': f'mr3-{component}-phase-ack-v{worker.control_version}',
            'epoch': worker.epoch, 'clock_ns': worker.physical_ns,
            'target_time_ns': worker.physical_ns, 'request_id': request['request_id'],
            'operation': 'takeover', 'ok': True}
        if component == 'motion':
            ack.update(schema=f'mr3-motion-control-ack-v{worker.control_version}', status=status(1))
        if reach:
            ack.update(safety_contract=worker.safety_contract, intent_refs=copy.deepcopy(refs),
                       safety_table_sha256=None)
        worker.receive_control_phase(component, ack)

    worker._publish = publish

    def wait(predicate, timeout, label):
        worker._healthy()
        if 'paused three-robot' in label:
            assert 'pause' in events and not predicate()
            worker.receive_startup_bool('motion_ready', '/motion_safety/ready', SimpleNamespace(data=True))
        if 'native drive exact-target' in label and not predicate():
            motion = worker._execution_motion()
            for index, name in enumerate(refs):
                if missing_storage and index == 2:
                    assert not predicate()
                    raise TimeoutError('actual third storage receipt missing')
                worker.receive_drive_status(name, {'schema': WORKER.DRIVE_PROTOCOL,
                    'epoch': worker.epoch, 'robot': name, 'clock_ns': worker.physical_ns,
                    'source_clock_ns': worker.physical_ns,
                    'decision_sequence': motion['decision_sequences'][name],
                    'cmd_seq': motion['decision_sequences'][name], **motion['outputs'][name]})
                assert predicate() is (index == 2)
            events.append('storage_' + str(worker.physical_ns))
        assert predicate(), label

    worker._wait = wait
    worker.verify_motion_output_topology = lambda: events.append('motion_topology')
    worker.verify_drive_topology = lambda: events.append('drive_topology')
    worker._start_step_helper = lambda: events.append('helper')
    worker._align_initial_clock = lambda: events.append('aligned')

    def physics(steps, wait_clock=True):
        if steps == 0:
            events.append('pause')
        else:
            assert steps == 20 and worker.controlled and len(worker.control_phase.completed) == 3
            assert worker.consumed_drive_phase is not None
            events.append('bootstrap')
            worker.physical_ns += 20_000_000
            worker.clock_ns = worker.physical_ns
            worker.receive_motion_status(status(2))
        return {'end_time_ns': worker.physical_ns}

    worker._physics = physics

    def snapshot():
        assert len(worker.control_phase.completed) == 3
        assert worker.consumed_drive_phase['expected_motion']['clock_ns'] == worker.physical_ns
        assert all(row['decision_sequence'] == 2 for row in worker.consumed_drive_phase['receipts'].values())
        events.append('release_snapshot')
        worker.snapshot = {'epoch': worker.epoch, 'sequence': 1, 'digest': 'artificial'}
        worker.watermarks = {'state_sequence': 100}
        worker.reward_ready = {'start_sim_time': worker.physical_ns / 1e9}
        for name in refs:
            worker.safety_intents[name] = {'schema': 'mr3-safety-intent-v1', 'epoch': worker.epoch,
                'robot': name, 'intent_sequence': 2, 'source_clock_ns': worker.physical_ns,
                'role': 'HOLD', 'anchor': None, 'admitted_signs': [],
                'lineage': {'release_clock_ns': worker.physical_ns}, 'target': None}

    worker._snapshot = snapshot
    worker._reward = lambda *args, **kwargs: {'reward': 0., 'terminated': False, 'truncated': False}
    worker._evaluator_phase = lambda: {'status': 'LIVE'}
    if not reach:
        worker.motion_ready = True
    return worker, events


def test_all_four_then_real_control_and_storage_matchers_are_required_before_release(monkeypatch):
    worker, events = complete_fixture(monkeypatch)
    result = worker.reset()
    assert events[:5] == ['helper', 'pause', 'aligned', 'motion_topology', 'drive_topology']
    assert events.index('takeover_peer') < events.index('bootstrap') < events.index('release_snapshot')
    assert len(worker.control_phase.completed) == 3
    assert result['info']['startup_readiness_protocol'] == WORKER.STARTUP_READINESS_PROTOCOL
    assert worker.startup_active is False
    assert journal(worker)[-1]['stage'] == 'reset_complete'


def test_missing_real_third_storage_receipt_never_releases(monkeypatch):
    worker, events = complete_fixture(monkeypatch, missing_storage=True)
    with pytest.raises(TimeoutError, match='actual third storage'):
        worker.reset()
    assert 'release_snapshot' not in events and 'bootstrap' not in events


def test_legacy_keeps_all_four_then_topology_before_pause_and_omits_new_info(monkeypatch):
    worker, events = complete_fixture(monkeypatch, reach=False)
    result = worker.reset()
    assert events[:5] == ['motion_topology', 'drive_topology', 'helper', 'pause', 'aligned']
    assert not any(key.startswith('startup_') for key in result['info'])
    assert worker.startup_readiness_file is None


def test_shared_absolute_deadline_decreases_and_reserves_cleanup_and_response(monkeypatch):
    worker, clock = fixture(monkeypatch)
    assert worker._startup_timeout(400.) == 355.
    clock.ns += 300_000_000_000
    assert worker._startup_timeout(400.) == 55.
    clock.ns += 55_000_000_000
    with pytest.raises(TimeoutError, match='cleanup/response reserve'):
        worker._startup_timeout(400.)
    failure = journal(worker)[-1]
    assert failure['kind'] == 'failure' and failure['ready']['motion_ready'] is False
    assert clock.ns + 65_000_000_000 == worker.startup_deadline_ns


def test_constructor_subtracts_time_already_spent_before_worker_initialization(tmp_path, monkeypatch):
    monkeypatch.setattr(WORKER.time, 'monotonic_ns', lambda: 150_000_000_000)
    owner = WORKER.Worker.__new__(WORKER.Worker)
    with pytest.raises(ValueError, match='invalid scene'):
        WORKER.Worker.__init__(owner, tmp_path, {
            'epoch': 'current', 'scene': 'artificial-stop-before-IO', 'seed': 101,
            'safety_contract': 'mr3-reach-v1',
            'startup_readiness_protocol': WORKER.STARTUP_READINESS_PROTOCOL,
            'startup_deadline_monotonic_ns': 520_000_000_000})
    assert owner.startup_wait_deadline_ns == 455_000_000_000
    assert owner.startup_wait_deadline_ns - 150_000_000_000 == 305_000_000_000
    assert list(tmp_path.iterdir()) == []


def test_nonzero_received_motion_before_initial_snapshot_cannot_be_hidden_by_takeover(monkeypatch):
    worker, _ = fixture(monkeypatch)
    worker.controlled = True
    worker.motion_status = None
    refs = {name: {'intent_sequence': 1, 'payload_sha256': 'a'*64}
            for name in ('tb1', 'tb2', 'tb3')}
    value = {'schema': 'mr3-motion-safety-status-v2', 'epoch': worker.epoch,
        'clock_ns': worker.physical_ns, 'ready': True,
        'completion_scope': 'publication_and_local_topic_receipt',
        'outputs': {name: {'linear_x': .1 if name == 'tb1' else 0., 'angular_z': 0.}
                    for name in refs}, 'decision_sequences': dict.fromkeys(refs, 1),
        'safety_contract': worker.safety_contract, 'intent_refs': refs,
        'safety_table_sha256': 'b'*64}
    with pytest.raises(ValueError, match='pre-release startup motion'):
        worker.receive_motion_status(value)
    assert worker.motion_status is None


def test_callback_journal_distinguishes_defaults_first_receipts_changes_and_old_epoch(monkeypatch):
    worker, _ = fixture(monkeypatch)
    worker.monitor_ready = False
    for value in (False, False, True):
        worker.receive_startup_bool('monitor_ready', '/task_monitor_ready', SimpleNamespace(data=value))
    rows = journal(worker)
    assert len(rows) == 2 and rows[0]['first_callback'] is True
    assert rows[0]['receipt']['data'] is False and rows[1]['receipt']['data'] is True
    worker.initial_inputs_ready = None
    worker.receive_initial_inputs({**acknowledgement(), 'epoch': 'previous'})
    assert len(journal(worker)) == 2 and worker.initial_inputs_ready is None
    worker.receive_initial_inputs(acknowledgement())
    assert journal(worker)[-1]['field'] == 'initial_inputs_ready'


def test_current_epoch_received_failure_is_immediate_and_journaled_only_during_startup(monkeypatch):
    worker, _ = fixture(monkeypatch)
    worker.receive_failure(SimpleNamespace(data=json.dumps({'epoch': 'previous', 'reason': 'old'})))
    worker.receive_failure(SimpleNamespace(data='unbound legacy text'))
    worker._healthy()
    worker.receive_failure(SimpleNamespace(data=json.dumps({'epoch': worker.epoch, 'reason': 'actual fault'})))
    with pytest.raises(RuntimeError, match='actual fault'):
        worker._healthy()
    assert journal(worker)[-1]['kind'] == 'failure'
    worker.startup_active = False
    worker._healthy()  # Normal post-reset terminal/failure handling is unchanged.


@pytest.mark.parametrize('field,value', [('startup_readiness_protocol', None),
    ('startup_readiness_protocol', True), ('startup_readiness_protocol', 'unknown'),
    ('startup_deadline_monotonic_ns', True), ('startup_deadline_monotonic_ns', None),
    ('startup_deadline_monotonic_ns', 99_000_000_000),
    ('startup_deadline_monotonic_ns', 521_000_000_000)])
def test_invalid_reach_startup_request_rejects_before_any_IO(tmp_path, monkeypatch, field, value):
    monkeypatch.setattr(WORKER.time, 'monotonic_ns', lambda: 100_000_000_000)
    request = {'epoch': 'current', 'scene': 'rooms', 'seed': 101, 'quantum_steps': 20,
        'safety_contract': 'mr3-reach-v1', 'startup_readiness_protocol': WORKER.STARTUP_READINESS_PROTOCOL,
        'startup_deadline_monotonic_ns': 520_000_000_000, field: value}
    with pytest.raises(ValueError, match='startup protocol'):
        WORKER.Worker(tmp_path, request)
    assert list(tmp_path.iterdir()) == []


def test_no_work_after_reserve_and_legacy_startup_fields_reject_before_IO(tmp_path, monkeypatch):
    monkeypatch.setattr(WORKER.time, 'monotonic_ns', lambda: 100_000_000_000)
    request = {'epoch': 'current', 'scene': 'rooms', 'seed': 101, 'quantum_steps': 20,
        'safety_contract': 'mr3-reach-v1', 'startup_readiness_protocol': WORKER.STARTUP_READINESS_PROTOCOL,
        'startup_deadline_monotonic_ns': 160_000_000_000}
    with pytest.raises(TimeoutError, match='cleanup/response reserve'):
        WORKER.Worker(tmp_path, request)
    request['safety_contract'] = 'legacy'
    with pytest.raises(ValueError, match='legacy reset must omit'):
        WORKER.Worker(tmp_path, request)
    assert list(tmp_path.iterdir()) == []
