# P2C.1 v28 朝向感知搜索组件 PASS

v27首强制原任务发现268.0秒、300.2秒RALLYtimeout，安全子门通过而native失败，原始失败完整保留，其余任务未调用。新候选针对搜索中历史位置圆盘未考虑真实相机朝向的问题，只替换交替已知空间搜索的兴趣掩码：原始新鲜交付odom/TF各0..2秒，记录每0.5米/22.5度bin首次实际位置与yaw；在当前交付地图中按原2米/90度射线重建历史视场，occupied/unknown遮挡，优先补查其外已知自由空间。保持16个候选朝向、原alternation/有用接续/身体/完整返航预算/充电公平/全部TTL/native门限。没有检测前真实目标坐标、hidden状态、原生审计流或新应用包；历史视场估计不是物体不存在或完美感知的证明。

解析几何夹具验证前后朝向、墙/unknown遮挡、范围、无效源、去重、原始年龄与独立重建。240×240/.05米开放图，原位置圆盘抑制5021格，新90度视场抑制1284格并保留背面。首次实现全圆重建600合成view约2.529–2.556秒；缩至实际扇区并去除排序后约0.916–0.921秒。100view约0.153秒。射线从实际亚格位置出发，采样集合与初版略不同；这不是逐格数值等价、任务反事实或最坏延迟保证。两版源码、夹具、CPU输出都保留，只有优化版进入下一freeze。

88定向PASS7.28秒、1190完整功能PASS91.94秒、四包5.47秒、171保护/4授权/54协议、两manifest与actual ROS DDS PASS。DDS从隔离topic实际交付odom/TF，形成原yaw/source历史并经真实coordinator发布camera-aware visual witness，再独立重建；仍为合成地图且synthetic Nav2客户端。旧79候选数值/旧int64错误复现、target survey与quiet/lapsed检查继续保留。只改两个中央方法与已知候选函数、增加一个纯视场函数，其余71中央方法、原native energy/TF sampler/launch/physics/native completion字节保持；300秒/5秒与所有硬预算未放宽。

首声明更新因物理manifest没有retained_failed_developments字段出现KeyError，已setdefault修正并validate-only两份，不属于任务启动或重试。新all4/17正式/2物理须同clean pushed freeze；917未暴露。P3C.5已验收，无P4/ns-3/Wi-Fi/RL。
