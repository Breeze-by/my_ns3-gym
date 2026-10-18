from pathlib import Path
import shutil

ROOT=Path('/home/zhuyulab/ns3-workspace')
W=ROOT/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
ROS=ROOT/'ros2_ws/ros2-multi-robot-automap'
A=W/'report/assets/20261018_mr3_p2a0_v25_smoother'
with (W/'report/20261018_mr3_p2a0_v25_smoother.md').open('a') as f:
    f.write('''

源码准入与执行声明已收口：[最终计划](assets/20261018_mr3_p2a0_v25_smoother/predeclared_plan_v25.json)
SHA `27a5027c930e2d805187ea9e7d53fd16e797ab395c0931c4b76f707a1f6ae051`，
222个独立source bindings，原34正式回执/12episode/608API/596脚本动作保持。
actual CLI派生并校验每个worker的domain/port，避免V24未使用元数据不同步的问题。
新平滑器准入核官方两timer逆、实际构建/压缩库和每轮三台实际进程映射；旧门不替换。
观察器START/SUMMARY新增自身真实PID/start，避免再次遗漏此身份。

作者最初fixture遗漏group/session的3FAIL、sealed v1/v2、PID复用Zombie反例以及后续窄修
全部保留。最终21项针对CPU通过；独立复核确认PID复用硬拒、同身份自然关闭仅pending且
无credit，不吞源/hash错误。根又执行原16学习审计单元（7.736638186965138墙秒）及一个
canonical位置真实source/build/archive检查（.880315454211086墙秒），均通过；没有重复
21套、ROS170套或旧SDK测试。六编排静态逆/原34/metadata/fatal lint通过1.484900236595422秒。
ENV保留先前50061原字节并追加2038字节；共享loader仅三个ENV常量、固定新verifier和
一个调用，精确逆后恢复原`cc467064…`，没有旧validator/数学放宽。

[独立准入复核](assets/20261018_mr3_p2a0_v25_smoother/custody_independent_review/handoff_v1.json)、
[部署检查](assets/20261018_mr3_p2a0_v25_smoother/deployment_checks/checks_v1.json)、
[root最终计划收据](assets/20261018_mr3_p2a0_v25_smoother/root_preparation/final_plan_receipt_v1.json)
保留范围区别。此时仅source-ready；实际新freeze前检与全矩阵尚未执行，不授原生PASS。
''')
with (ROS/'launch_commands.md').open('a') as f:
    f.write('''

V25完整准备矩阵按以下绑定入口执行一次，必须是clean pushed main；同冻结失败不重试。
在wireless-rl目录执行实际学习侧前检：

```bash
export PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1
env -u PYTHONPATH /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B report/assets/20261018_mr3_p2a0_v25_smoother/independent/mr3_p2a0_v25_buildproof_preflight.py
```

前检PASS后，在独立终端先启动只读watcher；保存的START回执出现后，在另一个终端
启动唯一parent。两处使用同一clean pushed exact40（下例从HEAD取得）：

```bash
MR3_V25_FREEZE=$(git rev-parse HEAD)
env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B report/assets/20261018_mr3_p2a0_v25_smoother/independent/mr3_p2a0_v25_cross_stage_mapping_monitor_v1.py --freeze "$MR3_V25_FREEZE"
```

```bash
MR3_V25_FREEZE=$(git rev-parse HEAD)
env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B report/assets/20261018_mr3_p2a0_v25_smoother/independent/mr3_p2a0_v25_run_matrix_v1.py "$MR3_V25_FREEZE"
```

parent串行执行interface32、terminal2、reset双worker共8x32、deadline300KEEP，原34门
逐stage全部drain；首FAIL阻止后续，累计工程墙秒不重置。源/库/Git须保持到原生、正式
reader和watcher全部自然结束及原件封存。P2A.0实际PASS并获用户验收后才进入训练。
''')
with (W/'log.md').open('a') as f:
    f.write('''

### 2026-10-18 V25新源码准入/有限CPU检查与完整矩阵预声明

同一未提交准备worktree，最终module6edeb3a7…、auditor7d1a1a70…、ENV41feac9a…；
尚无新原生freeze/PASS。作者v1 fakeproc缺group/session的3FAIL保留；18修复检查、
v2增PIDreuse-Z及canonicalmanifest路径的19检查、v3增sameworker-Z/empty与reuseworker-Z
的21检查依次实际通过。新增检查只修本helper分类：sameidentity合法关闭pending/no credit，
reuse及wrongargv/hash硬拒。作者CPU通过wall分别2.157729092054069/2.19473171280697/
2.2367755016312003；实际命令与stdout/stderr/缺失原console的范围分别见封存原件，
未伪造最初direct-tool stdout。独立新反例旧e890红/8e08绿保留，不重跑作者套件。

根实际命令：`rtk proxy /usr/bin/python3 /tmp/mr3_p2a0_v25_root_deployment_checks_v1.py`，
脚本绑定的Conda命令原16 auditor单元PASS（测试2.599秒/进程7.736638186965138墙秒），
一个canonical安装位置真实source/build/archive测试PASS（进程.880315454211086墙秒）。
选定[检查收据](report/assets/20261018_mr3_p2a0_v25_smoother/deployment_checks/checks_v1.json)
保存exact argv/SHA/console。无SDK/ROS/DDS/native/GPU调用，不重跑旧170套。
RT六编排static逆/34门/workerhelper/fatal lint PASS（一次1.484900236595422墙秒），
初机械发展稿、旧source与原检查全部保留[57成员封包](report/assets/20261018_mr3_p2a0_v25_smoother/matrix_preparation/handoff_final_v1.json)。

root闭合review copy v1误假定两handoff共用name/archive键，KeyError前只建空目录；
v2按实际API manifest/source basename完成，无source/bin修改或实验重跑。原v1/v2/helper
与显式错误说明保存在root_preparation，不把工具发展错误改记为作者/probe/native失败。

最终[计划](report/assets/20261018_mr3_p2a0_v25_smoother/predeclared_plan_v25.json)
27a5027c930e2d805187ea9e7d53fd16e797ab395c0931c4b76f707a1f6ae051，222source
bindings；原34/12episode/608API/596脚本动作/18000累计预算不变，携带572.9355761036277。
各stage命令保持原工作量，domain208/210/212+213/216，port13801/11/21+22/31，均由actualCLI
生成typed worker元数据并在三个入口交叉验证。source-ready仍需新clean pushed exact40
实际Conda前检，随后先watcher START再唯一parent；任何FAIL后续SKIP，不同冻结PASS不拼接。
无训练/pilot/P2B/gateway，本段不声称完整矩阵已运行。
''')
shutil.copyfile(Path(__file__),A/'root_preparation'/Path(__file__).name)
print('Recorded actual checks and conditional exact matrix commands.')
