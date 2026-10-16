import json,sys
from pathlib import Path
from mr3_learning.audit_ppo import load_native_gates
from mr3_learning.audit_evaluator_phase import audit_episode
root=Path('/home/zhuyulab/ns3-workspace')
run=Path(sys.argv[1]).resolve()
freeze=sys.argv[2]
phase,base,auditor,command,scalar,proof=load_native_gates(root,freeze)
summary=json.loads((run/'benchmark_summary.json').read_text())
result={'freeze':freeze,'benchmark_passed':summary['passed'],'source_proof':proof,'episodes':[],'errors':[]}
for worker in summary['workers_results']:
    for episode in worker['episodes']:
        directory=Path(episode['output_directory'])
        row={'directory':str(directory)}
        try:
            row['native']=phase.corrected_audit(base,auditor,command,[directory])
            row['scalar']=scalar.audit_episode(directory,freeze)
            row['evaluator_phase']=audit_episode(directory)
            if not row['native']['passed'] or row['scalar']['errors']:raise ValueError('native/scalar gate failed')
        except Exception as error:
            row['error']=repr(error);result['errors'].append(str(directory)+': '+repr(error))
        result['episodes'].append(row)
result['passed']=summary['passed'] and len(result['episodes'])==2 and not result['errors']
with (run/'audit_v6.json').open('x') as sink:json.dump(result,sink,indent=2);sink.write('\n')
print(json.dumps({'passed':result['passed'],'errors':result['errors'],'episodes':len(result['episodes'])}))
raise SystemExit(0 if result['passed'] else 1)
