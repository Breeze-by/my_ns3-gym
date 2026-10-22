#!/usr/bin/python3
"""DRAFT: post-reap V50 metadata/source/accounting/identity review only.

Never import an application, model, actor, scientific reader or ROS module.
Do not run until root confirms the complete V50 driver was actually reaped.
This verdict concerns closure consistency, not the P2A scientific conjunction.
"""
import argparse
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import time

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
ROS = ROOT / 'ros2_ws/ros2-multi-robot-automap'
A = W / 'report/assets/20261023_mr3_p2a_v50_qualification'
PREFIX = 'mr3_p2a_reach_v50'
FREEZE = '23e909380b470039bd5680cf2d07710dca71097e'
ENTRY = Decimal('55959.6049312316018')
NATIVE = ROS / 'log/mr3_p2a_reach_v50'
POLICY = ROS / 'log/mr3_ppo_reach_v50'
SCOPES = {'engineering', 'pilot', 'validation'}
EXCLUDED = frozenset(('execution_inputs', 'inputs', 'observation_archive',
    'navigation_archive', 'map_blobs', 'costmap_blobs', '__pycache__'))
BLOCK = 1024 * 1024
MAX_JSON = 64 * BLOCK


def require(condition, message):
    if not condition:
        raise ValueError(message)


def decimal(value):
    require(type(value) in (str, int, float), 'invalid decimal')
    result = Decimal(str(value))
    require(result.is_finite(), 'nonfinite decimal')
    return result


def positive(value):
    if type(value) is int and value > 0:
        return value
    if type(value) is str and re.fullmatch('[1-9][0-9]*', value):
        return int(value)
    raise ValueError('not a canonical positive PID/start')


def stamp(value):
    return [value.st_dev, value.st_ino, value.st_mode, value.st_size,
            value.st_mtime_ns, value.st_ctime_ns]


def parse(raw):
    def unique(rows):
        result = {}
        for key, value in rows:
            require(key not in result, 'duplicate metadata member: ' + key)
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError('nonfinite JSON: ' + value)))


def observe(pid, start):
    now = time.monotonic_ns()
    try:
        tail = (Path('/proc') / str(pid) / 'stat').read_text().rsplit(')', 1)[1].split()
        require(len(tail) >= 20, 'malformed /proc identity')
        current = int(tail[19])
        return dict(pid=pid, start_ticks=start, observed_monotonic_ns=now,
            current_start_ticks=current, state=tail[0],
            original_identity_gone=current != start,
            observation='same_pid_different_start' if current != start else 'present_including_Z')
    except (FileNotFoundError, ProcessLookupError):
        return dict(pid=pid, start_ticks=start, observed_monotonic_ns=now,
            original_identity_gone=True, observation='absent_proc_stat')


def union_ns(intervals):
    result, lo, hi = 0, None, None
    for begin, end in sorted(intervals):
        require(type(begin) is int and type(end) is int and 0 < begin <= end,
                'invalid parent interval')
        if lo is None:
            lo, hi = begin, end
        elif begin <= hi:
            hi = max(hi, end)
        else:
            result += hi - lo
            lo, hi = begin, end
    return result + (hi - lo if lo is not None else 0)


