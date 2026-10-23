"""Call the real frozen admission path without submitting either native case."""
import argparse
import importlib.util
import json
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--freeze', required=True)
p.add_argument('--output', required=True, type=Path)
a = p.parse_args()
program = Path(__file__).resolve().parents[1] / 'run_passive_pair_v1.py'
loader = importlib.util.spec_from_file_location('v55_actual_frozen_inputs', program)
d = importlib.util.module_from_spec(loader)
loader.loader.exec_module(d)
result = {'schema': 'mr3-v55-frozen-input-cpu-v1', 'passed': False,
          'execution_freeze': a.freeze, 'worlds_submitted': 0, 'errors': []}
try:
    scope = d.read(d.SCOPE)
    spec, before = d.verify_inputs(scope, a.freeze)
    after = [d.proof(row['path']) for row in before]
    d.require(before == after, 'source/ELF/config changed during CPU admission')
    result.update(passed=True, source_before=before, source_after=after,
                  source_unchanged=True, source_count=len(before),
                  declared_arms=[row['arm'] for row in spec['worlds']])
except Exception as error:
    result['errors'].append(repr(error))
d.write(a.output, result)
print(json.dumps({key: result[key] for key in
                 ('passed', 'worlds_submitted', 'errors')}))
raise SystemExit(0 if result['passed'] else 1)
