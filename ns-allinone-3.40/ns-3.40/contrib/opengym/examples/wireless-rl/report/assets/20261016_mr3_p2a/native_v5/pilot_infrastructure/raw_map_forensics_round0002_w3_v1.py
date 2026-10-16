#!/usr/bin/python3
"""Pure CPU replay of one immutable asynchronous raw-map capture; no ROS imports."""

import ast
import copy
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import scipy
from scipy import ndimage


ROOT = Path('/home/zhuyulab/ns3-workspace')
ROS = ROOT / 'ros2_ws/ros2-multi-robot-automap'
RUN = ROS / 'log/mr3_ppo/mr3_p2a_v5_pilot'
CAPTURE = RUN / 'raw_map_observer_round0002_w3_v1'
OUTPUT = RUN / 'raw_map_forensics_round0002_w3_v1.json'
ROBOTS = ('tb1', 'tb2', 'tb3')
COMMAND = ('rtk proxy env PYTHONNOUSERSITE=1 /usr/bin/python3 '
           + str(Path(__file__).resolve()))
assert not OUTPUT.exists(), 'receipt exists; never overwrite prior evidence'
artifacts = {}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def read(path):
    payload = path.read_bytes()
    artifacts[str(path.relative_to(ROOT))] = {'sha256': sha(payload), 'bytes': len(payload)}
    return payload


def namespace(value):
    return SimpleNamespace(**{key: namespace(item) for key, item in value.items()}) \
        if isinstance(value, dict) else value


class OfflineGrid:
    """Message fields required by unmodified merge_maps; no ROS/DDS construction."""

    def __init__(self):
        self.header = namespace({'stamp': {'sec': 0, 'nanosec': 0}, 'frame_id': ''})
        self.info = namespace({'map_load_time': {'sec': 0, 'nanosec': 0}, 'resolution': 0.,
                               'width': 0, 'height': 0,
                               'origin': {'position': {'x': 0., 'y': 0., 'z': 0.},
                                          'orientation': {'x': 0., 'y': 0., 'z': 0., 'w': 0.}}})
        self.data = []


def message(payload):
    result = OfflineGrid()
    result.header, result.info, result.data = (namespace(payload['header']),
                                              namespace(payload['info']), payload['data'])
    return result


def grid(payload):
    info = payload['info']
    return np.asarray(payload['data'], np.int16).reshape(info['height'], info['width'])


def origin(payload):
    return tuple(payload['info']['origin']['position'][key] for key in ('x', 'y'))


meta = json.loads(read(CAPTURE / 'metadata.json'))
summary = json.loads(read(CAPTURE / 'summary.json'))
closure = json.loads(read(CAPTURE / 'closure_receipt.json'))
event_bytes = read(CAPTURE / 'events.jsonl')
events = [json.loads(line) for line in event_bytes.splitlines()]
assert summary['errors'] == [] and summary['wall_seconds'] <= 20.
assert closure['process_exit_code'] == 0 and closure['identity_absent'] is True
assert meta['epoch'] == 'round0002_w3_e1_f3a69ded' and meta['domain_id'] == 167
assert meta['native_freeze'] == 'de7a805af9cd9bc7d1b24e60559ccc4d3054e4c3'
sources = {}
for filename, expected in meta['source_sha256'].items():
    payload = Path(filename).read_bytes()
    assert sha(payload) == expected, filename
    sources[filename] = expected

# Execute original pure functions with their original function bodies. Only ROS
# imports and the episode import wiring are omitted; no algorithm is rewritten.
component = ROS / 'src/multi_robot_exploration/multi_robot_exploration'
scope = {'__name__': 'offline_native_observation_replay'}
episode_path = component / 'mr3_episode.py'
episode_source = read(episode_path)
exec(compile(episode_source, str(episode_path), 'exec'), scope)
observation_path = component / 'mr3_observation.py'
observation_source = read(observation_path)
tree = ast.parse(observation_source)
tree.body = [node for node in tree.body if not (
    isinstance(node, ast.ImportFrom) and node.module == 'multi_robot_exploration.mr3_episode')]
exec(compile(tree, str(observation_path), 'exec'), scope)
info_path = component / 'mr3_information.py'
info_tree = ast.parse(read(info_path))
serializer_names = {'stamp_payload', 'vector_payload', 'quaternion_payload', 'pose_payload',
                    'header_payload', 'map_payload', 'map_digest'}
