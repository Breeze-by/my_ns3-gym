"""V66 artificial admission boundaries; no World, model or scientific reader."""
import copy
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch
import pytest

PACKAGE='report.assets.20261024_mr3_p2a_v66_owned_stream_qualification.'
preparing=importlib.import_module(PACKAGE+'prepare_plan_v1')


@pytest.fixture
def entry(tmp_path):
    # Copy only an already closed accounting header, never telemetry. This
    # artificial workspace does not claim any new actual execution.
    ledger=json.loads(preparing.NORMALIZED_PRIOR.read_text())
    resource=json.loads((preparing.A/'resource_v1.json').read_text())
    scope=json.loads((preparing.A/'scope_v1.json').read_text())
    authorization=json.loads((preparing.A/'authorization_v1.json').read_text())
    paths={name:tmp_path/name for name in ['ledger.json','resource_v1.json','scope_v1.json','authorization_v1.json']}
    def save(ledger=ledger,resource=resource,scope=scope,authorization=authorization):
        import hashlib
        def pin(path):
            raw=path.read_bytes()
            return {'path':path.name,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
        paths['ledger.json'].write_text(json.dumps(ledger)+'\n')
        resource=copy.deepcopy(resource);resource['previous_accounting']=pin(paths['ledger.json'])
        paths['resource_v1.json'].write_text(json.dumps(resource)+'\n')
        scope=copy.deepcopy(scope);scope['engineering_resource']=pin(paths['resource_v1.json'])
        authorization=copy.deepcopy(authorization);authorization['engineering_resource']=pin(paths['resource_v1.json'])
        paths['scope_v1.json'].write_text(json.dumps(scope)+'\n')
        paths['authorization_v1.json'].write_text(json.dumps(authorization)+'\n')
        return pin(paths['ledger.json'])['sha256']
    pin=save()
    with patch.object(preparing,'ROOT',tmp_path),patch.object(preparing,'A',tmp_path),patch.object(preparing,'RESOURCE',paths['resource_v1.json']),patch.object(preparing,'NORMALIZED_PRIOR',paths['ledger.json']),patch.object(preparing,'PREVIOUS_LEDGER_SHA256',pin):
        yield ledger,resource,scope,authorization,save


def test_new_block_keeps_all_actual_past_fees_and_original_policy_totals(entry):
    assert entry[0]['passed'] is True and entry[0]['activity_passed'] is False
    assert entry[0]['actual_root_tool_returncode']==1 and entry[0]['engineering_added_parent_union_seconds']=='57.081760798'
    resource,_,used,remaining=preparing.entry_budget(preparing.Inputs())
    assert str(used)=='109131.3266391666018'
    assert str(remaining)=='70868.6733608333982'
    assert resource['budget']['total_engineering_reservation_at_entry_seconds']=='47220'
    preparing.verify_authorization(preparing.Inputs())


@pytest.mark.parametrize('field,value',[
    ('engineering_added_parent_union_seconds','4'),('actual_root_tool_returncode',0),
    ('actual_before_after_equal',False),('nonowned_ancestor_absence_claimed',True),
    ('pilot_added_parent_union_seconds','1'),
])
def test_forged_fee_reap_source_or_nonowned_claim_rejected_even_with_updated_toy_pin(entry,field,value):
    ledger,resource,scope,auth,save=entry
    bad=copy.deepcopy(ledger);bad[field]=value;toy_pin=save(ledger=bad)
    with patch.object(preparing,'PREVIOUS_LEDGER_SHA256',toy_pin),pytest.raises(ValueError):
        preparing.entry_budget(preparing.Inputs())


def test_old_unfunded_balance_cannot_be_presented_as_complete_new_reservation(entry):
    ledger,resource,scope,auth,save=entry
    bad=copy.deepcopy(resource);bad['engineering_ceiling_seconds']='150000';bad['engineering_remaining_seconds']='40868.6733608333982'
    save(resource=bad)
    with pytest.raises(ValueError):preparing.entry_budget(preparing.Inputs())


@pytest.mark.parametrize('field,value',[
    ('motion_authority_profile',None),('capacity_qualified',True),
    ('automatic_policy_entry_allowed',True),('mandatory_roles',29),
    ('matrix_episodes',11),('preparation_probe_version','mr3-p2a-reach-outward-cancel-v1'),
])
def test_missing_new_profile_weakened_workload_and_automatic_policy_entry_rejected(entry,field,value):
    ledger,resource,scope,auth,save=entry
    bad=copy.deepcopy(scope);bad[field]=value;save(scope=bad)
    with pytest.raises(ValueError):preparing.verify_authorization(preparing.Inputs())


def test_numeric_approval_cannot_be_invented_from_continuation(entry):
    ledger,resource,scope,auth,save=entry
    bad=copy.deepcopy(auth);bad['numeric_user_approval_claimed']=True;save(authorization=bad)
    with pytest.raises(ValueError):preparing.verify_authorization(preparing.Inputs())


def test_untracked_python_test_is_classified_before_git_add(tmp_path):
    classification=importlib.import_module(PACKAGE+'classification_admission_v1')
    relative='ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/test/test_new_untracked.py'
    path=tmp_path/relative;path.parent.mkdir(parents=True);path.write_text('# artificial, not in Git\n')
    runtime,tests=classification.current_python_sources(tmp_path)
    assert relative in tests and relative not in runtime


@pytest.mark.parametrize('module',['prepare_plan_v1','preflight_v1','plan_check_v1','readiness_v1','run_matrix_v1','bootstrap_v1'])
def test_actual_entry_module_help_does_not_start_native_or_create_parent_state(module,tmp_path):
    env={**os.environ,'PYTHONNOUSERSITE':'1','PYTHONDONTWRITEBYTECODE':'1','CUDA_VISIBLE_DEVICES':''}
    env.pop('PYTHONPATH',None);env.pop('PYTHONHOME',None)
    result=subprocess.run([sys.executable,'-B','-m',PACKAGE+module,'--help'],cwd=preparing.W,env=env,capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr
    assert 'usage:' in result.stdout
    assert not Path('/tmp/mr3_p2a_reach_v66_driver_v1').exists()
