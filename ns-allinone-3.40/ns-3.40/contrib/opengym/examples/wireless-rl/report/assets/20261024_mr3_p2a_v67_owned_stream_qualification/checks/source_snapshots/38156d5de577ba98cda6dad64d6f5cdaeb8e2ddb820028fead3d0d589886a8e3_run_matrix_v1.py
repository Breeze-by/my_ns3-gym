"""One frozen V67 qualification matrix; no automatic policy entry.

The complete fee runs from the verified same-PID bootstrap through post-source
and final absence attempts, including gaps. Phase waits are evidence, not added
to that interval. Native work keeps its original finite cooperative guards and
owned cleanup; the complete 47220-second fee gate is not hard real time.
"""
import argparse
from decimal import Decimal
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import time

ROOT = Path('/home/zhuyulab/ns3-workspace')
WIRELESS = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
ASSETS = WIRELESS / 'report/assets/20261024_mr3_p2a_v67_owned_stream_qualification'
PREFIX = Path('/tmp/mr3_p2a_reach_v67')
STATE = Path(str(PREFIX) + '_driver_v1')
PLAN = ASSETS / 'plan_v1.json'
SCOPE = ASSETS / 'scope_v1.json'
RESOURCE = ASSETS / 'resource_v1.json'
MODULE = 'report.assets.20261024_mr3_p2a_v67_owned_stream_qualification.'
EXTERNAL_ABSENCE = ASSETS.parent / '20261023_mr3_p2a_v50_qualification/external_absence_v1.py'
PREVIOUS = ASSETS.parent / '20261024_mr3_p2a_v66_owned_stream_qualification/closure_ledger_v1.json'
PREVIOUS_SHA = '6e2832b06b6f8330b7eecb3c7027e29c8580b40c52b20f92f449adcb6a9ebe75'
ENTRY = Decimal('109144.8478173156018')
CAP = Decimal('47220')
ACTUATION_PROFILE = 'initial-zero-encoder-hold-v1'
AUTHORITY_PROFILE = 'mr3-owned-stream-authority-v1'
STABLE = ('st_dev', 'st_ino', 'st_mode', 'st_size', 'st_mtime_ns', 'st_ctime_ns')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def decode(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'duplicate JSON key')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def read(path):
    return decode(Path(path).read_bytes())


