# P2C.1 交付ACTIVE稳定与真实准备就绪组件 PASS

独立原对子723a844及593b5dd整体均FAIL；故障格各自原生返航独立PASS，第二对子理想格还出现后续正电量机器人失效。全部原失败/就绪clock浮点读者误报与source行绑定保留在20261009_p2c_return_ready_failed.md/.json；更早null/路径遗漏另保留。主v41 PARTIAL279.1也仍为FAIL，不回填。

新stage_p2c_return_probe.py在准备器边界适配原stage_p3b5_return_probe.py的函数内ActionClient导入，退出必恢复。原准备器/物理观察器及全部任务control/native/TF/launch字节与723a844完全相同。每次原网关短腿前等待真实Nav2全局costmap：map坐标、有限完整无旋转、原source header不未来且年龄≤2秒、范围包含两个原准备位置。只验证导航装置就绪，原received map/pose/TF/battery source TTL、known-free路径和机体安全仍由原准备器检查；Nav2地图不会进入AP观察、能量许可或无线模型。新增仅订阅原gateway交付battery：至少两个不同source stamp、跨原0.5秒心跳、原5秒TTL内连续ACTIVE；同源重复不计、RETURNING清除。原生隐含状态不参与准备控制。此保守准备门仅避开已观察启动竞争，不证明任意后续转态或一般安全。

原Nav2配置发布完整全局costmap（0.5Hz），未改参数。缺图/默认范围/未来/过期都会等待，原50秒准备期限内仍未准备则FAIL；abort无重试。每次就绪日志保留原stamp/范围/shape，独立读者核对每条原staging_requested前实际就绪；新run必须冻结wrapper与原base SHA，legacy原证据仍用原准备器审核。

真实ROS/DDS domain220的两个真实gateway ActionServer与costmap/clock publisher验证9情形：缺图/默认范围/单源或同源重复ACTIVE/RETURNING/转换后一条ACTIVE/未来地图/过期地图false，两个不同新鲜ACTIVE和状态恢复后两条分别true。没有发送Nav2动作、没有Gazebo/真实移动，不代替独立新两原格。

103定向PASS1.84s，完整1527PASS124.01s，四包build5.91s，171保护文件/4已有授权变化/54静态协议与原native/constants/Future约束PASS；两manifest command validate-only一致。源/原source绑定和全部组件输出见JSON/gzip。

本提交后需新clean pushed freeze，独立run-id20261009_p2c_return_stable的ideal/fault原格，分别domain218/219与Gazebo20298/20299。所有失败保留；即使受控对子PASS，完整P2C.1B仍需新4开发→同源17正式+2物理，不改变300秒/5秒/源TTL，不复用接受的P3C.5任务作为当前基线。917尚未执行，无P4/ns-3/Wi-Fi/RL。
