# P2C.1 v35 四开发原任务 FAIL

冻结7d9709b907f2f38f1252eee8ae4fb53c42f3cc13，control SHA8687306f698d83b121d9dbbe8d39147b4a112f5cf07d0f18916bf3d84cf6938d。首强制strict/native PASS并关闭后才调用后三格，同源四个owner/observer均自然exit0；原任务全部保留，无重试回填。正式17/物理2/917均未调用。

| 原格 | 原生结果与秒数 | 检测/集合秒 | Nav2 | 总charge | min energy |
|---|---|---|---|---|---|
| dev_corridors303 | FOUND timeout 300.1 | 296.20000000000005/None | 14 | 0 | 31.7484279854 |
| dev_forced2 | COMPLETE task_complete 200.7 | 100.09999999999991/115.0 | 22 | 2 | 14.1569981179 |
| dev_lab101 | EXPLORE timeout 300.4 | None/None | 3 | 0 | 32.8903769922 |
| dev_rooms202 | EXPLORE timeout 300.3 | None/None | 1 | 0 | 33.3518408817 |

四格0接触/耗尽/failed机器人/infra/retry。forced两机各charge1，真实5.0秒保持/51样本/最大间隔.1秒；独立48项返航/能量/来源/探索/集合/进程审计PASS，不能代替完整开发门禁。严格开发checker因后三格success=false而FAIL。

lease弃置次数/阶段：{"dev_corridors303": {"route_admission": 29, "candidate_generation": 20, "candidate_budget": 71, "dispatch": 1}, "dev_forced2": {"candidate_generation": 3, "candidate_budget": 1, "route_admission": 3, "dispatch": 1}, "dev_lab101": {"candidate_budget": 54, "candidate_generation": 42, "route_admission": 50}, "dev_rooms202": {"candidate_budget": 58, "route_admission": 47, "candidate_generation": 42}}。

首次保存了不可逆弃置时的完整冻结输入；三份诊断逐字等于原ledger行，绑定ledger SHA和index。固定来源时刻条件重建完整计算的三次cold：lab约2.35–2.41s、rooms3.47–3.61s、corr2.24–2.46s，原剩余租约约1.34/1.59/1.41s；每轮约270/561/243路线调用、1950/4554/2026返航预算查找。主要支出是大量候选的完整预算、局部障碍veto和同伴价格，随后路线前缀才拒绝。上述是条件计算剖析，并非历史实时回放、端到端因果或最坏时限。

保留原300s/2–5–60s来源TTL/5s真实保持、原生安全储备与所有历史失败。P2C.1仍未完成，P3C.5已验收，无P4/ns-3/Wi-Fi/RL。原始命令/source/evidence/owner哈希在JSON和gzip旁证中。
