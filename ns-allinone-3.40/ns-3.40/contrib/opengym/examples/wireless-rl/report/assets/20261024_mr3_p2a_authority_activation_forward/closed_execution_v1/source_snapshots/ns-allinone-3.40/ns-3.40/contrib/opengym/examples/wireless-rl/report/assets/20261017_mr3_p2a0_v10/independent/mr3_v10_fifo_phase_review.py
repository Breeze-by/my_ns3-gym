"""Streaming read-only telemetry FIFO and exact tagged target-age facts; no controls."""
import argparse
from collections import deque
import hashlib
import json
from pathlib import Path
import time


def canon(x):
    return json.dumps(x, sort_keys=True, separators=(',', ':'), allow_nan=False)


def main():
    p = argparse.ArgumentParser(); p.add_argument('episode', type=Path); p.add_argument('--freeze', required=True); p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(); errors = []; bindings = {}; names = ('tb1', 'tb2', 'tb3')
    def check(value, message):
        if not value: errors.append(message)
    def rows(name):
        path = a.episode / name; h = hashlib.sha256(); size = 0
        with path.open('rb') as f:
            for line in f:
                h.update(line); size += len(line)
                if not line.endswith(b'\n'):
                    errors.append('incomplete final row ' + name); break
                if line.strip(): yield json.loads(line)
        bindings[str(path)] = {'bytes': size, 'sha256': h.hexdigest()}
    metadata = json.loads((a.episode / 'metadata.json').read_bytes()); epoch = metadata['epoch']
    check(metadata['freeze'] == a.freeze, 'metadata freeze differs')
    transitions = list(rows('transitions.jsonl')); release = transitions[0]['info']['release_time_ns']
    physics = list(rows('physics.jsonl')); final = physics[-1]['end_time_ns']
    pending = {n: deque() for n in names}; decisions = {n: {} for n in names}; actual = {n: {} for n in names}; counts = {n: {'decisions': 0, 'actual': 0} for n in names}; last_record = 0; release_rows=[]
    for r in rows('motion_safety.jsonl'):
        check(r['epoch'] == epoch, 'motion epoch differs'); check(r['record_sequence'] == last_record + 1, 'motion record sequence gap'); last_record = r['record_sequence']; value = r['payload']; kind = r['kind']
        if kind == 'release': release_rows.append(round(value['stamp'] * 1e9))
        if kind == 'decision':
            n = value['robot']; seq = value['decision_sequence']; check(seq == counts[n]['decisions'] + 1, 'decision sequence gap ' + n); clock = value['clock_ns']; output = value['decision']['output']; check(clock == round(r['sim_time_sec'] * 1e9), 'decision clock differs ' + n); pending[n].append((seq, clock, output)); decisions[n][seq] = (clock, output); counts[n]['decisions'] += 1
        if kind == 'actual_cmd_vel':
            n = value['robot']; check(bool(pending[n]), 'actual without queued output ' + n)
            if not pending[n]: continue
            seq, clock, output = pending[n].popleft(); t = value['twist']; observed = [t['linear']['x'], t['angular']['z']]; check(canon(observed) == canon(output) and value['observed_decision_sequence'] == seq, 'actual FIFO output differs ' + n); check(all(t[group][axis] == 0.0 for group, axes in [('linear', ('y','z')), ('angular', ('x','y'))] for axis in axes), 'unsupported actual components ' + n); identity = value['publisher_identity']; check(identity['valid'] and len(identity['endpoints']) == 1 and identity['endpoints'][0]['namespace'] == '/' and identity['endpoints'][0]['node'] == 'motion_safety', 'actual graph publisher differs ' + n); actual[n][seq] = r['wall_monotonic_ns']; counts[n]['actual'] += 1
        if kind in ('actual_cmd_vel_error','settled_turn_model_failure','target_phase_error'): errors.append('fatal motion event ' + kind)
    check(len(release_rows) == 1, 'unique motion release missing')
    if release_rows: release = release_rows[0]
    for n in names: check(not pending[n], 'unmatched final telemetry outputs ' + n)
    motion_consumed = []
    stop_observed = []
    phase_rows = list(rows('motion_phase_worker.jsonl'))
    for control in rows('control_phase_worker.jsonl'):
        if control['kind'] == 'stop_observed':
            status = control['status']
            check(status.get('phase_kind') == 'stop' and status.get('ready') is False
                  and all(canon(value) == canon({'linear_x': 0., 'angular_z': 0.})
                          for value in status['outputs'].values()), 'stop status is not strict zero')
            phase_rows.append(dict(control, kind='stop_observed', ack=status))
            stop_observed.append(status)
    for r in phase_rows:
        check(r['epoch'] == epoch, 'motion phase epoch differs')
        ack = r.get('ack')
        if not ack: continue
        for n in names:
            seq = ack['decision_sequences'][n]; expected = decisions[n].get(seq); check(expected is not None and expected[0] == ack['clock_ns'], 'motion ACK decision clock differs ' + n)
            if expected:
                check(canon([ack['outputs'][n]['linear_x'],ack['outputs'][n]['angular_z']]) == canon(expected[1]), 'motion ACK output differs ' + n)
            check(seq in actual[n] and actual[n][seq] <= r['wall_monotonic_ns'], 'motion ACK precedes actual receipt ' + n)
        if r['kind'] == 'ack_consumed': motion_consumed.append(ack)
    check(len([x for x in motion_consumed if x['clock_ns'] == release and x['ready'] is True]) == 1, 'release motion ACK missing or not ready'); check(any(x['clock_ns'] == final for x in motion_consumed + stop_observed), 'final normal/strict-zero actual motion receipt missing')
    robots={}
    for n in names:
        stat={'task_actuations':0,'task_command_receipts':0,'max_exact_receive_age_ns':0,'max_exact_target_age_ns':0,'over160ms_actuations':0,'target_rejected_task':0}; last=0
        for r in rows('drive_' + n + '.jsonl'):
            check(r['epoch']==epoch and r['robot']==n and r['record_sequence']==last+1, 'driver identity/record order differs '+n);last=r['record_sequence']; kind=r['kind']
            if kind=='target_rejected' and release <= r['sim_time_ns'] <= final:stat['target_rejected_task']+=1
            if kind not in ('actuation','command_received') or not release <= r['sim_time_ns'] <= final or r['target_clock_ns'] < release:continue
            expected=decisions[n].get(r['target_decision_sequence']);check(expected is not None and expected[0]==r['target_clock_ns'] and canon(expected[1])==canon([r['desired_v'],r['desired_w']]),'driver tagged target differs '+n);age=r['sim_time_ns']-r['target_clock_ns'];check(age>=0,'driver target source is future '+n)
            if kind=='command_received':stat['task_command_receipts']+=1;stat['max_exact_receive_age_ns']=max(stat['max_exact_receive_age_ns'],age)
            else:stat['task_actuations']+=1;stat['max_exact_target_age_ns']=max(stat['max_exact_target_age_ns'],age);stat['over160ms_actuations']+=age>160000000
        check(stat['over160ms_actuations']==0 and stat['target_rejected_task']==0,'driver source age/rejected task failure '+n);robots[n]=stat
    consumed={}; advances={}; completed={}
    for index,r in enumerate(rows('drive_phase_worker.jsonl')):
        kind=r['kind'];check(r['epoch']==epoch,'drive worker epoch differs')
        if kind in ('ack_consumed','advance_permitted'):
            expected=r['expected_motion'];clock=expected['clock_ns']
            for n in names:
                receipt=r['receipts'][n];check(receipt['epoch']==epoch and receipt['robot']==n and receipt['decision_sequence']==expected['decision_sequences'][n] and receipt['source_clock_ns']==receipt['clock_ns']==clock and canon([receipt['linear_x'],receipt['angular_z']])==canon([expected['outputs'][n]['linear_x'],expected['outputs'][n]['angular_z']]),'drive consumed receipt not exact '+n)
            if kind=='ack_consumed':consumed[clock]=(index,canon(r['receipts']))
            else:
                check(clock in consumed and consumed[clock][0]<index and consumed[clock][1]==canon(r['receipts']),'advance without preceding exact consumed receipts');advances[r['request_id']]=r
        if kind=='physics_completed':completed[r['receipt']['request_id']]=r
    positive=[r for r in physics if r['steps']==20 and r['start_time_ns']>=release]
    check({r['request_id'] for r in positive}=={key for key,value in advances.items() if value['start_time_ns'] >= release and value['steps'] == 20},'post-release positive20tick requests differ from driver advance ledger')
    for r in positive:
        c=completed.get(r['request_id']);check(c is not None and canon(c['receipt'])==canon(r),'physics completion missing/different');check(advances[r['request_id']]['start_time_ns']==r['start_time_ns'],'advance start differs')
    result={'schema':'mr3-v10-final-telemetry-fifo-phase-observation-v1','passed':not errors,'epoch':epoch,'freeze':a.freeze,'capture_wall_monotonic_ns':time.monotonic_ns(),'release_ns':release,'final_physics_ns':final,'returned_steps':len(transitions)-1,'counts':counts,'unmatched':{n:len(pending[n]) for n in names},'motion_consumed_acks':len(motion_consumed),'strict_zero_stop_observations':len(stop_observed),'last_motion_ack':motion_consumed[-1] if motion_consumed else None,'drive_consumed_clocks':len(consumed),'positive20tick_physics':len(positive),'advance_permitted':len(advances),'robots':robots,'errors':sorted(set(errors)),'bindings':bindings,'scope':'Streaming actual telemetry FIFO/local completion, exact tagged source-age and ACK-before-positive20tick facts. Frozen full drive v5 and mandatory control-chain reader remain complete acceptance gates including bootstrap and stop authorization; no body/braking/stage credit.'}
    with a.output.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps({k:result[k] for k in ('passed','epoch','counts','returned_steps','robots','errors')}))


if __name__=='__main__':main()
