"""Prepare/seal one current-source CPU colcon activity; never run the build here.

The separately generated launcher is the only build action. Seal observes its
real wait and parent tool reap; it never invents compiler/test/loader execution.
"""
from pathlib import Path
from decimal import Decimal
import argparse
import gzip
import hashlib
import json
import shlex
import time

ROOT=Path('/home/zhuyulab/ns3-workspace')
ROS=ROOT/'ros2_ws/ros2-multi-robot-automap'
W=ROOT/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
OLD=W/'report/assets/20261023_mr3_p2a_v59_encoder_profile'
A=W/'report/assets/20261024_mr3_p2a_authority_activation'
B=A/'checks/native_build_v1'
OLD_MANIFEST=OLD/'checks/native_build_v1/build_manifest_v1.json'
OLD_MANIFEST_SHA='fc6d475efa4d66fa3645a11b160b06583c9eff2b7ab0ed292c821b4cae3c26f7'
BUILD_SCRIPT=OLD/'checks/native_build_v1/build_native_ros_v1.sh'
BUILD_SCRIPT_SHA='06964d045b1e16ca9e6a51abe0ae6cce097d57dbe732b757744c8306025158b9'
BUILD_ARGV=['/bin/bash','--noprofile','--norc',str(BUILD_SCRIPT)]
PROFILE='initial-zero-encoder-hold-v1'
ALGORITHM='initial_zero_encoder_hold_then_paired_common_fraction_v1'
# Root must fill the final installed masked Supervisor bytes/SHA before fresh seal/build prepare.
EXPECTED_SUPERVISOR={'path':str(W/'mr3_learning/supervisor.py'),'bytes':30319,'sha256':'94cf3440f6eb8f89d62e110c4f7bcb10300211adb6b5476a91b0e97c49e79dd5'}


def read(path):return json.loads(Path(path).read_bytes())


def write(path,value):
    with Path(path).open('x') as stream:
        json.dump(value,stream,indent=2,allow_nan=False);stream.write('\n')


def proof(path):
    path=Path(path);before=path.stat();data=path.read_bytes();after=path.stat()
    assert all(getattr(before,k)==getattr(after,k) for k in
               ('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns')),str(path)
    return {'path':str(path),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}


def original():
    assert proof(OLD_MANIFEST)['sha256']==OLD_MANIFEST_SHA
    assert proof(BUILD_SCRIPT)['sha256']==BUILD_SCRIPT_SHA
    return read(OLD_MANIFEST)


def declarations():
    old=original();paths=[Path(row['path']) for row in old['source_before']]
    assert len(paths)==20 and len(set(paths))==20
    paths.append(W/'mr3_learning/motion_authority_profile.py')
    assert len(paths)==len(set(paths))==21
    sources=[proof(path) for path in paths]
    assert type(EXPECTED_SUPERVISOR['bytes']) is int and EXPECTED_SUPERVISOR['bytes'] > 0 and type(EXPECTED_SUPERVISOR['sha256']) is str and len(EXPECTED_SUPERVISOR['sha256']) == 64 and all(c in '0123456789abcdef' for c in EXPECTED_SUPERVISOR['sha256']), 'final installed masked Supervisor pin remains pending; prepare refused'
    assert proof(W/'mr3_learning/supervisor.py')==EXPECTED_SUPERVISOR, 'install the exact final masked Supervisor before this new A71 build'
    fields=old['compiled_sources'];extra=old['initial_encoder_compiled_source']
    # Unchanged TU/header law. The other activity inputs remain provenance,
    # never claimed to have been compiled into the driver.
    for row in [*fields['driver'].values(),extra]:
        assert proof(row['path'])['sha256']==row['sha256']
    cmake=ROS/'src/multi_robot/CMakeLists.txt'
    assert proof(cmake)['sha256']==next(row['sha256'] for row in old['sources'] if row['path']==str(cmake))
    command=['/usr/bin/python3','-B','-m','mr3_learning.reach_execution','--scope','cpu',
             '--output',str(B/'build_actual_wait')]
    for path in paths:command+=['--source',str(path)]
    command+=['--',*BUILD_ARGV]
    return old,sources,fields,extra,command


