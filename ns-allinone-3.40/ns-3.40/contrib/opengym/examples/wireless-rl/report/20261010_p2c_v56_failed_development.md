# P2C.1 v56 四原开发整体 FAIL

冻结 `0bfaf4211b971dc64572d7790f831bc26531c7ad`。首forced原生COMPLETE214.8秒，检测159.3、集合161.4秒，两机各charge1、最低14.771983，22原生goal/20成功/2取消。原生保持2284.482→2289.482，51物理样本、最大间隔0.1秒，严格首gate PASS。

其余三原格均保持原FAIL：lab101 EXPLORE timeout300.2/未发现/0charge/最低27.184310，14goal/10成功/4取消；rooms202 EXPLORE timeout300.2/未发现/0charge/最低32.486187，2goal/2成功；corridors303 RALLY timeout300.2，检测86.7、集合106.6秒，tb2/tb3各charge1、最低24.927748，43goal/37成功/6取消。四原零接触、耗尽和真实机器人失效；owner/observer均关闭0/0。停止后的子进程清理退出单独保留，不据外层0宣称全子进程优雅关闭。

lab原125次规划弃置（generation20/budget68/route37），rooms原139次（generation111/budget16/route4/dispatch8），充电网关持续交付；后期无普通探索进展。固定原输入、原epoch、空缓存和合成动作端点的条件剖析显示完整预算/本机障碍/候选评分耗时超过一些原剩余租约；不能把三个同时运行的world认定为唯一原因。无充电两格的startup return_count1仅为原缺位姿funded hold，不是远端返航或补能成功。新鲜数据后的候选几何交接与未采用优化另见组件报告。

corr原最后中央hold始于425.8，任务430.0结束，仅4.2秒；native5秒证明None，中央COMPLETE未发生。原位姿、导航与账本保持，不能用中央稳定条件替代完整物理保持或推断唯一朝向原因。

四格各18独立协议/派发/路径/返航/能源/探索/补查等组件审计共72项PASS，不替代完整严格gate FAIL。审计脚本的通用scope字符串写native task FAIL；forced实际以summary和首严格gate的COMPLETE/PASS为准，此原输出不回写。17正式、同冻结新物理对子、917均未调用，不重跑或回填原失败、不跨版本合并成功率。原300s/5s/2-5-60s、完整身体去返能源/native/SLAM/Nav2/物理保持，P2C.1仍未完成，无P4/ns-3/Wi-Fi/RL。

[JSON](20261010_p2c_v56_failed_development.json)与originals归档完整summary、两严格gate、72独立审、全部私有和原生安全账本、原稳定诊断及所有原文件SHA；大型原CDR与日志保留在原目录。
