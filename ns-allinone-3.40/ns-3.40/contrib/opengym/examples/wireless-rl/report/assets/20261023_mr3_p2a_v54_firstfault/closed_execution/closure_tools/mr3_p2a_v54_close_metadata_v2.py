"""Finite V54 closed metadata copy/source/process accounting; no original raw reads."""
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import stat
import subprocess
import time

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A = W / 'report/assets/20261023_mr3_p2a_v54_firstfault'
FREEZE = '1d35dda0d9f1ae8c0fc7a692132fccec29b00282'
OLD = '1fa55bc56d5bb9e230d4b397f962d83b1604b278'
D = Path('/tmp/mr3_p2a_v54_driver_v1')
ENTRY = Decimal('90102.9195132536018')
CEILING = Decimal('120000')


def require(value, message):
    if not value:
        raise ValueError(message)


def read(path):
    path = Path(path)
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode), 'regular file required')
    raw = path.read_bytes()
    after = path.lstat()
    require((before.st_dev, before.st_ino, before.st_mode, before.st_size,
             before.st_mtime_ns, before.st_ctime_ns) ==
            (after.st_dev, after.st_ino, after.st_mode, after.st_size,
             after.st_mtime_ns, after.st_ctime_ns), 'metadata/source changed during read')
    return raw, {'path': str(path), 'bytes': len(raw),
                 'sha256': hashlib.sha256(raw).hexdigest()}


