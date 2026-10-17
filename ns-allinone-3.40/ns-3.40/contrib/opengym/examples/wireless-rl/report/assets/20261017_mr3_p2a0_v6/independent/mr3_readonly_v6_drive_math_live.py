"""Live same-file mathematical/sequence diagnostics, not a closed native audit."""
import argparse
from fractions import Fraction
import json
import math
from pathlib import Path
import time


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('run', type=Path)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    result = {'schema': 'mr3-v6-drive-live-math-v1', 'run': str(args.run),
              'wall_monotonic_ns': time.monotonic_ns(), 'episodes': [],
              'scope': 'Complete-line same-file live diagnostic only; no task, coverage, body response or closure credit. Frozen full consumer still mandatory.'}
    for ep in sorted(args.run.glob('worker*/episode*')):
        robots = {}
        for name in ('tb1', 'tb2', 'tb3'):
            path = ep / f'drive_{name}.jsonl'
            if not path.exists():
                robots[name] = {'available': False}
                continue
            errors, previous_seq, previous_clock, cmd_seq, act_seq = [], 0, None, 0, 0
            latest, last_act, counts = (0, 0., 0.), None, {}
            peak_rim, max_delta, minimum_alpha, first_act = 0., 0., 1., None
            with path.open() as stream:
                for text in stream:
                    if not text.endswith('\n'):
                        break
                    row = json.loads(text)
                    counts[row['kind']] = counts.get(row['kind'], 0) + 1
                    issues = []
                    if row['record_sequence'] != previous_seq+1:
                        issues.append('record sequence')
                    previous_seq = row['record_sequence']
                    if previous_clock is not None and row['sim_time_ns'] < previous_clock:
                        issues.append('source clock rewind')
                    previous_clock = row['sim_time_ns']
                    if row['kind'] == 'command_received':
                        if row['cmd_seq'] != cmd_seq+1:
                            issues.append('command sequence')
                        cmd_seq = row['cmd_seq']
                        latest = (cmd_seq, row['desired_v'], row['desired_w'])
                    elif row['kind'] == 'reset':
                        latest, last_act = (cmd_seq, 0., 0.), None
                    elif row['kind'] == 'actuation':
                        if row['actuation_seq'] != act_seq+1:
                            issues.append('actuation sequence')
                        act_seq = row['actuation_seq']
                        if (row['cmd_seq'], row['desired_v'], row['desired_w']) != latest:
                            issues.append('not locked latest received command')
                        if last_act is not None and row['sim_time_ns']-last_act != row['dt_ns']:
                            issues.append('dt is not actual source successor')
                        last_act = row['sim_time_ns']
                        first_act = row if first_act is None else first_act
                        a, dt, alpha = row['max_acceleration_mps2'], row['dt_sec'], row['alpha']
                        current, desired, applied = (row[k] for k in
                            ('current_rim_mps', 'desired_rim_mps', 'applied_rim_mps'))
                        finite = all(math.isfinite(v) for v in [a, dt, alpha, *current, *desired, *applied])
                        if not finite or a != 1. or dt <= 0 or not 0 <= alpha <= 1:
                            issues.append('invalid finite wheel inputs')
                        else:
                            q = Fraction.from_float
                            budget = q(a)*q(dt)
                            largest = max(abs(q(d)-q(c)) for c, d in zip(current, desired))
                            nominal = min(Fraction(1), budget/largest) if largest else Fraction(1)
                            if q(alpha) > nominal or abs(float(nominal)-alpha) > 1e-12:
                                issues.append('common alpha nominal fraction')
                            for c, d, out in zip(current, desired, applied):
                                if abs(q(out)-q(c)) > budget:
                                    issues.append('exact per-wheel acceleration budget')
                                if not min(q(c), q(d)) <= q(out) <= max(q(c), q(d)):
                                    issues.append('wheel reference outside convex segment')
                                if abs(out-(c+alpha*(d-c))) > 1e-12:
                                    issues.append('common-alpha reference equation')
                                peak_rim = max(peak_rim, abs(c), abs(out))
                                max_delta = max(max_delta, abs(out-c))
                            minimum_alpha = min(minimum_alpha, alpha)
                    if issues:
                        errors.append({'issues': issues, 'original': row})
            robots[name] = {'available': True, 'counts': counts, 'last_record_sequence': previous_seq,
                            'last_source_clock_ns': previous_clock, 'latest_command': latest,
                            'maximum_measured_or_applied_abs_rim_mps': peak_rim,
                            'maximum_abs_rim_step_mps': max_delta, 'minimum_alpha': minimum_alpha,
                            'first_actuation': first_act, 'errors': errors}
        result['episodes'].append({'directory': str(ep), 'robots': robots})
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps({'output': str(args.output), 'errors': [
        {name: len(value.get('errors', [])) for name, value in ep['robots'].items()}
        for ep in result['episodes']]}))


if __name__ == '__main__':
    main()
