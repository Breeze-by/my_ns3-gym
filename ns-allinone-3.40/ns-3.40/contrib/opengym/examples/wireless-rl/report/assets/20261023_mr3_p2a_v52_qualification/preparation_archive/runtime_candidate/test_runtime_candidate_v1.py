"""Unexecuted artificial before/after equivalence tests; no original evidence."""
import ast
import copy
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import ModuleType
import unittest

BASE = Path(__file__).resolve().parent
PINS = {
    'runtime_baseline_v1.py': '810fe0a12b21826e1337b48bbe137d7b47f2700ca176f16a576bc6541356c186',
    'runtime_candidate_v1.py': '62606874886060e197feb9245e6acc3fdea87b4c980454bbbe197babda6d1831',
    'frozen_artificial_fixture_v1.py.txt': 'b4b328b51795b9b1261601a106cf67861a022e22872b4993da794e5340df62f2',
}

def pinned(name):
    raw = (BASE / name).read_bytes()
    if hashlib.sha256(raw).hexdigest() != PINS[name]:
        raise ValueError('declared artificial source differs: ' + name)
    return raw

# Isolated private package: no sys.path/PYTHONPATH changes and no production
# tracker/geometry imports. The unchanged independent support may resolve only
# if a later explicit synthetic v2 pair case invokes it.
PACKAGE = '_mr3_runtime_v52_artificial'
package = ModuleType(PACKAGE)
package.__path__ = [str(BASE)]
sys.modules[PACKAGE] = package

def load(name, alias):
    pinned(name)
    key = PACKAGE + '.' + alias
    spec = importlib.util.spec_from_file_location(key, BASE / name)
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    spec.loader.exec_module(module)
    return module

old = load('runtime_baseline_v1.py', 'old')
new = load('runtime_candidate_v1.py', 'new')
fixture = ModuleType('_mr3_runtime_v52_frozen_artificial_fixture')
fixture.__file__ = str(BASE / 'frozen_artificial_fixture_v1.py.txt')
fixture.a = old
raw_fixture = pinned('frozen_artificial_fixture_v1.py.txt')
IMPORT = b'from mr3_learning import audit_reach_runtime as a\n'
if raw_fixture.count(IMPORT) != 1:
    raise ValueError('artificial fixture import projection is not unique')
# Only swap the old fixture module's reader binding. Keep all artificial input
# construction bytes/functions unchanged and never call its unittest.main.
exec(compile(raw_fixture.replace(IMPORT, b''), fixture.__file__, 'exec'), fixture.__dict__)


def outcome(function, *args, **kwargs):
    try:
        value = function(*args, **kwargs)
        encoded = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)
        return 'return', encoded, hashlib.sha256(encoded.encode()).hexdigest()
    except Exception as error:
        return 'error', type(error).__name__, error.args


def scan(rows, component, request_id):
    return [row for row in rows if row.get('component') == component
            and row['ack']['request_id'] == request_id]


