import json
import pytest
from check_p3b5_gate import ledger_audit, bootstrap


@pytest.mark.parametrize('corruption', [None, 'source', 'digest', 'declaration', 'file',
                                      'command', 'forged_source_digest', 'forged_file_source_digest', 'plain_digest'])
def test_staging_digest_binds_original_bytes_command_and_declaration(tmp_path, monkeypatch, corruption):
    import hashlib
    import shlex
    import check_p3b5_gate as gate
    from run_p2d_baseline import file_digest
    monkeypatch.setattr(gate, 'ROOT', tmp_path)
    fixture = tmp_path / 'scripts/stage_p3b5_return_probe.py'
    fixture.parent.mkdir()
    fixture.write_text('# Original UTF-8 source: 中文 π\n')
    declared = hashlib.sha256(fixture.read_bytes()).hexdigest()
    row = {'staging_source': fixture.read_text(), 'staging_source_sha256': file_digest(fixture),
           'staging_command': shlex.join(['/usr/bin/python3', str(fixture), '--owner-pid', '123'])}
    if corruption == 'source': row['staging_source'] += '# changed\n'
    if corruption == 'digest': row['staging_source_sha256'] = '0' * 64
    if corruption == 'declaration': declared = '0' * 64
    if corruption == 'file': fixture.write_text('# changed on disk\n')
    if corruption == 'command':
        other = fixture.with_name('other.py'); other.write_bytes(fixture.read_bytes())
        row['staging_command'] = shlex.join(['/usr/bin/python3', str(other)])
    if corruption in ('forged_source_digest', 'forged_file_source_digest'):
        row['staging_source'] = '# forged source\n'
        row['staging_source_sha256'] = hashlib.sha256(fixture.name.encode() + row['staging_source'].encode()).hexdigest()
        if corruption == 'forged_file_source_digest': fixture.write_text(row['staging_source'])
    if corruption == 'plain_digest': row['staging_source_sha256'] = declared
    if corruption is None:
        result = gate.staging_source_audit(row, declared)
        assert result['source_content_sha256'] == declared
        assert result['source_file_digest_sha256'] == row['staging_source_sha256']
        assert result['source_matches_predeclared_apparatus']
    else:
        with pytest.raises(AssertionError): gate.staging_source_audit(row, declared)


@pytest.mark.parametrize("corruption", [None, "angular", "duration", "gap", "roster", "clock", "declaration", "legacy"])
def test_completion_requires_native_hold_without_weakening_the_frozen_gate(corruption):
    from check_p3b5_gate import native_completion_ok
    proof = {"start_observer_sim_time_sec": 100., "end_observer_sim_time_sec": 105.,
             "observed_duration_sec": 5., "sample_count": 51,
             "maximum_observation_gap_sec": .1, "maximum_allowed_observation_gap_sec": 2.,
             "required_robot_names": ["tb1"], "maximum_position_error_m": .02,
             "maximum_linear_speed_mps": .01, "maximum_angular_speed_radps": .03,
             "clock_basis": "headerless_model_states_observer_sim_time"}
    result = {"schema_version": 9, "native_rally_hold_proof": proof,
              "required_robot_names": ["tb1"], "rally_hold_sec": 5.,
              "start_sim_time_sec": 90., "completion_time_sec": 15.,
              "coordinator_completion_time_sec": 14.}
    if corruption == "angular": proof["maximum_angular_speed_radps"] = .19315
    if corruption == "duration": proof["observed_duration_sec"] = 4.99
    if corruption == "gap": proof["maximum_observation_gap_sec"] = 2.01
    if corruption == "roster": proof["required_robot_names"] = ["tb2"]
    if corruption == "clock": proof["clock_basis"] = "generation_time"
    if corruption == "declaration": result["coordinator_completion_time_sec"] = 16.
    if corruption == "legacy": result["schema_version"] = 8
    if corruption is None: native_completion_ok(result)
    else:
        with pytest.raises(AssertionError): native_completion_ok(result)


