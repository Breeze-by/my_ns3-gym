#!/usr/bin/env python3
"""Same-process CPU comparison on constructed endpoints, never task counterfactuals."""
import argparse
import ast
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import time
import zlib

import numpy as np

from multi_robot_exploration import control as c


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--ledger',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--reference-commit',default='eec75bb9f70eb823e2a87d4971d4107d433e50f9')
    args=p.parse_args()
    event=next(e for e in map(json.loads,args.ledger.open()) if e.get('event')=='coordinator_return_map_veto')
    path='ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/control.py'
    reference=subprocess.check_output(['git','show',args.reference_commit+':'+path],text=True)
    names={'charging_route_field','known_return_route','route_respects_known_obstacles','qualified_return_candidates'}
    functions=[n for n in ast.parse(reference).body if isinstance(n,ast.FunctionDef) and n.name in names]
    assert len(functions)==len(names)
    scope=dict(vars(c))
    exec(compile(ast.Module(body=functions,type_ignores=[]),'<frozen P2C v9>','exec'),scope)
    maps=[]
    for key in ('fused_map','local_map'):
        s=event[key]
        raw=np.frombuffer(zlib.decompress(base64.b64decode(s['grid'])),dtype='<i2').reshape(s['shape'])
        maps.append(dict(data=raw,resolution=s['resolution'],origin=s['origin']))
    fused,local=maps
    rng=np.random.default_rng(20261008)
    cells=np.argwhere(fused['data']==0)
    points=[c.grid_to_world(*cells[i],fused['resolution'],*fused['origin'])
            for i in rng.choice(len(cells),100,replace=False)]
    timings={'scalar_v9':[],'vectorized_snapshot':[]};answers={}
    for repeat in range(5):
        for label in (list(timings) if repeat%2==0 else list(timings)[::-1]):
            function=scope['qualified_return_candidates'] if label=='scalar_v9' else c.qualified_return_candidates
            cache={};rows=[];times=[]
            for point in points:
                started=time.perf_counter()
                rows.append(function(fused['data'],fused['resolution'],fused['origin'],point,
                    event['home'],event['radius'],local,cache))
                times.append(time.perf_counter()-started)
            timings[label].append(times);answers[label]=rows
    for old,new in zip(answers['scalar_v9'],answers['vectorized_snapshot']):
        assert len(old)==2 and len(new) in (2,3)
        for a,b in zip(old,new):
            assert a['source']==b['source'] and a['qualified']==b['qualified']
            assert a['path_distance_m']==b['path_distance_m']
            assert np.array_equal(a['route'],b['route'])
    result=dict(status='PASS',scope='CPU/grid components:100 constructed endpoints on one actual delivered AP map pair; no task replay, causal mission gain or worst-case latency bound',
        seed=20261008,queries=100,repetitions=5,reference_commit=args.reference_commit,
        reference_control_sha256=hashlib.sha256(reference.encode()).hexdigest(),
        current_control_sha256=hashlib.sha256(Path(c.__file__).read_bytes()).hexdigest(),
        original_event_sha256=hashlib.sha256(json.dumps(event,sort_keys=True).encode()).hexdigest(),
        constructed_endpoints=points,original_two_candidates_equal=True,
        constrained_queries=sum(len(row)==3 for row in answers['vectorized_snapshot']),
        qualified_constrained_alternatives=sum(len(row)==3 and row[2]['qualified'] for row in answers['vectorized_snapshot']),
        note='Additional constrained candidates are a new search algorithm; only the original two candidates are compared for exact equivalence.',
        timings={name:dict(raw_seconds=values,total_sec_per_repeat=[sum(v) for v in values],
            median_warm_ms=float(np.median(np.asarray(values)[:,1:])*1000),
            p95_warm_ms=float(np.percentile(np.asarray(values)[:,1:],95)*1000),
            cold_first_query_sec=[v[0] for v in values]) for name,values in timings.items()})
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:{a:b for a,b in v.items() if a!='raw_seconds'} for k,v in result['timings'].items()}))


if __name__=='__main__':main()
