# P2C.1 v58 首格启动 FAIL

冻结 `920d54176619e75abd71bd8cce380f9a85957957`，原forced owner/runner1、observer0，均关闭；没有native result或result_path，评估尚未开始。原strict gate FAIL（缺result_path）保留，不能计算任务完成/充电/安全指标，余3开发/17正式/新物理/917未调用。

本轮构建命令漏用原 `colcon build --symlink-install`，导致安装后的禁止旁路审计配置是复制文件，其resolve根落入install/share；原source_violations读取该根下control.py时FileNotFoundError。原构建日志、错误trace、启动原CDR/ledger/launch和关闭记录保持，不修改原审计器或放宽源检查。生产控制逻辑本身未改动。

恢复原symlink构建、显式检查实际安装control/manifest的规范源码解析和七原源码规则，再以新冻结v59从首格开始；不能覆盖或重跑回填本次v58失败。完整P2C.1仍未完成，300s/5s/TTL/native/物理保持，无P4/ns-3/Wi-Fi/RL。

[JSON](20261010_p2c_v58_failed_startup.json)与originals保存原summary、strict gate、trace、launch、原observer及所有原文件SHA；大型原CDR/账本留在原目录。恢复证据另见[安装恢复组件](20261010_p2c_install_restore_components.md)。
