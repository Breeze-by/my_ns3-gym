#!/usr/bin/python3
"""Validate MR3-P1A documents without importing ROS or launching experiments.

Receipts are created exclusively. Reuse this checker with a new --output after
the final matrix; earlier receipts remain snapshots of their checked inputs.
"""

import argparse
import ast
import datetime
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess


ROOT = Path('/home/zhuyulab/ns3-workspace')
B = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
ROS = ROOT / 'ros2_ws/ros2-multi-robot-automap'
ASSETS = B / 'report/assets/20261014_mr3_p1a'
PRE = '81b2f8b9c2a36f0a8c5278e04fae66dc06859180'
BACKUP = '8fe1495b6624cd9136f3ce160acaa274428e54ae'
INPUT_HASHES = {}


def read(path):
    payload = path.read_bytes()
    INPUT_HASHES[str(path.relative_to(ROOT))] = hashlib.sha256(payload).hexdigest()
    return payload


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def load(path):
    return json.loads(read(path))


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def launch_arguments(path):
    tree = ast.parse(read(path))
    declared = {}

    def record(node, bindings):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            return
        if node.func.id != 'DeclareLaunchArgument' or not node.args:
            return
        first = node.args[0]
        name = first.value if isinstance(first, ast.Constant) else bindings.get(
            first.id if isinstance(first, ast.Name) else None)
        if name is not None:
            default = next((kw.value for kw in node.keywords if kw.arg == 'default_value'), None)
            declared[name] = ast.literal_eval(default) if default is not None else None

    for node in ast.walk(tree):
        record(node, {})
        if isinstance(node, ast.For) and isinstance(node.target, ast.Tuple):
            try:
                values = ast.literal_eval(node.iter)
            except (ValueError, TypeError):
                continue
            names = [entry.id for entry in node.target.elts if isinstance(entry, ast.Name)]
            for row in values:
                for nested in ast.walk(node):
                    record(nested, dict(zip(names, row)))
    return declared


def cli_arguments(path):
    tree = ast.parse(read(path))
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Attribute) and node.func.attr == 'add_argument']
    flags = {argument.value for node in calls for argument in node.args
             if isinstance(argument, ast.Constant) and isinstance(argument.value, str)
             and argument.value.startswith('--')}
    robot = next(node for node in calls if any(
        isinstance(argument, ast.Constant) and argument.value == '--robot-count'
        for argument in node.args))
    default = next(ast.literal_eval(kw.value) for kw in robot.keywords if kw.arg == 'default')
    require(default == 3, f'{path}: robot-count default is not three')
    return flags


