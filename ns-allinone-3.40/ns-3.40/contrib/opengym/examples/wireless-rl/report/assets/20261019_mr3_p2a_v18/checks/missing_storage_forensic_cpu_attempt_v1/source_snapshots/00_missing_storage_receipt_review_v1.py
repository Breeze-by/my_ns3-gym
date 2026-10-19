"""Read-only three-stream receipt forensics; never inject a receipt or run a tracker."""
import argparse
import ast
from collections import Counter
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A = Path(__file__).resolve().parent
ROS = ROOT/'ros2_ws/ros2-multi-robot-automap'
EP = ROS/'log/mr3_p2a_reach_v17/mr3_p2a_reach_v17_interface/worker0/episode001_open_101'
MANIFEST = W/'report/assets/20261019_mr3_p2a_v17/closed_execution/native_closed_manifest_v1.json'
OLD = '023e488811743b3f325538d2854205466925c5c4'
EPOCH = 'mr3_p2a_reach_v17_interface_w0_e1_72f1a48b'
SCHEMA = 'mr3-v18-missing-storage-receipt-review-v1'
ROBOTS = ('tb1','tb2','tb3')
FIRST = {'tb1':(906,927,18697000000),'tb2':(1596,1717,34727000000),'tb3':(753,927,18694000000)}
ACK_FIELDS = {'schema','epoch','robot','clock_ns','decision_sequence','source_clock_ns','cmd_seq','linear_x','angular_z'}


def require(condition,reason):
    if not condition:
        raise ValueError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)


def parse(raw):
    def pairs(rows):
        value = {}
        for key,child in rows:
            require(key not in value,'duplicate JSON key: '+key)
            value[key] = child
        return value
    def invalid(value):
        raise ValueError('nonfinite JSON: '+value)
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=invalid)


def stat(path):
    value = path.stat()
    return [value.st_dev,value.st_ino,value.st_size,value.st_mtime_ns,value.st_ctime_ns]


class Inputs:
    def __init__(self):
        self.proofs = {}

    def raw(self,path):
        before = stat(path); raw = path.read_bytes()
        require(before == stat(path),'input changed during read: '+str(path))
        self.proofs[str(path)] = {'path':str(path),'sha256':sha(raw),'bytes':len(raw),'stat':before}
        return raw

    def stream(self,path,spec,callback):
        before = stat(path); digest = hashlib.sha256(); size = lines = 0
        with path.open('rb') as stream:
            for lines,line in enumerate(stream,1):
                digest.update(line); size += len(line)
                callback(lines,line)
        require(before == stat(path),'closed original changed during streaming: '+str(path))
        require(digest.hexdigest() == spec['sha256'] and size == spec['bytes'],
                'original bytes differ from closed archive manifest: '+str(path))
        self.proofs[str(path)] = {'path':str(path),'sha256':digest.hexdigest(),'bytes':size,'stat':before,'lines':lines}
        return lines

    def finish(self):
        for proof in self.proofs.values():
            require(stat(Path(proof['path'])) == proof['stat'],'input changed during forensics: '+proof['path'])


def ack(value,robot):
    require(set(value) == ACK_FIELDS and value['schema'] == 'mr3-drive-target-consumed-v1'
            and value['epoch'] == EPOCH and value['robot'] == robot,'whole nine-field ACK identity differs')
    require(all(type(value[k]) is int and value[k] > 0 for k in
                ('clock_ns','decision_sequence','source_clock_ns','cmd_seq')),'ACK integer identity malformed')


def add(table,value,source):
    robot = value['robot']; ack(value,robot); command = value['cmd_seq']
    old = table[robot].get(command)
    if old is None:
        table[robot][command] = {'message':value,'sources':[source]}
    else:
        require(canonical(old['message']) == canonical(value),'same cmd has conflicting whole ACK')
        old['sources'].append(source)


