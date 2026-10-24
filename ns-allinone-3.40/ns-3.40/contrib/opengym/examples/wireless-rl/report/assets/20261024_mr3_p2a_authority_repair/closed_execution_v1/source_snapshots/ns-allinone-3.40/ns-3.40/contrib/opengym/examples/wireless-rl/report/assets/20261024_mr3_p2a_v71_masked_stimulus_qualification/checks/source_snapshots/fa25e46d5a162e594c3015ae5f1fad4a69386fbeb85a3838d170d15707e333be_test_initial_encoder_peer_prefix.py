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
from mr3_learning import audit_reach_peer_control as audit
from mr3_learning import audit_reach_controlled_physics as controlled
from mr3_learning import audit_reach_preparation as preparation
from mr3_learning import audit_reach_ppo as policy_audit
from mr3_learning import reach_preparation as plan_builder
from mr3_learning import reach_policy_chain as policy
from mr3_learning import audit_reach_reset_workload as workload
from mr3_learning.tests.test_audit_reach_ppo import artificial_authority_report, PROFILE as AUTHORITY_PROFILE
fixture = importlib.import_module('mr3_learning.tests.test_audit_reach_peer_control')
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


def authority_fixture():
    """Complete declared all-zero authority stream, not a bypassed oracle."""
    data=new_fixture();data['metadata.json']['motion_authority_profile']=AUTHORITY_PROFILE
    motion=data['motion_safety.jsonl'];motion[0]['payload'].update(
        robots=list(audit.ROBOTS),motion_authority_profile=AUTHORITY_PROFILE)
    def add(kind,payload,wall,clock):
        motion.append(dict(schema='mr3-motion-safety-v1',epoch=EPOCH,record_sequence=0,kind=kind,
            wall_monotonic_ns=wall,sim_time_sec=clock/1e9,payload=payload))
    def feed(robot,kind,message,wall,clock):
        identity=graph(robot)
        identity['topic']=f'/{robot}/mr3_drive/'+dict(applied='applied',storage='status',calibration='odometry_calibration')[kind]
        add('reach_driver_ingress',dict(robot=robot,kind=kind,message=message,
            raw_json=encoder.canonical(message),publisher_identity=identity),wall,clock)
    for j,robot in enumerate(audit.ROBOTS):
        identity=graph(robot);identity['topic']=f'/{robot}/mr3/motion_authority'
        identity['endpoints'][0].update(node_name='mr3_adapter',node_namespace='/')
        add('authority_configuration',dict(robot=robot,motion_authority_profile=AUTHORITY_PROFILE,
            publisher_identity=identity,scope='unique graph endpoint binding only; not packet authentication'),6+j,fixture.T0)
        odoms=[dict(schema='mr3-world-odometry-publication-v1',epoch=EPOCH,robot=robot,kind='configuration',
            record_sequence=1,provider='WORLD',period_ns=20_000_000,phase='world_update_begin_before_actuation')]
        for n,source in enumerate((fixture.sample.SOURCE,fixture.sample.SOURCE+20_000_000,fixture.sample.SOURCE+40_000_000),1):
            raw=fixture.odom(robot);raw['header']['stamp']=fixture.sample.stamp(source)
            odoms.append(dict(schema='mr3-world-odometry-publication-v1',epoch=EPOCH,robot=robot,kind='publication',
                record_sequence=n+1,publication_sequence=n,source_clock_ns=source,sim_time_ns=source,odometry=raw,
                odom_published=True,odom_tf_published=True,publication_scope='actual_publisher_calls_returned_not_delivery'))
            wall=(13,235,580)[n-1];clock=(fixture.T0,fixture.RELEASE,fixture.FINAL)[n-1]
            if n>1:add('own_odom',dict(robot=robot,input_sequence=n,message=copy.deepcopy(raw)),wall,clock)
            calibration=fixture.sample.calibration(robot)
            calibration.update(source_clock_ns=source,publication_sequence=n,odometry=copy.deepcopy(raw))
            feed(robot,'calibration',calibration,wall+1,clock)
        data['odometry_'+robot+'.jsonl']=odoms
        for row in data['drive_'+robot+'.jsonl']:
            if row['kind']!='command_received':continue
            seq=row['cmd_seq'];clock=row['sim_time_ns']
            feed(robot,'storage',dict(schema='mr3-drive-target-consumed-v1',epoch=EPOCH,robot=robot,
                clock_ns=clock,source_clock_ns=row['target_clock_ns'],decision_sequence=row['target_decision_sequence'],
                cmd_seq=seq,linear_x=0.,angular_z=0.),{1:39,2:343,3:639}[seq],clock)
    for row in motion:
        if row['kind']!='reach_decision':continue
        value=row['payload'];value.update(motion_authority_profile=AUTHORITY_PROFILE,effective_request=[0.,0.],
            motion_authority=dict(effective_request=[0.,0.],permission='zero_only',authority_sequence=0,owner=None,
                state='NONE',fault=None,callback_floor=0,raw_input_sequence=None,raw_goal_generation=None,
                raw_goal_association='UNKNOWN_UNSTAMPED_TWIST',
                claim='receiving permission only; callback floor is not generation time'))
    motion.sort(key=lambda row:row['wall_monotonic_ns'])
    for n,row in enumerate(motion,1):row['record_sequence']=n
    data['adapter.jsonl']=[dict(epoch=EPOCH,stamp=fixture.T0/1e9,kind='authority_configuration',payload=dict(
        motion_authority_profile=AUTHORITY_PROFILE,six_navigation_phases_unchanged=True,
        worker_quantum_ack_barrier=False,raw_goal_generation=None,raw_goal_association='UNKNOWN_UNSTAMPED_TWIST'))]
    data['supervisor_metadata.json']=dict(data['metadata.json'])
    data['benchmark_metadata.json']=dict(preparation_motion_probe=False)
    return data