@pytest.mark.parametrize('extra_time', [None, 21., 192.2])
def test_prepared_robot_cannot_be_staged_again_after_actual_return(extra_time):
    from check_p3b5_gate import staging_audit
    fixture={'poses':{'tb1':[.75,0.,0.]},'stage_deadline_sec':50.,
             'position_tolerance_m':.25,'navigation_leg_limit_m':.75}
    def request(t):
        return {'event':'staging_requested','robot':'tb1','observer_time':t,
                'waypoint':[.75,0.],'current_position':[0.,0.],
                'inputs':{k:{'source_time':t-.1,'age_sec':.1,'ttl_sec':2.}
                          for k in ('map_snapshot','pose_state','frame_state','battery_state')}}
    events=[request(1.),{'event':'staged','robot':'tb1','observer_time':20.,'position':[.75,0.]}]
    if extra_time is not None:events.append(request(extra_time))
    events.extend([{'event':'both_charged','observer_time':200.},
                   {'event':'coordinator_resumed','observer_time':200.}])
    if extra_time is None:assert set(staging_audit(events,0.,fixture))=={'tb1'}
    else:
        with pytest.raises(AssertionError):staging_audit(events,0.,fixture)


def write_events(tmp_path, events):
    path=tmp_path / "ledger.jsonl"
    path.write_text("".join(json.dumps(e)+"\n" for e in events))
    return path


def test_reject_original_future_source_before_transmission(tmp_path):
    path=write_events(tmp_path,[{"event":"tx","time":.2,"source_time":.229,
                                 "enqueue_time":.2,"admit_time":.2,"tx_time":.2}])
    with pytest.raises(AssertionError):ledger_audit(path)


@pytest.mark.parametrize('age', [0., 5., 5.001, -.001])
def test_observer_handoff_wait_cannot_claim_stale_or_future_visual_contact(tmp_path, age):
    event={'event':'coordinator_observer_handoff_wait','event_time':100.,'observer_source_time':100.-age}
    if 0<=age<=5:assert ledger_audit(write_events(tmp_path,[event]))['coordinator_decision_source_leases']=='PASS'
    else:
        with pytest.raises(AssertionError):ledger_audit(write_events(tmp_path,[event]))


@pytest.mark.parametrize("basis", ["current_map_frontiers", "current_map_known_free_sweep"])
def test_reacquisition_frontier_search_requires_fresh_states_and_recorded_route(tmp_path, basis):
    event={"event":"coordinator_navigation_decision","event_time":100.,
           "kind":"target_reacquisition_exploration","search_basis":basis,
           "search_route":[[1.,2.],[2.,2.]],"requested_position":[2.,2.],"map_resolution_m":.05,
           "inputs":{"tb1/pose_state":{"source_time":99.,"age_sec":1.,"ttl_sec":2.},
               "headquarters/target_detection":{"source_time":0.,"age_sec":100.,"ttl_sec":60.}}}
    assert ledger_audit(write_events(tmp_path,[event]))["coordinator_decision_source_leases"]=="PASS"
    for bad in ({**event,"search_basis":"expired_target"}, {**event,"search_route":[]},
                {**event,"requested_position":[3.,2.]},
                {**event,"inputs":{"tb1/pose_state":{"source_time":97.,"age_sec":3.,"ttl_sec":2.}}}):
        with pytest.raises(AssertionError):ledger_audit(write_events(tmp_path,[bad]))


def test_reject_expired_or_rollback_receipts(tmp_path):
    event={"event":"accepted","event_time":2.1,"source_time":0.,"ttl_sec":2.,
           "message_type":"pose_state","sender":"tb1","recipient":"headquarters","sequence":2}
    with pytest.raises(AssertionError):ledger_audit(write_events(tmp_path,[event]))
    event={**event,"event_time":1.}
    with pytest.raises(AssertionError):ledger_audit(write_events(tmp_path,[event,{**event,"sequence":1}]))


