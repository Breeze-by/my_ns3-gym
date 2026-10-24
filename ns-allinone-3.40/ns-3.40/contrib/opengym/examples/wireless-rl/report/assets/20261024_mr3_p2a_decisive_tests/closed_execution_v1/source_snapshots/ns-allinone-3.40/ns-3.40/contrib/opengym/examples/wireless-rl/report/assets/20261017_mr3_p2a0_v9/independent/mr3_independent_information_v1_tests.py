"""Causal mutations for the independent information-state ledger reader."""

import copy
import importlib.util
import gzip
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest

PATH = Path(__file__).with_name('mr3_independent_information_v1.py')
SPEC = importlib.util.spec_from_file_location('information_consumer_under_test', PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def odom(stamp):
    return {'header': {'frame_id': 'odom', 'stamp': {'sec': stamp // 10**9,
                                                     'nanosec': stamp % 10**9}},
            'child_frame_id': 'base_footprint',
            'pose': {'pose': {'position': {'x': .1, 'y': .2, 'z': 0.},
                              'orientation': {'x': 0., 'y': 0., 'z': 0., 'w': 1.}},
                     'covariance': [0.] * 36},
            'twist': {'twist': {'linear': {'x': .02, 'y': 0., 'z': 0.},
                                'angular': {'x': 0., 'y': 0., 'z': .1}},
                      'covariance': [0.] * 36}}


def tf(stamp):
    return {'header': {'frame_id': 'map', 'stamp': {'sec': stamp // 10**9,
                                                    'nanosec': stamp % 10**9}},
            'child_frame_id': 'odom',
            'transform': {'translation': {'x': 1., 'y': 2., 'z': 0.},
                          'rotation': {'x': 0., 'y': 0., 'z': 0., 'w': 1.}}}


class MotionBindingTests(unittest.TestCase):
    def test_same_clock_late_bundle_cannot_explain_earlier_decision(self):
        epoch = 'synthetic-e'
        first = {'epoch': epoch, 'sequence': 1,
                 'robots': [{'name': r, 'source_stamp': 9.5} for r in MODULE.ROBOTS]}
        second = {'epoch': epoch, 'sequence': 2,
                  'robots': [{'name': r, 'source_stamp': 9.9} for r in MODULE.ROBOTS]}
        pubs = [{'message_sha256': MODULE.digest(first), 'wall_monotonic_ns': 1},
                {'message_sha256': MODULE.digest(second), 'wall_monotonic_ns': 3}]
        rows = [{'epoch': epoch, 'record_sequence': 1, 'kind': 'received_states',
                 'wall_monotonic_ns': 2, 'payload': first},
                {'epoch': epoch, 'record_sequence': 2, 'kind': 'decision',
                 'wall_monotonic_ns': 3,
                 'payload': {'robot': 'tb1', 'received_peers': {
                     r['name']: r for r in first['robots'] if r['name'] != 'tb1'}}},
                {'epoch': epoch, 'record_sequence': 3, 'kind': 'received_states',
                 'wall_monotonic_ns': 4, 'payload': second}]
        self.assertEqual(MODULE.audit_motion(rows, pubs, epoch)['decisions'], 1)
        bad = copy.deepcopy(rows)
        bad[1]['payload']['received_peers'] = {
            r['name']: r for r in second['robots'] if r['name'] != 'tb1'}
        with self.assertRaisesRegex(ValueError, 'late received'):
            MODULE.audit_motion(bad, pubs, epoch)

    def test_unpublished_or_future_publication_is_rejected(self):
        message = {'epoch': 'e', 'sequence': 1,
                   'robots': [{'name': r} for r in MODULE.ROBOTS]}
        rows = [{'epoch': 'e', 'record_sequence': 1, 'kind': 'received_states',
                 'wall_monotonic_ns': 5, 'payload': message}]
        for pubs in ([], [{'message_sha256': MODULE.digest(message), 'wall_monotonic_ns': 6}]):
            with self.subTest(pubs=pubs), self.assertRaises(ValueError):
                MODULE.audit_motion(rows, pubs, 'e')


def fixture():
    epoch = 'synthetic-epoch'
    rows, motion, current, ingresses, last_delivered = [], [], {}, {}, {}
    current_tf = {}

    def add(kind, value, clock):
        seq = len(rows) + 1
        row = {'schema': MODULE.SCHEMA, 'epoch': epoch, 'record_sequence': seq,
               'kind': kind, 'clock_ns': clock, 'wall_monotonic_ns': 1000 + seq * 10,
               'payload': value}
        rows.append(row)
        return row

    def ingress(kind, robot, raw, seq, clock):
        source = MODULE.header_ns(raw) - (200_000_000 if kind == 'tf' else 0)
        ingresses[kind, robot, seq] = raw
        return add(kind + '_ingress', {'robot': robot, 'input_sequence': seq,
                                       'source_ns': source, 'raw': raw,
                                       'raw_sha256': MODULE.digest(raw),
                                       'admission': 'queued', 'matched_input_sequence': None},
                   clock)

    add('configuration', {'tf_validity_lead_sec': .2, 'pending_limit': 256,
        'state_period_sec': .1, 'odom_pending_order': 'source_ns_ascending',
                          'tf_pending_order': 'accepted_header_ascending'}, 9_900_000_000)
    for robot in MODULE.ROBOTS:
        ingress('odom', robot, odom(9_900_000_000), 1, 9_900_000_000)
        ingress('tf', robot, tf(10_000_000_000), 1, 9_900_000_000)
    # The actual v8-shaped producer hazard: the newest callback is nineteen ms
    # ahead of this clock, while a previously received causal odometry exists.
    for robot in MODULE.ROBOTS:
        ingress('odom', robot, odom(10_019_000_000), 2, 10_000_000_000)
    for cycle, clock in enumerate((10_000_000_000, 10_020_000_000, 10_040_000_000), 1):
        if cycle == 2:
            for robot in MODULE.ROBOTS:
                ingress('tf', robot, tf(10_240_000_000), 2, clock)
        if cycle in (1, 3):
            for robot in MODULE.ROBOTS:
                current_tf[robot] = 1 if cycle == 1 else 2
                add('tf_promote', {'robot': robot,
                    'selected_input_sequence': current_tf[robot],
                                   'pending_tf_input_sequences': []}, clock)
        for robot in MODULE.ROBOTS:
            oid, tid = (1 if cycle == 1 else 2), current_tf[robot]
            original_odom, original_tf = ingresses['odom', robot, oid], ingresses['tf', robot, tid]
            osource = MODULE.header_ns(original_odom)
            tsource = MODULE.header_ns(original_tf) - 200_000_000
            add('state_selection', {'cycle_id': cycle, 'robot': robot,
                'odom_input_sequence': oid, 'tf_input_sequence': tid,
                                    'odom_source_ns': osource, 'tf_source_ns': tsource,
                                    'pending_odom_input_sequences': [2] if cycle == 1 else [],
                                    'pending_tf_input_sequences': [2] if cycle == 2 else [],
                                    'skip_reason': None}, clock)
            odsecs = (original_odom['header']['stamp']['sec']
                      + original_odom['header']['stamp']['nanosec'] / 1e9)
            tfsecs = (original_tf['header']['stamp']['sec']
                      + original_tf['header']['stamp']['nanosec'] / 1e9)
            state = {'robot': robot, 'name': robot, 'x': 1.1, 'y': 2.2, 'yaw': 0.,
                     'v': .02, 'w': .1, 'odom_source_stamp': odsecs,
                     'tf_source_stamp': tfsecs - .2, 'tf_validity_stamp': tfsecs,
                     'tf_validity_lead_sec': .2, 'odometry': original_odom,
                     'transform': original_tf}
            envelope = {'epoch': epoch, 'stream': 'state', 'source': robot,
                        'source_stamp': min(odsecs, tfsecs - .2), 'generated_stamp': clock / 1e9,
                        'sequence': cycle, 'version': cycle, 'payload': state,
                        'received_stamp': None}
            add('state_send', {'cycle_id': cycle, 'robot': robot,
                'envelope': copy.deepcopy(envelope), 'payload_sha256': MODULE.digest(state)},
                clock)
            envelope['received_stamp'] = clock / 1e9
            last_delivered[robot] = envelope
            current[robot] = copy.deepcopy(state)
            current[robot].pop('transform')
            current[robot].update(epoch=epoch, sequence=cycle, version=cycle,
                                  source_stamp=envelope['source_stamp'],
                                  received_stamp=clock / 1e9,
                                  valid=0 <= clock / 1e9 - envelope['source_stamp'] <= .5)
        message = {'epoch': epoch, 'sequence': cycle,
                   'robots': [copy.deepcopy(current[r]) for r in MODULE.ROBOTS]}
        sides = [{'robot': r, 'odom_topic': '/mr3/received/' + r + '/odom',
                  'tf_topic': '/mr3/received/' + r + '/tf',
                  'odom_sha256': MODULE.digest(current[r]['odometry']),
                  'tf_sha256': MODULE.digest(last_delivered[r]['payload']['transform']),
                  'envelope_sequence': cycle} for r in MODULE.ROBOTS]
        publish_wall = 1000 + (len(rows) + 1) * 10
        add('state_publish', {'cycle_id': cycle, 'message': message,
            'message_sha256': MODULE.digest(message), 'envelopes': copy.deepcopy(last_delivered),
                              'side_publications': sides, 'scope': 'actual_publish_calls_returned',
                              'publish_started_wall_monotonic_ns': publish_wall - 3,
                              'publish_completed_wall_monotonic_ns': publish_wall - 1}, clock)
        # A subscriber may run before the publisher call has returned.
        motion.append({'epoch': epoch, 'record_sequence': len(motion) + 1,
                       'kind': 'received_states', 'wall_monotonic_ns': publish_wall - 2,
                       'payload': copy.deepcopy(message)})
        for robot in MODULE.ROBOTS:
            peers = {r: copy.deepcopy(current[r]) for r in MODULE.ROBOTS if r != robot}
            motion.append({'epoch': epoch, 'record_sequence': len(motion) + 1,
                           'kind': 'decision', 'wall_monotonic_ns': publish_wall + 1,
                           'payload': {'robot': robot, 'received_peers': peers}})
    return rows, motion, epoch


def replay(rows, motion=None, epoch='synthetic-epoch'):
    value = MODULE.LedgerReplay(epoch)
    for row in rows:
        value.record(row)
    counts = value.finish()
    if motion is not None:
        MODULE.audit_motion(motion, value.published, epoch)
    return counts


class ProducerReplayTests(unittest.TestCase):
    def setUp(self):
        self.rows, self.motion, self.epoch = fixture()

    def mutate(self, kind, change, occurrence=0):
        rows = copy.deepcopy(self.rows)
        selected = [r for r in rows if r['kind'] == kind][occurrence]
        change(selected['payload'])
        return rows

    def test_future_latest_does_not_replace_causal_sample_then_promotes(self):
        counts = replay(self.rows, self.motion)
        self.assertEqual(counts['odom_future_ingress'], 3)
        self.assertEqual(counts['selections_retaining_future_odom'], 3)
        self.assertEqual(counts['state_publish'], 3)

    def test_future_selection_or_skip_old_latest_implementation_is_rejected(self):
        changes = [lambda p: p.update(odom_input_sequence=2, odom_source_ns=10_019_000_000),
                   lambda p: p.update(odom_input_sequence=None, odom_source_ns=None,
                                      skip_reason='missing_odom'),
                   lambda p: p.update(skip_reason='future_source'),
                   lambda p: p.update(pending_odom_input_sequences=[])]
        for change in changes:
            with self.subTest(change=change), self.assertRaises(ValueError):
                replay(self.mutate('state_selection', change))

    def test_original_v8_future_skip_counterexample(self):
        # Original receive_local_odom stores latest10.019 and the old publish
        # guard skips because it is future at10.0; a valid9.9 sample was lost.
        latest_only_source = 10_019_000_000
        self.assertGreater(latest_only_source, 10_000_000_000)
        old = self.mutate('state_selection', lambda p: p.update(
            odom_input_sequence=2, odom_source_ns=latest_only_source, skip_reason='future_source'))
        with self.assertRaisesRegex(ValueError, 'latest causal'):
            replay(old)

    def test_raw_header_hash_and_input_identity_mutations(self):
        for change in (lambda p: p.update(source_ns=p['source_ns'] + 1),
                       lambda p: p.update(raw_sha256='0' * 64),
                       lambda p: p.update(input_sequence=2),
                       lambda p: p.update(input_sequence=True),
                       lambda p: p.update(admission='backwards')):
            with self.subTest(change=change), self.assertRaises(ValueError):
                replay(self.mutate('odom_ingress', change))

    def test_tf_source_never_replaced_by_new_odom_or_forward_validity(self):
        for change in (lambda p: p.update(tf_source_ns=10_000_000_000),
                       lambda p: p.update(tf_input_sequence=2),
                       lambda p: p.update(pending_tf_input_sequences=[99])):
            with self.subTest(change=change), self.assertRaises(ValueError):
                replay(self.mutate('state_selection', change))

        def freshen(p):
            p['envelope']['source_stamp'] = p['envelope']['payload']['odom_source_stamp']
        with self.assertRaisesRegex(ValueError, 'source freshened'):
            replay(self.mutate('state_send', freshen))

    def test_received_envelope_is_bound_to_actual_send(self):
        for field, value in (('sequence', 99), ('version', 99), ('source_stamp', 10.),
                             ('received_stamp', 11.)):
            def change(p, field=field, value=value):
                p['envelopes']['tb1'][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                replay(self.mutate('state_publish', change))

    def test_received_payload_and_side_publication_mutations(self):
        def message_change(p):
            p['message']['robots'][0]['odometry']['pose']['pose']['position']['x'] += .1
            p['message_sha256'] = MODULE.digest(p['message'])
        mutations = [message_change,
                     lambda p: p['side_publications'][0].update(tf_sha256='0' * 64),
                     lambda p: p['side_publications'][0].update(envelope_sequence=99),
                     lambda p: p.update(scope='intent_to_publish'),
                     lambda p: p.update(side_publications=[])]
        for change in mutations:
            with self.subTest(change=change), self.assertRaises(ValueError):
                replay(self.mutate('state_publish', change))

    def test_missing_ingress_send_selection_or_publish_is_rejected(self):
        for kind in ('odom_ingress', 'tf_ingress', 'tf_promote', 'state_selection',
                     'state_send', 'state_publish'):
            rows = copy.deepcopy(self.rows)
            target = next(i for i, row in enumerate(rows) if row['kind'] == kind)
            del rows[target]
            for index, row in enumerate(rows, 1):
                row['record_sequence'] = index
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                replay(rows)

    def test_cross_epoch_gap_unsupported_kind_and_empty_are_rejected(self):
        for alter in (lambda r: r[1].update(epoch='other'),
                      lambda r: r[1].update(record_sequence=99),
                      lambda r: r[1].update(kind='unknown'),
                      lambda r: r[0]['payload'].update(tf_validity_lead_sec=0.)):
            rows = copy.deepcopy(self.rows)
            alter(rows)
            with self.subTest(alter=alter), self.assertRaises(ValueError):
                replay(rows)
        with self.assertRaises(ValueError):
            replay([])


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.reader = MODULE.LedgerReplay('e')
        self.reader.record({'schema': MODULE.SCHEMA, 'epoch': 'e', 'record_sequence': 1,
                            'clock_ns': 10_000_000_000, 'wall_monotonic_ns': 1,
                            'kind': 'configuration',
                            'payload': {'tf_validity_lead_sec': .2, 'pending_limit': 256,
                                        'state_period_sec': .1,
                                        'odom_pending_order': 'source_ns_ascending',
                                        'tf_pending_order': 'accepted_header_ascending'}})

    def ingress(self, kind, source, seq, admission='queued', matched=None, raw=None):
        raw = raw or (odom(source) if kind == 'odom' else tf(source + 200_000_000))
        self.reader.ingress(kind, {'robot': 'tb1', 'input_sequence': seq, 'source_ns': source,
                                   'raw': raw, 'raw_sha256': MODULE.digest(raw),
                                   'admission': admission,
                                   'matched_input_sequence': matched}, 10_000_000_000)

    def test_late_causal_arrival_behind_future_is_selected(self):
        self.ingress('odom', 9_900_000_000, 1)
        self.reader.promote('odom', 'tb1', 10_000_000_000)
        self.ingress('odom', 10_019_000_000, 2)
        self.ingress('odom', 9_950_000_000, 3)
        chosen = self.reader.promote('odom', 'tb1', 10_000_000_000)
        self.assertEqual(chosen['sequence'], 3)
        self.assertEqual([r['sequence'] for r in self.reader.pending['odom', 'tb1']], [2])
        self.assertEqual(self.reader.promote('odom', 'tb1', 10_020_000_000)['sequence'], 2)

    def test_duplicate_and_backwards_are_logged_without_replacing_source(self):
        self.ingress('odom', 9_900_000_000, 1)
        self.reader.promote('odom', 'tb1', 10_000_000_000)
        self.ingress('odom', 9_900_000_000, 2, 'duplicate', 1)
        self.ingress('odom', 9_800_000_000, 3, 'backwards')
        self.assertEqual(self.reader.promote('odom', 'tb1', 10_000_000_000)['sequence'], 1)

    def test_conflicting_duplicate_and_queue_overflow_fail_closed(self):
        self.ingress('odom', 10_019_000_000, 1)
        changed = odom(10_019_000_000)
        changed['twist']['twist']['linear']['x'] = .12
        with self.assertRaisesRegex(ValueError, 'fail-closed'):
            self.ingress('odom', 10_019_000_000, 2, 'conflicting_duplicate', 1, changed)
        self.setUp()
        for seq in range(1, 257):
            self.ingress('odom', 10_000_000_000 + seq, seq)
        with self.assertRaisesRegex(ValueError, 'fail-closed'):
            self.ingress('odom', 11_000_000_000, 257, 'queue_overflow')

    def test_original_tf_pending_order_and_repeated_stamp_after_promotion(self):
        self.ingress('tf', 10_200_000_000, 1)
        self.ingress('tf', 10_100_000_000, 2, 'ignored_pending_order', 1)
        self.reader.tf_promote({'robot': 'tb1', 'selected_input_sequence': 1,
                                'pending_tf_input_sequences': []}, 10_200_000_000)
        changed = tf(10_400_000_000)
        changed['transform']['translation']['x'] = 1.01
        # Existing TF behavior is retained: once pending is empty, a repeated
        # source can be accepted even when the transform payload has changed.
        self.ingress('tf', 10_200_000_000, 3, raw=changed)
        self.reader.tf_promote({'robot': 'tb1', 'selected_input_sequence': 3,
                                'pending_tf_input_sequences': []}, 10_200_000_000)
        self.assertEqual(self.reader.current['tf', 'tb1']['raw_sha256'], MODULE.digest(changed))

    def test_strict_bool_numeric_and_canonical_float_types(self):
        rows, _, _ = fixture()
        cases = []
        for kind, field in (('configuration', 'pending_limit'), ('state_selection', 'cycle_id'),
                            ('state_selection', 'odom_input_sequence'),
                            ('state_selection', 'tf_input_sequence')):
            value = copy.deepcopy(rows)
            target = next(r for r in value if r['kind'] == kind)
            target['payload'][field] = True
            cases.append(value)
        value = copy.deepcopy(rows)
        value[0]['record_sequence'] = True
        cases.append(value)
        value = copy.deepcopy(rows)
        target = next(r for r in value if r['kind'] == 'state_send')
        target['payload']['envelope']['version'] = True
        cases.append(value)
        value = copy.deepcopy(rows)
        target = next(r for r in value if r['kind'] == 'state_send')
        target['payload']['envelope']['generated_stamp'] = 10
        cases.append(value)
        for index, value in enumerate(cases):
            with self.subTest(index=index), self.assertRaises(ValueError):
                replay(value)
        bad = odom(10_019_000_000)
        bad['twist']['twist']['linear']['x'] = False
        with self.assertRaisesRegex(ValueError, 'float field'):
            self.ingress('odom', 10_019_000_000, 1, raw=bad)


class ArtifactAndCliTests(unittest.TestCase):
    def make_episode(self, directory, compressed=False):
        rows, motion, epoch = fixture()
        motion.insert(0, {'epoch': epoch, 'record_sequence': 1, 'kind': 'release',
                          'wall_monotonic_ns': 1, 'payload': {'stamp': 10.0}})
        for seq, value in enumerate(motion, 1):
            value['record_sequence'] = seq
        content = {'metadata.json': {'epoch': epoch, 'freeze': 'a' * 40},
                   'summary.json': {'closed': True}}
        for name, value in content.items():
            (directory / name).write_bytes(MODULE.canonical(value) + b'\n')
        tables = {'physics.jsonl': [{'end_time_ns': 10_040_000_000}],
                  'transitions.jsonl': [{'kind': 'reset'}],
                  'information_states.jsonl': rows, 'motion_safety.jsonl': motion}
        for name, values in tables.items():
            data = b''.join(MODULE.canonical(value) + b'\n' for value in values)
            if compressed:
                (directory / (name + '.gz')).write_bytes(gzip.compress(data, mtime=0))
            else:
                (directory / name).write_bytes(data)
        return rows

    def test_plain_and_detached_gzip_archive_bindings(self):
        for compressed in (False, True):
            with self.subTest(compressed=compressed), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp)
                self.make_episode(path, compressed)
                result = MODULE.audit_episode(path, 'a' * 40)
                self.assertTrue(result['passed'], result['errors'])
                self.assertEqual(result['physics_end_ns'], 10_040_000_000)
                self.assertTrue(all(len(r['encoded_sha256']) == 64 for r in result['inputs']))

    def test_cli_reports_real_bool_failure_and_original_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            self.make_episode(path)
            output = path / 'review.json'
            command = [sys.executable, str(PATH), str(path), '--freeze', 'a' * 40,
                       '--output', str(output)]
            valid = subprocess.run(command, capture_output=True, text=True, check=False)
            self.assertEqual(valid.returncode, 0, valid.stdout + valid.stderr)
            self.assertIs(json.loads(output.read_text())['passed'], True)
            original = (path / 'information_states.jsonl').read_bytes()
            ledger = [json.loads(line) for line in original.splitlines()]
            selection = next(r['payload'] for r in ledger if r['kind'] == 'state_selection')
            selection.update(odom_input_sequence=2, odom_source_ns=10_019_000_000,
                             skip_reason='future_source')
            mutated = b''.join(MODULE.canonical(value) + b'\n' for value in ledger)
            (path / 'information_states.jsonl').write_bytes(mutated)
            failed = subprocess.run(command, capture_output=True, text=True, check=False)
            result = json.loads(output.read_text())
            self.assertEqual(failed.returncode, 1, failed.stdout + failed.stderr)
            self.assertIs(result['passed'], False)
            self.assertTrue(result['episodes'][0]['errors'])
            binding = next(x for x in result['episodes'][0]['inputs']
                           if x['path'].endswith('information_states.jsonl'))
            self.assertEqual(binding['encoded_sha256'], hashlib.sha256(mutated).hexdigest())

    def test_missing_ledger_and_plain_gzip_disagreement_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            self.make_episode(path)
            ledger = path / 'information_states.jsonl'
            (path / 'information_states.jsonl.gz').write_bytes(gzip.compress(b'{}\n', mtime=0))
            self.assertFalse(MODULE.audit_episode(path, 'a' * 40)['passed'])
            ledger.unlink()
            (path / 'information_states.jsonl.gz').unlink()
            self.assertFalse(MODULE.audit_episode(path, 'a' * 40)['passed'])

    def test_no_nonfinite_or_duplicate_json_keys_and_hash_recheck(self):
        for payload in (b'{"x":NaN}', b'{"x":1,"x":2}'):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                MODULE.parse(payload)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path / 'x.json').write_bytes(b'{}\n')
            inputs = MODULE.Inputs()
            inputs.read(path, 'x.json')
            (path / 'x.json').write_bytes(b'{"changed":true}\n')
            with self.assertRaisesRegex(ValueError, 'changed during'):
                inputs.verify()


