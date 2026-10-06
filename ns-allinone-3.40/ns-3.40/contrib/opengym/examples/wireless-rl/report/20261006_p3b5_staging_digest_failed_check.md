# P3B.5 v106 原严格校验失败保留

2026-10-06 P3B.5 v106全57原始自然关闭，冻结d8d361bfd9d81e0c7a00c428ea66cfac4b3a1a76；2026-10-06 06:24–08:42:53UTC。57raw/0unrun/0retry，0接触/infra/操作失败，57ledger与57graph独立PASS、54纯协议PASS。十fixed全部原生COMPLETE，lab303294.8s仅5.2s余量；forced ideal155.2s各charge1。首次809六格全部保留，rally ideal/fault120.9/126.6s原生COMPLETE，target两侧FOUND、coverage两侧达标。single_failure原生PARTIAL_COMPLETE148.9s，tb3为预声明真实FAILED、两健康机保持证明完整、最低19.47128、0碰撞。七port/PID/env与所有冻结source/helper/config、17用户资料hash PASS。原完整strict checker exit1：staging_source_sha256生产端为SHA256(文件名+原字节)，校验端却比较纯源码SHA；两行存储594a3fe...，原源码和预声明纯字节47ce799...完全一致。原FAIL traceback/源码、全部57原结果与命令/环境/hash/AP保留，不改原manifest、不补写结果、不重跑Gazebo。809已首次暴露，后续控制算法变化需真正新留出；只读校验修复待完成，P3B.5尚未PASS，无ns3/WiFi/RL。

证据：[20261006_p3b5_staging_digest_failed_check.json](20261006_p3b5_staging_digest_failed_check.json)。控制、仿真、准备夹具和57个原始结果均保持原字节；本报告不宣称完整门禁通过。

旧 `file_digest` 明确计算文件名 UTF-8 字节与原文件字节拼接后的 SHA256。生成端 `run_p3b5_tasks.py:314` 沿用此约定；原只读 checker:459 按纯源码比较，造成格式错配。独立审核已同时核验保存源码、实际冻结文件、旧摘要和运行前声明的纯字节摘要。计划修复只读校验器，继续检查实际命令路径及预声明源码，不放宽物理、时限、TTL、任务或安全条件。

首次严格检查命令及原始异常：

```text
/usr/bin/python3 scripts/check_p3b5_gate.py log/p3b5/p3b5_v106_zero/summary.json log/p3b5/p3b5_v106_lab/summary.json log/p3b5/p3b5_v106_rooms/summary.json log/p3b5/p3b5_v106_forced/summary.json log/p3b5/p3b5_v106_corridors/summary.json log/p3b5/p3b5_v106_holdout/summary.json --ideal-fixed log/p2d_baseline/p3b5_v106_fixed_lab101/summary.json log/p2d_baseline/p3b5_v106_fixed_lab/summary.json log/p2d_baseline/p3b5_v106_fixed_rooms/summary.json log/p2d_baseline/p3b5_v106_fixed_corridors/summary.json --forced log/p3b5/p3b5_v106_forced/summary.json --safety-probes log/p3b5/p3b5_v106_safety/summary.json --return-proof log/p3b5/p3b5_v106_returnproof/summary.json --return-physics log/p3b5/p3b5_v106_returnproof_physics/metadata.json --historical-ideal log/p2d_baseline/p3b5_ideal_gate_5c58bc7/summary.json --protocol log/p3b5_protocol_d8d361b.json --output /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/20261006_p3b5_gate.json

Traceback (most recent call last):
  File "/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/check_p3b5_gate.py", line 527, in <module>
    if __name__=='__main__': main()
  File "/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/scripts/check_p3b5_gate.py", line 459, in main
    assert hashlib.sha256(row['staging_source'].encode()).hexdigest()==row['staging_source_sha256']
AssertionError
```
