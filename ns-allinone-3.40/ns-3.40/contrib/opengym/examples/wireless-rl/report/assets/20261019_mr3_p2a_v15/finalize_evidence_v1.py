"""Assemble only actual, already waited CPU/build results; no experiments."""
from pathlib import Path
import hashlib
import json
import re

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A = Path(__file__).resolve().parent
required = ['ros_full_attempt_v3', 'learning_entry_cpu_attempt_v2',
    'information_reader_cpu_attempt_v2', 'runtime_reader_cpu_attempt_v1',
    'actor_boundary_cpu_attempt_v1', 'cpp_tests_attempt_v1', 'final_ros_build_attempt_v1']
rows = []
for path in sorted((A/'checks').glob('*/actual_wait.json')):
    data = json.loads(path.read_text())
    assert data['actual_waited'] and data['source_unchanged']
    console = Path(data['console']['path'])
    assert hashlib.sha256(console.read_bytes()).hexdigest() == data['console']['sha256']
    rows.append({'name':path.parent.name,'actual_returncode':data['actual_returncode'],
        'passed':data['passed'],'actual_child_wait_seconds':data['actual_child_wait_seconds'],
        'receipt':str(path.relative_to(A)), 'receipt_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
        'actual_argv':data['actual_argv'],'cwd':data['cwd'],'source_unchanged':True})
by_name={r['name']:r for r in rows}
for name in required:
    assert by_name[name]['passed'] and by_name[name]['actual_returncode']==0
    data=json.loads((A/by_name[name]['receipt']).read_text())
    for binding in data['source_after']:
        assert hashlib.sha256(Path(binding['path']).read_bytes()).hexdigest()==binding['sha256'], binding['path']
index={'schema':'mr3-p2a-v15-cpu-build-validation-index-v1','opening_commit':'1a5af58013f46f8638a2803e30f618eff044c4d6',
       'source_scope':'Uncommitted implementation snapshots are exact per attempt; no native/source-freeze qualification is inferred.',
       'final_required':required,'runs':rows,'native_runs':0,'gpu_calls':0,'native_admission':False,
       'historical_failures_preserved':True,'full_new_profile_qualification':False}
with (A/'validation_index_v1.json').open('x') as f:json.dump(index,f,ensure_ascii=False,indent=2);f.write('\n')
final=(A/'checks/ros_full_attempt_v3/console.log').read_text()
count=int(re.search(r'(\d+) passed in',final).group(1))
lines=['| Check | Actual result | Child wait (s) |','| --- | --- | --- |']
labels={'ros_full_attempt_v3':f'{count} ROS semantic cases PASS','learning_entry_cpu_attempt_v2':'100 learning entry/legacy cases PASS (CPU only)',
'information_reader_cpu_attempt_v2':'18 synthetic information cases PASS','runtime_reader_cpu_attempt_v1':'19 synthetic execution cases PASS',
'actor_boundary_cpu_attempt_v1':'1 fixed-tensor boundary case PASS','cpp_tests_attempt_v1':'3 GTest suites / 29 cases PASS','final_ros_build_attempt_v1':'Actual final C++/ROS incremental build PASS'}
for name in required:
    r=by_name[name];lines.append(f'| [{name}](assets/20261019_mr3_p2a_v15/{r["receipt"]}) | {labels[name]} | {r["actual_child_wait_seconds"]} |')
