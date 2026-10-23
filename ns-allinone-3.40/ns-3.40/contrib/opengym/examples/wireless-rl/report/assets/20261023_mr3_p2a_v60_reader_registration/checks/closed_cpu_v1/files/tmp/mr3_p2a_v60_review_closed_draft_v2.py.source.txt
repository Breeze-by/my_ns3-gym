#!/usr/bin/python3
"""DRAFT v1: post-reap V60 metadata/source/accounting/identity review only.

Never import an application, model, actor, scientific reader or ROS module.
Do not run until root confirms the complete V60 driver was actually reaped.
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
from types import ModuleType

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
ROS = ROOT / 'ros2_ws/ros2-multi-robot-automap'
A = W / 'report/assets/20261023_mr3_p2a_v60_reader_registration'
PREFIX = 'mr3_p2a_reach_v60'
FREEZE = '935b466bd076002afdfe161b55a508938de2a8b0'
ENTRY = Decimal('94316.6592918916018')
CEILING = Decimal('150000')
NATIVE = ROS / 'log/mr3_p2a_reach_v60'
POLICY = ROS / 'log/mr3_ppo_reach_v60'
ROOT_TOOL = Path('/tmp/mr3_p2a_v60_root_tool_v1')
ROOT_CUSTODY_PINS = {'launch_declaration_v1.json': '810698858d227fce4b4f9b789b08cb819fe5daaf6565e9badad8ca4c71338eba', 'live_ancestry_v1.json': 'acd851c3132334181ff9763889df8cda8eed5eade95183b4566ff4ee14738431', 'ownership_scope_v1.json': '38dfd99aab0d29e785c14ba59c00dce0d7dd97e554f91f6fcc4194afe6196414'}
OPERATIONAL_HISTORY_PATH = ROOT_TOOL/'handoff_before_v60_launch_v1.json'
OPERATIONAL_HISTORY_SHA256 = '35650de20950b22b013c9ece1b4664d5e42ec684ba4ad57c0d2f771988c9f7d2'
ACTUATION_PROFILE = 'initial-zero-encoder-hold-v1'
SCOPES = {'engineering', 'pilot', 'validation'}
EXCLUDED = frozenset(('execution_inputs', 'inputs', 'observation_archive',
    'navigation_archive', 'map_blobs', 'costmap_blobs', '__pycache__'))
BLOCK = 1024 * 1024
MAX_JSON = 64 * BLOCK
IDENTITY_HELPER = W / 'report/assets/20261019_mr3_p2a_v16/external_absence_v1.py'
IDENTITY_HELPER_SHA = 'cedae11c4b9bbf6f4887ae5afe2fa10fff04e5a28595f5c9e748669c8d18493f'


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


def same_identity(left, right):
    try:
        return ((positive(left['pid']), positive(left['start_ticks']))
                == (positive(right['pid']), positive(right['start_ticks'])))
    except (KeyError, TypeError, ValueError):
        return False


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


def observe_pid_only(pid):
    """Observe a PID without inventing the missing original start identity."""
    now = time.monotonic_ns()
    try:
        tail = (Path('/proc') / str(pid) / 'stat').read_text().rsplit(')', 1)[1].split()
        require(len(tail) >= 20, 'malformed /proc PID-only observation')
        return dict(pid=pid, observed_monotonic_ns=now,
            current_start_ticks=int(tail[19]), state=tail[0],
            observation='PID_present_original_start_unknown', original_identity_status='unknown')
    except (FileNotFoundError, ProcessLookupError):
        return dict(pid=pid, observed_monotonic_ns=now,
            observation='PID_absent_at_lookup_original_start_still_unknown', original_identity_status='unknown')
    except (OSError, ValueError, IndexError) as error:
        return dict(pid=pid, observed_monotonic_ns=now,
            observation='unreadable_PID_original_start_unknown', original_identity_status='unknown', error=repr(error))


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


def load_identity_helper():
    raw = IDENTITY_HELPER.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == IDENTITY_HELPER_SHA,
            'immutable A16 identity parser differs')
    module = ModuleType('_v60_exact_original_a16_identity_parser')
    module.__file__ = str(IDENTITY_HELPER)
    exec(compile(raw, str(IDENTITY_HELPER), 'exec'), module.__dict__)
    return module


def a16_pid_occurrence_rows(evidence):
    """Classify original canonical-pid locations; never borrow another object."""
    rows = []
    for pid, locations in sorted(evidence.pid_only.items()):
        for location in sorted(locations):
            matches = [place for (saved_pid, start), places in evidence.identities.items()
                if saved_pid == pid for place in places
                if place['pid_field'] == 'pid'
                and place['path'] + place['json_pointer'] == location]
            starts = {positive(place['start_value']) for place in matches}
            status = ('missing_same_object_start' if not matches else
                'paired_same_object' if len(starts) == 1 else 'conflicting_same_object_starts')
            rows.append(dict(a16_original_location=location, pid_field='pid', pid_value=pid,
                identity_status=status, same_object_pair_occurrences=matches))
    return rows


def archive_gate_results(parent_wait_proof_valid, required_reaped, bound_inputs_stable,
                         membership_stable, errors, identity_complete):
    parent_valid = parent_wait_proof_valid is True
    return dict(parent_wait_proof_valid=parent_valid,
        parent_coordinators_actual_waited_and_fresh_gone=parent_valid,
        archive_evidence_preservation_admissible=bool(parent_valid and required_reaped
            and bound_inputs_stable and membership_stable),
        closed_archive_eligible=bool(parent_valid and not errors and identity_complete
            and bound_inputs_stable and membership_stable))


def frozen_activity_python_paths():
    # The driver captured this tree before execution. Later closure-tool copies
    # must not retroactively change its declared source set.
    raw = subprocess.check_output(['git', 'ls-tree', '-z', '--name-only',
        FREEZE + ':' + str(A.relative_to(ROOT))], cwd=ROOT)
    names = [part.decode('utf-8') for part in raw.split(b'\0') if part]
    require(all('/' not in name and name not in ('.', '..') for name in names),
            'noncanonical frozen activity tree member')
    return sorted(A / name for name in names if name.endswith('.py'))


class Review:
    def __init__(self):
        self.errors, self.budget_violations, self.identity_errors = [], [], []
        self.files, self.documents, self.identities, self.reported_verdicts = {}, {}, {}, []
        self.pid_only, self.relationship_pids = {}, []
        self.bound_inputs_stable = True
        self.parent_wait_proof_valid = True
        self.identity_helper = load_identity_helper()
        self.a16_original_inputs, self.encoded_identity_inputs = [], []
        self.a16_canonical_pid_occurrences = []
        self.launch_pids = set()
        self.operational_history = []

    def stable(self, condition, message):
        if not condition:
            self.bound_inputs_stable = False
        return self.check(condition, message)

    def check(self, condition, message):
        if not condition:
            self.errors.append(message)
        return bool(condition)

    def parent_check(self, condition, message):
        if not condition:
            self.parent_wait_proof_valid = False
        return self.check(condition, message)

    def merge_a16(self, evidence, origin):
        # Keep the exact original same-object pairs/types and launch PID facts.
        # No PID-only occurrence obtains a start from another object.
        for key, places in evidence.identities.items():
            self.identities.setdefault(key, []).extend(places)
        # A16.pid_only is a raw canonical-PID occurrence registry: it also
        # includes objects which have a valid same-object start. Preserve all
        # original occurrences, but only genuinely unpaired ones are unknown.
        for row in a16_pid_occurrence_rows(evidence):
            self.a16_canonical_pid_occurrences.append(row)
            if row['identity_status'] == 'missing_same_object_start':
                self.pid_only.setdefault(row['pid_value'], []).append(dict(
                    path=row['a16_original_location'], pid_field='A16_original_canonical_PID',
                    pid_value=row['pid_value'], start_field=None,
                    identity_status='missing_same_object_start'))
        for pid in evidence.launch_pids:
            self.launch_pids.add(pid)
            self.pid_only.setdefault(pid, []).append(dict(path=origin,
                pid_field='A16_exact_launch_process_PID', pid_value=pid,
                start_field=None, identity_status='launch_PID_requires_global_saved_start_coverage'))
        self.identity_errors.extend(str(row['source']) + ': ' + str(row['reason'])
                                    for row in evidence.errors)

    def consume_encoded_identity(self, raw, origin, pointer):
        evidence = self.identity_helper.Evidence()
        try:
            value = self.identity_helper.parse(raw)
            evidence.visit(value, origin, pointer + '/@decoded_json')
        except (ValueError, TypeError, UnicodeError) as error:
            evidence.error(origin + pointer, error)
        self.merge_a16(evidence, origin + pointer)
        self.encoded_identity_inputs.append(dict(path=origin, json_pointer=pointer,
            raw_json_sha256=hashlib.sha256(raw.encode()).hexdigest(),
            raw_json_bytes=len(raw.encode()), exact_A16_extraction=True))

    def load_identity_stream(self, path):
        require(path.name in ('launch.log', 'ledger.jsonl') and not path.is_symlink(),
                'only declared launch/process ledger streams may be parsed')
        bound = self.bind(path)
        evidence = self.identity_helper.Evidence()
        evidence.consume(path)
        evidence.finish()
        self.merge_a16(evidence, str(path))
        require(len(evidence.bindings) == 1, 'A16 did not bind the one original stream')
        original = evidence.bindings[0]
        self.stable(original['sha256'] == bound['sha256'] and original['bytes'] == bound['bytes'],
                    'A16 consumed bytes differ from the reviewed stream: ' + str(path))
        self.a16_original_inputs.append(dict(original, exact_A16_extraction=True))
        self.documents[str(path)] = None
        return None

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
        self.stable(stamp(path.lstat()) == link_before and stamp(resolved.stat()) == before,
                   'file changed while hashing: ' + str(path))
        row = dict(path=str(path), resolved_path=str(resolved), bytes=size,
            sha256=digest.hexdigest(), link_stat=link_before, target_stat=before)
        old = self.files.get(str(path))
        self.stable(old is None or old == row, 'bound file changed between reads: ' + str(path))
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
        local, locally_paired_fields = {}, set()
        for pid_key, start_key in pairs:
            try:
                key = positive(value[pid_key]), positive(value[start_key])
                local.setdefault(key[0], set()).add(key[1])
                occurrence = dict(path=origin, json_pointer=pointer,
                    pid_field=pid_key, start_field=start_key,
                    pid_value=value[pid_key], start_value=value[start_key])
                self.identities.setdefault(key, []).append(occurrence)
                locally_paired_fields.add(pid_key)
            except ValueError as error:
                self.identity_errors.append(origin + pointer + ': ' + str(error))
        if any(len(starts) > 1 for starts in local.values()):
            self.identity_errors.append(origin + pointer + ': conflicting same-object saved starts')
        for key, item in value.items():
            is_pid_field = key in ('pid', 'process_pid') or key.endswith('_pid')
            if not is_pid_field or key in locally_paired_fields:
                continue
            occurrence = dict(path=origin, json_pointer=pointer, pid_field=key,
                pid_value=item, start_field=None, identity_status='missing_same_object_start')
            # These fields explicitly describe an observed/ancestry relation,
            # not a saved owned-process identity. Retain rather than promote it.
            if key in ('current_pid', 'observed_pid', 'parent_pid'):
                self.relationship_pids.append(occurrence)
                continue
            try:
                pid = positive(item)
                self.pid_only.setdefault(pid, []).append(occurrence)
            except ValueError as error:
                self.identity_errors.append(origin + pointer + ': invalid PID-only field ' + key + ': ' + str(error))
        # A prior external observer may already have reported a globally
        # unbound PID. Its original unknown must not disappear merely because
        # the list has no {pid,start_ticks} object for the generic walker.
        if 'pids_without_saved_start' in value:
            unknown = value['pids_without_saved_start']
            if type(unknown) is not list:
                self.identity_errors.append(origin + pointer + ': malformed pids_without_saved_start')
            else:
                for index, item in enumerate(unknown):
                    try:
                        pid = positive(item)
                        self.pid_only.setdefault(pid, []).append(dict(path=origin,
                            json_pointer=pointer + '/pids_without_saved_start/' + str(index),
                            pid_field='reported_unbound_PID', pid_value=item, start_field=None,
                            identity_status='reported_original_start_unknown'))
                    except ValueError as error:
                        self.identity_errors.append(origin + pointer + ': invalid reported unbound PID: ' + str(error))
        for key, child in value.items():
            child_pointer = pointer + '/' + str(key).replace('~', '~0').replace('/', '~1')
            if key == 'raw_json' and type(child) is str and ('pid' in child or 'start_ticks' in child):
                self.consume_encoded_identity(child, origin, child_pointer)
            self.visit(child, origin, child_pointer)

    def load(self, path):
        path = Path(path)
        if str(path) in self.documents:
            return self.documents[str(path)]
        if path.name in ('launch.log', 'ledger.jsonl'):
            return self.load_identity_stream(path)
        require(path.suffix == '.json' and not path.is_symlink(), 'metadata must be non-symlink JSON: ' + str(path))
        require(path.stat().st_size <= MAX_JSON, 'metadata exceeds explicit 64MiB limit: ' + str(path))
        bound = self.bind(path)
        raw = path.read_bytes()
        self.stable(hashlib.sha256(raw).hexdigest() == bound['sha256'], 'metadata read differs from binding')
        value = parse(raw)
        self.documents[str(path)] = value
        if path == OPERATIONAL_HISTORY_PATH:
            require(bound['sha256'] == OPERATIONAL_HISTORY_SHA256,
                    'predeclared operational handoff history changed')
            require(value.get('active_session') is None and value.get('active_tool_session') is None
                    and value.get('execution_freeze') == '783aec55353ecb93385ffe305300ab760f9c24fe'
                    and value.get('current_activity') == 'V59 full frozen qualification and policy chain',
                    'predeclared handoff is not the prior V59 closed operational snapshot')
            history = Review()
            history.visit(value, str(path))
            self.operational_history.append({'category':'prior-closed-operational-history',
                'binding':bound, 'original_bytes_and_identity_fields_preserved':True,
                'runtime_producer':False, 'current_owned_actor':False,
                'fresh_absence_required':False, 'current_cleanup_credit':False,
                'saved_identity_pairs':[{'pid':pid,'start_ticks':start,'occurrences':places}
                    for (pid,start),places in sorted(history.identities.items())],
                'pid_only_occurrences':history.pid_only,
                'identity_parse_errors':history.identity_errors})
            return value
        self.visit(value, str(path))
        return value

    def finish(self):
        for path, row in list(self.files.items()):
            self.bind(path, row)
        identities = []
        for (pid, start), places in sorted(self.identities.items()):
            try:
                row = observe(pid, start)
            except (OSError, ValueError, IndexError) as error:
                row = dict(pid=pid, start_ticks=start, original_identity_gone=False,
                    observation='unreadable_saved_PID_start', error=repr(error))
            identities.append(dict(row, occurrences=places))
        for row in identities:
            if not row['original_identity_gone']:
                self.errors.append('saved PID/start still exists (Z counts present): ' + str(row['pid']))
        self.errors.extend(self.identity_errors)
        known_pids = {pid for pid, start in self.identities}
        pid_only = []
        for pid, places in sorted(self.pid_only.items()):
            # A16's global PID inventory-coverage rule is retained. A PID-only
            # occurrence is never converted to a new pair or described as gone.
            separately_saved = [dict(pid=pid_, start_ticks=start)
                for pid_, start in sorted(self.identities) if pid_ == pid]
            pid_only.append(dict(observe_pid_only(pid), occurrences=places,
                has_separately_saved_start_identity=pid in known_pids,
                separately_saved_identity_candidates=separately_saved,
                no_pair_reconstructed_from_different_objects=True))
        unbound = sorted(set(self.pid_only) - known_pids)
        for pid in unbound:
            self.errors.append('saved PID has no separately saved start identity; unknown is retained: ' + str(pid))
        return identities, pid_only, unbound


def metadata_paths():
    roots = [p for p in Path('/tmp').glob(PREFIX + '*')]
    roots += [NATIVE, POLICY, ROOT_TOOL]
    paths = set()
    for root in roots:
        if root.is_symlink() or not root.exists():
            continue
        if root.is_file():
            if root.suffix == '.json' or root.name in ('launch.log', 'ledger.jsonl'):
                paths.add(root)
            continue
        for parent, names, files in os.walk(root, followlinks=False):
            parent = Path(parent)
            names[:] = [name for name in names
                if name not in EXCLUDED and not (parent / name).is_symlink()]
            paths.update(parent / name for name in files
                if (name.endswith('.json') or name in ('launch.log', 'ledger.jsonl'))
                and not (parent / name).is_symlink())
    return sorted(paths)


def verify_root_tool_wait(r, driver_dir, entry, summary, required_reaped):
    """Keep declared root ownership exact; transport ancestors remain nonowned."""
    tool_wait = r.load(ACTUAL_TOOL_WAIT)
    require(tool_wait.get('schema') == 'mr3-v60-root-actual-tool-wait-v1'
            and type(tool_wait.get('session_id')) is int and tool_wait['session_id'] == 30588
            and tool_wait.get('actual_waited') is True
            and type(tool_wait.get('actual_returncode_observed')) is int
            and type(tool_wait.get('observed_monotonic_ns')) is int
            and tool_wait['observed_monotonic_ns'] >= summary['ended_monotonic_ns'],
            'real root tool reap is absent, pending or malformed')
    records = {}
    for name, digest in ROOT_CUSTODY_PINS.items():
        path = ROOT_TOOL / name
        bound = r.bind(path, {'sha256':digest})
        raw = path.read_bytes()
        require(hashlib.sha256(raw).hexdigest() == bound['sha256'], 'root custody changed while reading')
        # Explicit classification below replaces generic all-ancestor ownership.
        value = parse(raw)
        r.documents[str(path)] = value
        records[name] = value
    launch = records['launch_declaration_v1.json']
    live = records['live_ancestry_v1.json']
    ownership = records['ownership_scope_v1.json']
    owned = ownership.get('owned_launch_lifetime_identities')
    nonowned = ownership.get('observed_persistent_nonowned_ancestors')
    ancestry = live.get('observed_ancestry')
    saved = entry['driver_identity']
    require(launch.get('schema') == 'mr3-v60-root-launch-declaration-v1'
            and launch.get('execution_freeze') == FREEZE
            and launch.get('source_freeze') == 'a03b9c53060d491e90f08c40ca58c5bb67256d3d'
            and launch.get('cwd') == str(W)
            and launch.get('chain_argv') == ['/home/zhuyulab/miniconda3/envs/ns3gym/bin/python','-B','-m',
                'report.assets.20261023_mr3_p2a_v60_reader_registration.execute_chain_v1','--freeze',FREEZE]
            and live.get('schema') == 'mr3-v60-live-root-ancestry-observation-v1'
            and live.get('tool_session') == 30588
            and live.get('driver_saved_identity_matches_live') is True
            and live.get('driver_entry', {}).get('path') == str(driver_dir/'entry.json')
            and live['driver_entry'].get('sha256') == r.files[str(driver_dir/'entry.json')]['sha256']
            and ownership.get('schema') == 'mr3-v60-root-ownership-scope-v1'
            and ownership.get('root_scope_requires_owned_freshgone_after_true_tool_reap') is True
            and type(owned) is list and len(owned) == 3
            and type(nonowned) is list and len(nonowned) == 2
            and ancestry == owned + nonowned
            and same_identity(saved, owned[0]) and owned[0]['argv'] == launch['chain_argv']
            and saved.get('parent') == owned[0]['parent'] == owned[1]['pid']
            and owned[1]['parent'] == owned[2]['pid'] and owned[2]['parent'] == nonowned[0]['pid']
            and nonowned[0]['parent'] == nonowned[1]['pid']
            and launch['declared_monotonic_ns'] <= live['observed_monotonic_ns']
            <= ownership['observed_monotonic_ns'] <= tool_wait['observed_monotonic_ns'],
            'saved root launch/ancestry/ownership does not match this actual driver')
    owned_keys = {(positive(row['pid']),positive(row['start_ticks'])) for row in owned}
    nonowned_keys = {(positive(row['pid']),positive(row['start_ticks'])) for row in nonowned}
    require(len(owned_keys) == 3 and len(nonowned_keys) == 2 and not owned_keys.intersection(nonowned_keys),
            'root owned/nonowned identity sets overlap or repeat')
    for index, row in enumerate(owned):
        key = positive(row['pid']),positive(row['start_ticks'])
        require(observe(*key)['original_identity_gone'], 'declared owned root identity remains present/Z')
        required_reaped[key] = {'pid':key[0],'start_ticks':key[1]}
        r.visit(row, str(ROOT_TOOL/'ownership_scope_v1.json'), '/owned_launch_lifetime_identities/'+str(index))
    post_path = ROOT_TOOL/'postreap_root_owned_v1.json'
    post_bound = None
    if post_path.exists():
        post_bound = r.bind(post_path)
        post_raw = post_path.read_bytes()
        require(hashlib.sha256(post_raw).hexdigest() == post_bound['sha256'], 'post-reap root record changed')
        post = parse(post_raw)
        r.documents[str(post_path)] = post
        require(post.get('actual_tool_reaped_first') is True
                and post.get('all_owned_root_saved_identities_fresh_gone') is True
                and post.get('nonowned_transport_ancestors_excluded_as_predeclared') == nonowned
                and [row.get('saved_identity') for row in post.get('observations',[])] == owned
                and all(row.get('saved_identity_gone') is True and row.get('current') is None
                        for row in post['observations'])
                and type(post.get('observed_monotonic_ns')) is int
                and post['observed_monotonic_ns'] >= tool_wait['observed_monotonic_ns'],
                'root post-reap observation/ownership differs from original declaration')
        for index, row in enumerate(post['observations']):
            r.visit(row, str(post_path), '/observations/'+str(index))
    r.root_ownership = {'owned_launch_lifetime_identities':owned,
        'observed_persistent_nonowned_ancestors':nonowned,
        'nonowned_absence_required':False, 'all_ancestor_absence_claimed':False,
        'scope_declared_before_closure':True, 'original_observations_preserved':True,
        'actual_root_interval_invented':False, 'root_tool_outer_wall_double_added':False,
        'postreap_owned_root_record':post_bound,
        'postreap_root_record_optional_owned_absence_still_independently_required':True}
    r.parent_check(tool_wait['actual_returncode_observed'] == (0 if summary.get('passed') is True else 1),
                   'real root return contradicts completed driver result')
    return tool_wait, launch, ROOT_TOOL/'live_ancestry_v1.json'


def run():
    r = Review()
    started = time.monotonic_ns()
    implementation = r.bind(Path(__file__).resolve())
    identity_parser = r.bind(IDENTITY_HELPER, IDENTITY_HELPER_SHA)
    frozen_identity_parser = subprocess.check_output(['git', 'show',
        FREEZE + ':' + str(IDENTITY_HELPER.relative_to(ROOT))], cwd=ROOT)
    r.check(hashlib.sha256(frozen_identity_parser).hexdigest() == IDENTITY_HELPER_SHA,
            'A16 identity parser differs from the frozen library source')
    real_tool = r.load(ACTUAL_TOOL_WAIT)
    require(real_tool.get('schema') == 'mr3-v60-root-actual-tool-wait-v1'
            and real_tool.get('session_id') == 30588 and real_tool.get('actual_waited') is True
            and type(real_tool.get('actual_returncode_observed')) is int,
            'actual root tool reap required before runtime metadata enumeration')
    git = lambda *args: subprocess.check_output(['git',*args],cwd=ROOT)
    require(git('rev-parse','HEAD').decode().strip() == FREEZE
            == git('rev-parse','origin/main').decode().strip()
            and not git('status','--porcelain'),
            'metadata review must precede archive/docs at the clean pushed execution freeze')
    driver_dir = Path('/tmp') / (PREFIX + '_driver_v1')
    entry = r.load(driver_dir / 'entry.json')
    saved = entry['driver_identity']
    first = observe(positive(saved['pid']), positive(saved['start_ticks']))
    # Refuse early. Do not enumerate any runtime evidence while driver exists.
    require(first['original_identity_gone'], 'V60 driver remains alive/Z; no closed-root enumeration performed')
    required_reaped = {(positive(saved['pid']), positive(saved['start_ticks'])):
        dict(pid=positive(saved['pid']), start_ticks=positive(saved['start_ticks']))}
    summary = r.load(driver_dir / 'summary.json')
    tool_wait, launch, ancestor_path = verify_root_tool_wait(
        r, driver_dir, entry, summary, required_reaped)
    plan_path = A / 'plan_v1.json'
    plan = r.load(plan_path)
    plan_sha = r.files[str(plan_path)]['sha256']
    resource_spec = plan.get('engineering_resource')
    require(type(resource_spec) is dict and resource_spec.get('path') == str(
            (A / 'resource_v1.json').relative_to(ROOT)), 'another/missing sealed resource')
    resource_path = ROOT / resource_spec['path']
    r.bind(resource_path, resource_spec)
    resource = r.load(resource_path)
    r.parent_check(resource.get('schema') == 'mr3-reach-autonomous-engineering-block-v1'
        and resource.get('decision_maker') == 'agent'
        and resource.get('numeric_user_approval_claimed') is False
        and decimal(resource['engineering_used_seconds']) == ENTRY
        and decimal(resource['engineering_ceiling_seconds']) == CEILING
        and decimal(resource['engineering_remaining_seconds']) == CEILING - ENTRY
        and plan['budget'].get('reservation_profile') == 'autonomous-engineering-block-v1'
        and len(plan['source_bindings']) == 1029 and len(plan['library_bindings']) == 10,
        'sealed autonomous resource/carry/source inventory differs')
    r.parent_check(entry.get('engineering_resource') == summary.get('engineering_resource')
            == resource_spec
        and entry.get('numeric_user_approval_claimed') is False
        and summary.get('numeric_user_approval_claimed') is False
        and entry.get('actuation_profile') == summary.get('actuation_profile') == plan.get('actuation_profile') == ACTUATION_PROFILE
        and decimal(entry['engineering_ceiling_seconds']) == CEILING,
        'driver entry/summary did not retain the same agent-selected sealed resource')
    r.parent_check(launch.get('plan', {}).get('path') == str(plan_path)
        and launch['plan'].get('sha256') == plan_sha
        and launch.get('resource', {}).get('path') == str(resource_path)
        and launch['resource'].get('sha256') == resource_spec.get('sha256'),
        'actual root launch does not bind the sealed plan/resource')
    r.parent_check(entry.get('freeze') == summary.get('freeze') == FREEZE, 'driver freeze differs')
    r.parent_check(same_identity(entry.get('driver_identity'), summary.get('driver_identity')), 'driver PID/start differs')
    r.parent_check(entry.get('plan') == summary.get('plan') == str(plan_path), 'driver bound plan path differs')
    r.parent_check(summary.get('schema') == 'mr3-v60-actual-chain-driver-result-v1', 'driver schema differs')
    r.parent_check(summary.get('p2b_gateway_started') is False and summary.get('old_failures_preserved') is True,
            'P2B/old-failure boundary differs')
    r.parent_check(decimal(entry['engineering_entry_used_seconds']) == ENTRY
            == decimal(plan['budget']['engineering_used_at_plan_entry_seconds']), 'engineering entry differs')
    expected_wait_sources = {ROOT / path for path in plan['source_bindings']}
    expected_wait_sources.update(Path(path) if Path(path).is_absolute() else ROOT / path
        for path in plan['library_bindings'])
    frozen_activity_sources = frozen_activity_python_paths()
    expected_wait_sources.update((plan_path, *frozen_activity_sources))
    # Match the producer's sorted declared paths, including any two aliases
    # which legitimately resolve to the same library file.
    expected_wait_source_paths = [str(path.resolve()) for path in sorted(expected_wait_sources)]
    rows = summary['actual_waits']
    require(type(rows) is list and rows, 'closed driver has no parent waits')
    ledger_path = driver_dir / 'ledger.jsonl'
    bound = r.bind(ledger_path)
    raw = ledger_path.read_bytes()
    r.stable(hashlib.sha256(raw).hexdigest() == bound['sha256'], 'ledger read changed')
    ledger = [parse(line) for line in raw.splitlines()]
    r.parent_check(rows == ledger, 'driver summary/parent ledger differs')
    r.parent_check(len({row['name'] for row in rows}) == len(rows), 'phase names repeated/no-retry violation')
    allowed = {'preflight', 'matrix', 'matrix_absence', 'qualification', 'minimum',
        'minimum_final', 'pilot', 'pilot_final', 'validation', 'validation_final',
        'minimum_failure_absence', 'pilot_failure_absence', 'validation_failure_absence', 'chain_final_absence'}
    phase_source_proofs = {}
    for index, row in enumerate(rows):
        name, scope = row['name'], row['scope']
        r.visit(row, str(ledger_path), '/' + str(index))
        require(scope in SCOPES, 'unknown parent fee scope')
        r.parent_check(name in allowed, 'unexpected submitted phase: ' + name)
        expected_scope = ('pilot' if name in ('pilot', 'pilot_final') else
                          'validation' if name in ('validation', 'validation_final') else 'engineering')
        r.parent_check(scope == expected_scope, 'phase moved to another fee scope: ' + name)
        lo, hi = row['started_monotonic_ns'], row['ended_monotonic_ns']
        elapsed = Decimal(union_ns([(lo, hi)])) / 10**9
        r.parent_check(decimal(row['actual_seconds']) == elapsed, 'parent fee arithmetic differs: ' + name)
        r.parent_check(type(row.get('returncode')) is int and type(row.get('receipt_errors')) is list
                and row['receipt_errors'] == [], 'parent wrapper return/receipt proof invalid: ' + name)
        r.parent_check(entry['started_monotonic_ns'] <= lo <= hi <= summary['ended_monotonic_ns'],
                       'phase is outside the complete saved driver interval')
        if index:
            r.parent_check(rows[index - 1]['ended_monotonic_ns'] <= lo, 'sequential parent phases overlap')
        outer = Path(row['outer'])
        require(outer.parent == Path('/tmp') and outer.name.startswith(PREFIX + '_'), 'outer path escapes V60')
        wait = r.load(outer / 'actual_wait.json')
        r.parent_check(wait.get('schema') == 'mr3-reach-outer-actual-wait-v1'
                and wait.get('actual_waited') is True
                and type(wait.get('actual_returncode')) is int, 'outer is not actually waited: ' + name)
        r.parent_check(same_identity(row.get('wrapper_identity'), wait.get('coordinator_identity')),
                       'wrapper PID/start differs: ' + name)
        r.parent_check(type(wait.get('child_identity')) is dict
                and type(wait.get('coordinator_identity')) is dict
                and wait['child_identity'].get('parent') == wait['coordinator_identity'].get('pid'),
                'actual waited child is not bound to its coordinator parent: ' + name)
        r.parent_check(row.get('actual_returncode') == wait.get('actual_returncode') and scope == wait.get('scope'),
                'outer scope/return code differs: ' + name)
        r.parent_check(lo <= wait['started_monotonic_ns'] <= wait['ended_monotonic_ns'] <= hi, 'inner wait outside parent: ' + name)
        r.parent_check(decimal(wait['actual_child_wait_seconds']) ==
            Decimal(wait['ended_monotonic_ns'] - wait['started_monotonic_ns']) / 10**9, 'inner wait arithmetic differs')
        r.parent_check(type(wait.get('source_before')) is list and bool(wait['source_before'])
                and wait.get('source_before') == wait.get('source_after')
                and wait.get('source_unchanged') is True,
                'actual wait lacks its unchanged complete source receipt: ' + name)
        r.parent_check([source.get('path') for source in wait['source_before']] == expected_wait_source_paths,
                'actual-wait source set differs from the frozen driver source set: ' + name)
        r.parent_check(wait.get('cwd') == str(W), 'actual-wait working directory differs: ' + name)
        r.parent_check(type(wait.get('actual_argv')) is list and bool(wait['actual_argv'])
                and all(type(arg) is str for arg in wait['actual_argv'])
                and type(wait.get('errors')) is list
                and wait.get('safety_contract') == 'mr3-reach-v1',
                'actual wait command/error/safety receipt malformed: ' + name)
        r.parent_check(wait.get('passed') is (wait.get('actual_returncode') == 0
                and not wait.get('errors') and wait.get('source_before') == wait.get('source_after')),
                'outer PASS contradicts its real return/errors/source receipt: ' + name)
        r.parent_check(row.get('returncode') == (0 if wait.get('passed') is True else 1),
                       'wrapper actual return code contradicts its saved receipt: ' + name)
        errors_before_sources = len(r.errors)
        for source in wait['source_after']:
            require(type(source.get('sha256')) is str and len(source['sha256']) == 64
                    and type(source.get('bytes')) is int and source['bytes'] >= 0,
                    'invalid saved phase source proof')
            old = phase_source_proofs.setdefault(source['path'], source)
            r.parent_check(all(old.get(k) == source.get(k) for k in ('path','sha256','bytes')),
                           'source bytes differed between submitted phases: '+source['path'])
        if len(r.errors) != errors_before_sources:
            r.parent_wait_proof_valid = False
        claimed = not row.get('receipt_errors') and row.get('returncode') == 0 and wait.get('passed') is True
        r.parent_check(row.get('passed') is claimed, 'parent phase PASS does not match rc/receipt: ' + name)
        for field in ('wrapper_identity',):
            identity = row.get(field)
            require(type(identity) is dict, 'missing parent wrapper saved identity: ' + name)
            seen = observe(positive(identity['pid']), positive(identity['start_ticks']))
            require(seen['original_identity_gone'], 'phase wrapper remains alive/Z; refuse runtime enumeration')
            required_reaped[positive(identity['pid']), positive(identity['start_ticks'])] = dict(
                pid=positive(identity['pid']), start_ticks=positive(identity['start_ticks']))
        for field in ('coordinator_identity', 'child_identity'):
            identity = wait.get(field)
            require(type(identity) is dict, 'missing outer saved identity: ' + name + '/' + field)
            seen = observe(positive(identity['pid']), positive(identity['start_ticks']))
            require(seen['original_identity_gone'], 'phase child remains alive/Z; refuse runtime enumeration')
            required_reaped[positive(identity['pid']), positive(identity['start_ticks'])] = dict(
                pid=positive(identity['pid']), start_ticks=positive(identity['start_ticks']))
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
    budgets = [('engineering_cumulative', ENTRY + fees['engineering'], CEILING),
               ('engineering_external', external, decimal(resource['external_wall_seconds']))]
    for name, cap in (('preflight', decimal(resource['preflight_wall_seconds'])),
                      ('matrix', decimal(resource['matrix_wall_seconds'])),
                      ('minimum', decimal(resource['minimum_wall_seconds']))):
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
    for path, source in phase_source_proofs.items():
        r.bind(path, source)
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
    membership_stable = metadata_paths() == selected
    r.stable(membership_stable, 'closed metadata membership changed during review')
    absence_path = Path('/tmp') / (PREFIX + '_chain_final_absence.json')
    matrix_submitted = any(row['name'] == 'matrix' for row in rows)
    absence = r.documents.get(str(absence_path))
    if matrix_submitted:
        r.check(type(absence) is dict, 'submitted matrix lacks final external absence report')
    identities, pid_only, unbound = r.finish()
    all_known_gone = bool(identities) and all(row['original_identity_gone'] for row in identities)
    identity_complete = all_known_gone and not r.identity_errors and not unbound
    # A scientifically failed run or an unknown saved identity still needs
    # preservation. With parents actually waited/gone and stable reviewed byte
    # inputs, a separate explicit preservation-only mode can attempt a stable
    # opaque snapshot; it does not claim all writers gone/final quiescence.
    archive_gates = archive_gate_results(r.parent_wait_proof_valid, required_reaped,
        r.bound_inputs_stable, membership_stable, r.errors, identity_complete)
    # Scientific FAIL, ineligibility and SKIPPED are preserved as reported facts,
    # not turned into a metadata inconsistency by demanding scientific PASS.
    return dict(schema='mr3-v60-independent-closed-metadata-review-draft-v2',
        created_utc=datetime.now(timezone.utc).isoformat(), freeze=FREEZE, plan_sha256=plan_sha,
        passed=not r.errors, review_errors=r.errors, activity_passed=summary.get('passed'),
        driver_errors=summary.get('errors'), completed_stages=summary.get('completed_stages'),
        **archive_gates,
        required_reaped_parent_identities=list(required_reaped.values()),
        all_saved_owned_PID_start_identities_fresh_gone=all_known_gone,
        identity_inventory_complete_under_A16_rules=identity_complete,
        saved_identity_count=len(identities), saved_identities=identities,
        operational_history_documents=r.operational_history,
        historical_saved_identity_count=len({(pair['pid'],pair['start_ticks'])
            for document in r.operational_history for pair in document['saved_identity_pairs']}),
        pid_only_occurrences=pid_only, pid_only_distinct_PID_count=len(pid_only),
        pids_without_saved_start=unbound, identity_parse_errors=r.identity_errors,
        relationship_or_observation_PID_fields_retained=r.relationship_pids,
        identity_scope='Owned runtime and the three predeclared launch-lifetime identities only; predeclared prior-closed operational-history identities are preserved in a separate category without current actor or cleanup credit; the two predeclared persistent transport ancestors remain explicitly nonowned and are excluded from absence requirements. Fresh observations for explicit same-object PID/start pairs; no PID-only occurrence is assigned an invented start or a gone verdict. A16 global PID inventory coverage is reported separately.',
        source_count=len(plan['source_bindings']), library_count=len(plan['library_bindings']),
        engineering_entry_seconds=str(ENTRY), engineering_added_parent_union_seconds=str(fees['engineering']),
        engineering_ceiling_seconds=str(CEILING), numeric_user_approval_claimed=False,
        engineering_resource_binding=r.files[str(resource_path)],
        root_actual_tool_wait=r.files[str(ACTUAL_TOOL_WAIT)],
        root_tool_session_id=tool_wait['session_id'],
        root_ownership_scope=r.root_ownership, actuation_profile=ACTUATION_PROFILE,
        root_tool_actual_returncode_observed=tool_wait['actual_returncode_observed'],
        actual_live_ancestor_observation=r.files[str(ancestor_path)],
        engineering_cumulative_seconds=str(ENTRY + fees['engineering']),
        engineering_remaining_seconds=str(CEILING - ENTRY - fees['engineering']),
        pilot_added_parent_union_seconds=str(fees['pilot']), validation_added_parent_union_seconds=str(fees['validation']),
        engineering_external_parent_union_seconds=str(external), resource_violations=r.budget_violations,
        policy_endpoint_gates=endpoints, actual_parent_intervals=rows,
        fee_basis='Complete parent actual-wait interval union per scope. Nested inner intervals and whole driver wall are not added. Gaps remain in policy endpoint gates.',
        metadata_and_source_bindings=list(r.files.values()), selected_metadata_paths=[str(path) for path in selected],
        reported_scientific_and_closure_verdicts=r.reported_verdicts,
        final_absence_reported_passed=absence.get('passed') if type(absence) is dict else None,
        source_before_after_checked=True, bound_inputs_stable=r.bound_inputs_stable,
        metadata_membership_stable=membership_stable, scientific_results_recomputed=False,
        reviewer_implementation=implementation, identity_parser_implementation=identity_parser,
        exact_A16_launch_and_raw_json_extraction=True,
        A16_original_identity_stream_bindings=r.a16_original_inputs,
        A16_identity_bearing_raw_json_inputs=r.encoded_identity_inputs,
        saved_launch_PID_count=len(r.launch_pids),
        A16_canonical_PID_occurrences=r.a16_canonical_pid_occurrences,
        frozen_activity_python_sources=[str(path) for path in frozen_activity_sources],
        scope_limitations=[
            'Actual argv is retained and structurally checked, but is not independently reconstructed per frozen phase; no qualification or scientific argument credit is granted.',
            'This review reconsumes declared JSON, launch.log, ledger.jsonl and embedded identity-bearing raw_json. Other original external-absence console input_bindings are retained as reported facts, not freshly reconsumed here. The byte collector separately hashes every archived original.',
            'Identity completeness is restricted to this declared metadata/launch/ledger extraction domain under A16 rules; no unrecorded-writer absence or whole-plant theorem is inferred.'],
        models_loaded=False, actor_inputs_read=False, raw_telemetry_read=False, signals_sent=0,
        native_runs=0, gpu_calls=0, independent_P2A_scientific_acceptance_inferred=False,
        required_separate_scientific_gate='Full same-freeze 12EP/30roles qualification, actual eligible minimum positive update, pilot real positive update/checkpoint, three final-only strict95/zero-update/same-checkpoint actual completions, original caps and closure; no cross-freeze or driver-PASS shortcut.',
        started_monotonic_ns=started, ended_monotonic_ns=time.monotonic_ns(),
        archive_mode_boundary='Closed archive requires consistent source/metadata and complete saved identity coverage. Preserve-evidence mode may preserve a stable byte snapshot despite original science/closure FAIL or unknown identities, but claims neither final quiescence nor scientific/native closure.',
        draft_execution_note='Prepared statically while activity was live; only the later explicit invocation performs metadata/proc reads.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze', required=True, choices=(FREEZE,))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--actual-tool-wait', type=Path, required=True)
    args = parser.parse_args()
    global ACTUAL_TOOL_WAIT
    ACTUAL_TOOL_WAIT = args.actual_tool_wait
    require(ACTUAL_TOOL_WAIT == ROOT_TOOL/'actual_tool_wait_v1.json',
            'actual tool wait must be the root real-reap receipt outside activity roots')
    require(args.output.parent == Path('/tmp') and args.output.name.startswith('mr3_p2a_v60_'),
            'review output must stay outside activity roots under /tmp/mr3_p2a_v60_*')
    require(not args.output.exists() and not args.output.is_symlink(), 'exclusive review output already exists')
    try:
        result = run()
    except BaseException as error:
        result = dict(schema='mr3-v60-independent-closed-metadata-review-draft-failure-v4',
            freeze=FREEZE, passed=False, closed_archive_eligible=False,
            archive_evidence_preservation_admissible=False, error=repr(error),
            scientific_results_recomputed=False, partial_or_failed_review_preserved=True)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({key: result.get(key) for key in ('passed', 'activity_passed', 'closed_archive_eligible',
        'archive_evidence_preservation_admissible', 'pid_only_distinct_PID_count', 'pids_without_saved_start',
        'saved_identity_count', 'engineering_added_parent_union_seconds', 'review_errors', 'error')}), flush=True)
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
