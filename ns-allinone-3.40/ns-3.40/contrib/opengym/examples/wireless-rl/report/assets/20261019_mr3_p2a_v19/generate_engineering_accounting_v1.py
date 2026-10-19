"""Reproduce the V19 closed-end Decimal ledger from original waited evidence.

Packaging/JSON/byte checks and supplementary saved PID/start lookups only.
No scientific reader, simulator, GPU, policy, or source-readiness check runs.
The resulting balance is the V19 closing point, not the later global balance.
"""
import argparse
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import time

A = Path(__file__).resolve().parent
B = A / 'closed_execution/auxiliary_closure_v1'
BASELINE = Decimal('32673.5464309836018')
CEILING = Decimal('52000')
FREEZE = '3631c788ca46e03a52f34ad48c41611761c17f1e'
ARCHIVE_SHA = '82d7fb728e5d948af29b01c95e877ff6fc3cf7ca4696442b215662e7282a6ff7'


def require(value, message):
    if not value:
        raise ValueError(message)


def read(path):
    return json.loads(path.read_text())


def fingerprint(path):
    before = path.stat()
    digest, size = hashlib.sha256(), 0
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
            size += len(block)
    after = path.stat()
    fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
    values = [getattr(before, key) for key in fields]
    require(values == [getattr(after, key) for key in fields] and size == before.st_size,
            'input changed while hashing: ' + str(path))
    return {'path': str(path), 'bytes': size, 'sha256': digest.hexdigest(), 'stat': values}


def argv():
    raw = Path('/proc/self/cmdline').read_bytes()
    require(raw.endswith(b'\0') and raw[:-1], 'actual argv is empty/not NUL terminated')
    parts = raw[:-1].split(b'\0')
    require(all(parts), 'actual argv has an empty argument')
    return [os.fsdecode(part) for part in parts]


