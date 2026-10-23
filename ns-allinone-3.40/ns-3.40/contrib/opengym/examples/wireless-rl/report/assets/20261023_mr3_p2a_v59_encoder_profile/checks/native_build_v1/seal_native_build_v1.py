"""Seal actual successful CPU driver build/tests. Does not load or run Gazebo."""
from pathlib import Path
import gzip
import hashlib
import json
import os
import re
import shlex
import subprocess
import time
import xml.etree.ElementTree as ET

ROOT = Path('/home/zhuyulab/ns3-workspace')
ROS = ROOT / 'ros2_ws/ros2-multi-robot-automap'
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A = W / 'report/assets/20261023_mr3_p2a_v59_encoder_profile'
B = A / 'checks/native_build_v1'

def read(p):
    return json.loads(p.read_bytes())

def write(p, value):
    with p.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')

def proof(p):
    p = Path(p)
    before = p.stat()
    raw = p.read_bytes()
    after = p.stat()
    fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
    assert all(getattr(before, key) == getattr(after, key) for key in fields), str(p)
    return {'path':str(p), 'bytes':len(raw), 'sha256':hashlib.sha256(raw).hexdigest()}

entry = read(B / 'build_entry_v1.json')
wait = read(B / 'build_actual_wait/actual_wait.json')
test = read(B / 'test_actual_wait_v2/actual_wait.json')
for receipt in (wait, test):
    assert receipt['passed'] and receipt['actual_waited'] and receipt['actual_returncode'] == 0
    assert receipt['errors'] == [] and receipt['source_unchanged'] and receipt['source_before'] == receipt['source_after']
assert wait['actual_argv'] == entry['actual_build_command']
assert read(B / 'build_parent_wait_v1.json')['actual_returncode'] == 0
assert read(B / 'test_parent_wait_v2.json')['actual_returncode'] == 0
source_after = [proof(Path(row['path'])) for row in entry['source_before']]
assert entry['source_before'] == source_after
fields = entry['compiled_sources']['driver']
extra = entry['initial_encoder_compiled_source']
flags_path = ROS / 'build/multi_robot/CMakeFiles/mr3_gazebo_diff_drive.dir/flags.make'
flags = flags_path.read_bytes()
macros = {
    'MR3_DRIVE_SOURCE_SHA256':'compiled_source_sha256',
    'MR3_DRIVE_HEADER_SHA256':'compiled_header_sha256',
    'MR3_DRIVE_HELPER_SHA256':'compiled_helper_sha256',
    'MR3_DRIVE_TARGET_SHA256':'compiled_target_contract_sha256',
    'MR3_ODOMETRY_JSON_HEADER_SHA256':'compiled_odometry_json_sha256',
    'MR3_DRIVE_FEED_HEADER_SHA256':'compiled_drive_feed_sha256'}
assignments = {}
for label in ('CXX_DEFINES', 'CXX_FLAGS'):
    found = [line.split(' = ',1)[1] for line in flags.decode().splitlines() if line.startswith(label+' = ')]
    assert len(found) == 1
    assignments[label] = shlex.split(found[0])
tokens = assignments['CXX_DEFINES'] + assignments['CXX_FLAGS']
for macro, field in macros.items():
    assert [t for t in tokens if t.split('=',1)[0] == '-D'+macro] == ['-D'+macro+'="'+fields[field]['sha256']+'"']
assert [t for t in tokens if t.split('=',1)[0] == '-DMR3_DRIVE_ENCODER_SERVO_SHA256'] == ['-DMR3_DRIVE_ENCODER_SERVO_SHA256="'+extra['sha256']+'"']
assert assignments['CXX_FLAGS'].count('-fno-fast-math') == 1
assert assignments['CXX_FLAGS'].count('-ffp-contract=off') == 1
assert not any(t in ('-ffast-math','-Ofast') or (t.startswith('-ffp-contract=') and t != '-ffp-contract=off') for t in tokens)
flags_archive = B / 'driver_flags_v1.make.rawbytes'
with flags_archive.open('xb') as stream: stream.write(flags)
commands_path = ROS / 'build/multi_robot/compile_commands.json'
commands = read(commands_path)
selected = [row for row in commands if row['file'] == fields['compiled_source_sha256']['path']]
assert len(selected) == 1
write(B / 'driver_compile_command_v1.json', selected[0])
with (B / 'compile_commands_v1.json.rawbytes').open('xb') as stream: stream.write(commands_path.read_bytes())
library_path = ROS / 'install/multi_robot/lib/libmr3_gazebo_diff_drive.so'
real_library = library_path.resolve(strict=True)
library = proof(library_path)
library['real_path'] = str(real_library)
raw = real_library.read_bytes()
assert raw[:4] == b'\x7fELF' and len(raw) == library['bytes'] and hashlib.sha256(raw).hexdigest() == library['sha256']
archive = A / 'native/libmr3_gazebo_diff_drive_initial_encoder_v1.so.gz'
with archive.open('xb') as target:
    with gzip.GzipFile(fileobj=target, mode='wb', filename='', mtime=0) as packed: packed.write(raw)
