"""Serialize the four declared V22 launch/audit CLIs; never override their gates."""

import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time


ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A = W / 'report/assets/20261018_mr3_p2a0_v25_smoother'
TEMP = Path('/tmp')
STAGES = ('interface', 'terminal', 'reset', 'deadline')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def identity(pid):
    try:
        raw = Path(f'/proc/{pid}/stat').read_text()
        fields = raw[raw.rfind(')') + 2:].split()
        return {'pid': pid, 'start_ticks': int(fields[19]), 'parent': int(fields[1]),
                'state': fields[0]}
    except (OSError, ValueError, IndexError):
        return None


def read_json(path):
    raw = path.read_bytes()
    return json.loads(raw), {'path': str(path), 'sha256': sha(raw)}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def actual_verdict(stage, freeze, plan_sha, specification):
    """Require real launch, summary, runner and every declared formal receipt."""
    prefix = TEMP / ('mr3_p2a0_v25_' + stage)
    launch, launch_proof = read_json(Path(str(prefix) + '_launch.json'))
    audit, audit_proof = read_json(Path(str(prefix) + '_audit_execution_v1.json'))
    summary_path = Path(specification['run_directory']) / 'benchmark_summary.json'
    summary, summary_proof = read_json(summary_path)
    require(launch.get('freeze') == audit.get('freeze') == summary.get('freeze') == freeze
            and launch.get('stage') == audit.get('stage') == stage
            and launch.get('plan_sha256') == audit.get('plan_sha256') == plan_sha,
            'stage receipts lost exact source/plan/stage identity')
    require(launch.get('status') == 'completed' and launch.get('passed') is True
            and type(launch.get('returncode')) is int and launch['returncode'] == 0
            and launch.get('within_wall_budget') is True
            and launch.get('benchmark_summary') == summary_proof
            and summary.get('passed') is True, 'actual native launch/summary gate failed')
    commands = audit.get('commands')
    require(audit.get('all_submitted_jobs_finished') is True
            and audit.get('runner_errors') == [] and isinstance(commands, list) and commands
            and any(item.get('required_success') is True for item in commands)
            and all(type(item.get('required_success')) is bool for item in commands),
            'actual audit runner jobs unfinished or invalid runner records')
    require(
        audit.get('passed') is True and all(
            item['required_success'] is False or item.get('passed') is True
            and type(item.get('returncode')) is int and item['returncode'] == 0
            for item in commands),
        'actual required audit gates failed after all submitted jobs finished')
    declared = specification['required_audit_receipts']
    records = audit.get('receipts')
    require(isinstance(records, list) and len(records) == len(declared)
            and {item.get('path') for item in records} == set(declared)
            and len(set(declared)) == len(declared), 'required audit receipt set changed')
    by_path = {item['path']: item for item in records}
    formal = []
    for path in declared:
        value, proof = read_json(Path(path))
        recorded = by_path[path]
        require(value.get('passed') is True and ('freeze' not in value or value['freeze'] == freeze)
                and recorded.get('passed') is True and recorded.get('sha256') == proof['sha256'],
                'mandatory formal receipt failed, missing or changed: ' + path)
        formal.append(proof)
    return {'passed': True, 'launch': launch_proof, 'audit_execution': audit_proof,
            'benchmark_summary': summary_proof, 'mandatory_receipts': formal,
            'native_wall_seconds': launch['wall_duration_sec']}


