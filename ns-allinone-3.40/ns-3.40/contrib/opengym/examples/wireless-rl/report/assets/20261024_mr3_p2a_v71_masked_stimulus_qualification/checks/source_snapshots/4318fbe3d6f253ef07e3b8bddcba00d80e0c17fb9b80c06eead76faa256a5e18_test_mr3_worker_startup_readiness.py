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
    worker.motion_authority_profile = WORKER.MOTION_AUTHORITY_PROFILE if reach else None
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


def test_real_pause_and_topology_can_complete_before_motion_ready(monkeypatch):
    worker, _ = fixture(monkeypatch)
    events = []
    worker._start_step_helper = lambda: events.append('helper')
    worker._physics = lambda steps, wait_clock=False: (
        events.append(('physics', steps, wait_clock)) or {'end_time_ns': worker.physical_ns})
    worker._align_initial_clock = lambda: events.append('align')
    worker.verify_motion_output_topology = lambda: events.append('motion_topology')
    worker.verify_drive_topology = lambda: events.append('drive_topology')

    def wait(predicate, timeout, label):
        assert predicate()

    worker._wait = wait
    worker._pause_and_drain_startup()
    assert events == ['helper', ('physics', 0, False), 'align', 'motion_topology', 'drive_topology']
    assert worker.motion_ready is False
    assert not hasattr(worker, 'start_ns')


def complete_fixture(monkeypatch, *, reach=True, missing_storage=False, motion_callback=True,
                     bootstrap_ready=True):
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
            'epoch': worker.epoch, 'clock_ns': worker.physical_ns,
            'ready': (not reach or sequence > 1 and bootstrap_ready),
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
        if 'controlled three-robot' in label and not predicate():
            assert 'bootstrap' in events
            if motion_callback:
                worker.receive_startup_bool('motion_ready', '/motion_safety/ready', SimpleNamespace(data=True))
            else:
                raise TimeoutError(label)
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
        assert set(worker.takeover_acks) == {'motion', 'state', 'peer'}
        assert all((name, ack['request_id']) in worker.control_phase.completed
                   for name, ack in worker.takeover_acks.items())
        assert worker.consumed_drive_phase['expected_motion']['clock_ns'] == worker.physical_ns
        assert all(row['decision_sequence'] == 2 for row in worker.consumed_drive_phase['receipts'].values())
        events.append('release_snapshot')
        worker.snapshot = {'epoch': worker.epoch, 'sequence': 1, 'digest': 'artificial'}
        worker.watermarks = {'state_sequence': 100}
        worker.reward_ready = {'start_sim_time': worker.physical_ns / 1e9}
        for name in refs:
            vector = {'x': 0., 'y': 0., 'z': 0.}
            odom = {'header': {'stamp': {'sec': worker.physical_ns // 10**9,
                                       'nanosec': worker.physical_ns % 10**9}, 'frame_id': name+'/odom'},
                    'child_frame_id': name+'/base_footprint',
                    'pose': {'pose': {'position': dict(vector), 'orientation': dict(vector, w=1.)},
                             'covariance': [0.]*36},
                    'twist': {'twist': {'linear': dict(vector), 'angular': dict(vector)},
                              'covariance': [0.]*36}}
            worker.safety_intents[name] = {'schema': 'mr3-safety-intent-v1', 'epoch': worker.epoch,
                'robot': name, 'intent_sequence': 2, 'source_clock_ns': worker.physical_ns,
                'role': 'HOLD', 'anchor': {'source_clock_ns': worker.physical_ns, 'odometry': odom},
                'admitted_signs': [], 'lineage': {'release_clock_ns': worker.physical_ns},
                'target': {'schema': 'mr3-drive-target-v1', 'epoch': worker.epoch, 'robot': name,
                           'clock_ns': worker.physical_ns, 'decision_sequence': 2,
                           'linear_x': 0., 'angular_z': 0.}}

    worker._snapshot = snapshot
    worker._reward = lambda *args, **kwargs: {'reward': 0., 'terminated': False, 'truncated': False}
    worker._evaluator_phase = lambda: {'status': 'LIVE'}
    if not reach:
        worker.motion_ready = True
    return worker, events


def test_zero_takeover_and_bootstrap_then_all_four_and_storage_are_required_before_release(monkeypatch):
    worker, events = complete_fixture(monkeypatch)
    result = worker.reset()
    assert events[:5] == ['helper', 'pause', 'aligned', 'motion_topology', 'drive_topology']
    assert events.index('takeover_peer') < events.index('bootstrap') < events.index('release_snapshot')
    assert len(worker.control_phase.completed) == 3
    assert result['info']['startup_readiness_protocol'] == WORKER.STARTUP_READINESS_PROTOCOL
    assert worker.startup_active is False
    assert journal(worker)[-1]['stage'] == 'reset_complete'


