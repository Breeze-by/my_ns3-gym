import json
from pathlib import Path

ROOT=Path('/home/zhuyulab/ns3-workspace')
W=ROOT/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
ROS=ROOT/'ros2_ws/ros2-multi-robot-automap'
report='20261018_mr3_p2a0_v25_smoother.md'
cn='V25已构建官方1.1.20平滑器的节点时钟修复，仅改两个timer及include；实际stock/fixed组件对照与独立复核通过，暂停输出7/3→0/0，原参数及安全/任务门保持。累计572.9355761036277/18000；尚待新clean pushed冻结的完整四阶段与原34正式门，不授P2A.0/PPO信用。V24及所有旧FAIL保留。'
en='2026-10-18: V25 canonical Nav2 1.1.20 overlay changes only two timer factories plus include to node clock. Actual stock/fixed component pair and independent review passed (paused output7/3 versus0/0); all parameters and task/body/stop gates retained. Engineering debit572.9355761036277/18000. Full same-freeze four-stage/34-gate matrix remains pending; P2A.0 incomplete, no PPO. All prior failures preserved. See wireless-rl/report/'+report+'.'
for p in (ROOT/'AGENTS.md',ROS/'AGENTS.md',W/'AGENTS.md'):
    text=p.read_text()
    lines=text.split('\n\n')
    index=next(i for i,s in enumerate(lines) if s.startswith('2026-10-18: V24') or s.startswith('V24冻结'))
    lines[index]=en if p!=W/'AGENTS.md' else cn+'见[V25](report/'+report+')。'
    text='\n\n'.join(lines)
    if p==ROOT/'AGENTS.md':
        old='/usr/bin/python3 /usr/bin/colcon build --symlink-install --allow-overriding nav2_bringup\n'
        assert text.count(old)==1
        text=text.replace(old,old.replace('nav2_bringup','nav2_bringup nav2_velocity_smoother'),1)
    p.write_text(text)
for p in (W/'RESEARCH_PLAN.md',W/'IMPLEMENTATION_PLAN.md',ROS/'user_guide.md',ROS/'launch_commands.md'):
    text=p.read_text()
    parts=text.split('\n\n')
    index=next(i for i,s in enumerate(parts) if s.startswith('V24冻结'))
    link='report/'+report if p.parent==W else '../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/'+report
    parts[index]=cn+'见[V25]('+link+')。'
    text='\n\n'.join(parts)
    if p.name=='IMPLEMENTATION_PLAN.md':
        old='未完成；V24安装生效但tb2角速FAIL；修正平滑器仿真时钟后新冻结完整重验，所有旧FAIL保留'
        assert old in text
        text=text.replace(old,'未完成；V25节点时钟组件对照通过，待同冻结完整四阶段；原门与所有旧FAIL保留',1)
    if p.name=='launch_commands.md':
        old='/usr/bin/python3 /usr/bin/colcon build --symlink-install --allow-overriding nav2_bringup\n'
        assert text.count(old)==1
        text=text.replace(old,old.replace('nav2_bringup','nav2_bringup nav2_velocity_smoother'),1)
        text+='''

## MR3-P2A.0 V25 节点时钟覆盖包

从官方1.1.20导入的 `src/nav2_velocity_smoother` 由正常 ament overlay 选择。
完整构建须允许覆盖此包；仅构建该包的命令如下（本次已执行，不作为矩阵重试命令）：

```bash
source /opt/ros/humble/setup.bash
cd /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap
export PYTHONNOUSERSITE=1
/usr/bin/python3 /usr/bin/colcon build --symlink-install --packages-select nav2_velocity_smoother --allow-overriding nav2_bringup nav2_velocity_smoother --cmake-args -DCMAKE_BUILD_TYPE=RelWithDebInfo -DCMAKE_EXPORT_COMPILE_COMMANDS=ON -DBUILD_TESTING=OFF
source install/setup.bash
```

实际package/launch executable/ldd已核为canonical新库。组件对照只验证timer机制；
完整四阶段仍待新冻结准入，不能由本构建或历史PASS授予P2A.0完成信用。
'''
    p.write_text(text)
p=W/'report/README.md';text=p.read_text()
marker='| [P2A.0 V24 安装生命周期]'
assert marker in text
text=text.replace(marker,'| [P2A.0 V25 平滑器节点时钟]('+report+') | 两timer最小修复及实际组件对照 | 组件/库来源通过，完整四阶段待新冻结；P2A.0未完成 |\n'+marker,1)
p.write_text(text)
(W/'report'/report).write_text('''# MR3-P2A.0 V25：平滑器节点时钟

2026-10-18；P2A.0尚未完成。用户要求继续完成本准备步骤；无新pilot、P2B或gateway。
本版针对V24实测平滑器在暂停仿真时间时继续累计OPEN_LOOP输出的时间接口缺陷。

官方Nav2 1.1.20（commit `a097086719c88f781aa59788eca29ac6ca5e56db`）单包保留
上游源码与Apache许可证，仅在激活和动态频率重配的两个timer factory改用节点clock，
增加create_timer include。没有改动约束算法、参数、驱动、候选、actor、奖励或任务门。

实际canonical包构建一次通过，68.82491580815986墙秒；原六个MR3库的stat/SHA未变。
核心库`ceedf1b35cc501e9caa655c5b0a66f538395893664ec683a6290760f37d60b52`，
standalone executable `0a5bf913f698dc0f43f57bd06a3f87d35a06e1b8366709576084b4afca5d6c5a`。
正常ament package解析、Launch executable解析及ldd均指向canonical overlay。
实际probe编译一次通过，44.30459033790976墙秒；编译分别列为源码准备成本。

同一真实C++组件探针各运行stock/fixed一次，均自然exit0和正常cleanup，保存PID/start均gone。
原版20/10Hz暂停输出分别7/3，修复版0/0；两处timer的is_steady分别true/false。
实际加载映射、单一非零publisher GID及输出caps通过独立读取；修复版观测到的相邻
20Hz回调最大增量.02500000000000001/.16000000000000003，10Hz为.05/.32，
仅按声明4ULP减法舍入容差判断该有限回调序列。此结果不证明连续dv/dt、机体安全或任务完成。

stock实际2.0057054478675127、fixed实际1.1961737689562142墙秒，合计3.201879216823727
计入工程余额：累计572.9355761036277/18000，余17427.064423896372。完整矩阵尚待
新clean pushed冻结和真实Conda前检；不得拼接不同冻结PASS。原四stage/12episode、
608 API上限/596脚本动作与34正式门保持，首FAIL后续SKIP。pilot1870决策/
2905.954739546403墙秒余额未使用；无GPU训练调用。

选定原件：[组件与构建](assets/20261018_mr3_p2a0_v25_smoother/component_probe/selected_manifest_v1.json)、
[实际ELF](assets/20261018_mr3_p2a0_v25_smoother/build_evidence/selected_elf_manifest_v1.json)、
[官方源码准备](assets/20261018_mr3_p2a0_v25_smoother/source_preparation/handoff_v1.json)。
全部V24失败与后续SKIP保持原义，见[V24报告](20261018_mr3_p2a0_v24_install.md)。
''')
print('Updated prospective V25 documents; no matrix PASS claimed.')