def main():
    require(len(sys.argv) == 2 and re.fullmatch('[0-9a-f]{40}', sys.argv[1]) is not None,
            'usage: run_matrix EXACT40')
    freeze = sys.argv[1]
    plan_path = A / 'predeclared_plan_v25.json'
    plan_raw = plan_path.read_bytes()
    plan_sha = sha(plan_raw)
    plan = json.loads(plan_raw)
    require(plan.get('schema') == 'mr3-p2a0-predeclaration-v25'
            and plan.get('readiness', {}).get('status') == 'ready'
            and plan['readiness'].get('pending_bindings') == []
            and not plan.get('new_source_bindings_pending')
            and tuple(item['stage'] for item in plan['stages']) == STAGES,
            'final four-stage V25 plan is not ready')
    preflight, preflight_proof = read_json(TEMP / 'mr3_p2a0_v25_source_preflight.json')
    require(preflight.get('passed') is True and preflight.get('freeze') == freeze
            and preflight.get('plan_sha256') == plan_sha, 'exact final source preflight missing')
    script = Path(__file__).resolve()
    sources = {script: sha(script.read_bytes())}
    bindings = {item['path']: item['sha256'] for item in plan['independent_source_bindings']}
    for operation in ('launch', 'audit'):
        coordinator = A / 'independent' / ('mr3_p2a0_v25_' + operation + '_stage.py')
        relative = str(coordinator.relative_to(ROOT))
        sources[ROOT / relative] = sha((ROOT / relative).read_bytes())
        require(bindings.get(relative) == sources[ROOT / relative],
                'unbound actual coordinator: ' + relative)
    worker_helper = A / 'independent/mr3_v25_stage_worker_bindings_v1.py'
    worker_relative = str(worker_helper.relative_to(ROOT))
    sources[worker_helper] = sha(worker_helper.read_bytes())
    require(bindings.get(worker_relative) == sources[worker_helper],
            'unbound stage worker-binding helper: ' + worker_relative)
    from mr3_v25_stage_worker_bindings_v1 import validate_worker_bindings
    for specification in plan['stages']:
        validate_worker_bindings(specification)
    env = dict(os.environ, PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1')
    env.pop('PYTHONPATH', None)

    def unchanged():
        require(plan_path.read_bytes() == plan_raw, 'declared plan changed during matrix')
        require(all(sha(path.read_bytes()) == digest for path, digest in sources.items()),
                'actual controller/coordinator source changed during matrix')
        require(subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
                == freeze, 'source HEAD differs from freeze')
        require(not subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True),
                'source worktree changed during matrix')
    unchanged()
    # Reject an attempted matrix before spawning any child, including partial attempts.
    for specification in plan['stages']:
        prefix = TEMP / ('mr3_p2a0_v25_' + specification['stage'])
        paths = [Path(specification['run_directory']), Path(str(prefix) + '_launch.json'),
                 Path(str(prefix) + '_audit_execution_v1.json'),
                 *map(Path, specification['required_audit_receipts'])]
        require(all(not path.exists() for path in paths),
                'stage output already exists; never retry')
    # Keep the existing passive watcher's ledger path; STAGES still covers all four.
    ledger_path = TEMP / 'mr3_p2a0_v25_remaining_matrix_v1.jsonl'
    with ledger_path.open('x') as ledger:
        def record(**value):
            row = dict(schema='mr3-declared-matrix-orchestration-v2', freeze=freeze,
                       plan_sha256=plan_sha, wall_monotonic_ns=time.monotonic_ns(),
                       utc=datetime.datetime.now(datetime.timezone.utc).isoformat(), **value)
            ledger.write(json.dumps(row) + '\n')
            ledger.flush()
            print(json.dumps(row), flush=True)

        record(event='started', controller_identity=identity(os.getpid()), parent=os.getppid(),
               argv=[sys.executable, *sys.argv], source_sha256=sources[script],
               sources={str(path): digest for path, digest in sources.items()},
               source_preflight=preflight_proof,
               scope='Bound finite CLI children only; no signals, retries, '
                     'parameter changes or gate overrides')

        def invoke(stage, operation):
            coordinator_name = 'mr3_p2a0_v25_' + operation + '_stage.py'
            command = [sys.executable, str(A / 'independent' / coordinator_name), stage, freeze]
            console = TEMP / ('mr3_p2a0_v25_' + stage + '_controller_' + operation + '.log')
            record(event='command_started', stage=stage, operation=operation,
                   argv=command, cwd=str(W), console=str(console))
            started = time.monotonic()
            child, child_identity, code, errors = None, None, None, []
            try:
                with console.open('x') as output:
                    try:
                        child = subprocess.Popen(command, cwd=W, env=env,
                                                 stdout=output, stderr=subprocess.STDOUT)
                        child_identity = identity(child.pid)
                        record(event='child_spawned', stage=stage, operation=operation,
                               child_identity=child_identity)
                        code = child.wait()
                    except BaseException as failure:
                        errors.append(repr(failure))
                    finally:
                        # Preserve the original exception; reap only this exact finite child.
                        # A second exception while waiting cannot orphan it or restore PASS.
                        if child is not None:
                            while code is None:
                                try:
                                    code = child.wait()
                                except BaseException as failure:
                                    errors.append(repr(failure))
            except BaseException as failure:
                errors.append(repr(failure))
            after = None if child is None else identity(child.pid)
            record(event='command_completed', stage=stage, operation=operation,
                   returncode=code, errors=errors, wall_seconds=time.monotonic() - started,
                   child_identity=child_identity, child_identity_after=after,
                   console_sha256=sha(console.read_bytes()) if console.exists() else None)
            return code == 0 and not errors

        for specification in plan['stages']:
            stage = specification['stage']
            native_ok, audit_ok, verdict, error = False, False, None, None
            try:
                unchanged()
                native_ok = invoke(stage, 'launch')
                unchanged()
                # A failed real attempt is still formally diagnosed once, never retried.
                audit_ok = invoke(stage, 'audit')
                unchanged()
                verdict = actual_verdict(stage, freeze, plan_sha, specification)
            except BaseException as failure:
                error = repr(failure)
            if not (native_ok and audit_ok and verdict is not None and verdict['passed'] is True
                    and error is None):
                record(event='version_failed_later_stages_skip', stage=stage,
                       native_ok=native_ok, audit_ok=audit_ok, verdict=verdict, error=error,
                       later_stages=[value for value in STAGES[STAGES.index(stage) + 1:]])
                return 1
            record(event='stage_passed', stage=stage, verdict=verdict)
        record(event='matrix_complete', passed=True,
               scope='All four actual launch and mandatory audit receipts passed; '
                     'not P2A acceptance')
        return 0


if __name__ == '__main__':
    raise SystemExit(main())
