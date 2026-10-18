import hashlib
import json
from pathlib import Path

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A = W / 'report/assets/20261018_mr3_p2a0_v24_install'
items = [(Path('/tmp/mr3_p2a0_v24_candidate_offline_sealed_v1.tar.gz'), 'offline/candidate/originals.tar.gz', '677bd24780248becbde814c8e9328ed8895417e9956a59632dcbd2f8288f1b18'), (Path('/tmp/mr3_p2a0_v24_candidate_offline_custody_v1.json'), 'offline/candidate/custody_v1.json', None), (Path('/tmp/mr3_p2a0_v24_matrix_metadata_addendum_sealed_v2.tar.gz'), 'offline/metadata_addendum_v2/originals.tar.gz', '0eea5836ef55eeba07aa320f581ff240f66f10a929e42d7493c3dd29c271b66f'), (Path('/tmp/mr3_p2a0_v24_matrix_metadata_addendum_custody_v2.json'), 'offline/metadata_addendum_v2/custody_v2.json', None)]
for directory, target in ((Path('/tmp/mr3_p2a0_v24_report_preparation_v1'), 'offline/report_preparation'), (Path('/tmp/mr3_p2a0_v24_matrix_pack_proposal_v1'), 'offline/closed_pack_preparation')):
    h = json.loads((directory / 'handoff_v1.json').read_text())
    assert h['all_writers_stopped']
    for p in sorted(directory.rglob('*')):
        if p.is_file():
            items.append((p, str(Path(target) / p.relative_to(directory)), None))
records = []
for source, relative, expected in items:
    raw = source.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if expected:
        assert digest == expected
    destination = A / relative
    if destination.exists():
        assert destination.read_bytes() == raw
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)
    assert destination.read_bytes() == raw
    records.append({'original': str(source), 'canonical': str(destination.relative_to(ROOT)), 'bytes': len(raw), 'sha256': digest})
result = {'schema': 'mr3-v24-root-preparation-original-custody-v1', 'files': records, 'scope': 'Original stopped source/CPU/draft/failure receipts, final one-field plan addendum and prospective closed collector; no native results.'}
(A / 'offline/preparation_copy_receipt_v1.json').write_text(json.dumps(result, indent=2) + '\n')
p = W / 'report/20261018_mr3_p2a0_v24_install.md'
text = p.read_text()
text = text.replace('最终计划/bindings、clean commit/push、source/ELF准入和完整同冻结四阶段仍待完成。', '最终计划和210项绑定已完成；clean commit/push、实际冻结准入和完整同冻结四阶段仍待完成。')
text = text.replace('- **PENDING**：CI最终source/admission/ENV/auditor/matrix bindings与精确计划SHA（预计210binding，未在本草稿授已冻结信用）。', '- **已完成源码准备**：固定auditor/ENV、actual782d/receipt84bb、新consumerf65及六协调器；210项绑定保留196项旧SHA，明确更新currentCPP/auditor两项并增加12项，不冒充旧198全不变。')
text += '''

## 源码收口与执行入口

[最终计划](assets/20261018_mr3_p2a0_v24_install/predeclared_plan_v24.json)
SHA `d682f40c01a660f598cdf6c81d9faa640c25af1ba87d9e96e56701bb2fec4ffc`，
[运行身份绑定](assets/20261018_mr3_p2a0_v24_install/independent/mr3_v24_corrector_binding_v1.json)
SHA `f21b16dbbf6101483c002c1fabd726ca0b8ea4c4051c1691d1d109adb786c854`。
固定audit与de297只改变5项constant赋值，所有函数不变；六协调器经明确版本/路径/累计成本逆替换恢复A23，
原Conda learner与系统ROS/parent边界、34门及每一实际违规独立失败的规则保持。

[作者原件](assets/20261018_mr3_p2a0_v24_install/offline/candidate/custody_v1.json)
保管88件1147551字节，包括初稿/失败和CPU真实来源。
独审在native前发现初计划active SO scalar残留旧7be；
[唯一字段补正](assets/20261018_mr3_p2a0_v24_install/offline/metadata_addendum_v2/custody_v2.json)
保留初631d原件，最终仅该字段指向actual782d，所有210绑定/源码/数学/预算不变。
consumer6项、binary身份4项及最终ENV2项检查各保留其真实源码和原输出，未重复旧ROS/SDK套件。

在wireless-rl目录，新代码clean commit并push之后，首先执行真实完整预检：

```bash
env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B report/assets/20261018_mr3_p2a0_v24_install/independent/mr3_p2a0_v24_buildproof_preflight.py
```

实际PASS后，以同一完整冻结SHA替换EXACT40，先启动monitor确认START，再启动唯一parent：

```bash
env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B report/assets/20261018_mr3_p2a0_v24_install/independent/mr3_p2a0_v24_cross_stage_mapping_monitor_v1.py --freeze EXACT40
env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B report/assets/20261018_mr3_p2a0_v24_install/independent/mr3_p2a0_v24_run_matrix_v1.py EXACT40
```

所有native、必需消费者和monitor自然关闭前保持源码/二进制/Git冻结；本段为执行入口，尚未授任何新原生结果信用。
'''
p.write_text(text)
with (W / 'log.md').open('a') as output:
    output.write('\n最终作者SOURCE/PLAN/METADATA/离线writer均STOP。Root按handoff先提升12项中的8项新文件、4项已同一文件只核字节；随后仅将plan /native_ray_box_correction/actual_library_sha256残留7be改782d，finalplan d682f40c01a660f598cdf6c81d9faa640c25af1ba87d9e96e56701bb2fec4ffc，binding f21b16dbbf6101483c002c1fabd726ca0b8ea4c4051c1691d1d109adb786c854。原631d、其handoff及错误scalar原件保留，未执行。作者88件1147551rawB→335024B tar677bd247…，addendum5件155343rawB→37840B tar0eea5836…，逐字往返/源末stat稳定；canonical分别offline/candidate和metadata_addendum_v2。最终210＝旧198中196同SHA＋currentCPP/auditor明确刷新2＋12新身份，原test43e13/其他source/34数学及累计71.97839368507266全不变。Root更新当前guide/路线及launch_commands中的准确Conda/monitor/parent命令，未启新native；新clean pushed冻结实际准入仍待执行。\n')
print(json.dumps({'selected': len(records), 'bytes': sum(r['bytes'] for r in records), 'native': False}))