def test_bootstrap_ready_status_without_actual_motion_ready_callback_never_releases(monkeypatch):
    worker, events = complete_fixture(monkeypatch, motion_callback=False)
    with pytest.raises(TimeoutError, match='controlled three-robot'):
        worker.reset()
    assert worker._execution_motion()['ready'] is True
    assert 'bootstrap' in events and 'release_snapshot' not in events


def test_motion_ready_callback_cannot_replace_bootstrap_exact_status_ready(monkeypatch):
    worker, events = complete_fixture(monkeypatch, bootstrap_ready=False)
    worker.motion_ready = True
    with pytest.raises(RuntimeError, match='initial controlled motion inputs'):
        worker.reset()
    assert 'bootstrap' in events and 'release_snapshot' not in events


def test_paused_false_uses_real_takeover_and_new_clock_commit_before_ready(monkeypatch):
    """Real worker/guard phase and storage matchers, with synthetic ROS/physics IO.

    The received-prefix flag is the artificial source boundary. No fixture
    assigns the worker's ready=True; only the guard's completed output emits it.
    """
    from std_msgs.msg import String
    from test_mr3_motion_control import ReachGuard, reach_bundle, reach_dependencies
    from multi_robot_exploration.mr3_control_phase import canonical
    from multi_robot_exploration.mr3_motion_control import MotionControlPhase
    from multi_robot_exploration.mr3_reach_runtime import ReachTracker
    from multi_robot_exploration.mr3_safety_intent import payload_sha256

    worker, events = complete_fixture(monkeypatch, motion_callback=False)
    worker.physics_file, worker.physics_number = io.StringIO(), 0
    original_physics = worker._physics

    class StartupGuard(ReachGuard):
        def complete_output(self, key):
            stamp, kind = key
            outputs = {name: {'linear_x': 0., 'angular_z': 0.} for name in self.reach}
            intents, targets = {}, {}
            for name in self.reach:
                targets[name] = {'schema': 'mr3-drive-target-v1', 'epoch': self.epoch,
                    'robot': name, 'clock_ns': stamp,
                    'decision_sequence': self.decision_sequences[name], **outputs[name]}
                intents[name] = self.reach[name].publish_target(targets[name])
            value = {'schema': 'mr3-motion-safety-status-v2', 'epoch': self.epoch,
                'clock_ns': stamp, 'ready': self.inputs_ready and kind != 'stop',
                'completion_scope': 'publication_and_local_topic_receipt',
                'decision_sequences': dict(self.decision_sequences), 'outputs': outputs,
                'safety_contract': self.safety_contract,
                'intent_refs': {name: {'intent_sequence': row['intent_sequence'],
                                      'payload_sha256': payload_sha256(row)}
                                for name, row in intents.items()},
                'safety_table_sha256': (self.control_safety_context['safety_table_sha256']
                                       if self.control_safety_context else None)}
            self.completed_motion[key] = value
            worker.receive_motion_status(value)
            worker.receive_startup_bool('motion_ready', '/motion_safety/ready',
                                        SimpleNamespace(data=value['ready']))
            assert self.phase.storage_ready(value) is False
            for index, name in enumerate(self.reach):
                receipt = {'schema': WORKER.DRIVE_PROTOCOL, 'epoch': self.epoch,
                    'robot': name, 'clock_ns': stamp, 'source_clock_ns': stamp,
                    'decision_sequence': self.decision_sequences[name],
                    'cmd_seq': self.decision_sequences[name], **outputs[name]}
                self.reach[name].receive_storage(receipt)
                worker.receive_drive_status(name, receipt)
                assert self.phase.storage_ready(value) is (index == 2)
                self.phase.poll()

    guard = StartupGuard()
    guard.epoch, guard.clock, guard.inputs_ready = worker.epoch, worker.physical_ns, False
    guard.received = reach_bundle(guard.epoch, guard.clock)
    guard.reach = {name: ReachTracker(guard.epoch, name) for name in ('tb1', 'tb2', 'tb3')}
    phase = MotionControlPhase(guard)
    guard.phase = phase
    phase.publisher.publish = lambda message: worker.receive_control_phase('motion', json.loads(message.data))
    guard.ensure_motion_output(guard.clock)  # Real emitted paused status is False.
    original_status = copy.deepcopy(worker.motion_status)

    def publish(component, request):
        events.append(request['operation'] + '_' + component)
        if component == 'motion':
            phase.receive_request(String(data=canonical(request)))
            if request['operation'] == 'commit':
                assert phase.pending and worker.control_phase.response is None
                assert guard.clock == original_status['clock_ns'] + 20_000_000
                events.append('received_prefix_at_new_clock')
                guard.inputs_ready = True
                phase.poll()  # The real steady pending poll now completes.
            return
        if request['operation'] == 'takeover':
            value = {'schema': f'mr3-{component}-phase-ack-v2', 'epoch': worker.epoch,
                'request_id': request['request_id'], 'operation': 'takeover', 'ok': True,
                'target_time_ns': guard.clock, 'clock_ns': guard.clock,
                'safety_contract': worker.safety_contract,
                'intent_refs': copy.deepcopy(worker.motion_status['intent_refs']),
                'safety_table_sha256': None}
        else:
            value = reach_dependencies(guard, phase, deliver=False)[component+'_commit']
            phase.receive_dependency(String(data=canonical(value)), component)
        worker.receive_control_phase(component, value)

    worker._publish = publish
    sent = []

    def physical_receipt(timeout):
        assert timeout > 0 and sent[-1]['steps'] == 20
        events.append('bootstrap')
        old = guard.clock
        guard.clock += 20_000_000
        worker.clock_ns = guard.clock
        guard.received = reach_bundle(guard.epoch, guard.clock)
        for row in guard.received['robots']:
            row['safety']['intent'] = copy.deepcopy(guard.reach[row['robot']].current_intent)
        table = {row['robot']: row['safety'] for row in guard.received['robots']}
        guard.received['safety_table_sha256'] = payload_sha256(table)
        guard.received['intent_refs'] = copy.deepcopy(original_status['intent_refs'])
        return {'ok': True, 'request_id': sent[-1]['request_id'], 'epoch': worker.epoch,
                'paused': True, 'start_iterations': 0, 'end_iterations': 20,
                'start_time_ns': old, 'end_time_ns': guard.clock}

    worker.helper_peer = SimpleNamespace(send=sent.append, receive=physical_receipt)
    worker._physics = lambda steps, wait_clock=True: (
        original_physics(steps, wait_clock) if steps == 0 else
        WORKER.Worker._physics(worker, steps, wait_clock))
    result = worker.reset()
    assert original_status['ready'] is False
    assert phase.responses['takeover10000000000'][1]['status'] == original_status
    assert result['info']['initial_motion_status']['ready'] is True
    assert worker.motion_ready is True and guard.halted is None
    assert events.index('bootstrap') < events.index('received_prefix_at_new_clock') < events.index('release_snapshot')
    assert len(worker.control_phase.completed) == 6  # Three takeovers and three new-clock commits.
    assert len(guard.calls) == 2  # The paused output was never overwritten/re-emitted.


