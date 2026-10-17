"""Independent phase mutations, with pinned raw-state fixtures and no ROS imports."""

import copy
import importlib.util
import gzip
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location('information_v2',
                                             Path(__file__).with_name('mr3_independent_information_v2.py'))
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)
OLD_TEST = M.LEGACY.with_name('mr3_independent_information_v1_tests.py')
SPEC = importlib.util.spec_from_file_location('immutable_raw_fixtures', OLD_TEST)
OLD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(OLD)


def fixture():
    original, unused_motion, epoch = OLD.fixture()
    out = []

    def add(kind, value, clock):
        row = {'schema': M.SCHEMA, 'epoch': epoch, 'record_sequence': len(out) + 1,
               'clock_ns': clock, 'wall_monotonic_ns': 1000 + (len(out) + 1) * 100,
               'kind': kind, 'payload': copy.deepcopy(value)}
        out.append(row)
        return row

    def req(operation, target, identifier):
        value = {'schema': 'mr3-state-phase-request-v1', 'epoch': epoch,
                 'request_id': identifier, 'operation': operation, 'target_time_ns': target}
        add('state_phase_request', {'request': value, 'duplicate': False}, target)
        return value

    def ack(value, clock):
        wall = 1000 + (len(out) + 1) * 100
        add('state_phase_ack', {'ack': value, 'cached': False,
                               'publish_started_wall_monotonic_ns': wall - 2,
                               'publish_completed_wall_monotonic_ns': wall - 1}, clock)

    cycles = set()
    for row in original:
        kind, value, clock = row['kind'], row['payload'], row['clock_ns']
        if kind == 'state_selection' and value['cycle_id'] not in cycles:
            cycles.add(value['cycle_id'])
            req('commit', clock, 'boundary' + str(clock))
        current = add(kind, value, clock)
        if kind == 'configuration':
            request = req('takeover', clock, 'takeover' + str(clock))
            ack({'schema': 'mr3-state-phase-ack-v1', **{key: request[key] for key in
                 ('epoch', 'request_id', 'operation', 'target_time_ns')},
                 'clock_ns': clock, 'ok': True, 'state_sequence': None,
                 'bundle_sha256': None, 'robots': {},
                 'scope': 'periodic_state_publication_disabled'}, clock)
        elif kind == 'state_publish':
            value = current['payload']
            wall = current['wall_monotonic_ns']
            value.update(side_publish_started_wall_monotonic_ns=wall - 5,
                         publish_started_wall_monotonic_ns=wall - 3,
                         publish_completed_wall_monotonic_ns=wall - 1)
            sides = {item['robot']: item for item in value['side_publications']}
            robots = {}
            for name, envelope in value['envelopes'].items():
                robots[name] = {'sequence': envelope['sequence'], 'version': envelope['version'],
                    'source_stamp': envelope['source_stamp'],
                    'source_ns': round(envelope['source_stamp'] * 1e9),
                    'odom_source_ns': round(envelope['payload']['odom_source_stamp'] * 1e9),
                    'tf_source_ns': round(envelope['payload']['tf_source_stamp'] * 1e9),
                    **{key: sides[name][key] for key in
                       ('odom_topic', 'tf_topic', 'odom_sha256', 'tf_sha256')}}
            ack({'schema': 'mr3-state-phase-ack-v1', 'epoch': epoch,
                 'request_id': 'boundary' + str(clock), 'operation': 'commit',
                 'target_time_ns': clock, 'clock_ns': clock, 'ok': True,
                 'state_sequence': value['message']['sequence'],
                 'bundle_sha256': value['message_sha256'], 'robots': robots,
                 'side_publish_started_wall_monotonic_ns': wall - 5,
                 'bundle_publish_started_wall_monotonic_ns': wall - 3,
                 'bundle_publish_completed_wall_monotonic_ns': wall - 1,
                 'scope': 'actual_state_and_side_publish_calls_returned'}, clock)
    return out, epoch


def replay(rows, epoch='synthetic-epoch'):
    value = M.LedgerReplay(epoch)
    for row in rows:
        value.record(row)
    return value.finish()