def load(path):
    def unique(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate JSON member')
            result[key] = value
        return result
    raw, binding = read(path)
    return json.loads(raw, object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON'))), binding


def bound(spec):
    raw, actual = read(spec['path'])
    require(actual['bytes'] == spec['bytes'] and actual['sha256'] == spec['sha256'],
            'bound source/ref differs: ' + spec['path'])
    return raw


def same(left, right):
    keys = ('pid', 'parent', 'group', 'session', 'start_ticks')
    require(all(type(left[k]) is int and left[k] > 0 and left[k] == right[k]
                for k in keys), 'saved same-object identities differ')


def gone(saved):
    result = {'saved_identity': saved, 'observed_monotonic_ns': time.monotonic_ns()}
    try:
        raw = Path(f"/proc/{saved['pid']}/stat").read_text()
        end = raw.rfind(')')
        require(end >= 0 and int(raw[:raw.index('(')].strip()) == saved['pid'], 'malformed proc stat')
        fields = raw[end + 2:].split()
        current_start, state = int(fields[19]), fields[0]
        result.update(same_identity_present=current_start == saved['start_ticks'],
                      observed_state=state, observed_start_ticks=current_start)
    except FileNotFoundError:
        result.update(same_identity_present=False, observed_state=None)
    except (OSError, ValueError, IndexError) as error:
        result.update(same_identity_present=None, error=repr(error))
    require(result['same_identity_present'] is False, 'saved identity present (including Z) or unreadable')
    return result


def dump(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')


def main():
    summary, summary_binding = load(D / 'summary.json')
    outer, outer_binding = load(D / 'forensic_actual_wait/actual_wait.json')
    result, result_binding = load('/tmp/mr3_p2a_v54_firstfault_v1.json')
    rootwait, rootwait_binding = load('/tmp/mr3_p2a_v54_actual_tool_wait_v1.json')
    launch, launch_binding = load('/tmp/mr3_p2a_v54_root_launch_v1.json')
    live, live_binding = load('/tmp/mr3_p2a_v54_live_ancestor_observation_v1.json')
    correction, correction_binding = load('/tmp/mr3_p2a_v54_live_argv_field_correction_v1.json')
    entry, _ = load(D / 'entry.json')
    submission, _ = load(D / 'submission.json')
    wrapper, _ = load(D / 'wrapper_identity.json')
    scope, _ = load(A / 'scope_v1.json')
    spec, _ = load(A / 'spec_v1.json')
    require(rootwait['schema'] == 'mr3-v54-root-tool-actual-wait-v1' and
            rootwait['tool_session_id'] == 36067 and rootwait['actual_waited'] is True and
            type(rootwait['actual_returncode_observed']) is int and
            rootwait['actual_returncode_observed'] == (0 if summary['passed'] is True else 1),
            'real root tool wait mismatch')
    bound(rootwait['launch']); bound(rootwait['live_ancestor'])
    require(rootwait['launch'] == launch_binding and rootwait['live_ancestor'] == live_binding,
            'critical root references differ')
    for key in ('original_live_observation', 'original_launch', 'original_driver_summary'):
        bound(correction[key])
    require(correction['schema'] == 'mr3-v54-original-live-argv-field-correction-v1' and
            correction['original_live_observation'] == live_binding and
            correction['original_launch'] == launch_binding and
            correction['original_driver_summary'] == summary_binding and
            correction['original_field_value_preserved'] == live['actual_tool_program_argument'] and
            correction['actual_tool_call_used_launch_absolute_program'] is True and
            correction['actual_launch_equals_driver_argv_after_interpreter_flags'] is True and
            correction['identity_observations_changed_or_reconstructed'] is False and
            correction['actual_tool_program_argument'] == summary['actual_driver_argv'][1],
            'actual auxiliary argv correction is not bound')
    require(summary['execution_freeze'] == result['source_before']['execution_freeze'] ==
            launch['freeze'] == FREEZE and summary['evidence_freeze'] == OLD, 'freeze mismatch')
    require(summary['actual_driver_argv'] == entry['actual_driver_argv'] and
            rootwait['launch_and_actual_program_argument_identical'] is True and
            summary['actual_driver_argv'] == [launch['argv'][0], *launch['argv'][2:]] and
            (W / summary['actual_driver_argv'][1]).resolve() == Path(launch['argv'][2]).resolve() and
            summary['cwd'] == launch['cwd'] == str(W), 'actual launch program/cwd differs')
    require(outer['scope'] == 'engineering' and outer['actual_waited'] is True and
            type(outer['actual_returncode']) is int and
            outer['actual_returncode'] == summary['actual_returncode'] and
            outer['actual_returncode'] == (0 if result['passed'] is True else 1) and
            outer['passed'] is (outer['actual_returncode'] == 0) and outer['errors'] == [] and
            outer['source_unchanged'] is True and outer['source_before'] == outer['source_after'] and
            summary['actual_wrapper_waited'] is True and type(result['passed']) is bool and
            type(summary['passed']) is bool, 'actual outcome/stability not preserved')
    if summary['passed']:
        require(result['passed'] is True and summary['source_before'] == summary['source_after'] and
                summary['errors'] == [] and summary['received_parent_signals'] == [],
                'successful driver metadata is inconsistent')
    require(summary['actual_consumer_argv'] == outer['actual_argv'] == submission['consumer_argv'],
            'actual consumer argv mismatch')
    require(result['source_before'] == result['source_after'], 'consumer sources changed')
    require(read(D / 'forensic_actual_wait/console.log')[1]['sha256'] == outer['console']['sha256'],
            'actual console SHA differs')
    source_checks = []
    for relative, expected in scope['source_bindings'].items():
        raw = bound({'path': str(ROOT / relative), **expected})
        gitraw = subprocess.check_output(['rtk', 'proxy', 'git', 'show', FREEZE + ':' + relative], cwd=ROOT)
        require(raw == gitraw, 'current/Git execution source differs: ' + relative)
        source_checks.append({'path': relative, **expected, 'current_equals_execution_git': True})
    require(len(source_checks) == 14, '14 execution sources required')
    for name in ('scope_v1.json', 'spec_v1.json'):
        path = A / name; raw, binding = read(path)
        require(raw == subprocess.check_output(['rtk', 'proxy', 'git', 'show', FREEZE + ':' + str(path.relative_to(ROOT))], cwd=ROOT), 'config/current/Git mismatch')
    for expected in outer['source_before']:
        raw = bound(expected)
        require(raw == subprocess.check_output(['rtk', 'proxy', 'git', 'show', FREEZE + ':' + str(Path(expected['path']).relative_to(ROOT))], cwd=ROOT), 'outer source/current/Git mismatch')
    old_checks = []
    for relative, expected in spec['interpretation_sources'].items():
        raw = bound({'path': str(ROOT / relative), **expected})
        require(raw == subprocess.check_output(['rtk', 'proxy', 'git', 'show', OLD + ':' + relative], cwd=ROOT), 'old interpretation source changed')
        old_checks.append({'path': relative, **expected, 'current_equals_evidence_git': True})
    require(len(old_checks) == 7, 'seven old interpretation sources required')
    same(summary['driver_identity'], entry['driver_identity'])
    same(summary['driver_identity'], live['saved_driver_identity'])
    same(summary['driver_identity'], live['live_driver_identity'])
    same(summary['wrapper_identity'], wrapper)
    same(summary['wrapper_identity'], outer['coordinator_identity'])
    same(summary['consumer_identity'], outer['child_identity'])
    same(summary['consumer_identity'], result['identity'])
    ancestor = live['actually_observed_tool_ancestor']
    require(live['relationship_confirmed_while_alive'] is True and
            live['no_missing_start_reconstruction'] is True and
            live['tool_session_id'] == 36067 and
            summary['driver_identity']['parent'] == ancestor['pid'] and
            summary['driver_identity']['group'] == ancestor['group'] and
            summary['driver_identity']['session'] == ancestor['session'], 'actual live ancestry not bound')
    observations = [gone(identity) for identity in
                    (summary['driver_identity'], summary['wrapper_identity'], summary['consumer_identity'], ancestor)]
    start, end = summary['started_monotonic_ns'], summary['ended_monotonic_ns']
    require(type(start) is int and type(end) is int and 0 < start < end <= time.monotonic_ns(), 'bad parent interval')
    fee = Decimal(end - start) / 10**9
    require(fee == Decimal(summary['actual_parent_wait_seconds']) == Decimal(summary['engineering_added_seconds']) and
            Decimal(summary['engineering_used_at_entry_seconds']) == ENTRY and
            Decimal(summary['engineering_ceiling_seconds']) == CEILING and
            Decimal(summary['engineering_cumulative_used_seconds']) == ENTRY + fee and
            Decimal(summary['engineering_remaining_seconds']) == CEILING - ENTRY - fee and
            summary['parent_fee_cap_seconds'] == '600' and
            start <= outer['started_monotonic_ns'] < outer['ended_monotonic_ns'] <= end,
            'actual parent fee/carry or nested containment differs')
    if summary['passed']:
        require(fee <= Decimal('600'), 'successful driver exceeds parent fee cap')
    reports = {r['input']: r for r in result['input_reports']}
    require(set(reports) == {'motion', 'startup'}, 'fixed input-report membership differs')
    for name, report in reports.items():
        require(type(report['whole_input_read']) is bool and
                type(report['parse_and_binding_complete']) is bool and
                report['stat_before'] == report['stat_after'], 'input metadata stability differs')
        if report['whole_input_read']:
            require(report['bytes_read'] == spec['inputs'][name]['bytes'] and
                    report['whole_input_sha256'] == spec['inputs'][name]['sha256'],
                    'complete input metadata SHA/size differs')
        else:
            require(report['whole_input_sha256'] is None, 'partial input must not claim full SHA')
        if report['parse_and_binding_complete']:
            require(report['whole_input_read'] is True and report['errors'] == [] and
                    report['error_count'] == 0, 'complete parse metadata differs')
    if result['passed']:
        require(all(report['parse_and_binding_complete'] for report in reports.values()) and
                result['errors'] == [] and result['within_work_limit'] is True and
                result['selection_complete_for_declared_rule'] is True and
                result['selection_dropped'] == 0,
                'successful result lacks complete producer receipt fields')
    closed = A / 'closed_execution'; closed.mkdir(exist_ok=False)
    originals = sorted(p for p in D.rglob('*') if p.is_file())
    require(len(originals) == 7, 'unexpected driver prefix membership')
    originals += [Path('/tmp/mr3_p2a_v54_firstfault_v1.json'), Path('/tmp/mr3_p2a_v54_actual_tool_wait_v1.json'),
                  Path('/tmp/mr3_p2a_v54_root_launch_v1.json'), Path('/tmp/mr3_p2a_v54_live_ancestor_observation_v1.json'),
                  Path('/tmp/mr3_p2a_v54_live_argv_field_correction_v1.json'), Path(__file__)]
    entries = []
    for original in originals:
        raw, original_binding = read(original)
        destination = closed / ('tmp/' + str(original.relative_to('/tmp')) if original.is_relative_to(D) else 'closure_tools/' + original.name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open('xb') as stream:
            stream.write(raw)
        require(read(destination)[0] == raw, 'canonical copy differs')
        entries.append({'original': str(original), 'canonical': str(destination.relative_to(A)),
                        'bytes': len(raw), 'sha256': original_binding['sha256'], 'codec': 'unchanged-bytes'})
    inventory = {'schema': 'mr3-v54-closed-metadata-byte-inventory-v1', 'passed': True,
                 'activity_passed': summary['passed'], 'evidence_freeze': OLD, 'execution_freeze': FREEZE,
                 'files': len(entries), 'original_bytes': sum(r['bytes'] for r in entries),
                 'canonical_bytes': sum(r['bytes'] for r in entries), 'links': [], 'link_count': 0,
                 'two_original_raw_inputs_read_or_copied': False, 'scientific_results_recomputed': False,
                 'all_saved_identities_fresh_gone': True, 'entries': entries}
    dump(A / 'closed_inventory_v1.json', inventory)
    review = {'schema': 'mr3-v54-closed-metadata-review-v1', 'passed': True, 'activity_passed': summary['passed'],
              'scope': 'Small closed metadata/source/current-Git/proc verification only; no original raw read or consumer rerun.',
              'actual_root_tool_session_id': 36067, 'actual_root_returncode_observed': rootwait['actual_returncode_observed'],
              'root_actual_wait': rootwait_binding, 'driver_summary': summary_binding,
              'original_live_argv_field_correction': correction_binding,
              'outer_actual_wait': outer_binding, 'forensic_result': result_binding,
              'evidence_freeze': OLD, 'execution_freeze': FREEZE,
              'source_before_after_scope': 'Outer 17 bindings and consumer source dictionaries are stable; original driver after/errors/pending fields remain untouched.',
              'execution_source_checks': source_checks, 'config_and_inventory_current_equal_execution_Git': True,
              'evidence_source_checks': old_checks, 'saved_identity_count': len(observations),
              'saved_identity_observations': observations, 'all_saved_identities_fresh_gone': True,
              'same_object_identity_binding_and_live_ancestor_confirmed': True,
              'actual_driver_program_from_entry_summary': summary['actual_driver_argv'][1],
              'launch_program_matches_complete_actual_driver_argv': True,
              'original_live_observation_program_argument_field': live.get('actual_tool_program_argument'),
              'original_live_observation_auxiliary_program_field_matches_actual_program': live.get('actual_tool_program_argument') == summary['actual_driver_argv'][1],
              'auxiliary_observation_field_never_used_as_program_or_identity_proof': True,
              'engineering_added_parent_wall_seconds': str(fee), 'nested_child_wall_seconds_not_added': outer['actual_child_wait_seconds'],
              'engineering_cumulative_seconds': str(ENTRY + fee), 'engineering_remaining_seconds': str(CEILING - ENTRY - fee),
              'within_parent_fee_cap': fee <= Decimal('600'),
              'first_runtime_fault_status': result['first_runtime_fault_status'],
              'full_motion_hash_claimed': reports['motion']['whole_input_read'],
              'reported_input_completeness': result['input_reports'],
              'reported_first_runtime_fault': result['first_runtime_fault'],
              'reported_first_failure_callback_status': result['first_failure_callback_status'],
              'reported_first_failure_callback': result['first_failure_callback'],
              'reported_selection_complete': result['selection_complete_for_declared_rule'],
              'descriptive_facts_not_independently_recomputed': True,
              'raw_inputs_copied_or_reread': False, 'worlds': 0, 'models_loaded': False,
              'scientific_qualification_credit': False, 'closed_inventory': read(A / 'closed_inventory_v1.json')[1]}
    dump(A / 'checks/closed_metadata_review_v1.json', review)
    print(json.dumps({'passed': True, 'activity_passed': summary['passed'], 'files': len(entries),
                      'saved_identity_count': len(observations), 'engineering_added_parent_wall_seconds': str(fee)}))


if __name__ == '__main__':
    main()
