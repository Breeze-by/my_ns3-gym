"""Independent CPU replay of existing actor81 frontier-union evidence only."""

import ast
import copy
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import FunctionType

import numpy as np
from scipy import ndimage


ROOT = Path('/home/zhuyulab/ns3-workspace')
ROS = ROOT / 'ros2_ws/ros2-multi-robot-automap'
RUN = ROS / 'log/mr3_ppo/mr3_p2a_v6_pilot'
V5 = RUN.parent / 'mr3_p2a_v5_pilot'
CAPTURE = V5 / 'raw_map_observer_round0002_w3_v1'
component = ROS / 'src/multi_robot_exploration/multi_robot_exploration'
FREEZE = 'af37b2aaa3cb9980434f7f16c1f52dec2506319d'
PROTOTYPE_VERSION = 'mr3-per-robot-geometric-staging-v4-offline-prototype'
sys.path.insert(0, str(component.parent))
from multi_robot_exploration import mr3_observation as m


def load(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def main():
    helper = RUN / 'frontier_union_feasibility_v6.py'
    receipt_path = RUN / 'frontier_union_feasibility_v6.json'
    receipt = load(receipt_path)
    assert sha(helper) == '02f139f4c5bec27c5aafdab954a6f1e9a1360d98f6c32cf5da4e1a83f82783db'
    assert sha(receipt_path) == '2dc5961c4dc4e524aec9e8906c76247f190b4a7d97f8cecb18625ac698cd1c8d'
    for relative, proof in receipt['inputs'].items():
        assert sha(ROOT / relative) == proof['sha256']
    source = component / 'mr3_observation.py'
    assert source.read_bytes() == subprocess.check_output(
        ['git', 'show', FREEZE + ':' + str(source.relative_to(ROOT))], cwd=ROOT)
    # Extract only pure definitions, avoiding the helper's writes/top-level replay.
    tree = ast.parse(helper.read_text())
    selected = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                and node.name in {'frontiers', 'union_frontiers', 'prototype_scope'}]
    assert len(selected) == 3
    scope = dict(globals())
    exec(compile(ast.Module(body=selected, type_ignores=[]), 'reviewed-pure-functions', 'exec'),
         scope)
    events = [json.loads(x) for x in (CAPTURE / 'events.jsonl').read_text().splitlines()]
    bundle = next(row['payload'] for row in events if row['kind'] == 'map_metadata')
    captured = next(row for row in events if row['kind'] == 'actor_snapshot'
                    and row['sequence'] == 81 and row['saved_line_proof'] is not None)
    actor = json.loads(gzip.decompress((CAPTURE / captured['artifact']).read_bytes()))

    def payload(digest):
        encoded = gzip.decompress((CAPTURE / 'maps' / (digest + '.json.gz')).read_bytes())
        assert hashlib.sha256(encoded).hexdigest() == digest
        value = json.loads(encoded)
        assert value['header']['frame_id'] == 'map'
        assert value['info']['origin']['orientation'] == {'w': 1., 'x': 0., 'y': 0., 'z': 0.}
        return value

    fused = payload(bundle['map_payload_sha256'])
    own = {name: payload(bundle['map_sources'][name]['payload_sha256']) for name in m.ROBOT_NAMES}

    def geometry(value):
        info = value['info']
        return (np.asarray(value['data'], dtype=np.int16).reshape(info['height'], info['width']),
                info['resolution'], tuple(info['origin']['position'][key] for key in ('x', 'y')))

    raw, resolution, origin = geometry(fused)
    maps = {}
    for name in m.ROBOT_NAMES:
        grid, native_resolution, native_origin = geometry(own[name])
        maps[name] = {'grid': grid, 'resolution': native_resolution, 'origin': native_origin,
                      'epoch': actor['epoch'], **bundle['map_sources'][name]}
        assert maps[name]['source_stamp'] <= maps[name]['received_stamp'] <= actor['source_stamp']
    before = {name: maps[name]['grid'].tobytes() for name in maps}
    fused_before = raw.tobytes()
    union, contributions = scope['union_frontiers'](raw, resolution, origin, maps)
    # Independent scalar projection via the normative containing-cell routine.
    expected = scope['frontiers'](raw)
    max_shift = 0.
    for name in m.ROBOT_NAMES:
        entry = maps[name]
        for row, column in np.argwhere(scope['frontiers'](entry['grid'])):
            x = entry['origin'][0] + (column + .5) * entry['resolution']
            y = entry['origin'][1] + (row + .5) * entry['resolution']
            cell = m._cell(x, y, resolution, origin, raw.shape)
            if cell is not None and raw[cell] == 0:
                expected[cell] = True
                centre = (origin[0] + (cell[1] + .5) * resolution,
                          origin[1] + (cell[0] + .5) * resolution)
                max_shift = max(max_shift, np.hypot(x - centre[0], y - centre[1]))
    assert np.array_equal(expected, union)
    assert np.all(raw[union] == 0)
    assert max_shift <= resolution / np.sqrt(2.)
    robots = copy.deepcopy(actor['robots'])
    for robot in robots:
        robot['navigation']['sequence'] = robot['navigation']['receipt_sequence']
    args = (raw, resolution, origin, robots, actor['source_stamp'], actor['epoch'],
            actor['map_version'], actor['sequence'])
    kwargs = {'robot_maps': maps, 'map_source_stamp': bundle['map_source_stamp'],
              'map_received_stamp': bundle['map_received_stamp'], 'map_sources': bundle['map_sources'],
              'task_start': actor['source_stamp'] - actor['task_elapsed_sec']}
    old = m.build_snapshot(*args, **kwargs)
    assert old == actor
    prototype_scope, build = scope['prototype_scope'](union)
    new = build(*args, **kwargs)
    new['candidate_rule'].update(frontier_sources=['fused_received'] +
        ['received_own:' + name for name in m.ROBOT_NAMES],
        frontier_projection='world cell centre to containing fused native cell; free endpoints only')
    keys = ('epoch', 'map_version', 'sequence', 'candidate_rule', 'candidates', 'path_maps')
    new['candidate_version'] = hashlib.sha256(canonical({key: new[key] for key in keys})).hexdigest()
    new['digest'] = m.snapshot_digest(new)
    saved = RUN / 'frontier_union_feasibility_v6'
    assert load(saved / 'old_v5_actor81_old_snapshot.json') == old
    assert load(saved / 'old_v5_actor81_prototype_snapshot.json') == new
    assert old['path_maps'] == new['path_maps'] and old['robots'] == new['robots']
    assert old['maps'] == new['maps'] and raw.tobytes() == fused_before
    assert all(maps[name]['grid'].tobytes() == before[name] for name in maps)
    assert old['diagnostics']['per_robot_reachable_target_cells'] == new['diagnostics'][
        'per_robot_reachable_target_cells']
    assert [i for i, (a, b) in enumerate(zip(old['joint_action_mask'], new['joint_action_mask']))
            if a != b] == [88]
    per_robot, joint, _ = m._action_masks(new['robots'], new['candidates'], new['source_stamp'])
    assert per_robot == new['per_robot_action_mask'] and joint == new['joint_action_mask']
    assert all(row['new_actual_candidates_or_mask'] is None
               for row in receipt['v6_prefix20_exact_scope_limits'])
    assert 'rclpy' not in sys.modules and 'torch' not in sys.modules
    review = {'schema': 'mr3-independent-frontier-union-feasibility-review-v1', 'passed': True,
              'helper_sha256': sha(helper), 'receipt_sha256': sha(receipt_path),
              'source_freeze_for_equal_observation_bytes': FREEZE,
              'actual_counterfactual_native_evidence_freeze':
                  'de7a805af9cd9bc7d1b24e60559ccc4d3054e4c3',
              'actual_state_scope': 'Only old-v5 round0002 worker3 actor81; NOT current V6 prefix.',
              'old_entire_native_snapshot_replayed': True,
              'prototype_entire_saved_snapshot_replayed': True,
              'independent_containing_cell_projection_equal': True,
              'all_union_frontier_endpoints_fused_known_free': True,
              'max_observed_projection_shift_m': float(max_shift),
              'declared_projection_shift_upper_bound_m': resolution / np.sqrt(2.),
              'raw_grids_maps_states_paths_and_target_counts_unchanged': True,
              'joint_mask_changed_indices': [88],
              'old_joint_legal_actions': sum(old['joint_action_mask']),
              'prototype_joint_legal_actions': sum(new['joint_action_mask']),
              'new_tb1_candidate': new['candidates'][0],
              'production_qualifiers': [
                  'Explicit new version/digest/freeze for source list, received map identities '
                  'and centre-to-containing-cell quantization. Existing1m/LOS applies to '
                  'projected fused-cell centres, not exact own-frontier centre distance.',
                  'The isolated helper assumes valid complete same-epoch nonfuture maps. '
                  'Production must reject/skip missing, wrong-epoch, future or wrong common-frame '
                  'geometry BEFORE frontier union, including maps that would otherwise inform '
                  'other robots whose own paths are valid. Preserve current received-store rules.',
                  'No stale-age policy is invented here; existing map ages remain explicit.'],
              'scope_limits': [
                  'No GT, grid clearing, unsafe-target relaxation, native/GPU/observer/optimizer job.',
                  'No current V6 counterfactual grids; no actual layered-costmap/Nav2 execution '
                  'or95% task success claim.',
                  'More frontier sources cannot fix an empty own-path/fused-arrival target intersection.',
                  'Original V5/V6 native outcomes, weights, current run and validation plan remain unchanged.'],
              'repro_script_sha256': sha(Path(__file__).resolve())}
    output = RUN / 'independent_frontier_union_feasibility_review_v6.json'
    with output.open('x') as stream:
        json.dump(review, stream, indent=2)
        stream.write('\n')
    print(json.dumps({'passed': True, 'output': str(output), 'sha256': sha(output),
                      'max_shift': float(max_shift), 'mask_delta': [88]}))


if __name__ == '__main__':
    main()
