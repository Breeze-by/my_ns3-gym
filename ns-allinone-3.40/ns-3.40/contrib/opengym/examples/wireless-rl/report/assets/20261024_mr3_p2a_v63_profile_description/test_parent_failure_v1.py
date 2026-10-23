"""Only new parent early-failure receipts; no descriptor/raw-profile process."""
import importlib.util
import json
import os
from pathlib import Path
import time
from unittest import mock

HERE=Path(__file__).resolve().parent


def parent():
    spec=importlib.util.spec_from_file_location('_v63_parent_failure_only',HERE/'run_description_v1.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_primitive_import_failure_keeps_unknown_complete_fee_and_real_lower_bound(tmp_path):
    module=parent();module.STATE=tmp_path
    with mock.patch.object(module,'primitives',side_effect=ValueError('synthetic source import refusal')):
        assert module.main(['--freeze','a'*40]) == 1
    value=json.loads((tmp_path/'summary.json').read_text())
    assert value['complete_parent_fee_known'] is False and value['actual_parent_seconds'] is None
    assert value['engineering_cumulative_seconds'] is None and value['consumer'] is None
    assert float(value['observed_driver_lower_bound_seconds']) >= 0
    assert value['post_source_check_attempted'] and value['errors']


def test_bootstrap_pid_start_mismatch_never_becomes_complete_fee(tmp_path):
    module=parent();module.STATE=tmp_path
    h,_=module.primitives()
    owner=h.identity(os.getpid());owner['start_ticks']+=1
    (tmp_path/'pre_exec_ancestry_v1.json').write_text(json.dumps(dict(
        complete_parent_started_monotonic_ns=time.monotonic_ns()-1000,
        execution_freeze='a'*40,bootstrap_identity=owner,observed_ancestors=[])))
    assert module.main(['--freeze','a'*40]) == 1
    value=json.loads((tmp_path/'summary.json').read_text())
    assert value['complete_parent_fee_known'] is False and value['actual_parent_seconds'] is None
    assert value['engineering_cumulative_seconds'] is None and value['consumer'] is None
    assert any('PID/start differs' in row['reason'] for row in value['errors'])
