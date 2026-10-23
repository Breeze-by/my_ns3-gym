"""Create an exclusive proposed/admitted scope from actual prepared/build artifacts; no World."""
import argparse
import importlib.util
from pathlib import Path

loader = importlib.util.spec_from_file_location('v57_pair_scope_driver', Path(__file__).with_name('run_passive_pair_v1.py'))
d = importlib.util.module_from_spec(loader)
loader.loader.exec_module(d)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prepared-spec', type=Path, required=True)
    p.add_argument('--build-manifest', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--admit', action='store_true', help='Root uses only after real build/CPU/source checks.')
    a = p.parse_args()
    spec, build = d.read(a.prepared_spec), d.read(a.build_manifest)
    old = d.OLD_CORE | {str(path.relative_to(d.ROOT)) for path in
                       (d.OLD_INPUTS[0], d.OLD_INPUTS[2], d.OLD_INPUTS[3])}
    required = d.CHAIN | old | {str((d.A / name).relative_to(d.ROOT)) for name in
        ('run_passive_pair_v1.py', 'prepare_passive_plant_v1.py', 'passive_plant_v1.cpp')}
    rows = {}
    for relative in sorted(required):
        row = d.proof(d.ROOT / relative)
        rows[relative] = {k: row[k] for k in ('bytes', 'sha256')}
    actual = d.read(build['actual_wait']['path'])
    scope = {'schema': 'mr3-v57-passive-pair-scope-v1', 'admitted': a.admit,
        'status': 'ROOT_SEALED_AFTER_REAL_CPU_BUILD' if a.admit else 'PREPARED_NOT_ADMITTED',
        'evidence_freeze': d.OLD, 'arms': list(d.ARMS), 'no_retry': True,
        'gazebo_master_uri': d.URI, 'per_case_outer_stop_seconds': 720,
        'interrupt_to_TERM_seconds': 10, 'TERM_to_KILL_seconds': 10,
        'budget': {'engineering_used_seconds': str(d.ENTRY), 'engineering_ceiling_seconds': str(d.CEILING),
            'engineering_remaining_seconds': str(d.CEILING - d.ENTRY), 'reservation_seconds': str(d.CAP),
            'pilot_added_seconds': '0', 'validation_added_seconds': '0'},
        'prepared_spec': d.proof(a.prepared_spec), 'elf': build['elf'],
        'build_manifest': d.proof(a.build_manifest), 'build_actual_wait': build['actual_wait'],
        'actual_compile_argv': actual['actual_argv'], 'source_bindings': rows,
        'old_source_bindings': {relative: rows[relative] for relative in sorted(old)},
        'entry_ledger': d.proof(d.W / 'report/assets/20261023_mr3_p2a_v56_startup_gdb/closure_ledger_v1.json'),
        'numeric_user_approval_claimed': False, 'scientific_qualification_credit': False}
    d.write(a.output, scope)


if __name__ == '__main__':
    main()
