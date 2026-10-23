# V61 五原件/接口清单：仅库存与源码元数据审查

证据冻结：`935b466bd076002afdfe161b55a508938de2a8b0`。未打开/读取/哈希五份raw，未运行reader/extractor/native，未修改repo或既有spec/admitted。当前raw SHA仅引用已闭合库存；此次仅核lstat/父目录和源码。

五原件合计 **523,777,922B**，全部原始plain文件、codec=`identity`；encoded与decoded字节/SHA可严格相同。库存的`gzip-mtime0-lossless`描述archive wrapper，不是这些原始输入的codec。

| input | logical_name | encoded bytes | closed original SHA256 |
| --- | --- | ---: | --- |
| adapter | `adapter.jsonl` | 11429267 | `049eaf8777c5ba79d47ccb74e30cd169c7b0e61ad8eee76f3e4e4ae939e345db` |
| motion | `motion_safety.jsonl` | 497781379 | `f77d80b7c240272ea326e67d64ab04032d98dd5b94274aac351198e737439b5b` |
| drive | `drive_tb2.jsonl` | 9096480 | `c7925e07c8c124ae22117134d4316b0c16edc5d2b7b9ba6d07e817583bf420ad` |
| odom | `odometry_tb2.jsonl` | 5240220 | `8815f9ef64d504dc0607aacb69e8ecc359aa45ee617d7788030baa9db41df125` |
| launch | `launch.log` | 230576 | `33bf50a6b89d90554940a0479ada881f6f0ba88b452207390a4dcc5c37a278bb` |

共同原始目录：

`/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_reach_v60/mr3_p2a_reach_v60_reset/worker1/episode002_open_101/`

五个lstat均regular，逐级父目录无symlink，字面路径等于canonical路径，dev/ino/mode/size/mtime/ctime均仍等库存source_stat_after。此元数据相等不替代未来consumer的全字节SHA。adapter另有原始.gz，但本清单有意选择库存指定plain路径，不混用不同原始对象。

前瞻limits建议（未安装）：两个total byte cap均523777922；每份decoded_byte_limit等各自原始bytes；line_bytes=8388608、lines_per_file=2000000、selected_records=12000、selected_raw_bytes=8388608、output_bytes=33554432、work_seconds=480，完整parent=660。行数/最大行长/选中行数未知，不把这些上限称为观测值或保证；触限保留INCOMPLETE/全费，不自动补读/重试。32MiB输出低于driver 64MiB metadata cap。

adapter用stamp秒，motion用sim_time_sec及有来源的odom/header或native-ingress时钟，drive用sim_time_ns，odom用sim_time_ns/source_clock_ns；actor/record_sequence格式与E producer源码静态兼容。launch只有原始文本和literal上下文，保留UNKNOWN_UNMAPPED_NATIVE_LOG，不虚构仿真时间或跨进程全序。细节见JSON。

16份解释源逐字等Git E及原spec pin。库存/ledger/closed-review实际schema与driver/consumer所需布尔和root rc字段相容；ledger为passed=true的工程关闭账，但activity_passed=false、root rc1、P2A_complete=false，不能改称科学PASS。实际余额108848.4042410476018/150000、余41151.5957589523982可覆盖660完整parent，nested不加。

下一安装时建议将canonical consumer明确命名cancel_window_extract_v3.py，联动driver CONSUMER、scope.source_bindings key与spec.consumer path/bytes/SHA。旧pending v4仍指v2(cc2930...)，不能只填inputs后误用；v3为860b69...，须新canonical CPU与新clean/pushed freeze。所有exact路径和metadata pins可直接从metadata_review_v1.json取用；本文件不是spec，不提供admission。
