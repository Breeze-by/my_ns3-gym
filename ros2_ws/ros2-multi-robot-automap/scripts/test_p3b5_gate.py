import json
import pytest
from check_p3b5_gate import ledger_audit, bootstrap


def write_events(tmp_path, events):
    path=tmp_path / "ledger.jsonl"
    path.write_text("".join(json.dumps(e)+"\n" for e in events))
    return path


def test_reject_original_future_source_before_transmission(tmp_path):
    path=write_events(tmp_path,[{"event":"tx","time":.2,"source_time":.229,
                                 "enqueue_time":.2,"admit_time":.2,"tx_time":.2}])
    with pytest.raises(AssertionError):ledger_audit(path)


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
