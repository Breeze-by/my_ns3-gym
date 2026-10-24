"""Independent received-event replay; does not import the stimulus producer."""
import argparse
import hashlib
import json
import math
from pathlib import Path


def require(value, reason):
    if not value:
        raise ValueError(reason)


def number(value):
    return type(value) in (float, int) and math.isfinite(value)


def replay(rows, decisions, expected_steps=96):
    require(len(rows) == expected_steps + 1 and len(decisions) == expected_steps, 'incomplete workload')
    slots = {name: [] for name in ('tb1', 'tb2', 'tb3')}
    epoch = rows[0]['snapshot']['epoch']
    for index, row in enumerate(rows):
        s = row['snapshot']; now = s['source_stamp']
        elapsed = s['task_elapsed_sec']
        require(s['epoch'] == epoch and number(elapsed)
                and round(elapsed * 10**9) == index * 10**9, 'epoch/cadence mismatch')
        for robot in s['robots']:
            name = robot['name']; history = slots[name]
            if not history:
                continue
            slot = history[-1]; nav = robot['navigation']; activity = robot['activity']
            if slot.get('complete'):
                continue
            active = nav.get('goal_id') == slot['goal_id'] and nav.get('owned') is True and nav.get('phase') == 'active'
            if active:
                accepted = nav.get('accepted_at')
                require(number(accepted) and slot['created'] <= accepted <= now, 'invalid acceptance')
                require(slot.get('accepted', accepted) == accepted, 'acceptance changed')
                slot['accepted'] = accepted
                path, stamp = activity.get('estimated_path_m'), activity.get('last_odom_source_stamp')
                if ('baseline' not in slot and robot.get('fresh') is True and robot.get('valid') is True
                        and activity.get('epoch') == epoch and activity.get('path_observation_complete') is True
                        and number(path) and path >= 0 and number(stamp) and accepted <= stamp <= now):
                    slot.update(baseline=path, baseline_source=stamp)
            if nav.get('last_goal_id') == slot['goal_id'] and nav.get('last_terminal') is not None:
                expected = 'SUCCEEDED' if slot['ordinal'] == 0 else 'CANCELED'
                require(nav['last_terminal'] == expected, name + ': unexpected terminal')
                require(slot['ordinal'] == 0 or ('wait' in slot and nav.get('stop_reason') == 'wait'), 'cancel without scientific WAIT')
                if nav.get('phase') == 'idle' and nav.get('owned') is False:
                    slot.setdefault('terminal_observed', now)
                    stamp = robot.get('odom_source_stamp'); speed = robot.get('v')
                    rest = slot.setdefault('rest', [])
                    if (robot.get('fresh') is True and robot.get('valid') is True and number(stamp)
                            and slot['terminal_observed'] <= stamp <= now and number(speed) and abs(speed) <= .01):
                        if not rest or stamp > rest[-1]:
                            rest.append(stamp)
                    else:
                        rest.clear()
                    if len(rest) >= 3 and now - slot['terminal_observed'] >= 3:
                        slot['complete'] = True
        if index == expected_steps:
            break
        command = rows[index + 1]['info'].get('command'); decision = decisions[index]
        require(type(command) is dict and command == decision['command'], 'actual command mismatch')
        require(command['epoch'] == epoch and command['observation_sequence'] == s['sequence']
                and command['observation_digest'] == s['digest'], 'command observation mismatch')
        action = command['action']; planned = decision['planned']
        require(planned['action'] == action and planned['clock'] == now, 'prospective action mismatch')
        require(s['joint_action_mask'][action] is True, 'illegal joint action')
        for i, name in enumerate(slots):
            choice = (action // 100, action // 10 % 10, action % 10)[i]
            require(s['per_robot_action_mask'][i][choice] is True, 'illegal robot action')
            history = slots[name]; robot = s['robots'][i]; nav = robot['navigation']
            if choice < 8:
                require(len(history) < 3 and (not history or history[-1].get('complete')), 'unclosed or extra goal')
                purpose = 'warmup' if not history else 'qualified' + str(len(history))
                require(planned['purposes'][name] == purpose, 'retrospective goal relabel')
                history.append(dict(ordinal=len(history), goal_id=epoch+':'+name+':'+str(command['command_id']), created=now))
            elif choice == 9:
                require(history, 'WAIT without goal')
                slot = history[-1]; activity = robot['activity']
                path, stamp = activity.get('estimated_path_m'), activity.get('last_odom_source_stamp')
                require(slot['ordinal'] > 0 and 'wait' not in slot and 'accepted' in slot and now-slot['accepted'] >= 5,
                        'WAIT purpose/commit mismatch')
                require(nav.get('goal_id') == slot['goal_id'] and nav.get('owned') is True and nav.get('phase') == 'active'
                        and robot.get('fresh') is True and robot.get('valid') is True and number(robot.get('v')) and robot['v'] >= .08,
                        'WAIT moving/ownership predicate failed')
                require('baseline' in slot and number(path) and path-slot['baseline'] >= .05 and activity.get('epoch') == epoch
                        and activity.get('path_observation_complete') is True and number(stamp) and slot['baseline_source'] <= stamp <= now,
                        'WAIT new-path predicate failed')
                slot['wait'] = dict(source_stamp=now, command_id=command['command_id'], v=robot['v'], new_path=path-slot['baseline'])
    require(all(len(h) == 3 and all(s.get('complete') for s in h) for h in slots.values()), 'six moving cancels not completed')
    return slots


def audit(directory, freeze):
    result = dict(schema='mr3-decisive-stimulus-replay-v1', freeze=freeze, passed=False, errors=[],
                  qualification=False, physical_credit=False, producer_imported_as_oracle=False, bindings={})
    try:
        paths = list(Path(directory).glob('worker*/episode*/transitions.jsonl'))
        require(len(paths) == 1, 'expected exactly one episode')
        paths.append(Path(directory)/'decisions.jsonl')
        raw = [p.read_bytes() for p in paths]
        result['bindings'] = {str(p): dict(sha256=hashlib.sha256(b).hexdigest(), bytes=len(b)) for p,b in zip(paths,raw)}
        result['robots'] = replay(*[[json.loads(line) for line in b.splitlines()] for b in raw])
        require(all(p.read_bytes() == b for p,b in zip(paths,raw)), 'inputs changed')
        result['passed'] = True
    except (OSError, ValueError, KeyError, TypeError, IndexError) as error:
        result['errors'].append(str(error))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--freeze', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.directory, args.freeze)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2)
    raise SystemExit(0 if result['passed'] else 1)
