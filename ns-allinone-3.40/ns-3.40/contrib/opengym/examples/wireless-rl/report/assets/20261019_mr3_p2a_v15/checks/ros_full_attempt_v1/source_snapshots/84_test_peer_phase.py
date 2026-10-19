"""Real received-side callbacks must precede controlled obstacle publication."""
import ast
import copy
import io
import json
from pathlib import Path
import subprocess
import time
from types import MethodType, SimpleNamespace

from geometry_msgs.msg import TransformStamped
from nav_msgs.msg import Odometry
from std_msgs.msg import String
from tf2_msgs.msg import TFMessage
import pytest

from multi_robot_exploration import peer_obstacles as peer
from multi_robot_exploration.mr3_information import state_payload


class Publisher:
    def __init__(self):
        self.messages = []

    def publish(self, message):
        self.messages.append(copy.deepcopy(message))


def fixture(clock_ns=1_100_000_000, source_ns=1_000_000_000):
    names, now = ['tb1', 'tb2', 'tb3'], [clock_ns]
    node = SimpleNamespace(
        names=names, stepped_mode=True, epoch='e', phase_controlled=False,
        phase_pending=None, phase_cache={}, phase_last_clock=None, phase_commit_sequence=0,
        phase_record_sequence=0, phase_audit=io.StringIO(), phase_bundles=[],
        phase_input_topics={(k, n): f'/mr3/received/{n}/{k}'
                            for k in ('odom', 'tf') for n in names},
        phase_input_sequences={(k, n): 0 for k in ('odom', 'tf') for n in names},
        phase_input_cache={(k, n): [] for k in ('odom', 'tf') for n in names},
        odometry={}, transforms={}, failed=False, mission_started=True, tf_source_lead_sec=.2,
        get_clock=lambda: SimpleNamespace(now=lambda: SimpleNamespace(nanoseconds=now[0])),
        get_logger=lambda: SimpleNamespace(error=lambda value: None),
        failure_publisher=Publisher(), phase_ack_pub=Publisher(),
        publishers_by_robot={n: Publisher() for n in names},
        body_publishers={n: Publisher() for n in names})
    for name, method in vars(peer.PeerObstacles).items():
        if callable(method) and name not in ('__init__', 'destroy_node'):
            setattr(node, name, MethodType(method, node))
    odometry, transforms = {}, {}
    for index, name in enumerate(names):
        odom, tf = Odometry(), TransformStamped()
        odom.header.frame_id, odom.child_frame_id = 'odom', 'base_footprint'
        odom.header.stamp.sec, odom.header.stamp.nanosec = divmod(source_ns, 10**9)
        odom.pose.pose.orientation.w = 1.
        odom.pose.pose.position.x = float(index)
        tf.header.frame_id, tf.child_frame_id = 'map', 'odom'
        tf.header.stamp.sec, tf.header.stamp.nanosec = divmod(source_ns + 200_000_000, 10**9)
        tf.transform.rotation.w, tf.transform.translation.y = 1., 2.
        odometry[name], transforms[name] = odom, tf
    return node, now, odometry, transforms


def send(node, request):
    node.receive_phase_request(String(data=peer.canonical(request)))
    messages = node.phase_ack_pub.messages
    return json.loads(messages[-1].data) if messages else None


def takeover(node):
    return send(node, {'schema': 'mr3-peer-phase-request-v1', 'epoch': 'e',
                       'request_id': 'takeover',
                       'target_time_ns': node.get_clock().now().nanoseconds,
                       'operation': 'takeover'})


def deliver(node, odometry, transforms, bundle):
    for name in node.names:
        node.receive_odom(odometry[name], name)
        node.receive_tf(TFMessage(transforms=[transforms[name]]), name)
    node.receive_state_bundle(String(data=peer.canonical(bundle)))


def inputs(node, odometry, transforms, before_callback=True):
    clock, start, robots, refs = node.get_clock().now().nanoseconds, time.monotonic_ns(), [], {}
    for name in node.names:
        state = state_payload(name, odometry[name], transforms[name], .2)
        source = min(state['odom_source_stamp'], state['tf_source_stamp'])
        raw_tf = state.pop('transform')
        state.update(epoch='e', sequence=1, version=1, source_stamp=source,
                     received_stamp=clock / 1e9, valid=True)
        robots.append(state)
        refs[name] = {'sequence': 1, 'version': 1, 'source_stamp': source,
                      'source_ns': round(source * 1e9),
                      'odom_source_ns': peer.stamp_ns(odometry[name].header.stamp),
                      'tf_source_ns': peer.stamp_ns(transforms[name].header.stamp) - 200_000_000,
                      'odom_topic': f'/mr3/received/{name}/odom',
                      'tf_topic': f'/mr3/received/{name}/tf',
                      'odom_sha256': peer.payload_sha(state['odometry']),
                      'tf_sha256': peer.payload_sha(raw_tf)}
    bundle = {'epoch': 'e', 'sequence': 1, 'robots': robots}
    if before_callback:
        deliver(node, odometry, transforms, bundle)
    ack = {'schema': 'mr3-state-phase-ack-v1', 'epoch': 'e', 'request_id': 'phase1',
           'target_time_ns': clock, 'clock_ns': clock, 'operation': 'commit', 'ok': True,
           'state_sequence': 1, 'bundle_sha256': peer.payload_sha(bundle), 'robots': refs,
           'side_publish_started_wall_monotonic_ns': start,
           'bundle_publish_started_wall_monotonic_ns': start,
           'scope': 'actual_state_and_side_publish_calls_returned'}
    return {'schema': 'mr3-peer-phase-request-v1', 'epoch': 'e', 'request_id': 'phase1',
            'target_time_ns': clock, 'operation': 'commit', 'state_commit': ack}, bundle


