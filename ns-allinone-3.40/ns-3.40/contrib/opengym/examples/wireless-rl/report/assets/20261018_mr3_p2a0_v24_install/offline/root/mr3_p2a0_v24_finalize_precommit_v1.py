import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A = W / 'report/assets/20261018_mr3_p2a0_v24_install'
B = Path('/tmp/mr3_p2a0_v24_admission_matrix_independent_review_v1')
h = json.loads((B / 'handoff_v1.json').read_text())
assert h['passed'] and h['source_and_metadata_STOP']
for source, name, expected in ((Path(h['review']), 'review_v1.json', h['review_sha256']), (Path(h['manifest']), 'manifest_v1.json', h['manifest_sha256']), (Path(h['archive']), 'originals.tar.gz', h['archive_sha256']), (B / 'handoff_v1.json', 'handoff_v1.json', None)):
    raw = source.read_bytes()
    if expected:
        assert hashlib.sha256(raw).hexdigest() == expected
    destination = A / 'offline/admission_review' / name
    assert not destination.exists()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(raw)
    assert destination.read_bytes() == raw
with (W / 'report/20261018_mr3_p2a0_v24_install.md').open('a') as output:
    output.write('\n\n最终[独立准入源码审查](assets/20261018_mr3_p2a0_v24_install/offline/admission_review/review_v1.json)通过，229输入末SHA/stat稳定；报告d2e0e6c4…，封包a57e94de…完整往返。初review脚本中文跨行文字匹配失败的原源与说明保留；没有独立原console则明确缺失，不伪造。根静态核对210绑定、196旧原样/2明确更新/12新、34门、8份Python AST、27份当时JSON与187链接均通过；不替代实际冻结预检。\n')
with (W / 'log.md').open('a') as output:
    output.write('\n最终源码独审 d2e0e6c4bc433b9c44333e3f459927e50559c714fe11790ca034d0941c208630 PASS，无阻断，229实际输入末SHA/stat稳定；5member往返封包a57e94de82886aa4dbd06d52a6c1a30cbaf50d00a9856077a7f6a4238b0b1738/28686B，全保管offline/admission_review。首review文字匹配断言失败属中文跨行的reviewer脚本问题，初源和说明保留；原工具traceback未独立保存成console，不伪造原件。根实际命令 rtk proxy /usr/bin/python3 -B /tmp/mr3_p2a0_v24_final_root_static_v1.py exit0：210实际SHA、196旧exact/2明确源更新/12新、原34门/608/596/71.97839368507266成本、8PythonAST/27当时JSON/187文档链接及actual782dgzip均PASS。此为worktree静态准备，无实际冻结准入或新native。接下来short checks、git diff --check及git add -n .后commit/push，再以报告/launch_commands准确Conda命令做实际冻结前检；唯一四阶段parent必须等待该PASS。\n')
paths = ['AGENTS.md', 'ros2_ws/ros2-multi-robot-automap/AGENTS.md', 'ros2_ws/ros2-multi-robot-automap/user_guide.md', 'ros2_ws/ros2-multi-robot-automap/launch_commands.md', 'ros2_ws/ros2-multi-robot-automap/src/multi_robot/src/mr3_ray_box_corrector.cpp']
prefix = str(W.relative_to(ROOT))
paths += [prefix + '/' + name for name in ('AGENTS.md', 'RESEARCH_PLAN.md', 'IMPLEMENTATION_PLAN.md', 'MR3_ENV_CONTRACT.md', 'log.md', 'mr3_learning/audit_ppo.py', 'report/README.md', 'report/20261018_mr3_p2a0_v24_install.md', 'report/assets/20261018_mr3_p2a0_v24_install')]
status = subprocess.check_output(['git', '-c', 'core.quotepath=false', 'status', '--porcelain', '-uall'], cwd=ROOT, text=True)
for line in status.splitlines():
    path = line[3:]
    assert any(path == item or path.startswith(item + '/') for item in paths), line
subprocess.run(['git', 'diff', '--check'], cwd=ROOT, check=True)
dry = subprocess.run(['git', 'add', '-n', '.'], cwd=ROOT, text=True, capture_output=True, check=True)
Path('/tmp/mr3_p2a0_v24_precommit_add_dry_v1.txt').write_text(dry.stdout + dry.stderr)
Path('/tmp/mr3_p2a0_v24_precommit_pathspec_v1.json').write_text(json.dumps({'paths': paths, 'untracked_in_scope_only': True, 'diff_check_exit': 0, 'actual_git_add_n_exit': dry.returncode, 'dry_lines': len(dry.stdout.splitlines())}, indent=2) + '\n')
print(json.dumps({'status_paths': len(status.splitlines()), 'actual_git_add_n_lines': len(dry.stdout.splitlines()), 'pathspec_count': len(paths), 'diff_check': True}))
