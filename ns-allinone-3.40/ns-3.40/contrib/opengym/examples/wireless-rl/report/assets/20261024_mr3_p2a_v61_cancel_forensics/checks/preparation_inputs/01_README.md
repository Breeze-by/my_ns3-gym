# V61 可安装候选：仅 /tmp staging，尚未执行

目录 `files/` 含恰好三源和两个 JSON。所有 canonical 目标位于：

`/home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261024_mr3_p2a_v61_cancel_forensics/`

| 文件 | 内容与状态 |
| --- | --- |
| cancel_window_extract_v3.py | 38260B，SHA `860b69ca4bf755da4af411f6f7a8ccb870329ee6f8f96c9d5254c26da072ee1e`；按已审 v3 原字节复制 |
| run_cancel_forensics_v1.py | 保留v1的CONSUMER一处改动，另只联动新A61目录日期；原 parent 的CONSUMER `cancel_window_extract_v2.py`→`cancel_window_extract_v3.py`；canonical guards、660 parent/480 work/600 owned stop、always wait 与费用规则保持 |
| test_cancel_forensics_v1.py | 8case 相关人工 CPU 草稿；旧7改 canonical 文件名及完整spec的反例准备，第8覆盖 v3 原路径相等及 parent 拒旧freeze/dirty Git；未执行 |
| extraction_spec_v1.json | 五份 exact original plain pins/identity、真实旧库存与关闭证明、v3 consumer、新资源限额已填；admitted=false |
| scope_v1.json | 真实旧ledger pin、canonical v3、parent及依赖共25运行时源预期pin已填；admitted=false；input_spec bytes/SHA必须最终admit后重算 |

本次仅在 /tmp 读写 staging；未安装 Root、未打开/读取/哈希任何实际 raw、未运行 reader/main/CPU、未提交。三个 Python 仅 AST、两个 JSON 仅解析与关联检查，不提供 canonical CPU 或科学资格信用。旧7case信用仅绑定旧 v2 `cc2930...`；不能借给 v3。

五原件：adapter.jsonl、motion_safety.jsonl、drive_tb2.jsonl、odometry_tb2.jsonl、launch.log，exact原始目录/路径按旧库存逐项固定，encoded总pin=decoded总pin=523777922B。各 decoded_byte_limit 等其原始字节，decoded SHA 等 encoded SHA。全局encoded/decoded cap各1073741824B；line=8388608B、每file2000000行、selected_records=12000、selected_raw_bytes=25165824B、output=67108864B、work=480秒，complete parent660秒。output恰等parent64MiB cap，未超出。行数/最大行长/选中数未知，这些是 raw 消费前的资源声明，不是完成保证；超限仍 INCOMPLETE/全费，不自动补读重试。

旧证据冻结 E=`935b466bd076002afdfe161b55a508938de2a8b0`。两窗、epoch、tb2、两个 goal、49.86秒 next-goal事实边界及16解释源均保持。库存的gzip-mtime0-lossless是归档容器codec；输入仍是原始plain identity，不读canonical重压wrapper。

安装/准入顺序：根的V60 closure commit/push须先真实完成；随后安装本五候选（仍unadmitted）并执行新的canonical 8case CPU/source-before-after/current/recovery/actualwait/freshgone。CPU人工路径使用新生成tiny文件和synthetic metadata，只做函数契约，不消费V60原件。若失败保存原attempt，不覆盖。根最终admit spec后重算其精确bytes/SHA进入scope.input_spec，再admit scope，封存/推送新的clean精确freeze；必须与旧E不同，且真reap完成后HEAD==origin/main/clean，才能进行一次正式有限取证。

将来相关CPU的最短核心 argv（当前未运行）：`/usr/bin/python3 -B -m unittest discover -s <canonical A61> -p test_cancel_forensics_v1.py -v`。仍需由根以现有实际wait/source稳定/身份关闭证明包装，不能把此建议argv当真实回执。

完整目标路径、每文件bytes/SHA、AST函数和未执行的8case清单见 staging_manifest_v1.json。本清单不能提供admission，也不能把V60工程关闭PASS变成原活动科学PASS。

日期联动v2：2026-10-24，仅新A61目录由20261023改为20261024，并重算由此改变的parent SHA及scope driver binding。旧V60/E路径、原件pins/解释源/limits不变；consumer和8case测试原字节均未变。staging_v1所有原件保留。未执行/安装/raw消费。