def terminal_drain_fixture(advance_ns=20_000_000, cancel=False):
    rows, epoch = fixture()
    commit = copy.deepcopy(rows[-1]['payload']['ack'])
    target = commit['clock_ns'] + advance_ns

    def add(kind, value):
        row = copy.deepcopy(rows[-1])
        row.update(kind=kind, payload=value, record_sequence=len(rows) + 1,
                   wall_monotonic_ns=row['wall_monotonic_ns'] + 100, clock_ns=target)
        rows.append(row)
        return row

    notice = {'epoch': epoch, 'end_sim_time_sec': target / 1e9,
              'termination_reason': 'coverage_reached'}
    if cancel:
        add('state_phase_request', {'request': {'schema': 'mr3-state-phase-request-v1',
            'epoch': epoch, 'request_id': 'pending_terminal', 'operation': 'commit',
            'target_time_ns': target}, 'duplicate': False})
    add('state_terminal_received', {'notice': notice, 'duplicate': False})
    if cancel:
        wall = rows[-1]['wall_monotonic_ns'] + 100
        add('state_phase_ack', {'ack': {'schema': 'mr3-state-phase-ack-v1', 'epoch': epoch,
            'request_id': 'pending_terminal', 'operation': 'commit', 'target_time_ns': target,
            'clock_ns': target, 'ok': False, 'error': 'state_phase_task_terminal',
            'terminal_notice': notice, 'scope': 'terminal_cancelled_uncommitted_state_phase'},
            'cached': False, 'publish_started_wall_monotonic_ns': wall - 2,
            'publish_completed_wall_monotonic_ns': wall - 1})
    add('state_drain_request', {'request': {'epoch': epoch, 'request_id': 'terminal_snapshot',
        'target_time_ns': target, 'allow_terminal': True}})
    wall = rows[-1]['wall_monotonic_ns'] + 100
    add('state_drain_ack', {'cached': False, 'publish_started_wall_monotonic_ns': wall - 2,
        'publish_completed_wall_monotonic_ns': wall - 1, 'ack': {
            'epoch': epoch, 'request_id': 'terminal_snapshot', 'target_time_ns': target,
            'ok': True, 'allow_terminal': True, 'state_sequence': commit['state_sequence'],
            'state_bundle_sha256': commit['bundle_sha256'],
            'state_commit_clock_ns': commit['clock_ns'],
            'state_reuse_scope': 'terminal_last_committed', 'terminal_notice': notice}})
    return rows, epoch


