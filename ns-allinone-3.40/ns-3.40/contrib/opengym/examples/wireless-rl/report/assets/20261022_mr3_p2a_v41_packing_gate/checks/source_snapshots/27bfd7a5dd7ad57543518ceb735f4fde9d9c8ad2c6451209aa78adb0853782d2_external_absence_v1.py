"""V41 saved-identity absence wrapper; no scientific consumer or signals.

The frozen A16 inspect function and its PID/start/Z rules execute unchanged.
Only the Evidence subclass adds the remaining declared stage/extra inventories.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace


ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
HELPER = W / 'report/assets/20261019_mr3_p2a_v16/external_absence_v1.py'
HELPER_SHA256 = 'cedae11c4b9bbf6f4887ae5afe2fa10fff04e5a28595f5c9e748669c8d18493f'
EXCLUDED_PARTS = frozenset(('execution_inputs', 'inputs', 'observation_archive',
                            'navigation_archive', 'map_blobs', 'costmap_blobs'))
# These raw native telemetry streams are not process inventories. In particular,
# transitions/adapter/costmaps can contain actor observations or map payloads.
EXCLUDED_JSONL = frozenset(('transitions.jsonl', 'adapter.jsonl', 'costmaps.jsonl',
    'physics.jsonl', 'motion_safety.jsonl', 'information.jsonl', 'odometry.jsonl',
    'motion_phase_worker.jsonl', 'drive_phase_worker.jsonl',
    'control_phase_worker.jsonl', 'evaluator_phase_worker.jsonl',
    'plant_stimulus_worker.jsonl'))


def fingerprint(path):
    path = Path(path)
    before = path.stat()
    digest, size = hashlib.sha256(), 0
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
            size += len(chunk)
    after = path.stat()
    fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
    old, new = [getattr(before, k) for k in fields], [getattr(after, k) for k in fields]
    if old != new:
        raise ValueError('file changed while hashing: ' + str(path))
    return {'path': str(path), 'bytes': size, 'sha256': digest.hexdigest(), 'stat': new}


def load_helper():
    raw = HELPER.read_bytes()
    if hashlib.sha256(raw).hexdigest() != HELPER_SHA256:
        raise ValueError('immutable A16 external absence helper differs')
    spec = importlib.util.spec_from_file_location('_v41_original_external_absence', HELPER)
    module = importlib.util.module_from_spec(spec)
    exec(compile(raw, str(HELPER), 'exec'), module.__dict__)
    return module


def selected_paths(root, *, extra=False):
    root = Path(root)
    if not root.exists():
        return set()
    candidates = root.rglob('*') if root.is_dir() else [root]
    result = set()
    for path in candidates:
        if not path.is_file() or EXCLUDED_PARTS.intersection(path.parts):
            continue
        if path.suffix == '.json' or path.name == 'launch.log':
            result.add(path)
        elif extra and path.suffix == '.jsonl' and path.name not in EXCLUDED_JSONL:
            result.add(path)
        elif extra and (path.suffix == '.log' or path.name in ('console', 'stdout', 'stderr')):
            result.add(path)
    return result


def inspect(args):
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(output)
    helper = load_helper()
    plan_path = args.plan.resolve(strict=True)
    plan_raw = plan_path.read_bytes()
    plan = helper.parse(plan_raw)
    matrix = Path(plan['output_directory']).resolve(strict=True)
    outer = args.matrix_outer.resolve(strict=True)
    stages = [Path(stage['run_directory']).resolve() for stage in plan['stages']]
    if not stages:
        raise ValueError('plan has no declared native stage')
    run = stages[0].resolve(strict=True)
    extras = [Path(path).resolve(strict=True) for path in args.extra]
    all_roots = list(dict.fromkeys([matrix, outer, *stages, *extras]))
    if any(output == root or output.is_relative_to(root) for root in all_roots):
        raise ValueError('output must be outside every closed evidence root')
    sources = [plan_path, HELPER.resolve(strict=True), Path(__file__).resolve(strict=True)]
    source_before = [fingerprint(path) for path in sources]
    if source_before[0]['sha256'] != hashlib.sha256(plan_raw).hexdigest():
        raise ValueError('plan changed before its source binding was captured')

    def membership():
        # Match the original three-root selection exactly, then add inventories.
        paths = {p for root in (matrix, outer, run) for p in root.rglob('*.json')
                 if p.is_file() and 'execution_inputs' not in p.parts}
        if (matrix / 'ledger.jsonl').is_file():
            paths.add(matrix / 'ledger.jsonl')
        paths.update(p for p in run.rglob('launch.log') if p.is_file())
        for root in stages[1:]:
            paths.update(selected_paths(root))
        for root in extras:
            paths.update(selected_paths(root, extra=True))
        return sorted(paths)

    paths_before = membership()
    roots_before = {str(root): root.exists() for root in all_roots}
    original_evidence = helper.Evidence
    augmented_instances = []

    class Evidence(original_evidence):
        def __init__(self):
            super().__init__()
            augmented_instances.append(self)
            for path in paths_before:
                try:
                    self.consume(path)
                except (OSError, ValueError, TypeError) as error:
                    self.error(str(path), error)

        def consume(self, path):
            if path not in self.stat_before:
                super().consume(path)

        def finish(self):
            super().finish()
            if membership() != paths_before or roots_before != {str(root): root.exists() for root in all_roots}:
                self.error('closed inventory', 'selected file/root membership changed during absence check')
            for row in self.bindings:
                try:
                    after = fingerprint(Path(row['path']))
                    if any(after[key] != row[key] for key in ('sha256', 'bytes')):
                        self.error(row['path'], 'closed input bytes changed during absence check')
                except (OSError, ValueError) as error:
                    self.error(row['path'], error)

    helper.Evidence = Evidence
    try:
        result = helper.inspect(SimpleNamespace(matrix=matrix, outer=outer, run=run, output=output))
    finally:
        helper.Evidence = original_evidence
    source_after = [fingerprint(path) for path in sources]
    stable = source_before == source_after
    membership_stable = (membership() == paths_before and roots_before == {
        str(root): root.exists() for root in all_roots})
    if not stable:
        result['errors'].append({'source': 'wrapper/plan/helper', 'reason': 'source changed during absence check'})
        result['passed'] = result['all_saved_identities_absent'] = False
    if not membership_stable:
        result['errors'].append({'source': 'closed inventory', 'reason': 'final selected membership differs'})
        result['passed'] = result['all_saved_identities_absent'] = False
    result.update(wrapper_schema='mr3-v41-external-absence-wrapper-v1',
        source_before=source_before, source_after=source_after, source_stable=stable,
        plan=str(plan_path), stage_native_roots=[str(p) for p in stages],
        extra_roots=[str(p) for p in extras],
        inventory_membership_stable=membership_stable,
        selected_inventory_paths=[str(p) for p in paths_before],
        original_inspect_unchanged=True, helper_sha256=HELPER_SHA256,
        activity_pass_inferred=False,
        enumeration_scope='Original matrix/outer/first-native boundary plus remaining existing stage JSON/launch inventories and explicitly supplied extra process JSON/JSONL/consoles; raw telemetry and actor/map payloads excluded from additions.')
    evidence = augmented_instances[0]
    result['matrix_activity_passed'] = evidence.documents.get(str(matrix / 'summary.json'), {}).get('passed')
    result['matrix_outer_passed'] = evidence.documents.get(str(outer / 'actual_wait.json'), {}).get('passed')
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--matrix-outer', type=Path, required=True)
    parser.add_argument('--extra', type=Path, action='append', default=[])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    result = inspect(args)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'passed': result['passed'], 'identity_count': result['identity_count'],
                      'source_stable': result['source_stable'], 'output': str(args.output)}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
