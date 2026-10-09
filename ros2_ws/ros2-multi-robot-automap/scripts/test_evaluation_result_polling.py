"""Read-only result polling tolerates an in-progress write, preserving hard errors."""
import json
import threading
import time
from types import SimpleNamespace

import pytest
import ros_smoke_test as smoke


def fault_result():
    return dict(episode_id='write_probe',termination_reason='timeout',task_phase='RALLY',
        success=False,elapsed_sim_time_sec=300.,model_state_message_count=1,robots={},
        collision_events=0,battery_minimum_energy=1.,start_sim_time_sec=0.)


def test_real_in_progress_file_write_is_read_once_complete(tmp_path,monkeypatch):
    result=tmp_path/'result.json';log=tmp_path/'launch.log';log.write_text('')
    result.write_text('{"episode_id":')
    original_sleep=time.sleep
    def finish():
        original_sleep(.08)
        result.write_text(json.dumps(fault_result()))
    writer=threading.Thread(target=finish);writer.start()
    monkeypatch.setattr(smoke.time,'sleep',lambda _:original_sleep(.01))
    try:
        value=smoke.wait_for_evaluation(SimpleNamespace(poll=lambda:None),result,log,1.,collect_fault_result=True)
        assert value==fault_result()
    finally:
        writer.join()


@pytest.mark.parametrize('text',['[]','{}'])
def test_completed_wrong_structure_still_fails_immediately(tmp_path,text):
    result=tmp_path/'result.json';result.write_text(text)
    with pytest.raises(RuntimeError):
        smoke.wait_for_evaluation(SimpleNamespace(poll=lambda:None),result,tmp_path/'absent.log',1.)


def test_unfinished_result_never_hides_producer_failure(tmp_path):
    result=tmp_path/'result.json';result.write_text('{')
    process=SimpleNamespace(poll=lambda:7,returncode=7)
    with pytest.raises(RuntimeError,match='launch exited.*7'):
        smoke.wait_for_evaluation(process,result,tmp_path/'absent.log',1.)


def test_invalid_result_remains_bounded_by_original_deadline(tmp_path,monkeypatch):
    result=tmp_path/'result.json';result.write_text('{')
    log=tmp_path/'launch.log';log.write_text('')
    original_sleep=time.sleep
    monkeypatch.setattr(smoke.time,'sleep',lambda _:original_sleep(.005))
    started=time.monotonic()
    with pytest.raises(TimeoutError):
        smoke.wait_for_evaluation(SimpleNamespace(poll=lambda:None),result,log,.04)
    assert time.monotonic()-started<.2
