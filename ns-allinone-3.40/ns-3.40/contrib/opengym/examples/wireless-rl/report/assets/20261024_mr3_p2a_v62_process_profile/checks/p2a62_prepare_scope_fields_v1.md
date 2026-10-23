# A62 固定scope producer（准备源码，未执行）

将 `/tmp/p2a62_prepare_scope_draft_v1.py` 原样安装为 `W/report/assets/20261024_mr3_p2a_v62_process_profile/prepare_scope_v1.py`，从 W 目录执行：

```sh
rtk proxy /usr/bin/python3 -B -m report.assets.20261024_mr3_p2a_v62_process_profile.prepare_scope_v1
rtk proxy /usr/bin/python3 -B -m report.assets.20261024_mr3_p2a_v62_process_profile.prepare_scope_v1 --admit
```

默认独占写 `scope_prepared_v1.json/admitted=False`；`--admit`独占写 `scope_v1.json`。两者不覆盖旧文件。`--admit`仅接受canonical全23测试proof/真实root reap/actualwait/JUnit和新canonical snapshot恢复；私有13/10结果不提供canonical执行信用。producer自身没有继承这23项测试信用，root可在实际source-bound CPU下执行它。此处不运行producer、native、旧activity、模型或科学reader。

字段与固定约束：

- `schema/diagnostic_profile/run_root`：与root最终parent和helper API一致；固定open101、1worker、三机器人、8个普通合法probe决策，无学习入口。
- `resource`：parent1800/native1500/close120/review最大300；close包含在native1500内，reader实际由parent按min(240,remaining−60)准入，升级/后核全费，不承诺HRT。
- `previous_accounting`与工程额：V61 ledger6554B/SHA6e9e…，U108886.5066566616018/C150000/R41113.4933433383982，预约1800；pilot/final保持，不声称数值用户批准。
- `expected_launcher_argv_template`：固定ns3gym Python/module/`--freeze __EXECUTION_FREEZE__`。ROS三角色与reader仍system Python。
- `source_bindings`：每行仅绝对canonical `path/bytes/sha256`，兼容parent的完整字典相等检查。取current production `source_inventory`、旧A60 plan keys的当前字节、新A62所有顶层.py/basepins、旧A61 helper/ledger、旧A60plan/nativebinding/buildbridge、必要build16 ROOT源与真实历史回执。旧plan hash不作当前source信用。scope本身由parent单独current/Git核，不造成自引用。
- `library_bindings`：旧10个actual native ELF当前字节等旧actual，以及system/learner两个resolved Python ELF，恰12行。别名lstat/readlink/resolution只明示为准备时观测，不冒称parent逐项重核别名；不扩读342 maps。
- `old_build_reuse`：完整历史20清单/manifest/actualbuild receipts绑定；仅16 ROOT输入作为本轮current Git源。4个外部历史build工具不执行、不重读当前值、不冒称before/after runtime准入；无A62新build或新native科学信用。
- `canonical_cpu_evidence`：权威 `checks/canonical_cpu_v1/proof_v1.json` 与其actualwait/JUnit/source recovery，核6个canonical test文件实际argv、23/FES0、new source snapshot恢复及与current bytes相等；记录被覆盖的具体runtime子集，不把封源当全库执行信用。
- `prepared_at_git_HEAD_not_execution_freeze/requires_new_clean_pushed_execution_freeze`：本次制作的HEAD是来源说明；最终执行仍须新commit/push且HEAD=origin、clean，不能把C或旧E当A62执行freeze。
- `scientific_qualification/capacity_qualified/automatic_pilot_final_entry_allowed/P2A_complete`均False；optimizer/pilot/final新增0，旧FAIL保持。

未运行生成器或新增测试；root统一安装后实际执行。producer不写任何policy计划、也不调用旧run函数。
