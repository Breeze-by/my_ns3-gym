import json
from pathlib import Path

p = Path('/tmp/mr3_p2a0_v24_copy_closed_evidence_v1.py')
text = p.read_text()
old = '''    assert not destination.exists(), str(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(raw)
    assert destination.read_bytes() == raw'''
new = '''    if destination.exists():
        assert destination.read_bytes() == raw, str(destination)
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)
    assert destination.read_bytes() == raw'''
assert text.count(old) == 1
text = text.replace(old, new)
old = '''for name in ('manifest_v1.json', 'handoff_v1.json', 'originals.tar.gz', 'raw_guard_smoother_review_v2.json'):
    copy(body / name, A / 'closed_body_review_v1' / name)'''
new = '''copy(body / 'sealed_manifest_v1.json', A / 'closed_body_review_v1/manifest_v1.json', 'd98263831d928ee275fef2b13251cc831774760c0e0142713b79a174699455d8')
for name in ('handoff_v1.json', 'originals.tar.gz', 'raw_guard_smoother_review_v2.json'):
    copy(body / name, A / 'closed_body_review_v1' / name)'''
assert text.count(old) == 1
text = text.replace(old, new)
destination = Path('/tmp/mr3_p2a0_v24_copy_closed_evidence_v2.py')
assert not destination.exists()
destination.write_text(text)
Path('/tmp/mr3_p2a0_v24_copy_helper_failure_v1.json').write_text(json.dumps({'scope': 'Root archive copy failure, no experiment/simulator retry. Original source packets unchanged; earlier copied bytes retained and checked identical on resume.', 'source': str(p), 'error': 'FileNotFoundError: /tmp/mr3_p2a0_v24_body_trigger_independent_v1/manifest_v1.json', 'cause': 'Root assumed manifest basename before consuming handoff; actual source is sealed_manifest_v1.json.', 'fix': 'Only source manifest mapping and byte-identical existing destination resume handling changed in v2.', 'original_tool_traceback_separately_saved': False}, indent=2) + '\n')
print(str(destination))
