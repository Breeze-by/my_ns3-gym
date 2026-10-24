"""Compare the indexed consumer with its frozen pre-optimization oracle.

These synthetic prefixes exercise ownership and callback matching only. They
do not establish native admission or the validity of an exploration policy.
"""
import ast
from collections import Counter
import copy
import hashlib
from pathlib import Path
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from mr3_learning import audit_reach_information as audit
from mr3_learning.tests.test_audit_reach_information import (
    EPOCH, graph, normal_lineage_fixture,
)


class InformationIndexRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = Path(audit.__file__).resolve()
        root = next(p for p in source.parents if (p / '.git').exists())
        frozen = subprocess.check_output([
            'git', '-C', str(root), 'show',
            '3631c788ca46e03a52f34ad48c41611761c17f1e:' + source.relative_to(root).as_posix(),
        ])
        if hashlib.sha256(frozen).hexdigest() != 'ab1bfe144e9ab85276718a6131fe87fd3c90a09a1bd71056acc203c0e0765e30':
            raise AssertionError('frozen information oracle bytes differ')
        functions = [n for n in ast.parse(frozen).body
                     if isinstance(n, ast.FunctionDef) and n.name == 'audit_motion']
        if len(functions) != 1:
            raise AssertionError('frozen motion oracle is not unique')
        namespace = dict(vars(audit))
        exec(compile(ast.Module(body=functions, type_ignores=[]),
                     'frozen-3631/audit_reach_information.py', 'exec'), namespace)
        cls.original = staticmethod(namespace['audit_motion'])

    @staticmethod
    def renumber(rows):
        for sequence, row in enumerate(rows, 1):
            row['record_sequence'] = sequence

    @staticmethod
    def outcome(function, case):
        rows, information, peer = copy.deepcopy(case)
        host, _ = audit.load_implementation()
        try:
            return 'returned', function(rows, information, peer, EPOCH, host.BASE)
        except Exception as error:
            return 'error', type(error).__name__, str(error)

    def equivalent(self, case, *, error=None):
        before = self.outcome(self.original, case)
        after = self.outcome(audit.audit_motion, case)
        self.assertEqual(before, after)
        if error is None:
            self.assertEqual(after[0], 'returned', after)
        else:
            self.assertEqual(after[0], 'error', after)
            self.assertIn(error, after[2])
        return after

    def test_complete_lineage_and_successor_match_frozen_report(self):
        for successor in (False, True):
            with self.subTest(successor=successor):
                self.equivalent(normal_lineage_fixture(successor=successor))

    def test_future_owner_cannot_prove_an_earlier_application(self):
        rows, information, peer = normal_lineage_fixture()
        actual = next(r for r in rows if r['kind'] == 'reach_driver_ingress')
        owner = next(r for r in rows if r['kind'] == 'reach_intent_publish'
                     and r['payload']['intent']['robot'] == 'tb1'
                     and r['payload']['intent']['intent_sequence'] == 5)
        rows.remove(actual)
        rows.insert(rows.index(owner), actual)
        actual['wall_monotonic_ns'] = owner['payload']['publish_started_wall_monotonic_ns'] - 1
        self.renumber(rows)
        self.equivalent((rows, information, peer), error='no earlier real owner publication')

    def test_exact_target_encoding_is_preserved(self):
        # Python equality would merge 0, 0.0 and -0.0; the original wire
        # canonicalization deliberately keeps their encodings distinct.
        for key, value in [('angular_z', 0), ('angular_z', -0.0),
                           ('angular_z', .01), ('linear_x', .1000001),
                           ('clock_ns', 1_080_000_001), ('decision_sequence', 99)]:
            with self.subTest(key=key, value=repr(value)):
                rows, information, peer = normal_lineage_fixture()
                actual = next(r for r in rows if r['kind'] == 'reach_driver_ingress')['payload']
                actual['message']['target'][key] = value
                actual['raw_json'] = audit.canonical(actual['message']).decode()
                self.equivalent((rows, information, peer), error='no earlier real owner publication')

    def duplicate_case(self, *, early_good):
        rows, information, peer = normal_lineage_fixture()
        moving = next(r for r in rows if r['kind'] == 'reach_intent_publish'
                      and r['payload']['intent']['robot'] == 'tb1'
                      and r['payload']['intent']['intent_sequence'] == 5)
        normal = rows[-1]
        if not early_good:
            # The first owner sees HOLD. A later duplicate sees delivered X.
            # Its ownership must be evaluated at the current N prefix, rather
            # than freezing the owner list at the earlier applied callback.
            rows.remove(moving)
            incoming = next(r for r in rows if r['kind'] == 'reach_state_ingress'
                            and r['payload']['message']['sequence'] == 2)
            moving['payload'].update(publish_started_wall_monotonic_ns=366,
                                     publish_completed_wall_monotonic_ns=367)
            moving['wall_monotonic_ns'] = 368
            rows.insert(rows.index(incoming), moving)
        else:
            # The first owner sees X; the later duplicate sees HOLD. Replacing
            # the multi-value index with a last-owner dict would reject this.
            bundle = copy.deepcopy(information.complete_publications[0]['message'])
            bundle['sequence'] = 3
            for state in bundle['robots']:
                state.update(sequence=3, version=3, received_stamp=1.1)
            information.complete_publications.append({
                'message': bundle, 'message_sha256': audit.sha(bundle),
                'publish_started_wall_monotonic_ns': 397,
            })
            at = rows.index(normal)
            for offset, (kind, payload) in enumerate([
                ('reach_state_ingress', {'message': bundle,
                    'raw_json': audit.canonical(bundle).decode(),
                    'publisher_identity': graph('/mr3/received/states', 'mr3_information', '/')}),
                ('received_states', bundle),
            ]):
                row = copy.deepcopy(normal)
                row.update(kind=kind, payload=copy.deepcopy(payload),
                           wall_monotonic_ns=401 + offset)
                rows.insert(at + offset, row)
        duplicate = copy.deepcopy(moving)
        duplicate['payload']['intent'].update(intent_sequence=6, source_clock_ns=1_100_000_000)
        duplicate['payload'].update(
            payload_sha256=audit.sha(duplicate['payload']['intent']),
            publish_started_wall_monotonic_ns=405, publish_completed_wall_monotonic_ns=406)
        duplicate.update(wall_monotonic_ns=407, sim_time_sec=1.1)
        normal['payload']['intent']['intent_sequence'] = 7
        normal['payload']['payload_sha256'] = audit.sha(normal['payload']['intent'])
        rows.insert(rows.index(normal), duplicate)
        self.renumber(rows)
        return rows, information, peer

    def test_all_duplicate_owners_and_current_prefix_are_retained(self):
        for early_good in (False, True):
            with self.subTest(early_good=early_good):
                self.equivalent(self.duplicate_case(early_good=early_good))

    def test_same_clock_owner_and_application_use_record_prefix(self):
        rows, information, peer = normal_lineage_fixture()
        owner = next(r for r in rows if r['kind'] == 'reach_intent_publish'
                     and r['payload']['intent']['robot'] == 'tb1'
                     and r['payload']['intent']['intent_sequence'] == 5)
        actual = next(r for r in rows if r['kind'] == 'reach_driver_ingress')
        same_clock = owner['payload']['intent']['source_clock_ns']
        actual['payload']['message']['source_clock_ns'] = same_clock
        actual['payload']['raw_json'] = audit.canonical(actual['payload']['message']).decode()
        actual['sim_time_sec'] = owner['sim_time_sec']
        # A wall-time tie leaves the record ordering as the only distinction.
        owner['wall_monotonic_ns'] = actual['wall_monotonic_ns']
        normal = rows[-1]['payload']
        normal['intent']['lineage']['actuation_source_clock_ns'] = same_clock
        normal['payload_sha256'] = audit.sha(normal['intent'])
        self.assertEqual(owner['sim_time_sec'], actual['sim_time_sec'])
        self.equivalent((rows, information, peer))
        first, second = rows.index(owner), rows.index(actual)
        rows[first], rows[second] = rows[second], rows[first]
        self.renumber(rows)
        self.equivalent((rows, information, peer), error='no earlier real owner publication')

    def test_none_hold_target_coexists_with_real_owner_targets(self):
        rows, information, peer = normal_lineage_fixture()
        owner = next(r for r in rows if r['kind'] == 'reach_intent_publish'
                     and r['payload']['intent']['robot'] == 'tb1'
                     and r['payload']['intent']['intent_sequence'] == 2)
        null_hold = copy.deepcopy(owner['payload']['intent'])
        self.assertEqual(null_hold['role'], 'HOLD')
        self.assertEqual(null_hold['lineage'], {'release_clock_ns': None})
        self.assertIsNone(null_hold['anchor'])
        null_hold['target'] = None
        null_sha = audit.sha(null_hold)
        owner['payload'].update(intent=null_hold, payload_sha256=null_sha)
        decision = next(r for r in rows if r['kind'] == 'reach_decision'
                        and r['payload']['robot'] == 'tb1')
        decision['payload']['intent'] = copy.deepcopy(null_hold)
        # Bind the changed synthetic declaration in the actual control status.
        for row in rows:
            if row['kind'] == 'control_ack':
                ack = row['payload']
            elif row['kind'] == 'control_ack_published':
                ack = row['payload']['ack']
            else:
                continue
            for refs in (ack['intent_refs'], ack['status']['intent_refs']):
                self.assertEqual(refs['tb1']['intent_sequence'], 2)
                refs['tb1']['payload_sha256'] = null_sha
        self.equivalent((rows, information, peer))

    def test_two_applications_retain_the_earlier_complete_target_key(self):
        rows, information, peer = self.duplicate_case(early_good=True)
        duplicate = next(r for r in rows if r['kind'] == 'reach_intent_publish'
                         and r['payload']['intent']['robot'] == 'tb1'
                         and r['payload']['intent']['intent_sequence'] == 6)
        duplicate['payload']['intent']['target']['angular_z'] = .1
        duplicate['payload']['payload_sha256'] = audit.sha(duplicate['payload']['intent'])
        first = next(r for r in rows if r['kind'] == 'reach_driver_ingress')
        second = copy.deepcopy(first)
        packet = second['payload']['message']
        packet.update(actuation_sequence=2, cmd_seq=6, source_clock_ns=1_100_000_000,
                      target=copy.deepcopy(duplicate['payload']['intent']['target']))
        second['payload']['raw_json'] = audit.canonical(packet).decode()
        second.update(wall_monotonic_ns=409, sim_time_sec=1.1)
        rows.insert(rows.index(rows[-1]), second)
        self.renumber(rows)
        first_target = first['payload']['message']['target']
        self.assertEqual(first_target['clock_ns'], packet['target']['clock_ns'])
        self.assertEqual(first_target['decision_sequence'], packet['target']['decision_sequence'])
        self.assertNotEqual(audit.canonical(first_target), audit.canonical(packet['target']))
        self.assertEqual(rows[-1]['payload']['intent']['lineage']['actuation_sequence'], 1)
        # Only the earlier target's owner saw X. The newer target's owner saw
        # HOLD, so looking up the newest cached key cannot establish this N.
        self.equivalent((rows, information, peer))
        packet['target']['angular_z'] = .2
        second['payload']['raw_json'] = audit.canonical(packet).decode()
        self.equivalent((rows, information, peer), error='no earlier real owner publication')

    def test_bundle_hash_work_does_not_scale_with_publication_history(self):
        case = normal_lineage_fixture()
        rows, information, _ = case
        template = copy.deepcopy(information.complete_publications[0])
        for sequence in range(100, 1100):
            publication = copy.deepcopy(template)
            publication['message']['sequence'] = sequence
            publication['message_sha256'] = audit.sha(publication['message'])
            publication['publish_started_wall_monotonic_ns'] = 10_000 + sequence
            information.complete_publications.append(publication)
        self.equivalent(case)
        incoming = {id(r['payload']) for r in rows if r['kind'] == 'received_states'}
        calls = []
        real_sha = audit.sha

        def counted(value):
            if id(value) in incoming:
                calls.append(id(value))
            return real_sha(value)

        host, _ = audit.load_implementation()
        with patch.dict(audit.audit_motion.__globals__, sha=counted):
            audit.audit_motion(*case, EPOCH, host.BASE)
        self.assertEqual(len(calls), len(incoming))

    def test_empty_publications_keep_original_failure_without_incoming_hash(self):
        case = normal_lineage_fixture()
        case[1].complete_publications.clear()
        self.equivalent(case, error='motion received bundle absent')
        incoming = {id(r['payload']) for r in case[0] if r['kind'] == 'received_states'}
        calls = []
        real_sha = audit.sha

        def counted(value):
            if id(value) in incoming:
                calls.append(id(value))
            return real_sha(value)

        host, _ = audit.load_implementation()
        with patch.dict(audit.audit_motion.__globals__, sha=counted):
            with self.assertRaisesRegex(ValueError, 'motion received bundle absent'):
                audit.audit_motion(*case, EPOCH, host.BASE)
        self.assertEqual(calls, [])


    def repeated_dependency(self, case, component='state'):
        rows, information, peer = case
        index = next(i for i, row in enumerate(rows) if row['kind'] == 'control_dependency'
                     and row['payload']['component'] == component)
        duplicate = copy.deepcopy(rows[index])
        duplicate['wall_monotonic_ns'] += 1
        rows.insert(index+1, duplicate)
        self.renumber(rows)
        return duplicate

    def test_ack_unused_malformed_tail_is_not_eagerly_encoded(self):
        case = normal_lineage_fixture()
        case[1].ack_publications.extend([
            {'start': 1, 'ack': {'invalid': float('nan')}},
            {'start': 100_000, 'ack': {'invalid': float('nan')}},
            {},
        ])
        self.repeated_dependency(case)
        self.equivalent(case)

    def test_ack_former_future_before_cached_match_keeps_first_error(self):
        case = normal_lineage_fixture()
        duplicate = self.repeated_dependency(case)
        case[1].ack_publications.insert(1, {
            'start': duplicate['wall_monotonic_ns'], 'ack': {'invalid': float('nan')},
        })
        self.equivalent(case, error='Out of range float values')

    def test_ack_same_full_payload_future_and_past_duplicates_are_retained(self):
        case = normal_lineage_fixture()
        duplicate = self.repeated_dependency(case)
        publication = copy.deepcopy(case[1].ack_publications[-1])
        publication['start'] = duplicate['wall_monotonic_ns']
        case[1].ack_publications.insert(1, publication)
        self.equivalent(case)

    def test_ack_same_id_changed_full_payload_and_numeric_encoding_are_rejected(self):
        for published, received in ((0, 0.0), (0.0, -0.0), ('a', 'b')):
            with self.subTest(published=repr(published), received=repr(received)):
                case = normal_lineage_fixture()
                row = next(r for r in case[0] if r['kind'] == 'control_dependency'
                           and r['payload']['component'] == 'state')
                row['payload']['value']['unused_full_wire_field'] = received
                case[1].ack_publications[-1]['ack']['unused_full_wire_field'] = published
                self.equivalent(case, error='motion dependency not actual earlier published complete ACK')

    def test_ack_component_history_cannot_be_reused_for_another_publisher(self):
        case = normal_lineage_fixture()
        case[2].ack_publications.clear()
        peer_ack = next(r['payload']['value'] for r in case[0] if r['kind'] == 'control_dependency'
                        and r['payload']['component'] == 'peer')
        case[1].ack_publications.append({'start': 1, 'ack': copy.deepcopy(peer_ack)})
        self.equivalent(case, error='motion dependency not actual earlier published complete ACK')

    def test_ack_no_eligible_source_does_not_encode_bad_query(self):
        for empty in (False, True):
            with self.subTest(empty=empty):
                case = normal_lineage_fixture()
                if empty:
                    case[1].ack_publications.clear()
                else:
                    for publication in case[1].ack_publications:
                        publication['start'] = 100_000
                row = next(r for r in case[0] if r['kind'] == 'control_dependency')
                row['payload']['value']['invalid'] = float('nan')
                self.equivalent(case, error='motion dependency not actual earlier published complete ACK')

    def test_ack_bad_source_error_precedes_bad_query_encoding(self):
        case = normal_lineage_fixture()
        case[1].ack_publications[:] = [{'start': 1}]
        row = next(r for r in case[0] if r['kind'] == 'control_dependency')
        row['payload']['value']['invalid'] = float('nan')
        self.equivalent(case, error='ack')

    def test_ack_source_attributes_are_not_read_before_motion_prefix_validation(self):
        self.equivalent(([{}], SimpleNamespace(), SimpleNamespace()), error='ledger row exact fields')


