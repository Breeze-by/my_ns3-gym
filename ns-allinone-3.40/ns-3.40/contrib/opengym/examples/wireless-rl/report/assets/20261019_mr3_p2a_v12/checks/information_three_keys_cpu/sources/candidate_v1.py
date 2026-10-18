"""Prospective selection-clock index experiment; never edits original readers.

The semantic report is deliberately the unchanged original report format, so
its consumer_sha256 remains the immutable HOST source, not effective new code.
The mandatory separate receipt explicitly binds this entry and transformed
method. A report without that receipt cannot describe this new consumer.
"""
import argparse
import ast
import hashlib
import importlib.util
import inspect
import json
from pathlib import Path
import textwrap
import time

HOST = Path('/home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v10/independent/mr3_independent_information_v2.py')
HOST_SHA = 'f73600551a68e833a4c0a2063b12b75038a748466c838c8583c00605a34b948b'
OLD = "all(item['clock_ns'] == clock for (number, _), item in self.selections.items()\n                if number == cycle)"
NEW = "all(self.selections[cycle, name]['clock_ns'] == clock for name in ROBOTS\n                if (cycle, name) in self.selections)"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build_candidate():
    assert sha(HOST) == HOST_SHA, 'immutable original host differs'
    spec = importlib.util.spec_from_file_location('mr3_information_three_key_immutable_host', HOST)
    host = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(host)
    original = host.RawReplay.selection
    source = textwrap.dedent(inspect.getsource(original))
    # Exactly one expression is changed. Both complete methods are source-bound.
    old = OLD
    new = NEW
    assert source.count(old) == 1, 'exact single clock-oracle source hunk missing'
    candidate = source.replace(old, new)
    assert ast.dump(ast.parse(candidate.replace(new, old)), include_attributes=False) == ast.dump(ast.parse(source), include_attributes=False)
    namespace = dict(original.__globals__)
    exec(compile(candidate, str(Path(__file__).resolve()) + ':selection', 'exec'), namespace)
    # This is a fresh, private imported class. No historical file/global module
    # or current runtime is overwritten; only this entry's dispatch is changed.
    host.LedgerReplay.selection = namespace['selection']
    proof = {'original_host': {'path': str(HOST), 'sha256': HOST_SHA},
             'immutable_raw_replay': {'path': str(host.LEGACY), 'sha256': host.LEGACY_SHA},
             'original_selection_sha256': hashlib.sha256(source.encode()).hexdigest(),
             'candidate_selection_sha256': hashlib.sha256(candidate.encode()).hexdigest(),
             'only_expression_before': old, 'only_expression_after': new,
             'method_ast_reverts_exactly': True,
             'invariant': 'Original selection validates robot in ROBOTS and unique(cycle,robot) before this predicate. Only that method writes selections; therefore all keys for a cycle are exactly a subset of the three fixed robot keys.'}
    return host, original, proof


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--freeze', required=True)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    assert not args.output.exists() and not args.receipt.exists(), 'exclusive new outputs only'
    entry_sha = sha(__file__)
    reference_raw = args.reference.read_bytes()
    reference = json.loads(reference_raw)
    host, _, proof = build_candidate()
    started = time.monotonic_ns()
    result = host.audit(args.directory, args.freeze)
    ended = time.monotonic_ns()
    encoded = (json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + '\n').encode()
    with args.output.open('xb') as stream:
        stream.write(encoded)
    equal = result == reference
    stable = sha(__file__) == entry_sha and sha(HOST) == HOST_SHA and args.reference.read_bytes() == reference_raw
    receipt = {'schema': 'mr3-information-three-key-equivalence-execution-v1',
        'freeze_of_historical_inputs': args.freeze, 'directory': str(args.directory.resolve()),
        'effective_new_entry': {'path': str(Path(__file__).resolve()), 'sha256': entry_sha},
        'effective_transformation': proof,
        'reference': {'path': str(args.reference.resolve()), 'sha256': hashlib.sha256(reference_raw).hexdigest()},
        'output': {'path': str(args.output.resolve()), 'sha256': hashlib.sha256(encoded).hexdigest()},
        'all_report_fields_deep_equal': equal, 'serialized_report_bytes_equal': encoded == reference_raw,
        'candidate_report_passed': result.get('passed'), 'source_and_reference_stable_end': stable,
        'started_wall_monotonic_ns': started, 'ended_wall_monotonic_ns': ended,
        'wall_seconds': str((ended - started) / 10**9), 'passed': equal and stable and result.get('passed') is True,
        'scope': 'New CPU-only offline candidate against saved original reports. Report consumer_sha256 names the unchanged original host source; THIS receipt identifies the different effective code. No native run, current V11 repair/PASS, new math predicate, changed threshold, old-source overwrite, old-reader rerun or training credit.'}
    with args.receipt.open('x') as stream:
        json.dump(receipt, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps(receipt), flush=True)
    return 0 if receipt['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
