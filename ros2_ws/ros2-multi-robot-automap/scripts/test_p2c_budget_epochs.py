"""Pricing provenance never renews a source or permits expired dispatch."""
import copy
import pytest
from check_p2c_gate import budget_evaluation_time


def event():
    return dict(event_time=11.,inputs={
        'tb1/pose_state':dict(source_time=10.,age_sec=1.,ttl_sec=2.),
        'headquarters/fused_map_snapshot':dict(source_time=9.,age_sec=2.,ttl_sec=5.)})


def test_distinct_valid_price_and_dispatch_instants_preserve_input_provenance():
    e=event();old=copy.deepcopy(e)
    assert budget_evaluation_time(e,dict(priced_at=10.5),'priced_at',True)==10.5
    assert e==old


@pytest.mark.parametrize('mutation',['future_price','before_source','missing_price','expired_dispatch','rewritten_age'])
def test_false_price_or_dispatch_provenance_is_rejected(mutation):
    e=event();f=dict(priced_at=10.5)
    if mutation=='future_price':f['priced_at']=11.1
    if mutation=='before_source':f['priced_at']=9.9
    if mutation=='missing_price':f={}
    if mutation=='expired_dispatch':e['event_time']=12.1;e['inputs']['tb1/pose_state']['age_sec']=2.1
    if mutation=='rewritten_age':e['inputs']['tb1/pose_state']['age_sec']=0.
    with pytest.raises(AssertionError):budget_evaluation_time(e,f,'priced_at',True)
