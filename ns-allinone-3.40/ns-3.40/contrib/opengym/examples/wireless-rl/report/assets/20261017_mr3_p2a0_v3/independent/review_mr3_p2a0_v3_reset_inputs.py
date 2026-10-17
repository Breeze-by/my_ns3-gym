"""Per-closed-episode conda activity/probe/contact/phase/received-causality audit."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path('/home/zhuyulab/ns3-workspace')
BASE = ROOT / 'ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261017_v3_reset'
LEARNER = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
FREEZE = 'f9312e1ed245fb93af50614fd34c960870edb78d'
OUT = Path('/tmp/mr3_p2a0_v3_reset_inputs_independent_review.json')
sys.path.insert(0, str(LEARNER))
from mr3_learning.audit_activity import audit_episode as activity, audit_probe_activity
from mr3_learning.audit_motion import audit_episode as motion
from mr3_learning.audit_evaluator_phase import audit_episode as phase
from mr3_learning.audit_preparation import audit_probe_execution


def read(path):
    return json.loads(path.read_text())


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def forbid(value):
    if isinstance(value, dict):
        return bool(set(value) & {'control_failure_truth_diagnostic', 'latest_model_state_diagnostic',
                                  'latest_model_states'}) or any(forbid(v) for v in value.values())
    return isinstance(value, list) and any(forbid(v) for v in value)


def review(directory):
    errors = []
    def require(ok, message):
        if not ok:
            errors.append(message)
    meta = read(directory / 'metadata.json')
    summary = read(directory / 'summary.json')
    supervisor = read(directory / 'supervisor_shutdown.json')
    task = read(directory / (meta['epoch'] + '.json'))
    transitions = rows(directory / 'transitions.jsonl')
    steps = [row for row in transitions if row['kind'] == 'step']
    result = {'directory': str(directory), 'epoch': meta['epoch'], 'errors': errors}
    require(meta['freeze'] == FREEZE, 'source freeze mismatch')
    require(summary['launch_returncode'] == 0 and not summary['native_failures']
            and not summary['failures'], 'original native/task failure present')
    require(supervisor['worker_returncode'] == 0 and not supervisor['forced_shutdown']
            and not supervisor['failed_sample'] and not supervisor['remaining_owned_processes']
            and not supervisor['remaining_owned_zombies'], 'strict supervised closure unavailable')
    require(len(steps) == 16 and steps[-1]['truncated'] and not steps[-1]['terminated'],
            'declared sixteen-step external-cut episode not fulfilled')
    require(task['termination_reason'] == 'training_external_truncation'
            and not task['control_failure'] and task['navigation_protocol_closed'],
            'genuine task failure or incomplete frozen ownership')
    require(summary['closed']['pending_goal_count'] == 0
            and summary['closed']['epoch'] == meta['epoch'], 'pending/wrong-epoch goal ownership')
    for label, consumer in (('activity_integrity', activity),
                            ('activity_strict_probe', audit_probe_activity),
                            ('native_probe_execution', audit_probe_execution),
                            ('motion_source_and_actual_fifo', motion),
                            ('evaluator_phase', phase)):
        try:
            result[label] = consumer(directory)
            require(result[label]['passed'] is True, label + ' returned nonpass')
        except Exception as error:
            result[label] = {'passed': False, 'error': repr(error)}
            errors.append(label + ': ' + repr(error))
    monitor = task['contact_monitor_summary']
    components = [v for robot in monitor['components'].values() for v in robot.values()]
    require(len(components) == 18 and monitor['fresh'] and not monitor['ever_unhealthy']
            and not monitor['latched_issues'] and task['collision_monitoring_active']
            and task['collision_monitoring_fresh'] and task['collision_events'] == 0,
            'full-body contact streams unavailable or contact observed')
    require(all(v['accepted_message_count'] > 0 and not v['health_reason']
                and v['source_age_sec'] <= .5 and v['receipt_age_sec'] <= .5 for v in components),
            'component source/receipt freshness missing')
    require(not any(forbid(row['snapshot']) or forbid(row['info'].get('reward_diagnostics', {}))
                    for row in transitions), 'truth diagnostic entered actor/reward IPC')
    result.update(api_steps=len(steps), task_termination=task['termination_reason'],
                  original_control_failure=task['control_failure'],
                  contacts={'components': len(components), 'fresh': monitor['fresh'],
                            'collision_events': task['collision_events']},
                  artifact_sha256={name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
                    for name in ('metadata.json', 'transitions.jsonl', 'adapter.jsonl',
                                 'summary.json', 'supervisor_shutdown.json', meta['epoch'] + '.json')})
    result['passed'] = not errors
    return result


metadata = read(BASE / 'benchmark_metadata.json')
if not (metadata['freeze'] == FREEZE and metadata['workers'] == 2
        and metadata['robots_per_worker'] == 3 and not metadata['terminal_probe']):
    raise ValueError('benchmark identity mismatch')
results, waiting = [], []
for directory in sorted(BASE.glob('worker*/episode*')):
    required = ('summary.json', 'supervisor_shutdown.json', 'native_stop.json')
    if not all((directory / name).exists() for name in required):
        waiting.append(str(directory))
        continue
    output = Path('/tmp/mr3_p2a0_v3_reset_' + directory.parent.name + '_' + directory.name
                  + '_inputs_review.json')
    if output.exists():
        value = read(output)
        if any(hashlib.sha256((directory / name).read_bytes()).hexdigest() != digest
               for name, digest in value['artifact_sha256'].items()):
            raise ValueError('closed original artifacts changed after independent review')
    else:
        value = review(directory)
        output.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    results.append(value)
complete = len(results) == 8 and not waiting
result = {'schema': 'mr3-p2a0-v3-reset-input-review-v1', 'freeze': FREEZE,
          'status': 'COMPLETE' if complete else 'IN_PROGRESS',
          'passed': all(r['passed'] for r in results) if complete else None,
          'all_closed_inputs_passed': all(r['passed'] for r in results) if results else None,
          'declared_episodes': 8, 'closed_episodes': len(results), 'waiting': waiting,
          'episodes': results,
          'scope': 'conda raw received-odom/acceptance/probe, exact-clock input/actual FIFO, '
                   'full contact and scalar isolation review; no 1m/95%/learning or physical bound proof'}
OUT.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
print(json.dumps({'status': result['status'], 'passed': result['passed'],
                  'closed_episodes': len(results), 'all_closed_inputs_passed': result['all_closed_inputs_passed'],
                  'errors': {r['directory']: r['errors'] for r in results if r['errors']}, 'output': str(OUT)}))
sys.exit(1 if any(not r['passed'] for r in results) else 0)
