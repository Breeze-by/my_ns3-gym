"""CPU-only temporary ACK candidate versus immutable3631 and adverse prefixes."""
import ast
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path('/home/zhuyulab/ns3-workspace')
WIRELESS=ROOT/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
sys.path.insert(0,str(WIRELESS))
from mr3_learning import audit_reach_information as audit
from mr3_learning.tests import test_reach_information_index_regression as regression

REL=Path('ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/mr3_learning/audit_reach_information.py')
PATCH=Path('/tmp/mr3_information_ack_index_optimization.patch')
META=Path('/tmp/mr3_information_ack_index_optimization_metadata_v2.json')
PROOF=Path('/tmp/mr3_information_ack_index_adversecase_proof_v1.json')
BASELINE_SHA='ab1bfe144e9ab85276718a6131fe87fd3c90a09a1bd71056acc203c0e0765e30'
def digest(raw):return hashlib.sha256(raw).hexdigest()
def binding(path):
 path=Path(path);raw=path.read_bytes();return {'path':str(path),'bytes':len(raw),'sha256':digest(raw)}

original=(ROOT/REL).read_bytes();meta=json.loads(META.read_bytes())
assert digest(original)==meta['base_source_sha256']
assert binding(PATCH)['sha256']==meta['patch_sha256']
frozen=subprocess.check_output(['git','show','3631c788ca46e03a52f34ad48c41611761c17f1e:'+str(REL)],cwd=ROOT)
assert digest(frozen)==BASELINE_SHA
with tempfile.TemporaryDirectory(prefix='mr3_ack_draft_cpu_') as directory:
 candidate_path=Path(directory)/REL;candidate_path.parent.mkdir(parents=True)
 candidate_path.write_bytes(original)
 actual=subprocess.run(['patch','-p1','--batch','--forward','-i',str(PATCH)],cwd=directory,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
 print(actual.stdout);assert actual.returncode==0
 candidate=candidate_path.read_bytes();assert digest(candidate)==meta['candidate_source_sha256']
 tree=ast.parse(candidate)
 nodes=[n for n in tree.body if (isinstance(n,ast.ClassDef) and n.name=='_AckPublicationIndex')
        or (isinstance(n,ast.FunctionDef) and n.name=='audit_motion')]
 assert len(nodes)==2
 lines=candidate.decode().splitlines(keepends=True)
 before_class=next(n for n in nodes if isinstance(n,ast.ClassDef)).lineno-1
 before_motion=next(n for n in nodes if isinstance(n,ast.FunctionDef)).lineno-1
 inverse=''.join(lines[:before_class]+lines[before_motion:])
 inverse=inverse.replace("    dependency_publications = {}\n",'',1)
 new="""            if component not in dependency_publications:
                sources = information.ack_publications if component == 'state' else peer.ack_publications
                dependency_publications[component] = _AckPublicationIndex(sources)
            require(dependency_publications[component].contains(ack, wall),
"""
 old="""            sources = information.ack_publications if component == 'state' else peer.ack_publications
            require(any(p['start'] <= wall and canonical(p['ack']) == canonical(ack) for p in sources),
"""
 assert inverse.count(new)==1;inverse=inverse.replace(new,old,1)
 assert inverse.encode()==original
 namespace=dict(vars(audit))
 exec(compile(ast.Module(body=nodes,type_ignores=[]),str(candidate_path),'exec'),namespace)
 # This is a process-local candidate binding for unit tests only. No repository
 # source or immutable helper is patched. Full original3631 function is loaded
 # by the regression class and compared for every existing/new fixture.
 with patch.object(audit,'audit_motion',namespace['audit_motion']),patch.object(audit,'_AckPublicationIndex',namespace['_AckPublicationIndex'],create=True):
  suite=unittest.defaultTestLoader.loadTestsFromModule(regression)
  result=unittest.TextTestRunner(verbosity=2).run(suite)
 proof={'schema':'mr3-information-ack-index-draft-cpu-proof-v1','passed':result.wasSuccessful(),
        'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
        'immutable3631_source_sha256':BASELINE_SHA,'owner_candidate_source_sha256':digest(original),
        'effective_combined_source_sha256':digest(candidate),'whole_ack_patch_inverse_equals_owner_candidate':True,
        'inverse_source_sha256':digest(inverse.encode()),'patch':binding(PATCH),
        'test_source':binding(Path(regression.__file__)),
        'production_source_unchanged':(ROOT/REL).read_bytes()==original,
        'scope':'Synthetic CPU only. Existing9 whole-motion baseline comparisons plus new adverse cases; no closedV19 replay, formal scientific/native role, simulator/GPU/policy/contract change or new freeze admission.',
        'valid_domain':'One original prefix() validates nondecreasing query wall; publisher ACKs are immutable recorded objects. Index retains original list offsets and object references, all duplicates; newly eligible earlier future publications are inspected before a cached match. Empty/noeligible sources do not canonicalize query; badsource precedes badquery; unused malformedtail is not inspected.'}
 with PROOF.open('x') as f:json.dump(proof,f,indent=2);f.write('\n')
 print(json.dumps(proof,indent=2))
 sys.exit(0 if result.wasSuccessful() and proof['production_source_unchanged'] else 1)
