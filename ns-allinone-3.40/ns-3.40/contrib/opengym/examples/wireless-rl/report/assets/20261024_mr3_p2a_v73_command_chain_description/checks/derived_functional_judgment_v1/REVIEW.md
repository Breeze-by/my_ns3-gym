# V73 功能判断：先取证 Reach D→X 拒绝，不改 authority/plant

仅用停止的V73派生JSON（2554234B，SHA `e467364d394108cd7acb0953663922d4f040cd38ffdb0785bdc66b62fe205c81`）。完整原件读取507221955B，parse/semantic/record-sequence gap均0；本分析未重开任何原motion、drive或其他raw。旧native FAIL与V73 description-only PASS保持分开。

**单一下一切入层：Reach 的 D→X 启动准入/实际 rejected checks。** 不能据此宣布安全公式有bug或放松R/STOP。两个机器人本身收到的是转向请求；第三台有足量前进请求，却被该具体转换分支拒绝。先核哪个peer/anchor/集合条件阻断，才选输入/调度或实现修复；暂不改rank、warmup窗口或plant，也不再读drive。

重点窗口 `[44.72,49.72)`（commit到期后、cleanup前），每机250个tick，全部EXACT_RAW_REQUEST、authority ACTIVE/normal_reach、ready=True，请求最大age40ms：

| 机器人 | raw→effective | Reach output | 原因 |
|---|---|---|---|
| tb1/tb2 | 250/250均 `[0,-.3]` | 逐tick原样 `[0,-.3]` | reach_clear各250；未收到正线速度，不能归因authority/Reach压掉其平移 |
| tb3 | 250/250正v且原样进入effective，237条v≥.08，最大.182895 | 250/250线速度0 | linear_brake_preserve_requested_turn223，reach_transition_envelope27；发布intent/tracker均D |

较宽cleanup前 `[39.72,49.72)` 每机500tick：tb1/2各498条可用raw的v全0，余2条原始请求缺失；tb3有287条正v（267≥.08），effective保留这些正v，所有output v仍0。故不是authority把tb3正v清掉。

可审原行指针（原行内容仅来自新derived中的引用，未重读原件）：

- tb1 clock44.72/decision2111，raw行74276→decision行74321；tb2 raw74277→decision74323。
- tb3 clock44.78/decision2114，raw76140→decision76181：`[.0828947,.0452632]`→同effective→`[0,.0452632]`，reason=linear_brake_preserve_requested_turn。
- tb3 clock46.18/decision2184，raw84228→decision84270：`[.178947,0]`→同effective→`[0,0]`，reason=reach_transition_envelope。

源码 `mr3_reach_runtime.py:496–520` 将这两reason定位为D角色尝试带bridge reserve的X转换，prospective pair `geometric_necessary`不全满足；只有原D证书完整时保留原请求的w。compact derived未保存具体rejected checks、完整own/peer安全表与anchor，因此哪个约束失败仍UNKNOWN，不能把正确保守制动直接改为放行。

整个输出窗39.72–51.72每机353条APPLIED均与Reach target、storage精确join，body target线速度均0，没有first_positive_body_target。**这不等于双轮motor为0**：原w/转向rim仍存在；tb1/2的极小正rim均值不是有意义前进，且原写轮/readback未在此审计。没有“正平移已APPLIED但plant不走”的支持证据。

tb1/2上游长时间纯转与大初始bearing相容，但Nav2内部路径切向/控制器状态和unstamped raw的goal generation仍UNKNOWN。只换成142也不能保证覆盖：tb3候选2约.3967m、几乎直前，可能5秒承诺前自然SUCCEEDED；不能按角度或min-path给新资格。

未来如有证据支持，可显式新版本允许有界自然完成warmup/较长观测布局；额外暖身GOAL必须真实记录且不算qualified。每机器人仍须两次真实GOAL→满足原正v/新增path且合法moving WAIT→真实取消/三fresh rest及3秒HOLD/等待交棒→下一GOAL，保5秒承诺、原perANDjoint、B/R/STOP/contact与完整科学门，不刷新anchor或rearm初始servo，不伪造时钟/自然终态。现在仅保存该约束，**下一实际活动只做V74拒绝条件提取**。
