"""Independent replay of the mr3-reach-v1 information delivery role.

Only the immutable, independent raw odometry/TF measurement oracle is reused.
Safety metadata is reconstructed from actual subscriber callback prefixes. This
role does not qualify reach geometry, calibration physics, handoff qualification,
obstacle geometry, native closure, training, or the historical 38-role matrix.
No ROS, production node, guard, or simulator is imported.
"""
import argparse
from collections import Counter
import copy
import hashlib
import inspect
import json
import math
from pathlib import Path
import struct
import textwrap

from .audit_information import load_implementation as load_measurement_implementation
from .motion_authority_profile import selected_motion_authority_profile

ROBOTS = ('tb1', 'tb2', 'tb3')
CONTRACT = 'mr3-reach-v1'
AGE = 500_000_000
BUNDLE_KEYS = {'epoch', 'sequence', 'robots', 'map_version', 'map_source_stamp',
    'map_received_stamp', 'map_sources', 'map_payload_sha256', 'navigation_composition',
    'navigation_sources', 'information_diagnostics', 'safety_contract', 'intent_refs',
    'safety_table_sha256'}


def load_implementation():
    """Retain the exact delivered TF in the private new-profile row oracle.

    The original loader and immutable files stay unchanged. The complete
    envelope, actual raw TF selection, side publication and full row comparisons
    still execute; this changes just the declared bundle projection.
    """
    host, provenance = load_measurement_implementation()
    original = host.RawReplay.publish
    source_path = Path(original.__code__.co_filename)
    raw = source_path.read_bytes()
    binding = next(item for item in provenance['unchanged_original_sources']
                   if Path(item['path']).resolve() == source_path.resolve())
    require(hashlib.sha256(raw).hexdigest() == binding['sha256'], 'immutable TF row oracle differs')
    before = b"            transform = state.pop('transform')\n"
    after = b"            transform = state['transform']\n"
    require(raw.count(before) == 1 and after not in raw, 'ambiguous received TF projection')
    projected = raw.replace(before, after, 1)
    require(projected.count(after) == 1 and projected.replace(after, before, 1) == raw,
            'whole TF row projection inverse differs')
    method = inspect.getsource(original)
    require(method.count(before.decode()) == 1, 'TF projection is outside the original publish method')
    changed = textwrap.dedent(method.replace(before.decode(), after.decode(), 1))
    namespace = dict(original.__globals__)
    exec(compile(changed, str(Path(__file__).resolve()) + ':delivered_transform', 'exec'), namespace)
    host.RawReplay.publish = namespace['publish']
    provenance = dict(provenance, reach_delivery_transform_projection={
        'original_source': binding, 'projected_whole_source_sha256': hashlib.sha256(projected).hexdigest(),
        'whole_source_inverse_sha256': hashlib.sha256(raw).hexdigest(), 'whole_source_inverse_equal': True,
        'literal_before': before.decode(), 'literal_after': after.decode(), 'literal_count': 1,
        'effective_publish_method_sha256': hashlib.sha256(changed.encode()).hexdigest(),
        'scope': 'keep actual delivered transform in new-profile whole row; all original raw/send/delivery/side comparisons remain',
        'original_files_modified': False, 'native_inputs_modified': False})
    return host, provenance


def require(value, reason):
    if not value:
        raise ValueError(reason)


def fields(value, keys, label):
    require(type(value) is dict and set(value) == set(keys), label + ' exact fields')


def integer(value, label, minimum=0):
    require(type(value) is int and value >= minimum, label + ' integer/range')
    return value


