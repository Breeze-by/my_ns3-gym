# V63：只描述V62两份已保存main profile（待闭合/未执行）

候选只消费固定motion_safety/main.pstats与adapter/main.pstats，**不重新采样、不重试原活动、不改10秒启动守卫**。V62原startup FAIL/0个返回transition保留；本描述若PASS只表示两份指定字节完整解码，不是8步、5lane、native/科学/容量或P2A通过。root cause固定UNKNOWN，不能预填性能归因。

原件pin只取自两份已闭合finished.json：motion402910B/SHA69f76cf0131e2bec91fa4cb969286a4c671eed091ea3e3077dc4d0178f451d93（原profile_complete=true，processCPU154460687906ns）；adapter492030B/SHA5f8451996b4aefdef30fb414a4d2f1e3ec11e4a3f9a494bd3da098306d89e81e（原profile_complete=false，encoder unobserved）。准备阶段未读或stat两pstats、未读原logs、未跑consumer/tests/native。

实现只AST提取A62 review_profile_v1.py原require+pstats_description两个节点，完整module19058B/SHAc83a9e97804158e085fbe1b4146621846b4d3f6c2e287d3dda71dd3b5955b9bf及Git G=81e63f50699073286c9773dcb92106de63fdf4ca逐字绑定，不import执行原full reviewer。不复制/改写统计算法，不读取pstats中函数名指向的源文件。pstats一次完整read同时核SHA后在内存marshal解码，复用原top30 self/cumulative描述。elapsed function时间包含等待、cumulative重叠；不能当CPU逐核分解、C++热点、吞吐或容量证明。

规范路径拟W/report/assets/20261024_mr3_p2a_v63_profile_description。consumer CLI：`describe_partial_profiles_v1.py --freeze HEX --spec A63/spec_v1.json --output /tmp/mr3_p2a_v63_profile_description_v1.json`。必须canonical consumer/spec本体同new clean pushed freeze。admitted必须True且闭合库存pin完整后，才允许打开pstats；现在spec是False、库存bytes/SHA为null，故不能正式消费。V62库存必须是closed_inventory_v1.json schema mr3-v62-opaque-closed-inventory-v1，entries[].original精确同对象匹配original_bytes/original_sha256；不跟archive canonical压缩包装作原件。

固定max2profiles、每份1MiB、profile累计2MiB（声明原件合894940B）；metadata/source读另受累计8MiB cap，旧scope338417B、finished元数据、完整库存、新spec/consumer及原描述源都逐次完整计数，Git返回源字节另记；不只算命中函数/行。work≤60秒协作式前后时间检查，root掌管complete parent120秒（含准入、全部读/解码、输出、真实reap/absence），不宣称硬实时。输出超1MiB会保留小partial FAIL摘要，原失败原件不动。

parent/scope/入场结算归root：U109067.3998164526018/C150000，余40932.6001835473982；按完整实际parent收取，不叠nested，pilot/final新增0。numeric_user_approval_claimed=false。新freeze前不得消费原profile。

已准备最短2组人工CPU源码与spec草案，**仅AST解析、没有执行**：一组只生成临时synthetic cProfile字节、验证原纯函数/单次读取；一组覆盖pending拒绝、额外profile、浮点pin、缺库存/错误原路径、提高资源、原库存错pin拒绝。人工pending负例显式构造False，不依赖正式spec最终是否admitted。后继CPU必须用reach_execution --scope cpu、实际wait/JUnit、源前后/快照恢复和freshgone；此处没有CPU/实际pstats信用。


## V2实际准备状态

V62库存已经真实闭合：216484B/SHA932696bd20ffa8beedfb7afbe1aca36a47c55d6075c2b75024a02d1249c7cdc4；148 regular原件213343452B→15944926B、0links。这里只读取其小metadata，未读/stat两原pstats。canonical V62 closure ledger7618B/SHA576b944fa34a4ad3d9d09a2af879de071f9f77fc5dc8ae5afc978d4038cfdf3c已实际物化，入场109067.3998164526018/C150000/余40932.6001835473982由真实ledger绑定。V2 spec/scope均admitted=true，但仍必须安装canonical、clean push新source freeze后才能实际消费。上文V1 pending/未执行段保留为当时准备快照。

新增fixed run_description_v1.py/bootstrap_v1.py：bootstrap先存真实PID/start/观测祖先再exec新driver；祖先非owned不发信号。bootstrap由G已审A62源码只改固定名字/路径，完整逆投影证明在bootstrap_source_projection_v1.json。driver只import G绑定的A62/A61纯proof/identity/wait定义，不调用旧activity main或旧budget。primitives导入失败也独立写failure summary，PID/start不匹配不授complete fee；无法证明完整start时actual_parent/cumulative=None，并保真实driver lower bound。descriptor deadline=min(now+60, complete_start+90)，剩余尾部含升级/真实wait/post-source，实际parent超120仍全费FAIL，不宣称硬实时。parent pre/post source集合明确拒绝.pstats，只有descriptor实际一遍读/解码两原件。

人工CPU初轮provisional tool42204真实reap0/.780771671s，4PASS（consumer2+parent早失败2），79源稳定/3身份gone，原件在checks/consumer_cpu_v1。真实ledger与admitted spec/scope补齐后，最终tool73756真实reap0/.870841188s，4PASS/0FES，82源before/after/current及快照逐项一致、3保存身份freshgone，证明checks/consumer_cpu_v2/proof_v1.json。测试只造synthetic pstats并复用原纯函数，实际覆盖pending/资源/pin/库存拒绝与parent import失败、bootstrap PID/start不匹配；未执行reader main、正向parent/bootstrap exec、原pstats、原logs、World或模型。CPU新增工程0。

root仍负责最终canonical安装映射/新freeze/实际唯一描述的根tool reap与driver freshgone；若canonical路径或source bytes变化，不能冒用/tmp CPU为新源信用。Scope+spec的5runtime文件、2tests及本说明见install manifest；旧V1目录完全保留。
