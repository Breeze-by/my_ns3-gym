# V65 构建来源拒绝与 V66 最小修复事实

V65 的 preflight FAIL 保持，0 World/0 matrix。A59 实际 build 的20个活动输入中，唯一改变的是第15行（零起始14）的 `mr3_learning/supervisor.py`：28,792B/b82379db…bfd92 →29,590B/7cf7f5fc…afde0。变化来自 receiving-authority metadata 和 outward-cancel-v2 的 Python 编排；它通过 reach_execution→preparation→native_custody→supervisor 被构建回执工具导入，属于活动来源 pin，不是编入驱动 ELF 的 C++。新导入的 motion_authority_profile.py 因而作为第21活动输入单独绑定。

CPP、六个header、CMake、原driver编译命令及数值选项均未改变。实际 ELF 仍2,122,904B/SHA df5d9703f23fd206b967eb9408a4504ed3735b9f71a3c31194b60443464139c7，逐字等于A59归档恢复；flags仍3,875B/d889c9d41fe50bbc16c52910398a449e4d2f8bde3ef6108ea3795cd21e805df4，7个源宏完整。原门要求全部活动输入当前字节等于旧actual before/after，所以拒绝是诚实的来源不匹配；没有改门或引入兼容例外。

Root在V66实际执行原A59脚本/argv的新CPU构建活动，tool24786真实reap0，child2.547287208秒，当前21源before/after稳定并核两身份gone。新manifest/bridge分别封在V66命名空间，原A59证据不写。此次是增量colcon活动：ELF同字节，没有虚称新compiler/link任务，也没有声称Python编入ELF或取得新的原生科学资格。原脚本只更新ROS mutable build/install/log，新回执/flags/ELFgzip/manifest/bridge不覆盖历史原件。

构建后已实际调用现有 native_custody.file_proof 复核A65 binding的全部10个二进制角色，resolved_path、SHA、bytes和dev/ino/size/mtime_ns/ctime_ns均10/10一致，stale objectstat为0；未执行这些二进制或loader。新binding仍须承接V66真实build证据并在新freeze检查当前来源，不能继续指向造成V65拒绝的旧A59活动pin。后续完整native资格与原科学门独立进行，本诊断不提供P2A/性能/容量信用。