def number(value):
    require(type(value) in (int, float) and math.isfinite(value), 'finite numeric scalar')
    return value


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def sha(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def equal(actual, expected, label):
    require(canonical(actual) == canonical(expected), label)


def digest(value):
    require(type(value) is str and len(value) == 64
            and all(c in '0123456789abcdef' for c in value), 'SHA256 identity')


def causal(source, now):
    integer(source, 'source')
    if now is not None:
        require(0 <= integer(now, 'clock') - source <= AGE, 'future/stale safety source')


def odometry(raw, base):
    fields(raw, ('header', 'child_frame_id', 'pose', 'twist'), 'odometry')
    fields(raw['header'], ('stamp', 'frame_id'), 'odom header')
    fields(raw['header']['stamp'], ('sec', 'nanosec'), 'odom stamp')
    require(type(raw['header']['frame_id']) is str and raw['header']['frame_id']
            and type(raw['child_frame_id']) is str and raw['child_frame_id'], 'odom frame IDs')
    for outer, inner, vectors in (('pose', 'pose', ('position', 'orientation')),
                                  ('twist', 'twist', ('linear', 'angular'))):
        fields(raw[outer], (inner, 'covariance'), 'odom ' + outer)
        fields(raw[outer][inner], vectors, 'odom ' + inner)
    base.validate_raw('odom', raw)
    return base.header_ns(raw)


def target(value, epoch, robot, source):
    fields(value, ('schema', 'epoch', 'robot', 'clock_ns', 'decision_sequence',
                   'linear_x', 'angular_z'), 'target')
    identity(value, 'mr3-drive-target-v1', epoch, robot)
    require(integer(value['clock_ns'], 'target clock') <= source, 'future target')
    integer(value['decision_sequence'], 'target decision', 1)
    require(abs(number(value['linear_x'])) <= .20 and abs(number(value['angular_z'])) <= .8,
            'unchanged target bounds')


def identity(value, schema, epoch, robot):
    require(robot in ROBOTS and type(epoch) is str and epoch
            and value['schema'] == schema and value['epoch'] == epoch
            and value['robot'] == robot, 'wire schema/epoch/robot')


def validate_intent(value, epoch, robot, base, now=None):
    """Independent wire checks; historical obligations are replayed separately."""
    fields(value, ('schema', 'epoch', 'robot', 'intent_sequence', 'source_clock_ns',
                   'role', 'anchor', 'admitted_signs', 'lineage', 'target'), 'intent')
    identity(value, 'mr3-safety-intent-v1', epoch, robot)
    seq = integer(value['intent_sequence'], 'intent sequence', 1)
    source = integer(value['source_clock_ns'], 'intent source')
    causal(source, now)
    role, anchor, signs, lineage, command = (value[k] for k in
        ('role', 'anchor', 'admitted_signs', 'lineage', 'target'))
    require(role in ('HOLD', 'D', 'X', 'N', 'STOP'), 'intent role')
    require(type(signs) is list and len(signs) <= 2 and len(set(signs)) == len(signs)
            and all(type(s) is int and s in (-1, 1) for s in signs), 'admitted signed family')
    if anchor is not None:
        fields(anchor, ('source_clock_ns', 'odometry'), 'anchor')
        require(integer(anchor['source_clock_ns'], 'anchor source')
                == odometry(anchor['odometry'], base) <= source, 'anchor raw source')
    if command is not None:
        target(command, epoch, robot, source)
    if role == 'HOLD':
        fields(lineage, ('release_clock_ns',), 'HOLD lineage')
        release = lineage['release_clock_ns']
        if release is None:
            require(anchor is None, 'pre-release anchor')
        else:
            require(anchor is not None and command is not None
                    and anchor['source_clock_ns'] <= integer(release, 'release') <= source,
                    'post-release causal HOLD anchor')
        require(not signs and (command is None or command['linear_x'] == command['angular_z'] == 0),
                'HOLD must be full zero')
    elif role in ('D', 'X', 'N'):
        keys = {'anchor_intent_sequence'}
        if role != 'D':
            keys.add('transition_intent_sequence')
        if role == 'N':
            keys.update(('actuation_sequence', 'actuation_source_clock_ns',
                         'causal_source_clock_ns', 'cmd_seq'))
        fields(lineage, keys, role + ' lineage')
        anchor_seq = integer(lineage['anchor_intent_sequence'], 'anchor intent', 1)
        require(anchor is not None and command is not None and anchor_seq <= seq,
                'active anchor/target lineage')
        if role == 'D':
            require(not signs and command['linear_x'] == 0, 'D zero linear')
        else:
            require(anchor_seq < integer(lineage['transition_intent_sequence'], 'transition', 1)
                    <= seq and signs, 'X/N transition lineage')
            require(command['linear_x'] == 0
                    or (1 if command['linear_x'] > 0 else -1) in signs, 'unannounced sign')
        if role == 'N':
            integer(lineage['actuation_sequence'], 'actuation', 1)
            integer(lineage['cmd_seq'], 'native command', 1)
            require(anchor['source_clock_ns'] <= integer(lineage['actuation_source_clock_ns'], 'applied')
                    < integer(lineage['causal_source_clock_ns'], 'causal raw') <= source,
                    'N strict post-actuation raw source')
            causal(lineage['causal_source_clock_ns'], now)
    else:
        fields(lineage, ('previous_intent_sequence', 'previous_role'), 'STOP lineage')
        require(integer(lineage['previous_intent_sequence'], 'previous intent', 1) < seq
                and lineage['previous_role'] in ('HOLD', 'D', 'X', 'N'), 'STOP prior lineage')
        require(command is None or command['linear_x'] == command['angular_z'] == 0, 'STOP full zero')
        previous = lineage['previous_role']
        require((previous == 'HOLD' or anchor is not None)
                and (not signs if previous in ('HOLD', 'D') else bool(signs)), 'STOP protected role')


def validate_calibration(value, epoch, robot, base, now=None):
    fields(value, ('schema', 'epoch', 'robot', 'source_clock_ns', 'publication_sequence',
                   'coefficient_c', 'coefficient_s', 'odometry', 'conversion_contract',
                   'producer_frame'), 'calibration')
    identity(value, 'mr3-odom-calibration-v1', epoch, robot)
    causal(value['source_clock_ns'], now)
    integer(value['publication_sequence'], 'publication', 1)
    c, s = (number(value[k]) for k in ('coefficient_c', 'coefficient_s'))
    require(abs(c) <= 1 and abs(s) <= 1 and c*c+s*s > 0
            and all(struct.unpack('!f', struct.pack('!f', x))[0] == x for x in (c, s)),
            'actual float32 coefficient representation')
    require(value['conversion_contract'] == 'float32-trig-binary64-rn-v1'
            and value['producer_frame'] == 'world-common-model-origin-v1'
            and odometry(value['odometry'], base) == value['source_clock_ns'], 'calibration source contract')


def safety(value, epoch, robot, raw, now, base):
    fields(value, ('intent', 'calibration'), 'safety sibling')
    validate_intent(value['intent'], epoch, robot, base, now)
    validate_calibration(value['calibration'], epoch, robot, base, now)
    equal(value['calibration']['odometry'], raw, 'calibration differs from complete selected odometry')
    if value['intent']['anchor'] is not None:
        anchor = value['intent']['anchor']['odometry']
        require(anchor['header']['frame_id'] == raw['header']['frame_id']
                and anchor['child_frame_id'] == raw['child_frame_id'], 'anchor/current frame changed')
    if value['intent']['role'] == 'N':
        require(value['intent']['lineage']['causal_source_clock_ns'] <= base.header_ns(raw),
                'N promise later than selected raw source')


def intent_refs(table):
    return {name: {'intent_sequence': item['intent']['intent_sequence'],
                   'payload_sha256': sha(item['intent'])} for name, item in table.items()}


def validate_refs(value):
    fields(value, ROBOTS, 'intent refs')
    for ref in value.values():
        fields(ref, ('intent_sequence', 'payload_sha256'), 'intent ref')
        integer(ref['intent_sequence'], 'intent reference', 1)
        digest(ref['payload_sha256'])


def bundle_evidence(value, epoch, base, now=None):
    fields(value, BUNDLE_KEYS, 'complete state bundle')
    require(value['epoch'] == epoch and value['safety_contract'] == CONTRACT, 'bundle contract/epoch')
    integer(value['sequence'], 'bundle sequence', 1)
    require(type(value['robots']) is list and len(value['robots']) == 3, 'complete three robot bundle')
    table = {}
    for row in value['robots']:
        name = row['name']
        require(name in ROBOTS and name not in table and row['epoch'] == epoch,
                'bundle unique robot identity')
        safety(row['safety'], epoch, name, row['odometry'], now, base)
        table[name] = row['safety']
    validate_refs(value['intent_refs'])
    equal(value['intent_refs'], intent_refs(table), 'bundle references differ from full intents')
    require(value['safety_table_sha256'] == sha(table), 'whole safety table digest')
    return {'safety_contract': CONTRACT, 'intent_refs': intent_refs(table),
            'safety_table_sha256': sha(table)}


def graph(value, topic, node, namespace, previous=None, motion=False):
    """A graph observation, deliberately not packet publisher authentication."""
    expected = {'scope', 'topic', 'valid', 'endpoints'}
    if not motion:
        expected.update(('packet_publisher_gid_available', 'error'))
    fields(value, expected, 'publisher graph')
    require(value['scope'] == 'graph_at_callback' and value['topic'] == topic
            and value['valid'] is True, 'publisher graph scope/validity')
    if not motion:
        require(value['packet_publisher_gid_available'] is False and value['error'] is None,
                'graph must not claim unavailable packet GID')
    require(type(value['endpoints']) is list and len(value['endpoints']) == 1, 'sole graph endpoint')
    endpoint = value['endpoints'][0]
    node_key, ns_key = ('node', 'namespace') if motion else ('node_name', 'node_namespace')
    fields(endpoint, (node_key, ns_key, 'topic_type', 'endpoint_gid'), 'graph endpoint')
    gid = endpoint['endpoint_gid']
    require(endpoint[node_key] == node and endpoint[ns_key] == namespace
            and endpoint['topic_type'] == 'std_msgs/msg/String'
            and type(gid) is str and len(gid) % 2 == 0 and len(gid) > 0
            and all(c in '0123456789abcdef' for c in gid) and any(c != '0' for c in gid)
            and (previous is None or previous == gid), 'graph owner/type/GID changed')
    return gid


def prefix(rows, schema, epoch, *, motion=False):
    wall = -1
    for index, row in enumerate(rows, 1):
        fields(row, ('schema', 'epoch', 'record_sequence', 'kind', 'sim_time_sec' if motion else 'clock_ns',
                     'wall_monotonic_ns', 'payload'), 'ledger row')
        require(row['schema'] == schema and row['epoch'] == epoch
                and type(row['record_sequence']) is int and row['record_sequence'] == index,
                'complete ledger schema/epoch/contiguous prefix')
        current = integer(row['wall_monotonic_ns'], 'record wall', 1)
        require(current >= wall, 'ledger wall regressed')
        wall = current
        clock = round(number(row['sim_time_sec']) * 1e9) if motion else integer(row['clock_ns'], 'clock')
        require(type(row['payload']) is dict, 'ledger payload object')
        yield row, clock, wall


def information_replay_class(host):
    """Reuse unchanged independent measurement/serialization; add the new role."""
    base = host.BASE

    class ReachInformation(host.LedgerReplay):
        def __init__(self, epoch):
            super().__init__(epoch)
            self.meta = {(kind, name): [] for kind in ('intent', 'calibration') for name in ROBOTS}
            self.meta_latest = {}
            self.meta_sequences = Counter()
            self.meta_gids = {}
            self.meta_prune = None
            self.actual_intent_ingress = []
            self.complete_publications = []
            self.ack_publications = []

        def record(self, row):
            # The caller validates the complete new ledger prefix, not a schema-v1 projection.
            kind, value, clock, wall = row['kind'], row['payload'], row['clock_ns'], row['wall_monotonic_ns']
            self.sequence += 1
            self.last_wall = wall
            self.counts[kind] += 1
            if self.meta_prune is not None:
                require(kind == self.meta_prune[0] + '_ingress' and value['robot'] == self.meta_prune[1],
                        'prune is not the same actual callback prefix')
            if kind == 'configuration':
                require(self.sequence == 1 and self.config is None, 'first unique configuration')
                require(value['safety_contract'] == CONTRACT and value['safety_identity_scope'] == 'graph_at_callback'
                        and type(value['safety_history_limit']) is int and value['safety_history_limit'] == 256,
                        'explicit reach information configuration')
                require(value['tf_validity_lead_sec'] == .2 and value['pending_limit'] == 256
                        and canonical(value['state_period_sec']) == canonical(.1)
                        and value['odom_pending_order'] == 'source_ns_ascending'
                        and value['tf_pending_order'] == 'accepted_header_ascending', 'original measurement configuration')
                self.config, self.lead_sec, self.lead_ns = value, .2, 200_000_000
                return
            require(self.config is not None, 'missing configuration')
            if kind in ('intent_prune', 'calibration_prune'):
                self.prune(kind.split('_')[0], value, clock)
            elif kind in ('intent_ingress', 'calibration_ingress'):
                self.meta_ingress(kind.split('_')[0], value, clock, wall)
            elif kind in ('odom_ingress', 'tf_ingress'):
                self.ingress(kind.split('_')[0], value, clock)
            elif kind == 'tf_promote':
                self.tf_promote(value, clock)
            elif kind == 'state_selection':
                self.selection(value, clock)
            elif kind == 'state_send':
                self.send(value, clock)
            elif kind == 'state_publish':
                self.publish(value, clock, wall)
            elif kind == 'state_phase_request':
                self.request(value, clock, wall)
            elif kind == 'state_phase_ack':
                self.ack(value, clock, wall)
            elif kind == 'state_terminal_received':
                self.terminal(value)
            elif kind == 'state_drain_request':
                self.drain_request(value)
            elif kind == 'state_drain_ack':
                self.drain_ack(value, clock, wall)
            else:
                raise ValueError('unknown/failing information record ' + str(kind))

        def prune(self, kind, value, clock):
            fields(value, ('robot', 'input_sequences'), 'metadata prune')
            key = kind, value['robot']
            require(key in self.meta, 'prune robot')
            expired = [r for r in self.meta[key] if r['source_clock_ns'] < clock - AGE]
            require(expired, 'unnecessary metadata prune')
            equal(value['input_sequences'], [r['input_sequence'] for r in expired], 'metadata prune lost/added prefix')
            self.meta[key] = [r for r in self.meta[key] if r['source_clock_ns'] >= clock - AGE]
            self.meta_prune = key

        def meta_ingress(self, kind, value, clock, wall):
            name = value['robot']; key = kind, name
            require(key in self.meta, 'metadata robot')
            self.meta_sequences[key] += 1
            require(type(value['input_sequence']) is int
                    and value['input_sequence'] == self.meta_sequences[key], 'metadata input sequence gap')
            topic = f'/{name}/mr3/safety_intent' if kind == 'intent' else f'/{name}/mr3_drive/odometry_calibration'
            require(value['topic'] == topic, 'metadata actual subscribed topic')
            received = integer(value['received_wall_monotonic_ns'], 'metadata callback wall', 1)
            require(received <= wall, 'metadata callback after ledger')
            gid = graph(value['publisher_identity'], topic, 'motion_safety' if kind == 'intent' else 'turtlebot3_diff_drive',
                        '/' if kind == 'intent' else '/' + name, self.meta_gids.get(key))
            require(type(value['raw_json']) is str and hashlib.sha256(value['raw_json'].encode()).hexdigest()
                    == value['raw_json_sha256'], 'actual metadata String bytes SHA')
            parsed = base.parse(value['raw_json'])
            (validate_intent if kind == 'intent' else validate_calibration)(parsed, self.epoch, name, base)
            equal(value['value'], parsed, 'parsed metadata differs from actual String')
            require(value['payload_sha256'] == sha(parsed), 'metadata complete payload SHA')
            source = parsed['source_clock_ns']
            seq = parsed['intent_sequence' if kind == 'intent' else 'publication_sequence']
            require(type(value['producer_sequence']) is int and value['producer_sequence'] == seq
                    and type(value['source_clock_ns']) is int and value['source_clock_ns'] == source,
                    'metadata declared producer identity')
            previous = self.meta_latest.get(key)
            if previous is not None and seq <= previous['producer_sequence']:
                require(self.meta_prune is None, 'older/duplicate callback cannot prune')
                matched = next((r for r in self.meta[key] if r['producer_sequence'] == seq), None)
                if matched is None and seq == previous['producer_sequence']:
                    matched = previous
                require(matched is None or matched['payload_sha256'] == sha(parsed), 'conflicting producer sequence')
                require(value['admission'] == ('duplicate' if matched is not None else 'older')
                        and value['matched_input_sequence'] == (matched['input_sequence'] if matched else None),
                        'metadata duplicate/older admission')
            else:
                require(previous is None or source > previous['source_clock_ns']
                        or kind == 'intent' and source == previous['source_clock_ns'], 'metadata source regressed')
                require(not any(r['source_clock_ns'] < clock - AGE for r in self.meta[key]), 'unrecorded metadata prune')
                require(len(self.meta[key]) < 256 and value['admission'] == ('queued_future' if source > clock else 'queued'),
                        'metadata queue overflow/admission')
                item = {k: value[k] for k in ('input_sequence', 'producer_sequence', 'source_clock_ns',
                                             'payload_sha256', 'value')}
                self.meta[key].append(copy.deepcopy(item)); self.meta_latest[key] = copy.deepcopy(item)
                self.meta_gids[key] = gid
            self.meta_prune = None
            if kind == 'intent':
                self.actual_intent_ingress.append(copy.deepcopy(value))

        def selection(self, value, clock):
            host.LedgerReplay.selection(self, value, clock)
            name, cycle = value['robot'], value['cycle_id']
            selected = self.selections[cycle, name]
            require(selected['skip_reason'] is None, 'reach publication cannot omit safety/measurement')
            expected = self.phase_pending['expected_intents'][name] if self.controlled else None
            eligible = [r for r in self.meta['intent', name] if r['source_clock_ns'] <= clock]
            if expected is None:
                intent = max(eligible, key=lambda r: (r['source_clock_ns'], r['producer_sequence'])) if eligible else None
            else:
                intent = next((r for r in self.meta['intent', name]
                               if r['producer_sequence'] == expected['intent_sequence']), None)
                require(intent is not None and intent['payload_sha256'] == expected['payload_sha256'],
                        'requested intent is not actual admitted input')
            source = selected['odom']['source_ns']
            calibrations = [r for r in self.meta['calibration', name] if r['source_clock_ns'] == source <= clock]
            require(intent is not None and calibrations, 'missing actual intent/calibration ingress')
            calibration = calibrations[-1]
            reconstructed = {'intent': copy.deepcopy(intent['value']), 'calibration': copy.deepcopy(calibration['value'])}
            safety(reconstructed, self.epoch, name, selected['odom']['raw'], clock, base)
            equal(value['safety_input_sequences'], {'intent': intent['input_sequence'],
                  'calibration': calibration['input_sequence']}, 'safety selection borrowed different callback')
            selected['state']['safety'] = reconstructed

        def publish(self, value, clock, wall):
            if self.controlled:
                require(self.phase_pending is not None and self.phase_pending['operation'] == 'commit'
                        and self.phase_pending['target_time_ns'] == clock and self.phase_candidate is None,
                        'unrequested/multiple controlled state publication')
            # This original method compares the COMPLETE augmented envelope and row.
            host.RawReplay.publish(self, value, clock, wall)
            evidence = bundle_evidence(value['message'], self.epoch, base, clock)
            require(all(row['valid'] is True for row in value['message']['robots']), 'invalid reach state row')
            if self.controlled:
                equal(evidence['intent_refs'], self.phase_pending['expected_intents'], 'phase intent refs changed')
                require(self.phase_request_walls[self.phase_pending['request_id']]
                        <= value['side_publish_started_wall_monotonic_ns'] <= value['publish_started_wall_monotonic_ns'],
                        'state side publication before request/after bundle')
                self.phase_candidate = copy.deepcopy({'payload': value, 'clock_ns': clock})
            self.complete_publications.append(copy.deepcopy(value))

        def request(self, payload, clock, wall):
            value = payload['request']
            fields(value, ('schema', 'epoch', 'request_id', 'operation', 'target_time_ns', 'expected_intents'), 'state phase request')
            require(value['schema'] == 'mr3-state-phase-request-v2' and value['epoch'] == self.epoch
                    and type(value['request_id']) is str and value['request_id']
                    and value['operation'] in ('takeover', 'commit'), 'state phase v2 identity')
            validate_refs(value['expected_intents'])
            target_clock = integer(value['target_time_ns'], 'phase target')
            require(type(payload['duplicate']) is bool, 'phase duplicate flag')
            identifier = value['request_id']; previous = self.phase_requests.get(identifier)
            if previous is not None:
                require(payload['duplicate'] is True, 'undeclared phase duplicate')
                equal(value, previous, 'conflicting duplicate state request')
                if identifier in self.phase_acks:
                    self.phase_duplicate_ack = identifier
                else:
                    equal(self.phase_pending, value, 'duplicate phase is not pending')
                return
            require(clock <= target_clock and payload['duplicate'] is False and self.phase_pending is None,
                    'late/overlapping new state request')
            if value['operation'] == 'commit':
                require(self.controlled and (self.last_committed_clock is None or target_clock > self.last_committed_clock),
                        'commit before takeover/rewrites committed clock')
            else:
                require(not self.controlled, 'takeover must be unique')
            self.controlled = True
            self.phase_requests[identifier] = copy.deepcopy(value)
            self.phase_request_walls[identifier] = wall
            self.phase_pending = copy.deepcopy(value)
            self.phase_candidate = None

        def ack(self, payload, clock, wall):
            ack = payload['ack']; identifier = ack['request_id']
            request = self.phase_requests.get(identifier)
            require(request is not None and ack['schema'] == 'mr3-state-phase-ack-v2'
                    and ack['epoch'] == self.epoch and ack['safety_contract'] == CONTRACT,
                    'state ACK v2 identity/request')
            ack_fields = {'schema', 'epoch', 'request_id', 'operation', 'target_time_ns', 'clock_ns',
                          'ok', 'scope', 'safety_contract', 'intent_refs', 'safety_table_sha256'}
            if ack['ok'] is False:
                ack_fields.update(('error', 'terminal_notice'))
            else:
                ack_fields.update(('state_sequence', 'bundle_sha256', 'robots'))
                if request['operation'] == 'commit':
                    ack_fields.update(('side_publish_started_wall_monotonic_ns',
                                       'bundle_publish_started_wall_monotonic_ns',
                                       'bundle_publish_completed_wall_monotonic_ns'))
            fields(ack, ack_fields, 'complete state ACK')
            require(type(ack['ok']) is bool and type(payload['cached']) is bool
                    and ack['operation'] == request['operation']
                    and type(ack['target_time_ns']) is int and ack['target_time_ns'] == request['target_time_ns'],
                    'state ACK request binding')
            start = integer(payload['publish_started_wall_monotonic_ns'], 'ACK start', 1)
            end = integer(payload['publish_completed_wall_monotonic_ns'], 'ACK end', 1)
            require(self.phase_request_walls[identifier] <= start <= end <= wall, 'state ACK actual publish window')
            if payload['cached']:
                require(self.phase_duplicate_ack == identifier, 'unrequested cached state ACK')
                equal(ack, self.phase_acks.get(identifier), 'cached state ACK changed')
                self.phase_duplicate_ack = None
                return
            equal(self.phase_pending, request, 'ACK not for pending state request')
            require(identifier not in self.phase_acks and type(ack['clock_ns']) is int and ack['clock_ns'] == clock,
                    'new state ACK clock/identity')
            if ack['ok'] is False:
                require(ack.get('error') == 'state_phase_task_terminal'
                        and ack.get('scope') == 'terminal_cancelled_uncommitted_state_phase'
                        and request['operation'] == 'commit' and self.phase_candidate is None
                        and self.terminal_notice is not None, 'failed state ACK')
                equal(ack['terminal_notice'], self.terminal_notice, 'terminal cancellation notice changed')
                require(base.seconds_ns(self.terminal_notice['end_sim_time_sec']) <= request['target_time_ns']
                        and clock <= request['target_time_ns'] and ack['intent_refs'] is None
                        and ack['safety_table_sha256'] is None, 'terminal cancellation scope')
            elif request['operation'] == 'takeover':
                require(clock == request['target_time_ns'] and self.phase_candidate is None
                        and ack['state_sequence'] is None and ack['bundle_sha256'] is None
                        and ack['robots'] == {} and ack['intent_refs'] is None and ack['safety_table_sha256'] is None
                        and ack['scope'] == 'periodic_state_publication_disabled', 'takeover falsely claims consumption')
                self.counts['takeover_acks'] += 1
            else:
                require(clock == request['target_time_ns'], 'state commit clock mismatch')
                self.commit(ack, start)
                self.last_committed_clock = clock
                self.phase_commits.append(copy.deepcopy(ack)); self.counts['state_commit_acks'] += 1
            self.phase_acks[identifier] = copy.deepcopy(ack)
            self.ack_publications.append({'ack': copy.deepcopy(ack), 'start': start, 'end': end})
            self.phase_pending = self.phase_candidate = None

        def commit(self, ack, started):
            require(self.phase_candidate is not None, 'commit without actual publication')
            value = self.phase_candidate['payload']
            require(ack['scope'] == 'actual_state_and_side_publish_calls_returned'
                    and type(ack['state_sequence']) is int and ack['state_sequence'] == value['message']['sequence']
                    and ack['bundle_sha256'] == value['message_sha256'], 'state commit bundle binding')
            for key, original in (('side_publish_started_wall_monotonic_ns', 'side_publish_started_wall_monotonic_ns'),
                                  ('bundle_publish_started_wall_monotonic_ns', 'publish_started_wall_monotonic_ns'),
                                  ('bundle_publish_completed_wall_monotonic_ns', 'publish_completed_wall_monotonic_ns')):
                require(type(ack[key]) is int and ack[key] == value[original], 'commit publication windows')
            require(ack['bundle_publish_completed_wall_monotonic_ns'] <= started, 'ACK before bundle publication returned')
            evidence = bundle_evidence(value['message'], self.epoch, base, ack['clock_ns'])
            for key in evidence:
                equal(ack[key], evidence[key], 'commit complete safety evidence')
            fields(ack['robots'], ROBOTS, 'ACK robot set')
            sides = {r['robot']: r for r in value['side_publications']}
            for name in ROBOTS:
                envelope = value['envelopes'][name]
                expected = {'sequence': envelope['sequence'], 'version': envelope['version'],
                    'source_stamp': envelope['source_stamp'], 'source_ns': round(envelope['source_stamp']*1e9),
                    'odom_source_ns': round(envelope['payload']['odom_source_stamp']*1e9),
                    'tf_source_ns': round(envelope['payload']['tf_source_stamp']*1e9),
                    **{k: sides[name][k] for k in ('odom_topic', 'tf_topic', 'odom_sha256', 'tf_sha256')},
                    'safety_sha256': sha(envelope['payload']['safety'])}
                equal(ack['robots'][name], expected, 'ACK whole raw and safety side binding')

        def finish(self):
            require(self.meta_prune is None and all(self.meta_sequences[k] for k in self.meta),
                    'unfinished prune/missing safety source')
            return super().finish()

    return ReachInformation


class PeerReplay:
    def __init__(self, epoch, base, information):
        self.epoch, self.base, self.information = epoch, base, information
        self.cache = {(kind, name): [] for kind in ('odom', 'tf') for name in ROBOTS}
        self.sequences = Counter()
        self.bundles = []
        self.gid = None
        self.configured = self.controlled = False
        self.pending = self.matched = self.outputs = None
        self.requests, self.acks, self.ack_publications = {}, {}, []
        self.last_clock = None
        self.counts = Counter()

    def actual_bundle(self, value, received):
        require(value['message_sha256'] == sha(value['message']), 'peer complete bundle SHA')
        bundle_evidence(value['message'], self.epoch, self.base)
        matches = [p for p in self.information.complete_publications
                   if p['message_sha256'] == value['message_sha256']
                   and p['publish_started_wall_monotonic_ns'] <= received]
        require(matches, 'peer bundle has no actual earlier complete Information publication')
        equal(matches[-1]['message'], value['message'], 'peer changed complete state bundle')
        self.gid = graph(value['publisher_identity'], '/mr3/received/states', 'mr3_information', '/', self.gid)

    def match(self, request):
        state = request['state_commit']; target_clock = request['target_time_ns']
        candidates = [r for r in self.bundles if r['message_sha256'] == state['bundle_sha256']
                      and r['message']['sequence'] == state['state_sequence']
                      and r['received_wall_monotonic_ns'] >= state['bundle_publish_started_wall_monotonic_ns']]
        require(candidates, 'peer lacks actual matching bundle callback')
        bundle = candidates[-1]
        evidence = bundle_evidence(bundle['message'], self.epoch, self.base, target_clock)
        for key in evidence:
            equal(state[key], evidence[key], 'peer state ACK differs from complete received safety')
        rows = {r['name']: r for r in bundle['message']['robots']}
        refs = {}
        for name in ROBOTS:
            row, binding = rows[name], state['robots'][name]
            require(row['valid'] is True and row['epoch'] == self.epoch, 'peer committed invalid state')
            for key in ('sequence', 'version'):
                equal(row[key], binding[key], 'peer envelope identity')
            for key in ('source', 'odom_source', 'tf_source'):
                require(round(number(row[key + '_stamp'])*1e9) == binding[key + '_ns'], 'peer source binding')
            require(sha(row['safety']) == binding['safety_sha256'], 'peer robot safety SHA')
            for kind in ('odom', 'tf'):
                require(binding[kind + '_topic'] == f'/mr3/received/{name}/{kind}', 'peer received-only topic')
                matches = [r for r in self.cache[kind, name] if r['raw_sha256'] == binding[kind + '_sha256']
                           and r['received_wall_monotonic_ns'] >= state['side_publish_started_wall_monotonic_ns']]
                require(matches, 'peer lacks actual matching raw side callback')
                selected = matches[-1]
                source = self.base.header_ns(selected['raw']) - (200_000_000 if kind == 'tf' else 0)
                require(source == binding[kind + '_source_ns'], 'peer side source differs')
                refs[kind + ':' + name] = {k: selected[k] for k in
                    ('input_sequence', 'raw_sha256', 'received_wall_monotonic_ns')}
        refs['bundle'] = {'state_sequence': state['state_sequence'], 'message_sha256': bundle['message_sha256'],
                         'received_wall_monotonic_ns': bundle['received_wall_monotonic_ns'],
                         'publisher_identity': bundle['publisher_identity']}
        refs['safety'] = evidence
        return refs

    def publications(self, outputs, wall):
        require(type(outputs) is list and len(outputs) == 6, 'six actual obstacle publications')
        identities = set()
        for value in outputs:
            fields(value, ('robot', 'kind', 'topic', 'payload', 'message_sha256',
                           'publish_started_wall_monotonic_ns', 'publish_completed_wall_monotonic_ns'), 'obstacle call')
            name, kind = value['robot'], value['kind']
            require(name in ROBOTS and kind in ('scan', 'cloud') and (name, kind) not in identities,
                    'unique obstacle publication')
            identities.add((name, kind))
            expected = f'/{name}/peer_obstacles' if kind == 'scan' else f'/{name}/peer_footprints'
            require(value['topic'] == expected and value['message_sha256'] == sha(value['payload']),
                    'actual obstacle payload/topic binding')
            require(integer(value['publish_started_wall_monotonic_ns'], 'obstacle start', 1)
                    <= integer(value['publish_completed_wall_monotonic_ns'], 'obstacle end', 1) <= wall,
                    'actual obstacle call window')

    def record(self, row, clock, wall):
        kind, value = row['kind'], row['payload']; self.counts[kind] += 1
        if kind == 'configuration':
            require(not self.configured and row['record_sequence'] == 1
                    and value['stepped_mode'] is True and value['tf_source_lead_sec'] == .2,
                    'peer first stepped configuration')
            equal(value['input_topics'], {kind + ':' + name: f'/mr3/received/{name}/{kind}'
                  for kind in ('odom', 'tf') for name in ROBOTS}, 'peer original received-only subscriptions')
            self.configured = True
            return
        require(self.configured, 'peer before configuration')
        if kind in ('received_odom', 'received_tf'):
            raw_kind = kind.split('_')[1]; name = value['robot']; key = raw_kind, name
            require(key in self.cache, 'peer raw robot')
            self.sequences[key] += 1
            require(type(value['input_sequence']) is int and value['input_sequence'] == self.sequences[key],
                    'peer raw callback sequence gap')
            require(value['topic'] == f'/mr3/received/{name}/{raw_kind}', 'peer raw subscribed topic')
            self.base.validate_raw(raw_kind, value['raw'])
            require(value['raw_sha256'] == sha(value['raw'])
                    and integer(value['received_wall_monotonic_ns'], 'peer raw wall', 1) <= wall,
                    'peer raw SHA/callback wall')
            self.cache[key].append(copy.deepcopy(value)); self.cache[key] = self.cache[key][-32:]
        elif kind == 'received_state_bundle':
            received = integer(value['received_wall_monotonic_ns'], 'peer bundle callback wall', 1)
            require(received <= wall, 'peer callback after record')
            self.actual_bundle(value, received)
            self.bundles.append(copy.deepcopy(value)); self.bundles = self.bundles[-32:]
        elif kind == 'controlled':
            require(not self.controlled and self.pending is None and value['operation'] == 'takeover',
                    'peer takeover unique')
            self.controlled = True
        elif kind == 'request_received':
            fields(value, {'schema', 'epoch', 'request_id', 'operation', 'target_time_ns'}
                   | ({'state_commit'} if value['operation'] == 'commit' else set()), 'peer request')
            require(value['schema'] == 'mr3-peer-phase-request-v2' and value['epoch'] == self.epoch
                    and type(value['request_id']) is str and value['request_id']
                    and value['operation'] in ('takeover', 'commit') and self.controlled,
                    'peer v2 request identity')
            require(self.pending is None and value['request_id'] not in self.requests
                    and clock <= integer(value['target_time_ns'], 'peer target')
                    and (self.last_clock is None or value['target_time_ns'] > self.last_clock),
                    'peer overlapping/late/repeated request')
            if value['operation'] == 'commit':
                state = value['state_commit']
                actual = [p for p in self.information.ack_publications
                          if p['start'] <= wall and canonical(p['ack']) == canonical(state)]
                require(actual and state['ok'] is True and state['operation'] == 'commit'
                        and state['request_id'] == value['request_id']
                        and state['clock_ns'] == state['target_time_ns'] == value['target_time_ns'],
                        'peer request lacks earlier actual state ACK')
            self.requests[value['request_id']] = copy.deepcopy(value)
            self.pending = copy.deepcopy(value); self.matched = self.outputs = None
        elif kind == 'inputs_matched':
            equal(value['request'], self.pending, 'peer match not current request')
            require(clock == self.pending['target_time_ns'] and self.pending['operation'] == 'commit'
                    and self.matched is None, 'peer match phase clock')
            self.matched = self.match(self.pending)
            equal(value['inputs'], self.matched, 'peer matched refs differ from actual callback prefix')
        elif kind in ('obstacles_published', 'warmup_obstacles_published'):
            self.publications(value['publications'], wall)
            if kind == 'obstacles_published':
                require(self.pending is not None and self.matched is not None and self.outputs is None
                        and value['request_id'] == self.pending['request_id']
                        and clock == self.pending['target_time_ns'], 'peer obstacles lack committed input match')
                self.outputs = copy.deepcopy(value['publications'])
            else:
                require(not self.controlled, 'automatic obstacles after takeover')
        elif kind in ('ack_published', 'cached_ack_published'):
            ack = value['ack']; identifier = ack['request_id']
            start = integer(value['publish_started_wall_monotonic_ns'], 'peer ACK start', 1)
            require(start <= integer(value['publish_completed_wall_monotonic_ns'], 'peer ACK end', 1) <= wall,
                    'peer ACK publication window')
            require(ack['schema'] == 'mr3-peer-phase-ack-v2' and ack['epoch'] == self.epoch
                    and ack['ok'] is True and ack['safety_contract'] == CONTRACT, 'failed/foreign peer ACK')
            if kind == 'cached_ack_published':
                equal(ack, self.acks.get(identifier), 'cached peer ACK not exact actual previous ACK')
                return
            require(self.pending is not None and identifier == self.pending['request_id']
                    and clock == ack['clock_ns'] == ack['target_time_ns'] == self.pending['target_time_ns']
                    and ack['operation'] == self.pending['operation'], 'peer ACK pending clock/identity')
            if ack['operation'] == 'takeover':
                require(ack['scope'] == 'automatic_obstacle_timer_disabled'
                        and ack['intent_refs'] is None and ack['safety_table_sha256'] is None,
                        'peer takeover cannot claim consumption')
            else:
                require(self.outputs is not None and ack['scope'] == 'actual_obstacle_publish_calls_returned'
                        and type(ack['commit_sequence']) is int
                        and ack['commit_sequence'] == self.counts['commits'] + 1, 'peer commit publication sequence')
                equal(ack['inputs'], self.matched, 'peer ACK changed actual matched inputs')
                equal(ack['publications'], self.outputs, 'peer ACK changed actual obstacle calls')
                equal(ack['state_commit'], self.pending['state_commit'], 'peer ACK changed full state commit')
                state = self.pending['state_commit']
                require(ack['bundle_sha256'] == state['bundle_sha256']
                        and ack['state_sequence'] == state['state_sequence']
                        and ack['obstacle_publication_sha256'] == sha(self.outputs), 'peer ACK full publication SHA')
                for key, evidence in self.matched['safety'].items():
                    equal(ack[key], evidence, 'peer ACK complete consumed safety table')
                require(max(p['publish_completed_wall_monotonic_ns'] for p in self.outputs) <= start,
                        'peer ACK precedes actual obstacle publish return')
                self.last_clock = clock; self.counts['commits'] += 1
            self.acks[identifier] = copy.deepcopy(ack)
            self.ack_publications.append({'ack': copy.deepcopy(ack), 'start': start})
            self.pending = self.matched = self.outputs = None
        else:
            raise ValueError('unknown/failing peer record ' + str(kind))

    def finish(self):
        require(self.configured and self.controlled and self.pending is None and self.counts['commits'] > 0
                and all(self.sequences[k] for k in self.cache), 'missing/incomplete peer delivery availability')
        return dict(self.counts)


def validate_applied(value, epoch, robot, base):
    fields(value, ('schema', 'epoch', 'robot', 'source_clock_ns', 'actuation_sequence',
                   'cmd_seq', 'dt_ns', 'target', 'pairs'), 'actual applied receipt')
    identity(value, 'mr3-drive-applied-v1', epoch, robot)
    source = integer(value['source_clock_ns'], 'applied source')
    integer(value['actuation_sequence'], 'actuation sequence', 1)
    integer(value['cmd_seq'], 'native command sequence', 1)
    integer(value['dt_ns'], 'native dt', 1)
    target(value['target'], epoch, robot, source)
    require(type(value['pairs']) is list and value['pairs'], 'actual applied wheel pairs')
    for index, pair in enumerate(value['pairs']):
        fields(pair, ('pair_index', 'current_rim_mps', 'desired_rim_mps', 'applied_rim_mps',
                      'alpha', 'max_acceleration_mps2'), 'applied pair')
        require(type(pair['pair_index']) is int and pair['pair_index'] == index, 'complete applied pair order')
        for key in ('current_rim_mps', 'desired_rim_mps', 'applied_rim_mps'):
            require(type(pair[key]) is list and len(pair[key]) == 2, 'applied rim pair shape')
            for component in pair[key]:
                number(component)
        require(0 <= number(pair['alpha']) <= 1 and number(pair['max_acceleration_mps2']) > 0,
                'applied pair limiter fields')


class _AckPublicationIndex:
    """Exact multi-value lookup along a validated nondecreasing wall prefix.

    Rows stay in publisher-list order. Unreached tails and not-yet-causal ACK
    bodies stay unencoded, preserving the original any() short circuit/errors.
    Previously validated publications are immutable and retained by reference.
    """
    def __init__(self, publications):
        self.publications = publications
        self.by_payload = {}
        self.future = []
        self.position = 0
        self.first = None

    def contains(self, ack, wall):
        key = None

        def remember(position, publication):
            nonlocal key
            payload = canonical(publication['ack'])
            if key is None:
                key = canonical(ack)
            matches = self.by_payload.setdefault(payload, [])
            matches.append((position, publication))
            matches.sort(key=lambda item: item[0])
            self.first = position if self.first is None else min(self.first, position)
            return payload == key

        def pending_before(limit):
            offset = 0
            while offset < len(self.future) and self.future[offset][0] < limit:
                position, publication = self.future[offset]
                if publication['start'] <= wall:
                    matched = remember(position, publication)
                    self.future.pop(offset)
                    if matched:
                        return True
                else:
                    offset += 1
            return False

        # A formerly-future row before the first remembered publication must
        # be inspected before encoding this query, including malformed bodies.
        if pending_before(self.position if self.first is None else self.first):
            return True
        if self.first is not None and key is None:
            key = canonical(ack)
        matches = self.by_payload.get(key, ()) if key is not None else ()
        if pending_before(matches[0][0] if matches else self.position):
            return True
        if matches:
            return True
        while self.position < len(self.publications):
            position = self.position
            publication = self.publications[position]
            if publication['start'] <= wall:
                matched = remember(position, publication)
            else:
                self.future.append((position, publication))
                matched = False
            self.position += 1
            if matched:
                return True
        return False


def audit_motion(rows, information, peer, epoch, base):
    counts = Counter(); current = None; authority_profile = None
    published = {name: {} for name in ROBOTS}
    owners_by_target = {name: {} for name in ROBOTS}
    raw = {name: {} for name in ROBOTS}; raw_sequences = Counter()
    applied = {name: {} for name in ROBOTS}; applied_last = Counter()
    applied_target_keys = {name: {} for name in ROBOTS}
    driver_gids, actual_ingress, decisions = {}, {}, {}
    control_acks, control_ack_publications = {}, set()
    deps = {'state': {}, 'peer': {}}
    dependency_publications = {}
    pending_state_ingress = None
    state_gid = None
    known_other = {'own_tf', 'raw_request', 'actual_cmd_vel', 'output_completed', 'release',
        'stop_request', 'terminal', 'output_observer_wait', 'control_request', 'control_abandoned',
        'reach_release_ready'}
    for row, clock, wall in prefix(rows, 'mr3-motion-safety-v1', epoch, motion=True):
        kind, value = row['kind'], row['payload']; counts[kind] += 1
        if pending_state_ingress is not None:
            require(kind == 'received_states', 'unclosed actual state ingress callback')
        if kind == 'configuration':
            require(row['record_sequence'] == 1 and value['safety_contract'] == CONTRACT
                    and value['controlled_execution'] is True, 'explicit stepped reach motion configuration')
            authority_profile = selected_motion_authority_profile(value)
        elif kind == 'own_odom':
            name = value['robot']; require(name in ROBOTS, 'own raw robot')
            raw_sequences[name] += 1
            require(type(value['input_sequence']) is int and value['input_sequence'] == raw_sequences[name],
                    'motion own raw callback sequence gap')
            source = odometry(value['message'], base)
            previous = raw[name].get(source)
            require(previous is None or canonical(previous) == canonical(value['message']), 'conflicting own raw source')
            raw[name][source] = copy.deepcopy(value['message'])
        elif kind == 'reach_driver_ingress':
            name, feed, message = value['robot'], value['kind'], value['message']
            require(name in ROBOTS and feed in ('calibration', 'applied', 'storage'), 'native reach ingress kind/robot')
            suffix = {'calibration': 'odometry_calibration', 'applied': 'applied', 'storage': 'status'}[feed]
            key = name, feed
            gid = graph(value['publisher_identity'], f'/{name}/mr3_drive/{suffix}',
                        'turtlebot3_diff_drive', '/' + name, driver_gids.get(key))
            driver_gids[key] = gid
            equal(base.parse(value['raw_json']), message, 'native feed differs from actual String bytes')
            require(message['epoch'] == epoch, 'foreign native reach packet')
            if feed == 'applied':
                validate_applied(message, epoch, name, base)
                seq = message['actuation_sequence']
                require(seq > applied_last[name], 'actual applied receipt regressed/duplicated')
                applied_last[name] = seq
                command = message['target']
                command_key = canonical(command)
                owners = owners_by_target[name].get(command_key, ())
                require(owners, 'actual applied target has no earlier real owner publication')
                applied[name][seq] = copy.deepcopy(message)
                applied_target_keys[name][seq] = command_key
            elif feed == 'calibration':
                validate_calibration(message, epoch, name, base)
            else:
                # Storage is not actuation and supplies no N credit in this role.
                require(type(message) is dict and message.get('robot') == name, 'storage identity')
        elif kind == 'reach_intent_publish':
            name, intent = value['robot'], value['intent']
            validate_intent(intent, epoch, name, base, clock)
            seq = intent['intent_sequence']
            require(seq == len(published[name]) + 1 and value['payload_sha256'] == sha(intent)
                    and value['scope'] == 'actual_publisher_call_returned_not_delivery', 'owner intent complete publication prefix')
            start = integer(value['publish_started_wall_monotonic_ns'], 'intent publish start', 1)
            require(start <= integer(value['publish_completed_wall_monotonic_ns'], 'intent publish end', 1) <= wall,
                    'owner intent actual publication window')
            role, lineage, anchor = intent['role'], intent['lineage'], intent['anchor']
            previous = published[name].get(seq-1)
            if previous is not None and previous['intent']['role'] == 'STOP':
                require(role == 'STOP', 'STOP is permanent')
            if anchor is not None:
                equal(raw[name].get(anchor['source_clock_ns']), anchor['odometry'],
                      'anchor is not actual prior own raw callback')
            if role in ('D', 'X', 'N'):
                anchor_seq = lineage['anchor_intent_sequence']
                source_intent = intent if anchor_seq == seq and role == 'D' else (
                    published[name].get(anchor_seq) or {}).get('intent')
                require(source_intent is not None and source_intent['role'] == 'D', 'missing actual D anchor intent')
                equal(source_intent['anchor'], anchor, 'active immutable anchor lineage')
            if role in ('X', 'N'):
                transition_seq = lineage['transition_intent_sequence']
                transition = intent if transition_seq == seq and role == 'X' else (
                    published[name].get(transition_seq) or {}).get('intent')
                require(transition is not None and transition['role'] == 'X'
                        and transition['target']['linear_x'] == 0, 'missing actual zero X preannouncement')
                equal(transition['anchor'], anchor, 'transition immutable anchor')
                equal(transition['admitted_signs'], intent['admitted_signs'], 'signed family changed since announcement')
            if role == 'N':
                require(lineage['anchor_intent_sequence'] < seq and lineage['transition_intent_sequence'] < seq,
                        'N lineage is not strictly prior')
                actual = applied[name].get(lineage['actuation_sequence'])
                require(actual is not None and actual['source_clock_ns'] == lineage['actuation_source_clock_ns']
                        and actual['cmd_seq'] == lineage['cmd_seq'], 'N lacks actual earlier applied receipt')
                require(lineage['causal_source_clock_ns'] in raw[name], 'N lacks strict later actual own raw callback')
                takeovers = [a for a in applied[name].values()
                             if a['target']['clock_ns'] > transition['source_clock_ns']
                             and a['target']['linear_x'] != 0
                             and (1 if a['target']['linear_x'] > 0 else -1) in intent['admitted_signs']
                             and a['source_clock_ns'] < lineage['causal_source_clock_ns']]
                require(takeovers, 'N cannot be established from a stored-only or zero-only handoff')
                delivered_takeovers = []
                for applied_target in takeovers:
                    owners = owners_by_target[name].get(
                        applied_target_keys[name][applied_target['actuation_sequence']], ())
                    for owner in owners:
                        delivered = owner.get('_received_self')
                        if (delivered is not None and delivered['role'] in ('X', 'N')
                                and delivered['lineage']['transition_intent_sequence'] == lineage['transition_intent_sequence']
                                and canonical(delivered['anchor']) == canonical(anchor)
                                and canonical(delivered['admitted_signs']) == canonical(intent['admitted_signs'])):
                            delivered_takeovers.append(applied_target)
                require(delivered_takeovers, 'N lacks actual prior delivered X before nonzero owner publication')
            if role == 'STOP':
                prior = published[name].get(lineage['previous_intent_sequence'])
                require(prior is not None and prior['intent']['role'] == lineage['previous_role'], 'STOP prior actual intent')
                equal(prior['intent']['anchor'], anchor, 'STOP changed protected anchor')
                equal(prior['intent']['admitted_signs'], intent['admitted_signs'], 'STOP changed protected signs')
            publication = copy.deepcopy(value)
            publication['_received_self'] = (copy.deepcopy(next(r['safety']['intent']
                for r in current['robots'] if r['name'] == name)) if current else None)
            published[name][seq] = publication
            if publication['intent']['target'] is not None:
                target_key = canonical(publication['intent']['target'])
                owners_by_target[name].setdefault(target_key, []).append(publication)
            actual_ingress[name, seq] = publication
        elif kind == 'reach_state_ingress':
            fields(value, ('message', 'raw_json', 'publisher_identity'), 'motion actual state ingress')
            equal(base.parse(value['raw_json']), value['message'], 'motion bundle differs from actual String bytes')
            state_gid = graph(value['publisher_identity'], '/mr3/received/states', 'mr3_information', '/', state_gid)
            bundle_evidence(value['message'], epoch, base)
            pending_state_ingress = copy.deepcopy(value['message'])
        elif kind == 'received_states':
            require(pending_state_ingress is not None, 'motion received state lacks actual graph-bound ingress')
            equal(value, pending_state_ingress, 'motion selected state differs from actual ingress')
            pending_state_ingress = None
            bundle_evidence(value, epoch, base)
            incoming_bundle_sha256 = sha(value) if information.complete_publications else None
            matches = [p for p in information.complete_publications
                       if p['message_sha256'] == incoming_bundle_sha256 and p['publish_started_wall_monotonic_ns'] <= wall]
            require(matches and (current is None or value['sequence'] > current['sequence']),
                    'motion received bundle absent from real publication/sequence regressed')
            equal(value, matches[-1]['message'], 'motion changed complete actual received bundle')
            current = copy.deepcopy(value)
        elif kind == 'reach_decision':
            name = value['robot']; require(name in ROBOTS, 'reach decision robot')
            require(type(value['clock_ns']) is int and value['clock_ns'] == clock, 'reach decision clock')
            received = {r['name']: r for r in current['robots']} if current else {}
            equal(value['received_peers'], {n: received.get(n) for n in ROBOTS if n != name},
                  'guard peers differ from actual received full table')
            consumed = value['safety_table_sha256']
            if consumed is not None:
                require(current is not None and current['safety_table_sha256'] == consumed,
                        'guard consumed a different complete frozen table')
                bundle_evidence(current, epoch, base, clock)
            intent = value['intent']; actual = published[name].get(intent['intent_sequence'])
            require(actual is not None, 'guard intent not actually published in prior local prefix')
            equal(intent, actual['intent'], 'guard intent differs from actual publication')
            key = clock, value.get('phase_kind', 'normal')
            decisions.setdefault(key, []).append((name, consumed, copy.deepcopy(intent)))
        elif kind == 'control_dependency':
            component, ack = value['component'], value['value']
            require(component in deps, 'control dependency component')
            if component not in dependency_publications:
                sources = information.ack_publications if component == 'state' else peer.ack_publications
                dependency_publications[component] = _AckPublicationIndex(sources)
            require(dependency_publications[component].contains(ack, wall),
                    'motion dependency not actual earlier published complete ACK')
            deps[component][ack['request_id']] = copy.deepcopy(ack)
        elif kind == 'control_commit':
            request = value['request']; identifier = request['request_id']
            require(request['schema'] == 'mr3-motion-control-request-v2' and request['operation'] == 'commit'
                    and request['target_time_ns'] == clock, 'motion actual commit v2 identity')
            for component in ('state', 'peer'):
                equal(request[component + '_commit'], deps[component].get(identifier),
                      'motion commit used undeclared/late actual dependency')
            table = request['state_commit']['safety_table_sha256']
            equal(request['peer_commit']['safety_table_sha256'], table, 'motion dependencies differ in table')
            group = decisions.get((clock, 'normal'), [])
            require(len(group) == 3 and {g[0] for g in group} == set(ROBOTS)
                    and all(g[1] == table for g in group), 'three logical guards did not consume the same full frozen table')
            counts['full_three_guard_commits'] += 1
        elif kind == 'control_ack':
            require(value['ok'] is True, 'failed actual motion control ACK')
            status = value['status']
            require(status['schema'] == 'mr3-motion-safety-status-v2' and status['safety_contract'] == CONTRACT,
                    'motion status explicit reach version')
            target_clock = value['target_time_ns']
            group = decisions.get((target_clock, status.get('phase_kind', 'normal')), [])
            require(len(group) == 3 and {g[0] for g in group} == set(ROBOTS), 'status lacks three actual guard decisions')
            equal(status['intent_refs'], intent_refs({n: {'intent': i} for n, _, i in group}),
                  'status new refs differ from actual new owner publications')
            require(all(table == status['safety_table_sha256'] for _, table, _ in group),
                    'status consumed table differs from actual guard decisions')
            equal(value['intent_refs'], status['intent_refs'], 'control ACK new owner refs')
            equal(value['safety_table_sha256'], status['safety_table_sha256'], 'control ACK consumed old table')
            identifier = value['request_id']
            require(identifier not in control_acks, 'repeated new control ACK')
            control_acks[identifier] = copy.deepcopy(value)
        elif kind in ('control_ack_published', 'control_cached_ack_published'):
            ack = value['ack']; identifier = ack['request_id']
            equal(ack, control_acks.get(identifier), 'motion published ACK differs from actual completed status')
            require(integer(value['publish_started_wall_monotonic_ns'], 'motion ACK start', 1)
                    <= integer(value['publish_completed_wall_monotonic_ns'], 'motion ACK end', 1) <= wall,
                    'motion ACK actual publication window')
            if kind == 'control_ack_published':
                require(identifier not in control_ack_publications, 'repeated uncached motion ACK publication')
                control_ack_publications.add(identifier)
            else:
                require(identifier in control_ack_publications, 'cached motion ACK lacks original actual publication')
        elif kind in ('authority_configuration','authority_callback','authority_ack_publication'):
            # This role verifies information delivery. Complete permission,
            # witness and owner replay remains mandatory in FIFO/runtime.
            require(authority_profile is not None and value.get('robot') in ROBOTS,
                    'authority event lacks declared current profile/robot')
            if kind=='authority_configuration':
                require(value.get('motion_authority_profile')==authority_profile,
                        'authority event/configuration profile differs')
            else:
                message=value.get('message')
                require(type(message) is dict and message.get('epoch')==epoch
                        and message.get('robot')==value['robot'], 'authority journal context differs')
                equal(base.parse(value['raw_json']),message,'authority journal raw bytes differ')
                if kind=='authority_callback':
                    require(message.get('schema')=='mr3-motion-authority-v1', 'authority packet schema differs')
                    result=value.get('result')
                    require(type(result) is dict and (result.get('accepted') is True
                        or result.get('reason') in ('stale_authority','retired_owner')),
                        'failed authority callback retained by information role')
                else:
                    require(message.get('schema')=='mr3-motion-authority-ack-wire-v1'
                            and message.get('profile')==authority_profile,
                            'authority ACK profile differs')
        elif kind in known_other:
            pass  # Other independently required roles own command/body/closure predicates.
        else:
            raise ValueError('unknown/failing reach motion record ' + str(kind))
    require(counts['configuration'] == 1 and counts['received_states'] > 0
            and counts['full_three_guard_commits'] > 0 and all(published[n] for n in ROBOTS),
            'missing actual owner/received/three-guard commit availability')
    require(pending_state_ingress is None, 'unfinished actual state ingress')
    require(control_acks and set(control_acks) == control_ack_publications,
            'missing actual motion ACK publication return')
    for ingress in information.actual_intent_ingress:
        intent = ingress['value']; publication = actual_ingress.get((intent['robot'], intent['intent_sequence']))
        require(publication is not None, 'Information intent callback has no real owner publication')
        equal(publication['intent'], intent, 'Information ingress differs from complete actual owner intent')
        require(publication['publish_started_wall_monotonic_ns'] <= ingress['received_wall_monotonic_ns'],
                'Information intent receipt predates actual publication start')
    return dict(counts)


def audit_episode(directory, freeze=None):
    """Return a fail-closed report; no scientific consumer or native process runs."""
    directory = Path(directory)
    host, provenance = load_implementation()
    base = host.BASE
    inputs = base.Inputs()
    entry = Path(__file__).resolve(); entry_sha = hashlib.sha256(entry.read_bytes()).hexdigest()
    authority_helper = Path(inspect.getsourcefile(selected_motion_authority_profile)).resolve()
    authority_helper_sha = hashlib.sha256(authority_helper.read_bytes()).hexdigest()
    result = {'schema': 'mr3-reach-information-review-v1', 'episode': str(directory),
        'safety_contract': CONTRACT, 'passed': False, 'errors': [], 'inputs': inputs.bindings,
        'implementation': {'path': str(entry), 'sha256': entry_sha,
                           'independent_measurement_oracle': provenance,
                           'authority_profile_helper': {'path':str(authority_helper),'sha256':authority_helper_sha}},
        'role': 'reach_information_delivery_necessary_evidence',
        'historical_38_role_qualification': False, 'native_admission': False,
        'limitations': [
            'Recorded callbacks establish their own prefix, not absence of middleware loss.',
            'Publisher identity is graph_at_callback, not packet GID authentication or P3 isolation.',
            'One central ideal delivery table feeds three logical guards; these are not three network endpoints.',
            'Map computation, actor projection, obstacle geometry, reach geometry, physical metric calibration, '
            'HOLD/D qualification, body models, native closure and task/training validity require separate roles.',
            'Calibration coefficients are source-bound declarations, not an independent proof of physical heading or compiler rounding.']}
    try:
        metadata = base.parse(inputs.read(directory, 'metadata.json'))
        require(type(metadata['epoch']) is str and metadata['epoch'], 'metadata epoch')
        require(type(metadata['freeze']) is str and len(metadata['freeze']) == 40, 'metadata exact freeze')
        require(freeze is None or metadata['freeze'] == freeze, 'metadata freeze mismatch')
        epoch = metadata['epoch']; result.update(epoch=epoch, freeze=metadata['freeze'])
        inputs.read(directory, 'summary.json')  # Bind the supplied episode, without inventing closure credit.
        ledger = inputs.rows(directory, 'information_states.jsonl')
        peer_rows = inputs.rows(directory, 'peer_phase.jsonl')
        motion_rows = inputs.rows(directory, 'motion_safety.jsonl')
        information = information_replay_class(host)(epoch)
        for row, _, _ in prefix(ledger, 'mr3-information-state-audit-v2', epoch):
            try:
                information.record(row)
            except (ValueError, KeyError, TypeError, OverflowError) as error:
                raise ValueError('information record ' + str(row['record_sequence']) + ': ' + str(error)) from error
        result['information_counts'] = information.finish()
        peer = PeerReplay(epoch, base, information)
        for row, clock, wall in prefix(peer_rows, 'mr3-peer-phase-audit-v2', epoch):
            try:
                peer.record(row, clock, wall)
            except (ValueError, KeyError, TypeError, OverflowError) as error:
                raise ValueError('peer record ' + str(row['record_sequence']) + ': ' + str(error)) from error
        result['peer_counts'] = peer.finish()
        result['motion_counts'] = audit_motion(motion_rows, information, peer, epoch, base)
        result['passed'] = True
    except (ValueError, KeyError, TypeError, OverflowError, OSError) as error:
        result['errors'].append(str(error))
    try:
        inputs.verify()
        require(hashlib.sha256(entry.read_bytes()).hexdigest() == entry_sha, 'reader source changed during audit')
        require(hashlib.sha256(authority_helper.read_bytes()).hexdigest()==authority_helper_sha,
                'authority profile helper changed during information audit')
        for binding in [provenance['effective_entry'], *provenance['unchanged_original_sources']]:
            require(hashlib.sha256(Path(binding['path']).read_bytes()).hexdigest() == binding['sha256'],
                    'independent measurement helper changed during audit')
    except (ValueError, OSError) as error:
        result['passed'] = False; result['errors'].append(str(error))
    return result


def audit(directory, expected_freeze=None):
    """Discover every EP/RUN attempt without changing per-episode predicates."""
    from .audit_reach_runtime import audit_episode_set
    result = audit_episode_set(directory, expected_freeze, audit_episode,
                               schema='mr3-reach-information-run-review-v1')
    result.update(historical_38_role_qualification=False, native_admission=False)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--freeze', help='Optional exact metadata freeze requirement')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    require(not args.output.exists(), 'exclusive new output required')
    from .audit_reach_runtime import run_workers
    result = (audit(args.directory, args.freeze) if run_workers(args.directory)
              else audit_episode(args.directory, args.freeze))
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'passed': result['passed'], 'output': str(args.output)}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