def test_missing_real_third_storage_receipt_never_releases(monkeypatch):
    worker, events = complete_fixture(monkeypatch, missing_storage=True)
    with pytest.raises(TimeoutError, match='actual third storage'):
        worker.reset()
    assert 'release_snapshot' not in events and 'bootstrap' not in events


def test_legacy_keeps_all_four_then_topology_before_pause_and_omits_new_info(monkeypatch):
    worker, events = complete_fixture(monkeypatch, reach=False)
    result = worker.reset()
    assert events[:5] == ['motion_topology', 'drive_topology', 'helper', 'pause', 'aligned']
    assert {key for key in result['info'] if key.startswith('startup_')} == {'startup_wall_sec'}
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


def test_cleanup_at_second_59_limits_physics_receive_to_one_second(monkeypatch):
    worker, clock = fixture(monkeypatch)
    worker.startup_active = False
    worker.cleanup_mode, worker.cleanup_deadline = True, 160.
    clock.ns = 159_000_000_000
    worker.physics_number = 0
    worker.physics_file = io.StringIO()
    worker._trace_drive_phase = lambda *args, **kwargs: None
    sends, waits = [], []

    def receive(timeout):
        waits.append(timeout)
        return {'ok': True, 'request_id': 'q1', 'epoch': worker.epoch, 'paused': True,
                'start_iterations': 1, 'end_iterations': 1,
                'start_time_ns': worker.physical_ns, 'end_time_ns': worker.physical_ns}

    worker.helper_peer = SimpleNamespace(send=sends.append, receive=receive)
    worker._physics(0, wait_clock=False)
    assert waits == [1.] and len(sends) == 1
    clock.ns = 160_000_000_000
    with pytest.raises(TimeoutError, match='cleanup total wall guard'):
        worker._physics(0, wait_clock=False)
    assert len(sends) == 1 and waits == [1.]


