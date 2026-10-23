# V52 实际闭合 CPU 与归档恢复

[闭合 CPU 证据](closed_cpu_evidence_v1.json)逐份核对六份真实 `actual_wait.json`、完整控制台 SHA、整数纳秒差与 Decimal 秒、原返回码、source-before/after 以及[可恢复源码索引](source_recovery_index_v1.json)。其中 overlay 人工 v1 的 rc1 原样保留；本证据 PASS 表示其失败原件和后继验证完整，不把原失败改为成功。原 argv 和 `/tmp` 路径保留，索引提供长期可恢复的对应字节。工具原文件名含 `draft` 是不可改的历史名称，真实是否运行以回执为准。

| 工作 | 原 rc | 实际 CPU 秒 | 验证范围 |
|---|---:|---:|---|
| tool-wait 人工 v2 |0|0.891500478|8 项正常/伪造 wait 与关键 ref 绑定 fixture |
| overlay 人工 v1 |1|1.57412754|8 项中 3 FAIL、2 ERROR，原件保留 |
| overlay 人工 v2 |0|8.187965435|9 项人工分片/恢复/失败保留 fixture |
| 实际闭合 metadata review v2 |0|9.116843688|实际工具 wait、933 源/10 ELF、主活动 611 保存身份 |
| 实际 lossless collector v2 |0|1721.014750639|7772 文件的原字节归档及已有解码校验 |
| 实际 packed overlay v2 |0|20.440347567|仅既有 packed 二进制分片、连接校验及精确 ignore |

独立 fresh `/proc` 核对以上六组的 **12 个 CPU PID/start**；同 start 的 Z 仍算 present，不可读也不能当 gone。[新 seal 的 actualwait](seal_cpu_actual_wait_v1/actual_wait.json)为 rc0、0.638006453 秒、六源稳定；其另外两个身份在实际工具 reap 后才写入[单独关闭记录](seal_cpu_postreap_v1.json)。这 14 个后继 CPU 身份与主活动 611 个身份分开，工程新增均为 0。本次 seal 只读小元数据/源码及 `/proc`，没有重跑 review、collector、overlay、科学 reader 或 raw/packed 内容。

`provenance/` 保存原静态审查、原人工验证证明和 deadline 小元数据说明。最初 reviewer 的 critical-ref latch 缺口和 overlay v1 不兼容 Git `check-ignore --literal-pathspecs` 的失败均保留；实际使用的 v2 经相应人工检查后执行。静态意见及人工检查不提供原生或学习资格。

## 两层归档表示

不变的 [V1 原库存](../../closed_inventory_v1.json) SHA 为 `63efb61cc7b2abaf723b3824399d203a1a0b288465a367110eabcb5ec565ccf7`，记录 7772 个逻辑原文件、15628170281 原字节、1293834289 packed canonical 字节、0 symlink。缺失的 policy root 是原活动从未启动学习的事实，不补造目录。V1 的名称/schema 含历史 `draft-v2` 字样，实际 `byte_archive_complete=true` 与真实 collector 回执共同建立闭合证明。

[最终 overlay manifest](../../packed_overlay_v1/manifest.json) SHA 为 `0b5d73736e9560982ca6234cb49e59d589de21e83d40ddeff3ead1abcb6104ad`。仅将以下两条既有 gzip 字节流拆成六份，每份至多 67108864 B；没有解压、重压、原始流重放或删除。每份 index/offset/bytes/SHA 和完整连接后的 packed SHA，以及对应 raw SHA 都在 manifest 中。V1 的原始 decoded-byte 证明保持，不为 overlay 再执行。

| 原 packed 尾路径 | packed 字节 | 分片数 | 完整 packed SHA256 |
|---|---:|---:|---|
| `information_states.jsonl.rawbytes.gz` |92314505|2|`a9181f78d15ae5c28a05d29d424b6654995c2ddec23d3708852825b2dd81d38c`|
| `motion_safety.jsonl.rawbytes.gz` |214063938|4|`74c8ea58dad810ef5e2b00917f42bb8de32b36008c050127dfcc92baeea00bf9`|

两条完整路径均位于 `closed_execution/native/mr3_p2a_reach_v52_deadline/worker0/episode001_open_101/`。原 packed 文件仍留本地，仅由 `closed_execution/.gitignore` 的两条精确路径排除 Git；其余 V1 原件、不可变 V1 inventory、分片及 manifest 必须提交。V1 canonical 字节指标指分片前的逻辑 packed 内容，不是保留本地双份后的磁盘用量。

## 从 Git 分片恢复 packed 字节

以下是未来恢复命令，本次闭合没有再运行。先在规范 checkout 中验证固定 manifest、V1 inventory 与恢复工具 SHA，再为每条目标选择一个**不存在**的输出文件：

```bash
V52_A=/home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261023_mr3_p2a_v52_qualification
/usr/bin/python3 -B - "$V52_A" <<'PY'
from pathlib import Path
import hashlib, sys
a = Path(sys.argv[1])
expected = {
    'closed_inventory_v1.json': '63efb61cc7b2abaf723b3824399d203a1a0b288465a367110eabcb5ec565ccf7',
    'packed_overlay_v1/manifest.json': '0b5d73736e9560982ca6234cb49e59d589de21e83d40ddeff3ead1abcb6104ad',
    'checks/closure_v2/tools/mr3_p2a_v52_packed_overlay_v2.py': 'b655d8c76573e8dc717d1e01b7627372e215fe568de05b7b76dfa50188caca5b',
}
for name, digest in expected.items():
    assert hashlib.sha256((a / name).read_bytes()).hexdigest() == digest, name
PY
/usr/bin/python3 -B "$V52_A/checks/closure_v2/tools/mr3_p2a_v52_packed_overlay_v2.py" restore \
  --manifest "$V52_A/packed_overlay_v1/manifest.json" \
  --canonical closed_execution/native/mr3_p2a_reach_v52_deadline/worker0/episode001_open_101/information_states.jsonl.rawbytes.gz \
  --output /tmp/mr3_v52_restored_information_states.rawbytes.gz
/usr/bin/python3 -B "$V52_A/checks/closure_v2/tools/mr3_p2a_v52_packed_overlay_v2.py" restore \
  --manifest "$V52_A/packed_overlay_v1/manifest.json" \
  --canonical closed_execution/native/mr3_p2a_reach_v52_deadline/worker0/episode001_open_101/motion_safety.jsonl.rawbytes.gz \
  --output /tmp/mr3_v52_restored_motion_safety.rawbytes.gz
```

`restore` 使用 exclusive 创建，逐份核 SHA/size、连续 offset 和次序，最后核完整 packed SHA/size，并返回 `decoded:false`。失败时保留部分输出，不能将它当成功恢复。分片文件名中的 `closed.tar.gz` 只是原 splitter 的通用名称，连接结果是上表对应原 gzip，不能当作 tar 解包。若以后需要原 JSONL，另行有界安排 gzip 解码并核 manifest 的 `original_bytes` 与 `original_sha256`；packed SHA 与 raw SHA 不能混用。

当前正式结论、完整累计账和下一路线见[规范末账](../../closure_ledger_v1.json)及[报告实际闭合段](../../../../20261023_mr3_p2a_v52_qualification.md)。P2A 未完成，CPU/归档 PASS 不替代 deadline 必要审计、minimum、pilot 或 strict95 final-only。