def prepare():
    old,sources,fields,extra,command=declarations()
    B.mkdir(parents=True,exist_ok=True);(A/'native').mkdir(exist_ok=True)
    assert not (B/'build_entry_v1.json').exists() and not (B/'build_actual_wait').exists()
    snapshots=B/'source_snapshots';snapshots.mkdir()
    recovery=[]
    for row in sources:
        data=Path(row['path']).read_bytes();assert hashlib.sha256(data).hexdigest()==row['sha256']
        path=snapshots/(row['sha256']+'.rawbytes.gz')
        if not path.exists():path.write_bytes(gzip.compress(data,mtime=0))
        assert gzip.decompress(path.read_bytes())==data
        recovery.append(dict(row,recovery=str(path)))
    entry={'schema':'mr3-initial-encoder-driver-build-entry-v1','declared_unix_ns':time.time_ns(),
        'cwd':str(W),'actual_wrapper_argv':command,'actual_build_command':BUILD_ARGV,
        'source_before':sources,'source_recovery':recovery,'compiled_sources':fields,
        'initial_encoder_compiled_source':extra,'preparation_tool':proof(__file__),
        'historical_manifest':proof(OLD_MANIFEST),'scope':'cpu','engineering_added_seconds':'0',
        'native_world_runs':0,'same_CPP_law_and_numeric_options':True,
        'activity_input_count':21,'Python_activity_inputs_are_not_compiled_source_claims':True,
        'compiler_or_link_jobs_not_inferred_from_command_execution':True}
    write(B/'build_entry_v1.json',entry)
    launcher=B/'launch_actual_build_v1.sh'
    with launcher.open('x') as stream:
        stream.write('#!/bin/bash\nset -eu\ncd '+shlex.quote(str(W))+'\nexec env -u PYTHONPATH -u PYTHONHOME PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 '+shlex.join(command)+'\n')
    print(json.dumps({'prepared':True,'build_executed':False,'launcher':str(launcher),
                      'source_count':21,'output':str(B/'build_actual_wait')}))