class Review:
    def __init__(self):
        self.errors, self.budget_violations, self.identity_errors = [], [], []
        self.files, self.documents, self.identities, self.reported_verdicts = {}, {}, {}, []

    def check(self, condition, message):
        if not condition:
            self.errors.append(message)
        return bool(condition)

    def bind(self, path, expected=None):
        path = Path(path)
        # Plan library paths may legitimately be symlinks. Preserve the declared
        # path and its resolved target, with both link/file stat identities.
        link_before = stamp(path.lstat())
        resolved = path.resolve(strict=True)
        before = stamp(resolved.stat())
        require(stat.S_ISREG(before[2]), 'not a regular source/metadata file: ' + str(path))
        digest, size = hashlib.sha256(), 0
        with path.open('rb') as stream:
            for chunk in iter(lambda: stream.read(BLOCK), b''):
                digest.update(chunk)
                size += len(chunk)
        self.check(stamp(path.lstat()) == link_before and stamp(resolved.stat()) == before,
                   'file changed while hashing: ' + str(path))
        row = dict(path=str(path), resolved_path=str(resolved), bytes=size,
            sha256=digest.hexdigest(), link_stat=link_before, target_stat=before)
        old = self.files.get(str(path))
        self.check(old is None or old == row, 'bound file changed between reads: ' + str(path))
        self.files[str(path)] = row
        if expected is not None:
            wanted = expected if type(expected) is str else expected['sha256']
            self.check(row['sha256'] == wanted, 'expected SHA differs: ' + str(path))
            if type(expected) is dict and 'bytes' in expected:
                self.check(size == expected['bytes'], 'expected byte count differs: ' + str(path))
        return row

    def visit(self, value, origin, pointer=''):
        if type(value) is list:
            for index, child in enumerate(value):
                self.visit(child, origin, pointer + '/' + str(index))
            return
        if type(value) is not dict:
            return
        pairs = set()
        for key in value:
            if key in ('current_start_ticks', 'observed_start_ticks'):
                continue  # These are observations, not the original saved ID.
            if key in ('start_ticks', 'saved_start_ticks'):
                candidates = ('pid',)
            elif key == 'process_start_ticks':
                candidates = ('process_pid',) if 'process_pid' in value else ('pid',)
            elif key.endswith('_start_ticks'):
                candidates = (key[:-len('start_ticks')] + 'pid',)
            else:
                continue
            matches = [name for name in candidates if name in value]
            if not matches:
                self.identity_errors.append(origin + pointer + ': unpaired ' + key)
            pairs.update((name, key) for name in matches)
        local = {}
        for pid_key, start_key in pairs:
            try:
                key = positive(value[pid_key]), positive(value[start_key])
                local.setdefault(key[0], set()).add(key[1])
                occurrence = dict(path=origin, json_pointer=pointer,
                    pid_field=pid_key, start_field=start_key,
                    pid_value=value[pid_key], start_value=value[start_key])
                self.identities.setdefault(key, []).append(occurrence)
            except ValueError as error:
                self.identity_errors.append(origin + pointer + ': ' + str(error))
        if any(len(starts) > 1 for starts in local.values()):
            self.identity_errors.append(origin + pointer + ': conflicting same-object saved starts')
        for key, child in value.items():
            self.visit(child, origin, pointer + '/' + str(key).replace('~', '~0').replace('/', '~1'))

    def load(self, path):
        path = Path(path)
        if str(path) in self.documents:
            return self.documents[str(path)]
        require(path.suffix == '.json' and not path.is_symlink(), 'metadata must be non-symlink JSON: ' + str(path))
        require(path.stat().st_size <= MAX_JSON, 'metadata exceeds explicit 64MiB limit: ' + str(path))
        bound = self.bind(path)
        raw = path.read_bytes()
        self.check(hashlib.sha256(raw).hexdigest() == bound['sha256'], 'metadata read differs from binding')
        value = parse(raw)
        self.documents[str(path)] = value
        self.visit(value, str(path))
        return value

    def finish(self):
        for path, row in list(self.files.items()):
            self.bind(path, row)
        identities = [dict(observe(pid, start), occurrences=places)
            for (pid, start), places in sorted(self.identities.items())]
        for row in identities:
            if not row['original_identity_gone']:
                self.errors.append('saved PID/start still exists (Z counts present): ' + str(row['pid']))
        self.errors.extend(self.identity_errors)
        return identities


def metadata_paths():
    roots = [p for p in Path('/tmp').glob(PREFIX + '*')]
    roots += [NATIVE, POLICY]
    paths = set()
    for root in roots:
        if root.is_symlink() or not root.exists():
            continue
        if root.is_file():
            if root.suffix == '.json':
                paths.add(root)
            continue
        for parent, names, files in os.walk(root, followlinks=False):
            parent = Path(parent)
            names[:] = [name for name in names
                if name not in EXCLUDED and not (parent / name).is_symlink()]
            paths.update(parent / name for name in files
                if name.endswith('.json') and not (parent / name).is_symlink())
    return sorted(paths)


