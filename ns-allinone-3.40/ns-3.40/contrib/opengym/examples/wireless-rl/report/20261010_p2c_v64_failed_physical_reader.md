# P2C.1 v64 原物理读者 FAIL 保留

同冻结 `69c0e610642a0cf2cea68a402beaae267e2199ab`，七原27软件/仪器摘要，仅两manifest字节因各自case范围不同，26非manifest摘要一致。全部owner/observer0，两物理staging/physics0，所有原PID关闭后才修读者。

|原场景|原生阶段/秒|充电总数|最低电量|原生保持|原strict|
|---|---|---|---|---|---|
|dev_corridors303|COMPLETE 251.3|2|24.397490|5.5s/56样本|PASS|
|dev_forced2|COMPLETE 223.1|2|9.501321|5.0s/51样本|PASS|
|dev_lab101|COMPLETE 207.1|1|24.642164|5.0s/51样本|PASS|
|dev_rooms202|COMPLETE 123.5|0|26.421689|5.7s/58样本|PASS|
|fixed_lab_101|COMPLETE 298.6|1|22.014279|5.0s/51样本|PASS|
|physical_fault|EXPLORE 300.3|2|12.224040|None|对子FAIL|
|physical_ideal|FOUND 300.0|2|12.190508|None|对子FAIL|

四开发完整strict PASS及首正式lab101完整strict PASS全部保留，均有原生完整保持。首正式298.6秒仍在原300秒内，不把该接近时限结果改为更快版本。七格零接触/耗尽/FAILED。物理ideal原FOUND300.0timeout/检测292.2秒，fault原EXPLORE300.3timeout；均两机各charge1，仅受控安全证据，非任务成功/TDI。

原physical checker对fault的check_one先PASS，但随后ideal的coordinator_observer_heading_quiet_hold检查中`radius_m-position_tolerance_m`执行float减None，原exit1/FAIL/trace完整保留。immutable evaluator只在首次rally assignment后学到hold/tolerance参数；原ideal FOUND无assignment，所以这四原字段全部None且native_rally_hold_proof=None。原私有quiet在2366.882秒，range3m/FOV90度齐全；已SHA绑定的runner.log实际命令使用原rally_position_tolerance_m:=0.35。读者应取执行的0.35验证FOUND观测/信息勘察，不能给原生结果补值或伪造保持。

未来修复仅read-only checker；current task/native/SLAM/Nav2/物理/TTL/300s/5s全部逐字保持。新增精确执行参数与原生非空参数一致性、缺失/重复/放宽/NaN及.35相机误差余量/源过期反例。修正后的原物理证据复读只作独立组件范围，原对子FAIL不覆盖、不回填为本批完整P2C.1 PASS。剩余14非留出正式、917双格未调用；新完整验收仍同clean pushed4→17+2。

首只读汇总误把summary当有manifest嵌套，KeyError后用实际顶层git_commit/source_digests确认27同源；一个只读文件列表命令括号错SyntaxError，修正后成功。几次只读rg指定不存在历史测试路径exit2，实际原代码/测试读取后修复，未启动或重试任何任务。上述工具错误与生产失败分开；这轮原任务全部自然关闭。完整strict、七私有/安全账本、冻结六源码字面和所有原文件SHA保存，大型CDR留原路径。P2C.1未完成，无P4/ns-3/Wi-Fi/RL。

[JSON](20261010_p2c_v64_failed_physical_reader.json)
