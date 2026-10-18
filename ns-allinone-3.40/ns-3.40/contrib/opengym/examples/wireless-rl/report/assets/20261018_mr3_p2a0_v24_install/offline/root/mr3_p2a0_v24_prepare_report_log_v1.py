import hashlib
from pathlib import Path

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A = W / 'report/assets/20261018_mr3_p2a0_v24_install'
B = Path('/tmp/mr3_p2a0_v24_report_preparation_v1')
report = (B / 'report_v24_preparatory_draft.md').read_text()
entry = (B / 'log_append_v24_preparation.txt').read_text()
assert hashlib.sha256(report.encode()).hexdigest() == '504731e3a545481b698bfc8fabb33a09d9e85e1c96f52693032e56b5085c637a'
assert hashlib.sha256(entry.encode()).hexdigest() == '5efa578cd6e4565de1b06e27eae830ce10931e728278b5892a33f7f16c61c536'
for name in ('report_v24_preparatory_draft.md', 'log_append_v24_preparation.txt', 'exact_commands_v1.json', 'budget_prior_v1.json'):
    destination = A / 'offline/report_preparation' / name
    assert not destination.exists()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes((B / name).read_bytes())
old = '最终ENV `cc467064ab66e04507ed4d4e805a4e23cdf09b3716fd85517ebb34fe7b2de521`、auditor `f1e0be60d35db3677fb9194341c1ae4133a5c74ed7199056fe18f7e797f40416`'
new = '最终auditor `cc467064ab66e04507ed4d4e805a4e23cdf09b3716fd85517ebb34fe7b2de521`、ENV `f1e0be60d35db3677fb9194341c1ae4133a5c74ed7199056fe18f7e797f40416`'
assert report.count(old) == 1
report = report.replace(old, new).replace('17928.02160631492734', '17928.021606314927').replace('至少一机双向', '至少一台实际转向反转')
report = report.replace('原任务95%、18路接触/新鲜度', '原任务95%/300s、每机1m和已接收目标、.50m队友安全包络、18路接触/新鲜度')
old = 'finalENVcc467064…/auditorf1e0be60…'
assert entry.count(old) == 1
entry = entry.replace(old, 'finalauditorcc467064…/ENVf1e0be60…').replace('17928.02160631492734', '17928.021606314927').replace('finalnarrow/frozenpreflight仍PENDING', '最终实际冻结前检仍PENDING')
entry += '''

Root于源码文案转录复核时更正agent草稿中交换的ENV/auditor标签；原草稿四件完整保管于A24/offline/report_preparation，哈希本身未变。实际build由独立读取44输入复核PASS（review59e7462c…），35原件407779B→75990B tar117e3eafa…，2CPU可执行物只记身份排除；A24/offline/build原件全量decode核验。根source promotion、actual binary archiver、原16 unit stdout/stderr/receipt共13件19894B保管A24/offline/root，非新native。
CI新增preInit consumer6方法级检查（最终f65c/test1192，源字段strictbool/null/phase/原bounds）与4项固定binary身份正负检查PASS；最终因果措辞后只补2 ENV身份正负检查，不重复16 unit/旧ROS170/旧SDK/旧数学套件。初稿watcher路径残留A22、binding额外metadata、原测试TMP依赖及inline handoff SyntaxError均在执行native前发现，原件保留；仅修接线/便携性，不把失败改为实际原生成功。最终plan中active SO scalar残留7be亦在独立审查时发现，待唯一元数据更正后声明新计划哈希，未运行旧声明。
'''
destination = W / 'report/20261018_mr3_p2a0_v24_install.md'
assert not destination.exists()
destination.write_text(report)
with (W / 'log.md').open('a') as output:
    output.write(entry)
print('V24 report/log written with corrected source labels; original drafts preserved.')