def qos_python(raw,worker=False):
    text = raw.decode(); tree = ast.parse(text); assignments = {}
    functions = {node.name:node for node in tree.body if isinstance(node,ast.FunctionDef)}
    for node in ast.walk(tree):
        if isinstance(node,ast.Assign):
            for target in node.targets:
                if isinstance(target,ast.Name): assignments[target.id] = node.value
    candidates = []
    for node in ast.walk(tree):
        if not (isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute)
                and node.func.attr == 'create_subscription' and len(node.args) >= 4):continue
        topic = ast.get_source_segment(text,node.args[1]) or ''
        if ('/mr3_drive/status' in topic if worker else '/mr3_drive/{suffix}' in topic):candidates.append(node)
    require(len(candidates) == 1,'cannot uniquely locate actual storage subscription')
    call = candidates[0]; expr = call.args[3]; definitions = []
    for _ in range(8):
        if isinstance(expr,ast.IfExp):
            require(isinstance(expr.test,ast.Compare) and any(isinstance(x,ast.Constant) and x.value == 'storage'
                    for x in expr.test.comparators),'unrecognized storage QoS branch')
            expr = expr.body
        elif isinstance(expr,ast.Name):
            require(expr.id in assignments,'unresolved QoS variable: '+expr.id)
            expr = assignments[expr.id]; definitions.append(expr)
        elif isinstance(expr,ast.Call) and isinstance(expr.func,ast.Name) and expr.func.id in functions:
            helper = functions[expr.func.id]
            require(expr.func.id == 'storage_receipt_qos' and len(expr.args) == 1
                    and ast.unparse(expr.args[0]) == 'self.reach_enabled', 'unknown QoS helper/profile')
            returns = [node for node in ast.walk(helper) if isinstance(node,ast.Return)]
            require(len(returns) == 1,'QoS helper does not have one static return')
            definitions.append(helper);expr = returns[0].value
        else:break
    if isinstance(expr,ast.Constant) and type(expr.value) is int:
        depth, options = expr.value, {'integer_shorthand':True}
    else:
        require(isinstance(expr,ast.Call),'QoS expression is not a static constructor')
        options = {item.arg:ast.get_source_segment(text,item.value) for item in expr.keywords}
        depth_node = next((item.value for item in expr.keywords if item.arg == 'depth'),None)
        if isinstance(depth_node,ast.IfExp):
            require(isinstance(depth_node.test,ast.Name) and depth_node.test.id == 'reach_enabled',
                    'unknown conditional QoS depth')
            depth_node = depth_node.body  # This forensic profile is explicitly mr3-reach-v1.
        require(isinstance(depth_node,ast.Constant) and type(depth_node.value) is int,'QoS depth is not a static integer')
        depth = depth_node.value
    nodes = [call,*definitions]
    return {'depth':depth,'evaluated_profile':'reach_enabled=True','options_source':options,'subscription_expression':ast.get_source_segment(text,call.args[3]),
            'source_spans':[{'line':node.lineno,'end_line':node.end_lineno,
                             'text':'\n'.join(text.splitlines()[node.lineno-1:node.end_lineno])} for node in nodes]}


def qos_native(raw):
    text = raw.decode()
    matches = list(re.finditer(r'const auto status_qos = rclcpp::QoS\((\d+)\)\.reliable\(\)\.transient_local\(\);',text))
    require(len(matches) == 1 and '"mr3_drive/status", status_qos' in text,'native ACK QoS/source is not explicit')
    match = matches[0]; line = text[:match.start()].count('\n')+1
    return {'depth':int(match.group(1)),'reliability':'reliable','durability':'transient_local',
            'source_spans':[{'line':line,'end_line':line+2,'text':'\n'.join(text.splitlines()[line-1:line+2])}]}


def source_qos(inputs):
    paths = {'native_publisher':ROS/'src/multi_robot/src/mr3_gazebo_diff_drive.cpp',
             'motion_subscriber':ROS/'src/multi_robot_exploration/multi_robot_exploration/motion_safety.py',
             'worker_subscriber':ROS/'scripts/mr3_env_worker.py'}
    result = {}
    for name,path in paths.items():
        old = subprocess.check_output(['git','show',OLD+':'+str(path.relative_to(ROOT))],cwd=ROOT)
        current = inputs.raw(path)
        extract = qos_native if name == 'native_publisher' else lambda raw:qos_python(raw,name == 'worker_subscriber')
        historical, prospective = extract(old),extract(current)
        require(historical['depth'] == 1,'historical ACK QoS is not the actual depth-one source')
        result[name] = {'path':str(path),'historical_freeze':OLD,'historical_source_sha256':sha(old),
                        'current_source_sha256':sha(current),'historical':historical,'current':prospective}
    return result