def lookup(pid, saved_start):
    require(type(pid) is int and pid > 0 and type(saved_start) is int and saved_start > 0,
            'supplementary saved PID/start identity is malformed')
    result = {'pid': pid, 'start_ticks': saved_start, 'observed_monotonic_ns': time.monotonic_ns()}
    try:
        raw = (Path('/proc') / str(pid) / 'stat').read_text()
        tail = raw.rsplit(')', 1)[1].split()
        result.update(current_start_ticks=int(tail[19]), state=tail[0])
        result['saved_identity_present'] = result['current_start_ticks'] == saved_start
        result['observation'] = 'same_identity_present_including_Z' if result['saved_identity_present'] else 'PID_reused_different_identity'
    except (FileNotFoundError, ProcessLookupError):
        result.update(saved_identity_present=False, observation='proc_stat_absent')
    except (OSError, ValueError, IndexError) as error:
        result.update(saved_identity_present=None, observation='unreadable', error=repr(error))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    require(args.output.is_absolute() and not args.output.exists(), 'exclusive absolute output required')
    started = time.monotonic_ns()
    inputs, bindings = {}, {}
    result = {'schema': 'mr3-p2a-v19-closed-engineering-accounting-v1',
              'scope': 'V19 closed-end native/external fee ledger and packaging proof; not current global accounting',
              'passed': False, 'scientific_pass_claimed': False, 'native_admission': False,
              'actual_argv': argv(), 'started_monotonic_ns': started, 'errors': [],
              'generator_claims_own_absence': False, 'generator_signals_sent': 0}

    def document(path):
        path = Path(path)
        if str(path) not in bindings:
            bindings[str(path)] = fingerprint(path)
        value = read(path)
        inputs[str(path)] = value
        return value

    def waited(path, expected_code):
        value = document(path)
        require(value.get('schema') == 'mr3-reach-outer-actual-wait-v1'
                and value.get('actual_waited') is True and value.get('actual_returncode') == expected_code
                and value.get('source_unchanged') is True and value.get('errors') == [],
                'original actual wait boundary differs: ' + str(path))
        start, end = value['started_monotonic_ns'], value['ended_monotonic_ns']
        require(type(start) is int and type(end) is int and end >= start, 'invalid original actual wait interval')
        fee = Decimal(end - start) / Decimal(10**9)
        require(fee == Decimal(value['actual_child_wait_seconds']), 'original ns/Decimal fee differs')
        return value, fee

    try:
        bindings[str(Path(__file__).resolve())] = fingerprint(Path(__file__).resolve())
        index = document(B / 'copy_index_v1.json')
        require(index['passed'] is True and index['file_count'] == 51
                and index['regular_file_bytes'] == 5321305, 'canonical auxiliary copy inventory differs')
        for row in index['copies']:
            for key in ('origin', 'copy'):
                path = Path(row[key])
                proof = fingerprint(path)
                require((proof['bytes'], proof['sha256']) == (row['bytes'], row['sha256']),
                        'original/canonical copy bytes differ: ' + str(path))
                bindings[str(path)] = proof
        result['canonical_copy_proof'] = {'index': str(B / 'copy_index_v1.json'),
            'file_count': 51, 'regular_file_bytes': 5321305, 'all_origin_copy_bytes_sha_equal': True}
        matrix, m = waited(B / 'matrix_outer/actual_wait.json', 1)
        control, c = waited(B / 'operator_interrupt/outer/actual_wait.json', 0)
        first, a1 = waited(B / 'absence_v1/outer/actual_wait.json', 1)
        second, a2 = waited(B / 'absence_v2/outer/actual_wait.json', 0)
        require((m, c, a1, a2) == tuple(map(Decimal,
            ('3809.076356086', '0.268437067', '0.365218825', '0.376774231'))), 'V19 expected original fees differ')
        require(matrix['started_monotonic_ns'] <= control['started_monotonic_ns']
                <= control['ended_monotonic_ns'] <= matrix['ended_monotonic_ns'],
                'operator interval is not fully contained in matrix')
        intervention = document(B / 'operator_interrupt/evidence/intervention.json')
        require(intervention['signal_sent'] is True and intervention['signal_name'] == 'SIGINT'
                and control['started_monotonic_ns'] <= intervention['signal_monotonic_ns'] <= control['ended_monotonic_ns'],
                'recorded external SIGINT is not in its actual waited interval')
        summary = document(B / 'matrix/summary.json')
        require(summary['freeze'] == FREEZE and summary['passed'] is False
                and summary['all_submitted_children_waited'] is True, 'original failed matrix boundary differs')
        stage = summary['stages'][0]
        require(stage['stage'] == 'interface' and stage['status'] == 'FAIL'
                and Decimal(stage['wall_seconds']) == Decimal('3790.370777463')
                and Decimal(stage['wall_seconds']) > Decimal('2400')
                and stage['within_stage_wall_allocation'] is False, 'original stage deadline failure differs')
        good = ('input_001', 'angular', 'physics', 'full', 'runtime', 'cadence')
        require(all(stage['audits'][name]['returncode'] == 0 and stage['audits'][name]['passed'] is True
                    for name in good), 'six observed closed science commands differ')
        information = stage['audits']['information']
        require(information['returncode'] == -2 and information['passed'] is False
                and 'declared result missing' in information['errors'], 'original interrupted reader failure differs')
        require([item['stage'] for item in summary['stages'][1:]] == ['terminal', 'reset', 'deadline']
                and all(item['status'] == 'SKIPPED' for item in summary['stages'][1:]), 'later stages were not skipped')
        require([item['id'] for item in stage['skipped_audits']] == ['fifo_001', 'peer_control', 'fifo_manifest', 'closure'],
                'original pending jobs differ')
        failed_absence = document(B / 'absence_v1/result.json')
        absence = document(B / 'absence_v2/result.json')
        require(failed_absence['passed'] is False and failed_absence['errors'], 'v1 absence FAIL was not retained')
        require(absence['passed'] is True and absence['identity_count'] == 58
                and absence['present'] == absence['unreadable'] == absence['pids_without_saved_start'] == absence['errors'] == [],
                'original v2 prior-identity absence proof differs')
        prelaunch = document(A / 'closed_execution/absence_v2_prelaunch_failure_v1.json')
        require(prelaunch['original_tool_response']['exit_code'] == 1
                and Decimal(str(prelaunch['original_tool_response']['wall_time_seconds'])) == Decimal('0.048720286')
                and prelaunch['helper_spawned'] is False and prelaunch['actual_child_wait_receipt_created'] is False
                and prelaunch['empty_output_directory_observation']['entries'] == [], 'prelaunch failure provenance differs')
        archive = document(A / 'closed_execution/native_archive/manifest.json')
        require(archive['passed'] is True and archive['source_unchanged'] is True and archive['errors'] == []
                and archive['source_inventory_before'] == archive['source_inventory_after']
                and archive['source_inventory_before']['regular_file_count'] == 514
                and archive['source_inventory_before']['regular_file_bytes'] == 1038191041
                and archive['readback']['member_count'] == 514
                and archive['readback']['all_member_bytes_and_sha_equal'] is True
                and archive['readback']['ordered_part_concatenation_equal'] is True,
                'original complete archive/readback proof differs')
        require(len(archive['ordered_parts']) == 1 and archive['logical_tar_xz'] ==
                {'bytes': 32677904, 'sha256': ARCHIVE_SHA}, 'archive logical identity differs')
        part = archive['ordered_parts'][0]
        require(part['ordinal'] == 1 and part['bytes'] == 32677904 and part['sha256'] == ARCHIVE_SHA,
                'archive ordered shard identity differs')
        part_path = A / 'closed_execution/native_archive' / part['relative_path']
        bindings[str(part_path)] = fingerprint(part_path)
        require((bindings[str(part_path)]['bytes'], bindings[str(part_path)]['sha256']) == (32677904, ARCHIVE_SHA),
                'canonical archive shard bytes differ')
        preflight, _ = waited(B / 'preflight_outer/actual_wait.json', 0)
        result['actual_child_commands'] = {name: value['actual_argv'] for name, value in
            (('preflight', preflight), ('matrix', matrix), ('operator', control), ('absence_v1', first), ('absence_v2', second))}
        result['actual_native_command'] = stage['native']['argv']
        result['actual_archive_command'] = archive['actual_argv']
        result['unknown_outer_full_argv_reconstructed'] = False
        charge = m + a1 + a2
        used, remaining = BASELINE + charge, CEILING - BASELINE - charge
        require(charge == Decimal('3809.818349142') and used == Decimal('36483.3647801256018')
                and remaining == Decimal('15516.6352198743982'), 'V19 closed-end Decimal conservation differs')
        result['accounting'] = {'baseline_used_seconds': str(BASELINE), 'approved_ceiling_seconds': str(CEILING),
            'matrix_seconds': str(m), 'absence_v1_seconds': str(a1), 'absence_v2_seconds': str(a2),
            'operator_seconds_observed': str(c), 'operator_interval_contained_in_matrix': True,
            'operator_additional_charge_seconds': '0', 'v19_charge_seconds': str(charge),
            'v19_closed_end_cumulative_used_seconds': str(used), 'v19_closed_end_remaining_seconds': str(remaining),
            'formula': 'baseline + M + A1 + A2; C is contained in M; exact original outer ns differences/Decimal',
            'prelaunch_toolwall_seconds_observed_only': '0.048720286', 'prelaunch_actual_child_wait_seconds': None,
            'prelaunch_no_child_wait_fee_invented': True,
            'not_charged_by_this_formula': 'finite preparation/packaging CPU; sibling/native/watcher/consumer walls overlap M; toolwall is not added'}
        result['native_outcome'] = {'matrix_passed': False, 'interface_seconds': stage['wall_seconds'],
            'nominal_interface_cap_seconds': '2400', 'effective_interface_cap_seconds': stage['effective_stage_wall_cap_seconds'],
            'native_returncode': stage['native']['returncode'], 'native_seconds': stage['native']['wall_seconds'],
            'six_actual_passed_command_ids': list(good), 'information_returncode': -2,
            'information_seconds': information['wall_seconds'], 'information_result_missing': True,
            'later_stages_skipped': ['terminal', 'reset', 'deadline'],
            'pending_audit_jobs_skipped': ['fifo_001', 'peer_control', 'fifo_manifest', 'closure'],
            'coordinator_recorded_signals_sent': summary['signals_sent'], 'recorded_external_SIGINT_count': 1,
            'global_zero_signals_claimed': False}
        extra = {}
        for name, value in (('absence_v1', first), ('absence_v2', second)):
            for key in ('child_identity', 'coordinator_identity'):
                saved = value[key]
                pair = saved['pid'], saved['start_ticks']
                extra.setdefault(pair, []).append(name + '.' + key)
        observations = [dict(lookup(pid, start), references=refs) for (pid, start), refs in sorted(extra.items())]
        present = [row for row in observations if row['saved_identity_present'] is True]
        unreadable = [row for row in observations if row['saved_identity_present'] is None]
        result['supplementary_absence'] = {'scope': 'Only the four saved A1/A2 helper/outer identities at these lookup times; not this generator or unrecorded processes',
            'identity_count': len(extra), 'observations': observations, 'present': present, 'unreadable': unreadable,
            'all_four_saved_identities_absent': len(extra) == 4 and not present and not unreadable,
            'original_v2_prior_identity_count': 58, 'original_v2_scope_is_not_relabelled': True,
            'matching_start_Z_is_present': True}
        require(len(extra) == 4 and not present and not unreadable, 'supplementary saved helper/outer identity is present/unreadable')
        result['policy_scope'] = {'qualification_started': False, 'ppo_started': False,
            'gpu_calls': summary['gpu_calls'], 'optimizer_updates': summary['optimizer_steps'],
            'pilot_started': False, 'validation_started': False, 'pilot_budget_changed': False,
            'pilot_remaining_decisions': 1870, 'pilot_remaining_wall_seconds': '2905.9547395464029',
            'final_only_development_validations_remaining': 3}
        result['archive'] = {'manifest': str(A / 'closed_execution/native_archive/manifest.json'),
            'regular_files': 514, 'regular_file_bytes': 1038191041, 'compressed_bytes': 32677904,
            'ordered_parts': archive['ordered_parts'], 'whole_member_readback_proof_retained': True,
            'archive_shard_current_bytes_sha_equal': True, 'raw_science_recalculated': False}
        after = {path: fingerprint(Path(path)) for path in bindings}
        require(bindings == after, 'original/canonical/generator bytes or stat changed during packaging checks')
        result.update(passed=True, source_unchanged=True, input_bindings=list(bindings.values()),
                      input_bindings_after=list(after.values()))
    except BaseException as error:
        result['errors'].append({'type': type(error).__name__, 'message': str(error)})
        result['input_bindings'] = list(bindings.values())
    result['ended_monotonic_ns'] = time.monotonic_ns()
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'passed': result['passed'], 'output': str(args.output), 'errors': result['errors'],
                      'accounting': result.get('accounting'), 'supplementary_absence': result.get('supplementary_absence')}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
