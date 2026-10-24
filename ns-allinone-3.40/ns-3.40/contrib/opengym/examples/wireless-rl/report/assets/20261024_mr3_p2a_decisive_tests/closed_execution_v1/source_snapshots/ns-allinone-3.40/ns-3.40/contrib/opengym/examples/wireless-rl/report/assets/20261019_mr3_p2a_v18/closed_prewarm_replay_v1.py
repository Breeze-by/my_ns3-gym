"""Counterfactual pure-tracker replay of the complete closed V17 zero trace.

No node, simulator, science reader, learner or policy executes. The original
native FAIL stays a FAIL. A CPU replay PASS is only a prerequisite for another
separately authorized freeze; it proves no continuous plant/qualification fact.
"""
import argparse
from collections import Counter
import hashlib
import importlib
import json
from pathlib import Path
import sys
import time

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
PACKAGE = ROOT/'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration'
EPISODE = ROOT/'ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_reach_v17/mr3_p2a_reach_v17_interface/worker0/episode001_open_101'
MANIFEST = W/'report/assets/20261019_mr3_p2a_v17/closed_execution/native_closed_manifest_v1.json'
SCHEMA = 'mr3-v18-closed-prewarm-replay-v1'
OLD_FREEZE = '023e488811743b3f325538d2854205466925c5c4'
EPOCH = 'mr3_p2a_reach_v17_interface_w0_e1_72f1a48b'
TRACE_SHA = '7f26ab78d030bd65ae9a97544a2f10538ec67e918808c821a0159c155d57ed1d'
TRACE_BYTES = 390357682
LAST_RECORD = 162691
RUNTIME_SHA = 'c17d008905364616c4027aeb1b6c180e7f4d0b522e310e242659a08cf376eb9e'
ROBOTS = ('tb1','tb2','tb3')
MODULES = ('mr3_reach_runtime','mr3_episode','mr3_drive_phase','mr3_safety_intent',
           'mr3_reach_geometry','mr3_velocity_metric')


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)


def parse(raw):
    def pairs(rows):
        value = {}
        for key, child in rows:
            require(key not in value,'duplicate JSON key: '+key)
            value[key] = child
        return value
    def invalid(value):
        raise ValueError('nonfinite JSON value: '+value)
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=invalid)


def stat_value(path):
    value = path.stat()
    return [value.st_dev,value.st_ino,value.st_size,value.st_mtime_ns,value.st_ctime_ns]


def binding(path):
    raw = path.read_bytes()
    return {'path':str(path),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'stat':stat_value(path)}