def output_count(node):
    publishers = [*node.publishers_by_robot.values(), *node.body_publishers.values()]
    return sum(len(p.messages) for p in publishers)


def test_takeover_disables_timer_and_commit_waits_for_actual_callbacks():
    node, _, odom, tf = fixture()
    assert takeover(node)['scope'] == 'automatic_obstacle_timer_disabled'
    request, bundle = inputs(node, odom, tf, before_callback=False)
    send(node, request)
    assert node.phase_pending is not None and output_count(node) == 0
    node.publish_obstacles()
    assert output_count(node) == 0
    deliver(node, odom, tf, bundle)
    node.poll_phase()
    ack = json.loads(node.phase_ack_pub.messages[-1].data)
    assert ack['ok'] is True and ack['state_commit'] == request['state_commit']
    assert ack['scope'] == 'actual_obstacle_publish_calls_returned'
    assert output_count(node) == 6 and len(ack['publications']) == 6
    assert ack['obstacle_publication_sha256'] == peer.payload_sha(ack['publications'])
    assert send(node, request) == ack and output_count(node) == 6


def test_old_identical_cached_payloads_cannot_substitute_for_phase_receipt():
    node, _, odom, tf = fixture()
    takeover(node)
    request, bundle = inputs(node, odom, tf)
    later = time.monotonic_ns()
    request['state_commit'].update(side_publish_started_wall_monotonic_ns=later,
                                   bundle_publish_started_wall_monotonic_ns=later)
    send(node, request)
    assert node.phase_pending is not None and output_count(node) == 0
    deliver(node, odom, tf, bundle)
    node.poll_phase()
    assert output_count(node) == 6


@pytest.mark.parametrize('missing', ['bundle', 'odom', 'tf'])
def test_missing_source_waits_without_physics_then_times_out(missing):
    node, now, odom, tf = fixture()
    takeover(node)
    request, bundle = inputs(node, odom, tf, before_callback=False)
    if missing != 'bundle':
        node.receive_state_bundle(String(data=peer.canonical(bundle)))
    for name in node.names:
        if missing != 'odom':
            node.receive_odom(odom[name], name)
        if missing != 'tf':
            node.receive_tf(TFMessage(transforms=[tf[name]]), name)
    send(node, request)
    assert node.phase_pending is not None and output_count(node) == 0
    node.phase_pending['requested_wall'] -= 10.
    node.poll_phase()
    ack = json.loads(node.phase_ack_pub.messages[-1].data)
    assert ack['ok'] is False and 'timeout' in ack['error']
    assert now[0] == request['target_time_ns'] and output_count(node) == 0


@pytest.mark.parametrize('field,changed', [
    ('epoch', 'other'), ('state_sequence', True), ('clock_ns', True),
    ('bundle_sha256', 'bad'), ('scope', 'safe'), ('ok', 1)])
def test_bad_state_commit_never_publishes(field, changed):
    node, _, odom, tf = fixture()
    takeover(node)
    request, _ = inputs(node, odom, tf)
    request['state_commit'][field] = changed
    ack = send(node, request)
    assert ack['ok'] is False and output_count(node) == 0


def test_request_identity_conflict_and_clock_replay_cannot_republish():
    node, _, odom, tf = fixture()
    takeover(node)
    request, _ = inputs(node, odom, tf)
    assert send(node, request)['ok'] is True
    changed = copy.deepcopy(request)
    changed['target_time_ns'] += 20_000_000
    assert send(node, changed)['ok'] is False and output_count(node) == 6
    request['request_id'] = request['state_commit']['request_id'] = 'next'
    assert send(node, request)['ok'] is False and output_count(node) == 6


def test_overlap_remains_real_failure_and_cannot_receive_success_ack():
    node, _, odom, tf = fixture()
    odom['tb2'].pose.pose.position.x = .499
    takeover(node)
    request, _ = inputs(node, odom, tf)
    assert send(node, request)['ok'] is False and output_count(node) == 0 and node.failed
    failure = json.loads(node.failure_publisher.messages[-1].data)
    assert failure['reason'] == 'peer_body_envelopes_overlap'
    assert failure['diagnostic']['pairs'][0]['centre_distance_m'] == .499


