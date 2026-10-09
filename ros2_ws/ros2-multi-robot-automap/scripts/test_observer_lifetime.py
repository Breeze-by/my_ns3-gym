import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import time
import pytest
from observer_lifetime import bind_to_owner

pytestmark=pytest.mark.skipif(sys.platform!='linux',reason='Linux owner-death binding')

def fixture_env():
    env=os.environ.copy()
    env['PYTHONPATH']=str(Path(__file__).resolve().parent)+os.pathsep+env.get('PYTHONPATH','')
    return env

def running(pid):
    try:return Path('/proc',str(pid),'stat').read_text().split()[2]!='Z'
    except (FileNotFoundError,ProcessLookupError):return False

@pytest.mark.parametrize('error',[FileNotFoundError,ProcessLookupError])
def test_proc_read_race_reports_a_vanished_child(monkeypatch,error):
    def disappeared(*args,**kwargs):raise error('child exited during /proc read')
    monkeypatch.setattr(Path,'read_text',disappeared)
    assert not running(1)

def test_proc_read_permission_error_is_not_reported_as_child_exit(monkeypatch):
    def denied(*args,**kwargs):raise PermissionError('unreadable child status')
    monkeypatch.setattr(Path,'read_text',denied)
    with pytest.raises(PermissionError):running(1)

def receive(process):
    deadline=time.monotonic()+3
    data=b''
    while not data.endswith(b'\n'):
        remaining=deadline-time.monotonic()
        assert remaining>0 and select.select([process.stdout],[],[],remaining)[0], 'owner/child did not start within wall budget'
        value=os.read(process.stdout.fileno(),1)
        assert value, 'owner/child closed stdout before readiness'
        data+=value
    return data.decode().strip()

def test_owner_death_kills_a_bound_observer_even_during_a_blocking_wait():
    child="from observer_lifetime import bind_to_owner; import time; bind_to_owner(); print('READY',flush=True); time.sleep(30)"
    owner="import os,subprocess,sys,time; env=os.environ.copy(); env['P3B5_OBSERVER_OWNER_PID']=str(os.getpid()); p=subprocess.Popen([sys.executable,'-c',sys.argv[1]],env=env); print('PID',p.pid,flush=True); time.sleep(30)"
    process=subprocess.Popen([sys.executable,'-c',owner,child],env=fixture_env(),stdout=subprocess.PIPE,text=True)
    pid=None
    try:
        lines=[receive(process),receive(process)]
        assert 'READY' in lines
        pid=int(next(x for x in lines if x.startswith('PID ')).split()[1])
        assert running(pid)
        process.kill();process.wait(timeout=3)
        deadline=time.monotonic()+3
        while running(pid) and time.monotonic()<deadline:time.sleep(.02)
        assert not running(pid), 'read-only observer survived owner death'
    finally:
        if process.poll() is None:process.kill();process.wait(timeout=3)
        if pid and running(pid):os.kill(pid,signal.SIGKILL)

def test_a_stale_owner_is_rejected_before_observer_initialization(monkeypatch):
    monkeypatch.setenv('P3B5_OBSERVER_OWNER_PID',str(os.getpid()))
    with pytest.raises(RuntimeError,match='owner already exited'):bind_to_owner()

def test_an_owner_lost_before_binding_does_not_leave_a_new_orphan():
    child="import time; time.sleep(.2); from observer_lifetime import bind_to_owner; bind_to_owner(); time.sleep(30)"
    owner="import os,subprocess,sys; env=os.environ.copy(); env['P3B5_OBSERVER_OWNER_PID']=str(os.getpid()); p=subprocess.Popen([sys.executable,'-c',sys.argv[1]],env=env); print(p.pid,flush=True)"
    process=subprocess.Popen([sys.executable,'-c',owner,child],env=fixture_env(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    pid=None
    try:
        pid=int(receive(process));process.wait(timeout=3)
        deadline=time.monotonic()+3
        while running(pid) and time.monotonic()<deadline:time.sleep(.02)
        assert not running(pid), 'observer continued after its owner vanished before binding'
        _,error=process.communicate(timeout=3)
        assert 'Read-only observer owner ' in error and 'exited' in error
    finally:
        if process.poll() is None:process.kill();process.wait(timeout=3)
        if pid and running(pid):os.kill(pid,signal.SIGKILL)
