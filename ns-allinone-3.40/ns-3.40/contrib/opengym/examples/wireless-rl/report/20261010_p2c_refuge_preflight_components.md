# P2C.1 让行释放准备门槛组件 PASS

[v61首正式FAIL](20261010_p2c_v61_failed_formal.md)完整保留：同c5e3331四原开发strict PASS、两原物理安全PASS后，fixed_lab_101 RALLY300.0秒timeout，tb1/tb3各charge1、最低24.971566、零接触/耗尽/FAILED，17子审PASS及tb2第2次返航未闭合FAIL。剩余14非留出正式和两917均未调用。原开发/物理PASS不带入新源码。

旧释放方法在等待预算缺失时先做三机排列、两机完整路线及能量，最后才因KeyError拒绝；它在普通prepare_rally_charges之前执行。旧已有合适优先级也重新排列。新方法先要求原wait预算存在、有限且非负；缺失即交回原准备流程。已有完整参与顺序且helper在ACTIVE owner之前时保持该顺序；否则仍走原map-safe排列。两条完整serial approach仍在当前融合与每机交付图上屏蔽所有静止身体、后者还屏蔽先到helper，重新核验当前与终点完整返充、原5s保持/等待/源租约。恢复final target仅改变意图，实际goal仍过原派发全门槛。

32定向情形覆盖原资金/源/身体/动作/充电拒绝与新增4无效wait和1既有顺序。新独立读者核验实际记录的order_source/previous_order与原完整路径/能量，声明开启后缺字段拒绝；没有放宽原资格。实际三机DDS四情形沿原native CDR几何，10s合成源戳与80电量：缺wait原搜索1次约1.472s、新0次约.001s，两者均不释放；原真实preflight准备后，两者均证明并派发1个helper，旧再搜索1次约1.434s、新0次约.177s。独立两机资格与outbound路径读者PASS。clock13使原10源过期均拒绝；fresh13但energy.1均拒绝，零追加goal。真实动作Future、线程、节点全闭合。旧e8af条件的原两机DDS回归仍旧0/new1goal，fallback原顺序选择保持。

这些是原native最新地图的条件机制与局部耗时，不保证与原中央消费版本完全相同；目标/refuge、TF/odom、80电量和DDS源戳是合成条件，无物理Nav2、原live反事实、任务因果收益或最坏延迟保证。初几何脚本把未捕获的gateway map当输入而KeyError，原失败保留，修成明确native条件，没有由此修改生产保护。

只1中央方法改变，其余82中央、101纯函数、globals/native保持。1902功能214.34秒、原--symlink-install四包6.20秒、190保护6历史授权54协议与两新声明PASS。300s/5s/2-5-60s/.45端点/.35路线/.6身体/1.8预约/原腿长度/次数/Nav2/SLAM/物理刺激均保持。

新v62须clean pushed同4开发→17正式+2原物理；15非留出和新物理全PASS后才917。组件PASS不替代完整P2C.1，无P4/ns-3/Wi-Fi/RL。[JSON](20261010_p2c_refuge_preflight_components.json)及provenance保存字面源、初诊断FAIL、全部输出/声明/SHA。
