import hashlib
import json
from pathlib import Path
import shlex
import shutil

ROOT=Path('/home/zhuyulab/ns3-workspace')
W=ROOT/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A=W/'report/assets/20261018_mr3_p2a0_v25_smoother'
for source,name in [(Path('/tmp/mr3_p2a0_v25_probe_api_independent_review_v1'),'api_independent_review'),(Path('/tmp/mr3_p2a0_v25_actual_probe_independent_review_v1'),'actual_independent_review')]:
    handoff=json.loads((source/'handoff_v1.json').read_text())
    dest=A/name;dest.mkdir(exist_ok=False)
    for key in ('review','manifest','archive'):
        row=handoff[key]
        raw=Path(row['source']).read_bytes()
        assert hashlib.sha256(raw).hexdigest()==row['sha256']
        (dest/row['name']).write_bytes(raw)
    shutil.copyfile(source/'handoff_v1.json',dest/'handoff_v1.json')
probe=json.loads((A/'component_probe/execution_v1.json').read_text())
assert probe['passed'] and probe['actual_probe_child_wall_seconds']==3.201879216823727
command='rtk proxy env -u PYTHONPATH /bin/bash --noprofile --norc -e -c '+shlex.quote('source /opt/ros/humble/setup.bash\nsource /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/install/setup.bash\nexport PYTHONNOUSERSITE=1\nexport PYTHONDONTWRITEBYTECODE=1\n/usr/bin/python3 -B '+shlex.join(probe['argv']))
entry='''

## 2026-10-18 MR3-P2A.0 V25：节点时钟覆盖包与真实stock/fixed组件对照

源码基底`94a5e26b99402e49b4e116931f8b8f625e603b0d`，执行时worktree含本版未提交
官方包及固定两timer补丁；source manifest/实际SHA保存在选定原件，不冒称clean freeze。
无训练/checkpoint/GPU、无Gazebo或环境API；不使用任务种子。原95%/300s、三台参与、
候选/actor/reward和全部原安全/速度/停车门不变。V24失败保持，不重跑失败冻结。

实际命令（每项各一次；后两编译/解析脚本内完整system ROS命令见同名选定源码/收据）：

```bash
rtk proxy /usr/bin/python3 /tmp/mr3_p2a0_v25_build_overlay_v1.py
rtk proxy /usr/bin/python3 /tmp/mr3_p2a0_v25_compile_probe_v1.py
rtk proxy /usr/bin/python3 /tmp/mr3_p2a0_v25_resolve_overlay_v1.py
'''+command+'''
```

canonical包构建PASS68.82491580815986墙秒；所有六个现有MR3库stat/SHA严格不变。
probe编译PASS44.30459033790976墙秒；两编译单列源码准备成本。正常ament/Launch/ldd
解析PASS，实际standalone/core选中canonical overlay。组件各stock/fixed一次均exit0，
normal_cleanup true，保存PID/start在wait后消失。原版paused20/10Hz输出7/3，修复版0/0；
两timer实际is_steady原版true、修复false，actual加载ELF/dev/inode/SHA与单一非零GID核实。
独立读取的fixed相邻回调增量在事先说明的4ULP减法舍入容差通过；无连续dv/dt/body证明。

stock2.0057054478675127+fixed1.1961737689562142=3.201879216823727实际墙秒计入工程预算，
累计572.9355761036277/18000，余额17427.064423896372。实际pair总wrapper3.728948475793004
另列不重复计入；没有信号、重试、超时kill或孤儿。pilot余额1870/2905.954739546403未用。

选定原件：[V25报告](report/20261018_mr3_p2a0_v25_smoother.md)、
[组件manifest](report/assets/20261018_mr3_p2a0_v25_smoother/component_probe/selected_manifest_v1.json)、
[ELF manifest](report/assets/20261018_mr3_p2a0_v25_smoother/build_evidence/selected_elf_manifest_v1.json)、
[独立actual审查](report/assets/20261018_mr3_p2a0_v25_smoother/actual_independent_review/handoff_v1.json)。
API静态审查发展稿引号SyntaxError/初seal-atime比较错误、原版官方来源网络记录保留各自原件；
这些不是作者包编译/probe失败。无正式矩阵PASS，P2A.0未完成；待新clean pushed冻结四阶段。
'''
with (W/'log.md').open('a') as f:f.write(entry)
p=W/'report/ARCHIVE_INDEX.json';d=json.loads(p.read_text())
d['clarifications'].append(dict(recorded_date='2026-10-18',review_base_commit='94a5e26b99402e49b4e116931f8b8f625e603b0d',report=str((W/'report/20261018_mr3_p2a0_v25_smoother.md').relative_to(ROOT)),affected_reports=[str((W/'report/20261018_mr3_p2a0_v24_install.md').relative_to(ROOT))],scope='V24 FAIL remains unchanged. V25 replaces two Nav2 wall timers with node-clock timers; single real stock/fixed component comparison passes. No complete same-freeze matrix/PPO credit yet. Selected source/build/component originals are canonical A25.'))
p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
print('Copied independent seals and appended actual preparation experiment log.')
