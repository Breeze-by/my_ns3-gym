# P2C.1 未集合阶段执行容差读者组件 PASS

[v64原物理读者FAIL](20261010_p2c_v64_failed_physical_reader.md)保留。同69c0e61四开发原生223.1/207.1/123.5/251.3秒全部完整strict PASS，首正式lab101原生298.6秒完整strict PASS；两物理原FOUND/EXPLORE300.0/300.3timeout、两机各charge1、零接触耗尽FAILED。原对子checker对ideal quiet heading出现float减None的TypeError/exit1，整体P2C.1未完成。其余14非留出正式和917双格未调用。

原evaluator按既有契约仅从首次rally assignment读取集合hold/tolerance，未集合FOUND结果仍全部None且无native hold。新planning_position_tolerance只读取已在check_one验证SHA的runner.log：必须恰好一条实际Command和一个执行的rally_position_tolerance_m:=0.35；非空原生参数必须一致。它给FOUND observer和target survey读者提供实际执行容差，不修改原生字段、结果或保持。不存在/重复/放宽/.5/NaN/原生不一致拒绝。radius3m仍减原.35米误差，原2/5/60s源/camera/能量/路线/完整native保持均保持。

12新增反例包含原实际FOUND quiet复现旧TypeError、新完整检查与结果不变；6执行参数伪造拒绝；相机2.649米合格/2.651米拒绝；旧target6秒、TF2.01秒和缺FOV拒绝。101定向7.17秒、1966功能205.00秒PASS；四包原symlink 6.73秒、190保护6历史授权54协议和两新声明PASS。

七原执行日志独立SHA/参数检查均.35；两未集合物理仍None。修正后的原物理对子全部严格读者复读PASS：ideal仅1 quiet、无集合保持；fault两机黑障窗口实际路径tb1 1.386689米/tb2 1.446499米，Nav2 EXEC实际运动均同量、净回home进展1.379355/1.439514米，起始home距离1.971882/2.009675米；原62..248秒窗口/.5米/1.1米准入和50/60..250秒全部保持。该复读为独立组件，不覆盖原FAIL、不带入新版本验收，也非任务成功/TDI或一般地图安全保证。

仅check_one给两读者传入执行参数，新增1纯读者方法，其余18读者方法逐AST保持；八task/native/SLAM/launch文件逐字保持，包括control BBB743、native f4845。两manifest只改parent/time/读者声明，所有case/刺激/物理字节保持。无新DDS/Gazebo任务；既有执行算法不变。新v65须clean pushed4开发→17正式+2物理，15非留出和新两物理严格通过才917。完整P2C.1仍未完成，无P4/ns-3/Wi-Fi/RL。

[JSON](20261010_p2c_partial_heading_components.json)及provenance保存字面、夹具、测试/复读/声明/原失败归档helper和SHA。
