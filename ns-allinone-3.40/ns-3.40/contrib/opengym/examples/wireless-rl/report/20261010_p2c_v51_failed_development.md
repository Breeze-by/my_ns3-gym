# P2C.1 v51 四开发原件整体 FAIL

冻结源码 `861c48e6e1c15201996677852d996a41b143263f`；四格owner/observer均关闭0/0后才修改。forced183.6秒、rooms132.1秒原生COMPLETE且严格全审PASS。lab141.0秒原生FAILED insufficient_rally_poses；corridors300.3秒原生timeout，中央298.7秒的COMPLETE没有原生连续5秒保持证据。整体FAIL全部保留。四格零接触、耗尽或机器人失效。

| 原格 | 原生成功 | 中央阶段 | 仿真秒 | 充电次数 | 最低能量 |
|---|---|---|---:|---|---:|
| dev_corridors303 | False | COMPLETE | 300.3 | {'tb1': 1, 'tb2': 0, 'tb3': 1} | 26.231729 |
| dev_forced2 | True | COMPLETE | 183.6 | {'tb1': 1, 'tb2': 1} | 14.906506 |
| dev_lab101 | False | FAILED | 141.0 | {'tb1': 0, 'tb2': 0, 'tb3': 0} | 26.666064 |
| dev_rooms202 | True | COMPLETE | 132.1 | {'tb1': 0, 'tb2': 0, 'tb3': 0} | 27.702501 |

lab43.2秒发现，未进入RALLY。12次失败分配在完整冻结控制器中重建失败，tb3的原交付约束图中所有集合候选不可达，充电中心亦不连通；这不是home-center可行性修复的证据。原分配计算仅0.120..0.386秒。固定末次原输入的三组纯几何成本为1.944..2.021秒，尚不包括实际send_survey_goal的身体、完整去返能量、序列化和租约复核。原末段旁录源龄多次2.5..3.3秒，该条件成本可耗尽原2秒派发租约；原任务缺各补查函数独立计时，不将其认作精确回调因果重放。原任务最终按原准备超时判无点。固定输入成本和合成DDS均不证明旧任务因果收益，也不证明障碍的物理来源。

17份正确调用的独立组件审计PASS，不替代原生任务。首次和第二次组件脚本误将不存在的RALLY proposal设required、又将未进入RALLY的None位置阈值传给heading读者；失败trace保留。第三次proposal optional且采用冻结原.35阈值，包含已有quiet heading证据核验，PASS。原12份分配规划图独立绑定原CDR，另见下一组件报告。未清地图、未屏蔽同伴、未改SLAM/Nav2/扫描/物理参数。

原300秒、5秒保持、TTLs、完整返航/能源与物理刺激保持。未调用17正式、新同冻结物理对子或917；不重试、不回填、不跨版本汇总成功率。P2C.1未完成；P3C.5已验收，无P4/ns-3/Wi-Fi/RL。

[JSON](20261010_p2c_v51_failed_development.json)及同名originals压缩包保留完整原summary、gate、安全旁录、私有事件和全部原文件SHA。原大型CDR/完整ledger仍留本地原目录。
