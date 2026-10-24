"""Independent v2 release dispatch checks; synthetic facts are not native credit."""
import copy
import hashlib
from pathlib import Path
import unittest

from mr3_learning import audit_reach_controlled_physics as dispatch
from mr3_learning.tests import test_audit_reach_peer_control as fixture


class ReachControlledDispatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module, cls.proof = dispatch.load_impl()
        cls.host, _ = fixture.audit.load_implementation()

    def data(self):
        value = fixture.make_fixture()
        status = next(r['payload']['status'] for r in value['motion_safety.jsonl']
                      if r['kind'] == 'output_completed'
                      and r['payload']['status']['clock_ns'] == fixture.RELEASE)
        value['transitions.jsonl'][0]['info']['initial_motion_status'] = copy.deepcopy(status)
        return value

    def check(self, value):
        phases = {name: self.module._phase_receipt(value['control_phase_worker.jsonl'], name,
                  'commit', fixture.RELEASE, fixture.EPOCH) for name in ('state', 'peer', 'motion')}
        return dispatch.verify_release_safety(value['metadata.json'], value['transitions.jsonl'][0], phases,
            value['information_states.jsonl'], value['peer_phase.jsonl'], value['motion_safety.jsonl'], self.host.BASE)

    def test_whole_source_inverse_loads_and_keeps_full_safety_input(self):
        self.assertTrue(self.proof['whole_source_inverse_equal'])
        self.assertEqual(self.proof['source_sha256'], dispatch.SOURCE_SHA256)
        self.assertEqual(self.proof['inverse_sha256'], dispatch.SOURCE_SHA256)
        source = Path(self.module.__file__).read_bytes()
        self.assertEqual(hashlib.sha256(source).hexdigest(), dispatch.SOURCE_SHA256)
        self.assertEqual(len(self.proof['literal_changes']), 5)
        self.assertEqual(self.module.CONTROL_PROTOCOL, dispatch.CONTROL_PROTOCOL)
        self.assertEqual(self.module.CONTROLLED_HANDSHAKE, dispatch.CONTROLLED_HANDSHAKE)
        self.assertIs(self.module.audit_motion, fixture.audit.audit_episode)

    def test_full_v2_release_preserves_consumed_table_and_new_owner_refs(self):
        value = self.data(); result = self.check(value)
        self.assertEqual(result['safety_contract'], 'mr3-reach-v1')
        self.assertNotEqual(result['intent_refs'], result['new_owner_intent_refs'])
        self.assertEqual(set(result['intent_refs']), set(fixture.NAMES))

    def test_v1_or_legacy_cannot_claim_new_release(self):
        for key, replacement in (('safety_contract', 'legacy'),
                                 ('execution_phase_protocol', 'mr3-controlled-execution-phase-v1')):
            value = self.data(); value['metadata.json'][key] = replacement
            with self.subTest(key=key), self.assertRaises(ValueError): self.check(value)

    def test_peer_cannot_omit_additional_safety_inputs(self):
        value = self.data()
        for row in value['control_phase_worker.jsonl']:
            if row.get('component') == 'peer' and row.get('ack', {}).get('operation') == 'commit':
                row['ack']['inputs'].pop('safety')
        with self.assertRaises(ValueError): self.check(value)

    def test_exact_complete_per_robot_safety_digest_is_required(self):
        value = self.data()
        for row in value['control_phase_worker.jsonl']:
            if row.get('component') == 'state' and row.get('ack', {}).get('operation') == 'commit':
                row['ack']['robots']['tb1']['safety_sha256'] = '0'*64
        with self.assertRaises(ValueError): self.check(value)

    def test_expected_intents_cannot_be_new_owner_refs(self):
        value = self.data()
        request = next(r['request'] for r in value['control_phase_worker.jsonl']
                       if r['kind'] == 'request' and r['component'] == 'state'
                       and r['request']['operation'] == 'commit')
        request['expected_intents'] = copy.deepcopy(value['transitions.jsonl'][0]['info']['initial_motion_status']['intent_refs'])
        with self.assertRaises(ValueError): self.check(value)

    def test_missing_actual_guard_bundle_ingress_is_not_covered_by_peer_ack(self):
        value = self.data()
        value['motion_safety.jsonl'][:] = [r for r in value['motion_safety.jsonl'] if r['kind'] != 'reach_state_ingress']
        with self.assertRaisesRegex(ValueError, 'actual whole-bundle'): self.check(value)

    def test_guard_raw_string_and_graph_owner_are_bound(self):
        for tamper in ('raw', 'owner'):
            value = self.data()
            ingress = next(r['payload'] for r in value['motion_safety.jsonl'] if r['kind'] == 'reach_state_ingress')
            if tamper == 'raw': ingress['raw_json'] = '{}'
            else: ingress['publisher_identity']['endpoints'][0]['node_name'] = 'imposter'
            with self.subTest(tamper=tamper), self.assertRaises(ValueError): self.check(value)

    def test_new_owner_refs_require_actual_publication_not_consumed_table(self):
        value = self.data()
        value['motion_safety.jsonl'][:] = [r for r in value['motion_safety.jsonl']
            if not (r['kind'] == 'reach_intent_publish' and r['payload']['robot'] == 'tb2'
                    and r['payload']['intent']['intent_sequence'] == 2)]
        with self.assertRaisesRegex(ValueError, 'actual intent publication'): self.check(value)

    def test_consumer_cannot_precede_actual_owner_publish_return(self):
        value = self.data()
        owner = next(r for r in value['motion_safety.jsonl'] if r['kind'] == 'reach_intent_publish'
                     and r['payload']['intent']['intent_sequence'] == 2)
        owner['payload']['publish_completed_wall_monotonic_ns'] = 10**9
        with self.assertRaisesRegex(ValueError, 'publication order'): self.check(value)

    def test_unknown_metadata_is_not_discarded_before_original_math(self):
        value = self.data()
        publication = next(r['payload'] for r in value['information_states.jsonl'] if r['kind'] == 'state_publish')
        publication['message']['robots'][0]['safety']['intent']['ignored_extra'] = True
        with self.assertRaises(ValueError): self.check(value)


if __name__ == '__main__':
    unittest.main()
