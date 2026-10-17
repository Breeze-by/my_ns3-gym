"""Isolated full-ledger replay for failed pre-release V9, no task credit."""
import collections
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path('/home/zhuyulab/ns3-workspace')
EP = ROOT / ('ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/'
             'mr3_p2a0_20261017_v9_interface/worker0/episode001_open_101')
READER = ROOT / ('ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/'
                 '20261017_mr3_p2a0_v9/independent/mr3_independent_information_v1.py')
OUT = Path('/tmp/mr3_p2a0_v9_interface_information_closed_diagnostic_v1.json')
FREEZE = '26534fae40409e266376baf0995fb15dc0223e4b'
EXPECTED = 'ba3e89fa6feda9406f984310adccf17c2f0638644fd0d26f0c2e9040ec0e7653'


def sha(path):
    value = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


assert sha(READER) == EXPECTED
spec = importlib.util.spec_from_file_location('frozen_independent_information_reader', READER)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
inputs = module.Inputs()
result = {'schema': 'mr3-v9-failed-startup-information-diagnostic-v1', 'passed': False,
          'overall_stage_passed': False, 'diagnostic_provenance_replay_passed': False,
          'freeze': FREEZE, 'episode': str(EP), 'consumer_sha256': EXPECTED,
          'inputs': inputs.bindings, 'errors': [],
          'scope': 'Isolated full raw producer/actual-receiver provenance replay only; no completed '
                   'reset/step/release, no formal episode/safety/physical/angular/settled credit.'}
try:
    meta = module.parse(inputs.read(EP, 'metadata.json'))
    assert meta['freeze'] == FREEZE
    result['epoch'] = meta['epoch']
    physics = inputs.rows(EP, 'physics.jsonl')
    result['physics_end_ns'] = max(row['end_time_ns'] for row in physics)
    transitions = inputs.rows(EP, 'transitions.jsonl')
    result['returned_transition_records'] = len(transitions)
    ledger = inputs.rows(EP, 'information_states.jsonl')
    motion = inputs.rows(EP, 'motion_safety.jsonl')
    replay = module.LedgerReplay(meta['epoch'])
    for line, row in enumerate(ledger, 1):
        try:
            replay.record(row)
        except Exception as error:
            raise ValueError('producer line' + str(line) + ': ' + repr(error)) from error
    result['producer_counts'] = replay.finish()
    result['motion_actual_receipt_and_decision_binding'] = module.audit_motion(
        motion, replay.published, meta['epoch'])
    kinds = collections.Counter(row['kind'] for row in motion)
    result['release_count'] = kinds['release']
    result['model_failure_count'] = kinds['settled_turn_model_failure']
    assert result['release_count'] == 0 and result['returned_transition_records'] == 0
    result['diagnostic_provenance_replay_passed'] = True
    result['nominal_state_cycles'] = len(replay.published)
    result['remaining_pending_inputs'] = {kind + ':' + robot: [
        {'input_sequence': row['sequence'], 'source_ns': row['source_ns'],
         'raw_sha256': row['raw_sha256']} for row in replay.pending[kind, robot]]
        for kind in ('odom', 'tf') for robot in module.ROBOTS}
except Exception as error:
    result['errors'].append(repr(error))
try:
    inputs.verify()
except Exception as error:
    result['diagnostic_provenance_replay_passed'] = False
    result['errors'].append(repr(error))
OUT.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + '\n')
print(json.dumps({'output': str(OUT), 'sha256': sha(OUT),
                  'overall_stage_passed': False,
                  'diagnostic_provenance_replay_passed': result['diagnostic_provenance_replay_passed'],
                  'errors': result['errors']}))
raise SystemExit(0 if result['diagnostic_provenance_replay_passed'] else 1)