def context(data):
    return {'actuation_profile': PROFILE, 'epoch': EPOCH, 'freeze': FREEZE,
            **({'motion_authority_profile':data['metadata.json']['motion_authority_profile']}
               if 'motion_authority_profile' in data['metadata.json'] else {}),
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
        data = authority_fixture()
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
        data = authority_fixture(); proof = context(data)
        configs = [{'path': '/synthetic/drive_' + robot + '.jsonl', 'configuration': row}
                   for robot, rows in proof['configurations'].items() for row in rows.values()]
        read = Mock(); read.bindings = {'synthetic': {'sha256': '0' * 64}}
        bound = {'document': {'actuation_profile': PROFILE,
                   'safety_contract':'mr3-reach-v1','motion_authority_profile':AUTHORITY_PROFILE,
                   'initial_encoder_compiled_source': {'sha256': SHA}},
                 'reader': read, 'path': '/synthetic/binding.json', 'sha256': '2' * 64,
                 'reach_build_bridge_proof': proof['reach_build_bridge_proof']}
        native = SimpleNamespace(load_binding=Mock(return_value=bound), configurations=Mock(return_value=configs))
        plan = {'actuation_profile': PROFILE,'safety_contract':'mr3-reach-v1',
                'motion_authority_profile':AUTHORITY_PROFILE,'custody_binding': '/synthetic/binding.json'}
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
            with patch.object(audit, 'audit_episode', return_value={'passed': True}) as called:
                module, _ = controlled.load_impl(plan_path=plan_path)
                module.audit_motion(Path(temp) / 'episode')
            called.assert_called_once_with(Path(temp) / 'episode', plan_path=plan_path)

    def test_public_full_audit_route_reaches_real_new_profile_peer_prefix(self):
        data = authority_fixture()
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp) / 'episode'; directory.mkdir()
            write_fixture(directory, data)
            plan_path = Path(temp) / 'plan.json'; plan_path.write_text(json.dumps(dict(
                safety_contract='mr3-reach-v1',motion_authority_profile=AUTHORITY_PROFILE,
                reset_workload_reader_profile=workload.PROFILE)))
            loaded, proof = preparation.load_impl(plan_path)
            # The full task/native evaluator is outside this artificial route
            # test. Its callback invokes the actual projected motion hook and
            # real public peer replay on the complete decoded CPU fixture.
            loaded.audit = lambda directory, root, freeze: loaded.audit_motion(directory)
            with patch.object(preparation, 'load_impl', return_value=(loaded, proof)), \
                 patch.object(audit, 'native_profile_context', return_value=context(data)) as selected:
                result = preparation.audit(directory, ROOT, FREEZE, plan_path)
            self.assertTrue(result['passed'], result.get('errors'))
            self.assertTrue(result['initial_encoder_compound_replay_passed'])
            selected.assert_called_once_with(directory, data['metadata.json'], plan_path)

    def test_full_ppo_episode_conjunction_forwards_plan(self):
        shared = artificial_authority_report(safety_contract='mr3-reach-v1',freeze=FREEZE)
        native_runtime = artificial_authority_report(contract='mr3-reach-v1',freeze=FREEZE,
                          independent_necessary_replay=True,continuous_physical_model_proved=False)
        archive = SimpleNamespace(audit_archives=Mock(return_value=shared), audit_activity=Mock(return_value=shared),
                                  audit_execution_inputs=Mock(return_value=shared))
        with tempfile.TemporaryDirectory() as temp, patch.object(policy_audit.audit_reach_information, 'audit_episode', return_value=shared), \
             patch.object(policy_audit.audit_reach_runtime, 'audit_episode', return_value=native_runtime), \
             patch.object(audit, 'audit_episode', return_value=shared) as called:
            directory=Path(temp)
            (directory/'metadata.json').write_text(json.dumps(dict(safety_contract='mr3-reach-v1',motion_authority_profile=AUTHORITY_PROFILE)))
            result = policy_audit.audit_episode_conjunction(directory, FREEZE, archive,
                                                           plan_path=Path('/synthetic/plan.json'))
        self.assertTrue(result['passed'], result['errors'])
        called.assert_called_once_with(directory, FREEZE, plan_path=Path('/synthetic/plan.json'))

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


    def test_all_four_actual_matrix_fifo_generators_forward_selected_plan(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); plan_path = root / 'plan.json'; binding = root / 'binding.json'
            binding.write_text(json.dumps({'actuation_profile': PROFILE, 'source_bindings': [], 'binaries': {}}))
            stages = []
            for name in plan_builder.primitives.STAGES:
                run, output = root / 'native' / name, root / 'output' / name
                native_argv = ['/synthetic/python', '-m', 'synthetic.benchmark', '--work-wall-seconds', '1',
                               '--preparation-probe-version', 'old', '--schedule', 'open:101']
                stages.append({'stage': name, 'run_directory': str(run), 'expected_episodes': 1,
                    'native': {'argv': native_argv, 'receipt': str(output / 'native_receipt.json')},
                    'watcher': {'argv': ['/synthetic/python', '-m', 'old'],
                                'output': str(output / 'live.json')},
                    'audits': [{'id': 'physical_per_episode', 'output': str(output / 'physics.json')}]})
            template = {'stages': stages, 'preflight': {}, 'budget': {}, 'source_bindings': {},
                        'output_directory': str(root / 'output'), 'learner_python': '/synthetic/python'}
            with patch.object(plan_builder.primitives, 'build_plan', return_value=template), \
                 patch.object(plan_builder, 'source_inventory', return_value=set()), \
                 patch.object(plan_builder, 'sha', return_value='4' * 64), \
                 patch.object(plan_builder, 'validate_plan', side_effect=lambda value, root: value):
                plan = plan_builder.build_plan(plan_path=plan_path, actuation_profile=PROFILE,
                    output_directory=root / 'output', run_root=root / 'native', custody_binding=binding,
                    binary_proof=root / 'binary.json', preflight=root / 'preflight.json',
                    engineering_remaining_seconds='20000', workspace=root)
            self.assertEqual(len(plan['stages']), 4)
            for stage in plan['stages']:
                jobs = [job for job in stage['audits'] if job['id'].startswith('fifo_') and 'argv' in job]
                self.assertTrue(jobs)
                for job in jobs:
                    self.assertEqual(job['argv'][job['argv'].index('--plan') + 1], str(plan_path))


if __name__ == '__main__':
    unittest.main()
