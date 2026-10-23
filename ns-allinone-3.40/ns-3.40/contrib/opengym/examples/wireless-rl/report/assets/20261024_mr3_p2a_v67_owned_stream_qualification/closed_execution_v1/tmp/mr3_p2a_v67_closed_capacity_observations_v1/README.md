# V67 已闭合小 metadata 的实际容量观察

固定 formal freeze `50c740a64754aaa2dc3f2707cf5b0159eb929a28`，plan SHA `feb5330fbacfa6925a7b57674204ab7e356e1e3fbb2a614086dd6236ccf041d0`。Root 独占实际 tool57699，本观察者不 poll/reap/signal 它，不改 canonical，不启动 policy/World/native/reader/tests，不读科学 raw、full科学result或旧 pstats。

`observe_closed_metadata_v1.py` 每次只检查固定四stage的 `native.json` / `stage.json` 是否出现；只有原实际 `subprocess_waited` native receipt 完整后，才读其声明的 closed `benchmark_summary.json`，整SHA对真实output_sha256。stage完整后只读 stage metadata 和各已经实际wait的 command JSON 回执，不运行或重新解读科学审计。每份输入必须是普通文件、≤预先固定2MiB、结尾换行且读时stat稳定；每个新milestone输出只创建一次，不覆盖历史。代码只是本 `/tmp` 定向观察工具，不能作为新科学资格gate。

输出命名 `<stage>_native_closed_v1.json` 和 `<stage>_stage_closed_v1.json`，都有整输入 path/bytes/SHA；scope分别明确native闭合但whole stage可能活动，或stage闭合但whole root parent可能活动。保存原 `passed/status/returncode/errors/skipped_audits`，不改判。观察者不给 Root actual tool reap、全部source/ELF稳定或full parent fee独立结论。

native事实包括每EP真实startup/transition/整EPwall、actual dt合计和0-dt个数、wall/task秒、正常/forced/failed shutdown及remaining arrays。原source没有独立closure wall timer，因此 `pure_closure_wall_seconds=null`，整EP−startup−transition标为**混合残余**，包括closure和其它未分别计时工作，不能冒精确关闭耗时。

stage事实包括原stagewall/实际derivedcap、全部audit actualwait墙时及身份/源profile关联、小回执整SHA、full wait、native结束→最后审计wait结束endpoint、firstauditspawn→lastauditwait endpoint，以及原registry的required role状态。并行reader和watcher重叠，不把nested秒数叠加到parent实际费；这些endpoint也不代替完整root parent或最终归档关闭费用。

原policy预算不变：minimum总1800/native ceiling1150；pilot总2905.9547395464029，含外finalizer300，main2605.9547395464029/native ceiling2100；final总9000含外300，main8700，内tail最低500，真实native最多8200−prework（字面8500被同原总额约束收紧）。没有用这些预算启动任何policy；capacity始终False、automatic policy entry始终False。各完成样本的startup、推进、日志量、audit关键链/尾部余量可供Root后继真实容量报告参考，1/2 worker短stimulus不能保证3并行长RL任务或PPO完整审计容量。

完整minimum→pilot→final入口、checkpoint固定/冻结物理scale/0 eval updates/三strict95和原安全质量合取见先前准备 `/tmp/mr3_p2a_v66_policy_handoff_preparation_v1/README.md`，其V66活动实际结果不能转给V67；这里只继承规范接口和原预算。任何unknown维持null，任何旧FAIL保持。此目录没有capacity=True或P2A完成声明。

## 本次实际已经闭合的结果

interface native实际wait **rc1 / passed=False / 911.312135158s**；原benchmark summary为62,358B/SHA `ae2ea4599ac0a93d4874dc282aee89052e5885a714fe2949098fa7d93442035b`，逐字匹配真实receipt output SHA。单EP真实32/32 transitions、dt合计32.0任务仿真秒；startup128.67949695512652s，transition773.4199208840728s，推进比24.169372527627275 wall秒/任务秒，整EP910.6216051066294s，混合残余8.52218726743008s。worker rc0、非forced、非failed_sample，remaining process/zombie数组空。这些是该有界刺激的实际成本，不是原生阶段PASS或性能因果结论。

原失败为 `preparation_abort.first_failure.kind=rpc_or_worker_exception`，reason `ValueError('bounded v2 stimulus coverage unavailable; no retries or gate reduction')`，epoch `mr3_p2a_reach_v67_interface_w0_e1_b97b4084`；`wall_limit_exceeded=False`、`cleanup_error=None`。原字段另存 `interface_native_status_detail_v1.json`，不读原始日志追因，不把32返回改成PASS，不据此重判V60物理失败。

interface stage实际 **FAIL / 927.515981244s / within_stage_wall_allocation=True**，`audits={}`，原`skipped_audits=[]`；没有full或其它科学reader的实际提交/wait。required role对应的passed均未知/缺项，不以false或PASS替补，不虚构审计耗时0。terminal/reset/deadline的原matrix status均为SKIPPED、reason=prior_failure_or_insufficient_balance，没有其native/EP/审计成本。

matrix outer实际wait **rc1 / 946.733745287s / source_unchanged=True**；matrix summary自身charged wall946.426180947s、all_submitted_children_waited=True、within_matrix_wall_allocation=True。两者由实际coordinator PID/start join。**这不是 Root tool57699 的实际reap或完整连续parent fee**；外层qualification/absence/post-source/最终关闭和全部费用仍由Root保存。native、stage、matrix这些嵌套秒数不相加。

现有证据没有完整full audit/尾部成本，没有300秒deadline样本，也没有3并发长RL负载。minimum/pilot/final未由本观察启动，容量资格仍False。本次目录已经封停写，最终SHA清单见 `manifest_v1.json`。