assert gzip.decompress(archive.read_bytes()) == raw
archive_ref = proof(archive)
archive_ref.update(raw_bytes=len(raw), raw_sha256=library['sha256'])
loader_env = {'PATH':'/usr/bin:/bin', 'LANG':'C.UTF-8', 'LC_ALL':'C.UTF-8',
    'LD_LIBRARY_PATH':'/opt/ros/humble/lib:/opt/ros/humble/lib/x86_64-linux-gnu'}
loader_command = ['/usr/bin/ldd',str(real_library)]
loader = subprocess.run(loader_command, env=loader_env, capture_output=True, text=True)
assert loader.returncode == 0 and 'not found' not in loader.stdout
write(B / 'driver_loader_v1.json', {'actual_argv':loader_command, 'environment':loader_env,
    'actual_returncode':loader.returncode,'actual_waited':True,'stdout':loader.stdout,'stderr':loader.stderr,
    'scope':'loader_only','native_world_runs':0})
xml_source = ROS / 'build/multi_robot/test_results/multi_robot/test_initial_zero_encoder_servo.gtest.xml'
xml = xml_source.read_bytes()
tests = ET.fromstring(xml)
assert tests.attrib['tests'] == '4' and all(tests.attrib[key] == '0' for key in ('failures','errors','disabled'))
with (B / 'receiver_gtest_v2.xml').open('xb') as stream:stream.write(xml)
identities = []
for relative in ('build_actual_wait/actual_wait.json','test_actual_wait/actual_wait.json','test_actual_wait_v2/actual_wait.json'):
    receipt = read(B / relative)
    for field in ('coordinator_identity','child_identity'):
        saved = receipt[field]
        try:
            proc = Path('/proc',str(saved['pid']),'stat').read_text()
            tail = proc[proc.rfind(')')+2:].split()
            present = int(tail[19]) == saved['start_ticks']
            status = 'same_identity_present' if present else 'pid_reused'
            observed_state = tail[0]
        except FileNotFoundError:
            present,status,observed_state = False,'absent',None
        assert not present, (saved,status)
        identities.append({'saved_identity':saved,'receipt':proof(B / relative),
            'observed_status':status,'observed_state':observed_state,'same_identity_present':present})
write(B / 'freshgone_v1.json', {'schema':'mr3-initial-encoder-driver-cpu-freshgone-v1','passed':True,
    'observed_unix_ns':time.time_ns(),'identities':identities,'saved_identity_count':len(identities),
    'actual_tool_results':{'build_session44877':0,'first_test_immediate_tool':1,'test_v2_session10104':0},
    'scope':'cpu','engineering_added_seconds':'0','native_world_runs':0})
assert proof(library_path) == {k:v for k,v in library.items() if k != 'real_path'}
assert source_after == [proof(Path(row['path'])) for row in entry['source_before']]
flags_spec = proof(flags_path);flags_spec['real_path'] = str(flags_path.resolve(strict=True))
manifest = {'schema':'mr3-initial-encoder-driver-build-manifest-v1','passed':True,'source_unchanged':True,
    'build_entry':proof(B / 'build_entry_v1.json'),'actual_wait':proof(B / 'build_actual_wait/actual_wait.json'),
    'receiver_test_actual_wait':proof(B / 'test_actual_wait_v2/actual_wait.json'),
    'previous_failed_test_entry':proof(B / 'test_actual_wait/actual_wait.json'),
    'receiver_gtest_xml':proof(B / 'receiver_gtest_v2.xml'),'receiver_cases_passed':4,
    'library':library,'compiler_flags':flags_spec,'compiler_flags_archive':proof(flags_archive),
    'compile_commands_archive':proof(B / 'compile_commands_v1.json.rawbytes'),
    'driver_compile_command':proof(B / 'driver_compile_command_v1.json'),
    'sources':source_after,'source_before':entry['source_before'],'source_after':source_after,
    'compiled_sources':entry['compiled_sources'],'initial_encoder_compiled_source':extra,
    'compiled_encoder_servo_sha256':extra['sha256'],
    'archived_library_gzip':archive_ref,'loader_receipt':proof(B / 'driver_loader_v1.json'),
    'freshgone':proof(B / 'freshgone_v1.json'),'numeric_compile_options':['-fno-fast-math','-ffp-contract=off'],
    'actuation_profile':'initial-zero-encoder-hold-v1',
    'actuation_algorithm':'initial_zero_encoder_hold_then_paired_common_fraction_v1',
    'scope':'cpu','engineering_added_seconds':'0','native_world_runs':0,
    'new_actual_build_executed':True,'existing_v15_no_new_build_credit_reused':False,
    'native_admission':False,'p2a_complete':False}
for field, spec in fields.items():manifest[field] = spec['sha256']
manifest['compiled_feed_header_sha256'] = fields['compiled_drive_feed_sha256']['sha256']
write(B / 'build_manifest_v1.json', manifest)
print(json.dumps({'passed':True,'library':library,'manifest':proof(B / 'build_manifest_v1.json'),
    'actual_build_wall_seconds':wait['actual_child_wait_seconds'],
    'actual_receiver_test_wall_seconds':test['actual_child_wait_seconds'],
    'receiver_cases_passed':4,'saved_identities_gone':len(identities),'world_runs':0}))