class RuntimeCandidateEquivalence(unittest.TestCase):
    def full(self, case, passed=None):
        before = copy.deepcopy(case)
        left = outcome(old._audit_records, **copy.deepcopy(case))
        right = outcome(new._audit_records, **copy.deepcopy(case))
        self.assertEqual(left, right)
        self.assertEqual(before, case)
        if passed is True:
            self.assertEqual(left[0], 'return')
            self.assertTrue(json.loads(left[1])['passed'])
        elif passed is False:
            self.assertEqual(left[0], 'error')
        return left

    def test_full_original_fixture_and_explicit_rule_complete_public_json_equal(self):
        case = fixture.fixture()
        self.full(case, True)
        case['metadata']['reach_geometry_rule'] = 'cone-support-v2'
        case['motion'][0]['payload']['reach_geometry_rule'] = 'cone-support-v2'
        self.full(case, True)

    def test_duplicate_missing_and_reversed_ack_streams_preserve_results(self):
        case = fixture.fixture()
        case['control_worker'].reverse()
        self.full(case, True)
        duplicate = copy.deepcopy(case)
        duplicate['control_worker'].append(copy.deepcopy(duplicate['control_worker'][0]))
        self.full(duplicate, False)
        missing = copy.deepcopy(case)
        missing['control_worker'].pop()
        self.full(missing, False)

    def test_lazy_component_invalid_ack_and_prior_gate_error_order(self):
        unused = fixture.fixture()
        unused['control_worker'].append({'kind':'ack_consumed', 'component':'unused', 'ack':None})
        self.full(unused, True)
        malformed = fixture.fixture()
        malformed['control_worker'].append({'kind':'ack_consumed', 'component':'state', 'ack':{}})
        self.full(malformed, False)
        # An existing earlier native/physics failure must win over future ACK
        # damage. Eager whole-stream ID extraction would violate this order.
        malformed['physics'][0]['steps'] = 19
        result = self.full(malformed, False)
        self.assertEqual(result[1], 'ValueError')

    def test_nonstring_ids_keep_original_equality_in_full_replay(self):
        for query in ([1, {'nested':True}], {'q':[1,2]}, 7, True):
            case = fixture.fixture()
            previous = case['drive_worker'][0]['control_request_id']
            case['drive_worker'][0]['control_request_id'] = copy.deepcopy(query)
            for row in case['control_worker']:
                if row['ack']['request_id'] == previous:
                    row['ack']['request_id'] = copy.deepcopy(query)
                    if row['component'] == 'peer':
                        row['ack']['state_commit']['request_id'] = copy.deepcopy(query)
            with self.subTest(query=query):
                self.full(case, True)

    def test_phase_index_duplicate_order_and_nonstring_fallback_oracle(self):
        rows = [
            {'component':'motion','ack':{'request_id':'b'},'ordinal':0},
            {'component':'state','ack':None},
            {'component':'motion','ack':{'request_id':'a'},'ordinal':2},
            {'component':'motion','ack':{'request_id':'a'},'ordinal':3},
            {'component':'other'},
        ]
        indices = {}
        for query in ('a','b','missing','a'):
            expected = scan(rows, 'motion', query)
            actual = new._phase_consumptions(rows, 'motion', query, indices)
            self.assertEqual(expected, actual)
            self.assertTrue(all(a is b for a,b in zip(expected,actual)))
        for values in ([1, True, 'a'], [[1], {'q':1}, 'a'], [None, 'a']):
            mixed = [{'component':'motion','ack':{'request_id':value}} for value in values]
            cache = {}
            for query in ('a', *values):
                self.assertEqual(outcome(scan,mixed,'motion',query),
                    outcome(new._phase_consumptions,mixed,'motion',query,cache))
        # The unused state defect is deferred until the original state query.
        self.assertEqual(outcome(scan,rows,'state','a'),
            outcome(new._phase_consumptions,rows,'state','a',indices))

    def test_replay_complete_return_and_original_stop_failures_equal(self):
        case = fixture.fixture()
        for module in (old,new):
            # Build indexes from the same artificial data, independently.
            native = module.native_index(copy.deepcopy(case['drivers']), copy.deepcopy(case['odometry_rows']), fixture.EPOCH)
            streams = module.ingress_index(copy.deepcopy(case['motion']), native, fixture.EPOCH)
            value = outcome(module.replay_robot,'tb1',streams['tb1'],native['tb1'],fixture.EPOCH,fixture.BEGIN,fixture.END)
            if module is old: expected = value
            else: self.assertEqual(expected,value)
        for offset,behavior in ((1_860_000_000,'deadline'),(2_000_000_000,'terminal')):
            stream,native,end = fixture.stop_trace(offset,behavior)
            self.assertEqual(outcome(old.replay_robot,'tb1',copy.deepcopy(stream),copy.deepcopy(native),fixture.EPOCH,fixture.BEGIN,end),
                outcome(new.replay_robot,'tb1',copy.deepcopy(stream),copy.deepcopy(native),fixture.EPOCH,fixture.BEGIN,end))

    def test_json_strictness_first_exception_and_complete_input_proofs_equal(self):
        payloads = [b'{"z":0,"a":[1,-0.0,true,null,"x"]}\n',
            b'{"x":1,"x":2}\n', b'{"x":1e999,"x":0}\n',
            b'{"x":1,"x":2,"nested":{"q":NaN}}\n',
            b'{"x":1e999}\n', b'{"x":NaN}\n', b'{"x":Infinity}\n',
            b'{"x":1}', b'{"x":1}\nnotjson\n', b'{"x":"\\ud800"}\n',
            b'{"x":1}\n\n', b'\xff\n', b'['*1100+b'0'+b']'*1100+b'\n']
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for n,payload in enumerate(payloads):
                for compressed in (False,True):
                    name = 'artificial.jsonl'
                    path = directory/(name+'.gz' if compressed else name)
                    other = directory/(name if compressed else name+'.gz')
                    if other.exists(): other.unlink()
                    path.write_bytes(gzip.compress(payload,mtime=0) if compressed else payload)
                    left,right=old.Inputs(),new.Inputs()
                    with self.subTest(n=n,compressed=compressed):
                        self.assertEqual(outcome(left.read,directory,name,True),outcome(right.read,directory,name,True))
                        self.assertEqual(left.proof,right.proof)
                        self.assertEqual(left.stats,right.stats)
                        left.close();right.close()

    def test_fresh_calls_observe_changed_input_without_object_identity_cache(self):
        case = fixture.fixture()
        self.full(case, True)
        case['control_worker'].append(copy.deepcopy(case['control_worker'][0]))
        self.full(case, False)
        case['control_worker'].pop()
        self.full(case, True)
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary);path=directory/'x.json'
            path.write_text('{"value":1}')
            first=outcome(new.Inputs().read,directory,path.name)
            path.write_text('{"value":2}')
            second=outcome(new.Inputs().read,directory,path.name)
            self.assertNotEqual(first,second)
            self.assertEqual(second,outcome(old.Inputs().read,directory,path.name))

    def test_actual_declaration_index_expression_retains_last_duplicate(self):
        tree = ast.parse(pinned('runtime_candidate_v1.py'))
        replay = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'replay_robot')
        assignment = next(node for node in replay.body if isinstance(node, ast.Assign)
            and any(isinstance(target,ast.Name) and target.id=='last_intent_for_target' for target in node.targets))
        expression = compile(ast.Expression(assignment.value), '<actual-candidate-declaration-index>', 'eval')
        declarations = [(9,{'target':{'decision_sequence':2},'label':'early-two'}),
            (4,{'target':{'decision_sequence':1},'label':'one'}),
            (2,{'target':{'decision_sequence':2},'label':'late-two'})]
        before = copy.deepcopy(declarations)
        index = eval(expression, {'declarations':declarations})
        for query in (1,2):
            expected = [value for _,value in declarations if value['target']['decision_sequence']==query][-1]
            self.assertIs(index[query],expected)
        self.assertEqual(declarations,before)

    def test_mathematics_and_canonical_source_ast_unchanged(self):
        left=ast.parse(pinned('runtime_baseline_v1.py'))
        right=ast.parse(pinned('runtime_candidate_v1.py'))
        permitted={'Inputs','replay_robot','_audit_records'}
        originals={node.name:node for node in left.body if isinstance(node,(ast.FunctionDef,ast.ClassDef))}
        changed={node.name:node for node in right.body if isinstance(node,(ast.FunctionDef,ast.ClassDef))}
        for name,node in originals.items():
            if name not in permitted:
                self.assertEqual(ast.dump(node,include_attributes=False),ast.dump(changed[name],include_attributes=False),name)
        self.assertNotIn('_phase_consumptions',originals)

if __name__=='__main__':
    unittest.main()
