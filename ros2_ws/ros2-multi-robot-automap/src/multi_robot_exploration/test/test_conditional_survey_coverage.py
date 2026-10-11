"""An optional fallback must not force extra navigation to satisfy coverage."""
import copy
import gzip
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import check_p2c_gate as gate


FIXTURE=Path(__file__).with_name('fixtures')/'p2c_v89_conditional_survey_coverage.json.gz'


def original_results():
    with gzip.open(FIXTURE,'rt') as stream:
        return json.load(stream)['original_results']


def complete_originals():
    return original_results()['log/p2c_v89_development_full_gate1.json']['evidence']


def test_actual_four_complete_assignments_have_no_fallback_opportunity():
    rows=complete_originals();before=copy.deepcopy(rows)
    result=gate.target_survey_coverage_audit(rows,conditional=True)
    assert result['status']=='NOT_TRIGGERED'
    assert result['complete_assignments']==4
    assert result['incomplete_assignments']==result['information_surveys']==0
    assert rows==before


def test_original_unconditional_rule_still_rejects_zero_execution():
    with pytest.raises(AssertionError,match='never exercised'):
        gate.target_survey_coverage_audit(complete_originals())


@pytest.mark.parametrize('conditional',[False,True])
def test_actual_original_information_survey_remains_positive_evidence(conditional):
    rows=original_results()['log/p2c_v88_forced_gate1.json']['evidence']
    result=gate.target_survey_coverage_audit(rows,conditional=conditional)
    assert result['status']=='PASS' and result['information_surveys']==1


def test_incomplete_assignment_without_information_survey_still_fails():
    rows=complete_originals();rows[0]['rally_assignment_audit']['failed_assignments_rebuilt']=1
    with pytest.raises(AssertionError,match='never exercised'):
        gate.target_survey_coverage_audit(rows,conditional=True)


@pytest.mark.parametrize('damage',['empty','missing_assignment','missing_survey','assignment_failed',
                                  'survey_failed','undeclared','no_complete_assignment'])
def test_missing_or_failed_proof_cannot_claim_no_fallback_opportunity(damage):
    rows=complete_originals()
    if damage=='empty':rows=[]
    elif damage=='missing_assignment':del rows[0]['rally_assignment_audit']
    elif damage=='missing_survey':del rows[0]['target_survey_audit']
    elif damage=='assignment_failed':rows[0]['rally_assignment_audit']['status']='FAIL'
    elif damage=='survey_failed':rows[0]['target_survey_audit']['status']='FAIL'
    elif damage=='undeclared':rows[0]['target_survey_audit']['declared']=False
    else:
        for row in rows:row['rally_assignment_audit']['chosen_assignments_rebuilt']=0
    with pytest.raises((AssertionError,KeyError)):
        gate.target_survey_coverage_audit(rows,conditional=True)


@pytest.mark.parametrize('key',['failed_assignments_rebuilt','chosen_assignments_rebuilt',
                              'target_information_survey_witnesses'])
@pytest.mark.parametrize('value',[-1,False,.5,'0',None])
def test_invalid_original_counts_are_rejected(key,value):
    rows=complete_originals()
    audit='target_survey_audit' if key=='target_information_survey_witnesses' else 'rally_assignment_audit'
    rows[0][audit][key]=value
    with pytest.raises(AssertionError,match='invalid original coverage counts'):
        gate.target_survey_coverage_audit(rows,conditional=True)


@pytest.mark.parametrize('conditional,selected,upstream_error,expected',[
    (True,False,False,0),(False,False,False,1),(True,True,False,0),(True,False,True,1)])
def test_full_gate_composes_coverage_with_original_native_audit_results(
        tmp_path,monkeypatch,conditional,selected,upstream_error,expected):
    # Only the orchestration boundary is mocked. Inputs are literal frozen
    # original reader results; this test earns no native task credit.
    original=original_results()['log/p2c_v89_development_full_gate1.json']
    rows={row['case']:row for row in original['evidence']}
    root=tmp_path/'root';run=root/'run';manifest=root/'manifest.json';output=root/'gate.json'
    config=dict(development_cases=list(rows),target_information_survey=True)
    if conditional:config['conditional_target_survey_coverage']={'rule':'no_incomplete_assignments'}
    for case in rows:
        directory=run/case;directory.mkdir(parents=True)
        (directory/'summary.json').write_text(json.dumps(dict(case=case,
            git_commit=original['task_stack_frozen_commit'],source_digests={'frozen':'same'})))
    manifest.write_text(json.dumps(config))

    class OriginalResultsPool:
        def __init__(self,**kwargs):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def map(self,function,items):
            for path,_ in items:
                case=json.loads(path.read_text())['case']
                if upstream_error and case==next(iter(rows)):
                    yield None,dict(case=case,error='original native audit FAIL')
                else:yield rows[case],None

    monkeypatch.setattr(gate,'ProcessPoolExecutor',OriginalResultsPool)
    monkeypatch.setattr(gate,'subprocess',SimpleNamespace(check_output=lambda *a,**k:json.dumps(config).encode()))
    monkeypatch.setattr(gate,'__file__',str(root/'one/two/three/gate.py'))
    argv=['gate','--run-root',str(run),'--development','--manifest',str(manifest),'--output',str(output)]
    if selected:argv+=['--cases',next(iter(rows))]
    monkeypatch.setattr('sys.argv',argv)
    assert gate.main()==expected
    result=json.loads(output.read_text())
    assert result['status']==('PASS' if expected==0 else 'FAIL')
    if conditional and not selected and not upstream_error:
        assert result['full_declared_scope'] and result['cases']==4
        assert result['target_survey_coverage']['status']=='NOT_TRIGGERED'
    elif selected or upstream_error:
        assert result['target_survey_coverage'] is None
    else:
        assert result['errors']==[dict(case='target_information_survey',error='new survey algorithm was never exercised')]