def seal():
    entry=read(B/'build_entry_v1.json');wait_path=B/'build_actual_wait/actual_wait.json';wait=read(wait_path)
    parent=read(B/'build_parent_wait_v1.json')
    assert parent['actual_tool_reaped'] is True and type(parent['actual_returncode']) is int and parent['actual_returncode']==0
    session=parent.get('actual_tool_session_id')
    if type(session) is int and session>0:
        pass  # The original actually yielded tool session was truly reaped.
    else:
        # A directly completed real exec has no numeric running-session ID.
        # Bind its original tool response; never make up a replacement session.
        observed=parent['actual_exec_return']
        assert session is None and parent['numeric_session_id_available'] is False
        assert type(observed.get('exit_code')) is int and observed['exit_code']==0
        assert type(observed.get('chunk_id')) is str and observed['chunk_id']
        assert observed.get('session_id') is None
        assert parent['actual_tool_direct_chunk_id']==observed['chunk_id']
    assert wait['passed'] is True and wait['actual_waited'] is True and type(wait['actual_returncode']) is int and wait['actual_returncode']==0 and wait['errors']==[]
    assert wait['source_unchanged'] is True and wait['source_before']==wait['source_after'] and len(wait['source_before'])==21
    assert wait['actual_argv']==entry['actual_build_command']==BUILD_ARGV and wait['cwd']==str(W)
    assert Decimal(wait['actual_child_wait_seconds'])==Decimal(wait['ended_monotonic_ns']-wait['started_monotonic_ns'])/10**9
    after=[proof(row['path']) for row in entry['source_before']]
    assert after==entry['source_before']
    assert [{k:row[k] for k in ('path','bytes','sha256')} for row in wait['source_before']]==after
    assert proof(entry['preparation_tool']['path'])==entry['preparation_tool']
    for row in entry['source_recovery']:
        assert hashlib.sha256(gzip.decompress(Path(row['recovery']).read_bytes())).hexdigest()==row['sha256']
    fields=entry['compiled_sources']['driver'];extra=entry['initial_encoder_compiled_source']
    flags_path=ROS/'build/multi_robot/CMakeFiles/mr3_gazebo_diff_drive.dir/flags.make'
    flags=flags_path.read_bytes();assignments={}
    for label in ('CXX_DEFINES','CXX_FLAGS'):
        found=[line.split(' = ',1)[1] for line in flags.decode().splitlines() if line.startswith(label+' = ')]
        assert len(found)==1;assignments[label]=shlex.split(found[0])
    tokens=assignments['CXX_DEFINES']+assignments['CXX_FLAGS']
    macros={'MR3_DRIVE_SOURCE_SHA256':'compiled_source_sha256','MR3_DRIVE_HEADER_SHA256':'compiled_header_sha256',
        'MR3_DRIVE_HELPER_SHA256':'compiled_helper_sha256','MR3_DRIVE_TARGET_SHA256':'compiled_target_contract_sha256',
        'MR3_ODOMETRY_JSON_HEADER_SHA256':'compiled_odometry_json_sha256','MR3_DRIVE_FEED_HEADER_SHA256':'compiled_drive_feed_sha256'}
    for macro,field in macros.items():
        assert [t for t in tokens if t.split('=',1)[0]=='-D'+macro]==['-D'+macro+'="'+fields[field]['sha256']+'"']
        assert '-U'+macro not in tokens
    assert [t for t in tokens if t.split('=',1)[0]=='-DMR3_DRIVE_ENCODER_SERVO_SHA256']==['-DMR3_DRIVE_ENCODER_SERVO_SHA256="'+extra['sha256']+'"']
    assert '-UMR3_DRIVE_ENCODER_SERVO_SHA256' not in tokens
    assert assignments['CXX_FLAGS'].count('-fno-fast-math')==assignments['CXX_FLAGS'].count('-ffp-contract=off')==1
    assert not any(t in ('-ffast-math','-Ofast') or t.startswith('-ffp-contract=') and t!='-ffp-contract=off' for t in tokens)
    flags_archive=B/'driver_flags_v1.make.rawbytes'
    with flags_archive.open('xb') as stream:stream.write(flags)
    commands_path=ROS/'build/multi_robot/compile_commands.json';commands=read(commands_path)
    selected=[row for row in commands if row['file']==fields['compiled_source_sha256']['path']];assert len(selected)==1
    write(B/'driver_compile_command_v1.json',selected[0])
    with (B/'compile_commands_v1.json.rawbytes').open('xb') as stream:stream.write(commands_path.read_bytes())
    library_path=ROS/'install/multi_robot/lib/libmr3_gazebo_diff_drive.so';library=proof(library_path)
    library['real_path']=str(library_path.resolve(strict=True));elf=library_path.read_bytes();assert elf[:4]==b'\x7fELF'
    for row in [*fields.values(),extra]:assert row['sha256'].encode() in elf
    archive=A/'native/libmr3_gazebo_diff_drive_initial_encoder_v1.so.gz'
    with archive.open('xb') as stream:
        with gzip.GzipFile(fileobj=stream,mode='wb',filename='',mtime=0) as packed:packed.write(elf)
    assert gzip.decompress(archive.read_bytes())==elf
    archive_ref=dict(proof(archive),raw_bytes=len(elf),raw_sha256=library['sha256'])
    identities=[]
    for name in ('coordinator_identity','child_identity'):
        saved=wait[name];assert type(saved['pid']) is int and saved['pid']>0 and type(saved['start_ticks']) is int and saved['start_ticks']>0
        current=None
        try:
            proc=Path('/proc',str(saved['pid']),'stat').read_text();tail=proc[proc.rfind(')')+2:].split()
            current={'start_ticks':int(tail[19]),'state':tail[0]}
        except FileNotFoundError:pass
        gone=current is None or current['start_ticks']!=saved['start_ticks'];assert gone
        identities.append({'role':name,'saved_identity':saved,'observed':current,'gone':gone})
    assert wait['child_identity']['parent']==wait['coordinator_identity']['pid']
    write(B/'freshgone_v1.json',{'passed':True,'identities':identities,'scope':'cpu','engineering_added_seconds':'0'})
    old=original();flags_spec=dict(proof(flags_path),real_path=str(flags_path.resolve(strict=True)))
    manifest={'schema':'mr3-initial-encoder-driver-build-manifest-v1','passed':True,'source_unchanged':True,
        'build_entry':proof(B/'build_entry_v1.json'),'actual_wait':proof(wait_path),
        'preparation_tool':entry['preparation_tool'],
        'actual_root_tool_reap':proof(B/'build_parent_wait_v1.json'),
        'library':library,'compiler_flags':flags_spec,'compiler_flags_archive':proof(flags_archive),
        'compile_commands_archive':proof(B/'compile_commands_v1.json.rawbytes'),
        'driver_compile_command':proof(B/'driver_compile_command_v1.json'),'sources':after,
        'source_before':entry['source_before'],'source_after':after,'compiled_sources':entry['compiled_sources'],
        'initial_encoder_compiled_source':extra,'compiled_encoder_servo_sha256':extra['sha256'],
        'archived_library_gzip':archive_ref,'freshgone':proof(B/'freshgone_v1.json'),
        'numeric_compile_options':['-fno-fast-math','-ffp-contract=off'],'actuation_profile':PROFILE,
        'actuation_algorithm':ALGORITHM,'scope':'cpu','engineering_added_seconds':'0','native_world_runs':0,
        'new_actual_build_executed':True,'actual_colcon_build_activity_executed':True,
        'same_ELF_bytes_as_A59':library['sha256']==old['library']['sha256'] and library['bytes']==old['library']['bytes'],
        'compiler_or_link_jobs_observed':None,'compiler_or_link_jobs_claimed':False,
        'incremental_no_compile_is_not_relabelled_new_compilation':True,
        'Python_activity_inputs_claimed_compiled':False,'receiver_tests_executed':False,'loader_executed':False,
        'existing_v15_no_new_build_credit_reused':False,'native_admission':False,'p2a_complete':False}
    for name,row in fields.items():manifest[name]=row['sha256']
    manifest['compiled_feed_header_sha256']=fields['compiled_drive_feed_sha256']['sha256']
    assert after==[proof(row['path']) for row in after]
    write(B/'build_manifest_v1.json',manifest)
    previous_bridge=read(OLD/'native_build_bridge_v1.json')
    bridge={k:previous_bridge[k] for k in ('schema','safety_contract','scope','actuation_profile','source_derivation')}
    bridge.update(passed=True,actual_wait=proof(wait_path),manifest=proof(B/'build_manifest_v1.json'),
        compiler_flags_archive=proof(flags_archive),commands=[{'argv':BUILD_ARGV,'returncode':0,'observed_returncode':0}],
        passed_scope='new actual current-source build activity; no inference of compiler jobs or native qualification',
        native_admission=False,historical_driver_build_credit_reused=False)
    write(A/'native_build_bridge_v1.json',bridge)
    print(json.dumps({'sealed':True,'manifest':proof(B/'build_manifest_v1.json'),
        'bridge':proof(A/'native_build_bridge_v1.json'),'same_ELF_bytes_as_A59':manifest['same_ELF_bytes_as_A59'],
        'source_count':21,'native_world_runs':0,'compiler_jobs_claimed':False}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('operation',choices=('prepare','seal'))
    args=parser.parse_args()
    if args.operation=='prepare':prepare()
    else:seal()
