# MR3 P2A V63：两份启动阶段 profile 的有限描述

V63 已完成代码与绑定准备，尚未读取原 pstats。它只解释 V62 失败后留下的两份主线程文件，不启动新仿真、不重判 V62，不授予八步性能、容量或科学资格。

[V62 实际闭合](20261024_mr3_p2a_v62_process_profile.md)保留 startup motion 相位 10 秒墙钟 guard 失败、0 个 task transition、worker forced -15。现存 motion main 和 adapter main 共 894940B；adapter encoder 未观测，worker 无 finished，五 lane 不完整。两份文件仍来自失败的、被 profiling 扰动的启动阶段，不能推算完整任务成本。

本轮固定原路径和由原 finished 元数据、[闭合库存](assets/20261024_mr3_p2a_v62_process_profile/closed_inventory_v1.json)共同绑定的 bytes/SHA；每份最多1MiB、合计2MiB，metadata 另限8MiB。consumer 对每份原 pstats 只做一次整读，在同一内存字节上核 SHA 并解码。描述函数只取原冻结 `81e63f50699073286c9773dcb92106de63fdf4ca` 中已验证的两个纯 AST 函数，绑定整个源文件，不执行原 full reviewer，也不重开原 raw logs。

完整 parent 预约120秒、consumer work60秒；后者 deadline 取 min(now+60, parent_start+90)，升级等待和来源复核共享剩余时间，完整实际超额全费 FAIL，不承诺硬实时。bootstrap 保存实际 PID/start 和 nonowned 祖先，exec 后核同一对象；未知起点或旧账不能生成虚假累计。原 pstats 排除在 parent pre/post hash 列表之外，确保解码消费仍只由 consumer 单次完成。

入场承接 [V62 规范末账](assets/20261024_mr3_p2a_v62_process_profile/closure_ledger_v1.json)：`U109067.3998164526018/C150000`，余额`40932.6001835473982`。pilot/final 原额不动，capacity=False，P2A 未完成。根因保持 UNKNOWN，等待实际描述后再选择优化；不扩大旧 guard，不重试 V62。

临时 v1/v2/v3、其准入绑定变化和人工 CPU 原件保持。安装后 canonical 4 项人工 CPU 已实际通过：工具85309真实 reap0、0.720401189秒，75来源 before/after/current 与恢复快照一致，两个保存 CPU 身份 fresh-gone；测试只用人工数据和早拒路径，未运行 reader main 或读取原 profile。见 [canonical CPU 证明](assets/20261024_mr3_p2a_v63_profile_description/checks/canonical_cpu_v1/proof_v1.json)。scope/spec 的 admitted=True 不代替新精确 Git freeze、真实 push 和正式来源核验。 私有三版及外部人工fixture共301 regular/24983672B、17目录、2个链接已[完整封存](assets/20261024_mr3_p2a_v63_profile_description/checks/preparation_history_v1/final_manifest_v1.json)为9307653B；链接只保literal/lstat、不跟随目标。归档工具32902真实reap0、6.562421634秒，306来源稳定、三个保存身份fresh-gone，工程新增0。

下一步在新冻结下单次执行，保存实际 rc、partial、完整费用和退出证据；依据两份真实 profile 的函数热点选择保持语义的优化。authority 核心、ROS shadow 和独立 reader 接线仍是未安装候选，已[无损保存](assets/20261024_mr3_p2a_v62_process_profile/checks/prospective_authority_v1/README.md)。此后仍须取消修复与有效 probe-v2、实际容量、新同 freeze 12EP/30 角色，以及真实 minimum/pilot 更新与三场 strict95 final；P2B/gateway 不启动。
