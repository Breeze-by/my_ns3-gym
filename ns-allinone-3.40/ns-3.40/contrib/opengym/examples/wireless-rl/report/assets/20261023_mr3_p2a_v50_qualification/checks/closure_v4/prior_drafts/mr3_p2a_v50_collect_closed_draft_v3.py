#!/usr/bin/python3
"""DRAFT v3: post-reap V50 opaque archival with explicit preservation mode.

Requires the separate completed metadata/proc review. Do not run while live.
The unchanged V45 byte copier hashes all original bytes, creates deterministic
gzip for text streams, and re-decodes each new wrapper to verify original SHA.
Already-compressed inputs/checkpoints are copied as original bytes, not loaded.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import time

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
ROS = ROOT / 'ros2_ws/ros2-multi-robot-automap'
A = W / 'report/assets/20261023_mr3_p2a_v50_qualification'
PREFIX = 'mr3_p2a_reach_v50'
FREEZE = '23e909380b470039bd5680cf2d07710dca71097e'
LEGACY = W / 'report/assets/20261022_mr3_p2a_v45_preparation_classification/collect_closed_v1.py'
LEGACY_SHA = '63d52ce389b7d61fa67f5080fa556b1f32e47b79e389800f9de55e97c40abf06'
NATIVE = ROS / 'log/mr3_p2a_reach_v50'
POLICY = ROS / 'log/mr3_ppo_reach_v50'
DEST = A / 'closed_execution'
INVENTORY = A / 'closed_inventory_v1.json'
FAILED = A / 'closed_inventory_v1.failed.json'
EXCLUDED = frozenset(('execution_inputs', 'inputs', 'observation_archive',
    'navigation_archive', 'map_blobs', 'costmap_blobs', '__pycache__'))


def file_state(path):
    value = path.lstat()
    return [value.st_dev, value.st_ino, value.st_mode, value.st_size,
            value.st_mtime_ns, value.st_ctime_ns]


def helper():
    raw = LEGACY.read_bytes()
    if hashlib.sha256(raw).hexdigest() != LEGACY_SHA:
        raise ValueError('immutable V45 byte copier/verifier differs')
    spec = importlib.util.spec_from_file_location('_v50_unchanged_closed_byte_copier', LEGACY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.A, module.DEST = A, DEST
    return module


def discover(m, tools):
    roots = [(path, 'tmp', Path(path.name)) for path in sorted(Path('/tmp').glob(PREFIX + '*'))]
    roots += [(NATIVE, 'native', Path()), (POLICY, 'policy', Path())]
    roots += [(path, 'closure_tools', Path(path.name)) for path in tools]
    selected, links, directories, missing = {}, {}, {}, []

    def link(source, label, relative):
        before = m.stamp(source.lstat())
        target = os.readlink(source)
        m.require(m.stamp(source.lstat()) == before, 'symlink changed while recording')
        lexical = Path(os.path.abspath(os.path.join(source.parent, target)))
        inside = lexical.is_relative_to(NATIVE) or lexical.is_relative_to(POLICY) or (
            lexical.is_relative_to('/tmp') and len(lexical.parts) >= 3 and lexical.parts[2].startswith(PREFIX))
        return dict(original=str(source), canonical_link_name=str((DEST / label / relative).relative_to(A)),
            target_text=target, lexical_target_without_dereference=str(lexical),
            target_scope='known-source-roots' if inside else 'outside-known-source-roots',
            target_followed=False, link_stat=before)

    for root, label, relative in roots:
        if not root.exists() and not root.is_symlink():
            missing.append(str(root))
            continue
        mode = root.lstat().st_mode
        if stat.S_ISLNK(mode):
            links[str(root)] = link(root, label, relative)
            continue
        m.require(stat.S_ISDIR(mode) or stat.S_ISREG(mode), 'special source root: ' + str(root))
        paths = [(root, relative)] if stat.S_ISREG(mode) else []
        if stat.S_ISDIR(mode):
            for parent, names, files in os.walk(root, followlinks=False):
                parent = Path(parent)
                directories[str(parent)] = m.stamp(parent.lstat())
                names.sort(); files.sort()
                for name in list(names):
                    child = parent / name
                    suffix = relative / child.relative_to(root)
                    if child.is_symlink():
                        links[str(child)] = link(child, label, suffix)
                        names.remove(name)
                    else:
                        m.require(stat.S_ISDIR(child.lstat().st_mode), 'special source directory: ' + str(child))
                for name in files:
                    child = parent / name
                    suffix = relative / child.relative_to(root)
                    if child.is_symlink():
                        links[str(child)] = link(child, label, suffix)
                    else:
                        paths.append((child, suffix))
        for source, suffix in paths:
            before = m.regular_stamp(source)
            target, compressed = m.target_for(label, suffix, source)
            m.require(source not in selected, 'duplicate original source')
            selected[source] = dict(target=target, compressed=compressed, stat=before)
    targets = [str(row['target']) for row in selected.values()]
    targets += [str(A / row['canonical_link_name']) for row in links.values()]
    m.require(selected and len(set(targets)) == len(targets), 'empty/colliding canonical archive')
    target_set = set(targets)
    m.require(not any(str(parent) in target_set for name in targets for parent in Path(name).parents
                      if parent != DEST), 'canonical file/link collides with target parent')
    return selected, links, directories, missing


def current_identity(identity):
    pid, start = identity['pid'], identity['start_ticks']
    now = time.monotonic_ns()
    try:
        tail = (Path('/proc') / str(pid) / 'stat').read_text().rsplit(')', 1)[1].split()
        if len(tail) < 20:
            raise ValueError('malformed /proc identity')
        current = int(tail[19])
        return dict(pid=pid, start_ticks=start, current_start_ticks=current, state=tail[0],
            observed_monotonic_ns=now, original_identity_gone=current != start,
            observation='same_pid_different_start' if current != start else 'present_including_Z')
    except (FileNotFoundError, ProcessLookupError):
        return dict(pid=pid, start_ticks=start, observed_monotonic_ns=now,
            original_identity_gone=True, observation='absent_proc_stat')
    except (OSError, ValueError, IndexError) as error:
        return dict(pid=pid, start_ticks=start, observed_monotonic_ns=now,
            original_identity_gone=False, observation='unreadable_saved_identity', error=repr(error))


def current_pid_only(row):
    now, pid = time.monotonic_ns(), row['pid']
    try:
        tail = (Path('/proc') / str(pid) / 'stat').read_text().rsplit(')', 1)[1].split()
        if len(tail) < 20:
            raise ValueError('malformed /proc PID-only observation')
        return dict(pid=pid, observed_monotonic_ns=now, current_start_ticks=int(tail[19]),
            state=tail[0], original_identity_status='unknown',
            observation='PID_present_original_start_unknown', no_original_start_reconstructed=True)
    except (FileNotFoundError, ProcessLookupError):
        return dict(pid=pid, observed_monotonic_ns=now, original_identity_status='unknown',
            observation='PID_absent_at_lookup_original_start_still_unknown', no_original_start_reconstructed=True)
    except (OSError, ValueError, IndexError) as error:
        return dict(pid=pid, observed_monotonic_ns=now, original_identity_status='unknown',
            observation='unreadable_PID_original_start_unknown', error=repr(error), no_original_start_reconstructed=True)


def closed_review(m, path, mode):
    review, proof = m.metadata(path)
    m.require(review.get('schema') == 'mr3-v50-independent-closed-metadata-review-draft-v3'
        and review.get('freeze') == FREEZE
        and review.get('parent_wait_proof_valid') is True
        and review.get('parent_coordinators_actual_waited_and_fresh_gone') is True
        and review.get('exact_A16_launch_and_raw_json_extraction') is True
        and review.get('bound_inputs_stable') is True and review.get('metadata_membership_stable') is True,
        'matching completed parent-wait and stable metadata review required')
    parents = review.get('required_reaped_parent_identities')
    m.require(type(parents) is list and parents, 'missing actually waited parent identities')
    for row in parents:
        m.require_absent(row)
    if mode == 'closed':
        m.require(review.get('closed_archive_eligible') is True and review.get('passed') is True
            and review.get('review_errors') == []
            and review.get('identity_inventory_complete_under_A16_rules') is True
            and review.get('pids_without_saved_start') == [] and review.get('identity_parse_errors') == [],
            'closed mode requires complete saved-identity inventory; use an explicitly labelled preservation snapshot for original FAIL/unknown')
    else:
        m.require(review.get('archive_evidence_preservation_admissible') is True,
            'preservation mode still requires real parent reap and stable reviewed metadata bytes')
    rows = review.get('saved_identities')
    m.require(type(rows) is list and len(rows) == review.get('saved_identity_count') and rows,
              'independent saved identity inventory is empty/inconsistent')
    m.require(len({(row['pid'], row['start_ticks']) for row in rows}) == len(rows),
              'duplicate saved identity inventory')
    fresh = []
    for row in rows:
        m.require(all(type(row.get(key)) is int and row[key] > 0 for key in ('pid', 'start_ticks')),
                  'invalid saved PID/start identity')
        observed = current_identity(row)
        fresh.append(observed)
        if mode == 'closed':
            m.require(row.get('original_identity_gone') is True and observed['original_identity_gone'],
                      'saved process is present/unknown, including Z; not a closed archive')
    unknown_fresh = [current_pid_only(row) for row in review.get('pid_only_occurrences', [])]
    # Ensure the source and closed metadata bytes reviewed remain the same now.
    for item in review['metadata_and_source_bindings']:
        source = Path(item['path'])
        m.require(str(source.resolve(strict=True)) == item['resolved_path'], 'reviewed target changed: ' + str(source))
        link_before = file_state(source)
        target = source.resolve(strict=True)
        target_before = file_state(target)
        m.require(link_before == item['link_stat'] and target_before == item['target_stat'],
                  'reviewed file/link stat changed: ' + str(source))
        with source.open('rb') as stream:
            sha, count = m.digest_stream(stream)
        m.require(sha == item['sha256'] and count == item['bytes'], 'reviewed bytes changed: ' + str(source))
        link_after = file_state(source)
        target_after = file_state(target)
        m.require(link_after == link_before and target_after == target_before,
                  'reviewed file changed while hashing: ' + str(source))
    return review, proof, dict(saved_pair_observations=fresh, PID_only_observations=unknown_fresh,
        PID_only_pair_reconstruction_performed=False,
        all_explicit_saved_pair_identities_gone=all(row['original_identity_gone'] for row in fresh),
        complete_identity_inventory_under_A16_rules=review['identity_inventory_complete_under_A16_rules'],
        original_review_errors_preserved=review['review_errors'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze', required=True, choices=(FREEZE,))
    parser.add_argument('--closed-review', required=True, type=Path)
    parser.add_argument('--mode', required=True, choices=('closed', 'preserve-evidence'))
    args = parser.parse_args()
    m = helper()
    m.require(not any(path.exists() or path.is_symlink() for path in (DEST, INVENTORY, FAILED)),
              'exclusive inventory/archive/previous failure exists; preserve it')
    entries, current = [], None
    try:
        review, proof, observations_before = closed_review(m, args.closed_review, args.mode)
        tools = list(dict.fromkeys((Path(__file__).resolve(), args.closed_review.resolve(strict=True),
            Path(review['reviewer_implementation']['path']))))
        m.require(all(path.parent == Path('/tmp') and path.name.startswith('mr3_p2a_v50_') for path in tools),
                  'closure-only tools must stay outside the activity prefix')
        before = discover(m, tools)
        selected, links, directories, missing = before
        selected_metadata = sorted(str(source) for source in selected
            if (source.suffix == '.json' or source.name in ('launch.log', 'ledger.jsonl'))
            and not EXCLUDED.intersection(source.parts) and source not in tools)
        m.require(selected_metadata == review['selected_metadata_paths'],
                  'closed process/report JSON membership changed since the independent review')
        DEST.mkdir(exist_ok=False)
        for source, row in sorted(selected.items()):
            current = str(row['target'])
            entries.append(m.archive(source, row))
        m.require(discover(m, tools) == before, 'closed membership/stat changed during entire archive')
        after_review, after_proof, observations_after = closed_review(m, args.closed_review, args.mode)
        m.require(after_review == review and after_proof == proof, 'review changed during archive')
        value = dict(schema='mr3-v50-closed-byte-archive-draft-v3', freeze=FREEZE,
            purpose='Post-wait opaque lossless byte archive; preserve all actual PASS/FAIL/SKIPPED outcomes.',
            archive_mode=args.mode,
            byte_archive_complete=True, scientific_results_recomputed=False, fees_recomputed=False,
            models_loaded=False, original_activity_passed=review['activity_passed'],
            P2A_scientific_acceptance_inferred=False, closure_metadata=proof,
            original_scientific_or_closure_FAIL_rejudged=False,
            identity_observations_before=observations_before, identity_observations_after=observations_after,
            original_PID_only_unknown_occurrences_preserved=review.get('pid_only_occurrences', []),
            original_identity_parse_errors_preserved=review.get('identity_parse_errors', []),
            closed_saved_identity_inventory_claimed=args.mode == 'closed',
            unrecorded_writer_absence_claimed=False, final_quiescence_claimed=False,
            preservation_boundary='preserve-evidence validates a stable byte snapshot only; original missing starts/present or unreadable saved identities/closure failures remain unresolved. No original start is inferred from current /proc or another object.',
            unchanged_archive_implementation=dict(path=str(LEGACY), sha256=LEGACY_SHA),
            roots=dict(tmp_prefix='/tmp/' + PREFIX + '*', native=str(NATIVE), policy=str(POLICY)),
            closure_only_tools=[str(path) for path in tools],
            source_binding_scope='Independent closed review contains current/Git/plan sources, ELF bytes and complete parent metadata hashes.',
            missing_optional_roots=missing, coverage='All regular files plus symlink metadata; no link targets followed.',
            links=[links[name] for name in sorted(links)], link_count=len(links),
            external_link_targets_not_followed=[row for row in links.values()
                if row['target_scope'] == 'outside-known-source-roots'],
            files=len(entries), original_bytes=sum(row['original_bytes'] for row in entries),
            canonical_bytes=sum(row['canonical_bytes'] for row in entries), entries=entries)
        m.write_json(INVENTORY, value)
        print(json.dumps({key: value[key] for key in ('byte_archive_complete', 'files',
            'original_bytes', 'canonical_bytes', 'link_count')}), flush=True)
        return 0
    except BaseException as error:
        m.write_json(FAILED, dict(schema='mr3-v50-closed-byte-archive-failure-draft-v3',
            freeze=FREEZE, error=repr(error), byte_archive_complete=False,
            archive_mode=args.mode,
            last_attempted_target=current, completed_entries=entries,
            originals_deleted=False, partial_outputs_preserved=True,
            scientific_results_recomputed=False, fees_recomputed=False))
        raise


if __name__ == '__main__':
    raise SystemExit(main())
