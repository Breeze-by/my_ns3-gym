# P2C.1 原安装恢复组件 PASS

[v58首格启动FAIL](20261010_p2c_v58_failed_startup.md)保持：owner/runner1、observer0全部关闭，没有原生评估结果；原安装配置复制路径导致禁止旁路源码审计FileNotFoundError。没有覆盖原失败或修改审计规则。

恢复项目原 `colcon build --symlink-install`，四包8.44秒PASS。实际安装control.resolve指向规范src/multi_robot_exploration/multi_robot_exploration/control.py，安装禁止旁路manifest.resolve也指向规范src/multi_robot_exploration/config。七原源码规则全部存在、均位于规范ROS/src且与冻结920d541字节相同，原source-only审计零violations PASS。生产控制器SHA保持e284836b14d0520979ca8c0b44dc30e03f137066b101f4ae84f18fbc6d3f4956；没有生产代码变化。

恢复后的安装环境重新运行七实际DDS/Future场景，结果仍旧cancel/新保持SUCCESS/newcycle-uncovered-ownreturn取消/stale-unfundable零goal，全部owned关闭。合成刷新原几何与ActionServer不是真实Nav2、原任务回放或任务收益证明。前一组件1876功能、190保护6原授权54协议结果因生产字节完全未变可复用，不虚称新重跑。两manifest仅更新parent/time与安装环境声明，全部case和物理刺激保持；两validate-only PASS。

丰富临时安装检查首次错误地限制七规则都在单exploration包，原manifest合法包含同级包；原source-only审计已PASS。仅临时检查器改为规范ROS/src和父冻结字节相等，首失败/source保持。该修正未放宽原禁止旁路规则。

新v59须同clean pushed从四开发开始，再17正式+2物理；917仍未暴露。完整P2C.1未完成，原300s/5s/TTL/身体/能源/native/SLAM/Nav2/物理全部保持，无P4/ns-3/Wi-Fi/RL。[JSON](20261010_p2c_install_restore_components.json)与provenance保存构建、原source-only、失败、installed路径/源码SHA、DDS及两声明。
