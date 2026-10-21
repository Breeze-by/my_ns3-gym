# MR3 P2A V31 Karto 显式模式的有界闭环验证

**已闭合：profile与三场完整300秒工程/独立审计PASS，三场任务0/3；rooms行动入口的净空证书缺口已定位。工程余5308.5872556263982秒。以下执行前范围保留，实际结果与下一步见后续节。**

本轮用户反复要求继续并“直接全部做完”，因此继续完成已授权的实现和验证，不在常规修改处重复请求确认。[事前范围](assets/20261021_mr3_p2a_v31_karto_behavior/scope_acceptance_v1.json)固定总工程块4500墙秒：单env/open101、8次以内profile最多600秒；只有同冻结完整profile/独立审计/实际wait/外部关闭通过后，才准一次三env open/rooms/corridors101、各最多300步/总900attempt、最多3600秒长行为；另预留300秒有限故障提取。没有补样、重试或训练。

准入使用V30实际构建的显式nativeAddScan薄适配库，默认endpoint保持。新计划、输出目录、source inventory、C++/SDK headers和实际ELF manifest独立绑定；不能复用V23/V24活动或其资格。收集前仍执行原接口符合性及独立检查；收集后独立重算actor输入、动作流、源龄与时间、奖励/行为。真实任务失败不由工程检查PASS覆盖。

入场累计45445.4237026666018/52000，余6554.5762973333982秒；4500块最坏留2054.5762973333982。费用按实际工程消费者区间union计，嵌套/并行不重算。pilot1870/2905.9547395464029、final-only401/402/403不动；二维训练额度、60000扩额、原生完整20100预约、P2B和gateway均未解锁。原三机、95%/300秒和质量.20/.02/.95门保持。P2A未完成。

当前为执行前声明，实际freeze、结果、费用和身份关闭将在本轮真实wait后追加。

## 同冻结实际结果

冻结`e7dc6903c0bb4c2fe09f0eb07266f46c9d259022`已commit/push后，clean前检通过；一次profile及一次三场behavior均完整工程PASS，没有重跑任何回合。默认endpoint未变。canonical原件见[闭合元数据/字节目录](assets/20261021_mr3_p2a_v31_karto_behavior/closed_metadata_v1.json)，1030文件、53542627bytes；其中包含两活动全部原件、实际outer、外部final及有限诊断失败/修复启动原件。

profile：8attempt/8return/0error，独立8action/8uniform/8return/9actor全验证，全部五阶段正常wait/source稳定、实际ELF匹配；main72.421918153＋final.593262480＝73.015180633秒。它是8步external_sampler_limit，不是任务成功。

behavior：三场各300步/300模拟秒真timeout，合计900attempt/900return/0error、900action/uniform/return与903actor全量独立验证。符合性/独立review/收集/审计/行为复算均PASS；全部接收输入、时钟、奖励与终态复算完整。无代理contact/unsafe记录；这不提供18路原生接触信用。三场任务均FAIL，不能用工程PASS覆盖。

| 场景 seed101 | 正确自由覆盖 | observed accuracy | occupied IoU | false-free | 质量/参与 | 三机物理路径m |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| open | 88.6127% | .972666 | .217144 | .008719 | PASS/PASS | 18.9762 / 16.0613 / 2.8079 |
| rooms | 58.3095% | .973877 | .109719 | .009877 | FAIL/FAIL | 0 / 0 / 0 |
| corridors | 38.4102% | .966650 | .114666 | .004532 | FAIL/FAIL | 9.1407 / 0 / 0 |

全部accuracy/false-free达原门；open还通过IoU门，rooms/corridors未达.20。当前不足包含探索覆盖和参与缺口，不能把低IoU直接归为表示绝对不可达。三场原95%门保持，任务成功0/3。V24是不同mapper/候选/轨迹的中断前缀，不能将两表差值称Karto的因果改善。

behavior phase实际嵌套墙时：conformity12.948255985、review.867118585、collection1005.968856839、audit71.611394057、behavior71.064959065秒；三worker并行及这些阶段不另加。main1164.760905882＋final.774370344＝1165.535276226秒，含所有外尾。实际SDK1848be4216072cad09e74680d9b474ad0908dd9d98ed9c01838d316a76efd80b及v2adapter b197d185864c16d66f8cf49690827d9c132acfdaf82ac3fee7106a107ee2de61逐项匹配manifest与worker /proc映射；source/bound_bytes稳定。profile final原保存12身份、behavior final原保存16身份均gone；全活动/诊断/outer合并36保存身份fresh gone。

