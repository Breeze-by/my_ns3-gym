"""Finite external legal-action diagnostic, never an exploration policy.

One prospectively labelled natural warmup, then two moving cancellations per
robot. All actions use the original per-robot AND joint masks. No controller,
physics, authority, reward, map or safety state is written by this module.
"""
import argparse
import copy
import json
import math
from pathlib import Path
import sys
import time

VERSION = 'mr3-decisive-async-cancel-diagnostic-v1'
STEPS = 96
ROBOTS = ('tb1', 'tb2', 'tb3')


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def require(value, reason):
    if not value:
        raise ValueError(reason)


class Probe:
    def __init__(self):
        self.epoch = None
        self.slots = {name: [] for name in ROBOTS}
        self.failures = []
        self.pending = None

    def fail(self, name, reason):
        item = dict(robot=name, reason=reason)
        if item not in self.failures:
            self.failures.append(item)

    def observe(self, snapshot):
        if self.epoch is None:
            self.epoch = snapshot['epoch']
        require(snapshot['epoch'] == self.epoch, 'cross epoch')
        now = snapshot['source_stamp']
        for robot in snapshot['robots']:
            name, nav = robot['name'], robot['navigation']
            if not self.slots[name]:
                continue
            slot = self.slots[name][-1]
            if slot.get('complete'):
                continue
            same = nav.get('goal_id') == slot['goal_id']
            accepted = nav.get('accepted_at')
            if same and nav.get('owned') is True and nav.get('phase') in ('active', 'canceling') and number(accepted):
                require(slot['created'] <= accepted <= now, 'invalid accepted timestamp')
                require('accepted' not in slot or slot['accepted'] == accepted, 'acceptance changed')
                slot.setdefault('accepted', accepted)
            activity = robot['activity']
            path, source = activity.get('estimated_path_m'), activity.get('last_odom_source_stamp')
            if ('baseline' not in slot and 'accepted' in slot and same
                    and nav.get('owned') is True and nav.get('phase') == 'active'
                    and robot.get('fresh') is True and robot.get('valid') is True
                    and activity.get('epoch') == self.epoch
                    and activity.get('path_observation_complete') is True
                    and number(path) and path >= 0 and number(source)
                    and slot['accepted'] <= source <= now):
                slot.update(baseline=path, baseline_source=source,
                            baseline_snapshot=snapshot['sequence'])
            if nav.get('last_goal_id') == slot['goal_id'] and nav.get('last_terminal') is not None:
                terminal = nav['last_terminal']
                desired = 'SUCCEEDED' if slot['purpose'] == 'warmup' else 'CANCELED'
                if terminal != desired or (slot['purpose'] != 'warmup' and (
                        'wait_command_id' not in slot or nav.get('stop_reason') != 'wait')):
                    self.fail(name, slot['purpose'] + ':unexpected_terminal:' + str(terminal))
                elif nav.get('phase') == 'idle' and nav.get('owned') is False:
                    slot.setdefault('terminal_observed', now)
                    slot['terminal'] = terminal
            if 'terminal_observed' in slot:
                stamp, speed = robot.get('odom_source_stamp'), robot.get('v')
                rest = slot.setdefault('rest_sources', [])
                good = (robot.get('fresh') is True and robot.get('valid') is True
                        and number(stamp) and slot['terminal_observed'] <= stamp <= now
                        and number(speed) and abs(speed) <= .01
                        and nav.get('phase') == 'idle' and nav.get('owned') is False
                        and nav.get('last_goal_id') == slot['goal_id'])
                if not good:
                    rest.clear()
                elif not rest or stamp > rest[-1]:
                    rest.append(stamp)
                    del rest[:-3]
                if len(rest) == 3 and now - slot['terminal_observed'] >= 3:
                    slot['complete'] = True
            if not slot.get('complete') and now - slot['created'] >= (32 if slot['purpose'] == 'warmup' else 28):
                self.fail(name, slot['purpose'] + ':bounded_opportunity_exhausted')

    def moving(self, snapshot, index, slot):
        robot = snapshot['robots'][index]
        nav, activity = robot['navigation'], robot['activity']
        now, path, source = snapshot['source_stamp'], activity.get('estimated_path_m'), activity.get('last_odom_source_stamp')
        return (slot['purpose'] != 'warmup' and 'wait_command_id' not in slot
            and 'accepted' in slot and now - slot['accepted'] >= 5
            and nav.get('goal_id') == slot['goal_id'] and nav.get('phase') == 'active'
            and nav.get('owned') is True and robot.get('fresh') is True and robot.get('valid') is True
            and number(robot.get('v')) and robot['v'] >= .08
            and 'baseline' in slot and number(path) and path - slot['baseline'] >= .05
            and activity.get('epoch') == self.epoch and activity.get('path_observation_complete') is True
            and number(source) and slot['baseline_source'] <= source <= now
            and snapshot['per_robot_action_mask'][index][9] is True)

    def choose(self, snapshot):
        require(self.pending is None, 'unresolved submission')
        self.observe(snapshot)
        require([r['name'] for r in snapshot['robots']] == list(ROBOTS), 'robot order')
        desired, purposes = [], {}
        failed = {row['robot'] for row in self.failures}
        for i, robot in enumerate(snapshot['robots']):
            name, nav = robot['name'], robot['navigation']
            slots = self.slots[name]
            choices = [8]
            if name not in failed:
                if slots and not slots[-1].get('complete'):
                    if self.moving(snapshot, i, slots[-1]):
                        choices = [9, 8]
                elif len(slots) < 3 and snapshot['task_elapsed_sec'] < 90:
                    if nav.get('phase') == 'idle' and nav.get('owned') is False and robot.get('fresh') is True and robot.get('valid') is True:
                        choices += [k for k in range(8) if snapshot['per_robot_action_mask'][i][k] is True]
                        purposes[name] = 'warmup' if not slots else 'qualified' + str(len(slots))
            desired.append(choices)
        legal = []
        for action, allowed in enumerate(snapshot['joint_action_mask']):
            choices = (action // 100, action // 10 % 10, action % 10)
            if allowed is True and all(c in desired[i] and snapshot['per_robot_action_mask'][i][c] is True for i, c in enumerate(choices)):
                legal.append(action)
        require(legal, 'no original legal joint action for finite diagnostic')

        def rank(action):
            choices = (action // 100, action // 10 % 10, action % 10)
            margins, paths = [], []
            for i, c in enumerate(choices):
                if c >= 8:
                    continue
                own, goal = snapshot['robots'][i], snapshot['candidates'][c]
                path = goal['path_distances_m'][i]
                require(number(path) and path >= 0, 'legal candidate path missing')
                paths.append(path)
                dx, dy = goal['x'] - own['x'], goal['y'] - own['y']
                for j, peer in enumerate(snapshot['robots']):
                    if j != i:
                        px, py = own['x'] - peer['x'], own['y'] - peer['y']
                        norm = math.hypot(dx, dy) * math.hypot(px, py)
                        # Undefined direction is ranked last, never removed or
                        # interpreted as a safety certificate.
                        margins.append((dx * px + dy * py) / norm if norm else -2.)
            return (-sum(c == 9 for c in choices), -len(paths),
                    -min(margins, default=-2.), -min(paths, default=0.), -sum(paths), action)

        action = min(legal, key=rank)
        self.pending = dict(epoch=self.epoch, observation_sequence=snapshot['sequence'],
            observation_digest=snapshot['digest'], action=action, clock=snapshot['source_stamp'],
            purposes=purposes)
        return action

    def submitted(self, info):
        request = self.pending
        require(request is not None, 'no planned submission')
        if info.get('action_submitted', True) is False:
            self.pending = None
            return
        command = info.get('command')
        require(type(command) is dict and type(command.get('command_id')) is int and command['command_id'] > 0,
                'missing actual returned command')
        require(all(command.get(k) == request[k] for k in ('epoch', 'observation_sequence', 'observation_digest', 'action')),
                'returned command differs from planned action')
        for name, choice in zip(ROBOTS, (request['action'] // 100, request['action'] // 10 % 10, request['action'] % 10)):
            if choice < 8:
                self.slots[name].append(dict(purpose=request['purposes'][name],
                    goal_id=self.epoch + ':' + name + ':' + str(command['command_id']),
                    goal_command_id=command['command_id'], created=request['clock']))
            elif choice == 9:
                self.slots[name][-1].update(wait_command_id=command['command_id'], wait_requested=request['clock'])
        self.pending = None

    def result(self):
        return dict(version=VERSION, slots=copy.deepcopy(self.slots), failures=list(self.failures),
            received_coverage_passed=not self.failures and all(len(s) == 3 and all(r.get('complete') for r in s) for s in self.slots.values()),
            scope='received lifecycle only; independent native/physics audits required', qualification=False)


def collect(plan_path):
    from .env import MR3Env
    from .supervisor import Supervisor
    plan = json.loads(Path(plan_path).read_bytes())
    run = Path(plan['run_directory'])
    require(not run.exists(), 'exclusive diagnostic output required')
    started = time.monotonic_ns()
    supervisor = Supervisor(run_id=run.name, worker_id=0, domain_id=210, gazebo_port=15901,
        output_root=run.parent, safety_contract='mr3-reach-v1', seed_rule='exact-point-bridge-v2',
        start_graph_rule='point-attachment-3x3-v1', reach_geometry_rule='cone-support-v2')
    env = MR3Env(supervisor=supervisor, max_steps=STEPS)
    probe = Probe()
    summary = dict(version=VERSION, passed=False, transitions=0, error=None, cleanup_error=None,
                   optimizer_steps=0, policy_calls=0, qualification=False, timing=[])
    run.mkdir(parents=True, exist_ok=True)
    (run/'diagnostic_metadata.json').write_text(json.dumps(dict(plan=str(plan_path), version=VERSION,
        steps=STEPS, scene='open', seed=101, command=sys.argv, started_monotonic_ns=started), indent=2)+'\n')
    try:
        _, info = env.reset(seed=101)
        summary['startup_wall_sec'] = info['startup_wall_sec']
        summary['episode_directory'] = str(supervisor.episode.directory)
        with (run/'decisions.jsonl').open('x') as stream:
            for step in range(STEPS):
                require((time.monotonic_ns()-started)/1e9 + 90 + 180 < plan['native_wall_seconds'], 'native work reservation exhausted')
                snapshot = supervisor.last_result['snapshot']
                action = probe.choose(snapshot)
                row = dict(step=step, planned=copy.deepcopy(probe.pending), before=probe.result())
                t = time.monotonic_ns()
                _, _, terminal, truncated, info = env.step(action)
                summary['timing'].append(dict(step=step, wall_seconds=(time.monotonic_ns()-t)/1e9,
                                              dt=info['dt'], physical_dt=info['physical_dt']))
                summary['transitions'] += 1
                probe.submitted(info)
                row.update(command=info.get('command'), action_submitted=info.get('action_submitted', True))
                stream.write(json.dumps(row, allow_nan=False)+'\n'); stream.flush()
                if terminal or truncated:
                    summary.update(terminated=terminal, truncated=truncated, reason=info.get('reason'))
                    break
            probe.observe(supervisor.last_result['snapshot'])
            summary.update(probe.result())
            summary['passed'] = summary['transitions'] == STEPS and summary['received_coverage_passed']
    except Exception as error:
        summary['error'] = repr(error)
        summary.update(probe.result())
    finally:
        t = time.monotonic_ns()
        try:
            env.close()
        except Exception as error:
            summary['cleanup_error'] = repr(error)
        summary.update(close_call_wall_seconds=(time.monotonic_ns()-t)/1e9,
            shutdown_receipts=supervisor.receipts, ended_monotonic_ns=time.monotonic_ns())
        summary['wall_seconds'] = (summary['ended_monotonic_ns']-started)/1e9
        summary['passed'] = summary['passed'] and not summary['error'] and not summary['cleanup_error']
        (run/'benchmark_summary.json').write_text(json.dumps(summary, indent=2, allow_nan=False)+'\n')
    print(json.dumps({k:summary.get(k) for k in ('passed','transitions','error','cleanup_error','wall_seconds','failures')},ensure_ascii=False), flush=True)
    return 0 if summary['passed'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    raise SystemExit(collect(parser.parse_args().plan))
