"""Seal a two-worker startup diagnostic; never grant qualification or launch ROS."""
import hashlib
import json
from pathlib import Path

from mr3_learning.reach_preparation import source_inventory

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
ROS = ROOT / 'ros2_ws/ros2-multi-robot-automap'
A = Path(__file__).resolve().parent
PYTHON = '/home/zhuyulab/miniconda3/envs/ns3gym/bin/python'


def proof(path):
    path = Path(path).resolve(strict=True)
    raw = path.read_bytes()
    return dict(path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def main():
    prior = json.loads((A.parent / '20261022_mr3_p2a_v45_preparation_classification/plan_v1.json').read_text())
    paths = {ROOT / relative for relative in source_inventory() | prior['source_bindings'].keys()}
    # New tests must already be bound even before their first Git add. This is
    # the explicit classification repair retained from V45, not an outcome reuse.
    paths.update((ROS / 'src/multi_robot_exploration/test').glob('test_*.py'))
    paths.update(A.glob('*.py'))
    cpu_proofs = []
    for group in ('geometry_cpu_v2', 'learner_cpu_v2', 'reader_cpu_v2',
                  'snapshot_cpu_v2', 'readiness_cpu_v2', 'startup_review_cpu_v1'):
        wait_path = A / 'checks' / group / 'actual_wait.json'
        wait = json.loads(wait_path.read_text())
        if (wait.get('passed') is not True or wait.get('actual_waited') is not True
                or wait.get('actual_returncode') != 0 or wait.get('source_unchanged') is not True):
            raise ValueError('artificial prerequisite not passed: ' + group)
        # These groups execute the runtime/tests, not the separately reviewed
        # orchestration declarations also conservatively captured by the wrapper.
        # In particular the later direct-script -> module entry fix cannot
        # borrow an import check from a command that never executed that script.
        for row in wait['source_after']:
            path = Path(row['path'])
            if path in {A / name for name in ('prepare_startup_v1.py', 'run_startup_v1.py',
                                              'execute_startup_v1.py')}:
                continue
            raw = path.read_bytes()
            if len(raw) != row['bytes'] or hashlib.sha256(raw).hexdigest() != row['sha256']:
                raise ValueError('tested runtime/helper changed after CPU: ' + str(path))
        receipt_paths = [wait_path, A / 'checks' / group / 'console.log',
                         A / 'checks' / (group + '_source_recovery.json')]
        cpu_proofs.append(dict(id=group, inputs=[proof(p) for p in receipt_paths],
            scope='artificial checks only; neither qualification nor execution of the new orchestration entry'))
        paths.update(receipt_paths)
    helper = W / 'report/assets/20261019_mr3_p2a_v16/external_absence_v1.py'
    paths.add(helper)
    if hashlib.sha256(helper.read_bytes()).hexdigest() != 'cedae11c4b9bbf6f4887ae5afe2fa10fff04e5a28595f5c9e748669c8d18493f':
        raise ValueError('immutable identity parser changed')
    library = []
    for path, digest in prior['library_bindings'].items():
        row = proof(path)
        if row['sha256'] != digest:
            raise ValueError('installed binary changed: ' + path)
        library.append(row)
    run_root = ROS / 'log/mr3_p2a_reach_v49'
    run_id = 'mr3_p2a_reach_v49_startup'
    argv = [PYTHON, '-B', '-m', 'mr3_learning.benchmark', '--workers', '2',
        '--schedule', 'rooms:101', '--steps', '1', '--run-id', run_id,
        '--safety-contract', 'mr3-reach-v1', '--seed-rule', 'exact-point-bridge-v2',
        '--start-graph-rule', 'point-attachment-3x3-v1', '--reach-geometry-rule', 'cone-support-v2',
        '--diagnostic-uniform-seed', '490101', '--base-domain', '212', '--base-port', '15901',
        '--output-root', str(run_root), '--work-wall-seconds', '600', '--close-reserve-seconds', '120']
    scope = dict(schema='mr3-p2a-v49-startup-diagnostic-scope-v1',
        run_dir=str(run_root / run_id), driver_dir='/tmp/mr3_p2a_reach_v49_startup_driver',
        fixed_configuration=dict(workers=2, episodes_per_worker=1, scenes=['rooms'], seed=101, episode_steps=1),
        expected_job=argv, source_bindings=[proof(p) for p in sorted(paths)],
        cpu_preparation_proofs=cpu_proofs,
        library_bindings=library,
        reservation=dict(native_wall_seconds='600', external_tail_seconds='120', total='720'),
        engineering_entry_used_seconds='55747.0395659926018', engineering_ceiling_seconds='75000',
        pilot_changed=False, final_only_changed=False, optimizer_steps=0, gpu_calls=0,
        qualification_claimed=False, P2A_complete=False,
        no_retry=True,
        budget_semantics='Benchmark uses its existing admission/close guard. The 720s total is a post-wait resource gate, not an OS hard kill. Every overrun is charged and fails this new activity.',
        purpose='Check actual received-ready protocol, first-fault propagation and complete native closure before any new full qualification. No old failure is retried or relabelled.')
    with (A / 'startup_scope_v1.json').open('x') as f:
        json.dump(scope, f, indent=2, allow_nan=False)
        f.write('\n')
    print(json.dumps(dict(sealed=True, source_count=len(paths), libraries=len(library), native_started=False)))


if __name__ == '__main__':
    main()
