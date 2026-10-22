"""Artificial receipts verify that closure refuses a live saved identity."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('v35_final_fixture', Path(__file__).with_name('forensic_final_v1.py'))
f = importlib.util.module_from_spec(spec)
spec.loader.exec_module(f)


def identity(pid):
    text = Path('/proc/{}/stat'.format(pid)).read_text()
    return {'pid':pid,'start_ticks':int(text[text.rfind(')')+2:].split()[19])}


def exercise(tmp_path, saved):
    outer, result, scope, output = [tmp_path/name for name in ('outer.json','result.json','scope.json','final.json')]
    outer.write_text(json.dumps({'actual_argv':['artificial','a'*40], 'passed':True, 'source_unchanged':True,
        'actual_waited':True,'errors':[],'coordinator_identity':saved,'child_identity':saved,
        'started_monotonic_ns':time.monotonic_ns()}))
    result.write_text(json.dumps({'source_stable':True,'source_freeze':'a'*40,'identity':saved}))
    scope.write_text(json.dumps({'execution_argv_template':['artificial','{freeze}'],
                                'activity_seconds_including_external_closure':60}))
    args=['fixture','--outer',str(outer),'--result',str(result),'--scope',str(scope),
          '--freeze','a'*40,'--output',str(output)]
    with patch.object(sys,'argv',args): status=f.main()
    return status,json.loads(output.read_text())


def test_live_original_identity_is_preserved_as_failure(tmp_path):
    status, value = exercise(tmp_path,identity(os.getpid()))
    assert status==1 and not value['passed'] and value['errors']
    assert len(value['saved_identities'])==1


def test_reaped_original_identity_closes_without_actor_replay(tmp_path):
    child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(.05)'])
    saved=identity(child.pid)
    child.wait()
    status,value=exercise(tmp_path,saved)
    assert status==0 and value['passed'] and not value['errors']
    assert len(value['saved_identities'])==1
