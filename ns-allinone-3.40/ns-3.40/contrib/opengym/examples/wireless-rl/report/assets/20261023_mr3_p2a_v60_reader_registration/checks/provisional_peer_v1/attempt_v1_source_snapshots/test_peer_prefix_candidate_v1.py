"""Artificial CPU fixtures. No saved V59 raw inputs, World, or native credit."""
import copy
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch, Mock

ROOT = Path('/home/zhuyulab/ns3-workspace')
WIRELESS = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
DRAFT = Path(__file__).resolve().parent
RELATIVE = WIRELESS.relative_to(ROOT) / 'mr3_learning'
sys.path.insert(0, str(WIRELESS))


def candidate(name):
    fullname = 'mr3_learning.' + name
    path = DRAFT / 'candidate' / RELATIVE / (name + '.py')
    spec = importlib.util.spec_from_file_location(fullname, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[fullname] = module
    spec.loader.exec_module(module)
    setattr(importlib.import_module('mr3_learning'), name, module)
    return module


# Load the prospective modules only in this isolated CPU process. Repository
# files stay unchanged. The copied source has a /tmp __file__; use the real
# immutable helper root explicitly rather than treating /tmp as a source freeze.
audit = candidate('audit_reach_peer_control')
audit.ROOT = ROOT
audit.load_impl.__defaults__ = (ROOT,)
controlled = candidate('audit_reach_controlled_physics')
preparation = candidate('audit_reach_preparation')
preparation.WIRELESS = WIRELESS
policy_audit = candidate('audit_reach_ppo')
policy_audit.WORKSPACE = ROOT
plan_builder = candidate('reach_preparation')
policy = candidate('reach_policy_chain')
fixture = importlib.import_module('mr3_learning.tests.test_audit_reach_peer_control')
fixture.audit = audit
motor_fixture = importlib.import_module('mr3_learning.tests.test_initial_encoder_replay')
encoder = audit.encoder_replay
EPOCH, FREEZE = fixture.EPOCH, fixture.FREEZE
PROFILE, SHA = encoder.PROFILE, motor_fixture.SHA


def graph(robot):
    return {'scope': 'graph_at_callback', 'valid': True,
            'packet_publisher_gid_available': False, 'error': None,
            'topic': f'/{robot}/mr3_drive/applied',
            'endpoints': [{'node_namespace': '/' + robot,
                           'node_name': 'turtlebot3_diff_drive',
                           'topic_type': 'std_msgs/msg/String',
                           'endpoint_gid': '42' * 24}]}


def new_fixture():
    data = fixture.make_fixture()
    data['metadata.json']['actuation_profile'] = PROFILE
    for robot in audit.ROBOTS:
        value = motor_fixture.Fixture()
        value.receive(fixture.T0)
        value.act(fixture.T0 + 14_000_000)
        value.receive(fixture.RELEASE)
        value.receive(fixture.FINAL)
        rows = json.loads(encoder.canonical(value.rows).replace(motor_fixture.EPOCH, EPOCH)
                          .replace('"tb1"', '"' + robot + '"'))
        data['drive_' + robot + '.jsonl'] = rows
        messages = json.loads(encoder.canonical(value.messages).replace(motor_fixture.EPOCH, EPOCH)
                              .replace('"tb1"', '"' + robot + '"'))
        message = messages[0]
        row = {'schema': 'mr3-motion-safety-v1', 'epoch': EPOCH,
               'record_sequence': 0, 'kind': 'reach_driver_ingress',
               'sim_time_sec': (fixture.T0 + 14_000_000) / 1e9,
               'wall_monotonic_ns': 160 + audit.ROBOTS.index(robot),
               'payload': {'robot': robot, 'kind': 'applied', 'message': message,
                           'raw_json': encoder.canonical(message),
                           'publisher_identity': graph(robot)}}
        data['motion_safety.jsonl'].append(row)
    data['motion_safety.jsonl'].sort(key=lambda row: row['wall_monotonic_ns'])
    for index, row in enumerate(data['motion_safety.jsonl'], 1):
        row['record_sequence'] = index
    return data


def context(data):
    return {'actuation_profile': PROFILE, 'epoch': EPOCH, 'freeze': FREEZE,
            'helper_sha256': SHA,
            'reach_build_bridge_proof': {'actuation_profile': PROFILE,
                'new_build_executed': True,
                'initial_encoder_compiled_source': {'sha256': SHA}},
            'configurations': {robot: {row['kind']: copy.deepcopy(row)
                for row in data['drive_' + robot + '.jsonl']
                if row['kind'] in ('configuration', 'initial_encoder_configuration')}
                for robot in audit.ROBOTS}}


def write_fixture(directory, data):
    for name, value in data.items():
        content = (''.join(json.dumps(row, allow_nan=False) + '\n' for row in value)
                   if name.endswith('.jsonl') else json.dumps(value, allow_nan=False))
        (directory / name).write_text(content)


class NewPrefixTests(unittest.TestCase):
    def setUp(self):
        self.core, _ = audit.load_impl()
        self.host, _ = audit.load_implementation()

    def replay(self, data, proof=None):
        return audit.replay_records(data, self.core, self.host,
                                    native_context=context(data) if proof is None else proof)

    def test_old_branch_and_immutable_whole_inverse_remain_exact(self):
        result = audit.replay_records(fixture.make_fixture(), self.core, self.host)
        self.assertTrue(result['passed'])
        self.assertNotIn('initial_encoder_native_prefix', result)
        _, provenance = audit.load_impl()
        self.assertTrue(provenance['whole_inverse_exact'])
        self.assertEqual(provenance['whole_inverse_sha256'], audit.ORIGINAL_SHA)
        self.assertEqual(len(provenance['identity_only_source_edits']), 9)

    def test_complete_new_prefix_replays_all_three_without_dropping_rows(self):
        data = new_fixture()
        saved = copy.deepcopy(data)
        calls = []
        original = self.core.native_receipts
        def observe(rows, epoch, robot):
            self.assertIs(rows, data['drive_' + robot + '.jsonl'])
            self.assertIn('initial_encoder_receive', {row['kind'] for row in rows})
            calls.append(robot)
            return original(rows, epoch, robot)
        with patch.object(self.core, 'native_receipts', side_effect=observe):
            result = self.replay(data)
        self.assertEqual(calls, list(audit.ROBOTS))
        self.assertEqual(data, saved)
        self.assertTrue(result['initial_encoder_compound_replay_passed'])
        self.assertFalse(result['initial_encoder_native_prefix']['native_inputs_normalized'])
        self.assertEqual(result['initial_encoder_native_prefix']
                         ['retained_current_epoch_applied_callbacks_joined'], dict.fromkeys(audit.ROBOTS, 1))

    def test_new_events_without_explicit_profile_still_fail(self):
        data = new_fixture(); data['metadata.json'].pop('actuation_profile')
        with self.assertRaisesRegex(ValueError, 'complete identity/record prefix'):
            audit.replay_records(data, self.core, self.host)

    def test_new_profile_without_context_fails_before_accepting_new_events(self):
        with self.assertRaisesRegex(ValueError, 'profile/epoch/freeze'):
            audit.replay_records(new_fixture(), self.core, self.host)

    def test_wrong_profile_or_old_build_or_helper_is_rejected(self):
        for field, value in [('actuation_profile', 'old'), ('new_build_executed', False),
                             ('initial_encoder_compiled_source', {'sha256': 'e' * 64})]:
            data = new_fixture(); proof = context(data)
            proof['reach_build_bridge_proof'][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'new-build/helper'):
                self.replay(data, proof)

    def test_unknown_event_and_record_gap_and_missing_receive_rejected(self):
        for operation in ('unknown', 'gap', 'missing_receive'):
            data = new_fixture(); rows = data['drive_tb2.jsonl']
            if operation == 'unknown': rows[1]['kind'] = 'initial_encoder_fabricated'
            elif operation == 'gap': rows[-1]['record_sequence'] += 1
            else:
                rows[:] = [row for row in rows if row['kind'] != 'initial_encoder_receive']
                for i, row in enumerate(rows, 1): row['record_sequence'] = i
            with self.subTest(operation=operation), self.assertRaises(ValueError): self.replay(data)

    def test_original_received_target_and_real_motor_readback_remain_checked(self):
        for operation in ('target', 'readback', 'reference'):
            data = new_fixture()
            if operation == 'target':
                next(row for row in data['drive_tb1.jsonl'] if row['kind'] == 'command_received')['desired_w'] = .2
            else:
                nested = next(row for row in data['drive_tb1.jsonl'] if row['kind'] == 'actuation')['initial_encoder_hold']
                nested['readback_motor_target_radps' if operation == 'readback' else 'reference_rad'][0] += .01
            with self.subTest(operation=operation), self.assertRaises(ValueError): self.replay(data)

    def test_actual_applied_pair_and_raw_json_and_graph_join_are_not_ignored(self):
        for operation in ('pair', 'raw_json', 'graph'):
            data = new_fixture()
            payload = next(row['payload'] for row in data['motion_safety.jsonl'] if row['kind'] == 'reach_driver_ingress')
            if operation == 'pair':
                payload['message']['pairs'][0]['applied_rim_mps'][0] += .001
                payload['raw_json'] = encoder.canonical(payload['message'])
            elif operation == 'raw_json': payload['raw_json'] = '{}'
            else: payload['publisher_identity']['endpoints'][0]['node_name'] = 'imposter'
            with self.subTest(operation=operation), self.assertRaises(ValueError): self.replay(data)

    def test_true_nonzero_feedback_keeps_body_desired_zero(self):
        value = motor_fixture.base()
        rows = value.rows
        proof = encoder.replay_native_drive(rows, profile=PROFILE, epoch=motor_fixture.EPOCH,
                                            robot='tb1', helper_sha256=SHA)
        last = [row for row in rows if row['kind'] == 'actuation'][-1]
        self.assertEqual(last['desired_rim_mps'], [0., 0.])
        self.assertNotEqual(last['applied_rim_mps'], [0., 0.])
        self.assertTrue(encoder.check_applied_receipt(value.messages[-1], proof))

    def test_public_episode_route_requires_context_and_reaches_real_fifo(self):
        data = new_fixture()
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp); write_fixture(directory, data)
            with patch.object(audit, 'native_profile_context', return_value=context(data)) as selected:
                result = audit.audit_episode(directory, FREEZE, plan_path='/synthetic/plan.json')
            self.assertTrue(result['passed'], result['errors'])
            selected.assert_called_once_with(directory, data['metadata.json'], '/synthetic/plan.json')
            self.assertTrue(result['initial_encoder_compound_replay_passed'])
            with patch.object(audit, 'native_profile_context', side_effect=ValueError('newbuild rejected')):
                failed = audit.audit_episode(directory, FREEZE, plan_path='/synthetic/plan.json')
            self.assertFalse(failed['passed']); self.assertEqual(failed['errors'], ['newbuild rejected'])

    def test_public_cli_forwards_exact_audit_plan(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'result.json'
            with patch.object(audit, 'audit_episode', return_value={'passed': True}) as called:
                self.assertEqual(audit.main([temp, '--freeze', FREEZE, '--plan', '/synthetic/plan.json', '--output', str(output)]), 0)
            called.assert_called_once_with(Path(temp), FREEZE, plan_path=Path('/synthetic/plan.json'))

    def test_context_reuses_real_source_and_native_binding_configuration_apis(self):
        data = new_fixture(); proof = context(data)
        configs = [{'path': '/synthetic/drive_' + robot + '.jsonl', 'configuration': row}
                   for robot, rows in proof['configurations'].items() for row in rows.values()]
        read = Mock(); read.bindings = {'synthetic': {'sha256': '0' * 64}}
        bound = {'document': {'actuation_profile': PROFILE,
                   'initial_encoder_compiled_source': {'sha256': SHA}},
                 'reader': read, 'path': '/synthetic/binding.json', 'sha256': '2' * 64,
                 'reach_build_bridge_proof': proof['reach_build_bridge_proof']}
        native = SimpleNamespace(load_binding=Mock(return_value=bound), configurations=Mock(return_value=configs))
        plan = {'actuation_profile': PROFILE, 'custody_binding': '/synthetic/binding.json'}
        with patch.object(plan_builder, 'load_plan', return_value=plan) as loaded, \
             patch.object(plan_builder, 'source_check', return_value={'synthetic': 'source'}) as source, \
             patch.object(audit.custody, 'load_implementation', return_value=(native, {})):
            actual = audit.native_profile_context('/synthetic/episode', data['metadata.json'], '/synthetic/plan.json')
        loaded.assert_called_once_with(Path('/synthetic/plan.json'), ROOT)
        source.assert_called_once_with(plan, Path('/synthetic/plan.json'), FREEZE, ROOT, require_clean=False)
        native.load_binding.assert_called_once_with('/synthetic/binding.json', FREEZE, root=ROOT)
        native.configurations.assert_called_once_with(Path('/synthetic/episode'), bound)
        read.finish.assert_called_once_with()
        self.assertEqual(actual['helper_sha256'], SHA)
        with self.assertRaisesRegex(ValueError, 'exact source plan'):
            audit.native_profile_context('/synthetic/episode', data['metadata.json'], None)

    def test_full_preparation_projection_and_controlled_fallback_forward_plan(self):
        with tempfile.TemporaryDirectory() as temp:
            plan_path = Path(temp) / 'plan.json'; plan_path.write_text('{}')
            loaded, _ = preparation.load_impl(plan_path)
            with patch.object(audit, 'audit_episode', return_value={'passed': True}) as called:
                loaded.audit_motion(Path(temp) / 'episode')
            called.assert_called_once_with(Path(temp) / 'episode', plan_path=plan_path)
            module, _ = controlled.load_impl(plan_path=plan_path)
            with patch.object(audit, 'audit_episode', return_value={'passed': True}) as called:
                module.audit_motion(Path(temp) / 'episode')
            called.assert_called_once_with(Path(temp) / 'episode', plan_path=plan_path)

    def test_full_ppo_episode_conjunction_forwards_plan(self):
        shared = {'passed': True, 'safety_contract': 'mr3-reach-v1', 'freeze': FREEZE}
        native_runtime = {'passed': True, 'contract': 'mr3-reach-v1', 'freeze': FREEZE,
                          'independent_necessary_replay': True, 'continuous_physical_model_proved': False}
        archive = SimpleNamespace(audit_archives=Mock(return_value=shared), audit_activity=Mock(return_value=shared),
                                  audit_execution_inputs=Mock(return_value=shared))
        with patch.object(policy_audit.audit_reach_information, 'audit_episode', return_value=shared), \
             patch.object(policy_audit.audit_reach_runtime, 'audit_episode', return_value=native_runtime), \
             patch.object(audit, 'audit_episode', return_value=shared) as called:
            result = policy_audit.audit_episode_conjunction('/synthetic/episode', FREEZE, archive,
                                                           plan_path=Path('/synthetic/plan.json'))
        self.assertTrue(result['passed'], result['errors'])
        called.assert_called_once_with(Path('/synthetic/episode'), FREEZE, plan_path=Path('/synthetic/plan.json'))

    def test_policy_public_fifo_jobs_include_plan_only_for_selected_new_profile(self):
        plan = {'learner_python': '/synthetic/python', 'custody_binding': '/synthetic/binding.json',
                'actuation_profile': PROFILE}
        spec = {'output_directory': '/synthetic/output', 'run_directory': '/synthetic/run'}
        for selected in (True, False):
            value = copy.deepcopy(plan)
            if not selected: value.pop('actuation_profile')
            jobs = policy.jobs_for_stage(value, '/synthetic/plan.json', '/synthetic/qual.json',
                                         spec, [Path('/synthetic/episode')])
            argv = next(job['argv'] for job in jobs if job['id'] == 'fifo_001')
            self.assertEqual('--plan' in argv, selected)
            if selected: self.assertEqual(argv[argv.index('--plan') + 1], '/synthetic/plan.json')


if __name__ == '__main__':
    unittest.main()
