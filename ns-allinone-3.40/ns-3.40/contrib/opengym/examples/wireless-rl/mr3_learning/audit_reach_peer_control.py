"""Independent mr3-reach-v1 peer geometry, control-chain and telemetry FIFO role.

The immutable independent control reader supplies unchanged geometry and causal
predicates. A private, exactly reversible source projection changes protocol
identities only. Complete new wire values pass additional strict v2 checks;
no input field is stripped and no historical audit/PASS is invoked. This role
must be combined with reach-information, reach-runtime and the other scientific
roles. It is not a continuous-body, native-closure or training qualification.
"""
import argparse
from collections import Counter
import copy
import hashlib
import inspect
import json
import math
from pathlib import Path
import re
from types import ModuleType

from . import audit_reach_information as information
from . import initial_encoder_replay as encoder_replay
from . import audit_reach_runtime as runtime
from . import native_custody_reach as custody
from .audit_reach_information import load_implementation

ROOT = Path(__file__).resolve().parents[7]
WIRELESS = Path('ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl')
ORIGINAL = WIRELESS / 'report/assets/20261017_mr3_p2a0_v10/independent/mr3_independent_control_phase_v1.py'
ORIGINAL_SHA = '04cd7d079c16004b20320868943bcdac899da7646304d30cbad0804d1a6ee8d3'
ROBOTS = information.ROBOTS
CONTRACT = information.CONTRACT
PROTOCOL = 'mr3-controlled-execution-phase-v2'
require, equal, fields = information.require, information.equal, information.fields
integer, canonical, sha = information.integer, information.canonical, information.sha
SAFETY = ('safety_contract', 'intent_refs', 'safety_table_sha256')
IDENTITY_EDITS = (
    ('mr3-state-phase-ack-v1', 'mr3-state-phase-ack-v2'),
    ('mr3-peer-phase-audit-v1', 'mr3-peer-phase-audit-v2'),
    ('mr3-peer-phase-request-v1', 'mr3-peer-phase-request-v2'),
    ('mr3-peer-phase-ack-v1', 'mr3-peer-phase-ack-v2'),
    ('mr3-motion-safety-status-v1', 'mr3-motion-safety-status-v2'),
    ('mr3-motion-control-request-v1', 'mr3-motion-control-request-v2'),
    ('mr3-motion-control-ack-v1', 'mr3-motion-control-ack-v2'),
    ('mr3-controlled-execution-phase-v1', 'mr3-controlled-execution-phase-v2'),
    ('elif kind == "decision":', 'elif kind == "reach_decision":'),
)


def valid_output(value):
    fields(value, ('linear_x', 'angular_z'), 'motion output')
    for key, cap in (('linear_x', .20), ('angular_z', .8)):
        require(type(value[key]) is float and math.isfinite(value[key]) and abs(value[key]) <= cap,
                'typed unchanged .20/.8 final output bound')


def validate_status(value, epoch):
    keys = {'schema', 'epoch', 'clock_ns', 'ready', 'completion_scope', 'decision_sequences', 'outputs', *SAFETY}
    stop = value.get('phase_kind') == 'stop'
    if stop:
        keys.add('phase_kind')
    fields(value, keys, 'complete v2 motion status')
    require(value['schema'] == 'mr3-motion-safety-status-v2' and value['epoch'] == epoch
            and value['safety_contract'] == CONTRACT and type(value['ready']) is bool
            and value['completion_scope'] == 'publication_and_local_topic_receipt', 'v2 status identity/scope')
    integer(value['clock_ns'], 'motion status clock')
    fields(value['decision_sequences'], ROBOTS, 'motion status decision roles')
    fields(value['outputs'], ROBOTS, 'motion status output roles')
    information.validate_refs(value['intent_refs'])
    for name in ROBOTS:
        integer(value['decision_sequences'][name], 'status decision sequence', 1)
        valid_output(value['outputs'][name])
    if value['safety_table_sha256'] is None:
        require(all(o == {'linear_x': 0., 'angular_z': 0.} for o in value['outputs'].values()),
                'no consumed table cannot authorize motion')
    else:
        information.digest(value['safety_table_sha256'])
    if stop:
        require(value['ready'] is False and all(o == {'linear_x': 0., 'angular_z': 0.}
                for o in value['outputs'].values()), 'permanent STOP must be strict three zero')
    return stop


