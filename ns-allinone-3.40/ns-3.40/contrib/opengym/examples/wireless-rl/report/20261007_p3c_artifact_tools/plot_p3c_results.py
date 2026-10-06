import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path('/home/zhuyulab/ns3-workspace')
ROS = ROOT / 'ros2_ws/ros2-multi-robot-automap'
REPORT = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report'
REPLAY = ROS / 'log/p3c/v7_accepted_replay'

def load(path):
    return json.loads(Path(path).read_text())

def records(path):
    with Path(path).open() as stream:
        return [json.loads(line) for line in stream]

def values(rows, getter):
    return [np.nan if getter(row) is None else getter(row) for row in rows]

plt.rcParams.update({'font.size':10, 'axes.spines.top':False, 'axes.spines.right':False})
summary = load(REPLAY/'summary.json')
pairs = {row['case_id']:row for row in summary['pairs']}
specs = [('up10_rooms','uplink','pose_state'), ('up100_lab','uplink','pose_state'),
         ('down100_lab','downlink','fused_map_snapshot'), ('ttl_lab','uplink','pose_state'),
         ('overflow_rooms','uplink','pose_state')]
fig, axes = plt.subplots(len(specs),2,figsize=(13,15),layout='constrained')
for index,(case,direction,kind) in enumerate(specs):
    pair = pairs[case]
    left,right = axes[index]
    for mode,color,style in [('ideal','#94a3b8','--'),('fault','#1864ab','-')]:
        directory = REPLAY/pair[mode]/'curves'
        rows = [r for r in records(directory/'windows.jsonl') if r['direction']==direction and r['message_type']==kind and r['sender']=='all']
        xs = [r['elapsed_sim_time'] for r in rows]
        left.plot(xs,values(rows,lambda r:r['goodput_bytes_per_sec']),color=color,linestyle=style,label=f'{mode} accepted')
        right.plot(xs,values(rows,lambda r:r['aoi']['p95']),color=color,linestyle=style,label=f'{mode} observed AoI p95')
        if mode=='fault':
            ttl = next((r['freshness_ttl_sec'] for r in rows if r.get('freshness_ttl_sec')),None)
            if ttl:
                right.axhline(ttl,color='#c53939',linestyle=':',label=f'source TTL {ttl:g}s')
            missing = [(r['elapsed_sim_time']-(r['sim_time']-r['start_sim_time']),r['elapsed_sim_time']) for r in rows if r['aoi']['observed_sec']==0 and r['aoi']['monitored_sec']>0]
            if missing:
                intervals=[]
                for a,b in missing:
                    if intervals and abs(intervals[-1][1]-a)<1e-6: intervals[-1]=(intervals[-1][0],b)
                    else: intervals.append((a,b))
                for i,(a,b) in enumerate(intervals): right.axvspan(a,b,color='#cbd5e1',alpha=.45,hatch='//',label='no receipt: AoI unknown' if i==0 else None)
    native = load(REPLAY/pair['fault']/'curves/summary.json')['task_result']
    left.set_title(f"{case}: {native['task_phase']} ({direction}/{kind})",loc='left',fontsize=11)
    right.set_title('Source freshness from accepted versions',loc='left',fontsize=11)
    left.set_ylabel('Application payload B/s'); right.set_ylabel('Observed source age (s)')
    for ax in (left,right):
        ax.grid(alpha=.2); ax.set_xlim(left=0); ax.set_xlabel('Simulation seconds since native episode start')
        ax.legend(fontsize=8,loc='upper left')
fig.suptitle('P3C | Accepted P3B.5 fault cases, unchanged raw data\nGray: same-configuration ideal; blue: fault. Unknown ages stay unknown.',fontsize=15)
fig.savefig(REPORT/'20261007_p3c_fault_curves.png',dpi=180)
plt.close(fig)

