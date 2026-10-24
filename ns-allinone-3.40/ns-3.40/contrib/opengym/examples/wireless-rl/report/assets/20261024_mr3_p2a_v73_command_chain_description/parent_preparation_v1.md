# V73 单流命令链描述父入口（pending）

仅 `/tmp` 软件准备；没有打开原始 motion、旧两输入、342库、World 或 PPO。规范 namespace 固定 `20261024_mr3_p2a_v73_command_chain_description`。实际业务字段、统计与七解释源由 Native 的 consumer 定义，本 parent 不推断 plant 原因，也不提供科学资格。

固定父 CLI 为 `/usr/bin/python3 -B -m report.assets.20261024_mr3_p2a_v73_command_chain_description.run_description_v1 --freeze NEW_EXACT_PUSHED_G`，在无线实验工作目录执行。独占状态 `/tmp/mr3_p2a_v73_parent_v1`；consumer 固定为同 namespace 的 `describe_motion_chain_v1 --freeze G --spec A73/description_spec_v1.json --output /tmp/mr3_p2a_v73_command_chain_description_v1.json`。没有任意命令/输入参数、重试或自动后继。consumer v2 39230B/SHA77d6c905f6b96466cf2405e9590e86ec1e0e68059bbd8b691772a2032eff38bf、Root refs3110B/SHAdc76a9a1b401df01c1cc41b9d957898a0c5b7a8c6f27950c4cb043a5133ed9f9已真填；缺pin仍会先拒绝；正式准入只来自冻结 spec.admitted，附属 scope draft 只是说明文档。

保留 A72 成熟 same-PID bootstrap→真实子进程 wait→source postcheck 的结构。首 module-entry时钟、PID/start、bootstrap exec 与真实回收绑定，完整parent300秒/work240秒、派生输出最多4MiB；合作式工作界和事后实际费用界不冒称硬实时。全部gap及source前后/recovery计入连续parent，nested和Root工具墙时不重复加。身份/start未证时费用只能为lowerbound/unknown累计；失败/partial/真实rc全保留。parent/consumer两份原保存身份需后继Root真实reap+fresh absence；祖先不是owned，不claim全树gone。

必须分开的三个冻结：

- 原生证据 `evidenceG=b3707dcf258c832f35ef60f47a5dc8dc52296629`：V71 Root65935 rc1，输入所描述的原activity为False。
- 前账 `previousLedgerG=74c8f710114bac3c2c91a5a1df8ebc6c63ec7637`：V72 Root64500 rc0/完整5.727286974秒，description-only PASS，ledger.activity_passed与description_passed均True，original_activity_passed仍为`{present:true,value:false}`。规范前账6593B/SHA `cd620cc88978991f6de366f281e8ce458f07379552abad59ba3886f3319078ab`，现在位于 `/tmp/p2a72_closed_copyready_v1/closure_ledger_v1.json`，规范目标A72/closure_ledger_v1.json。
- 新执行G：Root后继安装所有绑定regular文件后，commit/push并核clean HEAD==origin==CLI G。它不是以上两个旧G的别名。parent会分别检查旧证据G、前账G、actual previous ledger和新Git所有实际字节，不能强制前两者相同或将前描述PASS当原nativePASS。

入场U112586.9296634976018/C180000/R67413.0703365023982，原pilot/final不加；本次预约工程300秒。capacity、scientific qualification、P2A与auto-policy均False。原FAIL不改判。

Native 已封的实际 runtime闭包26份：consumer+20解释源（真实producer链的13 ROS Python源、driver C++与六个project headers；最终全路径/字节以Native manifest为准），再加spec、parent自己、A71 opaque inventory、A72 ledger、A72 fixed-motion refs（A72/checks/v73_fixed_inputs_v1.json）。本次已核20解释源+consumer，若以后新增解释依赖须新封版本而不能漏绑；parent不会为复用旧13计数删依赖。最终N+5全部current/Git前后核字节并保存恢复blob。唯一motion原件507221955B必须完全排除父source/metadata哈希集合；整文件单遍读取、完整SHA/严格JSON/统计由未来consumer独占。实际完整SHA/stat只能来自Root库存/refs，当前不填截断SHA或猜值。

Root父/consumer schema约定已经定稿：consumer output `mr3-v73-fixed-motion-command-chain-description-v1`，`original_activity_passed`保原nativeFalse的presence对象；`previous_description_passed`为真实bool True，`original_evidence_freeze`及`previous_description_execution_freeze`分别为上述两个旧G。原input proof数组只有这一输入。`engineering_budget_candidate`仍为固定300/240与实际新U/R，`previous_accounting.expected_execution_freeze`明确指V72。父输出保真实消费字节与unknown区别，不把opaque复制或metadata观察谎称零字节。

人工测试源码只检查未准入先拒、实际6593B关闭账的正门/混G及错误PASS负例、bootstrap PID/start与未知账户、完整301秒费用FAIL。这些测试不调用实际consumer。最早AST草稿与后续正式CPU证据应分开保留；最终consumer/source/ref pin齐后，才封最终SourceManifest并运行一次隔离CPU。Root实际新freeze准入之后才允许这一次命令链原件描述，不启动新rank或新World。

本父v2仅前向consumer新pin：Native v1对合法重复odom的本地input_sequence误作内容冲突，v2按原message SHA去重并记录callback/duplicate数量，消息真实冲突仍失败。父v1在实际CPU提交前已STOP，零CPU信用；其代码/初始审查/来源blob与Native原12P全部保留。本父v2逻辑逐字同v1，仅consumer SHA/bytes常量改变；即将用本字节跑4组CPU。