def failed_replay(inputs,path):
    raw = inputs.raw(path); original = Path('/tmp/mr3_p2a_reach_v18_closed_prewarm_replay.json')
    require(raw == inputs.raw(original),'canonical failed replay result differs from actual /tmp original')
    value = parse(raw)
    wait_path = A/'checks/closed_prewarm_cpu_attempt_v1/actual_wait.json'; wait = parse(inputs.raw(wait_path))
    require(type(wait['actual_returncode']) is int and wait['actual_returncode'] == 1
            and type(wait['started_monotonic_ns']) is int and type(wait['ended_monotonic_ns']) is int
            and 0 < wait['started_monotonic_ns'] < wait['ended_monotonic_ns']
            and wait['actual_waited'] is True and wait['source_unchanged'] is True
            and wait['source_before'] == wait['source_after'] and wait['passed'] is False,'original replay actual FAIL facts differ')
    duration = Decimal(wait['ended_monotonic_ns']-wait['started_monotonic_ns'])/10**9
    require(duration == Decimal(str(wait['actual_child_wait_seconds'])) == Decimal('269.896902167'),
            'failed replay actual ns duration differs')
    require(value['schema'] == 'mr3-v18-closed-prewarm-replay-v1' and value['passed'] is False
            and value['full_suffix_scanned'] is True and value['scientific_pass_claimed'] is False
            and value['replay']['new_faults'] == {} and value['replay']['first_fault'] is None
            and value['replay']['error_count'] == 3 and len(value['replay']['errors']) == 3
            and all(row['phase'] == 'closed_tail' for row in value['replay']['errors'])
            and all(value['replay']['pending'][name]['causal_count'] > 0 for name in ROBOTS),
            'original complete replay pending FAIL has been changed')
    require(value['trace']['sha256'] == '7f26ab78d030bd65ae9a97544a2f10538ec67e918808c821a0159c155d57ed1d'
            and value['trace']['bytes'] == 390357682
            and value['trace']['records'] == value['trace']['last_record_sequence'] == 162691
            and value['trace']['epoch'] == EPOCH and value['trace']['source_freeze'] == OLD,
            'failed replay is not bound to the same complete original V17 trace')
    return {'canonical_result':inputs.proofs[str(path)],'original_result':inputs.proofs[str(original)],
            'actual_wait':inputs.proofs[str(wait_path)],'passed':False,'actual_returncode':1,
            'actual_child_wait_seconds':str(duration),'full_suffix_scanned':True,
            'new_faults':{},'first_fault':None,'closed_tail_error_count':3}