class PhaseTests(unittest.TestCase):
    def setUp(self):
        self.rows, self.epoch = fixture()

    def mutate(self, kind, update, occurrence=-1):
        rows = copy.deepcopy(self.rows)
        selected = [row for row in rows if row['kind'] == kind][occurrence]
        update(selected['payload'])
        return rows

    def test_real_three_phase_raw_fixture_passes(self):
        counts = replay(self.rows)
        self.assertEqual(counts['state_commit_acks'], 3)
        self.assertEqual(counts['takeover_acks'], 1)

    def test_bundle_identity_mutations_rejected(self):
        for change in (lambda a: a.update(state_sequence=99),
                       lambda a: a.update(state_sequence=True),
                       lambda a: a.update(bundle_sha256='f' * 64),
                       lambda a: a.update(clock_ns=a['clock_ns'] + 1),
                       lambda a: a.update(operation='takeover'),
                       lambda a: a.update(scope='physical_receipt'),
                       lambda a: a.update(ok=False)):
            with self.subTest(change=change), self.assertRaises(ValueError):
                replay(self.mutate('state_phase_ack', lambda p: change(p['ack'])))

    def test_raw_side_and_source_bindings_cannot_change(self):
        for key, value in (('odom_sha256', 'f' * 64), ('tf_sha256', 'f' * 64),
                           ('source_ns', 0), ('version', 9), ('sequence', False),
                           ('tf_source_ns', 0), ('odom_topic', '/tb1/odom')):
            with self.subTest(key=key), self.assertRaises(ValueError):
                replay(self.mutate('state_phase_ack',
                       lambda p: p['ack']['robots']['tb1'].update({key: value})))

    def test_publication_windows_bind_actual_calls(self):
        for key in ('side_publish_started_wall_monotonic_ns',
                    'bundle_publish_started_wall_monotonic_ns',
                    'bundle_publish_completed_wall_monotonic_ns'):
            with self.subTest(key=key), self.assertRaises(ValueError):
                replay(self.mutate('state_phase_ack', lambda p: p['ack'].update({key: 1})))

    def test_cached_ack_exact_replay_without_new_publication(self):
        rows = copy.deepcopy(self.rows)
        request = next(row['payload']['request'] for row in reversed(rows)
                       if row['kind'] == 'state_phase_request')
        old = copy.deepcopy(rows[-1])
        row = copy.deepcopy(old)
        row.update(kind='state_phase_request', record_sequence=len(rows) + 1,
                   wall_monotonic_ns=old['wall_monotonic_ns'] + 100,
                   payload={'request': request, 'duplicate': True})
        rows.append(row)
        old['record_sequence'] = len(rows) + 1
        old['wall_monotonic_ns'] = row['wall_monotonic_ns'] + 100
        old['payload']['cached'] = True
        rows.append(old)
        self.assertEqual(replay(rows)['state_commit_acks'], 3)
        rows[-1]['payload']['ack']['bundle_sha256'] = 'f' * 64
        with self.assertRaises(ValueError):
            replay(rows)

    def test_cached_ack_without_duplicate_request_is_rejected(self):
        rows = copy.deepcopy(self.rows)
        old = copy.deepcopy(rows[-1])
        old.update(record_sequence=len(rows) + 1,
                   wall_monotonic_ns=old['wall_monotonic_ns'] + 100)
        old['payload']['cached'] = True
        rows.append(old)
        with self.assertRaises(ValueError):
            replay(rows)

    def test_missing_phase_commit_is_not_legacy_periodic_pass(self):
        rows, unused, epoch = OLD.fixture()
        with self.assertRaises(ValueError):
            replay(rows, epoch)

    def test_unrequested_controlled_publication_is_rejected(self):
        rows = [row for row in copy.deepcopy(self.rows)
                if not (row['kind'] == 'state_phase_request'
                        and row['payload']['request']['operation'] == 'commit')]
        for index, row in enumerate(rows, 1):
            row['record_sequence'] = index
        with self.assertRaisesRegex(ValueError, 'unrequested controlled'):
            replay(rows)

    def test_takeover_cannot_claim_publication_credit(self):
        for change in (lambda a: a.update(state_sequence=0),
                       lambda a: a.update(bundle_sha256='f' * 64),
                       lambda a: a.update(robots={'tb1': {}})):
            with self.subTest(change=change), self.assertRaises(ValueError):
                replay(self.mutate('state_phase_ack', lambda p: change(p['ack']), occurrence=0))

    def test_future_source_and_dropped_pending_old_raw_gates_remain(self):
        for change in (lambda p: p.update(odom_source_ns=10_019_000_000,
                                          odom_input_sequence=2),
                       lambda p: p.update(pending_odom_input_sequences=[])):
            with self.subTest(change=change), self.assertRaises(ValueError):
                replay(self.mutate('state_selection', change, occurrence=0))

    def test_wrong_phase_epoch_and_type_rejected(self):
        for change in (lambda p: p['request'].update(epoch='other'),
                       lambda p: p['request'].update(target_time_ns=True),
                       lambda p: p.update(duplicate=0)):
            with self.subTest(change=change), self.assertRaises(ValueError):
                replay(self.mutate('state_phase_request', change))

    def test_terminal_drain_preserves_real_previous_watermark_without_publication(self):
        rows, epoch = terminal_drain_fixture()
        counts = replay(rows, epoch)
        self.assertEqual(counts['terminal_only_state_reuse'], 1)
        self.assertEqual(counts['state_publish'], 3)

    def test_terminal_drain_cannot_be_enabled_by_request_flag_alone(self):
        rows, epoch = terminal_drain_fixture()
        rows = [row for row in rows if row['kind'] != 'state_terminal_received']
        for index, row in enumerate(rows, 1):
            row['record_sequence'] = index
        with self.assertRaisesRegex(ValueError, 'no actual terminal'):
            replay(rows, epoch)

    def test_terminal_drain_rejects_live_flag_and_changed_original_commit(self):
        for key, value in (('state_sequence', 99), ('state_bundle_sha256', 'f' * 64),
                           ('state_commit_clock_ns', 0), ('state_reuse_scope', 'exact_commit')):
            rows, epoch = terminal_drain_fixture()
            rows[-1]['payload']['ack'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                replay(rows, epoch)
        rows, epoch = terminal_drain_fixture()
        rows[-2]['payload']['request']['allow_terminal'] = False
        with self.assertRaises(ValueError):
            replay(rows, epoch)

    def test_terminal_drain_requires_original_epoch_and_end_at_or_before_boundary(self):
        for change in (lambda n: n.update(epoch='other'),
                       lambda n: n.update(end_sim_time_sec=300.),
                       lambda n: n.update(termination_reason='training_external_truncation')):
            rows, epoch = terminal_drain_fixture()
            terminal = next(row for row in rows if row['kind'] == 'state_terminal_received')
            change(terminal['payload']['notice'])
            with self.subTest(change=change), self.assertRaises(ValueError):
                replay(rows, epoch)

    def test_actual_terminal_cancellation_preserves_previous_commit(self):
        rows, epoch = terminal_drain_fixture(600_000_000, cancel=True)
        counts = replay(rows, epoch)
        self.assertEqual(counts['state_commit_acks'], 3)
        self.assertEqual(counts['terminal_cancelled_state_commits'], 1)
        self.assertEqual(counts['terminal_only_state_reuse'], 1)

    def test_cancelled_commit_requires_actual_notice_and_no_new_publication(self):
        for change in (lambda a: a.update(error='timeout'),
                       lambda a: a.update(terminal_notice={}),
                       lambda a: a.update(scope='normal_commit'),
                       lambda a: a.update(ok=True)):
            rows, epoch = terminal_drain_fixture(600_000_000, cancel=True)
            cancelled = next(row for row in rows if row['kind'] == 'state_phase_ack'
                             and row['payload']['ack'].get('ok') is False)
            change(cancelled['payload']['ack'])
            with self.subTest(change=change), self.assertRaises(ValueError):
                replay(rows, epoch)

    def test_standalone_cli_uses_v2_with_pinned_raw_reader_and_gzip_inputs(self):
        rows, epoch = terminal_drain_fixture()
        motion = [{'epoch': epoch, 'record_sequence': 1, 'kind': 'release',
                   'wall_monotonic_ns': 1, 'payload': {'stamp': 10.}}]
        for row in rows:
            if row['kind'] != 'state_publish':
                continue
            value = row['payload']
            motion.append({'epoch': epoch, 'record_sequence': len(motion) + 1,
                           'kind': 'received_states', 'payload': value['message'],
                           'wall_monotonic_ns': value['publish_started_wall_monotonic_ns'] + 1})
            robots = {robot['name']: robot for robot in value['message']['robots']}
            for name in M.ROBOTS:
                motion.append({'epoch': epoch, 'record_sequence': len(motion) + 1,
                               'kind': 'decision',
                               'wall_monotonic_ns': value['publish_completed_wall_monotonic_ns'] + 1,
                               'payload': {'robot': name, 'received_peers': {
                                   peer: state for peer, state in robots.items() if peer != name}}})
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / 'metadata.json').write_text(json.dumps({'epoch': epoch, 'freeze': 'a' * 40}))
            (directory / 'physics.jsonl').write_text(json.dumps({'end_time_ns': 10_060_000_000}) + '\n')
            (directory / 'transitions.jsonl').write_text('')
            (directory / 'summary.json').write_text('{}')
            data = ''.join(json.dumps(row) + '\n' for row in rows).encode()
            (directory / 'information_states.jsonl.gz').write_bytes(gzip.compress(data, mtime=0))
            (directory / 'motion_safety.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in motion))
            output = directory / 'new_result.json'
            completed = subprocess.run(['/usr/bin/python3', str(Path(M.__file__)), str(directory),
                                        '--freeze', 'a' * 40, '--output', str(output)],
                                       capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads(output.read_text())
            self.assertTrue(result['passed'])
            self.assertEqual(result['schema'], 'mr3-independent-information-review-v2')
            self.assertEqual(result['immutable_raw_replay']['sha256'], M.LEGACY_SHA)


if __name__ == '__main__':
    unittest.main()
