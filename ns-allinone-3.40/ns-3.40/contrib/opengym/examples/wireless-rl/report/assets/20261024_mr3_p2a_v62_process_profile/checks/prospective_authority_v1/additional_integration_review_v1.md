# 后续接线必须覆盖的两个回调边界

本补充写在 opaque 包完成之后，不属于包内既定 membership。原包、8项核心 CPU、静态 ROS shadow 均不改；生产尚未安装，以下没有新测试信用。

1. 原 adapter 的 accepted 回调会保存 handle 并订阅 result；completed 回调会移除 handle。如果 result 早于 logical accept receipt 的交付，dispatcher 后来进入 active 时，handle 可能已不存在。新授权逻辑应保留真实接受的 UUID 身份到 terminal 释放，或对已经匹配真实 terminal 的 never-granted owner 保持零权限并正常交付原结果。不能伪造或推迟原 acceptance/receipt，也不能把正常 quick-success/abort 一概当基础设施错误、丢掉正常任务负样本。
2. revoke publication 异常时，真实 native cancel 仍须尝试。其 closure 内也应真实挂接 cancel done_callback；不能因 finally 后传播 publication 异常而丢失原 RPC 响应。保存 publication、actual callback、原 receipt 和 later handoff 的各自事实。

最小既定分支保持：自然 terminal 在真实 delivery 时撤权并立即调用原 on_result；canceling 的匹配 terminal 先记录真实 receipt，再等待匹配 stopReady，最后在 later current clock 调用原 on_result。两者均不改原停止 B 起点、不增加第七导航 phase、不改六维编码或5秒承诺。没有 worker phase 屏障就不宣称 ACK-before-next-quantum。

GRANT 后 unstamped raw 的生成 goal/generation 仍 UNKNOWN；callback floor 只隔离已接收的旧缓存。独立 reader 必须按实际 journals 重建授权、停止义务和 callback 调度，不能调用生产 authority helper给自身行为授予 PASS。
