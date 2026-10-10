# P2C.1 v57 四原开发整体 FAIL

冻结 `abd9822c486b487af0999b6f20e58f150fb29cb0`。forced原生COMPLETE266.7秒，检测196.9、集合200.3，两机各charge1、最低8.802693，30原生goal/28成功/2取消；原生保持2396.482→2401.482、51样本、最大间隔0.2秒，首严格gate PASS。rooms202原生COMPLETE140.0秒，检测47.5、集合64.4，0charge、最低25.446423，14goal/11成功/3取消；原生保持263.8→268.8、51样本。两成功均有完整native5秒证据。

lab101原FOUND timeout300.4，检测267.1、未进RALLY，tb1/tb2各charge1、最低16.157599，35goal/33成功/2取消。tb3原生return cycle2在任务末仍RETURNING、正电量但未闭合，独立native_return FAIL保持，不能用零耗尽或外层0代替。corridors303原RALLY timeout300.2，检测276.7、集合280.6，三机各charge1、最低19.075339，66goal/39成功/26取消、零abort；末仍有活动动作，native5秒None。

corr原23探索返航清道中22取消、最后1成功。首原276.7秒的tb1/tb2均RETURNING/count2，原完整受保护返路集合也包含两机，但旧goal Future和电池心跳只豁免名义owner tb1，另一返航tb2即取消已合格的tb3让行。这是代码与原实际取消的机制证据；刷新原几何的DDS条件比较另见组件报告，不能推断修改必能在300秒内完成全任务。

四原零接触、耗尽和真实机器人FAILED；owner/observer全部0关闭。停止后的子进程清理退出单独保留，不据外层0宣称所有子进程优雅关闭。原规划弃置lab13/rooms4/corr7，rooms6次实际几何交接派发；这些只是各原账本描述，不能跨版本合并成功率或认定性能变化的唯一原因。

四格原18子审共70 PASS/2 FAIL。lab另一原outbound FAIL为同header不同地图内容的只读绑定假设错误：/merge_map header2161.882有两份原CDR，两份observer receipt均2161.882、均早于2162.882派发；旧读者首先遇到426格差异的版本而拒绝，第二份与保存的规划图逐格完全相同。原失败和两SHA保留；改为每份见证独立寻找原同header完整匹配后，独立只读复核31决策/895路径点/59源header PASS。完整路径、逐格内容、原有限isolated own-cell谓词均未放宽；这不修复native未闭合返航或任务超时，也不证明唯一version级网关因果。

完整严格gate FAIL保持，17正式、同冻结新物理对子、917均未调用；不重跑回填原失败。原300s/5s/2-5-60s、完整身体去返能源、native/SLAM/Nav2/物理保持，P2C.1仍未完成，无P4/ns-3/Wi-Fi/RL。

[JSON](20261010_p2c_v57_failed_development.json)与originals归档四完整summary、两严格gate、70原子审/2原失败、私有及原生安全账本、重复header诊断、独立修正读者和所有原文件SHA。大型原CDR与日志仍保留原目录。