def test_exact_half_second_passes_and_one_nanosecond_older_fails():
    for source, allowed in ((564_000_000, True), (563_999_999, False)):
        node, _, odom, tf = fixture(1_064_000_000, source)
        takeover(node)
        request, _ = inputs(node, odom, tf)
        assert send(node, request)['ok'] is allowed
        assert output_count(node) == (6 if allowed else 0)


def test_nonstepped_actual_ros_outputs_equal_original_frozen_geometry():
    node, _, odom, tf = fixture()
    node.stepped_mode = False
    for name in node.names:
        node.receive_odom(odom[name], name)
        node.receive_tf(TFMessage(transforms=[tf[name]]), name)
    root = Path(__file__).resolve().parents[5]
    relative = str(Path(peer.__file__).resolve().relative_to(root))
    old = subprocess.run(['git', 'show', '26534fae40409e266376baf0995fb15dc0223e4b:' + relative],
                         cwd=root, check=True, capture_output=True, text=True).stdout
    tree, current = ast.parse(old), ast.parse(Path(peer.__file__).read_text())

    def point(module):
        return next(n for n in module.body if isinstance(n, ast.FunctionDef)
                    and n.name == 'body_points')
    assert ast.dump(point(tree)) == ast.dump(point(current))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'PeerObstacles')
    original = next(n for n in cls.body if isinstance(n, ast.FunctionDef)
                    and n.name == 'publish_obstacles')
    namespace = dict(vars(peer))
    exec(compile(ast.Module(body=[original], type_ignores=[]), '<old-peer>', 'exec'), namespace)
    namespace['publish_obstacles'](node)
    expected = [copy.deepcopy(p.messages[-1]) for p in (
        *node.publishers_by_robot.values(), *node.body_publishers.values())]
    node.publish_obstacles()
    actual = [p.messages[-1] for p in (
        *node.publishers_by_robot.values(), *node.body_publishers.values())]
    assert actual == expected
    for index, (actual_message, expected_message) in enumerate(zip(actual, expected)):
        kind = "scan" if index < 3 else "cloud"
        assert peer.canonical(peer.obstacle_payload(actual_message, kind)) == peer.canonical(
            peer.obstacle_payload(expected_message, kind))


def test_side_subscription_must_really_resolve_to_received_only_topic():
    node, _, odom, tf = fixture()
    takeover(node)
    request, _ = inputs(node, odom, tf)
    node.phase_input_topics['odom', 'tb1'] = '/tb1/odom'
    ack = send(node, request)
    assert ack['ok'] is False and 'received-only' in ack['error']
    assert output_count(node) == 0


def test_commit_requires_takeover_and_cannot_repeat_takeover():
    node, _, odom, tf = fixture()
    request, _ = inputs(node, odom, tf)
    assert send(node, request)['ok'] is False and output_count(node) == 0
    assert takeover(node)['ok'] is True
    other = {'schema': 'mr3-peer-phase-request-v1', 'epoch': 'e',
             'request_id': 'takeover2', 'target_time_ns': node.get_clock().now().nanoseconds,
             'operation': 'takeover'}
    assert send(node, other)['ok'] is False


def test_pending_phase_clock_cannot_advance_without_error():
    node, now, odom, tf = fixture()
    takeover(node)
    request, _ = inputs(node, odom, tf, before_callback=False)
    send(node, request)
    now[0] += 20_000_000
    node.poll_phase()
    ack = json.loads(node.phase_ack_pub.messages[-1].data)
    assert ack['ok'] is False and 'clock passed' in ack['error']
    assert output_count(node) == 0


def test_captured_callback_message_cannot_mutate_after_its_sha_was_recorded():
    node, _, odom, tf = fixture()
    takeover(node)
    request, _ = inputs(node, odom, tf)
    odom['tb1'].pose.pose.position.x = 10.
    assert send(node, request)['ok'] is True
    cloud = node.body_publishers['tb1'].messages[-1]
    coordinates = peer.np.frombuffer(cloud.data, dtype='<f4').reshape(-1, 3)
    assert float(peer.np.median(coordinates[:, 0])) > .5


def test_actual_callback_refs_precede_matching_and_publication_ack():
    node, _, odom, tf = fixture()
    takeover(node)
    request, _ = inputs(node, odom, tf)
    send(node, request)
    rows = [json.loads(line) for line in node.phase_audit.getvalue().splitlines()]
    matched = next(row for row in rows if row['kind'] == 'inputs_matched')
    published = next(row for row in rows if row['kind'] == 'obstacles_published')
    ack = next(row for row in rows if row['kind'] == 'ack_published'
               and row['payload']['ack']['operation'] == 'commit')
    assert matched['record_sequence'] < published['record_sequence'] < ack['record_sequence']
    raw = {(row['kind'], row['payload'].get('robot'),
            row['payload'].get('input_sequence')): row for row in rows}
    for key, ref in matched['payload']['inputs'].items():
        if key == 'bundle':
            continue
        kind, name = key.split(':')
        item = raw['received_' + kind, name, ref['input_sequence']]
        assert item['payload']['raw_sha256'] == ref['raw_sha256']
        assert item['record_sequence'] < matched['record_sequence']
