# P2A 两项决定性测试：行为可行性与完整采样成本

2026-10-24，用户明确要求实际测试后判断是否调整路线。本活动是新的有限工程诊断，不是重试 V71、完整资格矩阵或学习；旧失败、P2A 未完成、capacity=False 保持。结果尚待执行，以下为运行前声明。

## 问题与固定判定

1. **行为可行性。** open101、一个 worker、三机、最多 96 个完整任务步。每机恰好一个预先标为暖身的 GOAL，只接受其自然 SUCCEEDED；暖身最多 32 仿真秒，之后分别尝试两个 qualified GOAL，每次机会最多 28 仿真秒。每机独立推进，真实 accept 后一次捕获完整路径基线；同 active owner、accept+5s、v≥.08 m/s、新增 path≥.05 m、原 WAIT mask 同时满足才提交 WAIT。必须实际取消，获得三条不同且新鲜的静止观测与至少 3s 交接。qualified 早成功、暖身失败或窗口耗尽都保留失败，不改分类、不重试。最终 96 步是诊断上限，不更改原 300 秒任务截止。收到态覆盖和原生物理/协议审计分开，只有二者通过才称这个具体输入方案可行。
2. **采样成本。** 使用既有 benchmark 的 uniform legal 输入、seed41，双 worker 各一回合 open101、各最多 64 步；保持现行 exact-point/point-attachment/cone-support、owned authority 和 initial encoder profile。包括两次真实 cold reset、采样、关闭、全部适用独立审计、custody review 的连续父墙时，与原 pilot 剩余 2905.9547395464029 秒比较。没有模型和优化器，这只是采样的乐观成本；不足以证明 PPO 收敛或三场 300 步验证容量。若此乐观成本已超原额度，不能声称现有 pilot 方案可负担。

第一项只排序原 per-robot AND joint True 的动作：优先合格 WAIT、GOAL 数，再按目标相对队友的最小离开方向投影、最短声明路径（较长优先）、总路径及动作编号排序。未定义方向排最后，不作为安全通过。KEEP 保留所有原约束；不生成速度、不绕过 Nav2/Reach，不刷新 anchor/authority/路径基线，不使用真值。自然暖身没有 qualified 信用，但全过程仍接受原安全审计。

两项各 native 6000 墙秒（含正常关闭；180 秒预留）、只读审计 6000 秒，连续父总预约 26000 秒，包含前后来源、等候和记账间隙。软界超额全部计费并记失败，不假称硬实时。承接 V74 末账 U112685.3057936486018/C180000/R67314.6942063513982，预约后余 41314.6942063513982；pilot/final 不收费、不借用、不扩额。上限由代理在现有自主授权及本次明确测试请求下前瞻选择，不称用户逐数值批准。

## 工具与证据边界

复用现有 Supervisor、MR3Env、benchmark、live custody、独立 FIFO/authority、information、cadence/runtime 和完整 diagnostic native/contact/clock/scalar/evaluator/archive/activity/input 检查。独立收到态复核器从原始 transitions 与实际 command 重建每机暖身、两次取消、五秒/速度/新增路径及静止交接，不导入刺激程序。现有诊断读者补齐显式当前 profile 参数传递；peer 读者仅新增带完整 source/Git/build 绑定的非训练诊断入口，原资格入口不变。运行前检查这些真实入口及软件负例，新的运行必须来自 clean、已推送的 exact freeze。

源码/ELF检查不提供新编译信用：本活动不改变 Supervisor、ROS 控制、C++ 或七宏，保留当前实际构建与 ELF。完整科学资格仍需另行同冻结 12EP/30 角色；本诊断的成功不能代替它。全部消费者保留真实 rc、失败、缺项和实际等待。闭合身份限已保存 PID/start，不声称无记录的外部进程退出。

如果第一项失败但来源、进程正常闭合，第二项仍独立执行；如果缺来源/custody/退出证明，则先处理具体关闭问题，不能冒险叠加新 World。若第二项发生真实基础设施错误，保留不完整采样与已花成本，不能线性外推为成功容量。两项都不启动 PPO、pilot/final 或 gateway。

## 软件准备

真实 canonical CPU v2 返回 0，63 passed / 1 deselected，父等待 16.015314416 秒、六个修改源前后相等。独立 replay 含成功事件及速度不足/事后改标签负例。旧 fixture 缺少必需 authority 字段的问题已在 HEAD 原读者复现，单独排除而未降低生产审计要求；v1 和早期失败说明保留。CPU 不供 native/行为/容量信用。

## 结果

待真实运行后填写，不预写 PASS。
