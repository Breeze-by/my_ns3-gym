import gzip,hashlib,json,os,time
from pathlib import Path
run=Path('/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_proxy2d_v24/full_behavior_v1')
ep=run/'stages/group3/worker1/episode001_rooms_101'
started=time.monotonic_ns();bindings=[]
def rows(path):
 raw=path.read_bytes();bindings.append({'path':str(path),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
 for line in gzip.decompress(raw).splitlines():
  if time.monotonic_ns()-started>30*10**9: raise TimeoutError('finite failure extraction exceeded30s')
  yield json.loads(line)
protocol=list(rows(ep/'protocol.jsonl.gz'));failures=[r for r in protocol if r['kind']=='dispatcher_event' and r['event']['type']=='protocol_failure'];out=[]
for r in failures:
 e=r['event'];goal=e.get('goal_id');accepts=[q for q in protocol if q['kind']=='proxy_delivery' and q['envelope']['stream']=='receipt' and q['envelope']['payload'].get('type')=='accept' and q['envelope']['payload'].get('goal_id')==goal]
 out.append({'failure':r,'accept_receipts':accepts,'accepted_to_failure_ns':None if not accepts else r['clock_ns']-accepts[0]['clock_ns']})
trace=list(rows(ep/'trace.jsonl.gz'));last=next(r for r in reversed(trace) if r['event']=='step_return');attempt=next(r for r in reversed(trace) if r['event']=='step_attempt');error=next(r for r in reversed(trace) if r['event']=='step_error')
for v in bindings: assert hashlib.sha256(Path(v['path']).read_bytes()).hexdigest()==v['sha256']
raw=Path('/proc/self/stat').read_text();f=raw[raw.rfind(')')+2:].split()
result={'schema':'mr3-proxy2d-finite-failure-extract-v1','scope':'Read-only protocol/trace extraction after the failed activity; no world, actor/reward replay, retry or qualification. All current-run input bytes remain unchanged.','input_bindings':bindings,'protocol_failures':out,'last_return':{'event_sequence':last['event_sequence'],'source_stamp':last['snapshot']['source_stamp'],'sequence':last['snapshot']['sequence'],'terminated':last['terminated'],'truncated':last['truncated'],'reason':last['reason'],'digest':last['snapshot']['digest']},'last_attempt':{k:attempt[k] for k in ('event_sequence','action','global_attempt','preceding_digest','started_wall_ns')},'last_error':error,'consumer_identity':{'pid':os.getpid(),'start_ticks':int(f[19]),'parent':int(f[1]),'group':int(f[2]),'session':int(f[3])},'elapsed_ns':time.monotonic_ns()-started,'qualification':False,'training_eligible':False,'native_credit':False}
with Path('/tmp/mr3_proxy2d_v24_failure_extract.json').open('x') as s: s.write(json.dumps(result,indent=2)+'\n')
print(json.dumps({'protocol_failures':out,'last_return':result['last_return'],'scope':result['scope']}))
