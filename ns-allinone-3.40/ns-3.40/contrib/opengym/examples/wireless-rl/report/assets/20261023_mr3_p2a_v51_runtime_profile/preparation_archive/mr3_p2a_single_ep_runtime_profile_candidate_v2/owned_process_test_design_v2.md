# V2 人工 owned-process 回归设计（尚未执行）

本设计不使用V50输入，不导入原runtime或任何ROS/World/model。测试应由root实际CPU wrapper执行并保存exact argv、源码、真实PID/start/group、signal时间、actualwait/rc与console。以下每项只验证lifecycle，不提供native或科学信用。

1. **真实正常返回**：新session启动`/usr/bin/python3 -c` toy child，输出一个固定小JSON后return7；通过真实Popen.wait取得7，保存identity，确认wait后原PID/start不存在。`stop_and_wait`无须伪造rc或用/proc推断rc；非零保持FAIL。
2. **清理期间两次真实信号（主阻断反例）**：启动一个忽略TERM、等待stdin或睡眠的toy child到新session；guard父进程使用与`main`相同的仅记录TERM/INT handler。一个独立测试helper在父进入`stop_and_wait`后向**测试父的保存PID/start**各发一次TERM和INT。确认handler返回、不抛出，父仍进行TERM10→KILL→真实wait，最后rc为实际负SIGKILL，`received_parent_signals`保存两次事件，`actual_waited=True`；原保存child身份gone。父不能在waited=False时return；此用例始终FAIL/完整费用，不能因成功reap写成profile PASS。
3. **清理wait的Python异常**：真实Popen toy child外包一个仅委托真实`wait`的薄fixture，先各抛一次InterruptedError、KeyboardInterrupt和RuntimeError，随后实际调用底层Popen.wait；真实signal只发该owned session。确认所有异常都保留在errors，最后rc来自真实wait，原PID/start gone且不会提前return。另用纯stub覆盖`wait(timeout=...)` TimeoutExpired后KILL及无时限wait再次被中断；最终仅在一次真实/明确委托wait返回整数时认为waited。
4. **主wait期间请求停止**：用短toy child/full-run admission的纯mock source/input fixture（绝不指向V50）进入100ms主等待循环；记录一个TERM。下次主循环检查应转入finally清理，先TERM、必要时KILL，只有实际wait返回后继续输出。源/输入前置hash过程中已收到信号，也必须在Popen前拒绝，不启动新的child。
5. **错误/超时/超额不变**：workdeadline耗尽、handler记录中断、wait异常或主840/总900超额任一个发生，始终passed=False；即使child最终rc0也不能覆盖。unbounded reap异常重试不得制造rc0或宣称硬实时；所有实际overrun交外部parent完整计费。partial/no pstats仍保留。
6. **V1保留与差分**：逐字核旧目录所有文件仍等于`v1_preservation_manifest.json`；V2 common/child与V1完全一致。只guard新增signal记录、100ms主wait和cleanup实际wait重试；固定EP、1次audit、14inputs/23proof+init、两个freeze、840+60、原数学及原FAIL全部保持。

信号测试只向测试自己刚保存且仍匹配的父/owned child process group发信号。不可用`pkill`或扫描并停止其他活动。测试失败也必须finally实际stop/wait其toy进程；不能为快速测试丢弃清理。真实TERM→KILL用例预计至少10秒，必须给CPU wrapper留完整时限，不重试或用sleep伪造执行结果。

当前只有测试设计，未启动toy子进程、未读/proc、未实际发signal、未运行任何candidate/reader/tests。
