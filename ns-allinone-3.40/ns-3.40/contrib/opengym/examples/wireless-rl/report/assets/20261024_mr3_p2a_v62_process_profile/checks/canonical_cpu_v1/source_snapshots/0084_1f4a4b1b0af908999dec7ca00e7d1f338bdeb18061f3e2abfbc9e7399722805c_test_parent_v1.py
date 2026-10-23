"""CPU contracts for the V62 parent; all children below are artificial toys."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

import pytest


HERE = Path(__file__).resolve().parent


def load(name, file):
    definition = importlib.util.spec_from_file_location(name, file)
    module = importlib.util.module_from_spec(definition)
    definition.loader.exec_module(module)
    return module


def parent():
    path = HERE/'run_profile_v1.py'
    if not path.exists():
        path = HERE/'p2a62_run_profile_draft_v1.py'
    return load('_v62_artificial_parent', path)


def test_real_nonzero_child_wait_is_preserved(tmp_path):
    module = parent()
    result = module.wait_command(module.helpers(),
        ['/usr/bin/python3', '-B', '-c', 'import time; time.sleep(.05); raise SystemExit(7)'],
        tmp_path/'toy.log')
    (tmp_path/'toy_actual_wait.json').write_text(json.dumps(result, indent=2))
    assert result['actual_waited'] is True and result['actual_returncode'] == 7
    assert result['identity']['pid'] > 0 and result['identity']['start_ticks'] > 0
    assert result['ended_monotonic_ns'] > result['started_monotonic_ns']
    assert not result['deadline_triggered'] and not result['wait_errors']


def test_deadline_cannot_be_erased_by_late_zero_exit(tmp_path):
    module = parent()
    result = module.wait_command(module.helpers(), ['/usr/bin/python3', '-B', '-c',
        'import signal,time; signal.signal(signal.SIGINT,lambda *_:exit(0)); time.sleep(60)'],
        tmp_path/'deadline_toy.log', stop_deadline=time.monotonic()+.5)
    (tmp_path/'toy_actual_wait.json').write_text(json.dumps(result, indent=2))
    assert result['actual_waited'] is True and result['actual_returncode'] == 0
    assert result['deadline_triggered'] and result['wait_errors']
    assert result['signals'][0]['signal'] == 2 and result['signals'][0]['sent']


def test_signal_observation_error_does_not_abandon_child_wait(tmp_path):
    module = parent()
    real = module.helpers()
    class FaultOnce:
        calls = 0
        identity = staticmethod(real.identity)
        owned_signal = staticmethod(real.owned_signal)
        def current(self, saved):
            self.calls += 1
            if self.calls == 1:
                raise ValueError('artificial transient observation error')
            return real.current(saved)
    result = module.wait_command(FaultOnce(),
        ['/usr/bin/python3', '-B', '-c', 'import time; time.sleep(60)'],
        tmp_path/'observation_toy.log', stop_deadline=time.monotonic()+.2)
    (tmp_path/'toy_actual_wait.json').write_text(json.dumps(result, indent=2))
    assert result['actual_waited'] is True and result['actual_returncode'] == -15
    assert result['deadline_triggered'] and len(result['wait_errors']) >= 2


def setup_partial(module, monkeypatch, tmp_path, start):
    module.STATE = tmp_path/'synthetic_parent'
    module.STATE.mkdir()
    module.SCOPE = tmp_path/'synthetic_scope.json'
    owner = module.helpers().identity(os.getpid())
    (module.STATE/'pre_exec_ancestry_v1.json').write_text(json.dumps(dict(
        execution_freeze='a'*40, bootstrap_identity=owner,
        complete_parent_started_monotonic_ns=start, observed_ancestors=[])))
    monkeypatch.setattr(sys, 'argv', ['artificial_parent', '--freeze', 'a'*40])


def test_bad_scope_still_settles_complete_measured_fee(monkeypatch, tmp_path):
    module = parent()
    setup_partial(module, monkeypatch, tmp_path, time.monotonic_ns())
    module.SCOPE.write_text('{bad JSON')
    assert module.main() == 1
    result = json.loads((module.STATE/'summary.json').read_text())
    assert result['complete_parent_fee_known'] is True
    assert result['actual_parent_seconds'] is not None
    assert result['engineering_cumulative_seconds'] is not None
    assert result['errors'] and result['launcher'] is None
    assert result['P2A_complete'] is False


@pytest.mark.parametrize('bad_start', [None, '123', -1, True])
def test_bad_bootstrap_start_remains_unknown_not_fake_fee(monkeypatch, tmp_path, bad_start):
    module = parent()
    setup_partial(module, monkeypatch, tmp_path, bad_start)
    assert module.main() == 1
    result = json.loads((module.STATE/'summary.json').read_text())
    assert result['complete_parent_fee_known'] is False
    assert result['actual_parent_seconds'] is None
    assert result['engineering_cumulative_seconds'] is None
    assert float(result['observed_driver_lower_bound_seconds']) >= 0
    assert result['errors'] and result['launcher'] is None


def test_failed_admission_still_attempts_source_after(monkeypatch, tmp_path):
    module = parent()
    setup_partial(module, monkeypatch, tmp_path, time.monotonic_ns())
    module.SCOPE.write_text('{}')
    calls = []
    def fail_verify(*args):
        calls.append('actual source check attempted')
        raise ValueError('artificial admission refusal')
    monkeypatch.setattr(module, 'verify', fail_verify)
    assert module.main() == 1
    result = json.loads((module.STATE/'summary.json').read_text())
    assert len(calls) == 2 and result['post_source_check_attempted']
    assert result['complete_parent_fee_known'] and result['errors']


def test_bootstrap_exec_failure_preserves_real_interval(monkeypatch, tmp_path):
    path = HERE/'bootstrap_v1.py'
    if not path.exists():
        path = HERE/'p2a62_bootstrap_draft_v1.py'
    module = load('_v62_artificial_bootstrap', path)
    module.ROOT = HERE
    module.W = tmp_path
    module.STATE = tmp_path/'synthetic_bootstrap'
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, 'argv', ['artificial_bootstrap', '--freeze', 'b'*40])
    def refuse_exec(*args):
        raise OSError('artificial exec failure; no child started')
    monkeypatch.setattr(module.os, 'execv', refuse_exec)
    with pytest.raises(OSError, match='artificial exec failure'):
        module.main()
    result = json.loads((module.STATE/'bootstrap_failure_v1.json').read_text())
    assert result['saved_identity']['pid'] == os.getpid()
    assert result['ended_monotonic_ns'] >= result['started_monotonic_ns']
    assert float(result['actual_parent_seconds']) >= 0
    assert result['engineering_cumulative_seconds'] is None and not result['native_started']
