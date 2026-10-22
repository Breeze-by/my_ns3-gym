"""Bookkeeping only: AST-parse draft text and bind source files, never import it."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess

OUT = Path(__file__).parent
ROOT = Path('/home/zhuyulab/ns3-workspace')
WREL = 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/'
PURE = 'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/'
NATIVE = 'ros2_ws/ros2-multi-robot-automap/src/multi_robot/'
FREEZE = '23e909380b470039bd5680cf2d07710dca71097e'
EPISODE = ROOT / 'ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_reach_v50/mr3_p2a_reach_v50_reset/worker0/episode001_open_101'
paths = [PURE + name for name in ('motion_safety.py', 'mr3_reach_runtime.py', 'mr3_reach_geometry.py',
    'mr3_velocity_metric.py', 'mr3_safety_intent.py', 'mr3_information.py', 'peer_obstacles.py',
    'mr3_control_phase.py', 'mr3_motion_control.py', 'mr3_drive_phase.py', 'mr3_episode.py',
    'mr3_motion_safety.py', 'mr3_reach_support.py')]
paths += [NATIVE + name for name in ('src/mr3_gazebo_diff_drive.cpp', 'CMakeLists.txt',
    'include/multi_robot/mr3_drive_feed.hpp', 'include/multi_robot/paired_wheel_slew.hpp',
    'include/multi_robot/mr3_drive_target.hpp', 'include/multi_robot/mr3_odometry_json.hpp',
    'launch/gazebo_multirobot_mapping_with_nav2.launch.py')]
paths += [WREL + 'mr3_learning/' + name for name in
    ('audit_reach_runtime.py', 'reach_support_replay.py', '__init__.py')]
paths += ['ros2_ws/ros2-multi-robot-automap/scripts/mr3_env_worker.py']
evidence = []
for relative in sorted(paths):
    raw = (ROOT / relative).read_bytes()
    old = subprocess.check_output(['git', 'show', FREEZE + ':' + relative], cwd=ROOT, timeout=10)
    if raw != old:
        raise ValueError('source differs from original evidence freeze: ' + relative)
    evidence.append(dict(path=relative, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()))
candidates = []
for path in sorted(OUT.glob('*_v1.py')):
    raw = path.read_bytes()
    ast.parse(raw, filename=str(path))  # Syntax only; no compile/exec/import or function calls.
    candidates.append(dict(candidate_path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
                           syntax_AST_parsed=True, imported_or_executed=False))
(OUT / 'static_source_inventory_v1.json').write_text(json.dumps(dict(
    schema='mr3-single-ep-runtime-profile-static-inventory-v1', evidence_freeze=FREEZE,
    runtime_inputs_read=False, proc_read=False, candidate_or_reader_executed=False,
    candidate_sources=candidates, evidence_sources=evidence,
    original_source_proof_has_HEAD_or_clean_gate=False,
    original_source_proof_policy='23 named current bytes equal Git evidence freeze; no HEAD/status/clean requirement. Extra __init__ import source bound separately.',
    execution_source_seal_pending=True, native_or_training_credit=False), indent=2) + '\n')
names = ('metadata.json', 'supervisor_metadata.json', 'transitions.jsonl',
    'drive_tb1.jsonl', 'drive_tb2.jsonl', 'drive_tb3.jsonl',
    'odometry_tb1.jsonl', 'odometry_tb2.jsonl', 'odometry_tb3.jsonl',
    'motion_safety.jsonl', 'physics.jsonl', 'drive_phase_worker.jsonl',
    'control_phase_worker.jsonl', 'information_states.jsonl')
template = dict(schema='mr3-single-ep-runtime-profile-scope-v1',
    native_evidence_freeze=FREEZE, episode=str(EPISODE), epoch=None,
    main_seconds=840, tail_seconds=60, guard_cleanup_reserve_seconds=30,
    budget_admission=None, budget_admission_ref=dict(path=None, bytes=None, sha256=None),
    closed_inventory=dict(path=None, bytes=None, sha256=None),
    closed_review=dict(path=None, bytes=None, sha256=None),
    evidence_sources=evidence,
    execution_sources=[dict(path='REPLACE_WITH_NEW_CANONICAL_REPORT_PACKAGE/' + Path(row['candidate_path']).name,
        bytes=row['bytes'], sha256=row['sha256']) for row in candidates],
    inputs=[dict(logical_name=name, path=str(EPISODE / name), bytes=None, sha256=None) for name in names],
    preparation_only=True, admission_passed=False)
interpreter = Path('/usr/bin/python3').resolve()
raw = interpreter.read_bytes()
template['interpreter'] = dict(path=str(interpreter), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
(OUT / 'scope_TEMPLATE_NOT_ADMITTED.json').write_text(json.dumps(template, indent=2) + '\n')

