from pathlib import Path

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
ROS = ROOT / 'ros2_ws/ros2-multi-robot-automap'
report = W / 'report/20261018_mr3_p2a0_v24_install.md'
lines = report.read_text().splitlines()
assert lines[2].startswith('**状态：准备阶段')
lines[0] = '# MR3-P2A.0 V24：安装生命周期修复及实际角速失败'
lines[2] = '**状态：V24整体FAIL；后三阶段按预声明SKIP，P2A.0仍未完成。** 安装修复实际生效，110/210冻结准入通过；接口轮返回14条step后，tb2真实角速度越过原1.2上限，执行模型拒绝下一步。全部原件与强制失败样本清理保留，不在同冻结重试。'
text = '\n'.join(lines) + '\n'
text = text.replace('- **PENDING**：新clean commit/push、实际782d ELF与Git/worktree宏/归档身份、正确conda learner entry的真实准入。', '- **已实际完成**：新clean pushed冻结5d684c46的110/210完整Conda准入与实际782d加载；这不覆盖后续真实角速FAIL。')
text = text.replace('- **PENDING**：同一新freeze完整interface→terminal→reset→deadline，原mandatory、每EP loaded corrector/ODE maps、installed/callback ledger、真实原生运动/停车与严格退出全部闭合。', '- **未完成**：完整四阶段。V24 interface失败后terminal/reset/deadline全部SKIP；必须修复后用新冻结整套重验。')
text += '''

## 实际冻结与失败闭合

唯一执行冻结 `5d684c46f9f99a867a94f1fed8c52e923e2486ef` 已推送。
实际Conda完整预检exit0/18.76524052489549wall，110runtime/210independent及3个真实imports/help通过，
回执 `bd92102f0342af129e42b8bea26328942ddcac47040002266eb92b726cf9ca9b`。
monitor先完成START，再于2026-10-18 00:13:49 UTC启动唯一完整parent；原源码/库/Git保持冻结至所有读者结束。

Gazebo实际installed记录确认phase/null计数/全部可用preInit字段、150/.001；
真实callback发生，最终process_lifetime_summary共762781 calls、callback_errors=0。
九个Nav2参数服务实际读回通过，reset在sim42返回；接口随后保存14条完整step，dt均1秒。
step请求16/action888在sim56.98收到normal_control_model_invalid，未返回该步，不补造transition或任务终态。

直接触发是tb2 source56.968的raw angular=(0,0,-1.206191435678961)，仅12ms源龄，
超过原fullnorm1.2；不是把参数读回PASS当作实测速度PASS。
三机此前均已有A制停信用，tb1/tb2也有B；平面/chord无>.30，采样角加速度均<7。
故障后约.20秒尾窗的missing_rest不能被称作已证超过.78秒，但唯一实际角速越界已经足够FAIL。

11个提交的正式job全部wait：6PASS/5FAIL；10个mandatory回执5PASS/5FAIL，
runner_errors=[]且all_submitted_jobs_finished=true。
parent自然exit1、monitor自然exit0，terminal/reset/deadline按原规则SKIP。
[闭合核验](assets/20261018_mr3_p2a0_v24_install/closed_native_review_v1/mr3_p2a0_v24_final_closure_observation_v1.json)
确认44个原生保存身份及加父级后的48个PID/start均fresh absent。
39个launch原生进程退出0、native_stop/server与清理子回执通过，
仍完整保留supervisor forced_shutdown=true/failed_sample=true/worker_returncode=-15；整体strict closure未通过。
生命周期修复局部生效不授完整P2A.0或正常episode关闭信用。

## 上游时间接口归因

[有界驱动原件](assets/20261018_mr3_p2a0_v24_install/closed_control_forensic_v1/context_summary_v1.json)
确认110个真实target均在.20/.8内、64次actuation精确使用latest tuple。
55.574–56.662目标为(0,-.8)，随后转前进转向；峰值时desired=(.2,-.378947)，
实际轮差代理-1.224470、施加轮差代理-1.101559、body=-1.206191。
零storage发生在56.98故障之后；此窗口没有角向符号反转，不能将越界归因于后续cancel。
paired helper原数学通过，有限步长从超界实测轮速回向目标并不保证body瞬态不越界。

[独立raw/guard核验](assets/20261018_mr3_p2a0_v24_install/closed_body_review_v1/raw_guard_smoother_review_v2.json)
确认24个普通decision均clear、无component_filter且finaloutput等于绑定raw_request；故跃迁已在上游输入。
56.66 raw(0,-.8)到56.68(.1,-.631579)，选入raw sequence3550→3556，
20ms sim间隔对应.299825384s wall。这里只逐值核验所选latest记录，未冒充读完全部中间publication。
实际smoother包1.1.20-1jammy.20260326.004635，OPEN_LOOP20Hz/.5/3.2配置与API读回保持。
[对应Humble源码](https://api.nav2.org/nav2-humble/html/velocity__smoother_8cpp_source.html)
两处使用wall timer且每callback按accel/frequency积分，与暂停仿真时的限速前提不符。
这确立了需要修正的时间接口；物理接触/滑移/servo机制尚未唯一分离，不按比例外推新cap保证。
下一版本将先验证官方单包的仿真时钟timer修复，保持.8请求cap、1.2实测及全部原门，
再在新冻结完整重验；本版不声称该修复已经执行或充分。

另于执行后库存发现旧plan.worker_bindings仍留V23的188/136xx元数据，实际stage CLI/原件为198/13701。
旧六协调器均不读取该字段；旧plan原件不改写，此声明不一致及源审漏项保留。
下一版本必须由实际stage command与worker index派生并交叉验证所有domain/port，不能继续机械继承残值。

## 唯一证据与成本

[完整原件封存](assets/20261018_mr3_p2a0_v24_install/native/manifest.json)
SHA3c776e11…：513原件318062459B，518无损parts共20573758B；
307个native原件与206个metadata原件全部逐字往返，末whole SHA/stat稳定。
522个封存文件按每part声明的prospective_canonical复制至interface/metadata，避免额外native嵌套。
[打包支持](assets/20261018_mr3_p2a0_v24_install/closed_pack_support_v1/handoff_v1.json)
保留精确argv/实际preflight三入口/所有真实FAIL与后续SKIP。

本次launch receipt497.7553032017313wall，加prior71.97839368507266，累计569.733696886804/18000，
余17430.266303113195。parent launch区间498.1903878697194、formal288.55652650492266、
封存12.170313973911107等CPU/编排成本另列，不重复加计native。
pilot1870决策/2905.954739546403wall余额不动；无新PPO/GPU调用、无95%策略信用。
'''
report.write_text(text)
cn = 'V24冻结5d684c46实际准入110/210及安装/参数读回通过，但14个返回step后tb2 raw角速1.206191>原1.2，整体FAIL、后三SKIP。48保存身份gone/39原生exit0与forced失败样本清理分别保留，strict close未通过。上游raw在20ms sim跳0→.1，guard原值放行；Humble平滑器walltimer时间接口待下一版修复并完整重验，全部原门/.8cap保持。累计569.733696886804/18000，无PPO。见[V24](report/20261018_mr3_p2a0_v24_install.md)。'
for p in [W / name for name in ('AGENTS.md', 'RESEARCH_PLAN.md', 'IMPLEMENTATION_PLAN.md')] + [ROS / name for name in ('user_guide.md', 'launch_commands.md')]:
    lines = p.read_text().splitlines()
    matches = [i for i, line in enumerate(lines) if line.startswith('V24修复WorldCreated安装阶段')]
    assert len(matches) == 1
    lines[matches[0]] = cn if p.parent == W else cn.replace('(report/', '(../../ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/')
    p.write_text('\n'.join(lines) + '\n')
