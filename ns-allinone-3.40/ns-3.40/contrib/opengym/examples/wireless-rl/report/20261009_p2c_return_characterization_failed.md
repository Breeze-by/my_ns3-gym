# P2C.1 独立返航表征原两格 FAIL

与v41主失败分开预声明，冻结723a844；两原格全部保留，不计入完整任务成功或TDI。命令为taskset -c 0-79 /usr/bin/python3 scripts/run_p2c_tasks.py --manifest scripts/p2c_blackout_manifest.json --case physical_ideal/physical_fault --run-id 20261009_p2c_return_characterization，理想domain218/port20298、故障219/20299。完整argv、时间和命令/source/env/ledger/图/原生物理SHA见JSON。

理想格原生COMPLETE211.2秒、每机charge1/min20.97300534492981、零接触/耗尽/机器人失效，但远端准备在首条Nav2动作立即ABORTED，staging exit1；因此严格安全对子FAIL。任务后来的成功不能代替远端准备证据。启动日志显示实际Nav2仍使用不覆盖负坐标准备位的默认代价地图范围；这是待验证的准备就绪缺口，不作所有abort的确定因果归因。原任务算法/安全没有修改。

故障格EXPLORE timeout300.1秒、每机charge1/min12.332414691017467，原生返航/实际Nav2运动通过独立严格审核；此处只证明受控60..250秒断网中的本地返航/充电，非任务成功。两owner与全部观察器/准备器关闭，理想仅staging1，故障全部0；无升级清理/重试/回填。

第一只读读者对未检测目标的null相机元数据执行radians触发TypeError；修复为保留null，只有真实朝向witness才要求有限正值。第二读者将相对run-root与原始绝对physics_command比较而失败；修复为canonical路径。27项读者检查通过，修复后的同一原数据为故障独立PASS/整体FAIL。所有初始失败读者输出和traceback保留，未改写任何原任务输入或结果。

后续仅增加独立准备器边界适配：等待实际Nav2全局代价地图新鲜、同map坐标且覆盖声明准备位置，仍执行原已知自由短腿/原50秒准备期限/原断网62..248秒物理验证窗口。必须另冻结并运行两份新原格，不得覆盖或替换本对子。
