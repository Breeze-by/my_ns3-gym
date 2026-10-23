"""Static binary/GDB-record inspection only; never loads Gazebo or a World."""
import hashlib,json,os,subprocess,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
LIB=Path('/usr/lib/x86_64-linux-gnu/libgazebo_util.so.11.10.2')
CONSOLE=Path('/tmp/mr3_p2a_v56_startup_gdb_v1/actual_wait/console.log')
EXPECTED={'/usr/lib/x86_64-linux-gnu/libgazebo_util.so.11.10.2': '08ab9e6f790198e042ab9001ef3ebaa5f9f1621d07881c31322310a954251e29', '/tmp/mr3_p2a_v56_startup_gdb_v1/actual_wait/console.log': 'c7687743f1f2f4523dcf318ff903c82806a261d25ec6b8a1cf3b1aa3f1ffc7b8'}
def identity():
 s=Path('/proc/self/stat').read_text(); fields=s[s.rfind(')')+2:].split()
 return dict(pid=os.getpid(),parent=os.getppid(),group=os.getpgrp(),session=os.getsid(0),start_ticks=int(fields[19]))
def stable(p):
 before=p.stat();raw=p.read_bytes();after=p.stat()
 keys=('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns')
 assert all(getattr(before,k)==getattr(after,k)for k in keys),str(p)
 return raw
out=HERE/'evidence';out.mkdir(exist_ok=False)
for p in (LIB,CONSOLE):
 raw=stable(p); assert hashlib.sha256(raw).hexdigest()==EXPECTED[str(p)]
commands=[('constructor_disassembly.txt',['/usr/bin/objdump','-d','-C','--start-address=0x361d0','--stop-address=0x36350',str(LIB)]),('home_rodata.txt',['/usr/bin/objdump','-s','--start-address=0x7b1c0','--stop-address=0x7b210',str(LIB)])]
receipts=[]
for name,argv in commands:
 child=subprocess.Popen(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
 stdout,stderr=child.communicate()
 receipts.append(dict(actual_argv=argv,pid=child.pid,actual_waited=True,returncode=child.returncode,stderr=stderr))
 assert child.returncode==0 and stderr==''
 (out/name).write_text(stdout)
assembly=(out/'constructor_disassembly.txt').read_text()
assert '362ab:' in assembly and 'getEnv(char const*)@plt' in assembly
assert '362b4:' in assembly and 'mov    %rax,%rdi' in assembly
assert '362ba:' in assembly and 'strlen@plt' in assembly and '362bf:' in assembly
assert '484f 4d45' in (out/'home_rodata.txt').read_text()
console=stable(CONSOLE).decode()
assert 'No HOME defined in the environment. Will not log.' in console
assert '0x00007ffff74ad2bf in gazebo::util::DiagnosticManager::DiagnosticManager()' in console
assert 'gazebo::loadWorld' in console and '__strlen_evex' in console
proof={'schema': 'mr3-v56-home-constructor-static-proof-v1', 'status': 'CONFIRMED_NULL_HOME_DEREFERENCE_PATH', 'native_runs': 0, 'source_mutations': False, 'inputs': [{'path': '/usr/lib/x86_64-linux-gnu/libgazebo_util.so.11.10.2', 'resolved': '/usr/lib/x86_64-linux-gnu/libgazebo_util.so.11.10.2', 'bytes': 654680, 'sha256': '08ab9e6f790198e042ab9001ef3ebaa5f9f1621d07881c31322310a954251e29', 'stable': True}, {'path': '/tmp/mr3_p2a_v56_startup_gdb_v1/actual_wait/console.log', 'resolved': '/tmp/mr3_p2a_v56_startup_gdb_v1/actual_wait/console.log', 'bytes': 79439, 'sha256': 'c7687743f1f2f4523dcf318ff903c82806a261d25ec6b8a1cf3b1aa3f1ffc7b8', 'stable': True}], 'facts': {'constructor_symbol': '_ZN6gazebo4util17DiagnosticManagerC1Ev', 'constructor_vma': '0x361d0', 'environment_key_vma': '0x7b1d2', 'environment_key_hex': '48 4f 4d 45 00', 'environment_key': 'HOME', 'call_getEnv': '0x362ab', 'move_return_to_strlen_arg': '0x362b4: mov %rax,%rdi', 'call_strlen_without_null_guard': '0x362ba', 'return_address': '0x362bf', 'actual_gdb_frame1': '0x00007ffff74ad2bf', 'gdb_frame0': '__strlen_evex', 'gdb_loadworld_path': 'DiagnosticManager ctor -> World::Init -> init_world -> gazebo::loadWorld -> main', 'closed_console_warning': 'No HOME defined in the environment. Will not log.'}, 'official_source': {'url': 'https://raw.githubusercontent.com/gazebosim/gazebo-classic/gazebo11/gazebo/util/Diagnostics.cc', 'getenv_line': 33, 'path_assign_before_null_test_line': 34, 'null_check_line': 36, 'scope': 'Upstream source matches verified local machine-code path; no claim that a source download alone identifies installed ELF.'}, 'interpretation': 'Missing HOME reaches local ctor getEnv(HOME) -> unguarded strlen before fallback. Native crashed during World initialization, before runWorld and custom control/anchor callbacks. This is diagnostic launch environment failure, not evidence about solver or drift.', 'minimal_future_fix': 'New declared attempt: driver cleanenv includes a real absolute owned HOME directory, mkdir exclusive before submit, record HOME policy, keep rest plant/control constants; optional executable preflight rejects absent/empty HOME rather than relying on buggy library fallback. No change to installed Gazebo or original V55/V56 evidence.', 'limitations': ['This static proof does not run a fixed native attempt.', 'No physical diagnostic/qualification credit is added.', 'Future actual startup and full measurement must be independently recorded under new scope/freeze.']}
proof.update(actual_argv=[sys.executable,*sys.argv],identity=identity(),passed=True,static_subprocess_receipts=receipts)
(out/'proof_v1.json').write_text(json.dumps(proof,indent=2)+'\n')
for p in (LIB,CONSOLE):assert hashlib.sha256(stable(p)).hexdigest()==EXPECTED[str(p)]
print(json.dumps(dict(passed=True,native_runs=0,output=str(out))))