@pytest.mark.parametrize('complete,now,expected', [
    (False, 500., 515.), (True, 1000., 1060.),
])
def test_cleanup_deadline_retains_parent_response_reserve_only_during_startup(
        monkeypatch, complete, now, expected):
    worker, clock = fixture(monkeypatch)
    worker.startup_active = False
    worker.startup_stage = 'reset_complete' if complete else 'failed'
    clock.ns = round(now * 1e9)
    worker.control_phase = SimpleNamespace(abandon_for_stop=lambda: None)
    worker._trace_control_phase = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError('fixture stop'))
    with pytest.raises(RuntimeError, match='fixture stop'):
        worker.abort_cleanup(RuntimeError('original'))
    assert worker.cleanup_deadline == expected
    assert worker._startup_timeout(60.) == expected - now


def test_expired_startup_cleanup_never_begins_another_blocking_operation(monkeypatch):
    worker, clock = fixture(monkeypatch)
    worker.startup_active, worker.startup_stage = False, 'failed'
    clock.ns = 515_000_000_000
    worker.control_phase = SimpleNamespace(abandon_for_stop=lambda: pytest.fail('no work budget'))
    with pytest.raises(TimeoutError, match='cleanup total wall guard'):
        worker.abort_cleanup(RuntimeError('original'))
    assert worker.cleanup_deadline == 515.


def test_cleanup_clock_alignment_waits_are_clamped_to_remaining_budget(monkeypatch):
    worker, clock = fixture(monkeypatch)
    worker.startup_active = False
    worker.cleanup_mode = True
    worker.cleanup_deadline = clock.monotonic() + .003
    worker.clock_ns = worker.physical_ns - 1
    worker.helper_peer = SimpleNamespace(send=lambda *args: pytest.fail('expired cleanup must not tick again'))
    with pytest.raises(TimeoutError, match='cleanup total wall guard'):
        worker._align_initial_clock()
    assert clock.monotonic() == worker.cleanup_deadline


def test_cleanup_close_waits_share_the_same_remaining_second(monkeypatch):
    worker, clock = fixture(monkeypatch)
    worker.finished, worker.startup_active, worker.cleanup_mode = True, False, True
    worker.cleanup_deadline = clock.monotonic() + 1.
    waits = []

    def shutdown(timeout_sec):
        waits.append(('executor', timeout_sec))
        clock.ns += 600_000_000

    def join(timeout):
        waits.append(('spin', timeout))
        raise RuntimeError('fixture stop before node destruction')

    worker.executor = SimpleNamespace(shutdown=shutdown)
    worker.spin_thread = SimpleNamespace(join=join)
    with pytest.raises(RuntimeError, match='fixture stop before node destruction'):
        worker.close()
    assert waits[0] == ('executor', 1.)
    assert waits[1][0] == 'spin' and waits[1][1] == pytest.approx(.4)


def test_constructor_subtracts_time_already_spent_before_worker_initialization(tmp_path, monkeypatch):
    monkeypatch.setattr(WORKER.time, 'monotonic_ns', lambda: 150_000_000_000)
    owner = WORKER.Worker.__new__(WORKER.Worker)
    with pytest.raises(ValueError, match='invalid scene'):
        WORKER.Worker.__init__(owner, tmp_path, {
            'epoch': 'current', 'scene': 'artificial-stop-before-IO', 'seed': 101,
            'safety_contract': 'mr3-reach-v1',
            'motion_authority_profile': WORKER.MOTION_AUTHORITY_PROFILE,
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
        'safety_contract': 'mr3-reach-v1', 'motion_authority_profile': WORKER.MOTION_AUTHORITY_PROFILE,
        'startup_readiness_protocol': WORKER.STARTUP_READINESS_PROTOCOL,
        'startup_deadline_monotonic_ns': 520_000_000_000, field: value}
    with pytest.raises(ValueError, match='startup protocol'):
        WORKER.Worker(tmp_path, request)
    assert list(tmp_path.iterdir()) == []


def test_no_work_after_reserve_and_legacy_startup_fields_reject_before_IO(tmp_path, monkeypatch):
    monkeypatch.setattr(WORKER.time, 'monotonic_ns', lambda: 100_000_000_000)
    request = {'epoch': 'current', 'scene': 'rooms', 'seed': 101, 'quantum_steps': 20,
        'safety_contract': 'mr3-reach-v1', 'motion_authority_profile': WORKER.MOTION_AUTHORITY_PROFILE,
        'startup_readiness_protocol': WORKER.STARTUP_READINESS_PROTOCOL,
        'startup_deadline_monotonic_ns': 160_000_000_000}
    with pytest.raises(TimeoutError, match='cleanup/response reserve'):
        WORKER.Worker(tmp_path, request)
    request['safety_contract'] = 'legacy'
    request.pop('motion_authority_profile')
    with pytest.raises(ValueError, match='legacy reset must omit'):
        WORKER.Worker(tmp_path, request)
    assert list(tmp_path.iterdir()) == []
