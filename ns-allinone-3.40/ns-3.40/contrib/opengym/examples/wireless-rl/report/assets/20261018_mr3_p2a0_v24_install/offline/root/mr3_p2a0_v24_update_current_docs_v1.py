from pathlib import Path

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
ROS = ROOT / 'ros2_ws/ros2-multi-robot-automap'
cn = 'V24修复WorldCreated安装阶段的无效计数读取：保留Load-before-Init回调，以有定义的加载/传感器状态和零时钟准入，iteration明确null而不伪造零；Running实值仅记录。实际新库782d与源码f826及固定审计绑定已准备，原数学/1ms/停车/安全/95%门不变。原V23联合guard具体失败分项未观测，全部FAIL保留。累计71.97839368507266/18000，须新clean pushed冻结完整四阶段重验；P2A.0未完成、无PPO。见[V24](report/20261018_mr3_p2a0_v24_install.md)。'
for p in [W / name for name in ('AGENTS.md', 'RESEARCH_PLAN.md', 'IMPLEMENTATION_PLAN.md')] + [ROS / name for name in ('user_guide.md', 'launch_commands.md')]:
    lines = p.read_text().splitlines()
    indices = [i for i, line in enumerate(lines) if line.startswith('V23冻结9160543e真实前检')]
    assert len(indices) == 1, (str(p), indices)
    lines[indices[0]] = cn if p.parent == W else cn.replace('(report/', '(../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/')
    p.write_text('\n'.join(lines) + '\n')
en = '2026-10-18: V24 repairs undefined preInit iteration measurement in the existing WorldCreated callback. Counter is explicitly unavailable/null; source-bound Load-before-Init flags/clock0/noSensors and actual ODE150/.001 remain required. Running is recorded, not a thread-start gate. Actual new SO782d/sourcef826/fixed auditorcc467064 prepared; all math/stopping/safety/95% unchanged. V23 individual failing guard branch was not measured; all failures retained. Prior71.97839368507266/18000, new clean pushed full4stage remains necessary. P2A.0 incomplete/no PPO. See wireless-rl/report/20261018_mr3_p2a0_v24_install.md.'
for p in (ROOT / 'AGENTS.md', ROS / 'AGENTS.md'):
    lines = p.read_text().splitlines()
    indices = [i for i, line in enumerate(lines) if line.startswith('2026-10-18: V23 9160543e actual preflight')]
    assert len(indices) == 1
    lines[indices[0]] = en
    p.write_text('\n'.join(lines) + '\n')
p = W / 'IMPLEMENTATION_PLAN.md'
text = p.read_text()
old = '| MR3-P2A.0 | 生命周期、候选及安全执行、参与观测准备 | 未完成；V17 reset真实停车FAIL保持；V22修正RayBox并选择quick150工程候选，待新冻结完整四阶段重验 |'
new = '| MR3-P2A.0 | 生命周期、候选及安全执行、参与观测准备 | 未完成；V24修复安装生命周期测量，RayBox/quick150候选须新冻结完整四阶段重验；V17/V23失败保留 |'
assert text.count(old) == 1
p.write_text(text.replace(old, new))
p = W / 'report/README.md'
text = p.read_text()
needle = '| [P2A.0 V23 显式解释器]'
assert text.count(needle) == 1
row = '| [P2A.0 V24 安装生命周期](20261018_mr3_p2a0_v24_install.md) | 修正preInit计数测量并绑定实际新库 | SDK/构建/窄CPU与独审通过；新冻结完整矩阵待准入 |\n'
p.write_text(text.replace(needle, row + needle))
p = ROS / 'launch_commands.md'
with p.open('a') as output:
    output.write('''

## MR3-P2A.0 V24 安装阶段修复与完整准备矩阵

以下在wireless-rl目录执行；须新代码提交推送、工作树干净并完成源码审查。
先以固定Conda运行真实完整预检：

```bash
env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B report/assets/20261018_mr3_p2a0_v24_install/independent/mr3_p2a0_v24_buildproof_preflight.py
```

通过后将EXACT40替换为本次完整冻结SHA；先启动只读monitor并确认START，再另终端启动唯一parent。

```bash
env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B report/assets/20261018_mr3_p2a0_v24_install/independent/mr3_p2a0_v24_cross_stage_mapping_monitor_v1.py --freeze EXACT40
env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B report/assets/20261018_mr3_p2a0_v24_install/independent/mr3_p2a0_v24_run_matrix_v1.py EXACT40
```

benchmark/完整审计仍由绑定源码使用固定Conda，parent和ROS读者使用系统Python。
新domain198/200/202+203/206、port13701/13711/13721+22/13731；原四阶段/34门/12episode/608 API/596脚本决策保持。
工程18000墙秒累计先扣71.97839368507266，所有native和必需消费者及monitor自然结束前不改源码、库或Git。
失败保留并跳过后续stage，不在同冻结重试。此命令用于训练前工程验收；P2A.0证据提交推送并获用户验收后才进入训练。
原启动/物理/任务门及pilot余额不变，见[V24报告](../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261018_mr3_p2a0_v24_install.md)。
''')
print('Current route/guides/commands updated; new full matrix remains pending.')