def test_accept_deferral_and_physical_cluster_accounting(tmp_path):
    event={"event":"tx","time":.229,"source_time":.229,"enqueue_time":.229,"admit_time":.229,"tx_time":.229}
    assert ledger_audit(write_events(tmp_path,[event]))["attempt_stage_causality"]=="PASS"
    result=bootstrap([("one",0.),("one",1.),("two",1.)])
    assert result["n"]==3 and result["clusters"]==2
    assert result["mean"]==pytest.approx(2/3)
    assert result["ci95"]==[.5,1.]


@pytest.mark.parametrize("age", [-.001, 2.001])
def test_reject_new_navigation_decision_using_a_future_or_expired_sample(tmp_path, age):
    event={"event":"coordinator_navigation_decision","event_time":100.,
           "kind":"rally","inputs":{"tb1/pose_state":{
               "source_time":100.-age,"age_sec":age,"ttl_sec":2.}}}
    with pytest.raises(AssertionError):ledger_audit(write_events(tmp_path,[event]))


@pytest.mark.parametrize('age',[0.,2.,2.001,-.001])
def test_charge_decision_requires_the_same_fresh_pose_lease_as_navigation(tmp_path,age):
    event={'event':'coordinator_charge_decision','event_time':100.,
           'task_phase':'EXPLORE','inputs':{'tb1/pose_state':{
               'source_time':100.-age,'age_sec':age,'ttl_sec':2.}}}
    if 0<=age<=2.:
        assert ledger_audit(write_events(tmp_path,[event]))['coordinator_decision_source_leases']=='PASS'
    else:
        with pytest.raises(AssertionError):ledger_audit(write_events(tmp_path,[event]))


@pytest.mark.parametrize('age',[0.,10.,10.001,-.001])
def test_charge_consumption_cannot_use_an_expired_or_future_request(tmp_path,age):
    event={'event':'consumed','message_type':'charge_request','consumed_time':100.,
           'delivery_time':100.,'source_time':100.-age}
    if 0<=age<=10.:
        assert ledger_audit(write_events(tmp_path,[event]))['receiver_ttl_and_versions']=='PASS'
    else:
        with pytest.raises(AssertionError):ledger_audit(write_events(tmp_path,[event]))


def test_expired_target_can_only_be_used_for_local_return_refuge_audit(tmp_path):
    event={"event":"coordinator_navigation_decision","event_time":100.,
           "kind":"local_return_yield","inputs":{
               "tb1/pose_state":{"source_time":99.,"age_sec":1.,"ttl_sec":2.},
               "headquarters/target_detection":{"source_time":0.,"age_sec":100.,"ttl_sec":60.}}}
    assert ledger_audit(write_events(tmp_path,[event]))["coordinator_decision_source_leases"]=="PASS"
    with pytest.raises(AssertionError):ledger_audit(write_events(tmp_path,[{**event,"kind":"rally"}]))


def test_blind_scan_cannot_hide_a_new_translation_based_on_an_expired_target(tmp_path):
    event={"event":"coordinator_navigation_decision","event_time":100.,
           "kind":"target_reacquisition_scan","requested_position":[1.,2.],"current_position":[1.,2.],
           "inputs":{"tb1/pose_state":{"source_time":99.,"age_sec":1.,"ttl_sec":2.},
               "headquarters/target_detection":{"source_time":0.,"age_sec":100.,"ttl_sec":60.}}}
    assert ledger_audit(write_events(tmp_path,[event]))["coordinator_decision_source_leases"]=="PASS"
    with pytest.raises(AssertionError):ledger_audit(write_events(tmp_path,[{**event,"requested_position":[1.1,2.]}]))