def load_impl(root=ROOT):
    """Return private v2 replay classes and explicit effective-source provenance.

    The original audit entrypoints are never called. The eight schema strings
    and one event selector are the only source replacements. New strict status
    predicates replace the private globals used by all inherited causal checks.
    """
    path = Path(root) / ORIGINAL
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == ORIGINAL_SHA, 'immutable control source differs')
    projected = raw
    changes = []
    for before, after in IDENTITY_EDITS:
        b, a = before.encode(), after.encode()
        count = projected.count(b)
        require(count > 0 and a not in projected, 'original protocol projection is not exact/unique')
        projected = projected.replace(b, a)
        changes.append({'before': before, 'after': after, 'occurrences': count})
    inverse = projected
    for before, after in reversed(IDENTITY_EDITS):
        inverse = inverse.replace(after.encode(), before.encode())
    require(inverse == raw, 'whole immutable control source inverse differs')
    core = ModuleType('mr3_reach_private_independent_control_v2')
    core.__file__ = str(path)
    exec(compile(projected, str(path) + ':explicit-v2-projection', 'exec'), core.__dict__)
    core.valid_output, core.validate_status = valid_output, validate_status
    provenance = {'schema': 'mr3-reach-peer-control-implementation-v1',
        'immutable_source': {'path': str(path), 'sha256': ORIGINAL_SHA},
        'projected_source_sha256': hashlib.sha256(projected).hexdigest(),
        'whole_inverse_sha256': hashlib.sha256(inverse).hexdigest(), 'whole_inverse_exact': True,
        'identity_only_source_edits': changes,
        'strict_private_global_overrides': {name: hashlib.sha256(inspect.getsource(function).encode()).hexdigest()
            for name, function in (('valid_output', valid_output), ('validate_status', validate_status))},
        'entry': {'path': str(Path(__file__).resolve()),
                  'sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
        'strict_wire_replay_helper': {'path': str(Path(information.__file__).resolve()),
            'sha256': hashlib.sha256(Path(information.__file__).read_bytes()).hexdigest()},
        'scope': 'New effective implementation identity, not the original reader identity or original PASS. '
                 'Complete wire data is unchanged. Original expected_outputs, MotionReplay, ControlReplay, '
                 'native_receipts and audit_advances predicates remain applicable and necessary.'}
    return core, provenance


def peer_replay_class(core):
    class ReachPeer(information.PeerReplay):
        def __init__(self, epoch, base, info):
            super().__init__(epoch, base, info)
            self.expected_geometry = None
            self.match_wall = None
            self.request_walls = {}
            self.control_acks = {}

        def record(self, row, clock, wall):
            kind, value = row['kind'], row['payload']
            if kind == 'request_received':
                self.request_walls[value['request_id']] = wall
            if kind == 'inputs_matched':
                # Parent independently reconstructs the complete bundle and
                # six matching callbacks before any geometry is computed.
                super().record(row, clock, wall)
                selected = {}
                state = self.pending['state_commit']
                for name in ROBOTS:
                    for raw_kind in ('odom', 'tf'):
                        matches = [r for r in self.cache[raw_kind, name]
                            if r['raw_sha256'] == state['robots'][name][raw_kind + '_sha256']
                            and r['received_wall_monotonic_ns'] >= state['side_publish_started_wall_monotonic_ns']]
                        require(matches, 'geometry lacks matched original side callback')
                        selected[raw_kind, name] = matches[-1]
                self.expected_geometry = core.expected_outputs(selected, clock)
                self.match_wall = wall
                return
            super().record(row, clock, wall)
            if kind == 'ack_published':
                ack = value['ack']; identifier = ack['request_id']
                self.control_acks[identifier] = {'ack': copy.deepcopy(ack),
                    'request': copy.deepcopy(self.requests[identifier]),
                    'request_wall': self.request_walls[identifier],
                    'publish_started_wall_monotonic_ns': value['publish_started_wall_monotonic_ns'],
                    'publish_completed_wall_monotonic_ns': value['publish_completed_wall_monotonic_ns']}

        def publications(self, outputs, wall):
            super().publications(outputs, wall)
            if not self.controlled:
                return  # Original warmup is recorded, without controlled geometry credit.
            require(self.expected_geometry is not None and self.match_wall is not None,
                    'peer geometry before actual full input matching')
            for item in outputs:
                key = item['robot'], item['kind']
                equal(item['payload'], self.expected_geometry[key],
                      'full peer scan/cloud bytes differ from immutable independent geometry')
                require(self.match_wall <= item['publish_started_wall_monotonic_ns'],
                        'peer actual publication before input matching')

    return ReachPeer


def request_shape(value, component, epoch):
    operation = value['operation']
    allowed = {'schema', 'epoch', 'request_id', 'operation', 'target_time_ns'}
    if component == 'state':
        allowed.add('expected_intents')
    elif operation == 'commit':
        allowed.add('state_commit')
        if component == 'motion':
            allowed.add('peer_commit')
    elif component == 'motion' and operation == 'stop' and 'reason' in value:
        allowed.add('reason')
    fields(value, allowed, 'complete v2 ' + component + ' request')
    schema = 'mr3-motion-control-request-v2' if component == 'motion' else f'mr3-{component}-phase-request-v2'
    require(value['schema'] == schema and value['epoch'] == epoch
            and type(value['request_id']) is str and value['request_id']
            and operation in (('takeover', 'commit', 'stop') if component == 'motion' else ('takeover', 'commit')),
            'v2 request identity')
    integer(value['target_time_ns'], 'request target')
    if component == 'state':
        information.validate_refs(value['expected_intents'])


def motion_replay_class(core, authority_context=None):
    class ReachMotion(core.MotionReplay):
        def __init__(self, epoch, state_acks, peer_acks, info, base):
            super().__init__(epoch, state_acks, peer_acks)
            self.information, self.base = info, base
            self.raw_requests, self.request_sequences = {}, Counter()
            self.owner_intents = {n: {} for n in ROBOTS}
            self.state_ingress = None
            self.state_gid = None
            self.output_gids = {}
            self.constructed_acks = {}
            self.counts = Counter()

        def check_dependencies(self, request, wall):
            super().check_dependencies(request, wall)
            evidence = information.bundle_evidence(self.received, self.epoch, self.base, request['target_time_ns'])
            for item in (request['state_commit'], request['peer_commit']):
                for key in SAFETY:
                    equal(item[key], evidence[key], 'motion dependency substituted full safety evidence')

        def record(self, row):
            kind, value, wall = row['kind'], row['payload'], row['wall_monotonic_ns']
            clock = round(information.number(row['sim_time_sec']) * 1e9)
            self.counts[kind] += 1
            if self.state_ingress is not None:
                require(kind == 'received_states', 'actual state callback prefix was interrupted')
            if kind == 'configuration':
                require(row['record_sequence'] == 1 and value['safety_contract'] == CONTRACT
                        and value['controlled_execution'] is True, 'explicit controlled reach profile required')
            elif kind in ('control_failure', 'invalid_received_states', 'clock_changed_during_decision',
                          'reach_model_failure', 'normal_control_model_invalid', 'invalid_reach_driver_ingress',
                          'settled_turn_model_failure', 'actual_cmd_vel_error', 'target_phase_error'):
                raise ValueError('actual failure remains invalid: ' + kind)
            elif kind == 'raw_request':
                name, request = value['robot'], value['request']
                require(name in ROBOTS and type(request['supported']) is bool, 'raw request robot/type')
                self.request_sequences[name] += 1
                require(type(request['sequence']) is int and request['sequence'] == self.request_sequences[name],
                        'raw request callback sequence gap')
                if request['supported']:
                    expected = {'linear': {'x': request['v'], 'y': 0., 'z': 0.},
                                'angular': {'x': 0., 'y': 0., 'z': request['w']}}
                    equal(value['twist'], expected, 'supported request changed complete raw Twist')
                    information.number(request['v']); information.number(request['w'])
                self.raw_requests[name] = copy.deepcopy(request)
            elif kind == 'reach_state_ingress':
                equal(self.base.parse(value['raw_json']), value['message'], 'actual received state String changed')
                self.state_gid = information.graph(value['publisher_identity'], '/mr3/received/states',
                                                   'mr3_information', '/', self.state_gid)
                information.bundle_evidence(value['message'], self.epoch, self.base)
                incoming_bundle_sha256 = sha(value['message']) if self.information.complete_publications else None
                require(any(p['message_sha256'] == incoming_bundle_sha256
                            and p['publish_started_wall_monotonic_ns'] <= wall
                            for p in self.information.complete_publications), 'state callback has no real complete publication')
                self.state_ingress = copy.deepcopy(value['message'])
            elif kind == 'received_states':
                require(self.state_ingress is not None, 'guard state lacks actual graph-bound callback')
                equal(value, self.state_ingress, 'guard substituted actual received state')
                self.state_ingress = None
            elif kind == 'reach_intent_publish':
                name, intent = value['robot'], value['intent']
                information.validate_intent(intent, self.epoch, name, self.base, clock)
                require(intent['intent_sequence'] == len(self.owner_intents[name]) + 1
                        and value['payload_sha256'] == sha(intent)
                        and value['scope'] == 'actual_publisher_call_returned_not_delivery', 'actual owner intent prefix')
                require(integer(value['publish_started_wall_monotonic_ns'], 'owner publish start', 1)
                        <= integer(value['publish_completed_wall_monotonic_ns'], 'owner publish end', 1) <= wall,
                        'owner actual publish window')
                self.owner_intents[name][intent['intent_sequence']] = copy.deepcopy(value)
            elif kind == 'control_request':
                request_shape(value, 'motion', self.epoch)
            elif kind == 'control_abandoned':
                require(value['request_id'] in self.requests, 'abandonment erased an unknown request')
                equal(value, self.requests[value['request_id']][0], 'abandoned request identity changed')
            elif kind == 'reach_decision':
                self.check_decision(value, clock)
            elif kind in ('authority_configuration', 'authority_callback', 'authority_ack_publication'):
                require(authority_context is not None,
                        'new authority event lacks complete independent receiving/stop/owner/protocol proof')
            elif kind == 'actual_cmd_vel':
                name, identity = value['robot'], value['publisher_identity']
                endpoints = identity['endpoints']
                require(identity['valid'] is True and identity['scope'] == 'graph_at_callback'
                        and identity['topic'] == f'/{name}/cmd_vel' and len(endpoints) == 1,
                        'actual output unique graph identity')
                endpoint = endpoints[0]; gid = endpoint['endpoint_gid']
                require(endpoint['namespace'] == '/' and endpoint['node'] == 'motion_safety'
                        and endpoint['topic_type'] == 'geometry_msgs/msg/Twist'
                        and type(gid) is str and re.fullmatch(r'(?:[0-9a-f]{2}){16,}', gid)
                        and int(gid, 16) != 0 and (name not in self.output_gids or self.output_gids[name] == gid),
                        'actual output graph owner/type/GID changed')
                self.output_gids[name] = gid
            elif kind == 'output_completed':
                self.check_status(value['status'])
            elif kind == 'control_ack':
                require(value['schema'] == 'mr3-motion-control-ack-v2' and value['epoch'] == self.epoch
                        and value['ok'] is True and value['safety_contract'] == CONTRACT,
                        'new motion control ACK failed/profile differs')
                self.check_status(value['status'])
                for key in ('intent_refs', 'safety_table_sha256'):
                    equal(value[key], value['status'][key], 'control ACK differs from actual completed status safety')
                require(value['request_id'] not in self.constructed_acks, 'new control ACK constructed twice')
                self.constructed_acks[value['request_id']] = copy.deepcopy(value)
            elif kind in ('control_ack_published', 'control_cached_ack_published'):
                equal(value['ack'], self.constructed_acks.get(value['ack']['request_id']),
                      'published motion ACK lacks actual completed construction')
            elif kind not in {'own_odom', 'own_tf', 'reach_driver_ingress', 'reach_release_ready',
                    'release', 'stop_request', 'terminal', 'failure', 'invalid_terminal_notice',
                    'control_dependency', 'control_commit', 'output_observer_wait'}:
                raise ValueError('unknown reach motion record ' + str(kind))
            # Runs all original applicable predicates against the original full row.
            super().record(row)

        def check_decision(self, value, clock):
            name, decision = value['robot'], value['decision']
            require(name in ROBOTS and type(value['clock_ns']) is int and value['clock_ns'] == clock
                    and type(value['ready']) is bool and type(value['started']) is bool,
                    'reach decision identity/clock/flags')
            equal(value['request'], self.raw_requests.get(name), 'guard changed/borrowed actual request callback')
            output = decision['output']
            require(type(output) is list and len(output) == 2 and type(decision['allow']) is bool,
                    'reach decision typed output/allow')
            valid_output({'linear_x': output[0], 'angular_z': output[1]})
            rows = {r['name']: r for r in self.received['robots']} if self.received is not None else {}
            equal(value['received_peers'], {n: rows.get(n) for n in ROBOTS if n != name}, 'guard peer full bundle changed')
            table = value['safety_table_sha256']
            if table is not None:
                require(self.received is not None and self.received['safety_table_sha256'] == table,
                        'guard used a different consumed table')
                information.bundle_evidence(self.received, self.epoch, self.base, clock)
            else:
                equal(output, [0., 0.], 'guard without consumed table moved')
            intent = value['intent']
            actual = self.owner_intents[name].get(intent['intent_sequence'])
            require(actual is not None, 'decision intent was not actually published')
            equal(intent, actual['intent'], 'decision changed actual owner intent')
            target = intent['target']
            require(target is not None and target['decision_sequence'] == value['decision_sequence']
                    and target['clock_ns'] == clock, 'decision/target exact identity')
            equal(output, [target['linear_x'], target['angular_z']], 'decision differs from exact actual target')
            if not decision['allow'] or not value['ready'] or not value['started'] or value.get('phase_kind') == 'stop':
                equal(output, [0., 0.], 'denied/unready/pre-release/STOP output is not strict zero')
            request = value['request']
            if authority_context is not None:
                permission = authority_context['gates'][name].decision_permissions.get(value['decision_sequence'])
                require(permission is not None and value.get('motion_authority_profile') == authority_context['profile'],
                        'peer decision missing independently reconstructed authority permission')
                equal(value['motion_authority'], permission, 'peer authority permission changed after replay')
                equal(value['effective_request'], permission['effective_request'], 'peer effective request bypassed authority')
                if permission['permission'] == 'zero_only':
                    equal(output, [0.,0.], 'unowned/revoked/expired raw stream escaped zero-only authority')
            available = (request is not None and request['supported'] is True
                and request['publisher_identity']['valid'] is True
                and 0 <= clock-round(information.number(request['received_stamp'])*1e9) <= 200_000_000)
            if not available:
                equal(output, [0., 0.], 'unavailable actual request created motion')
                return
            identity = request['publisher_identity']
            endpoints = identity['endpoints']
            require(identity['scope'] == 'graph_at_callback' and identity['topic'] == f'/{name}/cmd_vel_unguarded'
                    and len(endpoints) == 1 and endpoints[0]['namespace'] == '/' + name
                    and endpoints[0]['node'] == 'velocity_smoother', 'request actual smoother owner')
            normalized = []
            for actual_number, cap in ((request['v'], .20), (request['w'], .8)):
                if abs(actual_number) > cap:
                    if abs(actual_number) != math.nextafter(cap, math.inf):
                        equal(output, [0., 0.], 'unsupported request escaped hard-zero filter')
                        return
                    actual_number = math.copysign(cap, actual_number)
                normalized.append(float(actual_number))
            if output == [0., 0.] or canonical(output) == canonical(normalized):
                return
            require(decision['reason'] == 'linear_brake_preserve_requested_turn' and decision['allow'] is True
                    and normalized[0] != 0 and normalized[1] != 0 and output == [0., normalized[1]]
                    and rows[name]['safety']['intent']['role'] == 'D'
                    and value['intent']['role'] == 'D', 'output selected a new velocity/heading instead of preserving request')
            equal(decision['component_filter']['canonical_input'], normalized, 'partial filter canonical request changed')
            rejected = decision['component_filter']['rejected_transition_checks']
            require(type(rejected) is dict and rejected
                    and any(v.get('geometric_necessary') is False for v in rejected.values()),
                    'partial filter lacks rejected prospective X evidence')

        def check_status(self, status):
            stop = validate_status(status, self.epoch)
            group = []
            for name in ROBOTS:
                value = self.decisions.get((name, status['decision_sequences'][name]))
                require(value is not None, 'status lacks prior actual decisions')
                decision = value[0]
                require((decision.get('phase_kind') == 'stop') == stop, 'status changed actual decision category')
                group.append(decision)
            expected = {d['robot']: {'intent_sequence': d['intent']['intent_sequence'],
                                     'payload_sha256': sha(d['intent'])} for d in group}
            equal(status['intent_refs'], expected, 'status new refs differ from actual owner publications')
            require(all(d['safety_table_sha256'] == status['safety_table_sha256'] for d in group),
                    'three logical guards did not consume one frozen table')

        def finish(self):
            require(self.state_ingress is None and len(self.release) == 1 and self.takeovers == 1,
                    'unfinished ingress/missing unique release/takeover')
            require(all(not self.output_pending[n] and self.last_sequences[n] > 0 for n in ROBOTS),
                    'unmatched final telemetry output FIFO')
            require(set(self.constructed_acks) == set(self.acks), 'constructed motion ACK lacks actual published return')
            return {'decisions': {n: self.last_sequences[n] for n in ROBOTS},
                    'actual_outputs': {n: sum(key[0] == n for key in self.observed) for n in ROBOTS},
                    'unmatched': {n: len(self.output_pending[n]) for n in ROBOTS},
                    'normal_statuses': sum(key[1] == 'normal' for key in self.completed),
                    'stop_statuses': sum(key[1] == 'stop' for key in self.completed)}

    return ReachMotion


def control_replay_class(core):
    class ReachControl(core.ControlReplay):
        def __init__(self, epoch, component_acks, motion, base):
            super().__init__(epoch, component_acks, motion)
            self.base = base
            self.last_wall = -1
            self.owner_latest, self.owner_gids = {}, {}
            self.release_capture = None
            self.release_capture_used = False
            self.counts = Counter()
            self.rejected_terminal, self.closed_terminal = {}, set()

        def record(self, row):
            require(row['schema'] == PROTOCOL and row['epoch'] == self.epoch, 'worker explicit v2 profile')
            wall = integer(row['wall_monotonic_ns'], 'worker record wall', 1)
            require(wall >= self.last_wall, 'worker callback prefix wall regressed')
            self.last_wall = wall
            kind = row['kind']; self.counts[kind] += 1
            if kind == 'owner_intent_received':
                name, intent = row['robot'], row['intent']
                information.validate_intent(intent, self.epoch, name, self.base)
                require(row['payload_sha256'] == sha(intent)
                        and row['identity_scope'] == 'graph_at_callback_not_per_packet_identity', 'worker owner callback scope/SHA')
                graph = row['publisher_graph']
                require(type(graph) is list and len(graph) == 1, 'worker sole actual owner graph')
                endpoint = graph[0]; gid = endpoint['endpoint_gid']
                require(endpoint['namespace'] == '/' and endpoint['node'] == 'motion_safety'
                        and endpoint['type'] == 'std_msgs/msg/String'
                        and type(gid) is str and re.fullmatch(r'(?:[0-9a-f]{2}){16,}', gid)
                        and int(gid, 16) != 0 and (name not in self.owner_gids or self.owner_gids[name] == gid),
                        'worker owner graph identity changed')
                publication = self.motion.owner_intents[name].get(intent['intent_sequence'])
                require(publication is not None and publication['publish_started_wall_monotonic_ns'] <= wall,
                        'worker owner callback has no actual earlier publication')
                equal(intent, publication['intent'], 'worker owner intent differs from actual publication')
                previous = self.owner_latest.get(name)
                require(previous is None or canonical(previous) == canonical(intent)
                        or intent['intent_sequence'] > previous['intent_sequence']
                        and intent['source_clock_ns'] >= previous['source_clock_ns'], 'worker owner callback regressed/conflicted')
                self.owner_gids[name] = gid; self.owner_latest[name] = copy.deepcopy(intent)
                return
            if kind == 'release_intents_captured':
                release = integer(row['release_clock_ns'], 'captured actual release')
                require(self.release_capture is None and len(self.motion.release) == 1
                        and release == self.motion.release[0][0]
                        and row['worker_clock_ns'] == row['worker_physical_ns'] == release,
                        'release refs lack exact real release/unique capture')
                require(set(self.owner_latest) == set(ROBOTS), 'release refs missing actual owner callbacks')
                for name, intent in self.owner_latest.items():
                    information.validate_intent(intent, self.epoch, name, self.base, release)
                    require(intent['role'] == 'HOLD' and intent['lineage']['release_clock_ns'] == release,
                            'release refs borrowed pre-release or non-HOLD intent')
                expected = {n: {'intent_sequence': v['intent_sequence'], 'payload_sha256': sha(v)}
                            for n, v in self.owner_latest.items()}
                equal(row['intent_refs'], expected, 'release refs differ from actual subscribed post-release HOLDs')
                self.release_capture = copy.deepcopy(expected)
                return
            if kind in ('infrastructure_abort_started', 'infrastructure_abort_closed'):
                raise ValueError('actual worker infrastructure abort remains invalid')
            if kind == 'request':
                component, request = row['component'], row['request']
                require(component in ('state', 'peer', 'motion'), 'worker request component')
                request_shape(request, component, self.epoch)
                if component == 'state':
                    if request['operation'] == 'commit' and self.release_capture is not None and not self.release_capture_used:
                        expected = self.release_capture
                        self.release_capture_used = True
                    else:
                        actual = [value for (kind_, _), value in self.consumed.items()
                                  if kind_ == 'motion' and value[1] <= wall]
                        require(actual, 'state refs lack a genuinely consumed prior motion status')
                        expected = max(actual, key=lambda v: v[1])[0]['status']['intent_refs']
                    equal(request['expected_intents'], expected, 'state requested refs differ from actual previous output/release callback')
            if kind == 'ack_received':
                ack = row['ack']
                require(type(ack) is dict, 'actual worker ACK must be an object')
                if ack.get('epoch') == self.epoch:
                    require(type(ack.get('ok')) is bool, 'actual worker ACK typed result')
                    if not ack['ok']:
                        require(row['component'] == 'state' and ack.get('error') == 'state_phase_task_terminal'
                                and ack.get('scope') == 'terminal_cancelled_uncommitted_state_phase'
                                and type(ack.get('terminal_notice')) is dict,
                                'actual nonterminal negative ACK is sticky, including abandoned requests')
            if kind == 'terminal_cancelled':
                key = row['component'], row['ack']['request_id']
                require(key in self.received and key in self.rejected_terminal and key not in self.closed_terminal,
                        'terminal cancellation lacks unique real rejected ACK')
                equal(row['ack'], self.received[key][0], 'terminal cancellation changed actual ACK')
                equal(row['terminal_notice'], row['ack']['terminal_notice'], 'terminal cancellation lost actual notice')
                require(row['terminal_notice']['epoch'] == self.epoch
                        and round(information.number(row['terminal_notice']['end_sim_time_sec'])*1e9)
                        <= row['worker_physical_ns'], 'terminal cancellation notice clock')
                self.closed_terminal.add(key)
            super().record(row)
            if kind == 'ack_rejected':
                key = row['component'], row['ack']['request_id']
                self.rejected_terminal[key] = copy.deepcopy(row['ack'])

        def finish(self):
            require(self.pending is None, 'unconsumed final worker control request')
            require(self.release_capture is not None, 'missing actual post-release HOLD capture')
            require(set(self.rejected_terminal) == self.closed_terminal, 'unclosed actual terminal rejection')
            return dict(self.counts)

    return ReachControl


LEGACY_NATIVE_KINDS = frozenset((
    'configuration', 'reset', 'command_received', 'actuation', 'status_publish', 'target_rejected'))
ENCODER_NATIVE_KINDS = frozenset(('initial_encoder_configuration', 'initial_encoder_receive'))


def native_profile_context(directory, metadata, plan_path):
    """Reuse the strict frozen binding/new-build and actual configuration gates.

    This is read-only source/build evidence. Loaded-process lifetime remains the
    separate mandatory custody/closure role; no normalization is performed.
    """
    profile = custody.initial_encoder_profile(metadata)
    if profile is None:
        return None
    from . import reach_preparation
    require(plan_path is not None, 'new encoder peer replay requires its exact source plan')
    plan_path = Path(plan_path).resolve()
    plan = reach_preparation.load_plan(plan_path, ROOT)
    from .motion_authority_profile import selected_motion_authority_profile
    authority = selected_motion_authority_profile(metadata, required=True)
    require(selected_motion_authority_profile(plan, required=True) == authority,
            'peer plan and episode receiving authority profiles differ')
    require(custody.initial_encoder_profile(plan) == profile,
            'peer source plan and episode actuation profiles differ')
    freeze = metadata['freeze']
    source = reach_preparation.source_check(plan, plan_path, freeze, ROOT, require_clean=False)
    module, implementation = custody.load_implementation(ROOT)
    bound = module.load_binding(plan['custody_binding'], freeze, root=ROOT)
    require(custody.initial_encoder_profile(bound['document']) == profile,
            'peer native binding and episode actuation profiles differ')
    # This inherited reader checks the actual SDF/loaded library and both
    # native/supervisor profile metadata, including the compiled helper SHA.
    configurations = module.configurations(Path(directory), bound)
    bound['reader'].finish()
    selected = {}
    for robot in ROBOTS:
        rows = [item['configuration'] for item in configurations
                if Path(item['path']).name == 'drive_' + robot + '.jsonl']
        require(len(rows) == 2 and {r['kind'] for r in rows} ==
                {'configuration', 'initial_encoder_configuration'},
                'peer lacks actual original and encoder native configurations')
        selected[robot] = {row['kind']: row for row in rows}
    return {'actuation_profile': profile, 'motion_authority_profile': authority,
        'epoch': metadata['epoch'], 'freeze': freeze,
        'binding': {'path': bound['path'], 'sha256': bound['sha256']},
        'helper_sha256': bound['document']['initial_encoder_compiled_source']['sha256'],
        'reach_build_bridge_proof': bound['reach_build_bridge_proof'],
        'source_proof': source, 'implementation_provenance': implementation,
        'configurations': selected, 'bindings': bound['reader'].bindings}


def compound_native_prefix(metadata, drivers, motion_rows, context):
    """Check complete original driver rows with the existing independent law.

    Only the two explicitly declared new event kinds gain admission. Native
    storage commands, complete record ordering, every actual motor write and
    every retained current-epoch APPLIED callback keep their original values.
    This reuses the three drive traces already read by this role; it does not
    run the complete runtime/geometry replay again.
    """
    profile = custody.initial_encoder_profile(metadata)
    if profile is None:
        require(context is None, 'old native prefix cannot borrow an encoder proof')
        return None
    require(type(context) is dict and context.get('actuation_profile') == profile
            and context.get('epoch') == metadata['epoch'] and context.get('freeze') == metadata['freeze'],
            'peer encoder proof has another profile/epoch/freeze')
    build = context['reach_build_bridge_proof']
    require(build.get('new_build_executed') is True and build.get('actuation_profile') == profile
            and build.get('initial_encoder_compiled_source', {}).get('sha256') == context['helper_sha256'],
            'peer encoder prefix lacks the strict actual new-build/helper proof')
    motors = {}
    for robot in ROBOTS:
        rows = drivers[robot]
        require(rows and all(row.get('kind') in LEGACY_NATIVE_KINDS | ENCODER_NATIVE_KINDS for row in rows),
                'unknown native kind cannot acquire encoder prefix credit')
        actual = context['configurations'][robot]
        equal(rows[0], actual['configuration'], 'peer driver configuration differs from actual bound configuration')
        encoders = [row for row in rows if row['kind'] == 'initial_encoder_configuration']
        require(len(encoders) == 1, 'missing or repeated encoder configuration')
        equal(encoders[0], actual['initial_encoder_configuration'],
              'peer encoder configuration differs from actual bound configuration')
        motors[robot] = encoder_replay.replay_native_drive(rows, profile=profile,
            epoch=metadata['epoch'], robot=robot, helper_sha256=context['helper_sha256'])
    applied, stable = dict.fromkeys(ROBOTS, 0), {}
    for row in motion_rows:
        if row['kind'] != 'reach_driver_ingress' or row['payload'].get('kind') != 'applied':
            continue
        payload = row['payload']; message = payload['message']
        equal(runtime.decode_text(payload['raw_json']), message, 'APPLIED actual raw JSON changed')
        if message.get('epoch') != metadata['epoch']:
            continue  # Retained old callbacks supply no current credit.
        robot = payload['robot']
        require(robot in ROBOTS and message.get('robot') == robot, 'APPLIED subscribed/native robot differs')
        runtime.graph_identity(payload['publisher_identity'], robot, 'applied', stable)
        encoder_replay.check_applied_receipt(message, motors[robot])
        applied[robot] += 1
    return {'actuation_profile': profile, 'passed': True,
        'actual_new_build_required_and_verified': True, 'complete_native_rows_retained': True,
        'native_inputs_normalized': False, 'accepted_additional_event_kinds': sorted(ENCODER_NATIVE_KINDS),
        'motor_replay': {robot: {key: value for key, value in replay.items() if key != 'actuations'}
                         for robot, replay in motors.items()},
        'retained_current_epoch_applied_callbacks_joined': applied,
        'scope': 'Complete three native compound laws plus exact retained APPLIED joins; '
                 'delivery completeness, geometry, physics and loaded-process closure remain separate mandatory roles.'}


def fifo_facts(motion_phase, drive_rows, drive_worker, physical, motion, control, epoch, release, final, *, encoder_prefix=False):
    """Retain the original independent FIFO/source-age facts under v2 status."""
    received = {}; consumed = []
    last_clock, last_sequences = -1, dict.fromkeys(ROBOTS, -1)
    for row in motion_phase:
        require(row['epoch'] == epoch and row['kind'] in ('ack_received', 'ack_consumed'),
                'normal motion worker record identity/kind')
        wall = integer(row['wall_monotonic_ns'], 'motion worker wall', 1)
        status = row['ack']; require(not validate_status(status, epoch), 'stop overwrote normal status channel')
        actual = motion.completed.get(core_status_key(status))
        require(actual is not None and actual['start'] <= wall, 'normal status callback precedes actual publication')
        equal(status, actual['status'], 'motion worker changed actual status bytes')
        key = status['clock_ns']
        if row['kind'] == 'ack_received':
            require(key >= last_clock and all(status['decision_sequences'][n] >= last_sequences[n] for n in ROBOTS),
                    'normal status callback clock/sequence regressed')
            if key > last_clock:
                require(all(status['decision_sequences'][n] > last_sequences[n] for n in ROBOTS),
                        'normal status clock advanced without three new decisions')
            previous = received.get(key)
            require(previous is None or canonical(previous[0]) == canonical(status), 'motion worker same-clock status changed')
            received[key] = copy.deepcopy(status), wall
            last_clock, last_sequences = key, dict(status['decision_sequences'])
        else:
            require(key in received and received[key][1] <= wall
                    and row['worker_physical_ns'] == row['worker_clock_ns'] == key,
                    'normal status consumption without actual callback/exact paused clock')
            equal(status, received[key][0], 'normal status changed between callback and consumption')
            consumed.append(status)
    require(sum(s['clock_ns'] == release and s['ready'] is True for s in consumed) == 1,
            'missing unique healthy release motion consumption')
    require(any(s['clock_ns'] == final for s in consumed + [s for s, _ in control.stop_observed]),
            'final physical clock lacks normal or strict-stop actual completion')
    robots = {}
    for name in ROBOTS:
        counts = {'task_actuations': 0, 'task_command_receipts': 0, 'target_rejected_task': 0,
                  'max_exact_receive_age_ns': 0, 'max_exact_target_age_ns': 0, 'over160ms_actuations': 0}
        for index, row in enumerate(drive_rows[name], 1):
            require(row['epoch'] == epoch and row['robot'] == name and type(row['record_sequence']) is int
                    and row['record_sequence'] == index and row['kind'] in
                    (LEGACY_NATIVE_KINDS | ENCODER_NATIVE_KINDS if encoder_prefix else LEGACY_NATIVE_KINDS),
                    'native driver complete identity/record prefix')
            source = row['sim_time_ns']
            if row['kind'] == 'target_rejected' and release <= source <= final:
                counts['target_rejected_task'] += 1
            if row['kind'] not in ('command_received', 'actuation') or not release <= source <= final or row['target_clock_ns'] < release:
                continue
            expected = motion.decisions.get((name, row['target_decision_sequence']))
            require(expected is not None and expected[0]['clock_ns'] == row['target_clock_ns'],
                    'native tagged source has no actual guard decision')
            equal([row['desired_v'], row['desired_w']], expected[0]['decision']['output'], 'native desired target changed guard output')
            age = integer(source, 'native source') - integer(row['target_clock_ns'], 'native target source')
            require(age >= 0, 'future native target source')
            if row['kind'] == 'command_received':
                counts['task_command_receipts'] += 1
                counts['max_exact_receive_age_ns'] = max(counts['max_exact_receive_age_ns'], age)
            else:
                counts['task_actuations'] += 1
                counts['max_exact_target_age_ns'] = max(counts['max_exact_target_age_ns'], age)
                counts['over160ms_actuations'] += age > 160_000_000
        require(counts['over160ms_actuations'] == counts['target_rejected_task'] == 0,
                'native task target age/rejection failure')
        robots[name] = counts
    positive = {r['request_id']: r for r in physical if r['steps'] == 20 and r['start_time_ns'] >= release}
    advances = {r['request_id']: r for r in drive_worker if r['kind'] == 'advance_permitted'
                and r['start_time_ns'] >= release and r['steps'] == 20}
    require(set(positive) == set(advances), 'actual positive20tick physics and permission sets differ')
    for row in drive_worker:
        require(row['kind'] in ('ack_received', 'ack_consumed', 'advance_permitted', 'physics_completed'),
                'unknown/failing drive worker record')
        if row['kind'] == 'advance_permitted' and row.get('control_kind') == 'normal':
            require(row['steps'] == 20, 'reach normal advance must retain genuine20ms quantum')
    return {'passed': True, 'robots': robots, 'motion_consumed_acks': len(consumed),
            'positive20tick_physics': len(positive), 'unmatched': {n: len(motion.output_pending[n]) for n in ROBOTS}}


def core_status_key(status):
    return status['clock_ns'], status.get('phase_kind', 'normal')


def replay_records(data, core, host, *, native_context=None):
    """Pure decoded-artifact replay, exposed for synthetic CPU tests only."""
    metadata = data['metadata.json']; epoch = metadata['epoch']; base = host.BASE
    require(metadata.get('safety_contract') == CONTRACT
            and metadata.get('execution_phase_protocol') == PROTOCOL
            and metadata.get('reset_handshake') == 'paused-controlled-state-peer-guard-storage-v2',
            'old profile/phase metadata cannot acquire new role credit')
    from .motion_authority_profile import selected_motion_authority_profile
    authority = selected_motion_authority_profile(metadata)
    authority_report = authority_context = None
    if authority is not None:
        from . import motion_authority_audit
        require(native_context is not None and native_context.get('motion_authority_profile') == authority,
                'peer authority role lacks strict plan/source/native profile context')
        release = data['transitions.jsonl'][0]['info']['release_time_ns']
        end = max(r['end_time_ns'] for r in data['physics.jsonl'])
        drive = {n:data['drive_'+n+'.jsonl'] for n in ROBOTS}
        odom = {n:data['odometry_'+n+'.jsonl'] for n in ROBOTS}
        actual = runtime.native_index(drive,odom,epoch,actuation_profile=metadata['actuation_profile'],
            encoder_helper_sha256=native_context['helper_sha256'])
        streams = runtime.ingress_index(data['motion_safety.jsonl'],actual,epoch,
            reach_geometry_rule=runtime.geometry_rule(metadata))
        authority_report, authority_context = motion_authority_audit.replay_motion(
            data['motion_safety.jsonl'],actual,epoch,release)
        # The same original independent physical/STOP-debt replay is mandatory;
        # do not infer it from a ready flag, helper import or zero body request.
        stop = {n:runtime.replay_robot(n,streams[n],actual[n],epoch,release,end) for n in ROBOTS}
        adapter = motion_authority_audit.replay_adapter(data['adapter.jsonl'],data['transitions.jsonl'],
            epoch,authority_context,motion_authority_audit.original_protocol_class(ROOT))
        authority_report.update(schema='mr3-independent-motion-authority-episode-v1',passed=True,
            epoch=epoch,adapter=adapter,original_global_stop_debts_and_fixed_radius_passed=True,
            original_stop_replay=stop)
        authority_context['profile'] = authority
    info = information.information_replay_class(host)(epoch)
    for row, _, _ in information.prefix(data['information_states.jsonl'], 'mr3-information-state-audit-v2', epoch):
        info.record(row)
    info.finish()
    state_acks = {identifier: {'ack': copy.deepcopy(value), 'request': copy.deepcopy(info.phase_requests[identifier]),
        'request_wall': info.phase_request_walls[identifier],
        'publish_started_wall_monotonic_ns': next(p['start'] for p in info.ack_publications if p['ack']['request_id'] == identifier),
        'publish_completed_wall_monotonic_ns': next(p['end'] for p in info.ack_publications if p['ack']['request_id'] == identifier)}
        for identifier, value in info.phase_acks.items()}
    peer = peer_replay_class(core)(epoch, base, info)
    for row, clock, wall in information.prefix(data['peer_phase.jsonl'], 'mr3-peer-phase-audit-v2', epoch):
        peer.record(row, clock, wall)
    peer_counts = peer.finish()
    motion = motion_replay_class(core,authority_context)(epoch, state_acks, peer.control_acks, info, base)
    for row, _, _ in information.prefix(data['motion_safety.jsonl'], 'mr3-motion-safety-v1', epoch, motion=True):
        motion.record(row)
    motion_counts = motion.finish()
    release = motion.release[0][0]
    transitions = data['transitions.jsonl']
    require(transitions and transitions[0]['kind'] == 'reset'
            and transitions[0]['info']['release_time_ns'] == release, 'original reset/release differs from actual motion callback')
    control = control_replay_class(core)(epoch, {'state': state_acks, 'peer': peer.control_acks,
                                              'motion': motion.acks}, motion, base)
    for row in data['control_phase_worker.jsonl']:
        control.record(row)
    control_counts = control.finish()
    physical = data['physics.jsonl']; require(physical, 'missing actual physics receipts')
    end = max(integer(r['end_time_ns'], 'physical end') for r in physical)
    require(release <= end, 'release beyond final actual physics')
    drivers = {n: data['drive_' + n + '.jsonl'] for n in ROBOTS}
    compound = compound_native_prefix(metadata, drivers, data['motion_safety.jsonl'], native_context)
    native = {n: core.native_receipts(drivers[n], epoch, n) for n in ROBOTS}
    advances = core.audit_advances(data['drive_phase_worker.jsonl'], physical, epoch, control, native, release)
    fifo = fifo_facts(data['motion_phase_worker.jsonl'], drivers, data['drive_phase_worker.jsonl'],
                      physical, motion, control, epoch, release, end, encoder_prefix=compound is not None)
    statuses = [(ack['status'], wall) for (component, _), (ack, wall) in control.consumed.items() if component == 'motion']
    replay = {'records': len(data['control_phase_worker.jsonl']), 'consumed_motion_phases': len(statuses),
        'stop_clocks': sorted({s['clock_ns'] for s, _ in statuses if s.get('phase_kind') == 'stop'}),
        'normal_clocks': sorted({s['clock_ns'] for s, _ in statuses if s.get('phase_kind') != 'stop'}),
        'terminal_cancellations': control_counts.get('terminal_cancelled', 0),
        'bootstrap_zero_quanta': advances['bootstrap_zero_advances'],
        'scope': 'Complete actual v2 state/peer/guard/FIFO/storage/physics causal necessities; not body response or closure.'}
    return {'passed': True, 'epoch': epoch, 'task_release_ns': release, 'physics_end_ns': end,
            **({'motion_authority_profile':authority,'independent_motion_authority_replay_passed':True,
                'motion_authority_replay':authority_report} if authority is not None else {}),
            'peer': peer_counts, 'motion_fifo': motion_counts, 'worker_control': control_counts,
            'advance_replay': advances, 'fifo': fifo, 'controlled_execution_replay': replay,
            'execution_replay': copy.deepcopy(replay),
            **({'actuation_profile': compound['actuation_profile'],
                'initial_encoder_compound_replay_passed': True,
                'initial_encoder_native_prefix': compound} if compound is not None else {})}


def audit_episode(directory, expected_freeze=None, *, plan_path=None):
    directory = Path(directory)
    core, implementation = load_impl()
    host, measurement = load_implementation()
    inputs = host.BASE.Inputs()
    result = {'schema': 'mr3-reach-peer-control-fifo-review-v1', 'episode': str(directory),
        'safety_contract': CONTRACT, 'passed': False, 'errors': [], 'inputs': inputs.bindings,
        'artifact_proof': {}, 'bindings': {}, 'implementation': implementation,
        'independent_measurement_oracle': measurement,
        'roles': ['reach_peer_geometry', 'reach_control_chain', 'reach_motion_fifo'],
        'historical_38_role_qualification': False, 'native_admission': False,
        'limitations': ['Necessary evidence only; conjunction with reach-information and reach-runtime is required.',
            'No continuous body model, fixed-anchor qualification, metric/heading calibration, paired-slew math, '
            'contact/task/reward/actor acceptance or native shutdown proof is inferred.',
            'Publisher graph observations are not packet authentication, three independent network endpoints or P3 isolation.']}
    try:
        metadata = host.BASE.parse(inputs.read(directory, 'metadata.json'))
        freeze = metadata['freeze']
        require(type(freeze) is str and re.fullmatch(r'[0-9a-f]{40}', freeze)
                and (expected_freeze is None or freeze == expected_freeze), 'exact episode freeze differs')
        result['freeze'] = freeze
        data = {'metadata.json': metadata}
        data['summary.json'] = host.BASE.parse(inputs.read(directory, 'summary.json'))
        for name in ('transitions.jsonl', 'information_states.jsonl', 'peer_phase.jsonl', 'motion_safety.jsonl',
                     'control_phase_worker.jsonl', 'drive_phase_worker.jsonl', 'motion_phase_worker.jsonl',
                     'physics.jsonl', *(f'drive_{n}.jsonl' for n in ROBOTS)):
            data[name] = inputs.rows(directory, name)
        from .motion_authority_profile import selected_motion_authority_profile
        authority = selected_motion_authority_profile(metadata, required=True)
        data['adapter.jsonl'] = inputs.rows(directory, 'adapter.jsonl')
        for name in ROBOTS:
            data['odometry_'+name+'.jsonl'] = inputs.rows(directory,'odometry_'+name+'.jsonl')
        context = native_profile_context(directory, metadata, plan_path)
        result.update(replay_records(data, core, host, native_context=context))
        if context is not None:
            result['initial_encoder_source_build_context'] = context
    except (OSError, ValueError, KeyError, TypeError, OverflowError, IndexError, AssertionError) as error:
        result['passed'] = False; result['errors'].append(str(error))
    try:
        inputs.verify()
        for item in inputs.bindings:
            key = Path(item['path']).name
            result['artifact_proof'][key] = {'path': item['path'], 'sha256': item['encoded_sha256'],
                                            'bytes': item['encoded_bytes'], 'decoded_sha256': item['decoded_sha256']}
            result['bindings'][item['path']] = {'sha256': item['encoded_sha256'], 'bytes': item['encoded_bytes']}
        for entry in (implementation['entry'], implementation['immutable_source'], implementation['strict_wire_replay_helper'], measurement['effective_entry'],
                      *measurement['unchanged_original_sources']):
            require(hashlib.sha256(Path(entry['path']).read_bytes()).hexdigest() == entry['sha256'],
                    'independent consumer source changed during replay')
    except (OSError, ValueError) as error:
        result['passed'] = False; result['errors'].append(str(error))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--freeze', required=True)
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    require(not args.output.exists(), 'exclusive new output required')
    result = audit_episode(args.directory, args.freeze, plan_path=args.plan)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'passed': result['passed'], 'output': str(args.output)}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
