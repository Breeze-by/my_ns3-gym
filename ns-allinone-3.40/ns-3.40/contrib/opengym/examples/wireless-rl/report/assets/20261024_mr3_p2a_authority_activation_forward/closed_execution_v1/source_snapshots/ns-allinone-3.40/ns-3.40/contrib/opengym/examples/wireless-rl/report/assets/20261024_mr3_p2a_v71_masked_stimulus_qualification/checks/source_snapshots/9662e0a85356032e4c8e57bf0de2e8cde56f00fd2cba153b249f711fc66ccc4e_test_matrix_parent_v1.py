"""Finite artificial lifecycle/admission tests; no native activity or raw input."""
from contextlib import ExitStack
from decimal import Decimal
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch

HERE = Path(__file__).resolve().parent


def load(name):
    spec=importlib.util.spec_from_file_location('_v67_toy_'+name,HERE/(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


def setup_parent(m, root):
    state=root/'state';state.mkdir()
    freeze='a'*40
    m.write(state/'pre_exec_ancestry_v1.json',dict(execution_freeze=freeze,
        bootstrap_identity=m.identity(__import__('os').getpid()),
        complete_parent_started_monotonic_ns=time.monotonic_ns()))
    return state,freeze


def test_real_child_rc7_and_exact_env(tmp_path):
    m=load('run_matrix_v1')
    output=tmp_path/'out'
    argv=[sys.executable,'-B','-c',
          'import os,sys; assert os.environ["PYTHONNOUSERSITE"]=="1"; '
          'assert "PYTHONPATH" not in os.environ; assert sys.dont_write_bytecode; sys.exit(7)']
    row=m.wait_child(argv,output)
    assert row['actual_waited'] and row['actual_returncode']==7 and not row['errors']
    saved=row['wrapper_identity'];assert saved['start_ticks']>0
    assert not Path('/proc',str(saved['pid'])).exists()


def test_identity_observation_failure_still_realwait(tmp_path):
    m=load('run_matrix_v1')
    with patch.object(m,'identity',side_effect=RuntimeError('artificial observation failure')):
        row=m.wait_child([sys.executable,'-B','-c','raise SystemExit(9)'],tmp_path/'out')
    assert row['actual_waited'] and row['actual_returncode']==9 and row['wrapper_identity'] is None
    assert 'identity capture' in row['errors'][0]


def test_wait_interruption_does_not_abandon_child(tmp_path):
    m=load('run_matrix_v1');original=m.subprocess.Popen;children=[]
    def popen(*args,**kwargs):
        child=original(*args,**kwargs);children.append(child);realwait=child.wait;calls=0
        def wait(*a,**k):
            nonlocal calls
            calls+=1
            if calls==1:raise RuntimeError('artificial interrupted observer')
            return realwait(*a,**k)
        child.wait=wait;return child
    with patch.object(m.subprocess,'Popen',side_effect=popen):
        row=m.wait_child([sys.executable,'-B','-c','raise SystemExit(3)'],tmp_path/'out')
    assert row['actual_waited'] and row['actual_returncode']==3 and row['errors']
    assert children[0].returncode==3 and not Path('/proc',str(children[0].pid)).exists()


def test_phase_actual_source_wait_and_no_double_fee(tmp_path):
    m=load('run_matrix_v1');state=tmp_path/'state';state.mkdir();rows=[]
    command=[sys.executable,'-B','-c','print("artificial CPU only")']
    with patch.object(m,'STATE',state):
        assert m.phase('toy',command,sys.executable,[HERE/'run_matrix_v1.py',HERE/'test_matrix_parent_v1.py'],
                       rows,tmp_path/'actual')
    row=rows[0];receipt=row['receipt']
    assert row['command']==command and row['actual_argv'][-len(command):]==command
    assert receipt['actual_argv']==command and receipt['source_before']==receipt['source_after']
    assert receipt['actual_waited'] and row['actual_waited']
    assert row['started_monotonic_ns']<=receipt['started_monotonic_ns']<=receipt['ended_monotonic_ns']<=row['ended_monotonic_ns']


def test_phase_bad_receipt_preserves_true_child_rc(tmp_path):
    m=load('run_matrix_v1');state=tmp_path/'state';state.mkdir();rows=[];outer=tmp_path/'outer';outer.mkdir()
    m.write(outer/'actual_wait.json',{'actual_waited':False})
    with patch.object(m,'STATE',state),patch.object(m,'wait_child',return_value=dict(actual_returncode=0,
            actual_waited=True,started_monotonic_ns=1,ended_monotonic_ns=2,errors=[])):
        assert not m.phase('toy', ['never-executed'],sys.executable,[],rows,outer)
    assert rows[0]['actual_returncode']==0 and rows[0]['errors'] and not rows[0]['passed']


def test_extra_current_assets_cannot_override_plan_source_pin(tmp_path):
    m=load('run_matrix_v1');assets=tmp_path/'assets';assets.mkdir()
    source=assets/'run_matrix_v1.py';source.write_text('# artificial source\n')
    library=tmp_path/'library';library.write_bytes(b'artificial ELF stand-in')
    names={'ROOT':tmp_path,'ASSETS':assets,'PLAN':assets/'plan.json',
           'SCOPE':assets/'scope.json','RESOURCE':assets/'resource.json','PREVIOUS':assets/'ledger.json'}
    for key in ('PLAN','SCOPE','RESOURCE','PREVIOUS'):names[key].write_text('{}\n')
    plan={'source_bindings':{str(source.relative_to(tmp_path)):'0'*64},
          'library_bindings':{str(library):m.proof(library)['sha256']}}
    with ExitStack() as stack:
        for key,value in names.items():stack.enter_context(patch.object(m,key,value))
        stack.enter_context(patch.object(m,'clean_freeze'))
        stack.enter_context(patch.object(m,'git',side_effect=lambda *args:
            (tmp_path/args[1].split(':',1)[1]).read_bytes()))
        try:m.source_check(plan,'a'*40)
        except ValueError as error:assert 'plan source/library SHA differs' in str(error)
        else:raise AssertionError('current asset must retain its actual sealed plan pin')


def test_bad_bootstrap_identity_leaves_fee_unknown(tmp_path):
    m=load('run_matrix_v1');state,freeze=setup_parent(m,tmp_path)
    record=m.read(state/'pre_exec_ancestry_v1.json');record['bootstrap_identity']['start_ticks']+=1
    (state/'pre_exec_ancestry_v1.json').write_text(json.dumps(record))
    with patch.object(m,'STATE',state),patch.object(m,'load_dependencies') as imports:
        assert m.main(['--freeze',freeze])==1
    result=m.read(state/'summary.json');imports.assert_not_called()
    assert result['actual_parent_seconds'] is None and result['engineering_cumulative_seconds'] is None
    assert not result['complete_parent_fee_known'] and not result['matrix_submitted']


def test_dependency_failure_settles_known_parent_from_real_ledger(tmp_path):
    m=load('run_matrix_v1');state,freeze=setup_parent(m,tmp_path)
    with patch.object(m,'STATE',state),patch.object(m,'canonical_location',return_value=True),\
         patch.object(m,'load_dependencies',side_effect=ImportError('artificial')):
        assert m.main(['--freeze',freeze])==1
    result=m.read(state/'summary.json');fee=Decimal(result['actual_parent_seconds'])
    assert fee>0 and result['complete_parent_fee_known'] and result['engineering_ceiling_seconds'] is None
    assert Decimal(result['engineering_cumulative_seconds'])==m.ENTRY+fee
    assert not result['matrix_submitted'] and result['pilot_added_union_seconds']=='0'


def test_unadmitted_scope_earlyrefusal_and_postsource_attempt(tmp_path):
    m=load('run_matrix_v1');state,freeze=setup_parent(m,tmp_path);scope=tmp_path/'scope'
    scope.write_text('{"admitted":false}')
    reach=SimpleNamespace(load_plan=lambda _: {'artificial_fixture':True})
    preparing=SimpleNamespace(verify_plan_resource=lambda _: ({},SimpleNamespace(finish=lambda:None)))
    with patch.object(m,'STATE',state),patch.object(m,'SCOPE',scope),\
         patch.object(m,'canonical_location',return_value=True),\
         patch.object(m,'load_dependencies',return_value=(reach,preparing)),\
         patch.object(m,'source_check',return_value=[]) as source,patch.object(m,'phase') as phase:
        assert m.main(['--freeze',freeze])==1
    phase.assert_not_called();assert source.call_count==1
    result=m.read(state/'summary.json')
    assert result['post_source_check_attempted'] and result['actual_parent_seconds'] is not None
    assert not result['matrix_submitted'] and not result['capacity_qualified']


def test_only_matrix_stages_and_postsource_failure_fails(tmp_path):
    m=load('run_matrix_v1');state,freeze=setup_parent(m,tmp_path);prefix=tmp_path/'activity';scope=tmp_path/'scope'
    scope.write_text('{}');qualification=Path(str(prefix)+'_qualification.json')
    qualification.write_text(json.dumps(dict(passed=True,freeze=freeze,mandatory_roles=30,episodes=[{}]*12,
        actuation_profile=m.ACTUATION_PROFILE,motion_authority_profile=m.AUTHORITY_PROFILE)))
    plan={'learner_python':sys.executable,'preflight':{'path':'artificial-only'}}
    reach=SimpleNamespace(load_plan=lambda _:plan)
    resource={'budget':{'engineering_cumulative_ceiling_seconds':'180000',
                        'external_final_and_accounting_reservation_seconds':'300'}}
    preparing=SimpleNamespace(verify_plan_resource=lambda _: (resource,SimpleNamespace(finish=lambda:None)))
    phases=[]
    def phase(name,command,python,sources,rows,outer=None):
        if name=='matrix':
            # Match the unchanged real _qualification_evidence argv predicate.
            assert command[:3]==[python,'-m','mr3_learning.reach_preparation']
        phases.append(name);now=time.monotonic_ns()
        rows.append(dict(name=name,outer=str(tmp_path/name),started_monotonic_ns=now,ended_monotonic_ns=now,
                         passed=True,actual_returncode=0));return True
    def absence(name,plan,python,sources,rows,matrix_outer):
        return phase(name,[],python,sources,rows)
    with ExitStack() as stack:
        for key,value in {'STATE':state,'PREFIX':prefix,'SCOPE':scope}.items():stack.enter_context(patch.object(m,key,value))
        stack.enter_context(patch.object(m,'load_dependencies',return_value=(reach,preparing)))
        stack.enter_context(patch.object(m,'canonical_location',return_value=True))
        stack.enter_context(patch.object(m,'verify_admission'))
        stack.enter_context(patch.object(m,'source_check',side_effect=[[{'path':str(HERE/'run_matrix_v1.py')}],ValueError('artificial postsource')]))
        stack.enter_context(patch.object(m,'phase',side_effect=phase))
        stack.enter_context(patch.object(m,'matrix_absence',side_effect=absence))
        assert m.main(['--freeze',freeze])==1
    assert phases==['preflight','matrix','matrix_absence','qualification','chain_final_absence']
    result=m.read(state/'summary.json')
    assert result['completed_stages']==['matrix_qualification'] and not result['passed']
    assert result['engineering_added_union_seconds']==result['actual_parent_seconds']
    assert result['pilot_added_union_seconds']==result['validation_added_union_seconds']=='0'
    assert not result['automatic_policy_entry_allowed'] and not result['P2A_complete']


def test_noncanonical_parent_refuses_before_import_or_phase(tmp_path):
    m=load('run_matrix_v1');state,freeze=setup_parent(m,tmp_path)
    with patch.object(m,'STATE',state),patch.object(m,'canonical_location',return_value=False),\
         patch.object(m,'load_dependencies') as imports,\
         patch.object(m,'phase') as phase:
        assert m.main(['--freeze',freeze])==1
    imports.assert_not_called();phase.assert_not_called();result=m.read(state/'summary.json')
    assert result['complete_parent_fee_known'] and result['actual_parent_seconds'] is not None
    assert not result['matrix_submitted'] and any('canonical source-bound' in e for e in result['errors'])


def test_bootstrap_exec_failure_records_real_interval_and_ancestry(tmp_path):
    b=load('bootstrap_v1');state=tmp_path/'state';calls=[]
    def fail(program,argv,env):
        calls.append((program,argv,env));raise OSError('artificial exec failure')
    with patch.object(b,'STATE',state),patch.object(b,'canonical_location',return_value=True),\
         patch.object(b.os,'execve',side_effect=fail):
        try:b.main(['--freeze','a'*40])
        except OSError:pass
        else:raise AssertionError('real exec error must propagate')
    record=json.loads((state/'pre_exec_ancestry_v1.json').read_text())
    failure=json.loads((state/'bootstrap_failure_v1.json').read_text())
    assert Decimal(failure['actual_parent_seconds'])>0 and failure['engineering_cumulative_seconds'] is None
    assert failure['started_monotonic_ns']==record['complete_parent_started_monotonic_ns']
    assert record['ancestors_nonowned'] and not record['ancestor_absence_or_signal_authorized']
    assert calls[0][1][:3]==['/usr/bin/python3','-B','-m']
    assert calls[0][2]['PYTHONNOUSERSITE']=='1' and 'PYTHONPATH' not in calls[0][2]
