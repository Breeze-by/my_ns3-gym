#!/usr/bin/env python3
"""Descriptive read-only paired extraction; no native launch or source mutation."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import subprocess

ROOT = Path('/home/zhuyulab/ns3-workspace')
ROS_REL = Path('ros2_ws/ros2-multi-robot-automap')
BASE = ROOT / ROS_REL / 'log/mr3_plant'
FREEZE = '7bbf7ba97e12e3b5db47fb48d7ffa4ccf0740971'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def proof(p):
    raw = p.read_bytes()
    return {'path': str(p), 'bytes': len(raw), 'sha256': sha(raw)}


def rows(p):
    with p.open('rb') as f:
        for line, raw in enumerate(f, 1):
            yield {'line_1based': line, 'raw_line_sha256_with_newline': sha(raw), 'raw': json.loads(raw)}


def norm(v):
    return math.sqrt(sum(x*x for x in v))


def sub(a, b):
    return [x-y for x,y in zip(a,b)]


def cross(a, b):
    return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]


def measure(x):
    m, c, b = x['model'], x['canonical'], x['base']
    rims = [j['velocity_radps']*.033 for j in x['joints_right_left']]
    targets = [j['motor_velocity_target_radps']*.033 for j in x['joints_right_left']]
    offset = sub(b['world_cog_pose']['position_xyz'], b['world_pose']['position_xyz'])
    return {
        'model_planar_mps': math.hypot(*m['world_linear_velocity_xyz'][:2]),
        'model_angular_z_radps': m['world_angular_velocity_xyz'][2],
        'base_origin_planar_mps': math.hypot(*b['world_origin_linear_velocity_xyz'][:2]),
        'base_cog_planar_mps': math.hypot(*b['world_cog_linear_velocity_xyz'][:2]),
        'base_cog_identity_residual_mps': norm(sub(sub(b['world_cog_linear_velocity_xyz'], b['world_origin_linear_velocity_xyz']), cross(b['world_angular_velocity_xyz'], offset))),
        'model_canonical_origin_velocity_difference_mps': norm(sub(m['world_linear_velocity_xyz'], c['world_origin_linear_velocity_xyz'])),
        'model_canonical_origin_position_difference_m': norm(sub(m['world_pose']['position_xyz'], c['world_pose']['position_xyz'])),
        'canonical_base_origin_position_difference_m': norm(sub(c['world_pose']['position_xyz'], b['world_pose']['position_xyz'])),
        'measured_mean_rim_mps': sum(rims)/2,
        'motor_target_mean_rim_mps': sum(targets)/2,
    }


def ref(row, origin):
    x = row['raw']
    return {k:v for k,v in row.items() if k != 'raw'} | {
        'record_sequence': x['record_sequence'], 'sim_time_ns': x['sim_time_ns'],
        'relative_ns': x['sim_time_ns']-origin,
        **({'phase': x['phase']} if 'phase' in x else {}),
    }


def load_arm(arm):
    run = BASE / ('mr3_p2a_v8_'+arm)
    ep = run/'worker0/episode001_open_101'
    meta = json.loads((ep/'metadata.json').read_bytes())
    closed = json.loads((ep/'summary.json').read_bytes())['closed']
    assert meta['freeze'] == FREEZE and meta['plant_stimulus_arm'] == arm
    origin = round(closed['start_sim_time_sec']*1e9)
    end = round(closed['stop_sim_time_sec']*1e9)
    assert end-origin == 4000000000
    observer = list(rows(ep/'physics_tb3.jsonl'))
    samples = [r for r in observer if r['raw']['kind']=='sample' and origin<r['raw']['sim_time_ns']<=end]
    assert len(samples)==8000
    data = {(r['raw']['sim_time_ns']-origin,r['raw']['phase']): (r,measure(r['raw'])) for r in samples}
    assert len(data)==8000
    phases = ['before_physics_after_collision','world_update_end_after_physics_and_pose_propagation']
    assert set(data)=={(t,phase) for t in range(1000000,4000000001,1000000) for phase in phases}
    maxstats={}
    for key in next(iter(data.values()))[1]:
        r,v=max(data.values(),key=lambda z:abs(z[1][key]))
        maxstats[key]={'maximum_absolute':abs(v[key]),'signed_value_at_max_abs':v[key], 'reference':ref(r,origin)}
    drive=list(rows(ep/'drive_tb3.jsonl'))
    act=[r for r in drive if r['raw']['kind']=='actuation' and origin<r['raw']['sim_time_ns']<=end]
    pulsearea=[r for r in act if 2100000000<=r['raw']['sim_time_ns']-origin<=2370000000]
    actstats={}
    for key in ['current_rim_mps','applied_rim_mps']:
        r=max(act,key=lambda r:abs(sum(r['raw'][key])/2))
        actstats[key]={'maximum_absolute_mean_mps':abs(sum(r['raw'][key])/2),'signed_mean_mps':sum(r['raw'][key])/2,'reference':ref(r,origin)}
    after=[data[(t,phases[1])][0]['raw'] for t in range(1000000,4000000001,1000000)]
    chords=math.fsum(math.hypot(*sub(after[i]['model']['world_pose']['position_xyz'],after[i-1]['model']['world_pose']['position_xyz'])[:2]) for i in range(1,len(after)))
    speed_sum=math.fsum(math.hypot(*x['model']['world_linear_velocity_xyz'][:2])*.001 for x in after)
    custody=json.loads((ep/'plant_native_custody.json').read_bytes())
    assert custody['passed'] is True
    mapped={}
    for p in custody['processes']:
        for item in p.get('maps',[]):
            if item.get('role') in ('smoother_core','observer','drive'):
                mapped.setdefault(item['role'],set()).add(item['sha256'])
    out={
        'episode_directory':str(ep),'epoch':meta['epoch'],'freeze':meta['freeze'],
        'window_start_exclusive_ns':origin,'window_end_inclusive_ns':end,
        'complete_1ms_before_after_pairs':4000,'model_planar_samples_gt_01':sum(v['model_planar_mps']>.01 for _,v in data.values()),
        'maximum_absolute_statistics':maxstats,'driver_mean_statistics':actstats,
        'sampled_after_phase_chord_sum_m':chords,'sampled_after_phase_rectangle_speed_sum_m':speed_sum,
        'sampled_path_scope':'Descriptive sampled sums only, not continuous-path proofs.',
        'observer_configuration':observer[0]['raw'],
        'driver_configuration':drive[0]['raw'],
        'custody_expected_smoother_core':custody['expected_current_smoother_core'],
        'custody_selected_mapped_sha256':{k:sorted(v)for k,v in mapped.items()},
        'central_pulse_comparison_actuation_raw_rows':[{**r,'relative_ns':r['raw']['sim_time_ns']-origin} for r in pulsearea],
        'input_proof':[proof(ep/name)for name in ['metadata.json','summary.json','physics_tb3.jsonl','drive_tb3.jsonl','plant_stimulus_worker.jsonl','plant_native_custody.json','physics_diagnostic_binding.json','drive_model_tb3.sdf']],
    }
    return out,data


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('/tmp/mr3_p2a_v8_paired_physical_review_v1.json'))
    parser.add_argument('--response-csv',type=Path,default=Path('/tmp/mr3_p2a_v8_paired_physical_response_1ms_v1.csv'))
    args=parser.parse_args()
    for p in [args.output,args.response_csv]:
        if p.exists():raise FileExistsError(p)
    arms={};data={}
    for arm in ['continuous','pulse']:arms[arm],data[arm]=load_arm(arm)
    columns=['arm','relative_ns','phase','sim_time_ns','record_sequence','line_1based','model_planar_mps','model_angular_z_radps','measured_mean_rim_mps','motor_target_mean_rim_mps','base_origin_planar_mps','base_cog_planar_mps','raw_line_sha256_with_newline']
    with args.response_csv.open('x',newline='')as f:
        writer=csv.DictWriter(f,fieldnames=columns);writer.writeheader()
        for t in range(2190000000,2320000001,1000000):
            for phase in ['before_physics_after_collision','world_update_end_after_physics_and_pose_propagation']:
                for arm in ['continuous','pulse']:
                    row,value=data[arm][(t,phase)]
                    writer.writerow({k:({'arm':arm,'relative_ns':t,**row['raw'],**row,**value})[k]for k in columns})
    source_proof=[]
    for relative in ['src/multi_robot/src/mr3_gazebo_diff_drive.cpp','src/multi_robot/include/multi_robot/paired_wheel_slew.hpp','src/multi_robot/src/mr3_stop_response_observer.cpp','src/nav2_velocity_smoother/src/velocity_smoother.cpp']:
        rel=str(ROS_REL/relative);spec=FREEZE+':'+rel
        frozen=subprocess.check_output(['git','show',spec],cwd=ROOT)
        source_proof.append({'git_spec':spec,'git_object':subprocess.check_output(['git','rev-parse',spec],cwd=ROOT,text=True).strip(),'sha256':sha(frozen),'bytes':len(frozen)})
    for arm in arms.values():
        assert arm['driver_configuration']['compiled_source_sha256']==source_proof[0]['sha256']
        assert arm['driver_configuration']['compiled_helper_sha256']==source_proof[1]['sha256']
        assert arm['observer_configuration']['compiled_source_sha256']==source_proof[2]['sha256']
    key_points=[]
    for t in [2200000000,2218000000,2240000000,2252000000,2286000000]:
        point={'relative_ns':t}
        for arm in ['continuous','pulse']:
            r,v=data[arm][(t,'world_update_end_after_physics_and_pose_propagation')]
            point[arm]={'reference':ref(r,arms[arm]['window_start_exclusive_ns']),**{k:v[k]for k in ['model_planar_mps','model_angular_z_radps','measured_mean_rim_mps','motor_target_mean_rim_mps']}}
        key_points.append(point)
    report={
        'schema':'mr3-p2a-v8-paired-physical-readonly-review-v1',
        'scope':'Read-only descriptive paired extraction after both arms closed. Formal stimulus validity and strict native closure results are owned by their independent consumers; they are not rerun here. No source/library/Git mutation or native execution.',
        'freeze':FREEZE,'arms':arms,'exact_freeze_source_proof':source_proof,
        'comparison_windows':{'whole_arm_relative_ns':[0,4000000000],'turn_request_envelope_relative_ns':[1200000000,2740000000],'continuous_requested_turn_sec':1.54,'pulse_total_requested_turn_sec':1.50,'pulse_zero_request_relative_ns':[2200000000,2240000000],'pulse_requested_zero_duration_ms':40,'one_ms_response_relative_ns_inclusive':[2190000000,2320000000],'pulse_actual_zero_wheel_update_relative_ns':2218000000,'pulse_actual_resume_wheel_update_relative_ns':2252000000,'pulse_actual_braking_target_hold_ms':34,'continuous_neighbour_wheel_updates_relative_ns':[2226000000,2260000000],'wheel_phase_difference_ms':8},
        'selected_after_physics_response_points':key_points,
        'full_actual_1ms_response_csv':{**proof(args.response_csv),'rows':524,'scope':'Actual native before/after model,base,joint and motor readback at every relative1ms from2.190 through2.320seconds. Values are not reconstructed from planned stimulus. Original raw row SHA and line supplied.'},
        'conclusions_and_limits':[
            'Both4second windows contain4000complete1ms before/after pairs. No observed model-planar sample exceeds.01; the original V7settled-turn failure is not reproduced in these two sparse from-rest arms.',
            'Pulse zero and resume both reach actual wheel actuation. This valid40ms source pulse causes one34ms-held braking wheel target; it is not the original V7single20ms source event.',
            'This is a descriptive within-freeze input contrast, not an estimate of a general pulse causal effect: reset clocks, driver phase, startup/settling state and resultant trajectories are not exactly paired.',
            'The controlled request envelope contains only1.54seconds continuous turn, or1.50seconds total pulse-arm turn. Neither matches the original V7near-peer navigation history or approximately3.075seconds active settled-turn duration before its first violation.',
            'Model/canonical origin velocity and position agree; base CoG-origin velocity identities hold to floating precision. CoG speed is not being substituted for the model/base-footprint origin speed in these observed arms.',
            'Nonzero rim feedback asymmetry and issued mean components exist in both arms at substantially smaller scale than V7. Body speeds, issued targets and feedback remain distinct measurements; no additive body-drift contribution or solver cause is established.',
            'Similar small sampled path/speed values across arms do not prove the original model valid, identify a root cause, demonstrate a repair, supply95percent/300second task credit or erase V7FAIL/optimizer history. No production-driver change is justified as fixed from these data alone.',
        ],
        'original_v7_reference':{'freeze':'8d7f19fc8225eae0ccdc6609b828ee8e832f7c93','first_failure_planar_mps':.02020358683181293,'zero_update_issued_mean_rim_mps':.006761302059522432,'zero_source_requested_ms':20,'active_duration_to_first_violation_sec':3.075,'scope':'Historical mismatch anchor only; not a same-freeze matched arm.'},
        'extractor_proof':proof(Path(__file__).resolve()),
    }
    with args.output.open('x')as f:json.dump(report,f,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps({'report':proof(args.output),'response_csv':proof(args.response_csv),'arm_summary':{arm:{'max_model_planar_mps':v['maximum_absolute_statistics']['model_planar_mps']['maximum_absolute'],'sampled_chord_sum_m':v['sampled_after_phase_chord_sum_m'],'max_base_cog_residual_mps':v['maximum_absolute_statistics']['base_cog_identity_residual_mps']['maximum_absolute']}for arm,v in arms.items()}}))


if __name__=='__main__':main()
