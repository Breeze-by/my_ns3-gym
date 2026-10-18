"""Original information mathematics with a three-key same-cycle clock lookup.

Historical reports/helpers remain unchanged. The legacy report identity fields
name those original mathematical sources; implementation_provenance identifies
this different effective implementation explicitly.
"""
import argparse
import ast
import hashlib
import importlib.util
import inspect
import json
from pathlib import Path
import textwrap

WORKSPACE = Path(__file__).resolve().parents[7]
ASSETS = Path('ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets')
HOST_RELATIVE = ASSETS / '20261017_mr3_p2a0_v10/independent/mr3_independent_information_v2.py'
RAW_RELATIVE = ASSETS / '20261017_mr3_p2a0_v9/independent/mr3_independent_information_v1.py'
HOST_SHA = 'f73600551a68e833a4c0a2063b12b75038a748466c838c8583c00605a34b948b'
RAW_SHA = 'ba3e89fa6feda9406f984310adccf17c2f0638644fd0d26f0c2e9040ec0e7653'
IMPLEMENTATION = 'cycle_three_keys_v1'
OLD = "all(item['clock_ns'] == clock for (number, _), item in self.selections.items()\n                if number == cycle)"
NEW = "all(self.selections[cycle, name]['clock_ns'] == clock for name in ROBOTS\n                if (cycle, name) in self.selections)"


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def load_implementation(root=WORKSPACE):
    host_path, raw_path = root / HOST_RELATIVE, root / RAW_RELATIVE
    host_raw, raw = host_path.read_bytes(), raw_path.read_bytes()
    require(digest(host_raw) == HOST_SHA and digest(raw) == RAW_SHA,
            'immutable original information source differs')
    spec = importlib.util.spec_from_file_location('mr3_three_key_private_information_host', host_path)
    host = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(host)
    require(Path(host.LEGACY).resolve() == raw_path.resolve(),
            'original information host resolved a different raw-helper path')
    original = host.RawReplay.selection
    source = textwrap.dedent(inspect.getsource(original))
    require(source.count(OLD) == 1, 'exact single original clock-oracle expression missing')
    changed = source.replace(OLD, NEW)
    require(ast.dump(ast.parse(changed.replace(NEW, OLD)), include_attributes=False)
            == ast.dump(ast.parse(source), include_attributes=False), 'clock-oracle AST inverse differs')
    original_indented, changed_indented = (textwrap.indent(value, '    ').encode()
                                          for value in (source, changed))
    require(raw.count(original_indented) == 1, 'original whole source lacks unique exact method bytes')
    projected = raw.replace(original_indented, changed_indented)
    require(projected.count(changed_indented) == 1
            and projected.replace(changed_indented, original_indented) == raw,
            'whole original information source inverse differs')
    namespace = dict(original.__globals__)
    exec(compile(changed, str(Path(__file__).resolve()) + ':selection', 'exec'), namespace)
    host.LedgerReplay.selection = namespace['selection']
    provenance = {'schema': 'mr3-information-implementation-v1', 'implementation': IMPLEMENTATION,
        'effective_entry': {'path': str(Path(__file__).resolve()),
                            'sha256': digest(Path(__file__).read_bytes())},
        'unchanged_original_sources': [{'path': str(host_path), 'sha256': HOST_SHA},
                                       {'path': str(raw_path), 'sha256': RAW_SHA}],
        'original_selection_method_sha256': digest(source.encode()),
        'effective_selection_method_sha256': digest(changed.encode()),
        'changed_expression_before': OLD, 'changed_expression_after': NEW,
        'method_ast_inverse_exact': True, 'whole_original_source_inverse_exact': True,
        'projected_original_source_sha256': digest(projected),
        'whole_original_inverse_sha256': digest(projected.replace(changed_indented, original_indented)),
        'legacy_report_identity_fields': 'consumer_sha256 and immutable_raw_replay identify unchanged original mathematical sources, not the full effective implementation. This provenance identifies the new entry and exact single expression change.',
        'equivalence_basis': 'Original robot membership and unique(cycle,robot) checks remain before the oracle. Only selection writes the dictionary, so same-cycle entries are exactly a subset of the three fixed robot keys. Every other predicate, record, source, threshold and output field is unchanged.'}
    return host, provenance


def add_provenance(result, provenance):
    require('implementation_provenance' not in result, 'original report unexpectedly has implementation provenance')
    return dict(result, implementation_provenance=provenance)


def audit(directory, freeze, root=WORKSPACE):
    host, provenance = load_implementation(root)
    result = host.audit(Path(directory), freeze)
    require(digest(Path(__file__).read_bytes()) == provenance['effective_entry']['sha256']
            and digest((root / HOST_RELATIVE).read_bytes()) == HOST_SHA
            and digest((root / RAW_RELATIVE).read_bytes()) == RAW_SHA,
            'effective or original information source changed during audit')
    return add_provenance(result, provenance)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--freeze', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    require(not args.output.exists(), 'exclusive new output required')
    result = audit(args.directory, args.freeze)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'passed': result['passed'], 'output': str(args.output)}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
