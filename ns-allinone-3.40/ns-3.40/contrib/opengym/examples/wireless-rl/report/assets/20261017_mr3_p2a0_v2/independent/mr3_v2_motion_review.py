"""Independent read-only motion/native evidence consumer; no production imports."""
from collections import deque
import gzip
import hashlib
import json
import math


NAMES = ('tb1', 'tb2', 'tb3')


def load_rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def ns(value):
    return round(value * 1e9)


def stamp(header):
    value = header['stamp']
    return value['sec'] + value['nanosec'] / 1e9


def yaw(q):
    return math.atan2(2 * (q['w'] * q['z'] + q['x'] * q['y']),
                      1 - 2 * (q['y'] ** 2 + q['z'] ** 2))


def own(name, source, sequence, epoch):
    if not all(key in source for key in ('odom', 'tf')):
        return None
    odom, tf = source['odom'], source['tf']
    if (odom['header']['frame_id'].lstrip('/') != 'odom'
            or odom['child_frame_id'].lstrip('/') not in ('base_link', 'base_footprint')):
        return None
    orientation, rotation = odom['pose']['pose']['orientation'], tf['transform']['rotation']
    for quaternion in (orientation, rotation):
        values = [quaternion[key] for key in ('x', 'y', 'z', 'w')]
        if (any(type(v) not in (int, float) or not math.isfinite(v) for v in values)
                or abs(sum(v * v for v in values) - 1.) > .01):
            return None
    angle = yaw(rotation)
    point, translation = odom['pose']['pose']['position'], tf['transform']['translation']
    odom_time, validity = stamp(odom['header']), stamp(tf['header'])
    tf_time = validity - .2
    return {'robot': name, 'name': name, 'epoch': epoch, 'valid': True,
            'x': translation['x'] + math.cos(angle) * point['x'] - math.sin(angle) * point['y'],
            'y': translation['y'] + math.sin(angle) * point['x'] + math.cos(angle) * point['y'],
            'yaw': math.atan2(math.sin(angle + yaw(orientation)),
                              math.cos(angle + yaw(orientation))),
            'v': odom['twist']['twist']['linear']['x'],
            'w': odom['twist']['twist']['angular']['z'],
            'odom_source_stamp': odom_time, 'tf_source_stamp': tf_time,
            'tf_validity_stamp': validity, 'tf_validity_lead_sec': .2,
            'source_stamp': min(odom_time, tf_time),
            'input_sequences': {key: sequence[key] for key in ('odom', 'tf')}}


def healthy(state, clock, epoch):
    if not isinstance(state, dict) or state.get('valid') is not True or state.get('epoch') != epoch:
        return False
    if any(type(state.get(key)) not in (int, float) or not math.isfinite(state[key])
           for key in ('x', 'y', 'yaw', 'v', 'w', 'source_stamp')):
        return False
    stamps = [state['source_stamp']] + [state[key] for key in ('odom_source_stamp', 'tf_source_stamp')
                                      if key in state]
    return (all(type(t) in (int, float) and math.isfinite(t) and t > 0
                and 0 <= clock - ns(t) <= 500000000 for t in stamps)
            and abs(state['v']) <= .30 and abs(state['w']) <= 1.2)