cases=['up10_rooms','down10_rooms','up100_lab','down100_lab','ttl_lab','overflow_rooms','single_failure_rooms']
fig,axs=plt.subplots(1,3,figsize=(14,5),layout='constrained',gridspec_kw={'width_ratios':[2,1,1]})
y=np.arange(len(cases))
comparisons=[pairs[case]['comparison'] for case in cases]
ideal=[c['ideal_task']['completion_time_sec'] for c in comparisons]
fault=[c['fault_task']['completion_time_sec'] if c['fault_task']['success'] else 300 for c in comparisons]
axs[0].barh(y-.18,ideal,.32,color='#94a3b8',label='ideal native full COMPLETE')
axs[0].barh(y+.18,fault,.32,color='#1864ab',label='fault, full-mission RMST300')
for i,c in enumerate(comparisons):
    if c['fault_task']['partial_completion'] and c['fault_task']['completion_time_sec'] is not None:
        axs[0].plot(c['fault_task']['completion_time_sec'],i+.18,'^',color='#d66a13',label='native partial time' if i==6 else None)
    axs[0].text(304,i+.18,c['fault_task']['task_phase'],fontsize=8,va='center')
axs[0].set_yticks(y,cases); axs[0].set_xlim(0,440); axs[0].set_xlabel('Simulation seconds; full failure/partial censored at 300')
axs[0].legend(fontsize=8); axs[0].invert_yaxis()
axs[1].barh(y,[c['tdi'] for c in comparisons],color='#d66a13'); axs[1].set_xlim(0,1.1); axs[1].set_xlabel('Frozen TDI (ideal must qualify)')
axs[2].barh(y,[c['fault_task']['battery_minimum_energy'] for c in comparisons],color='#2a9d8f'); axs[2].set_xlabel('Fault minimum local energy')
for ax in axs[1:]: ax.set_yticks(y,[]); ax.invert_yaxis(); ax.grid(axis='x',alpha=.2)
for ax in axs: ax.set_ylim(7,-1.5)
fig.suptitle('P3C | Native task outcomes beside communication faults\nDescriptive fixed pairs, application sensitivity; no Wi-Fi or causal-performance claim',fontsize=14)
fig.savefig(REPORT/'20261007_p3c_task_comparison.png',dpi=180)
plt.close(fig)

directory=ROS/'log/p3c/p3c_v8_dynamic/p3c_v8_dynamic_dynamic/ledger_metrics'
rows=records(directory/'windows.jsonl')
events=records(directory/'events.jsonl')
fig,axs=plt.subplots(4,1,figsize=(13,10),sharex=True,layout='constrained')
definitions=[('Accepted application payload (B/s)',lambda r:r['goodput_bytes_per_sec']),
             ('Resolved attempt loss (ratio)',lambda r:r['attempt_loss_rate']),
             ('Pose / fused-map source AoI p95 (s)',lambda r:r['aoi']['p95']),
             ('Actual in-flight packets',lambda r:sum(q['in_flight'] for q in r['queues'].values()) if r['queues'] else None)]
for index,(label,getter) in enumerate(definitions):
    ax=axs[index]
    for direction,color in [('uplink','#1864ab'),('downlink','#d66a13')]:
        kind=('pose_state' if direction=='uplink' else 'fused_map_snapshot') if index==2 else 'all'
        data=[r for r in rows if r['direction']==direction and r['message_type']==kind and r['sender']=='all']
        ax.plot([r['elapsed_sim_time'] for r in data],values(data,getter),color=color,label=direction+('/'+kind if index==2 else ''))
    for event in events:
        if event['event']=='configuration_applied':
            x=event['elapsed_sim_time']; ax.axvline(x,color='#8490a5',linestyle=':',alpha=.8)
            if index==0:
                labels={1:'up loss 10%',2:'down delay 2s',3:'both loss 100%',4:'recover'}
                ax.text(x+1,ax.get_ylim()[1]*.95,labels[event['configuration']['revision']],rotation=45,fontsize=8,va='top')
    ax.set_ylabel(label); ax.grid(alpha=.2); ax.legend(loc='upper right',fontsize=9)
axs[1].set_ylim(-.03,1.03)
axs[2].axhline(2,color='#1864ab',linestyle=':',alpha=.5); axs[2].axhline(5,color='#d66a13',linestyle=':',alpha=.5)
axs[-1].set_xlabel('Simulation seconds since first central EXPLORE; verticals = actual service-confirmed boundaries')
fig.suptitle('P3C | Live fault console feedback on a real Gazebo mission\nFour acknowledged revisions; native COMPLETE 265.6s, zero contacts. Curves are saved GUI-prefix values.',fontsize=14)
fig.savefig(REPORT/'20261007_p3c_live_feedback.png',dpi=180)
plt.close(fig)
print(json.dumps({'status':'PASS','figures':[str(p) for p in REPORT.glob('20261007_p3c_*.png')]}))