def test_wait_excludes_live_goals_and_autonomous_charge(tmp_path):
    from check_p3b5_gate import local_wait_audit
    events=[{"event":"coordinator_wait","time":0},
            {"event":"accepted","time":2,"message_type":"navigation_goal","recipient":"tb1","correlation_id":1},
            {"event":"enqueue","time":4,"source_time":4,"message_type":"navigation_result","sender":"tb1","correlation_id":1}]
    trace={"local_battery_transitions":{"tb1":[{"mode":"ACTIVE","source_time":0},
                                               {"mode":"RETURNING","source_time":5},
                                               {"mode":"CHARGING","source_time":6},
                                               {"mode":"ACTIVE","source_time":8}]}}
    result=local_wait_audit(write_events(tmp_path,events),trace,0,10)
    assert result["tb1"]["stale_controller_wait_sec"]==5


@pytest.mark.parametrize('start,moving,status,time,passes', [
    (2.,True,2,60.,True), (.8,True,2,60.,False),
    (2.,False,2,60.,False), (2.,True,4,60.,False),
    (2.,True,2,260.,False)])
def test_physical_return_requires_real_home_progress_and_live_nav2(start,moving,status,time,passes):
    from check_p3b5_gate import physical_return_audit
    events=[]
    for k in range(8):
        events.append({'event':'physics','observer_time':time+k*.5,
            'robots':{name:{'x':start-(k*.1 if moving else 0.),'y':0.,
                'battery':{'mode':'RETURNING','return_count':1},
                'nav2_status':[{'status':status}]}
                for name in ('tb1','tb2')}})
    homes={'tb1':(0.,0.),'tb2':(0.,0.)}
    if passes:
        result=physical_return_audit(events,0.,homes)
        assert set(result)==set(homes)
        assert result['tb1']['nav2_executing_motion_m']==pytest.approx(.7)
    else:
        with pytest.raises(AssertionError):physical_return_audit(events,0.,homes)


@pytest.mark.parametrize('mismatch', ['none','commit','duplicate'])
def test_fixed_partition_preserves_version_and_unique_cells(tmp_path,mismatch):
    from check_p3b5_gate import fixed_ideal_batches
    manifest={'task_stack_clean':True,'worktree_dirty':True,
        'task_stack_candidate_commit':'one','git_commit':'one',
        'source_digests':{'core':'hash'},'environment':{'ros':'humble'}}
    row={'scenario_id':'lab','robot_count':3,'gazebo_seed':101}
    paths=[]
    for index in range(2):
        entry={**row,'gazebo_seed':101+index}
        m=manifest.copy()
        if index and mismatch=='commit':m.update(task_stack_candidate_commit='two',git_commit='two')
        if index and mismatch=='duplicate':entry=row
        path=tmp_path/f'{index}.json';path.write_text(json.dumps({'manifest':m,
            'max_duration_sec':300,'infrastructure_retries':0,'episodes':[entry]}));paths.append(path)
    if mismatch=='none':
        combined=fixed_ideal_batches(paths)
        assert len(combined['episodes'])==2 and len(combined['batches'])==2
    else:
        with pytest.raises(AssertionError):fixed_ideal_batches(paths)


def test_native_nav2_uuid_can_be_serialized_by_physics_observer():
    import ast
    import json
    from pathlib import Path
    import numpy as np
    from action_msgs.msg import GoalStatusArray, GoalStatus
    source = Path(__file__).with_name("observe_p3b5_return_physics.py").read_text()
    action = next(node for node in ast.parse(source).body
                  if isinstance(node, ast.FunctionDef) and node.name == "action")
    namespace = {"status": {}}
    exec(compile(ast.Module(body=[action], type_ignores=[]), "observer_action", "exec"), namespace)
    message = GoalStatusArray()
    state = GoalStatus()
    state.goal_info.goal_id.uuid = np.arange(16, dtype=np.uint8)
    state.status = 2
    message.status_list = [state]
    namespace["action"]("tb1", message)
    assert json.loads(json.dumps(namespace["status"])) == {
        "tb1": [{"uuid": list(range(16)), "status": 2}]}