def cached_fixture():
    import math
    rows, _, epoch = fixture()
    stop = next(i for i, row in enumerate(rows) if row['kind'] == 'state_publish') + 1
    rows = rows[:stop]
    original = copy.deepcopy(rows[-1]['payload'])

    def add(kind, payload, clock=10_000_000_000):
        seq = len(rows) + 1
        rows.append({'schema': MODULE.SCHEMA, 'epoch': epoch, 'record_sequence': seq,
                     'kind': kind, 'clock_ns': clock, 'wall_monotonic_ns': seq * 10 + 1000,
                     'payload': payload})

    for robot in MODULE.ROBOTS:
        raw = odom(10_000_000_000)
        raw['pose']['pose']['position'].update(x=1.7e308, y=1.7e308)
        add('odom_ingress', {'robot': robot, 'input_sequence': 3,
                             'source_ns': 10_000_000_000, 'raw': raw,
                             'raw_sha256': MODULE.digest(raw), 'admission': 'queued',
                             'matched_input_sequence': None})
        raw = tf(10_000_000_000)
        raw['transform']['rotation'].update(z=math.sin(math.pi / 8),
                                            w=math.cos(math.pi / 8))
        add('tf_ingress', {'robot': robot, 'input_sequence': 2,
                           'source_ns': 9_800_000_000, 'raw': raw,
                           'raw_sha256': MODULE.digest(raw), 'admission': 'queued',
                           'matched_input_sequence': None})
    for robot in MODULE.ROBOTS:
        add('tf_promote', {'robot': robot, 'selected_input_sequence': 2,
                           'pending_tf_input_sequences': []})
    for robot in MODULE.ROBOTS:
        add('state_selection', {'cycle_id': 2, 'robot': robot,
                                'odom_input_sequence': 3, 'tf_input_sequence': 2,
                                'odom_source_ns': 10_000_000_000,
                                'tf_source_ns': 9_800_000_000,
                                'pending_odom_input_sequences': [2],
                                'pending_tf_input_sequences': [],
                                'skip_reason': 'nonfinite_state'})
    original['cycle_id'] = 2
    original['message']['sequence'] = 2
    original['message_sha256'] = MODULE.digest(original['message'])
    wall = (len(rows) + 1) * 10 + 1000
    original.update(publish_started_wall_monotonic_ns=wall - 3,
                    publish_completed_wall_monotonic_ns=wall - 1)
    add('state_publish', original, 10_020_000_000)
    return rows


