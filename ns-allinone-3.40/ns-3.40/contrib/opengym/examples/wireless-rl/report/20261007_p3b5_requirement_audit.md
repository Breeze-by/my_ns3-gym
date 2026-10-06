# P3B.5 逐条需求复核与独立方向延迟补验

状态：进行中。原[20261006严格门禁报告](20261006_p3b5_gate.md)的57次原始结果与checker PASS全部保留；本报告补验完整文字要求，不把54格协议测试当作机器人任务测试。

发现的缺口是：原任务0.5/2秒延迟为双向同时注入，缺少上行单独、下行单独的任务运行。现已预声明四个补验case及其同seed/同物理配置ideal配对，共六个原始episode。任务源码保持原d8d361b字节不变，当前提交仅增加清单、只读审核和文档。

清单：`ros2_ws/ros2-multi-robot-automap/scripts/p3b5_directional_delay_manifest.json`；逐case保存目标/world/机器人/电池/任务模式、上下行参数、TTL/deadline/retry/queue capacity/300秒horizon与环境版本。实际实验commit由首RUN之前的manifest记录。固定fault seed17011；走廊2机器人seed202用于0.5秒，房间3机器人seed101用于2秒。原809及707已经暴露，不把本补验称为新留出或算法泛化。

实验计划：两个独立Gazebo master19700/19701，domain180–182/200–202，同CPU亲和性0–79；各场景串行ideal→uplink-delay→downlink-delay，无整轮重试、回填或门槛放宽。每格保留任务JSON/CSV、命令、通信账本、原生电量/Nav2/碰撞观察、graph与只读AP/实际时钟参数旁录。理想失败不会进入TDI。

逐条证据和补验结果在所有owned任务/观察器自然关闭后填写。尚未进入P3C、ns-3、Wi-Fi或RL。