def write(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n'); stream.flush(); os.fsync(stream.fileno())


def identity(pid):
    tail = Path('/proc', str(pid), 'stat').read_text().rsplit(')', 1)[1].split()
    return dict(pid=pid, start_ticks=int(tail[19]), parent=int(tail[1]),
                group=int(tail[2]), session=int(tail[3]), state=tail[0])


def same(a, b):
    return (type(a) is dict and type(b) is dict
            and all(type(a.get(k)) is int and a[k] > 0 and a[k] == b.get(k)
                    for k in ('pid', 'start_ticks')))


def environment():
    env = dict(os.environ, PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1', CUDA_VISIBLE_DEVICES='0')
    env.pop('PYTHONPATH', None); env.pop('PYTHONHOME', None)
    return env


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, timeout=20)


def clean_freeze(freeze):
    require(type(freeze) is str and re.fullmatch('[0-9a-f]{40}', freeze), 'exact 40-hex freeze required')
    require(git('rev-parse', 'HEAD').decode().strip() == freeze
            == git('rev-parse', 'origin/main').decode().strip()
            and not git('status', '--porcelain', '--untracked-files=all'),
            'source must be clean HEAD == origin/main == execution freeze')


def proof(path):
    """Regular bytes; installed ELF links bind literal and resolved identity."""
    path = Path(path)
    literal = path.lstat(); resolved = path.resolve(strict=True)
    before = resolved.stat()
    require(stat.S_ISREG(before.st_mode), 'not a regular bound source/library')
    with resolved.open('rb') as stream:
        require(all(getattr(os.fstat(stream.fileno()), k) == getattr(before, k) for k in STABLE),
                'opened object changed')
        digest = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
        require(all(getattr(os.fstat(stream.fileno()), k) == getattr(before, k) for k in STABLE),
                'bound object changed while hashing')
    require(all(getattr(resolved.stat(), k) == getattr(before, k) for k in STABLE)
            and all(getattr(path.lstat(), k) == getattr(literal, k) for k in STABLE)
            and path.resolve(strict=True) == resolved, 'bound path changed while hashing')
    return dict(path=str(path), bytes=before.st_size, sha256=digest.hexdigest(),
                resolved_path=str(resolved), stat={k:getattr(before, k) for k in STABLE},
                literal_lstat={k:getattr(literal, k) for k in STABLE},
                literal_target=os.readlink(path) if stat.S_ISLNK(literal.st_mode) else None)


def previous_entry():
    raw = PREVIOUS.read_bytes()
    require(len(raw) == 5261 and hashlib.sha256(raw).hexdigest() == PREVIOUS_SHA,
            'fixed actual V66 closed failure ledger bytes differ')
    value = decode(raw)
    require(value.get('passed') is True and value.get('activity_passed') is False
            and value.get('matrix_submitted') is False and value.get('World_started') is False
            and value.get('preflight_submitted') is False and value.get('actual_phase_wait_count') == 0
            and value.get('original_source_scope_status') == 'UNKNOWN_INITIAL_SOURCE_CHECK_ABORTED'
            and value.get('actual_before_after_equal') is None
            and value.get('actual_returned_source_before_count') == 0
            and value.get('actual_returned_source_after_count') == 0
            and value.get('current_source_Git_full_scope_pass_claimed') is False
            and Decimal(value['engineering_cumulative_seconds']) == ENTRY
            and Decimal(value['engineering_ceiling_seconds']) == 180000
            and Decimal(value['engineering_remaining_seconds']) + ENTRY == 180000
            and Decimal(value['engineering_added_parent_union_seconds']) == Decimal('13.521178149')
            and value.get('actual_root_tool_session_id') == 16973
            and value.get('actual_root_tool_returncode') == 1,
            'fixed actual V66 closed account differs')
    return ENTRY


def load_dependencies():
    return (importlib.import_module('mr3_learning.reach_preparation'),
            importlib.import_module(MODULE + 'prepare_plan_v1'))


def canonical_location():
    return Path(__file__).resolve() == ASSETS/'run_matrix_v1.py' and Path.cwd() == WIRELESS


def source_check(plan, freeze):
    clean_freeze(freeze)
    sources = {ROOT / path: sha for path, sha in plan['source_bindings'].items()}
    for path in (*ASSETS.glob('*.py'), PLAN, SCOPE, RESOURCE, PREVIOUS):
        sources.setdefault(path, None)
    libraries = {Path(p) if Path(p).is_absolute() else ROOT / p:sha
                 for p, sha in plan['library_bindings'].items()}
    require(sources and libraries and not (set(sources) & set(libraries)), 'incomplete source/library sets')
    rows = []
    for is_source, bindings in ((True, sources), (False, libraries)):
        for path, expected in sorted(bindings.items()):
            value = proof(path)
            require(expected is None or expected == value['sha256'], 'plan source/library SHA differs: '+str(path))
            if is_source:
                require(hashlib.sha256(git('show', freeze+':'+str(path.relative_to(ROOT)))).hexdigest()
                        == value['sha256'], 'source differs from new Git freeze: '+str(path))
            rows.append(dict(value, kind='source' if is_source else 'library'))
    clean_freeze(freeze)
    return rows


def wait_child(argv, console):
    """Every submitted child is truly drained, even if identity observation fails."""
    started, saved, errors, rc = time.monotonic_ns(), None, [], None
    with Path(console).open('x') as output:
        child = subprocess.Popen(argv, cwd=WIRELESS, env=environment(),
                                 stdout=output, stderr=subprocess.STDOUT)
        try:
            saved = identity(child.pid)
        except BaseException as error:
            errors.append('identity capture: '+repr(error))
        while True:
            try:
                rc = child.wait()
                break
            except BaseException as error:
                errors.append('actual wait: '+repr(error))
    return dict(actual_argv=argv, wrapper_identity=saved, actual_waited=True,
                actual_returncode=rc, started_monotonic_ns=started,
                ended_monotonic_ns=time.monotonic_ns(), errors=errors)


def phase(name, command, python, sources, rows, outer=None):
    outer = outer or Path(str(PREFIX)+'_'+name+'_wait')
    flags = [part for path in sorted(sources) for part in ('--source', str(path))]
    argv = [python, '-B', '-m', 'mr3_learning.reach_execution', '--scope', 'engineering',
            '--output', str(outer), *flags, '--', *command]
    row = dict(name=name, scope='engineering', outer=str(outer), command=command,
               passed=False, receipt=None, errors=[], actual_returncode=None,
               actual_waited=False, wrapper_identity=None)
    try:
        row.update(wait_child(argv, STATE/(name+'.log')))
        receipt = read(outer/'actual_wait.json'); row['receipt'] = receipt
        lo, hi = receipt['started_monotonic_ns'], receipt['ended_monotonic_ns']
        require(receipt['actual_waited'] is True and receipt['scope'] == 'engineering'
                and receipt['source_unchanged'] is True and receipt['errors'] == []
                and receipt['source_before'] == receipt['source_after']
                and receipt['actual_argv'] == command
                and row['started_monotonic_ns'] <= lo <= hi <= row['ended_monotonic_ns']
                and Decimal(receipt['actual_child_wait_seconds']) == Decimal(hi-lo)/10**9,
                'invalid real phase wait/source receipt')
        row['passed'] = (row['actual_returncode'] == 0 and not row['errors']
                         and receipt['actual_returncode'] == 0 and receipt['passed'] is True)
    except BaseException as error:
        row['errors'].append(repr(error))
    rows.append(row)
    with (STATE/'phase_ledger.jsonl').open('a') as stream:
        stream.write(json.dumps(row, allow_nan=False)+'\n'); stream.flush(); os.fsync(stream.fileno())
    return row['passed']


def matrix_absence(name, plan, python, sources, rows, matrix_outer):
    command = ['/usr/bin/python3', '-B', str(EXTERNAL_ABSENCE), '--plan', str(PLAN),
               '--matrix-outer', str(matrix_outer), '--output', str(PREFIX)+'_'+name+'.json']
    for row in rows:
        if Path(row['outer']).exists():
            command.extend(['--extra', row['outer']])
    return phase(name, command, python, sources, rows)


def verify_admission(plan, scope, resource):
    budget = resource['budget']
    require(scope.get('schema') == 'mr3-p2a-v67-native-qualification-scope-v1'
            and scope.get('admitted') is True and scope.get('capacity_qualified') is False
            and scope.get('automatic_policy_entry_allowed') is False
            and scope.get('mandatory_roles') == 30 and scope.get('matrix_episodes') == 12
            and scope.get('motion_authority_profile') == AUTHORITY_PROFILE
            and scope.get('actuation_profile') == ACTUATION_PROFILE,
            'not the admitted matrix-only 12EP/30-role authority scope')
    require(plan.get('motion_authority_profile') == AUTHORITY_PROFILE
            and plan.get('actuation_profile') == ACTUATION_PROFILE
            and plan.get('fresh_qualification_scope', {}).get('mandatory_roles') == 30
            and plan['fresh_qualification_scope'].get('episodes') == 12,
            'plan is not the fixed full qualification workload')
    require(Decimal(budget['engineering_used_at_plan_entry_seconds']) == ENTRY
            and Decimal(budget['engineering_cumulative_ceiling_seconds']) == 180000
            and Decimal(budget['total_engineering_reservation_at_entry_seconds']) == CAP
            and Decimal(budget['matrix_wall_seconds']) == 45000
            and Decimal(budget['preflight_wall_reservation_seconds']) == 120
            and Decimal(budget['engineering_remaining_seconds']) == 180000-ENTRY
            and Decimal(budget['engineering_remaining_seconds']) >= CAP,
            'new finite engineering reservation differs from actual entry')
    require(Path(plan['output_directory']) == Path(str(PREFIX)+'_matrix'), 'fixed V67 matrix output differs')


def main(argv=None):
    entered = time.monotonic_ns()
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--freeze', required=True)
    args = parser.parse_args(argv)
    started, complete_fee_known, owner, used, ceiling = entered, False, None, None, None
    plan, scope, before, after, rows, errors = None, None, [], [], [], []
    resource, sources, python, qualified, matrix_submitted = None, [], None, False, False
    completed = []
    try:
        owner = identity(os.getpid())
        bootstrap = read(STATE/'pre_exec_ancestry_v1.json')
        require(bootstrap['execution_freeze'] == args.freeze and same(bootstrap['bootstrap_identity'], owner),
                'bootstrap/exec identity or freeze differs')
        candidate = bootstrap['complete_parent_started_monotonic_ns']
        require(type(candidate) is int and 0 < candidate <= entered, 'invalid real bootstrap start')
        started, complete_fee_known = candidate, True
        used = previous_entry()
        require(canonical_location(), 'only the canonical source-bound parent from W may execute')
        reach, preparing = load_dependencies()
        plan = reach.load_plan(PLAN); scope = read(SCOPE)
        resource, inputs = preparing.verify_plan_resource(plan); inputs.finish()
        verify_admission(plan, scope, resource)
        ceiling = Decimal(resource['budget']['engineering_cumulative_ceiling_seconds'])
        before = source_check(plan, args.freeze)
        sources = [Path(row['path']) for row in before]
        python = plan['learner_python']
        write(STATE/'entry.json', dict(schema='mr3-v67-matrix-parent-entry-v1', execution_freeze=args.freeze,
            driver_identity=owner, bootstrap=bootstrap, source_before=before,
            engineering_entry_seconds=str(used), engineering_ceiling_seconds=str(ceiling),
            complete_parent_cap_seconds=str(CAP), numeric_user_approval_claimed=False,
            matrix_only=True, capacity_qualified=False, automatic_policy_entry_allowed=False))
        preflight = [python, '-B', '-m', MODULE+'preflight_v1', '--plan', str(PLAN),
                     '--freeze', args.freeze, '--output', plan['preflight']['path']]
        require(phase('preflight', preflight, python, sources, rows), 'frozen preflight failed; no matrix submitted')
        last = rows[-1]
        require(Decimal(last['ended_monotonic_ns']-last['started_monotonic_ns'])/10**9 <= 120,
                'actual preflight exceeded its original allocation')
        matrix_outer = Path(str(PREFIX)+'_matrix_wait')
        matrix_submitted = True
        matrix_ok = phase('matrix', [python, '-B', '-m', 'mr3_learning.reach_preparation',
                          '--plan', str(PLAN), '--freeze', args.freeze], python, sources, rows, matrix_outer)
        last = rows[-1]
        matrix_ok = matrix_ok and Decimal(last['ended_monotonic_ns']-last['started_monotonic_ns'])/10**9 <= 45000
        absent = matrix_absence('matrix_absence', plan, python, sources, rows, matrix_outer)
        require(matrix_ok and absent, 'matrix or saved-identity absence failed')
        qualification = Path(str(PREFIX)+'_qualification.json')
        require(phase('qualification', [python, '-B', '-m', 'mr3_learning.reach_preparation',
                '--plan', str(PLAN), '--freeze', args.freeze, '--qualify', str(matrix_outer/'actual_wait.json'),
                '--output', str(qualification)], python, sources, rows), 'full qualification failed')
        result = read(qualification)
        require(result.get('passed') is True and result.get('freeze') == args.freeze
                and result.get('mandatory_roles') == 30 and len(result.get('episodes', [])) == 12
                and result.get('actuation_profile') == ACTUATION_PROFILE
                and result.get('motion_authority_profile') == AUTHORITY_PROFILE,
                'qualification is not actual full same-freeze 12EP/30-role evidence')
        qualified = True; completed.append('matrix_qualification')
    except BaseException as error:
        errors.append(repr(error))
    finally:
        if matrix_submitted:
            try:
                if not matrix_absence('chain_final_absence', plan, python, sources, rows,
                                      Path(str(PREFIX)+'_matrix_wait')):
                    errors.append('final complete saved-identity absence failed')
            except BaseException as error:
                errors.append('final absence attempt: '+repr(error))
        if plan is not None:
            try:
                after = source_check(plan, args.freeze)
            except BaseException as error:
                errors.append('post-source: '+repr(error))
    ended = time.monotonic_ns()
    measured = Decimal(ended-started)/10**9
    fee = measured if complete_fee_known else None
    if fee is not None and fee > CAP:
        errors.append('complete parent fee exceeds prospective cap; all actual seconds retained')
    if used is not None and ceiling is not None and fee is not None and used+fee > ceiling:
        errors.append('actual cumulative engineering ceiling exceeded')
    external_ns = sum(row['ended_monotonic_ns']-row['started_monotonic_ns'] for row in rows
                      if row['name'] not in ('preflight', 'matrix')
                      and 'ended_monotonic_ns' in row and 'started_monotonic_ns' in row)
    external_seconds = Decimal(external_ns)/10**9
    try:
        if resource is not None and external_seconds > Decimal(resource['budget']['external_final_and_accounting_reservation_seconds']):
            errors.append('actual external absence/qualification waits exceed the sealed reserve')
    except BaseException as error:
        errors.append('external resource settlement unavailable: '+repr(error))
    passed = bool(complete_fee_known and not errors and qualified and before and before == after)
    summary = dict(schema='mr3-v67-matrix-parent-result-v1', passed=passed, execution_freeze=args.freeze,
        driver_identity=owner, errors=errors, actual_waits=rows, completed_stages=completed,
        started_monotonic_ns=started, ended_monotonic_ns=ended, complete_parent_fee_known=complete_fee_known,
        actual_parent_seconds=str(fee) if fee is not None else None,
        observed_driver_lower_bound_seconds=None if complete_fee_known else str(measured),
        engineering_entry_seconds=str(used) if used is not None else None,
        engineering_added_union_seconds=str(fee) if fee is not None else None,
        engineering_cumulative_seconds=str(used+fee) if used is not None and fee is not None else None,
        engineering_ceiling_seconds=str(ceiling) if ceiling is not None else None,
        engineering_remaining_seconds=str(ceiling-used-fee) if ceiling is not None and used is not None and fee is not None else None,
        complete_parent_cap_seconds=str(CAP), source_before=before, source_after=after,
        engineering_external_actual_seconds=str(external_seconds),
        post_source_check_attempted=plan is not None,
        pilot_added_union_seconds='0', validation_added_union_seconds='0', optimizer_updates=0,
        matrix_submitted=matrix_submitted, scientific_qualification=qualified and passed,
        capacity_qualified=False, automatic_policy_entry_allowed=False, P2A_complete=False,
        numeric_user_approval_claimed=False, old_failures_preserved=True,
        accounting_basis='verified bootstrap to post-source continuous actual parent; includes gaps; nested phase intervals not added',
        original_native_guard_and_owned_cleanup_unchanged=True, hard_realtime_cap_claimed=False,
        actual_tool_reap_and_driver_freshgone_required_externally=True)
    STATE.mkdir(parents=True, exist_ok=True)
    write(STATE/'summary.json', summary)
    print(json.dumps({k:summary[k] for k in ('passed','actual_parent_seconds','engineering_cumulative_seconds')}), flush=True)
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