serializer_scope = {'json': json, 'hashlib': hashlib}
exec(compile(ast.Module(body=[node for node in info_tree.body
                             if isinstance(node, ast.FunctionDef)
                             and node.name in serializer_names], type_ignores=[]),
             str(info_path), 'exec'), serializer_scope)
merge_path = ROS / 'src/merge_map/merge_map/merge_map.py'
merge_tree = ast.parse(read(merge_path))
merge_scope = {'math': math, 'np': np, 'OccupancyGrid': OfflineGrid}
exec(compile(ast.Module(body=[node for node in merge_tree.body
                             if isinstance(node, ast.FunctionDef) and node.name == 'merge_maps'],
                        type_ignores=[]), str(merge_path), 'exec'), merge_scope)
merge = merge_scope['merge_maps']
serialize = serializer_scope['map_payload']

maps = {}
for path in sorted((CAPTURE / 'maps').glob('*.json.gz')):
    encoded = gzip.decompress(read(path))
    assert sha(encoded) == path.name.removesuffix('.json.gz')
    payload = json.loads(encoded)
    assert canonical(payload) == encoded and serialize(message(payload)) == payload
    maps[sha(encoded)] = payload
bundles = [event['payload'] for event in events if event['kind'] == 'map_metadata']
assert len(bundles) == 1
bundle = bundles[0]
assert bundle['epoch'] == meta['epoch'] and set(bundle['map_sources']) == set(ROBOTS)
actors, native_line_bindings = {}, []
for path in sorted((CAPTURE / 'observations').glob('*.json.gz')):
    payload = json.loads(gzip.decompress(read(path)))
    assert sha(canonical(payload)) == path.name.removesuffix('.json.gz')
    assert scope['snapshot_digest'](payload) == payload['digest']
    actors[payload['sequence']] = payload
native_path = Path(meta['episode_directory']) / 'transitions.jsonl'
for event in events:
    proof = event.get('saved_line_proof')
    if event['kind'] != 'actor_snapshot' or proof is None:
        continue
    with native_path.open('rb') as stream:
        stream.seek(proof['complete_line_start_offset'])
        raw_line = stream.read(proof['complete_line_end_offset']
                               - proof['complete_line_start_offset'])
    assert sha(raw_line) == proof['line_sha256']
    record = json.loads(raw_line)
    assert record['snapshot'] == actors[event['sequence']]
    native_line_bindings.append({'sequence': event['sequence'], 'digest': event['digest'],
                                 'native_path': str(native_path.relative_to(ROOT)),
                                 'proof': proof})
actor = actors[81]
assert actor['epoch'] == bundle['epoch'] and actor['map_version'] == bundle['map_version']
assert actor['map']['sources'] == bundle['map_sources']
own = {name: maps[bundle['map_sources'][name]['payload_sha256']] for name in ROBOTS}
fused = maps[bundle['map_payload_sha256']]
for name in ROBOTS:
    assert actor['path_maps'][name]['payload_sha256'] == bundle['map_sources'][name]['payload_sha256']
    assert actor['path_maps'][name]['epoch'] == actor['epoch']
    for field in ('sequence', 'version', 'source_stamp', 'received_stamp'):
        assert actor['path_maps'][name][field] == bundle['map_sources'][name][field]
    raw_geometry = hashlib.sha256(canonical({'resolution': own[name]['info']['resolution'],
                                             'origin': origin(own[name]),
                                             'shape': list(grid(own[name]).shape)}))
    raw_geometry.update(np.asarray(grid(own[name]), dtype='<i2').tobytes())
    assert raw_geometry.hexdigest() == actor['path_maps'][name]['geometry_sha256']

replayed_hub = merge([message(own[name]) for name in ROBOTS], 'map')
assert canonical(serialize(replayed_hub)) == canonical(fused)
navigation = {}
for name in ROBOTS:
    output = serialize(merge([message(own[name]), replayed_hub], 'map'))
    captured = [event for event in events if event.get('topic') == f'/{name}/navigation_map']
    assert len(captured) == 1 and sha(canonical(output)) == captured[0]['payload_sha256']
    assert canonical(output) == canonical(maps[captured[0]['payload_sha256']])
    navigation[name] = {'replayed_payload_sha256': sha(canonical(output)),
                        'captured_payload_sha256': captured[0]['payload_sha256'],
                        'exact_full_payload_equal': True, 'equal_to_hub': output == fused}