report='''# MR3-P2A V15：已批准安全契约的生产接线与CPU/编译准备

用户“批准”接受V14科学候选后，本轮实现显式`mr3-reach-v1`及两个版本化独立必要审计器。
**P2A未完成：本轮无Gazebo/ROS任务采集、GPU调用、pilot或final-only验证，新profile尚无完整原生资格。**
[批准原文与不变预算](assets/20261019_mr3_p2a_v15/contract_acceptance_v1.json)、
[生产契约](../MR3_REACH_CONTRACT.md)和[完整实际argv/失败索引](assets/20261019_mr3_p2a_v15/validation_index_v1.json)为本轮入口。
准备在opening `1a5af58013f46f8638a2803e30f618eff044c4d6`之上的工作源码运行；每次精确快照/SHA/stat另存，不能冒充一次原生冻结矩阵。

## 实现与边界

驱动保留原七字段目标、九字段存储ACK、paired slew及轮更新数学；新增同次全部SetParam成功返回后的typed应用回执，
以及同源完整原odom和实际float32 c/s的校准消息。实际配置展开新feed header SHA；编译禁止fast-math/FMA，原生线程检查RN/非FTZ/非DAZ。
应用回执证明写入调用返回成功，不证明身体响应。精确[接口原件](assets/20261019_mr3_p2a_v15/native_feed_interface_v2.json)保留author未运行范围；实际build见下表。

Information真实订阅模式/校准，把安全sidecar放进原同一state envelope/send/delivery；完整三机表和单条引用均绑定原始内容。
peer、motion与worker以v2相位消费同一实际bundle；输出的新intent refs与本轮已消费表SHA严格区分。
中央节点仍是三个逻辑本机guard，Humble来源诚实标为graph_at_callback，不宣称packet身份或P3网络隔离。

执行器保留所有原始/坏源/tail、固定锚、完整累计路径诊断，严格检查20ms raw及34ms应用水位。
D/N采用2R，X桥采用4R；raw WORLD与map完整证书分别计算后AND。
H/D责任保留原T，未实际消费的微小目标不能退锚或清terminal；实际应用还须严格更晚raw才能退休旧责任。
finite-H完整路径必要下界不扩成无限terminal L1门，固定terminal disk仍持续检查。

三机准入全部完成后才发布本轮输出；第三台故障会同时压零前三台，避免递归stop半轮输出。
D原证书通过而X额外余量不足时，仅保留请求原角速度并归零平移，不选择heading或宣X。
实际回执先于存储ACK到达时保留event并等待，不关闭物理水位；矛盾ACK仍永久故障。
actor/candidate/mask/map/reward接口不增加sidecar渠道，新增整snapshot及固定tensor不变反例已检。

## 实际验证

'''+ '\n'.join(lines)+'''

全部表列命令由有限runner真正child.wait()，记录PID/start、完整argv/cwd/env、单调钟及前后源码绑定。
子进程总耗时不与最后一次tool poll耗时混用。CPU SB3测试有合成CPU优化，不是机器人训练、GPU更新或pilot样本。
最终完整ROS检查排除三个原style/lint文件，未把这些排除项记PASS；没有另行编造全CI通过。

失败完整保留：首轮pure为42PASS/4FAIL（缺peer、故障未锁、raw/cali洞）；ROS首次因未source canonical install而collection rc2；
第二次416PASS/21FAIL（20个numpy协方差标量+1个legacy fixture版本字段），修后438PASS。
完整首轮1374PASS/5FAIL：新增真实feed打破旧“整段源码不变”测试、已存在绝对gzserver入口与测试不一致、两个旧fixture缺recorder ready、一个H测试漏计下一次真实消费。
原测试源及每轮FAIL均在快照内；修后先1380PASS，最后收尾改动再完整重验。
跨topic反例真实2PASS/2FAIL后修为缺证据等待、矛盾永久故障；学习侧首试因conda没有pytest rc1，改用已有unittest，不安装依赖。
所有历史V12速度峰、V13矩阵/optional/minimum累计漂移FAIL及V14原型FAIL不改判；旧V14资产未改。

## 尚未取得的资格与预算

两个新reader只是必要叶，不替代peer云/scan、完整full汇合、参数读回、cadence/FIFO、实际ELF custody、输入/接触/停止覆盖与关闭。
[只读路由评审](assets/20261019_mr3_p2a_v15/qualification_routing_review_v1.md)逐项指出旧v1/source锁；
当前旧preparation组合和PPO对新profile的拒绝有意保留，不能剥metadata或借旧38/38放行。
须先完成新版角色路由、CPU反例及清洁提交冻结，再开始完整同冻结原生复验；本报告不称该调度已接通。

工程仍31596.4775930946018/34000墙秒，余2403.5224069053982；本轮CPU/build准备单列，没有增加或借用原生/pilot额度。
pilot仍1870决策/2905.9547395464029墙秒，三场final-only开发验证及P2B/gateway状态不变。
[预算提案](assets/20261019_mr3_p2a_v15/engineering_budget_proposal_v1.json)请求累计上限34000→52000（增加18000墙秒），**尚未获批**。
若获批可用20403.5224069053982；预约matrix18000、fresh16 minimum1800、外部final/尾账300，余303.5224069053982。
依据是旧V13完整分段实际费用约14672.891703579秒（仅成本参考，无新源信用），其中deadline一项7023.863327403已超过现余额。
新阶段预算包括全部已提交消费者真实wait和关闭；任何必需门FAIL即停止后续，超额照实计FAIL并收费，不自动重试。
minimum必须等新版完整资格通过；pilot/final-only仍受原余额和终态条件约束。本次没有启动这些步骤。
'''
(W/'report/20261019_mr3_p2a_v15.md').write_text(report)
marker='## 2026-10-19 MR3-P2A V15：获批契约生产接线、CPU/build与资格边界'
log=W/'log.md';old=log.read_text();assert marker not in old
entry='\n\n'+marker+'\n\n用户本轮原文“批准”，候选SHA b1443df121a5ba1af0ff8c55417294bd8fd246fc85463776e1ce022c1752a043；opening Git1a5af58013f46f8638a2803e30f618eff044c4d6，working源码逐次精确快照；无新原生冻结/任务采集、GPU或pilot/验证。生产实现与失败边界见[报告](report/20261019_mr3_p2a_v15.md)。\n\n逐次实际完整command argv/cwd/env、真实child.wait、PID/start、elapsed和前后source/stat均在[唯一索引](report/assets/20261019_mr3_p2a_v15/validation_index_v1.json)所指actual_wait.json；各console与源快照同目录，不补造未知rc。以下为逐次实际实验记录：\n\n| Run | Actual rc | Child wait s | Scope |\n| --- | --- | --- | --- |\n'
for row in rows:entry+=f'| [{row["name"]}](report/assets/20261019_mr3_p2a_v15/{row["receipt"]}) | {row["actual_returncode"]} | {row["actual_child_wait_seconds"]} | CPU/build only; source stable |\n'
entry+='\n最终ROS '+str(count)+' PASS；学习入口100、信息审计18、执行审计19、tensor边界1、C++29 cases/3 suites PASS。所有首轮FAIL、collection rc2和无pytest rc1原样保留，修复因果见报告。合成CPU优化不是native/GPU/PPO pilot信用。原shared log仅追加、V14原件及所有历史FAIL保持。\n\n工程31596.4775930946018/34000，余2403.5224069053982；pilot1870/2905.9547395464029及三final-only未动。新profile完整qualification dispatcher/其他v2角色尚须接通，旧38/38不得复用，PPO仍拒新profile；没有假称P2A完成。预算提案34000→52000（增加18000）尚未批准，详情[原件](report/assets/20261019_mr3_p2a_v15/engineering_budget_proposal_v1.json)。\n'
log.write_text(old+entry)
print(json.dumps({'runs':len(rows),'final_ros_cases':count,'required_passed':len(required),'native_admission':False}))
