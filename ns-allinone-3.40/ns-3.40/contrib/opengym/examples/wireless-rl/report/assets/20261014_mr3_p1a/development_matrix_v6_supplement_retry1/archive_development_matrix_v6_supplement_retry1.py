#!/usr/bin/env python3
"""Archive the completed one-attempt prospective supplement, never run ROS."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path

ROOT = Path('/home/zhuyulab/ns3-workspace')
ROS = ROOT / 'ros2_ws/ros2-multi-robot-automap'
A = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261014_mr3_p1a'
FREEZE = '5e478025ede4f66420cc293655c0c03db791b2ab'
RUN_ID = 'mr3_p1a_v6_open_shutdown_retry1_20261014_172003'
PRE_SHA = 'a22af2d3cdf9c1db1af76b5ff25be7667ce8d67b5fbebf26b2fb513ed9337605'

def sha(data):
    return hashlib.sha256(data).hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, required=True)
    args = parser.parse_args()
    base = args.base.resolve()
    assert not base.exists(), base
    pre_path = A / 'v6_open303_infrastructure_retry1_predeclaration.json'
    assert sha(pre_path.read_bytes()) == PRE_SHA
    pre = json.loads(pre_path.read_text())
    assert pre['source_freeze'] == FREEZE and pre['maximum_additional_attempts'] == 1
    for name, expected in pre['original_evidence_sha256'].items():
        assert sha((ROOT / name).read_bytes()) == expected
    source = ROS / 'log/mr3_p1a' / RUN_ID
    batch = json.loads((source / 'summary.json').read_text())
    assert batch['run_id'] == RUN_ID and batch['seeds'] == [303]
    assert len(batch['episodes']) == 1 and batch['episodes'][0]['gazebo_seed'] == 303
    auditor = Path('/tmp/audit_development_matrix_v6_supplement_retry1.py')
    assert auditor.is_file()
    original = A / 'development_matrix_v6'
    inputs = [(pre_path, 'validation_inputs/' + pre_path.name),
              (A / (RUN_ID + '_invocation.json'), 'validation_inputs/' + RUN_ID + '_invocation.json'),
              (A / 'v6_open303_infrastructure_retry1_native_environment.json', 'validation_inputs/v6_open303_infrastructure_retry1_native_environment.json'),
              (A / 'runtime_component_manifest_matrix6.json', 'validation_inputs/runtime_component_manifest_matrix6.json'),
              (A / 'v6_infrastructure_retry1_invocation_source.py', 'validation_inputs/v6_infrastructure_retry1_invocation_source.py'),
              (original / 'validation_inputs/frozen_predeclared_native_plan.json', 'validation_inputs/frozen_predeclared_native_plan.json'),
              (original / 'frozen_ros_smoke_test.py', 'frozen_ros_smoke_test.py'),
              (original / 'frozen_contracts/open.json', 'frozen_contracts/open.json'),
              (original / 'frozen_mr3_fastdds_loopback_udp.xml', 'frozen_mr3_fastdds_loopback_udp.xml'),
              (auditor, auditor.name),
              (Path(__file__), Path(__file__).name)]
    assert all(path.is_file() for path, _ in inputs)
    base.mkdir(parents=True)
    raw_records, input_records = [], []
    def copy(path, relative, records, role):
        data = path.read_bytes()
        destination = base / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open('xb') as stream:
            stream.write(data)
        assert destination.read_bytes() == data
        records.append({'source_path': str(path), 'canonical_path': relative,
                        'size_bytes': len(data), 'sha256': sha(data), 'role': role})
    for path in sorted(source.rglob('*')):
        if path.is_file():
            copy(path, str(Path('open') / path.relative_to(source)), raw_records, 'unaltered_supplement_native_original')
    for path, relative in inputs:
        copy(path, relative, input_records, 'supplement_validation_input_not_native_result')
    for record in raw_records:
        assert sha(Path(record['source_path']).read_bytes()) == record['sha256']
    receipt = {'type': 'canonical_byte_preserving_supplement_copy_not_experiment',
               'recorded_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
               'source_freeze': FREEZE, 'attempt_count': 1,
               'completed_families': ['open'], 'raw_files': raw_records,
               'validation_inputs': input_records, 'unstarted_cells': [],
               'native_original_file_count': len(raw_records),
               'native_original_total_bytes': sum(x['size_bytes'] for x in raw_records),
               'original_nine_archive_modified': False,
               'originals_modified': False, 'simulator_runs': 0, 'policy_runs': 0}
    with (base / 'copy_hash_receipt.json').open('x') as stream:
        json.dump(receipt, stream, indent=2, sort_keys=True, allow_nan=False)
    print(json.dumps({k:v for k,v in receipt.items() if k not in ('raw_files','validation_inputs')}, indent=2))

if __name__ == '__main__':
    main()