res, org, raw = fused['info']['resolution'], origin(fused), grid(fused)
robot_maps = {name: {'grid': grid(own[name]), 'resolution': own[name]['info']['resolution'],
                    'origin': origin(own[name]), 'epoch': actor['epoch'],
                    **bundle['map_sources'][name]} for name in ROBOTS}
input_robots = copy.deepcopy(actor['robots'])
for robot in input_robots:
    # _robot_state names the incoming receipt metadata 'sequence', then saves
    # that exact scalar as navigation.receipt_sequence in the output snapshot.
    robot['navigation']['sequence'] = robot['navigation']['receipt_sequence']
rebuilt = scope['build_snapshot'](
    raw, res, org, input_robots, actor['source_stamp'], actor['epoch'],
    actor['map_version'], actor['sequence'], map_source_stamp=bundle['map_source_stamp'],
    map_received_stamp=bundle['map_received_stamp'], map_sources=bundle['map_sources'],
    task_start=actor['source_stamp'] - actor['task_elapsed_sec'], robot_maps=robot_maps)
if rebuilt != actor:
    differences = []

    def compare(left, right, path=''):
        if isinstance(left, dict) and isinstance(right, dict):
            for key in left.keys() | right.keys():
                compare(left.get(key), right.get(key), path + '/' + str(key))
        elif isinstance(left, list) and isinstance(right, list) and len(left) == len(right):
            for i, (a, b) in enumerate(zip(left, right)):
                compare(a, b, path + '/' + str(i))
        elif left != right:
            differences.append({'path': path, 'replayed': left, 'native': right})

    compare(rebuilt, actor)
    print(json.dumps({'snapshot_replay_differences': differences[:30]}, indent=2))
    raise AssertionError('full snapshot replay differs from captured native snapshot')

traversable, clearance = scope['native_traversable'](raw, res)
targets = np.argwhere(traversable & (clearance >= scope['TARGET_CLEARANCE_M']))
states = copy.deepcopy(actor['robots'])
paths, provenance, valid_seeds = scope['_own_map_paths'](
    robot_maps, states, actor['source_stamp'], actor['epoch'], res, org, targets)
points = np.column_stack((org[0] + (targets[:, 1] + .5) * res,
                          org[1] + (targets[:, 0] + .5) * res))
pose = np.asarray((states[0]['x'], states[0]['y']))
available = np.flatnonzero(np.isfinite(paths[:, 0])
                           & (np.linalg.norm(points - pose, axis=1) > .10))
assert len(available) == 2
frontier = (raw == 0) & ndimage.binary_dilation(raw < 0,
                                              structure=ndimage.generate_binary_structure(2, 1))
frontier_cells = np.argwhere(frontier)
frontier_xy = np.column_stack((org[0] + (frontier_cells[:, 1] + .5) * res,
                               org[1] + (frontier_cells[:, 0] + .5) * res))
own_grid, own_org, own_res = grid(own['tb1']), origin(own['tb1']), own['tb1']['info']['resolution']
own_frontier = np.argwhere((own_grid == 0) & ndimage.binary_dilation(
    own_grid < 0, structure=ndimage.generate_binary_structure(2, 1)))
own_frontier_xy = np.column_stack((own_org[0] + (own_frontier[:, 1] + .5) * own_res,
                                   own_org[1] + (own_frontier[:, 0] + .5) * own_res))
nav_seed, _, nav_diag = scope['_seed_diagnostics'](
    raw, traversable, clearance, states[0], res, org)
nav_paths, nav_ids = scope['_path_distances'](traversable, [nav_seed], res)
target_rows = []
for index in available:
    point, cell = points[index], targets[index]
    target_own = scope['_cell'](*point, own_res, own_org, own_grid.shape)
    visible = [i for i, frontier_cell in enumerate(own_frontier)
               if np.linalg.norm(own_frontier_xy[i] - point) <= 1.
               and scope['_known_line'](own_grid, target_own, tuple(frontier_cell))]
    native_distance = nav_paths[0, nav_ids[tuple(cell)]]
    target_rows.append({'fused_cell': cell.tolist(), 'world_xy_m': point.tolist(),
                        'own_path_distance_m': float(paths[index, 0]),
                        'fused_target_clearance_m': float(clearance[tuple(cell)]),
                        'nearest_fused_frontier_m': float(np.linalg.norm(
                            frontier_xy - point, axis=1).min()),
                        'nearest_own_frontier_m': float(np.linalg.norm(
                            own_frontier_xy - point, axis=1).min()),
                        'own_known_free_frontier_lines_within1m': len(visible),
                        'strict_current_navigation_start_path_finite': bool(
                            np.isfinite(native_distance))})
