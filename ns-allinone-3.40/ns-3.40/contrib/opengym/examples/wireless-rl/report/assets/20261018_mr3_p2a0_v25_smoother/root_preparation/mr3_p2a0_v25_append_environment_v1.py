import hashlib
import json
from pathlib import Path

ROOT=Path('/home/zhuyulab/ns3-workspace')
W=ROOT/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
p=W/'MR3_ENV_CONTRACT.md'
old=p.read_bytes()
sha=lambda b:hashlib.sha256(b).hexdigest()
assert sha(old)=='f1e0be60d35db3677fb9194341c1ae4133a5c74ed7199056fe18f7e797f40416'
append='''

## P2A.0 V25：Nav2 平滑器使用节点时钟

V24 的真实输入链显示，仿真时间只前进 20ms 时，原 Humble 平滑器可在墙钟上
执行多个回调，OPEN_LOOP 输出因此累计多次名义加速度增量。V25 在 canonical
ROS workspace 覆盖官方 `nav2_velocity_smoother` 1.1.20（上游 commit
`a097086719c88f781aa59788eca29ac6ca5e56db`）。仅在激活和动态修改频率的
两处，以 `rclcpp::create_timer` 和节点 `get_clock()` 替换 wall timer，并增加
对应头文件。其他官方源码、算法、参数、话题、生命周期和依赖保持原字节。
包内 `MR3_PROVENANCE.md` 说明来源，Apache 2.0 许可证随包保留。

`use_sim_time=true` 时，两个 timer 均跟随仿真时钟；仿真暂停期间不得累计平滑
输出。现有 OPEN_LOOP、20Hz、线速度 .20、角速度 .8、线加速度 .5、角加速度
3.2 及其减速度配置保持。每个回调仍按原频率计算增量；此修复不把量化回调
解释为任意短时间间隔内的连续加速度保证。

实际覆盖包核心库 SHA256 为
`ceedf1b35cc501e9caa655c5b0a66f538395893664ec683a6290760f37d60b52`；
实际 standalone executable 为
`0a5bf913f698dc0f43f57bd06a3f87d35a06e1b8366709576084b4afca5d6c5a`。
启动仍通过 package/executable 的正常 ament overlay 解析。源码、官方差异、构建、
压缩库原件及逐 episode 三台实际进程的 executable/core-library 映射须通过固定
独立准入；不能仅凭 install 中有文件或预先添加库路径授予原生信用。

原任务、奖励、候选和掩码不变。95%/300s、三台参与、18 路接触新鲜度、.50m
队友包络、实测完整平面 .30m/s、完整角速 1.2rad/s、采样角加速度 7rad/s²、
.78s/.144m 停车、完整平面静止 .01m/s 与三个唯一新鲜样本等门全部保持。
组件 stock/fixed 对照只验证计时机制；P2A.0 仍须在新冻结完整通过原四阶段和
全部正式独立审计，不拼接历史 PASS，不构成 PPO 或 95% 策略成功证明。
'''.encode()
p.write_bytes(old+append)
assert p.read_bytes()[:len(old)]==old
allbytes=p.read_bytes()
normative_bytes=40186
result=dict(schema='mr3-v25-env-exact-prefix-append-v1',prior_sha256=sha(old),prior_bytes=len(old),
            appended_sha256=sha(append),appended_bytes=len(append),ENV_DOCUMENT_SHA256=sha(allbytes),
            ENV_EXECUTION_APPENDIX_SHA256=sha(allbytes[normative_bytes:]),
            ENV_EXECUTION_APPENDIX_BYTES=len(allbytes)-normative_bytes,exact_prior_prefix=True)
Path('/tmp/mr3_p2a0_v25_environment_append_v1.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
