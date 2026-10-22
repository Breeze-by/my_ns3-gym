"""External finite-diagnostic closure; no actor, map or geometry replay."""
import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import time


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def gone(identity):
    try:
        text = Path('/proc/{}/stat'.format(identity['pid'])).read_text()
    except FileNotFoundError:
        return True
    fields = text[text.rfind(')') + 2:].split()
    return int(fields[19]) != identity['start_ticks']  # Z with same start is present.


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--outer', type=Path, required=True)
    p.add_argument('--result', type=Path, required=True)
    p.add_argument('--scope', type=Path, required=True)
    p.add_argument('--freeze', required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    errors, identities = [], []
    outer = json.loads(args.outer.read_text())
    scope = json.loads(args.scope.read_text())
    expected = [item.replace('{freeze}', args.freeze) for item in scope['execution_argv_template']]
    if (outer['actual_argv'] != expected or not outer['passed'] or not outer['source_unchanged']
            or not outer['actual_waited'] or outer['errors']):
        errors.append('main outer did not complete its exact stable command')
    for key in ('coordinator_identity', 'child_identity'):
        if isinstance(outer.get(key), dict): identities.append(outer[key])
    try:
        result = json.loads(args.result.read_text())
        if (result.get('error') or not result.get('source_stable')
                or result.get('source_freeze') != args.freeze):
            errors.append('main forensic result failed or belongs to another source')
        if isinstance(result.get('identity'), dict): identities.append(result['identity'])
    except (OSError, ValueError) as error:
        errors.append(repr(error))
    unique = {(v['pid'], v['start_ticks']): v for v in identities}
    for value in unique.values():
        try:
            if not gone(value): errors.append('original saved identity still present: '+str(value))
        except (OSError, ValueError, KeyError, IndexError) as error:
            errors.append('absence unreadable: '+repr(error))
    elapsed = Decimal(time.monotonic_ns() - outer['started_monotonic_ns']) / 10**9
    if elapsed > scope['activity_seconds_including_external_closure']:
        errors.append('external closure missed total diagnostic deadline')
    value = {'schema':'mr3-v35-forensic-external-final-v1','freeze':args.freeze,
        'main_outer_sha256':digest(args.outer),'result_sha256':digest(args.result) if args.result.exists() else None,
        'saved_identities':list(unique.values()),'elapsed_seconds':str(elapsed),
        'errors':errors,'passed':not errors,'qualification':False,'training_eligible':False,'native_credit':False}
    with args.output.open('x') as stream:
        stream.write(json.dumps(value,indent=2)+'\n')
    print(json.dumps({'passed':value['passed'],'saved_identities':len(unique)}))
    return 0 if value['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