def review(inputs,args):
    manifest = parse(inputs.raw(MANIFEST)); require(manifest['source_freeze'] == OLD,'closed manifest source freeze differs')
    root = Path(manifest['source_root']); require(root == ROS/'log/mr3_p2a_reach_v17','closed original root differs')
    specs = {row['path']:row for row in manifest['source_files']}
    require(len(specs) == len(manifest['source_files']),'duplicate archive source path')
    native = {name:{} for name in ROBOTS}; motion = {name:{} for name in ROBOTS}; worker = {name:{} for name in ROBOTS}
    counts = {name:Counter() for name in ('native','motion','worker')}; support = {name:[] for name in ROBOTS}; applied = {name:[] for name in ROBOTS}
    def source(path,line,raw,record):
        return {'path':str(path),'line_number':line,'record_sequence':record.get('record_sequence'),
                'line_sha256':sha(raw),'record':record}
    for name in ROBOTS:
        path = EP/('drive_'+name+'.jsonl'); last_command = 0
        def consume_native(line,raw,name=name,path=path):
            nonlocal last_command
            row = parse(raw); require(row['record_sequence'] == line and row['epoch'] == EPOCH and row['robot'] == name,
                                      'native original line/identity differs')
            counts['native'][name+':'+row['kind']] += 1
            if row['kind'] == 'status_publish':
                require(row['cmd_seq'] == last_command+1,'native status cmd order/gap differs');last_command = row['cmd_seq']
                add(native,row['status'],source(path,line,raw,row))
        inputs.stream(path,specs[str(path.relative_to(root))],consume_native)
    trace = EP/'motion_safety.jsonl'
    spec = specs[str(trace.relative_to(root))]
    require(spec['sha256'] == '7f26ab78d030bd65ae9a97544a2f10538ec67e918808c821a0159c155d57ed1d'
            and spec['bytes'] == 390357682,'original full motion trace identity differs')
    def consume_motion(line,raw):
        if b'"kind":"reach_driver_ingress"' not in raw:return
        if b'"kind":"storage"' not in raw and b'"kind":"applied"' not in raw:return
        row = parse(raw); data = row['payload']; name = data['robot']; message = data['message']
        require(row['record_sequence'] == line and row['epoch'] == EPOCH and name in ROBOTS,'Motion original ordered identity differs')
        require(canonical(parse(data['raw_json'])) == canonical(message),'Motion raw_json/message differs')
        counts['motion'][name+':'+data['kind']] += 1
        if data['kind'] == 'storage':add(motion,message,source(trace,line,raw,row))
        else:
            target = message['target']
            require(message['epoch'] == EPOCH and message['robot'] == name and target['robot'] == name
                    and target['epoch'] == EPOCH,'applied original owner differs')
            applied[name].append({'cmd_seq':message['cmd_seq'],'decision_sequence':target['decision_sequence'],
                'source_clock_ns':message['source_clock_ns'],'actuation_sequence':message['actuation_sequence'],
                'source':source(trace,line,raw,row)})
    require(inputs.stream(trace,spec,consume_motion) == 162691,'complete motion original suffix is missing')
    path = EP/'drive_phase_worker.jsonl'
    def consume_worker(line,raw):
        row = parse(raw);counts['worker'][row['kind']] += 1
        if row['kind'] == 'ack_received':
            require(row['epoch'] == EPOCH and row['topic_robot'] == row['ack']['robot'],'worker original owner differs')
            add(worker,row['ack'],source(path,line,raw,row))
    inputs.stream(path,specs[str(path.relative_to(root))],consume_worker)
    result = {}
    for name in ROBOTS:
        for label,table in (('motion',motion),('worker',worker)):
            for command,entry in table[name].items():
                require(command in native[name] and canonical(entry['message']) == canonical(native[name][command]['message']),
                        label+' whole nine-field ACK differs from actual native publication')
        missing_motion = sorted(set(native[name])-set(motion[name]));missing_worker = sorted(set(native[name])-set(worker[name]))
        absent_applied = [row for row in applied[name] if row['cmd_seq'] not in motion[name]]
        require(absent_applied,'no actual applied command demonstrates missing Motion storage')
        first = absent_applied[0]; command,decision,clock = FIRST[name]
        require((first['cmd_seq'],first['decision_sequence'],first['source_clock_ns']) == (command,decision,clock),
                'earliest missing applied identity differs from closed replay finding')
        original = native[name][command]['message']
        require(command in worker[name] and original['decision_sequence'] == decision
                and original['clock_ns'] <= clock and original['source_clock_ns'] == first['source']['record']['payload']['message']['target']['clock_ns'],
                'first missing applied lacks exact original native/worker support')
        result[name] = {'native_unique_status_count':len(native[name]),'motion_unique_status_count':len(motion[name]),
            'worker_unique_status_count':len(worker[name]),'missing_from_motion_count':len(missing_motion),
            'missing_from_motion_cmd_sequences':missing_motion,'missing_from_worker_count':len(missing_worker),
            'missing_from_worker_cmd_sequences':missing_worker,'received_motion_mismatch_count':0,'received_worker_mismatch_count':0,
            'applied_events_without_motion_ack_count':len(absent_applied),
            'first_missing_applied':first,'matching_motion_receipt_count':0,
            'native_original_status_lines':native[name][command]['sources'],
            'worker_original_receipt_lines':worker[name][command]['sources']}
    return {'robots':result,'record_counts':{key:dict(value) for key,value in counts.items()},
            'qos_source_evidence':source_qos(inputs),'preserved_failed_replay':failed_replay(inputs,args.failed_replay)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--failed-replay',type=Path,default=A/'closed_prewarm_replay_failed_result_v1.json')
    args = parser.parse_args()
    require(not args.output.exists() and args.output.resolve().is_relative_to(Path('/tmp')),'exclusive output must be new /tmp path')
    inputs = Inputs();inputs.raw(Path(__file__).resolve());started = time.monotonic_ns();errors = [];findings = {}
    try:
        findings = review(inputs,args);inputs.finish()
    except (OSError,ValueError,KeyError,TypeError,IndexError,ArithmeticError,subprocess.SubprocessError) as error:
        errors.append(type(error).__name__+': '+str(error))
    result = {'schema':SCHEMA,'passed':not errors,'scope':'complete_closed_original_receipt_forensics_only',
        'scientific_pass_claimed':False,'native_admission':False,'old_native_failure_reclassified':False,
        'old_replay_failure_reclassified':False,'new_native_runs':0,'gpu_calls':0,'tracker_calls':0,
        'started_monotonic_ns':started,'ended_monotonic_ns':time.monotonic_ns(),
        'source_freeze':OLD,'epoch':EPOCH,'findings':findings,'input_bindings':list(inputs.proofs.values()),'errors':errors,
        'conclusion_scope':'Native publish and worker receipt exist; Motion full trace has no matching ACK. The concrete loss layer is unknown. Historical and current source QoS are distinguished; source settings alone do not prove the loss mechanism.',
        'prohibited_credit':'No ACK is injected, no tracker or science reader is called, and complete old replay remains FAIL. A forensic PASS is not a replay/native/continuous-model qualification.'}
    with args.output.open('x') as stream:
        json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps({'schema':SCHEMA,'passed':result['passed'],'errors':errors,'output':str(args.output)}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