base audit遗留字段`complete_full_behavior_diagnostic=false`仅识别旧kind full_behavior，未识别新karto_behavior，是标签假阴性；原JSON保持不改。真300秒终态、900全验证与工程PASS由其余完整原字段及独立行为复算支持，不把该标签当新矩阵/训练资格。

## 有限诊断：行动入口在起点证书处关闭

[诊断声明v1](assets/20261021_mr3_p2a_v31_karto_behavior/forensic_plan_v1.json)拟一个有限只读consumer；首次直接脚本启动因`mr3_learning`导入路径错误，在任何原件读取前rc1、实际1.317476475秒。失败源码/console/费用保留。[v2启动修订](assets/20261021_mr3_p2a_v31_karto_behavior/forensic_plan_v2.json)只改为system Python从canonical cwd经runpy启动同一诊断源，无World/scene/ENV/SDK重试；在同一300秒预留内rc0、actualwait4.121108373秒。另一个先行输入结构peek未提供资格信用，完整工具调用耗时1.5秒保守计2秒，不隐去这一未包装读取。

[诊断结果](assets/20261021_mr3_p2a_v31_karto_behavior/forensic_result_v1.json)固定读取三场reset、final和首次三机seed都被拒绝的边界，共9份原actor输入及已核trace/ref，前后字节稳定。使用原received own/navigation/fused map、原估计pose与原净空函数，不用truth，不改输入/阈值/掩码。rooms tb2/tb3在全部301观测被seed_pose_body_clearance拒绝；tb1从15秒后也连续286观测被拒绝。rooms 298/301观测没有合法GOAL（另有KEEP/WAIT），三机物理平移均0。corridors三机共同seed拒绝127/301，且263/301无合法GOAL；open共同拒绝1/301，205/301无GOAL。这些是观测边界计数，不能直接当持续秒数，也不能与reason多标签数量相加。

所选初始、rooms15秒/final等原件中，own与navigation均给tb2/tb3约.282843m净空下界，小于原.29m；最近occupied cell centre距估计pose约.3553m。原seed cell本身可以过门，但“cell-bound再扣pose偏移”的保守下界拒绝了实际起点。不能仅由centre距离宣称真实安全；必须证明点到整块non-free closed cell以及pose→同一seed-centre桥的连续距离。fused图更保守，但本次实际导航拒绝在own图也出现，不能归咎只读fused、用优先级覆盖或清除占据。近界几何证书是否假阴性，是下一项可检验假设；当前证据尚未给出安全修复。

## 费用、判断与后续边界

六个实际outer不相交的union为1243.989041707秒（两活动main/final、失败诊断启动及修订启动）；另加明确披露的2秒discovery保守上计，本轮1245.989041707秒。累计**46691.4127443736018/52000**，余**5308.5872556263982**。未将嵌套阶段、三worker并行或等待间隙重复相加。pilot1870/2905.9547395464029和final-only401/402/403均未动。

判断：保留联合RL方向；快速代理已能完成稳定的三场长回合工程验证，open质量门也能通过，继续原样堆mapper/阈值或随机矩阵价值低。优先检验并修复行动入口的保守几何证书，再决定学习投入。当前掩码缺口不是PPO训练可自行改写的条件；不能根据随机0/3否定RL，也不能以Karto名称主张完整SLAM/偏差修正。完整SLAM亦未必改变相同occupancy核的表面/量程问题，不自动选为修复。

下一步保持原.29m、unknown/outside blocked、原seed cell和既有traversable graph，只做禁用的精确点/桥证书CPU原型及反例，先证明收益与拒绝条件，不能snap/移动机器人、删occupied、lower margin或改任务门。新的actor观测/安全规则必须明确版本与准入；V21纯观测源码逐字门尚不容许直接替换。二维PPO额度、原生完整20100秒预约、60000扩额仍未批准/不可容纳，不能消耗pilot绕过。P2A仍未完成，P2B/gateway未启动。

最终[静态核验](assets/20261021_mr3_p2a_v31_karto_behavior/static_result_v1.json)rc0/actualwait2.471473577s，核1030原件、全部原source/ELF、账、终态及338链接；外层wait后[38保存身份全gone](assets/20261021_mr3_p2a_v31_karto_behavior/saved_process_absence_v1.json)（36活动/诊断＋2静态CPU），工程新增0。

后续[V32禁用几何原型](20261021_mr3_p2a_v32_seed_certificate.md)已完成14项人工CPU，尚未接生产或提供真实场景信用；下一AI不应从零重复原型，按V32边界设计新版本/准入。
