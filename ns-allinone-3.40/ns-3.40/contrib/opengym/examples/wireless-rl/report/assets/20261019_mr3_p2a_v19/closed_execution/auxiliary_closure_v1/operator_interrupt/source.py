import hashlib,json,os,signal,time
from pathlib import Path

LEDGER=Path('/tmp/mr3_p2a_reach_v19_matrix/ledger.jsonl')
OUT=Path('/tmp/mr3_p2a_reach_v19_operator_interrupt')
PLAN=Path('/home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261019_mr3_p2a_v19/predeclared_plan_v1.json')

def require(ok,msg):
    if not ok: raise ValueError(msg)

def identity(pid):
    raw=Path(f'/proc/{pid}/stat').read_text()
    v=raw.rsplit(')',1)[1].split()
    return {'pid':pid,'parent':int(v[1]),'group':int(v[2]),'session':int(v[3]),'start_ticks':int(v[19]),'state':v[0]}

def argv(pid):
    b=Path(f'/proc/{pid}/cmdline').read_bytes()
    require(b.endswith(b'\0') and b[:-1], 'nonempty complete process argv required')
    return [os.fsdecode(x) for x in b[:-1].split(b'\0')]

OUT.mkdir(exist_ok=False)
raw=LEDGER.read_bytes()
(OUT/'ledger_snapshot_before.jsonl').write_bytes(raw)
rows=[json.loads(x) for x in raw.splitlines()]
require(hashlib.sha256(PLAN.read_bytes()).hexdigest()=='331d83cb8fb7fb7498f9243eaccd49138f9117baae9ae69684d30b55ae8c2d3e','plan SHA differs')
record={'schema':'mr3-reach-external-reader-interruption-v1','freeze':'3631c788ca46e03a52f34ad48c41611761c17f1e','scope':'controlled diagnostic interruption of sole remaining owned read-only consumer after irreversible stage wall failure','actual_control_argv':argv(os.getpid()),'operator':identity(os.getpid()),'started_monotonic_ns':time.monotonic_ns(),'ledger_path':str(LEDGER),'ledger_snapshot_sha256':hashlib.sha256(raw).hexdigest(),'signal_sent':False,'signal_name':'SIGINT','scientific_pass_claimed':False,'target_actual_wait_required_from_original_coordinator':True,'fee_rule':'control operation overlapping matrix outer is included once in matrix wall, not added twice','errors':[]}
rc=1
try:
    own=[r for r in rows if r.get('id')=='information']
    require(own,'information child missing')
    saved=own[-1]
    if saved['event']=='child_waited':
        record['no_signal_reason']='original coordinator already recorded actual wait'
    else:
        require(saved['event']=='child_spawned' and saved['pid']==1372897,'unexpected pending reader')
        require(saved['freeze']==record['freeze'],'reader freeze differs')
        require(saved['process_identity']['start_ticks']==417336943,'saved reader start differs')
        require(saved['command_argv'][1:3]==['-m','mr3_learning.audit_reach_information'],'not the intended read-only audit')
        pending={r['id']:r for r in rows if 'id' in r}
        require([k for k,r in pending.items() if r.get('event')=='child_spawned']==['information'],'reader is not sole pending submitted child')
        elapsed=time.monotonic_ns()-rows[0]['wall_monotonic_ns']
        require(elapsed>2400*10**9,'stage wall failure not yet established')
        pid=saved['pid']; coordinator=saved['coordinator_identity']
        before=identity(pid); parent=identity(coordinator['pid'])
        require(before['start_ticks']==saved['process_identity']['start_ticks'] and before['parent']==coordinator['pid'] and before['group']==parent['group'],'owned reader identity/parent/group differs')
        require(parent['start_ticks']==coordinator['start_ticks'] and argv(parent['pid'])==saved['coordinator_actual_argv'],'coordinator identity/argv differs')
        require(argv(pid)==saved['command_argv'],'reader actual argv differs')
        record.update(target_before=before,coordinator_before=parent,target_actual_argv=argv(pid),matrix_elapsed_at_intervention_ns=elapsed)
        fd=os.pidfd_open(pid)
        try:
            again=identity(pid)
            require(again['start_ticks']==before['start_ticks'] and again['parent']==before['parent'] and argv(pid)==saved['command_argv'],'reader identity changed before pidfd signal')
            record['signal_monotonic_ns']=time.monotonic_ns()
            signal.pidfd_send_signal(fd,signal.SIGINT,None,0)
            record['signal_sent']=True
        finally:
            os.close(fd)
    rc=0
except BaseException as error:
    record['errors'].append({'type':type(error).__name__,'message':str(error)})
record['ended_monotonic_ns']=time.monotonic_ns()
with (OUT/'intervention.json').open('x') as f: json.dump(record,f,indent=2);f.write('\n')
print(json.dumps({'signal_sent':record['signal_sent'],'errors':record['errors'],'receipt':str(OUT/'intervention.json')}))
raise SystemExit(rc)