class AckPublicationIndexTests(unittest.TestCase):
    @staticmethod
    def outcome(call):
        try:
            return 'returned', call()
        except Exception as error:
            return 'error', type(error).__name__, str(error)

    def compare(self, publications, queries):
        index = audit._AckPublicationIndex(publications)
        for ack, wall in queries:
            before = self.outcome(lambda: any(p['start'] <= wall
                and audit.canonical(p['ack']) == audit.canonical(ack) for p in publications))
            after = self.outcome(lambda: index.contains(ack, wall))
            self.assertEqual(before, after)
        return index

    def test_nondecreasing_queries_keep_offsets_duplicates_and_original_references(self):
        ack = {'request_id': 'same', 'nested': [0.0]}
        publications = [{'start': 20, 'ack': copy.deepcopy(ack)},
                        {'start': 10, 'ack': copy.deepcopy(ack)}]
        before = copy.deepcopy(publications)
        index = self.compare(publications, [(ack, 9), (ack, 10), (ack, 19), (ack, 20), (ack, 21)])
        matches = index.by_payload[audit.canonical(ack)]
        self.assertEqual([position for position, _ in matches], [0, 1])
        self.assertIs(matches[0][1], publications[0]); self.assertIs(matches[1][1], publications[1])
        self.assertEqual(publications, before)

    def test_future_bad_source_becomes_eligible_before_cached_match(self):
        ack = {'request_id': 'same'}
        publications = [{'start': 11, 'ack': {'bad': float('nan')}}, {'start': 1, 'ack': ack}]
        self.compare(publications, [(ack, 10), (ack, 11)])

    def test_empty_future_and_bad_source_query_exception_priority(self):
        bad = {'bad': float('nan')}
        for publications, queries in (([], [(bad, 1)]),
                ([{'start': 2, 'ack': bad}], [(bad, 1), (bad, 2)]),
                ([{'start': 1}], [(bad, 1)]),
                ([{'start': 1, 'ack': {'good': True}}], [(bad, 1)])):
            with self.subTest(publications=repr(publications)):
                self.compare(publications, queries)

    def test_full_wire_encoding_and_unreached_tail_remain_exact(self):
        publications = [{'start': 1, 'ack': {'id': 'same', 'n': 0}},
                        {'start': 2, 'ack': {'id': 'same', 'n': 0.0}},
                        {'start': 3, 'ack': {'id': 'same', 'n': -0.0}}, {}]
        self.compare(publications, [({'n': 0, 'id': 'same'}, 1),
            ({'id': 'same', 'n': 0.0}, 2), ({'id': 'same', 'n': -0.0}, 3),
            ({'id': 'same', 'n': 0}, 4)])

    def test_canonical_work_is_linear_in_reached_ack_publications_and_queries(self):
        publications = [{'start': n, 'ack': {'request_id': str(n), 'payload': list(range(10))}}
                        for n in range(1, 101)]
        queries = [(copy.deepcopy(p['ack']), p['start']) for p in publications]
        ids = {id(p['ack']) for p in publications}; calls = Counter()
        original = audit.canonical
        def counted(value):
            calls['publication' if id(value) in ids else 'query'] += 1
            return original(value)
        index = audit._AckPublicationIndex(publications)
        with patch.dict(index.contains.__globals__, canonical=counted):
            for ack, wall in queries:
                self.assertTrue(index.contains(ack, wall))
        self.assertEqual(calls, {'publication': 100, 'query': 100})


if __name__ == '__main__':
    unittest.main()