assert all(row['nearest_fused_frontier_m'] > 1. for row in target_rows)

# Prospective interface illustration only: one already certified target inserted
# into a detached candidate list; no runtime action, ranking or planner fallback.
index = available[0]
prospective_candidates = copy.deepcopy(actor['candidates'])
prospective_candidates[0] = {
    'index': 0, 'valid': True, 'x': float(points[index, 0]), 'y': float(points[index, 1]),
    'reachable': np.isfinite(paths[index]).tolist()}
_, prospective_mask, prospective_reasons = scope['_action_masks'](
    states, prospective_candidates, actor['source_stamp'])
prospective = {'label': 'offline prospective candidate insertion only; never executed',
               'candidate': prospective_candidates[0], 'joint_action': 88, 'choices': [0, 8, 8],
               'unchanged_joint_mask_legal': prospective_mask[88],
               'strict_current_navigation_route_certified': False,
               'caveat': 'Joint endpoint geometry can pass while the captured navigation '
                         'start cell is occupied; this is not a valid complete-route repair.'}


def source_support_at_cell(payload, output_cell):
    """Exact input-cell support under the unchanged merge_maps overlap arithmetic."""
    incoming = grid(payload)
    source_org = origin(payload)
    row, column = output_cell
    ox, oy = (org[0] - source_org[0]) / res, (org[1] - source_org[1]) / res
    first_c, last_c = math.floor(column + ox + 1e-9), math.ceil(column + ox + 1. - 1e-9) - 1
    first_r, last_r = math.floor(row + oy + 1e-9), math.ceil(row + oy + 1. - 1e-9) - 1
    values = [{'cell': [rr, cc], 'value': int(incoming[rr, cc])}
              for rr, cc in sorted(set((rr, cc) for rr in (first_r, last_r)
                                       for cc in (first_c, last_c)))
              if 0 <= rr < incoming.shape[0] and 0 <= cc < incoming.shape[1]]
    return {'intersecting_native_source_cells': values,
            'resampled_max_value': max((entry['value'] for entry in values), default=-1),
            'occupied_support': any(entry['value'] >= 50 for entry in values)}


source_support = {}
for name in ROBOTS:
    incoming = grid(own[name])
    src_org, src_res = origin(own[name]), own[name]['info']['resolution']
    occupied = np.argwhere(incoming >= 50)
    lower = np.column_stack((src_org[0] + occupied[:, 1] * src_res,
                              src_org[1] + occupied[:, 0] * src_res))
    point_to_square = np.linalg.norm(np.maximum(
        np.maximum(lower - pose, pose - (lower + src_res)), 0.), axis=1)
    src_cell = scope['_cell'](*pose, src_res, src_org, incoming.shape)
    source_support[name] = {
        'payload_sha256': bundle['map_sources'][name]['payload_sha256'],
        'epoch_version_sequence': {'epoch': bundle['epoch'], **bundle['map_sources'][name]},
        'raw_source_value_at_tb1_pose': int(incoming[src_cell]),
        'occupied_squares_intersecting_tb1_radius_0_25m': int((point_to_square <= .25).sum()),
        'occupied_squares_intersecting_tb1_radius_0_39m': int((point_to_square <= .39).sum()),
        'nearest_occupied_square_distance_from_tb1_m': float(point_to_square.min()),
        'support_for_actual_fused_navigation_start_cell': source_support_at_cell(
            own[name], nav_seed)}