def run():
    r = Review()
    started = time.monotonic_ns()
    implementation = r.bind(Path(__file__).resolve())
    driver_dir = Path('/tmp') / (PREFIX + '_driver_v1')
    entry = r.load(driver_dir / 'entry.json')
    saved = entry['driver_identity']
    first = observe(positive(saved['pid']), positive(saved['start_ticks']))
    # Refuse early. Do not enumerate any runtime evidence while driver exists.
    require(first['original_identity_gone'], 'V50 driver remains alive/Z; no closed-root enumeration performed')
    summary = r.load(driver_dir / 'summary.json')
    plan_path = A / 'plan_v1.json'
    plan = r.load(plan_path)
    plan_sha = r.files[str(plan_path)]['sha256']
    r.check(entry.get('freeze') == summary.get('freeze') == FREEZE, 'driver freeze differs')
    r.check(entry.get('driver_identity') == summary.get('driver_identity'), 'driver identity differs')
    r.check(entry.get('plan') == summary.get('plan') == str(plan_path), 'driver bound plan path differs')
    r.check(summary.get('schema') == 'mr3-v50-actual-chain-driver-result-v1', 'driver schema differs')
    r.check(summary.get('p2b_gateway_started') is False and summary.get('old_failures_preserved') is True,
            'P2B/old-failure boundary differs')
    r.check(decimal(entry['engineering_entry_used_seconds']) == ENTRY
            == decimal(plan['budget']['engineering_used_at_plan_entry_seconds']), 'engineering entry differs')
    rows = summary['actual_waits']
    require(type(rows) is list and rows, 'closed driver has no parent waits')
    ledger_path = driver_dir / 'ledger.jsonl'
    bound = r.bind(ledger_path)
    raw = ledger_path.read_bytes()
    r.check(hashlib.sha256(raw).hexdigest() == bound['sha256'], 'ledger read changed')
    ledger = [parse(line) for line in raw.splitlines()]
    r.check(rows == ledger, 'driver summary/parent ledger differs')
    r.check(len({row['name'] for row in rows}) == len(rows), 'phase names repeated/no-retry violation')
    allowed = {'preflight', 'matrix', 'matrix_absence', 'qualification', 'minimum',
        'minimum_final', 'pilot', 'pilot_final', 'validation', 'validation_final',
        'minimum_failure_absence', 'pilot_failure_absence', 'validation_failure_absence', 'chain_final_absence'}
    for index, row in enumerate(rows):
        name, scope = row['name'], row['scope']
        r.visit(row, str(ledger_path), '/' + str(index))
        require(scope in SCOPES, 'unknown parent fee scope')
        r.check(name in allowed, 'unexpected submitted phase: ' + name)
        expected_scope = ('pilot' if name in ('pilot', 'pilot_final') else
                          'validation' if name in ('validation', 'validation_final') else 'engineering')
        r.check(scope == expected_scope, 'phase moved to another fee scope: ' + name)
        lo, hi = row['started_monotonic_ns'], row['ended_monotonic_ns']
        elapsed = Decimal(union_ns([(lo, hi)])) / 10**9
        r.check(decimal(row['actual_seconds']) == elapsed, 'parent fee arithmetic differs: ' + name)
        r.check(hi <= summary['ended_monotonic_ns'], 'phase outlives saved driver summary')
        if index:
            r.check(rows[index - 1]['ended_monotonic_ns'] <= lo, 'sequential parent phases overlap')
        outer = Path(row['outer'])
        require(outer.parent == Path('/tmp') and outer.name.startswith(PREFIX + '_'), 'outer path escapes V50')
        wait = r.load(outer / 'actual_wait.json')
        r.check(wait.get('schema') == 'mr3-reach-outer-actual-wait-v1'
                and wait.get('actual_waited') is True
                and type(wait.get('actual_returncode')) is int, 'outer is not actually waited: ' + name)
        r.check(row.get('wrapper_identity') == wait.get('coordinator_identity'), 'wrapper identity differs: ' + name)
        r.check(row.get('actual_returncode') == wait.get('actual_returncode') and scope == wait.get('scope'),
                'outer scope/return code differs: ' + name)
        r.check(lo <= wait['started_monotonic_ns'] <= wait['ended_monotonic_ns'] <= hi, 'inner wait outside parent: ' + name)
        r.check(decimal(wait['actual_child_wait_seconds']) ==
            Decimal(wait['ended_monotonic_ns'] - wait['started_monotonic_ns']) / 10**9, 'inner wait arithmetic differs')
        r.check(wait.get('source_unchanged') is (wait.get('source_before') == wait.get('source_after')),
                'source stability boolean differs: ' + name)
        for source in wait['source_after']:
            r.bind(source['path'], source)
        claimed = not row.get('receipt_errors') and row.get('returncode') == 0 and wait.get('passed') is True
        r.check(row.get('passed') is claimed, 'parent phase PASS does not match rc/receipt: ' + name)
        for field in ('wrapper_identity',):
            identity = row.get(field)
            require(type(identity) is dict, 'missing parent wrapper saved identity: ' + name)
            seen = observe(positive(identity['pid']), positive(identity['start_ticks']))
            require(seen['original_identity_gone'], 'phase wrapper remains alive/Z; refuse runtime enumeration')
        for field in ('coordinator_identity', 'child_identity'):
            identity = wait.get(field)
            require(type(identity) is dict, 'missing outer saved identity: ' + name + '/' + field)
            seen = observe(positive(identity['pid']), positive(identity['start_ticks']))
            require(seen['original_identity_gone'], 'phase child remains alive/Z; refuse runtime enumeration')
        r.reported_verdicts.append(dict(kind='parent_phase', name=name, passed=row.get('passed'),
            returncode=row.get('returncode'), actual_returncode=row.get('actual_returncode'),
            receipt_errors=row.get('receipt_errors'), outer_source_unchanged=wait.get('source_unchanged')))
    fees = {scope: Decimal(union_ns([(row['started_monotonic_ns'], row['ended_monotonic_ns'])
        for row in rows if row['scope'] == scope])) / 10**9 for scope in sorted(SCOPES)}
    for scope, key in (('engineering', 'engineering_added_union_seconds'),
                       ('pilot', 'pilot_added_union_seconds'), ('validation', 'validation_added_union_seconds')):
        r.check(fees[scope] == decimal(summary[key]), 'driver parent union differs: ' + scope)
    r.check(ENTRY + fees['engineering'] == decimal(summary['engineering_cumulative_used_seconds']), 'cumulative arithmetic differs')
    external_rows = [row for row in rows if row['scope'] == 'engineering'
        and row['name'] not in ('preflight', 'matrix', 'minimum')]
    external = Decimal(union_ns([(row['started_monotonic_ns'], row['ended_monotonic_ns'])
        for row in external_rows])) / 10**9
    r.check(external == decimal(summary['engineering_external_actual_seconds']), 'external parent fee arithmetic differs')
    budgets = [('engineering_cumulative', ENTRY + fees['engineering'], Decimal('75000')),
               ('engineering_external', external, Decimal('300'))]
    for name, cap in (('preflight', Decimal('120')), ('matrix', decimal(plan['budget']['matrix_wall_seconds'])),
                      ('minimum', Decimal('1800'))):
        budgets.extend((name, decimal(row['actual_seconds']), cap) for row in rows if row['name'] == name)
    endpoints = {}
    for name, cap in (('pilot', Decimal('2905.9547395464029')), ('validation', Decimal('9000'))):
        relevant = [row for row in rows if row['name'] in (name, name + '_final')]
        if relevant:
            endpoint = Decimal(relevant[-1]['ended_monotonic_ns'] - relevant[0]['started_monotonic_ns']) / 10**9
            endpoints[name] = dict(endpoint_seconds=str(endpoint), main_and_final_present=
                [row['name'] for row in relevant] == [name, name + '_final'])
            budgets.extend(((name + '_union', fees[name], cap), (name + '_endpoint', endpoint, cap)))
            budgets.extend((row['name'], decimal(row['actual_seconds']), Decimal('300'))
                for row in relevant if row['name'] == name + '_final')
    r.budget_violations = [dict(gate=name, actual=str(actual), cap=str(cap))
        for name, actual, cap in budgets if actual > cap]
    if summary.get('passed') is True:
        r.check(not r.budget_violations, 'driver PASS contradicts actual prospective resource gates')
    names = list(plan['source_bindings'])
    batch = subprocess.run(['git', 'cat-file', '--batch'], cwd=ROOT,
        input=('\n'.join(FREEZE + ':' + name for name in names) + '\n').encode(),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    require(batch.returncode == 0, 'frozen Git source batch failed')
    cursor = 0
    for name in names:
        path = Path(name)
        require(not path.is_absolute() and '..' not in path.parts, 'plan source is not canonical repository relative')
        r.bind(ROOT / path, plan['source_bindings'][name])
        end = batch.stdout.find(b'\n', cursor)
        header = batch.stdout[cursor:end].split()
        require(len(header) == 3 and header[1] == b'blob', 'missing frozen source: ' + name)
        size = int(header[2]); cursor = end + 1
        payload = batch.stdout[cursor:cursor + size]; cursor += size + 1
        r.check(hashlib.sha256(payload).hexdigest() == plan['source_bindings'][name], 'Git/plan SHA differs: ' + name)
    r.check(cursor == len(batch.stdout), 'unconsumed frozen source bytes')
    for name, wanted in plan['library_bindings'].items():
        path = Path(name)
        r.bind(path if path.is_absolute() else ROOT / path, wanted)
    # The plan is a tracked sealed input too, not merely a current JSON file.
    saved_plan = subprocess.run(['git', 'show', FREEZE + ':' + str(plan_path.relative_to(ROOT))],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    r.check(saved_plan.returncode == 0 and hashlib.sha256(saved_plan.stdout).hexdigest() == plan_sha,
            'current plan differs from frozen plan')
    selected = metadata_paths()
    for path in selected:
        value = r.load(path)
        if type(value) is dict and ('passed' in value or 'completed' in value):
            r.reported_verdicts.append(dict(kind='existing_metadata_only', path=str(path),
                schema=value.get('schema'), passed=value.get('passed'), completed=value.get('completed'),
                errors=value.get('errors'), error=value.get('error'), status=value.get('status')))
    r.check(metadata_paths() == selected, 'closed metadata membership changed during review')
    absence_path = Path('/tmp') / (PREFIX + '_chain_final_absence.json')
    matrix_submitted = any(row['name'] == 'matrix' for row in rows)
    absence = r.documents.get(str(absence_path))
    if matrix_submitted:
        r.check(type(absence) is dict, 'submitted matrix lacks final external absence report')
    identities = r.finish()
    all_gone = bool(identities) and not r.identity_errors and all(row['original_identity_gone'] for row in identities)
    # Scientific FAIL, ineligibility and SKIPPED are preserved as reported facts,
    # not turned into a metadata inconsistency by demanding scientific PASS.
    return dict(schema='mr3-v50-independent-closed-metadata-review-draft-v1',
        created_utc=datetime.now(timezone.utc).isoformat(), freeze=FREEZE, plan_sha256=plan_sha,
        passed=not r.errors, review_errors=r.errors, activity_passed=summary.get('passed'),
        driver_errors=summary.get('errors'), completed_stages=summary.get('completed_stages'),
        archive_eligible=not r.errors and all_gone,
        all_saved_PID_start_identities_fresh_gone=all_gone,
        saved_identity_count=len(identities), saved_identities=identities,
        source_count=len(plan['source_bindings']), library_count=len(plan['library_bindings']),
        engineering_entry_seconds=str(ENTRY), engineering_added_parent_union_seconds=str(fees['engineering']),
        engineering_cumulative_seconds=str(ENTRY + fees['engineering']),
        engineering_remaining_seconds=str(Decimal('75000') - ENTRY - fees['engineering']),
        pilot_added_parent_union_seconds=str(fees['pilot']), validation_added_parent_union_seconds=str(fees['validation']),
        engineering_external_parent_union_seconds=str(external), resource_violations=r.budget_violations,
        policy_endpoint_gates=endpoints, actual_parent_intervals=rows,
        fee_basis='Complete parent actual-wait interval union per scope. Nested inner intervals and whole driver wall are not added. Gaps remain in policy endpoint gates.',
        metadata_and_source_bindings=list(r.files.values()), selected_metadata_paths=[str(path) for path in selected],
        reported_scientific_and_closure_verdicts=r.reported_verdicts,
        final_absence_reported_passed=absence.get('passed') if type(absence) is dict else None,
        source_before_after_checked=True, scientific_results_recomputed=False,
        reviewer_implementation=implementation,
        models_loaded=False, actor_inputs_read=False, raw_telemetry_read=False, signals_sent=0,
        native_runs=0, gpu_calls=0, independent_P2A_scientific_acceptance_inferred=False,
        required_separate_scientific_gate='Full same-freeze 12EP/30roles qualification, actual eligible minimum positive update, pilot real positive update/checkpoint, three final-only strict95/zero-update/same-checkpoint actual completions, original caps and closure; no cross-freeze or driver-PASS shortcut.',
        started_monotonic_ns=started, ended_monotonic_ns=time.monotonic_ns(),
        draft_execution_note='Prepared statically while activity was live; only the later explicit invocation performs metadata/proc reads.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze', required=True, choices=(FREEZE,))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(args.output.parent == Path('/tmp') and args.output.name.startswith('mr3_p2a_v50_'),
            'review output must stay outside activity roots under /tmp/mr3_p2a_v50_*')
    require(not args.output.exists() and not args.output.is_symlink(), 'exclusive review output already exists')
    try:
        result = run()
    except BaseException as error:
        result = dict(schema='mr3-v50-independent-closed-metadata-review-draft-failure-v1',
            freeze=FREEZE, passed=False, archive_eligible=False, error=repr(error),
            scientific_results_recomputed=False, partial_or_failed_review_preserved=True)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({key: result.get(key) for key in ('passed', 'activity_passed', 'archive_eligible',
        'saved_identity_count', 'engineering_added_parent_union_seconds', 'review_errors', 'error')}), flush=True)
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