def review(directory, meta, trans, require):
    label, epoch = directory.name, meta['epoch']
    topology = json.loads((directory / 'motion_topology.json').read_text())
    records = load_rows(directory / 'motion_safety.jsonl')
    phases = load_rows(directory / 'motion_phase_worker.jsonl')
    physics = load_rows(directory / 'physics.jsonl')
    release = trans[0]['info']['release_time_ns']
    sources = {name: {} for name in NAMES}
    sequences = {name: {'odom': 0, 'tf': 0, 'request': 0, 'decision': 0} for name in NAMES}
    requests, peers, decisions = {}, {}, {}
    pending = {name: deque() for name in NAMES}
    statistics = {name: {'decisions': 0, 'actual': 0, 'nonzero_requests': 0,
                         'nonzero_outputs': 0, 'max_abs_v': 0., 'max_abs_w': 0.}
                  for name in NAMES}
    for value in statistics.values():
        value.update(max_planar_speed_norm=0., max_abs_lateral_v=0., max_abs_vertical_v=0.,
                     max_angular_speed_norm=0., max_source_chord_speed=0.,
                     duplicate_odom_source_count=0, older_odom_source_count=0)
    previous_odom = {}
    last_wall, last_clock, released = -1, -1, False
    peer_sequence = -1
    identities = {}
    for name in NAMES:
        topic = '/' + name + '/cmd_vel'
        entries = topology['endpoints'][topic]
        require(len(entries) == 1 and entries[0]['namespace'] == '/'
                and entries[0]['node'] == 'motion_safety'
                and entries[0]['topic_type'] == 'geometry_msgs/msg/Twist', label + ': output topology')
        identities[name] = entries[0]
    for index, row in enumerate(records, 1):
        clock, wall = ns(row['sim_time_sec']), row['wall_monotonic_ns']
        require(row['epoch'] == epoch and row['record_sequence'] == index
                and clock >= last_clock and wall >= last_wall, label + ': motion record order')
        last_clock, last_wall = clock, wall
        kind, value = row['kind'], row['payload']
        if kind in ('own_odom', 'own_tf'):
            name, key = value['robot'], 'odom' if kind == 'own_odom' else 'tf'
            require(value['input_sequence'] == sequences[name][key] + 1, label + ': own input sequence')
            sequences[name][key] += 1
            sources[name][key] = value['message']
            if key == 'odom':
                stats, twist = statistics[name], value['message']['twist']['twist']
                stats['max_abs_v'] = max(stats['max_abs_v'], abs(twist['linear']['x']))
                stats['max_abs_w'] = max(stats['max_abs_w'], abs(twist['angular']['z']))
                stats['max_planar_speed_norm'] = max(stats['max_planar_speed_norm'],
                    math.hypot(twist['linear']['x'], twist['linear']['y']))
                stats['max_abs_lateral_v'] = max(stats['max_abs_lateral_v'],
                                                abs(twist['linear']['y']))
                stats['max_abs_vertical_v'] = max(stats['max_abs_vertical_v'],
                                                 abs(twist['linear']['z']))
                stats['max_angular_speed_norm'] = max(stats['max_angular_speed_norm'],
                    math.sqrt(sum(twist['angular'][axis] ** 2 for axis in ('x', 'y', 'z'))))
                source_stamp = ns(stamp(value['message']['header']))
                point = value['message']['pose']['pose']['position']
                old = previous_odom.get(name)
                if old is not None and source_stamp > old[0]:
                    speed = math.hypot(point['x'] - old[1]['x'], point['y'] - old[1]['y'])
                    speed /= (source_stamp - old[0]) / 1e9
                    stats['max_source_chord_speed'] = max(stats['max_source_chord_speed'], speed)
                elif old is not None:
                    field = ('duplicate_odom_source_count' if source_stamp == old[0]
                             else 'older_odom_source_count')
                    stats[field] += 1
                if old is None or source_stamp > old[0]:
                    previous_odom[name] = source_stamp, point
        elif kind == 'received_states':
            require(value['epoch'] == epoch and value['sequence'] > peer_sequence,
                    label + ': received peer epoch/sequence')
            peer_sequence = value['sequence']
            peers = {r['name']: r for r in value['robots']}
            require(set(peers) == set(NAMES) and len(value['robots']) == 3, label + ': peer robot set')
        elif kind == 'invalid_received_states':
            peers = {}
        elif kind == 'raw_request':
            name, request = value['robot'], value['request']
            require(request['sequence'] == sequences[name]['request'] + 1
                    and ns(request['received_stamp']) == clock, label + ': request callback sequence')
            sequences[name]['request'] += 1
            requests[name] = request
        elif kind == 'release':
            require(not released and ns(value['stamp']) == release, label + ': release stamp')
            released = True
        elif kind == 'decision':
            name, sequence = value['robot'], value['decision_sequence']
            require(sequence == sequences[name]['decision'] + 1 and value['clock_ns'] == clock,
                    label + ': exact decision clock/sequence')
            sequences[name]['decision'] += 1
            own_state = own(name, sources[name], sequences[name], epoch)
            received = {other: peers.get(other) for other in NAMES if other != name}
            require(value['own_state'] == own_state, label + ': own estimate not original raw odom/TF')
            require(value['received_peers'] == received, label + ': peers bypass received inputs')
            require(value['request'] == requests.get(name), label + ': request bypass callback')
            require(value['started'] is released, label + ': release decision causality')
            if value['ready']:
                require(all(healthy(own(n, sources[n], sequences[n], epoch), clock, epoch)
                            and healthy(peers.get(n), clock, epoch) for n in NAMES),
                        label + ': ready used unhealthy estimated source')
            decision = value['decision']
            output = decision['output']
            request = value['request']
            require(len(output) == 2 and all(type(v) in (int, float) and math.isfinite(v) for v in output)
                    and abs(output[0]) <= .26 and abs(output[1]) <= 1., label + ': final command bounds')
            if decision['allow']:
                require(request is not None and request['supported']
                        and output == [request['v'], request['w']], label + ': allowed command changed')
            else:
                require(output == [0., 0.], label + ': rejected command not zero')
            if not released or not value['ready']:
                require(output == [0., 0.], label + ': prerelease/unhealthy command moved')
            key = name, sequence
            decisions[key] = {'clock': clock, 'wall': wall, 'ready': value['ready']}
            pending[name].append((key, output))
            statistics[name]['decisions'] += 1
            statistics[name]['nonzero_outputs'] += bool(any(output))
            statistics[name]['nonzero_requests'] += bool(request and request['supported']
                                                        and (request['v'] or request['w']))
        elif kind == 'actual_cmd_vel':
            name, identity, twist = value['robot'], value['publisher_identity'], value['twist']
            require(identity['scope'] == 'graph_at_callback' and identity['valid'] is True
                    and identity['topic'] == '/' + name + '/cmd_vel'
                    and identity['endpoints'] == [identities[name]], label + ': actual output graph identity')
            require(bool(pending[name]), label + ': actual output without prior publication')
            if not pending[name]:
                continue
            key, expected = pending[name].popleft()
            require([twist['linear']['x'], twist['angular']['z']] == expected
                    and all(twist[axis][dim] == 0 for axis, dim in
                            (('linear', 'y'), ('linear', 'z'), ('angular', 'x'), ('angular', 'y')))
                    and value['observed_decision_sequence'] == key[1], label + ': actual output FIFO')
            decisions[key]['actual_wall'] = wall
            decisions[key]['actual_clock'] = clock
            statistics[name]['actual'] += 1
    require(released and all(not queue for queue in pending.values()), label + ': incomplete final output FIFO')
    received, consumed = {}, []
    for row in phases:
        ack = row['ack']
        clock = ack['clock_ns']
        require(row['epoch'] == ack['epoch'] == epoch
                and ack['completion_scope'] == 'publication_and_local_topic_receipt', label + ': ACK identity/scope')
        for name in NAMES:
            key = name, ack['decision_sequences'][name]
            require(key in decisions, label + ': ACK missing decision')
            if key not in decisions:
                continue
            d = decisions[key]
            require(d['clock'] == clock and d['ready'] == ack['ready']
                    and d.get('actual_wall', 10**30) <= row['wall_monotonic_ns'],
                    label + ': ACK before three observed same-clock outputs')
        if row['kind'] == 'ack_received':
            require(clock not in received or received[clock] == ack, label + ': changing same-clock ACK')
            received[clock] = ack
        elif row['kind'] == 'ack_consumed':
            require(received.get(clock) == ack
                    and row['worker_clock_ns'] == row['worker_physical_ns'] == clock
                    and (not consumed or clock > consumed[-1]), label + ': nonexact/missing consumed ACK')
            consumed.append(clock)
    require(consumed.count(release) == 1 and received[release]['ready'] is True,
            label + ': initial healthy observed output barrier')
    require([clock for clock in consumed if clock > release]
            == [r['end_time_ns'] for r in physics if r['end_time_ns'] > release],
            label + ': missing policy/cleanup motion barrier')
    costmaps, streams = {}, set()
    for row in load_rows(directory / 'costmaps.jsonl'):
        digest = row['payload_sha256']
        raw = gzip.decompress((directory / row['artifact']).read_bytes())
        payload = json.loads(raw)
        require(hashlib.sha256(raw).hexdigest() == digest and payload['header'] == row['source_header']
                and row['epoch'] == epoch, label + ': original costmap bytes binding')
        require(len(payload['data']) == payload['info']['width'] * payload['info']['height'],
                label + ': costmap shape')
        streams.add((row['robot'], row['layer']))
        costmaps[digest] = True
    require(streams == {(name, layer) for name in NAMES for layer in ('global', 'local')},
            label + ': six actual costmap streams')
    return {'raw_motion_records': len(records), 'robots': statistics,
            'release_ns': release, 'motion_acks_consumed': len(consumed),
            'costmap_streams': sorted(streams), 'unique_costmaps': len(costmaps),
            'scope': 'independent raw input reconstruction and observed graph/value FIFO; '
                     'no production geometry imports, no actuator consumption claim'}
