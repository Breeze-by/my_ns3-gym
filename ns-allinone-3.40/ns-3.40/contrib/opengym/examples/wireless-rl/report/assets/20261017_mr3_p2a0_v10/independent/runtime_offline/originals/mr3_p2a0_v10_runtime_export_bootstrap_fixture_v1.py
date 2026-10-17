"""Export final synthetic fixture, no ROS/native or altered production rules."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from mr3_learning.tests.test_audit_preparation import ControlledPreparationTests
from mr3_learning.audit_preparation import controlled_bootstrap, dispatch_controlled_physics

root = Path('/tmp/mr3_p2a0_v10_runtime_bootstrap_fixture_v1')
root.mkdir(exist_ok=False)
ControlledPreparationTests.setUpClass()
case = ControlledPreparationTests()
directory, files, motion = case.setup_episode(root)
epoch = files['metadata.json']['epoch']
release = 1_020_000_000
try:
    case.original_physics(files['physics.jsonl'], epoch, release)
except ValueError as error:
    original_rejection = str(error)
else:
    raise AssertionError('immutable native gate must reject setup20 with task-release switch')
auditor = SimpleNamespace(audit_physics=case.original_physics)
dispatch_controlled_physics(auditor, [root], {directory: motion})
result = auditor.audit_physics(files['physics.jsonl'], epoch, release)
proof = controlled_bootstrap(directory, files['physics.jsonl'], epoch, release, motion)
assert result['total_physical_ticks'] == 60 and result['original_integer_continuity_quantum_math']
assert proof['actual_task_release_time_ns'] == release
out = {'passed': True, 'scope': 'final synthetic fixture export; not native credit',
       'fixture': str(directory), 'motion_review': motion, 'bootstrap_proof': proof,
       'immutable_original_rejection': original_rejection, 'dispatch_result': result}
(root / 'fixture_review.json').write_text(json.dumps(out, indent=2) + '\n')
print(json.dumps({'passed': True, 'fixture': str(directory),
                  'file_count': sum(path.is_file() for path in root.rglob('*'))}))
