"""Finite metadata/source/process closure; never recompute scene geometry."""
import argparse
import hashlib
import json
import os
from pathlib import Path

ROOT = Path('/home/zhuyulab/ns3-workspace')


def identity(pid):
    fields = (Path('/proc') / str(pid) / 'stat').read_text().rsplit(')', 1)[1].split()
    return {'pid': pid, 'parent': int(fields[1]), 'group': int(fields[2]),
            'session': int(fields[3]), 'start_ticks': int(fields[19]), 'state': fields[0]}


def collect(value, saved):
    if isinstance(value, dict):
        if isinstance(value.get('pid'), int) and isinstance(value.get('start_ticks'), int):
            saved[(value['pid'], value['start_ticks'])] = value
        for child in value.values():
            collect(child, saved)
    elif isinstance(value, list):
        for child in value:
            collect(child, saved)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--guard', type=Path, required=True)
    parser.add_argument('--outer', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    errors, inputs, saved, absence = [], {}, {}, []
    for label, path in (('outer', args.outer),
                        ('guard', args.guard / 'guard_receipt_v1.json'),
                        ('geometry', args.guard / 'geometry_result.json')):
        try:
            inputs[label] = json.loads(path.read_text())
        except Exception as error:
            errors.append(f'{label}: {error!r}')
    outer, guard, geometry = (inputs.get(label, {}) for label in ('outer', 'guard', 'geometry'))
    if not (outer.get('scope') == 'engineering' and outer.get('passed')
            and outer.get('actual_waited') and outer.get('actual_returncode') == 0
            and outer.get('source_unchanged')):
        errors.append('main actual-wait/source failure retained')
    if not (guard.get('passed') and guard.get('actual_waited')
            and guard.get('actual_returncode') == 0 and guard.get('source_unchanged')
            and not guard.get('timed_out')):
        errors.append('guard actual-wait/source failure retained')
    if not (geometry.get('passed') and geometry.get('bound_bytes_unchanged')
            and not geometry.get('errors')):
        errors.append('geometry computation/source failure retained')
    try:
        assert geometry['schema'] == 'mr3-proxy2d-quality-geometry-v1'
        assert [row['scene'] for row in geometry['scenes']] == ['open', 'rooms', 'corridors']
        assert not geometry['qualification'] and not geometry['training_eligible'] and not geometry['native_credit']
        for relative, source in geometry['source_and_asset_bindings'].items():
            raw = (ROOT / relative).read_bytes()
            assert len(raw) == source['bytes']
            assert hashlib.sha256(raw).hexdigest() == source['sha256'], relative
        for row in geometry['scenes']:
            n = row['truth_occupied_cell_count']
            t = row['possible_endpoint_overlap_correct_occupied_cells']
            assert 0 <= t <= n and n > 0
            assert abs(row['conditional_occupied_iou_upper_enclosure'] - t / n) < 1e-15
            assert row['solid_occupied_cells_outside_surface_enclosure'] == n - t
    except Exception as error:
        errors.append(f'geometry metadata validation: {error!r}')
    for value in inputs.values():
        collect(value, saved)
    for (pid, start), record in sorted(saved.items()):
        row = {'saved_identity': record}
        try:
            current = identity(pid)
        except FileNotFoundError:
            row['status'] = 'gone'
        except Exception as error:
            row.update(status='unreadable', error=repr(error))
            errors.append(f'unreadable saved pid {pid}')
        else:
            row['current_identity'] = current
            row['status'] = 'reused' if current['start_ticks'] != start else 'present'
            if row['status'] == 'present':
                errors.append(f'saved pid still present, including zombie: {pid}')
        absence.append(row)
    result = {'schema': 'mr3-p2a-v26-final-metadata-v1', 'passed': not errors,
              'scope': __doc__, 'errors': errors, 'saved_processes': absence,
              'consumer_identity': identity(os.getpid()),
              'qualification': False, 'training_eligible': False, 'native_credit': False}
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'passed': not errors, 'errors': errors, 'saved_processes': len(absence)}))
    return 0 if not errors else 1


if __name__ == '__main__':
    raise SystemExit(main())
