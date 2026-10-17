"""Paused commits cannot advance on requested or cached-but-unreceived inputs."""

import copy
import hashlib
from types import SimpleNamespace

import pytest
from std_msgs.msg import String

from multi_robot_exploration.mr3_control_phase import canonical
from multi_robot_exploration.mr3_motion_control import MotionControlPhase


class Publisher:
    def __init__(self):
        self.messages = []

    def publish(self, value):
        self.messages.append(value.data)


class Guard:
    def __init__(self):
        self.epoch, self.clock = 'epoch', 20_000_000
        self.started, self.halted, self.stop_time = False, None, None
        self.timer = SimpleNamespace(cancel=lambda: None)
        self.completed_motion, self.issued_motion = {}, set()
        self.received = {'sequence': 1, 'robots': []}
        self.events, self.calls, self.subscriptions = [], [], []
        self.decision_sequences = dict.fromkeys(('tb1', 'tb2', 'tb3'), 0)
        self.inputs_ready, self.complete = True, True
        self.normal_control_model_fault = None

    def create_publisher(self, *args):
        return Publisher()

    def create_subscription(self, *args):
        self.subscriptions.append(args)
        return args

    def create_timer(self, *args, **kwargs):
        return None

    def get_clock(self):
        return SimpleNamespace(now=lambda: SimpleNamespace(nanoseconds=self.clock))

    def record(self, *args):
        self.events.append(args)

    def normal_velocity_fault(self, clock):
        # This fixture isolates phase/dependency ordering; body models have
        # dedicated real-source node tests and are valid for this stub.
        assert clock == self.clock
        return None

    def control_inputs_ready(self, clock):
        assert clock == self.clock
        return self.inputs_ready

    def ensure_motion_output(self, clock, stop=False):
        key = clock, 'stop' if stop else 'normal'
        if key in self.issued_motion:
            return
        self.calls.append(key)
        self.decision_sequences = {name: value + 1
                                   for name, value in self.decision_sequences.items()}
        self.issued_motion.add(key)
        if self.complete:
            self.complete_output(key)

    def complete_output(self, key):
        clock, kind = key
        value = {'clock_ns': clock, 'ready': kind != 'stop',
                 'decision_sequences': dict(self.decision_sequences),
                 'outputs': {name: {'linear_x': 0., 'angular_z': 0.}
                             for name in ('tb1', 'tb2', 'tb3')}}
        if kind == 'stop':
            value['phase_kind'] = 'stop'
        self.completed_motion[key] = value
        self.phase.poll()  # Real self-receipt also polls reentrantly.


def setup():
    node = Guard()
    phase = MotionControlPhase(node)
    node.phase = phase
    return node, phase


def request(node, operation, identity=None, **refs):
    return {'schema': 'mr3-motion-control-request-v1', 'epoch': node.epoch,
            'request_id': identity or operation + str(node.clock),
            'target_time_ns': node.clock, 'operation': operation, **refs}


def send(phase, value):
    phase.receive_request(String(data=canonical(value)))


def dependencies(node, phase, deliver=True):
    common = {'epoch': node.epoch, 'request_id': 'boundary' + str(node.clock),
              'target_time_ns': node.clock, 'clock_ns': node.clock,
              'operation': 'commit', 'ok': True, 'state_sequence': 1,
              'bundle_sha256': hashlib.sha256(canonical(node.received).encode()).hexdigest()}
    state = dict(common, schema='mr3-state-phase-ack-v1',
                 scope='actual_state_and_side_publish_calls_returned')
    peer = dict(common, schema='mr3-peer-phase-ack-v1', commit_sequence=1,
                state_commit=copy.deepcopy(state), scope='actual_obstacle_publish_calls_returned')
    if deliver:
        for component, value in (('state', state), ('peer', peer)):
            phase.receive_dependency(String(data=canonical(value)), component)
    return {'state_commit': state, 'peer_commit': peer}


def takeover(node, phase):
    send(phase, request(node, 'takeover'))
    assert phase.responses['takeover20000000'][1]['ok'] is True
    node.clock += 20_000_000


def test_commit_waits_for_actual_dependency_callbacks_and_local_receipt():
    node, phase = setup()
    takeover(node, phase)
    refs = dependencies(node, phase, deliver=False)
    send(phase, request(node, 'commit', 'boundary' + str(node.clock), **refs))
    assert phase.pending and len(node.calls) == 1
    for component in ('state', 'peer'):
        phase.receive_dependency(String(data=canonical(refs[component + '_commit'])), component)
    assert phase.pending is None and len(node.calls) == 2
    ack = phase.responses['boundary40000000'][1]
    assert ack['ok'] and ack['status']['clock_ns'] == node.clock
    send(phase, request(node, 'commit', 'boundary40000000', **refs))
    assert len(node.calls) == 2  # Exact duplicate returns the immutable original receipt.


def test_guard_waits_for_three_actual_self_receipts():
    node, phase = setup()
    takeover(node, phase)
    node.complete = False
    refs = dependencies(node, phase)
    send(phase, request(node, 'commit', 'boundary40000000', **refs))
    phase.poll()
    assert phase.pending and len(node.calls) == 2
    node.complete_output((node.clock, 'normal'))
    assert phase.pending is None


