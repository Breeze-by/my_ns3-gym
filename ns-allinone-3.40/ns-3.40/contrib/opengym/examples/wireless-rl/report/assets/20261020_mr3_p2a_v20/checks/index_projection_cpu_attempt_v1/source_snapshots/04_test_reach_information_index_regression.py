"""Compare the indexed consumer with its frozen pre-optimization oracle.

These synthetic prefixes exercise ownership and callback matching only. They
do not establish native admission or the validity of an exploration policy.
"""
import ast
import copy
import hashlib
from pathlib import Path
import subprocess
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


if __name__ == '__main__':
    unittest.main()
