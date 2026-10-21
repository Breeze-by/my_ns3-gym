"""Metadata-only admission for the sole V26 geometry consumer, not a retry."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path('/home/zhuyulab/ns3-workspace')
A = Path(__file__).resolve().parent


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args], timeout=10)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9a-f]{40}', args.freeze):
        parser.error('complete exact40 freeze required')
    if args.output.exists():
        raise FileExistsError(args.output)
    plan = json.loads((A / 'predeclared_plan_v1.json').read_text())
    errors = []
    try:
        assert git('rev-parse', 'HEAD').decode().strip() == args.freeze
        assert git('rev-parse', 'origin/main').decode().strip() == args.freeze
        assert not git('status', '--porcelain'), 'clean pushed checkout required'
        assert plan['scenes'] == ['open', 'rooms', 'corridors']
        assert plan['engineering_entry_seconds'] == '45440.5368851356018'
        assert plan['activity_ceiling_seconds'] == '120'
        assert plan['consumer_ceiling_seconds'] == '90'
        assert plan['real_geometry_consumers'] == 1
        assert args.output == Path(plan['preflight_result'])
        for key in ('guard_output', 'main_outer', 'final_outer', 'final_result'):
            assert not Path(plan[key]).exists(), f'original exclusive output already exists: {key}'
        for relative, binding in plan['source_bindings'].items():
            raw = (ROOT / relative).read_bytes()
            assert len(raw) == binding['bytes']
            assert hashlib.sha256(raw).hexdigest() == binding['sha256'], relative
            assert git('show', args.freeze + ':' + relative) == raw, relative
    except Exception as error:
        errors.append(repr(error))
    result = {'schema': 'mr3-p2a-v26-preflight-v1', 'passed': not errors,
              'freeze': args.freeze, 'errors': errors,
              'scope': __doc__, 'source_bindings': plan['source_bindings'],
              'qualification': False, 'training_eligible': False, 'native_credit': False}
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps({'passed': not errors, 'errors': errors, 'bindings': len(plan['source_bindings'])}))
    return 0 if not errors else 1


if __name__ == '__main__':
    raise SystemExit(main())