class StrictCacheAndClockTests(unittest.TestCase):
    def test_cross_quantum_delivery_is_legal_and_cached_stamp_is_preserved(self):
        rows = cached_fixture()
        self.assertEqual(replay(rows)['state_publish'], 2)
        bad = copy.deepcopy(rows)
        value = bad[-1]['payload']
        value['envelopes']['tb1']['received_stamp'] = 10.02
        value['message']['robots'][0]['received_stamp'] = 10.02
        value['message_sha256'] = MODULE.digest(value['message'])
        with self.assertRaisesRegex(ValueError, 'cached delivery changed'):
            replay(bad)

    def test_configuration_types_period_and_order_are_exact(self):
        for field, changed in (('pending_limit', 256.0), ('state_period_sec', .2),
                               ('odom_pending_order', 'latest_only'),
                               ('tf_pending_order', 'latest_only')):
            rows, _, _ = fixture()
            rows[0]['payload'][field] = changed
            with self.subTest(field=field), self.assertRaises(ValueError):
                replay(rows)

    def test_exact_half_second_and_one_nanosecond_older_state_validity(self):
        for publish_clock, expected in ((10_300_000_000, True),
                                        (10_300_000_001, False)):
            rows, _, _ = fixture()
            stop = next(i for i, row in enumerate(rows) if row['kind'] == 'state_publish') + 1
            rows = rows[:stop]
            last = rows[-1]
            last['clock_ns'] = publish_clock
            for envelope in last['payload']['envelopes'].values():
                envelope['received_stamp'] = publish_clock / 1e9
            for state in last['payload']['message']['robots']:
                state.update(received_stamp=publish_clock / 1e9, valid=expected)
            last['payload']['message_sha256'] = MODULE.digest(last['payload']['message'])
            with self.subTest(clock=publish_clock):
                self.assertEqual(replay(rows)['state_publish'], 1)
                wrong = copy.deepcopy(rows)
                wrong[-1]['payload']['message']['robots'][0]['valid'] = not expected
                wrong[-1]['payload']['message_sha256'] = MODULE.digest(
                    wrong[-1]['payload']['message'])
                with self.assertRaisesRegex(ValueError, 'differs from delivered'):
                    replay(wrong)

    def test_first_selection_clock_cannot_be_rewritten_or_send_delayed(self):
        rows, _, _ = fixture()
        for kind in ('state_selection', 'state_send'):
            bad = copy.deepcopy(rows)
            target = [row for row in bad if row['kind'] == kind][1]
            target['clock_ns'] += 20_000_000
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                replay(bad)