class Replay:
    def __init__(self,runtime):
        self.runtime = runtime
        self.trackers = {name:runtime.ReachTracker(EPOCH,name) for name in ROBOTS}
        self.counts = Counter()
        self.errors = []
        self.error_count = 0
        self.new_faults = {}
        self.first_fault = self.first_original_fault = None
        self.first_stop = {}
        self.last_clock = self.last_wall = None
        self.last_sequence = 0
        self.phase_keys = set()
        self.support = []
        self.synchronize_counts = Counter()
        self.synchronize_ready = Counter()

    def problem(self,where,error):
        self.error_count += 1
        if len(self.errors) < 12:
            self.errors.append({**where,'reason':str(error)})

    def invoke(self,name,method,args,where):
        tracker = self.trackers[name]
        try:
            value = getattr(tracker,method)(*args)
        except (ValueError,KeyError,TypeError,OverflowError) as error:
            self.problem({**where,'robot':name,'operation':method},error)
            value = None
        if tracker.fault and name not in self.new_faults:
            event = {**where,'robot':name,'operation':method,'reason':tracker.fault}
            self.new_faults[name] = event
            if self.first_fault is None:
                self.first_fault = event
        return value

    def synchronize(self,names,clock,where):
        require(type(clock) is int and clock >= 0,'missing actual integer phase clock')
        require(self.last_clock is None or clock >= self.last_clock,'actual phase clock regressed')
        self.last_clock = clock
        for name in names:
            self.synchronize_counts[name] += 1
            if self.invoke(name,'synchronize',(clock,),where) is True:
                self.synchronize_ready[name] += 1

    def zero_intent(self,intent):
        require(intent['epoch'] == EPOCH and intent['robot'] in ROBOTS,'intent owner/epoch differs')
        require(intent['role'] in ('HOLD','STOP') and intent['anchor'] is None
                and intent['admitted_signs'] == [],'trace escaped pre-release HOLD/shutdown STOP scope')
        target = intent['target']
        require(isinstance(target,dict) and target['linear_x'] == target['angular_z'] == 0,
                'missing original target or nonzero publication outside replay scope')
        if intent['role'] == 'HOLD':
            require(intent['lineage'] == {'release_clock_ns':None},'trace contains a release')
        else:
            require(intent['lineage'].get('previous_role') == 'HOLD','STOP did not originate in actual pre-release HOLD')
        return target

    def consume(self,record,line_sha):
        sequence = record['record_sequence']
        require(type(sequence) is int and sequence == self.last_sequence+1,'original record gap/regression')
        self.last_sequence = sequence
        require(record['schema'] == 'mr3-motion-safety-v1' and record['epoch'] == EPOCH,'original trace schema/epoch differs')
        wall = record['wall_monotonic_ns']
        require(type(wall) is int and (self.last_wall is None or wall >= self.last_wall),'original wall order regressed')
        self.last_wall = wall
        kind, data = record['kind'], record['payload']
        self.counts[kind] += 1
        where = {'record_sequence':sequence,'sim_time_sec':record['sim_time_sec'],
                 'wall_monotonic_ns':wall,'kind':kind,'line_sha256':line_sha}
        if kind == 'configuration':
            require(sequence == 1 and data['robots'] == list(ROBOTS)
                    and data['safety_contract'] == 'mr3-reach-v1' and data['controlled_execution'] is True,
                    'missing original three-robot reach configuration')
        elif kind == 'own_odom':
            name = data['robot']; require(name in ROBOTS,'raw owner differs')
            self.invoke(name,'receive_raw',(data['message'],data['input_sequence']),where)
        elif kind == 'reach_driver_ingress':
            name, feed, message = data['robot'],data['kind'],data['message']
            require(name in ROBOTS and feed in ('calibration','storage','applied'),'unknown actual native feed')
            require(canonical(parse(data['raw_json'])) == canonical(message),'actual raw_json/message differ')
            require(message['epoch'] == EPOCH and message['robot'] == name,'native feed identity differs')
            require(data['publisher_identity']['valid'] is True,'original native feed lacks valid recorded graph identity')
            self.counts[name+':'+feed] += 1
            if sequence in (400,401):
                self.support.append({**where,'robot':name,'feed':feed,'message':message})
            self.invoke(name,'receive_'+feed,(message,),where)
        elif kind == 'reach_intent_publish':
            name = data['robot']; intent = data['intent']; target = self.zero_intent(intent)
            require(name == intent['robot'],'intent publication owner differs')
            require(hashlib.sha256(canonical(intent).encode()).hexdigest() == data['payload_sha256'],
                    'original intent publication payload digest differs')
            phase = (target['clock_ns'],target['decision_sequence'])
            if phase not in self.phase_keys:
                # The node synchronizes BEFORE registering any robot target.
                # Its trace logs registration later at actual intent publish.
                # Restore that known call position with the same input prefix;
                # no later callback or sample is inspected to do so.
                self.synchronize(ROBOTS,target['clock_ns'],{**where,'phase':'before_first_target_registration'})
                self.phase_keys.add(phase)
            tracker = self.trackers[name]
            if intent['role'] == 'STOP' and not tracker.stopped:
                self.first_stop[name] = {**where,'reason':'actual STOP intent proves production stop-before-publication',
                                         'lineage':intent['lineage']}
                self.invoke(name,'stop',(),where)
            old = tracker.published.get(target['decision_sequence'])
            if old is None:
                generated = self.invoke(name,'publish_target',(target,),where)
            else:
                require(canonical(old) == canonical(target),'same published target sequence changed')
                generated = self.invoke(name,'make_intent',(intent['source_clock_ns'],target),where)
            if generated is not None:
                require(canonical(generated) == canonical(intent),'replayed registered intent differs from actual published intent')
        elif kind == 'reach_decision':
            name = data['robot']; require(name in ROBOTS,'decision owner differs')
            require(data['started'] is False and data['decision']['output'] == [0.,0.],
                    'actual decision escaped zero pre-release scope')
            self.zero_intent(data['intent'])
            require(canonical(self.trackers[name].current_intent) == canonical(data['intent']),
                    'decision has no preceding exact registered publication')
            original = data.get('tracker',{}).get('fault')
            if original and self.first_original_fault is None:
                self.first_original_fault = {**where,'robot':name,'reason':original}
            # Never inherit original tracker.fault, ready, model state or anchor.
            self.synchronize((name,),data['clock_ns'],{**where,'phase':'recorded_decision_clock'})
            self.counts['original_ready_true' if data['ready'] else 'original_ready_false'] += 1
        elif kind == 'output_completed':
            status = data['status']
            require(status['schema'] == 'mr3-motion-safety-status-v2' and status['epoch'] == EPOCH,
                    'actual phase status differs')
            self.synchronize(ROBOTS,status['clock_ns'],{**where,'phase':'recorded_output_completed_clock'})
        elif kind == 'stop_request':
            for name in ROBOTS:
                self.first_stop.setdefault(name,{**where,'reason':'actual stop_request'})
                self.invoke(name,'stop',(),where)
        elif kind in ('release','reach_release_ready'):
            raise ValueError('actual release is outside closed pre-release replay scope')

    def finish(self):
        require(self.last_clock is not None,'no actual phase clock was recorded')
        self.synchronize(ROBOTS,self.last_clock,{'record_sequence':self.last_sequence,
                         'kind':'end_of_closed_trace','phase':'final_drain_at_last_recorded_phase_clock'})
        watermarks, pending = {}, {}
        for name, tracker in self.trackers.items():
            require(tracker.release_ns is None and tracker.anchor is None and not tracker.actual_normal,
                    'replay unexpectedly entered a released/normal regime')
            for feed in ('calibration','storage','applied'):
                require(self.counts[name+':'+feed] > 0,'required original stream missing: '+name+':'+feed)
            require(tracker.raw_seen and tracker.published and tracker.intents,'required original raw/publication missing')
            entries = [{'source_clock_ns':source,'kind':'raw' if kind == 0 else 'applied'}
                       for source,kind,item in tracker.events]
            causal = [entry for entry in entries if entry['source_clock_ns'] <= self.last_clock]
            missing_calibration = sorted(set(tracker.raw_seen)-set(tracker.calibrations))
            pending[name] = {'count':len(entries),'by_kind':dict(Counter(entry['kind'] for entry in entries)),
                             'causal_count':len(causal),'future_count':len(entries)-len(causal),
                             'first':min(entries,key=lambda entry:entry['source_clock_ns']) if entries else None,
                             'last':max(entries,key=lambda entry:entry['source_clock_ns']) if entries else None,
                             'unmatched_raw_calibration_sources':missing_calibration[:12],
                             'unmatched_raw_calibration_count':len(missing_calibration)}
            if causal or missing_calibration:
                self.problem({'robot':name,'phase':'closed_tail'},'required causal event/metadata remains unresolved')
            latest = tracker.storage.latest.get(name)
            watermarks[name] = {'status':tracker.status(),'last_synchronized_clock_ns':tracker.last_clock,
                'last_raw_source_ns':max(tracker.raw_seen),'last_calibration_source_ns':max(tracker.calibrations),
                'last_applied_sequence':max(tracker.applied_seen),
                'last_applied_source_ns':tracker.applied_seen[max(tracker.applied_seen)]['source_clock_ns'],
                'last_storage':latest,'last_published_sequence':max(tracker.published),
                'registered_intents':len(tracker.intents),'retained_ingress':len(tracker.ingress),
                'synchronize_calls':self.synchronize_counts[name],'synchronize_ready':self.synchronize_ready[name]}
        require(len(self.support) == 2 and self.support[0]['record_sequence'] == 400
                and self.support[1]['record_sequence'] == 401,'original same-tick support missing')
        applied, stored = self.support[0]['message'],self.support[1]['message']
        require(applied['source_clock_ns'] == stored['clock_ns'] == 711000000
                and applied['cmd_seq'] == 14 and stored['cmd_seq'] == 15,'original 711ms values differ')
        return {'new_faults':self.new_faults,'first_fault':self.first_fault,
                'first_original_fault':self.first_original_fault,'counts':dict(self.counts),
                'last_phase_clock_ns':self.last_clock,'last_watermarks':watermarks,'pending':pending,
                'same_tick_original_support':self.support,'actual_shutdown_stop_sources':self.first_stop,
                'release_calls':0,'nonzero_publications':0,'errors':self.errors,'error_count':self.error_count}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    require(not args.output.exists() and args.output.resolve().is_relative_to(Path('/tmp')),
            'output must be an exclusive new /tmp path')
    started = time.monotonic_ns(); inputs = []; sources = []; errors = []; detail = {}; trace = {}
    complete = False; replay = None
    try:
        for path in (Path(__file__).resolve(),MANIFEST,EPISODE/'metadata.json',EPISODE/'infrastructure_failure.json'):
            inputs.append(binding(path))
        manifest = parse(MANIFEST.read_bytes()); metadata = parse((EPISODE/'metadata.json').read_bytes())
        require(manifest['source_freeze'] == metadata['freeze'] == OLD_FREEZE and metadata['epoch'] == EPOCH,
                'old closed source freeze/epoch differs')
        relative = 'mr3_p2a_reach_v17_interface/worker0/episode001_open_101/motion_safety.jsonl'
        rows = [row for row in manifest['source_files'] if row['path'] == relative]
        require(len(rows) == 1 and rows[0]['sha256'] == TRACE_SHA and rows[0]['bytes'] == TRACE_BYTES,
                'original fully archived V17 trace binding differs')
        before_sources = {name:binding(PACKAGE/(name+'.py')) for name in MODULES}
        require(before_sources['mr3_reach_runtime']['sha256'] == RUNTIME_SHA,'selected new runtime is not the sealed repair')
        runtime = importlib.import_module('multi_robot_exploration.mr3_reach_runtime')
        for name in MODULES:
            module = sys.modules['multi_robot_exploration.'+name]
            require(Path(module.__file__).resolve() == PACKAGE/(name+'.py'),'imported dependency is not canonical source: '+name)
            proof = binding(PACKAGE/(name+'.py')); require(proof == before_sources[name],'source changed while importing: '+name)
            sources.append({**proof,'module':'multi_robot_exploration.'+name})
        sources.extend({**binding(path),'module':'call_order_reference_only'} for path in
                       (PACKAGE/'motion_safety.py',PACKAGE/'__init__.py'))
        replay = Replay(runtime); path = EPISODE/'motion_safety.jsonl'; before = stat_value(path)
        digest, size, lines = hashlib.sha256(), 0, 0
        with path.open('rb') as stream:
            for line in stream:
                digest.update(line); size += len(line); lines += 1
                try:
                    replay.consume(parse(line),hashlib.sha256(line).hexdigest())
                except (ValueError,KeyError,TypeError,OverflowError) as error:
                    replay.problem({'line_number':lines,'phase':'actual_original_record'},error)
                # Continue through the complete suffix even after any new fault.
        trace = {'path':str(path),'sha256':digest.hexdigest(),'bytes':size,'stat':before,
                 'records':lines,'last_record_sequence':replay.last_sequence,'epoch':EPOCH,
                 'source_freeze':OLD_FREEZE,'manifest_path':str(MANIFEST)}
        inputs.append({key:value for key,value in trace.items() if key in ('path','sha256','bytes','stat')})
        require(before == stat_value(path),'original closed trace changed during streaming replay')
        complete = size == TRACE_BYTES and digest.hexdigest() == TRACE_SHA and lines == replay.last_sequence == LAST_RECORD
        require(complete,'complete original trace digest/bytes/terminal sequence differs')
        detail = replay.finish()
        for proof in inputs+sources:
            require(stat_value(Path(proof['path'])) == proof['stat'],'bound input/source changed during replay: '+proof['path'])
    except (OSError,ValueError,KeyError,TypeError,OverflowError,ImportError) as error:
        errors.append(type(error).__name__+': '+str(error))
    if replay is not None and not detail:
        detail = {'new_faults':replay.new_faults,'first_fault':replay.first_fault,
                  'first_original_fault':replay.first_original_fault,'counts':dict(replay.counts),
                  'errors':replay.errors,'error_count':replay.error_count}
    passed = complete and not errors and replay is not None and not replay.error_count and not replay.new_faults
    result = {'schema':SCHEMA,'passed':passed,'scientific_pass_claimed':False,'native_admission':False,
              'scope':'CPU counterfactual pure tracker on complete old actual pre-release zero input/publication trace including shutdown STOP; not a new node/native execution',
              'full_suffix_scanned':complete,'old_native_failure_reclassified':False,
              'new_native_runs':0,'gpu_calls':0,'optimizer_steps':0,'continuous_physical_model_proved':False,
              'started_monotonic_ns':started,'ended_monotonic_ns':time.monotonic_ns(),
              'python':sys.executable,'input_bindings':inputs,'runtime_source_bindings':sources,
              'trace':trace,'replay':detail,'errors':errors,
              'causal_rule':'Actual file record order; synchronize before first actual target registration per phase and at recorded decision/status clocks. Final drain uses only last actually recorded phase clock. Future samples stay pending; no original fault/model state is inherited.',
              'limitations':'Sampled closed data exposes necessary implementation contradictions only. ready=false is not failure or qualification. No release, policy step, geometry admission or continuous plant proof is synthesized.'}
    with args.output.open('x') as stream:
        json.dump(result,stream,indent=2); stream.write('\n')
    print(json.dumps({'schema':SCHEMA,'passed':passed,'full_suffix_scanned':complete,
                      'first_fault':detail.get('first_fault'),'error_count':detail.get('error_count'),
                      'errors':errors,'output':str(args.output)}))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
