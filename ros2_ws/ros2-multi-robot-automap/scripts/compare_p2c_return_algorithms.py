#!/usr/bin/env python3
"""Read-only component comparison; costs and timings are not mission outcomes."""
import argparse
import hashlib
import heapq
import json
import math
import platform
import subprocess
import time
from pathlib import Path

import numpy as np
import scipy
from scipy import ndimage
from multi_robot_exploration import control


def astar_contact(safe, contact, start, heuristic):
    """A* reference on the same eight-neighbour, no-corner-cut grid.

    Euclidean distance to the closest contact is an admissible lower bound on
    every grid path. This reference is intentionally outside runtime control.
    """
    queue=[(float(heuristic[start]),0.,start)]
    costs={start:0.}; expanded=0
    while queue:
        _, cost, cell=heapq.heappop(queue)
        if cost!=costs.get(cell):continue
        expanded+=1
        if contact[cell]:return cost,expanded
        r,c=cell
        for dr,dc in ((-1,0),(1,0),(0,-1),(0,1),(-1,-1),(-1,1),(1,-1),(1,1)):
            nr,nc=r+dr,c+dc
            if not (0<=nr<safe.shape[0] and 0<=nc<safe.shape[1]) or not safe[nr,nc]:continue
            if dr and dc and (not safe[r,nc] or not safe[nr,c]):continue
            new=cost+math.hypot(dr,dc)
            if new<costs.get((nr,nc),math.inf):
                costs[nr,nc]=new
                heapq.heappush(queue,(new+float(heuristic[nr,nc]),new,(nr,nc)))
    return math.inf,expanded


def fixtures():
    for size in (64,128):
        for layout in ('open','detour','maze','disconnected'):
            grid=np.zeros((size,size),dtype=np.int16)
            if layout in ('detour','disconnected'):
                grid[:size if layout=='disconnected' else size-10,size//2]=100
            if layout=='maze':
                for n,c in enumerate(range(16,size-8,16)):
                    grid[0:size-12 if n%2==0 else size,c]=100
                    if n%2:grid[:12,c]=0
            yield f'{layout}_{size}',grid,.2,(0.,0.),(.9,.9),.8


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():parser.error('refuse to overwrite component evidence')
    rows=[];rng=np.random.default_rng(20261008)
    for name,grid,res,origin,home,radius in fixtures():
        safe=control.traversable_grid(grid,res,control.RALLY_PATH_CLEARANCE_M)
        rr,cc=np.indices(grid.shape)
        contact=safe & ((res*(cc+.5)-home[0])**2+(res*(rr+.5)-home[1])**2<=(radius-.2)**2)
        candidates=np.argwhere(safe)
        cells=[tuple(map(int,x)) for x in candidates[rng.choice(len(candidates),24,replace=False)]]
        heuristic=ndimage.distance_transform_edt(~contact)
        cache={};beg=time.perf_counter()
        reverse=control.charging_route_field(grid,res,origin,home,radius,cache)[1]
        build=time.perf_counter()-beg
        for cell in cells:
            position=control.grid_to_world(*cell,res,*origin)
            beg=time.perf_counter();forward=control.path_distance_grid(safe,cell)
            expected=float(np.min(forward[contact]));forward_time=time.perf_counter()-beg
            beg=time.perf_counter();cost,expanded=astar_contact(safe,contact,cell,heuristic)
            astar_time=time.perf_counter()-beg
            beg=time.perf_counter();cached,_=control.known_return_route(grid,res,origin,position,home,radius,cache)
            cached_time=time.perf_counter()-beg
            in_contact=math.dist(position,home)<=radius
            agreement=(math.isinf(expected) and math.isinf(cost)) or math.isclose(cost,expected,rel_tol=1e-10,abs_tol=1e-10)
            agreement=agreement and ((cached is None and math.isinf(expected)) or
                (cached is not None and math.isclose(cached,0. if in_contact else expected*res,abs_tol=1e-9)))
            if not agreement:raise AssertionError((name,cell,expected,cost,cached))
            legacy=math.dist(position,home)*2.
            rows.append(dict(fixture=name,start_cell=cell,geometry_cells=grid.size,
                known_contact_path_m=None if math.isinf(expected) else expected*res,
                legacy_euclidean_factor_m=legacy,
                legacy_below_shortest_path=math.isfinite(expected) and legacy<expected*res-1e-9,
                legacy_false_finite=math.isinf(expected),astar_expanded=expanded,
                forward_dijkstra_sec=forward_time,astar_sec=astar_time,
                cached_query_sec=cached_time,reverse_field_build_sec=build,agreement=True))
    times={key:dict(median=float(np.median([r[key] for r in rows])),
                    p95=float(np.quantile([r[key] for r in rows],.95)))
           for key in ('forward_dijkstra_sec','astar_sec','cached_query_sec')}
    result=dict(schema_version=1,scope='component_grid_cost_and_cpu_only',seed=20261008,
        comparison=['legacy_euclidean_factor_diagnostic','forward_Dijkstra_reference',
                    'A_star_Euclidean_heuristic_reference','cached_reverse_multi_source_Dijkstra'],
        source_sha256=hashlib.sha256(Path(control.__file__).read_bytes()).hexdigest(),
        helper_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        git_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        python=platform.python_version(),scipy=scipy.__version__,timings=times,
        queries=len(rows),agreement=all(r['agreement'] for r in rows),
        legacy_underestimates=sum(r['legacy_below_shortest_path'] for r in rows),
        legacy_false_finite=sum(r['legacy_false_finite'] for r in rows),rows=rows)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='rows'},indent=2))


if __name__=='__main__':main()
