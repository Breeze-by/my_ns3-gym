"""Offline-only two-oracle implementation comparison on immutable closed inputs.

The unchanged legacy report is accompanied by a mandatory effective-code
receipt. Historical report identity fields continue to name their original
mathematical host, and never claim to identify this different implementation.
"""
import argparse
import ast
from bisect import bisect_left, insort
import hashlib
import importlib.util
import inspect
import json
from pathlib import Path
import textwrap
import time

ROOT = Path('/home/zhuyulab/ns3-workspace')
ASSETS = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets'
HOST = ASSETS / '20261017_mr3_p2a0_v10/independent/mr3_independent_information_v2.py'
RAW = ASSETS / '20261017_mr3_p2a0_v9/independent/mr3_independent_information_v1.py'
INDEX = Path('/tmp/mr3_p2a0_v26_information_index_proposal_v1/indexed_oracle.py')
HOST_SHA = 'f73600551a68e833a4c0a2063b12b75038a748466c838c8583c00605a34b948b'
RAW_SHA = 'ba3e89fa6feda9406f984310adccf17c2f0638644fd0d26f0c2e9040ec0e7653'
INDEX_SHA = '2651d31eeae6af7f8e93461fc4252378481a897acccaa737ec0ff27a169612ec'
OLD = "all(item['clock_ns'] == clock for (number, _), item in self.selections.items()\n                if number == cycle)"
NEW = "all(self.selections[cycle, name]['clock_ns'] == clock for name in ROBOTS\n                if (cycle, name) in self.selections)"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_candidate():
    if (sha(HOST), sha(RAW), sha(INDEX)) != (HOST_SHA, RAW_SHA, INDEX_SHA):
        raise ValueError('fixed original or reviewed index source differs')
    host = load('mr3_combined_private_original_host', HOST)
    index = load('mr3_combined_private_reviewed_index', INDEX)
    if Path(host.LEGACY).resolve() != RAW.resolve():
        raise ValueError('original host resolves a different raw helper')
    original_selection = host.RawReplay.selection
    selection = textwrap.dedent(inspect.getsource(original_selection))
    expected = textwrap.dedent(inspect.getsource(host.RawReplay.expected_latest))
    indexed = textwrap.dedent(inspect.getsource(index.expected_latest))
    if selection.count(OLD) != 1:
        raise ValueError('exact unique original selection expression missing')
    changed_selection = selection.replace(OLD, NEW)
    if ast.dump(ast.parse(changed_selection.replace(NEW, OLD)), include_attributes=False) != ast.dump(ast.parse(selection), include_attributes=False):
        raise ValueError('selection AST inverse differs')
    raw = RAW.read_bytes()
    refs = sorted(node.lineno for node in ast.walk(ast.parse(raw))
                  if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                  and node.value.id == 'self' and node.attr == 'admitted')
    if refs != [203, 306, 315]:
        raise ValueError('fixed admitted init/append/query premise differs')
    edits = [(textwrap.indent(before, '    ').encode(), textwrap.indent(after, '    ').encode())
             for before, after in ((selection, changed_selection), (expected, indexed))]
    projected = raw
    for before, after in edits:
        if projected.count(before) != 1:
            raise ValueError('original exact method byte span not unique')
        projected = projected.replace(before, after)
    inverse = projected
    for before, after in reversed(edits):
        if inverse.count(after) != 1:
            raise ValueError('replacement exact method byte span not unique')
        inverse = inverse.replace(after, before)
    if inverse != raw:
        raise ValueError('two-method whole-source inverse differs')
    selection_namespace = dict(original_selection.__globals__)
    exec(compile(changed_selection, str(Path(__file__).resolve()) + ':selection', 'exec'), selection_namespace)
    expected_namespace = dict(host.RawReplay.expected_latest.__globals__, bisect_left=bisect_left, insort=insort)
    exec(compile(indexed, str(Path(__file__).resolve()) + ':expected_latest', 'exec'), expected_namespace)
    # Two fresh private subclass methods; neither transform edits the other's
    # state. RawReplay's originals remain available as the differential oracle.
    host.LedgerReplay.selection = selection_namespace['selection']
    host.LedgerReplay.expected_latest = expected_namespace['expected_latest']
    proof = {
        'original_host': {'path': str(HOST), 'sha256': HOST_SHA},
        'immutable_raw_replay': {'path': str(RAW), 'sha256': RAW_SHA},
        'reviewed_index': {'path': str(INDEX), 'sha256': INDEX_SHA},
        'original_selection_sha256': hashlib.sha256(selection.encode()).hexdigest(),
        'candidate_selection_sha256': hashlib.sha256(changed_selection.encode()).hexdigest(),
        'original_expected_latest_sha256': hashlib.sha256(expected.encode()).hexdigest(),
        'candidate_expected_latest_sha256': hashlib.sha256(indexed.encode()).hexdigest(),
        'method_ast_reverts_exactly': True,
        'whole_original_source_inverse_exact': True,
        'projected_original_source_sha256': hashlib.sha256(projected).hexdigest(),
        'whole_original_inverse_sha256': hashlib.sha256(inverse).hexdigest(),
        'admitted_fixed_source_references': refs,
        'only_method_replacements': ['LedgerReplay.selection', 'LedgerReplay.expected_latest'],
        'stdlib_names_bound_for_indexed_method': ['bisect.bisect_left', 'bisect.insort'],
        'selection_invariant': 'Only original validated unique (cycle,robot) records write selections; same-cycle keys are a subset of three fixed robots.',
        'index_invariant': 'Fixed original admitted lists are append-only; item source_ns/sequence are never mutated. Integer nanosecond clock and (source_ns,sequence,-offset) retain original maximum and earliest exact tie, returning the original item object.',
        'state_scope': 'Selection writes only its unchanged original state. expected_latest adds a private index cache without modifying admitted/raw/pending/current or selected reference.'}
    return host, original_selection, proof


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--freeze', required=True)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.receipt.exists():
        raise ValueError('exclusive new outputs required')
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
    stable = (sha(__file__), sha(HOST), sha(RAW), sha(INDEX)) == (entry_sha, HOST_SHA, RAW_SHA, INDEX_SHA) and args.reference.read_bytes() == reference_raw
    equal, byte_equal = result == reference, encoded == reference_raw
    receipt = {'schema': 'mr3-information-combined-equivalence-execution-v2',
        'freeze_of_historical_inputs': args.freeze, 'directory': str(args.directory.resolve()),
        'effective_new_entry': {'path': str(Path(__file__).resolve()), 'sha256': entry_sha},
        'effective_transformations': proof,
        'reference': {'path': str(args.reference.resolve()), 'sha256': hashlib.sha256(reference_raw).hexdigest()},
        'output': {'path': str(args.output.resolve()), 'sha256': hashlib.sha256(encoded).hexdigest()},
        'all_report_fields_deep_equal': equal, 'serialized_report_bytes_equal': byte_equal,
        'candidate_report_passed': result.get('passed'), 'source_and_reference_stable_end': stable,
        'started_wall_monotonic_ns': started, 'ended_wall_monotonic_ns': ended,
        'wall_seconds': str((ended - started) / 10**9), 'passed': equal and byte_equal and stable and result.get('passed') is True,
        'scope': 'Offline CPU-only closed V26 comparisons. Report old consumer fields name the original mathematical host; this mandatory receipt identifies both effective transforms. No current V11 repair/PASS, new native run, changed mathematical predicate or threshold, producer-selected oracle, input mutation, or historical source/report overwrite.'}
    with args.receipt.open('x') as stream:
        json.dump(receipt, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps(receipt), flush=True)
    return 0 if receipt['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