class EmptyStartupTests(unittest.TestCase):
    def test_missing_state_placeholder_rejects_false_for_numeric_zero(self):
        rows, _, epoch = fixture()
        for row in rows:
            value = row['payload']
            if 'cycle_id' in value:
                value['cycle_id'] += 1
            if row['kind'] == 'state_publish':
                value['message']['sequence'] += 1
                value['message_sha256'] = MODULE.digest(value['message'])
        prefix = []
        for robot in MODULE.ROBOTS:
            prefix.append({'kind': 'state_selection', 'payload': {
                'cycle_id': 1, 'robot': robot, 'odom_input_sequence': None,
                'tf_input_sequence': None, 'odom_source_ns': None, 'tf_source_ns': None,
                'pending_odom_input_sequences': [], 'pending_tf_input_sequences': [],
                'skip_reason': 'missing_odom'}})
        message = {'epoch': epoch, 'sequence': 1, 'robots': [
            {'robot': robot, 'name': robot, 'valid': False,
             'x': 0.0, 'y': 0.0, 'yaw': 0.0, 'v': 0.0, 'w': 0.0,
             'epoch': epoch, 'sequence': 0, 'version': 0,
             'source_stamp': None, 'received_stamp': None} for robot in MODULE.ROBOTS]}
        prefix.append({'kind': 'state_publish', 'payload': {
            'cycle_id': 1, 'message': message, 'message_sha256': MODULE.digest(message),
            'envelopes': dict.fromkeys(MODULE.ROBOTS), 'side_publications': [],
            'scope': 'actual_publish_calls_returned',
            'publish_started_wall_monotonic_ns': 1020,
            'publish_completed_wall_monotonic_ns': 1030}})
        rows[1:1] = prefix
        for seq, row in enumerate(rows, 1):
            row.update(schema=MODULE.SCHEMA, epoch=epoch, record_sequence=seq,
                       wall_monotonic_ns=1000 + seq * 10)
            row.setdefault('clock_ns', 9_900_000_000)
            if row['kind'] == 'state_publish':
                row['payload'].update(publish_started_wall_monotonic_ns=1000 + seq * 10 - 3,
                                      publish_completed_wall_monotonic_ns=1000 + seq * 10 - 1)
        self.assertEqual(replay(rows)['state_publish'], 4)
        for field in ('x', 'sequence', 'version'):
            bad = copy.deepcopy(rows)
            value = next(r['payload'] for r in bad if r['kind'] == 'state_publish')
            value['message']['robots'][0][field] = False
            value['message_sha256'] = MODULE.digest(value['message'])
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'placeholder'):
                replay(bad)


if __name__ == '__main__':
    unittest.main(verbosity=2)