def test_takeover_cannot_reuse_older_completed_status_while_newer_target_is_pending():
    node, phase = setup()
    node.ensure_motion_output(node.clock)
    node.decision_sequences = dict.fromkeys(('tb1', 'tb2', 'tb3'), 2)
    send(phase, request(node, 'takeover'))
    assert phase.pending and not phase.responses
    node.complete_output((node.clock, 'normal'))
    assert phase.responses['takeover20000000'][1]['status']['decision_sequences'] == {
        'tb1': 2, 'tb2': 2, 'tb3': 2}


@pytest.mark.parametrize('change', [
    lambda state, peer: state.update(schema='other'),
    lambda state, peer: state.update(state_sequence=True),
    lambda state, peer: peer.update(commit_sequence=True),
    lambda state, peer: peer.update(clock_ns=True),
    lambda state, peer: peer.update(bundle_sha256='0' * 64),
    lambda state, peer: peer.update(scope='requested_only'),
])
def test_dependency_mutations_latch_zero_and_never_normal_commit(change):
    node, phase = setup()
    takeover(node, phase)
    refs = dependencies(node, phase, deliver=False)
    change(refs['state_commit'], refs['peer_commit'])
    for component in ('state', 'peer'):
        phase.receive_dependency(String(data=canonical(refs[component + '_commit'])), component)
    send(phase, request(node, 'commit', 'boundary40000000', **refs))
    assert node.halted and phase.stopping
    assert (node.clock, 'normal') not in node.calls
    assert (node.clock, 'stop') in node.calls
    assert phase.responses['boundary40000000'][1]['ok'] is False


def test_dependency_substitution_and_changed_same_id_fail_closed():
    node, phase = setup()
    takeover(node, phase)
    refs = dependencies(node, phase)
    refs['state_commit']['bundle_sha256'] = '0' * 64
    send(phase, request(node, 'commit', 'boundary40000000', **refs))
    assert node.halted and (node.clock, 'normal') not in node.calls


def test_old_takeover_clock_cannot_be_relabelled_as_new_normal_commit():
    node, phase = setup()
    send(phase, request(node, 'takeover'))
    refs = dependencies(node, phase)
    send(phase, request(node, 'commit', 'boundary20000000', **refs))
    assert phase.responses['boundary20000000'][1]['ok'] is False
    assert node.calls == [(node.clock, 'normal'), (node.clock, 'stop')]


def test_terminal_stop_can_replace_pending_commit_without_ready_inputs():
    node, phase = setup()
    takeover(node, phase)
    node.inputs_ready = False
    refs = dependencies(node, phase)
    send(phase, request(node, 'commit', 'boundary40000000', **refs))
    assert phase.pending
    node.stop_time = node.clock / 1e9
    phase.ensure_stop()
    send(phase, request(node, 'stop'))
    ack = phase.responses['stop40000000'][1]
    assert ack['ok'] and ack['status']['ready'] is False
    assert ack['status']['phase_kind'] == 'stop'
    assert node.halted is None  # Orderly shutdown does not invent a safety failure.
    assert (node.clock, 'normal') not in node.calls
    node.clock += 20_000_000
    send(phase, request(node, 'commit', 'boundary60000000'))
    assert phase.responses['boundary60000000'][1]['status']['phase_kind'] == 'stop'


def test_same_clock_stop_never_overwrites_normal_status():
    node, phase = setup()
    takeover(node, phase)
    refs = dependencies(node, phase)
    send(phase, request(node, 'commit', 'boundary40000000', **refs))
    original = canonical(phase.responses['boundary40000000'])
    phase.ensure_stop()
    send(phase, request(node, 'stop'))
    assert canonical(phase.responses['boundary40000000']) == original
    assert (node.clock, 'stop') in node.calls


def test_dependency_timeout_and_passed_clock_publish_zero_without_advance():
    node, phase = setup()
    takeover(node, phase)
    refs = dependencies(node, phase, deliver=False)
    send(phase, request(node, 'commit', 'boundary40000000', **refs))
    phase.pending['started'] -= 11
    phase.poll()
    assert phase.responses['boundary40000000'][1]['ok'] is False
    assert node.halted and (node.clock, 'stop') in node.calls


def test_received_bundle_hash_must_equal_actual_main_topic():
    node, phase = setup()
    takeover(node, phase)
    refs = dependencies(node, phase)
    node.received['sequence'] = 2
    send(phase, request(node, 'commit', 'boundary40000000', **refs))
    assert phase.pending and (node.clock, 'normal') not in node.calls


def test_other_epoch_dependency_cannot_satisfy_current_commit():
    node, phase = setup()
    takeover(node, phase)
    refs = dependencies(node, phase, deliver=False)
    foreign = dict(refs['state_commit'], epoch='other')
    phase.receive_dependency(String(data=canonical(foreign)), 'state')
    send(phase, request(node, 'commit', 'boundary40000000', **refs))
    assert phase.pending and not phase.dependencies['state']
