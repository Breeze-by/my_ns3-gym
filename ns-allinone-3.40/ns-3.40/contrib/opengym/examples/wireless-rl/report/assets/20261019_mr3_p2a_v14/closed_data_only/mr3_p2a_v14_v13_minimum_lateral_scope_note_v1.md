# V14只读统计封存范围

分析的是原0063 V13失败minimum的闭合native publication/actuation原件，未运行正式consumer/source检查/native/GPU/仿真，旧FAIL不变。只读统计首跑实际child rc0/3.080302444秒；内部统计2.217123809秒与child全wait不是同一计时边界。

三个source-time窗口分别保留：release41.12→评价器declaredend56.98；release→最后API真实physical quantum57.0；declaredend后→native物理关闭57.2。触发56.995没有被删除或因callbackclock滞后重标为合法。

任务source窗口共有2379样本；按实际wheel update已消费target_v分组，非零524样本（tb1/2/3=251/122/151），max|bodyvy|=.0012727477023301292，0样本>.01；r含不属target sign的vx时本组max同值。峰tb2 source43.296，rawodom line1968，前一actual update43.294/line5082/actseq1157，vx=.1601736049195775、vy=−.0012727477023301292。

零目标1855样本含真实braking/settling；planar max.1627186256645024、86个>.01，不等于1855个已qualified disk样本，更不是新的模型失败信用。不能把刚发布/存储/施加zero当作身体rest。

所有2412个release→close样本在CSV逐条保留source/odomline/actualupdate/consumedcmd/issuedrimmean/bodycomponents；0 unknown matching。匹配严格取actuation时间<odom source，因为WORLD odom在同clock轮写之前发布；latest storage独立列出，sameclock storage先后不猜。

这是20ms离散样本，只能寻找已有反例，不能证明1ms连续/未来侧滑界、heading cone或停车终端集。统计不是新科学PASS、actor准入或物理修复。精确原件及6个raw引用见artifact index，原大raw不复制。
