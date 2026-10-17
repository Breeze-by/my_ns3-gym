"""Synthetic actual pure-producer schema compatibility; no ROS/native activity."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path('/home/zhuyulab/ns3-workspace')
PACKAGE = ROOT / 'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration'
sys.path.insert(0, str(PACKAGE))
from multi_robot_exploration import mr3_motion_safety as producer
spec = importlib.util.spec_from_file_location('settled_external_tests', '/tmp/mr3_independent_settled_turn_v1_tests.py')
tests = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tests)
consumer = tests.consumer
source = Path(producer.__file__)
before = hashlib.sha256(source.read_bytes()).hexdigest()
data = tests.fixture()
tracker = producer.SettledTurnTracker()
for row in data['motion']:
    payload = row['payload']
    if row['kind'] == 'own_odom':
        tracker.observe(payload['message'], payload['input_sequence'])
    elif row['kind'] == 'decision':
        clock = payload['clock_ns']
        sequence = payload['decision_sequence']
        if sequence == 3:
            own = payload['own_state']
            own['settled_turn'] = tracker.certificate(clock)
            decision = producer.guard_motion([payload['request']['v'], payload['request']['w']],
                                             own, payload['received_peers'], clock / 1e9,
                                             data['metadata']['epoch'])
            assert decision['reason'] == 'settled_turn_drift_reserve', decision
            payload['decision'] = decision
            tracker.activate(clock)
        tracker.output(payload['decision']['output'][0], clock, sequence)
result = consumer.audit_records(**data, require_use=True)
after = hashlib.sha256(source.read_bytes()).hexdigest()
assert before == after
output = Path('/tmp/mr3_p2a0_v8_settled_turn_producer_compat_v3.json')
with output.open('x') as stream:
    stream.write(json.dumps({'schema': 'mr3-v8-settled-turn-producer-schema-compat-v1',
        'passed': result['passed'], 'producer_source': str(source), 'source_before': before,
        'source_after': after, 'consumer_sha256': hashlib.sha256(Path(consumer.__file__).read_bytes()).hexdigest(),
        'fixture': data, 'independent_result': result,
        'scope': 'Synthetic real pure-tracker+guard output consumed by independent module. No ROS construction, driver process, world movement, actual storage or physical claim.'}, indent=2, allow_nan=False) + '\n')
print(json.dumps({'passed': result['passed'], 'source_stable': before == after, 'output': str(output)}))