en = '2026-10-18: V24 freeze5d684c46 actual preflight110/210 and installed preInit fields/ODE150/.001 passed, but tb2 raw1.206191>original1.2 after14 returned steps. OverallFAIL/later3SKIP;48 saved identities absent/39 native exits0 do not replace forced/failedsample/worker-15 strictcloseFAIL. Exact raw input jumps0→.1 within20ms sim and guard passes it unchanged; actual Humble smoother walltimer timing needs new-version repair. No .8cap/body/safety/task reduction or PPO;569.733696886804/18000 charged. See wireless-rl/report/20261018_mr3_p2a0_v24_install.md.'
for p in (ROOT / 'AGENTS.md', ROS / 'AGENTS.md'):
    lines = p.read_text().splitlines()
    matches = [i for i, line in enumerate(lines) if line.startswith('2026-10-18: V24 repairs undefined')]
    assert len(matches) == 1
    lines[matches[0]] = en
    p.write_text('\n'.join(lines) + '\n')
p = W / 'IMPLEMENTATION_PLAN.md'
t = p.read_text()
old = '| MR3-P2A.0 | 生命周期、候选及安全执行、参与观测准备 | 未完成；V24修复安装生命周期测量，RayBox/quick150候选须新冻结完整四阶段重验；V17/V23失败保留 |'
new = '| MR3-P2A.0 | 生命周期、候选及安全执行、参与观测准备 | 未完成；V24安装生效但tb2角速FAIL；修正平滑器仿真时钟后新冻结完整重验，所有旧FAIL保留 |'
assert t.count(old) == 1
p.write_text(t.replace(old, new))
p = W / 'report/README.md'
t = p.read_text().replace('SDK/构建/窄CPU与独审通过；新冻结完整矩阵待准入', '真实安装生效；14步后角速越界FAIL/后三SKIP，待平滑器时钟修复')
p.write_text(t)
p = ROS / 'launch_commands.md'
t = p.read_text().replace('## MR3-P2A.0 V24 安装阶段修复与完整准备矩阵', '## MR3-P2A.0 V24 历史失败命令（不重跑）')
p.write_text(t)
with (W / 'log.md').open('a') as f:
    f.write('''

### 2026-10-18 — V24真实完整入口执行、角速FAIL与全部闭合

源码冻结5d684c46f9f99a867a94f1fed8c52e923e2486ef已推送，finalplan d682f40c01a660f598cdf6c81d9faa640c25af1ba87d9e96e56701bb2fec4ffc。先actual完整Conda预检：rtk proxy env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B /tmp/mr3_p2a0_v24_run_actual_preflight_v1.py，内层准确argv为固定Conda -B report/assets/20261018_mr3_p2a0_v24_install/independent/mr3_p2a0_v24_buildproof_preflight.py，cwd wireless-rl。exit0/18.76524052489549wall，110runtime/210independent/3真实imports-help通过；receipt bd92102f0342af129e42b8bea26328942ddcac47040002266eb92b726cf9ca9b。四个特别选存offline/build证据文件被opengym build/ ignore匹配，提交前显式dryrun和-f逐四路径加入，未加入运行build树。
实际monitor命令同环境 /usr/bin/python3 -B report/assets/20261018_mr3_p2a0_v24_install/independent/mr3_p2a0_v24_cross_stage_mapping_monitor_v1.py --freeze 5d684c46f9f99a867a94f1fed8c52e923e2486ef，stdout/stderr重定向/tmp/mr3_p2a0_v24_cross_stage_mapping_parent_console_v1.log。确认真实START后，于00:13:49UTC执行同环境 /usr/bin/python3 -B report/assets/20261018_mr3_p2a0_v24_install/independent/mr3_p2a0_v24_run_matrix_v1.py 5d684c46f9f99a867a94f1fed8c52e923e2486ef，console/tmp/mr3_p2a0_v24_matrix_parent_console_v1.log。所有原生/11正式任务/monitor结束前source/bin/Git均不变。actualstage CLI为fixedConda -u -m mr3_learning.benchmark --workers 1 --schedule open:101 --steps 32 --preparation-motion-probe --preparation-probe-version mr3-p2a0-outward-cancel-v6 --base-domain 198 --base-port 13701 --output-root /home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0 --run-id mr3_p2a0_20261018_v24_interface --preparation-parameter-review；所有逐leaf实际argv/cwd/环境/exit/原console在唯一封存metadata。
actualcorrector phase/null/可用preInit字段/native150/.001安装通过，first_actual_callback及outside-nearparallel真实出现，最终762781calls/error0；实际9参数服务读回PASS。reset release sim42/startup132.2021218878217wall，14返回step各dt1，总有效14；request16/action888在56.98失败未返回，不补造样本/任务terminal。首fault tb2 source56.968，full raw angularz-1.206191435678961>1.2，源龄12ms。normal_control_model_invalid/infrastructure_failure原样保持。
11formal实际全wait：6PASS5FAIL；10mandatory5PASS5FAIL，errors[]/alljobsfinishedTrue。peer/drive/input/settled/information回执PASS，control/angular/physics/full/closure回执FAIL。parentexit1/monitorexit0，后terminal/reset/deadline按声明SKIP。39原生launch进程均exit0，44native保存身份及加父级48PID/start freshgone；但supervisorforced_shutdownTrue/failed_sampleTrue/worker-15仍strictcloseFAIL，native_stop/server_clean/infrastructure_cleanup局部PASS不能洗掉它。独立闭合script rtk proxy /usr/bin/python3 -B /tmp/mr3_p2a0_v24_final_closure_observation_v1.py，exit0、读取/核源体.5589912836439908wall，review63b889da5…，131输入末SHA/stat稳定；根session exit证据和watcher未记录PID/start局限明确，未伪造。
有界driver过滤仅一遍3个大原件，初筛选script失败及修正原件均保管closed_control_forensic_v1；110incoming目标均≤.20/.8，64actuation exactlatesttuple。55.574–56.662 pureCW(0,-.8)，56.68转mixed，峰时desired(.2,-.378947)、current轮差proxy-1.224470、applied-1.101559、body-1.206191；56.98零storage为故障后果，不把先前越界归cancel/角反转。paired helper数学原PASS不证明physicalbody界；contact/slip/servo机制未唯一归因。独立physical/angular原leaf确认planar/chord≤.30、采样角加速度<7，三机此前已有A制停信用（tb1/tb2还有B）；故障后.20s尾窗缺rest不是已证.78违界，实际唯一angularhard超限仍独立FAIL。
独立raw_guard_smoother_review_v2 f51df929…确认24普通tb2decision clear/filterNone/output逐值等rawrequest，1faultstop分列；56.66raw0→56.68raw.1，selectedsequence3550→3556/.02sim/.299825384wall，未将selectedlatest冒充所有中间pub。实际SDK1.1.20-1jammy.20260326.004635，OPEN_LOOP20Hz/.5/3.2读回PASS单列；官方1.1.20 timer源码支持walltimer/每callback积分接口缺陷。原URL20s TimeoutError、探索KeyError与未单存console范围均保留于36原件552aca68…/191596B支持包，不重试网络或重跑formal。下一版优先实测仿真时钟timer修复，原.8cap/1.2body/其他原门全部保持，尚无修复充分性或新矩阵PASS。
执行后库存发现V24未使用worker_bindings元数据仍188/136xx，而实际CLI及运行198/13701，原source审查漏项保留、不回改旧plan；下版从实际command+workerindex派生并强制一致校核。该发现不替代已有真实角速失败。
一次完整选存command/source及逐--extra精确argv见closed_pack_support_v1，rtk proxy env -i PATH=/usr/bin:/bin PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 LANG=C.UTF-8 LC_ALL=C.UTF-8 TZ=UTC /usr/bin/python3 -B /tmp/mr3_p2a0_v24_matrix_pack_proposal_v1/mr3_p2a0_v24_matrix_pack_closed_v1.py --freeze 5d684c46f9f99a867a94f1fed8c52e923e2486ef --target /tmp/mr3_p2a0_v24_selected_closed_v1 --all-writers-closed [逐原文件--extra清单保管原argv，未用未展开glob]，12.170313973911107wall；513原件318062459rawB→518parts20573758encodedB，max2429072B，各part/whole decodedSHA与末stat均PASS。522选存文件按prospective_canonical逐part复制A24/native/interface及metadata，不额外嵌套native；初rootcopy误猜manifest basename、resume guard漏改两个仅copy脚本失败保留，v3逐字续拷完成550件22401348B，不重跑任何原生或科学审计。
本次native launch receipt497.7553032017313wall，prior71.97839368507266，累计569.733696886804/18000，余17430.266303113195；parentlaunch498.1903878697194、audit288.55652650492266及其他CPU/封存另列，不重复计费。pilot1870/2905.954739546403不动，无GPU/PPO/P2B/gateway。P2A.0未完成；保持全部FAIL，修复后新clean pushed冻结完整四阶段，成功证据提交推送再待用户验收。
''')
print('V24 actual failure/source evidence and current route recorded; no new source implementation.')