receipt = {
    'schema': 'mr3-v5-round2-worker3-exact-rawmap-forensics-v1',
    'utc_analysis': datetime.now(timezone.utc).isoformat(), 'command': COMMAND,
    'cwd': str(ROOT), 'script_sha256': sha(Path(__file__).read_bytes()),
    'python': sys.executable, 'numpy': np.__version__, 'scipy': scipy.__version__,
    'execution': {'ROS_imported_or_initialized': False, 'observer_processes_started': 0,
                  'native_or_gpu_jobs': 0, 'optimizer_steps': 0, 'signals': 0,
                  'tracked_source_edits': 0, 'original_capture_or_native_files_modified': False},
    'capture': {'directory': str(CAPTURE.relative_to(ROOT)), 'epoch': meta['epoch'],
                'domain_id': meta['domain_id'], 'native_freeze': meta['native_freeze'],
                'completed_observer_wall_seconds': summary['wall_seconds'],
                'observer_errors': summary['errors']},
    'artifacts': artifacts, 'source_hashes_equal_capture_metadata': sources,
    'native_actor_line_bindings': native_line_bindings,
    'selected_exact_bundle': bundle,
    'selected_actor': {'sequence': 81, 'digest': actor['digest'],
                       'source_stamp': actor['source_stamp'],
                       'task_elapsed_seconds': actor['task_elapsed_sec'],
                       'full_source_map_epoch_version_sequence_payload_geometry_equal': True},
    'unchanged_merge_replay': {'all3_delivered_maps_to_hub_full_payload_equal': True,
                              'hub_sha256': bundle['map_payload_sha256'],
                              'own_plus_hub_to_navigation': navigation},
    'unchanged_observation_replay': {'full_snapshot_equal': True,
        'recomputed_snapshot_digest': rebuilt['digest'],
        'input_reconstruction': 'Exact saved navigation.receipt_sequence copied back to '
                                'input navigation.sequence, as named by _robot_state; no '
                                'map/state values invented.',
        'initial_CPU_replay_diagnostic': 'Direct reuse of postprocessed robot dictionaries '
                                         'initially omitted the renamed receipt_sequence '
                                         'for tb2/tb3; the only differing semantic leaves '
                                         'were null versus39/36. The inverse field-name '
                                         'mapping above restores full snapshot equality.',
        'tb1_seed': provenance['tb1'], 'candidate_diagnostics': rebuilt['diagnostics']},
    'tb1_actual_pre_frontier_targets': target_rows,
    'actual_navigation_start': {'received_pose': pose.tolist(),
                                'native_fused_cell': list(nav_seed),
                                'raw_value': int(raw[nav_seed]), 'diagnostics': nav_diag,
                                'no_start_snapping_clearing_or_unknown_fill': True},
    'per_source_observed_occupied_support': source_support,
    'offline_prospective_joint_mask_only': prospective,
    'findings': ['This capture exactly binds actor81 and its3 delivered raw maps/fused bundle; '
                 'the unmodified merger reproduces fused and all3 navigation payloads byte-for-byte.',
                 'For tb1 the actual target intersection contains2 points, but all392 fused '
                 'frontiers are more than1m away from feasible staging: pool0 occurs at the '
                 'frontier-stage cap, not K8 or joint conflict filtering.',
                 'The exact current navigation/fused grid independently marks the actual tb1 '
                 'start occupied100, so an unchanged .29m route certificate fails despite its '
                 'healthy own-map seed. Adding own-frontier endpoints alone is not sufficient '
                 'to certify complete-route feasibility.',
                 'Source attribution refers to received map evidence only. Occupancy support '
                 'from other robot map sources near the estimated tb1 body does not prove '
                 'which physical object, robot or wall produced a return.'],
    'limits': ['This is a newly captured asynchronous diagnostic of round0002 w3. It does not '
               'retroactively reconstruct round0000 w0 tb2 (whose target intersection was0).',
               'Actual Nav2 layered costmap, planner treatment of start/footprint, and execution '
               'of prospective targets were not observed or invoked. Raw-navigation certificate '
               'failure is not itself proof of a particular Nav2 rejection response.',
               'No source filtering, map cleaning, unknown clearing, candidate rule modification, '
               'hand goal, safety gate change or task-success relabeling was performed.']}
for relative, proof in artifacts.items():
    assert sha((ROOT / relative).read_bytes()) == proof['sha256'], relative
with OUTPUT.open('x') as stream:
    json.dump(receipt, stream, indent=2, allow_nan=False)
    stream.write('\n')
print(json.dumps({'receipt': str(OUTPUT), 'sha256': sha(OUTPUT.read_bytes()),
                  'actor_exact_replay': rebuilt['digest'], 'target_rows': target_rows,
                  'nav_start': receipt['actual_navigation_start'],
                  'source_support': source_support, 'prospective_joint': prospective}, indent=2))