def dictionaries(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from dictionaries(child)
    elif isinstance(value, list):
        for child in value:
            yield from dictionaries(child)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ASSETS / 'pre_matrix3_document_checks.json')
    parser.add_argument('--p1a-state', choices=('in_progress', 'awaiting_acceptance'),
                        default='in_progress')
    args = parser.parse_args()
    require(not args.output.exists(), f'Refusing to overwrite receipt: {args.output}')
    active = [ROOT / 'README.md', ROOT / 'AGENTS.md', ROOT / 'ns-allinone-3.40/AGENTS.md']
    active += [B / name for name in ('AGENTS.md', 'RESEARCH_PLAN.md', 'IMPLEMENTATION_PLAN.md',
                                    'MR3_TASK_CONTRACT.md', 'USER_GUIDE.md', 'report/README.md')]
    active += [ROS / name for name in ('AGENTS.md', 'README.md', 'user_guide.md',
                                      'Technical_Manual.md', 'launch_commands.md')]
    # Current dated MR3 reports are checked for links, not rewritten or treated as instructions.
    documents = active + sorted((B / 'report').glob('20261014*.md'))
    links = blocks = robot_commands = 0
    launch = launch_arguments(ROS / 'src/multi_robot/launch/gazebo_multirobot_mapping_with_nav2.launch.py')
    require(launch.get('robot_count') == '3', 'Active launch default is not three')
    cli = {name: cli_arguments(ROS / 'scripts' / name)
           for name in ('ros_smoke_test.py', 'run_ideal_baseline.py')}
    for path in dict.fromkeys(documents):
        text = read(path).decode()
        require(len(re.findall(r'^```(?:[A-Za-z0-9_+-]+)?[ \t]*$', text, re.M)) % 2 == 0,
                f'Unbalanced code fences: {path}')
        for target in re.findall(r'(?<!!)\[[^\]\n]+\]\(([^)\n]+)\)', text):
            if '://' in target or target.startswith('#'):
                continue
            local = target.split('#', 1)[0].strip('<>')
            if local:
                resolved = Path(local) if local.startswith('/') else path.parent / local
                require(resolved.exists(), f'Broken local link: {path}: {target}')
                links += 1
        if path not in active:
            continue
        require(not re.search(r'P0.{0,12}(?:文档待用户验收|documentation awaits)', text, re.I),
                f'Stale P0 pending status: {path}')
        for block in re.findall(r'```bash\n(.*?)```', text, re.S):
            checked = subprocess.run(['bash', '-n'], input=block, text=True, capture_output=True)
            require(checked.returncode == 0, f'Invalid shell syntax: {path}: {checked.stderr}')
            blocks += 1
            for line in block.replace('\\\n', ' ').splitlines():
                tokens = shlex.split(line, comments=True)
                if 'gazebo_multirobot_mapping_with_nav2.launch.py' in tokens:
                    used = {word.split(':=', 1)[0] for word in tokens if ':=' in word}
                    require(used <= launch.keys(), f'Unknown launch args: {path}: {used - launch.keys()}')
                    require('robot_count:=3' in tokens, f'Launch omits explicit three: {path}')
                    robot_commands += 1
                for name, flags in cli.items():
                    if not any(Path(word).name == name for word in tokens):
                        continue
                    used = {word.split('=', 1)[0] for word in tokens if word.startswith('--')}
                    require(used <= flags, f'Unknown CLI flags: {path}: {name}: {used - flags}')
                    require('--robot-count' in tokens and tokens[tokens.index('--robot-count') + 1] == '3',
                            f'CLI omits explicit three: {path}: {name}')
                    robot_commands += 1
    require(robot_commands > 0, 'No current three-robot commands checked')
    plan = read(B / 'IMPLEMENTATION_PLAN.md').decode()
    statuses = {cells[1].strip(): cells[3].strip() for line in plan.splitlines()
                if line.startswith('| MR3-P') for cells in [line.split('|')]}
    expected = ('MR3-P0', 'MR3-P1A', 'MR3-P1B', 'MR3-P1C', 'MR3-P2A', 'MR3-P2B',
                'MR3-P2C', 'MR3-P3A', 'MR3-P3B', 'MR3-P4A', 'MR3-P4B', 'MR3-P5')
    require(set(statuses) == set(expected), 'Checkpoint table is incomplete')
    require('已验收' in statuses['MR3-P0'], 'P0 acceptance is missing')
    state = '实施与验证中' if args.p1a_state == 'in_progress' else '待用户验收'
    require(state in statuses['MR3-P1A'], f'P1A status differs from requested {args.p1a_state}')
    require(all(statuses[stage] == '未开始' for stage in expected[2:]), 'A later stage is started')

    archive = load(B / 'report/ARCHIVE_INDEX.json')
    require(archive['pre_route_commit'] == PRE and archive['original_route_backup']['commit'] == BACKUP,
            'Archival freeze identifiers changed')
    for ref in ('p2c1/global-mission-20261012', 'origin/p2c1/global-mission-20261012'):
        require(git('rev-parse', ref).decode().strip() == BACKUP, f'Backup changed: {ref}')
    bodies = 0
    for item in archive['files']:
        original = git('show', PRE + ':' + item['path'])
        require(hashlib.sha256(original).hexdigest() == item['sha256'], f'Original hash: {item["path"]}')
        current = read(ROOT / item['path'])
        if '/report/' in item['path']:
            require(current.split(b'\n\n', 1)[1] == original, f'Historical report modified: {item["path"]}')
            bodies += 1
        if item['path'].endswith('/log.md'):
            marker = b'## Logging rule\n'
            require(current[current.index(marker):].startswith(original[original.index(marker):]),
                    'Historical log entries were rewritten')

    config = ROS / 'src/multi_robot/config/mr3_p1a'
    protocol = load(config / 'protocol.json')
    require(protocol['robot_names'] == ['tb1', 'tb2', 'tb3'], 'Protocol robot names differ')
    held = protocol['held_out']
    require(held['policy_runs'] == 0 and held['simulator_runs'] == 0, 'Held-out runs are declared')
    require(hashlib.sha256(read(ROS / 'scripts/generate_mr3_worlds.py')).hexdigest() == held['generator_sha256'],
            'Layout generator hash changed')
    layouts = protocol['development'] + held['layouts']
    for item in layouts:
        path = config / item['task_contract']
        require(hashlib.sha256(read(path)).hexdigest() == item['task_contract_sha256'], f'Contract hash: {path}')
        contract = load(path)
        require(contract['robots'] == ['tb1', 'tb2', 'tb3'] and contract['coverage_threshold'] == .95
                and contract['max_duration_sec'] == 300, f'Task gates changed: {path}')
        world = ROS / 'src/multi_robot/worlds' / item['world_file']
        require(contract['world_file'] == world.name and hashlib.sha256(read(world)).hexdigest() == contract['world_sha256'],
                f'World/hash mismatch: {world}')
        if 'world_sha256' in item:
            require(item['world_sha256'] == contract['world_sha256'], f'Layout hash: {world}')

    development = {item['world_file'] for item in protocol['development']}
    held_worlds = {item['world_file'] for item in held['layouts']}
    native_paths = []
    observed_worlds = set()
    for directory in (ASSETS, ROS / 'log/mr3_p1a'):
        for path in sorted(directory.rglob('*.json')):
            value = json.loads(path.read_bytes())
            for entry in dictionaries(value):
                if {'world_file', 'termination_reason', 'elapsed_sim_time_sec', 'robots'} <= entry.keys():
                    world = Path(entry['world_file']).name
                    require(world in development and world not in held_worlds, f'Held-out native run: {path}')
                    native_paths.append(str(path.relative_to(ROOT)))
                    observed_worlds.add(world)
                command = entry.get('command')
                tokens = shlex.split(command) if isinstance(command, str) else command
                if not isinstance(tokens, list) or not any(
                    str(token).endswith(('run_ideal_baseline.py', 'ros_smoke_test.py',
                                         'gazebo_multirobot_mapping_with_nav2.launch.py')) for token in tokens):
                    continue
                worlds = [str(token).split(':=', 1)[1] for token in tokens if str(token).startswith('world:=')]
                if '--world' in tokens:
                    worlds.append(tokens[tokens.index('--world') + 1])
                require(not any(Path(world).name in held_worlds for world in worlds), f'Held-out command: {path}')

    latest_plan = load(ASSETS / 'predeclared_native_plan.json')['development_matrix_retries'][-1]
    require(latest_plan['version'] == 3, 'Latest matrix is not version 3')
    batches = latest_plan['batches']
    require([row['world'] for row in batches] == ['p1c_rooms.world', 'p1c_corridors.world', 'p1c_open.world'],
            'Version3 world order differs')
    require([row['ros_domain_id'] for row in batches] == [224, 225, 226]
            and [row['gazebo_port'] for row in batches] == [11831, 11832, 11833], 'Version3 isolation differs')
    require(all(row['seeds'] == [101, 202, 303] for row in batches), 'Version3 seeds differ')
    result = {
        'type': 'P1A_static_documents_not_a_simulator_or_training_experiment',
        'checked_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'git_head': git('rev-parse', 'HEAD').decode().strip(), 'p1a_state': args.p1a_state,
        'checker_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'checks': {'active_documents': len(active), 'local_links': links, 'bash_syntax_blocks': blocks,
                   'explicit_three_robot_commands': robot_commands, 'source_default_and_flags': True,
                   'checkpoints': statuses, 'archive_original_hashes': len(archive['files']),
                   'unchanged_original_report_bodies': bodies, 'historical_log_prefix_unchanged': True,
                   'backup_local_and_remote_unchanged': True, 'world_contract_hashes': len(layouts),
                   'heldout_policy_and_simulator_runs_declared_zero': True,
                   'native_episode_artifact_records_checked': len(native_paths),
                   'recorded_native_worlds': sorted(observed_worlds), 'version3_predeclaration': True},
        'heldout_absence_scope': 'Canonical retained P1A native JSONs and recorded launch/runner commands; '
                                 'static metadata cannot prove absence of unrecorded runs elsewhere.',
        'input_sha256': INPUT_HASHES, 'result': 'PASS', 'simulator_runs': 0, 'training_runs': 0,
    }
    with args.output.open('x') as output:
        json.dump(result, output, ensure_ascii=False, indent=2)
        output.write('\n')
    print(json.dumps({'result': 'PASS', 'receipt': str(args.output), 'checks': result['checks']},
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
