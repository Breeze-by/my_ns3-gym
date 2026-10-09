# P2C.1 v26 四原开发 FAIL

冻结67264507420969a9ae9ea3ffe74aa00d69573853的all4：forced原生COMPLETE241.9秒/检测145.3/RALLY147.3、两机各charge1；rooms原生COMPLETE211.5秒/检测93.3/RALLY113.4、零charge；lab检测106.1/RALLY147.3、300.2秒timeout/两机charge1；corr检测109.0/RALLY132.1、300.1秒timeout/两机charge1。四格零接触/耗尽/failed机器人/任务期子进程崩溃，四owner与observer0，所有owned关闭后才编辑。Lab末三机位置误差0.02248/0.00940/0.01822米但缺完整native五秒保持；corr一机仍距2.51246米，不能判成功。房间209.4秒中间口头记录有误，以原211.5秒更正；未改任何原结果。

四份同冻结原summary/源码/环境/命令/图/账本/metrics/关闭记录与SHA保留；strict full开发FAIL（仅lab/corr native success断言），无任务重试/回填/阈值放宽。新17正式/两受控物理与917未调用。

四格八类独立审计全部PASS：16闭合返航触发/16map预算/28pose租约、12local腿/6charger returns、590能量快照、53探索（11已知空间补查）/18接续/4相对偏好/53局部可见偏好、3真实目标信息勘察（lab2/rooms1）、10AP返路否决、3失败/4成功集合分配、1两前沿提前充电与全部native图/任务期进程审计。这些本地腿不是预声明远端断网双格的替代。新目标信息勘察已有真实Nav2派发，仍不等同整任务通过或因果收益。

发现后实际原记录显示7次target_observation_heading：corr两次的目标源龄1.0/.7秒，rooms一次.6秒，lab一次.5秒；另三次lab6.6/5.4/5.3秒为正常确认间断。原restore_observer_heading在健康确认时仍允许居中转向，会抢占FOUND勘察和RALLY预充电回调。现有RALLY纠正已使用>5秒确认间断，下一候选将前段统一；不改当前所存原轨迹，不从七条记录推断节省几秒。查看充电顺序前提时发现corr正式集合只余一台未funded，另台已经charged，未运行也未采用充电排列反事实试验。

P3C.5已验收，P2C.1仍进行，无P4/ns-3/Wi-Fi/RL。
