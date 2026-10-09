# P2C.1 v41 单次求解几何复用与约束优先核验组件 PASS

v40冻结d70b277首forced原生FAILED192.8s/insufficient_rally_poses，118.7s发现、无RALLY/native保持；两机各charge1/min14.95501，0接触耗尽机器人失效/任务期infra/retry。原任务strict FAIL，12独立审计PASS仍不是成功，其他3dev/17formal/2physical/917未调用。全部原数据和37附件见20261009_p2c_v40_failed_development.md/.json。

本轮在准确首/末失败输入上比较原算法、仅共享几何、仅约束优先和二者组合，5次paired cold；四种完整输出完全相同。首输入中位1.229/.750/.767/.450s，末1.185/.727/.728/.439s；一份实际可行输入约.490/.493/.487/.491s，组合不加速。仅二者组合合入，并增加不可变来源门禁。

复用仅存在于一次assign_rally_poses的两个原采样层：原安全图、每机起点和充电中心距离场、既有合格返路memo、软净空场。只有bytes拥有的不可变融合图及全部本地图满足门禁才跨层共享；可写数组和可写父数组的只读view逐层重建，每个公开提案新建缓存。预算、充电等待、分配、源戳不缓存，所有原current/end完整返路、local占据veto、body/route、observer/充电/cap/等待/稳定tie仍完整计算；原几何memo128位置与末段2048节点上限保持。

按本地已知终点较少的机器人优先构建完整能量选项，是失败检测的计算顺序偏好；本地图unknown/missing不拒绝融合合格路径。原分支搜索顺序、候选域72+外边界≤48→464、同一次第一完整可行层及所有硬准入不变。源码仅两个纯函数变化；中央类、native电池、clock/action/TF/Nav2/SLAM/物理字节保持。

最终源码八组原始ledger绑定输入，各5paired cold，全部位置/yaw完整提案与冻结d70相同：

| 原输入 | 原中位wall秒 | 新中位wall秒 |
|---|---:|---:|
|20261009_p2c_v40_dev_forced2_first|1.20505|0.44583|
|20261009_p2c_v40_dev_forced2_last|1.23354|0.45541|
|20261009_p2c_v38_dev_forced2_first|0.55589|0.55861|
|20261009_p2c_v14_dev_forced2_first|0.73208|0.73420|
|20261009_p2c_v14_dev_lab101_first|0.94249|0.94308|
|20261009_p2c_v14_dev_rooms202_first|2.31589|2.33096|
|20261009_p2c_v14_dev_corridors303_first|2.80508|1.99202|
|20261009_p2c_v26_dev_corridors303_first|1.57179|1.57717|

两份几何失败中位CPU降低约63%，一份走廊可行输入2.80508→1.99202秒约降低29%；其他五份可行输入略增0.06%..0.65%，房间仍约2.3wall秒。wall量不是sim源期限，也不是原现场因果对照；不能宣称普遍加速或硬时限/任务成功。

21新增检查覆盖8实际输入、不可变/可变/可写父数组只读view、两层中途地图变动、未知/缺本地图仍有合格融合候选，以及新提案改变地图/原点/位置/home/energy/mode后重新核验。40定向PASS32.08s，1484完整PASS147.47s，四包build7.71s，171保护/4已授权变化/54static/8中央+2native Future注册PASS。

真实coordinator→独立DDS receiver共6份witness，覆盖一份不可行、二机/三机可行输入的新旧提案，独立读者逐格还原与源戳完全一致；仅fixed AP epochs，未运行Nav2动作或Gazebo任务。两份manifest validate-only PASS，全部38历史失败cohort索引补齐，原case/300s/owner120s/TTL/5s和物理刺激不变。

下一次clean pushed freeze仍须先forced严格native COMPLETE且每机charge≥1，再其余3dev；all4过才同freeze17formal+2physical，917最后首次暴露。组件PASS不等于新任务栈验收；P2C.1尚未完成，P3C.5已验收，无P4/ns-3/Wi-Fi/RL。
