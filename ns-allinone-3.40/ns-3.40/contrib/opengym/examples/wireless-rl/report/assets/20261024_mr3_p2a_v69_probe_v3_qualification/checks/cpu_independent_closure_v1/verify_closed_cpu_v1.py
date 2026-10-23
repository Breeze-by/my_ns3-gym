"""Read-only verification of six already closed A69 CPU activities. No imports of project code."""
from pathlib import Path
from decimal import Decimal
import collections
import hashlib
import json
import os
import stat
import subprocess
import time
import xml.etree.ElementTree as ET

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A = W/'report/assets/20261024_mr3_p2a_v69_probe_v3_qualification'
OUT = Path(__file__).parent
GROUPS = ('fresh_ros_cpu_v1','fresh_learner_cpu_v1','admission_cpu_v1','readiness_cpu_v1','prepare_cpu_v1','plan_check_cpu_v1')
CACHE = {}
REPORT = {'schema':'mr3-v69-independent-closed-cpu-review-v1','passed':False,
    'method':'stdlib metadata/source/recovery verification only; no project code or tests executed',
    'new_freeze_git_checked':False,'native_or_scientific_qualification_credit':False,
    'canonical_mutations':0,'groups':[],'errors':[]}


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def stamp(path):
    s=path.stat()
    require(stat.S_ISREG(s.st_mode),'non-regular bound input: '+str(path))
    return [s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns]


def read(path):
    path=Path(path)
    if path not in CACHE:
        before=stamp(path);raw=path.read_bytes()
        require(before==stamp(path),'input changed while reading: '+str(path))
        CACHE[path]=(raw,before)
    return CACHE[path][0]


def load(path):
    return json.loads(read(path))


def fileproof(path):
    raw=read(path)
    return {'path':str(path),'bytes':len(raw),'sha256':sha(raw)}


def source_map(rows):
    require(type(rows) is list,'source records must be list')
    result={}
    for row in rows:
        path=Path(row['path'])
        require(path.is_absolute() and str(path) not in result,'duplicate/nonabsolute source')
        require(type(row['bytes']) is int and row['bytes']>=0,'invalid bound source size')
        raw=read(path)
        require(len(raw)==row['bytes'] and sha(raw)==row['sha256'],'current source differs: '+str(path))
        require(CACHE[path][1]==row['stat'],'current source stat differs: '+str(path))
        result[str(path)]={'bytes':len(raw),'sha256':sha(raw)}
    return result


def gone(identity):
    require(type(identity.get('pid')) is int and identity['pid']>0 and type(identity.get('start_ticks')) is int,'invalid saved identity')
    p=Path('/proc')/str(identity['pid'])/'stat'
    try:
        line=p.read_text();tail=line[line.rfind(')')+2:].split()
    except FileNotFoundError:
        return dict(saved=identity,gone=True,reason='pid_absent')
    current=int(tail[19])
    require(current!=identity['start_ticks'],'saved process is still present: '+str(identity['pid']))
    return dict(saved=identity,gone=True,reason='pid_reused_with_different_start',current_start_ticks=current)


def check_junit(path,expected,modules=None,names=None):
    root=ET.fromstring(read(path));cases=list(root.iter('testcase'));suites=list(root.iter('testsuite'))
    require(len(cases)==expected and sum(int(x.attrib['tests']) for x in suites)==expected,'JUnit case count differs')
    require(all(int(x.attrib.get(k,0))==0 for x in suites for k in ('errors','failures','skipped')),'JUnit nonzero failures/errors/skips')
    require(not any(list(c) for c in cases),'JUnit case has failure/error/skip/output child')
    if modules is not None:
        for module in modules:
            stem=Path(module).stem
            require(any(stem in c.attrib.get('classname','').split('.') for c in cases),'declared test has no non-skipped case: '+module)
    if names is not None:
        require(sorted(c.attrib['name'] for c in cases)==sorted(names),'admission exact testcase names differ')
    return dict(fileproof(path),tests=len(cases),failures=0,errors=0,skipped=0,declared_module_count=len(modules or []))


def git_blobs(requests):
    requests=sorted(set(requests))
    if not requests:
        return {}
    p=subprocess.run(['git','cat-file','--batch'],cwd=ROOT,input=''.join(x+'\n' for x in requests).encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True)
    offset=0;result={}
    for request in requests:
        end=p.stdout.index(b'\n',offset);header=p.stdout[offset:end].split();offset=end+1
        require(len(header)==3 and header[1]==b'blob','recovery Git blob missing/nonblob: '+request)
        size=int(header[2]);raw=p.stdout[offset:offset+size];offset+=size
        require(len(raw)==size and p.stdout[offset:offset+1]==b'\n','invalid git batch response')
        offset+=1;result[request]={'bytes':size,'sha256':sha(raw)}
    require(offset==len(p.stdout),'unexpected git batch tail')
    return result


def main():
    fresh=load(A/'fresh_cpu_spec_v1.json');admission=load(A/'admission_cpu_spec_v1.json')
    require(len(fresh['source_bindings'])==322 and fresh['status']=='SEALED_NOT_EXECUTED','fresh source declaration differs')
    # Recreate the stated filesystem union without importing/executing its runner.
    ros=ROOT/'ros2_ws/ros2-multi-robot-automap';paths=set()
    for d in (W/'mr3_learning',W/'mr3_learning/tests',ros/'src/multi_robot_exploration/multi_robot_exploration',ros/'src/multi_robot_exploration/test',ros/'src/merge_map/merge_map',ros/'src/merge_map/test',A):
        paths.update(d.glob('*.py'))
    paths.update((ros/'scripts/mr3_env_worker.py',ros/'src/multi_robot/launch/gazebo_multirobot_mapping_with_nav2.launch.py'))
    require({str(p.relative_to(ROOT)) for p in paths}==set(fresh['source_bindings']),'current filesystem Python union changed')
    for relative,pin in fresh['source_bindings'].items():
        require({'bytes':len(read(ROOT/relative)),'sha256':sha(read(ROOT/relative))}==pin,'fresh exact current pin differs: '+relative)
    fresh_map={str(ROOT/k):v for k,v in fresh['source_bindings'].items()}
    fresh_map[str(A/'fresh_cpu_spec_v1.json')]={k:v for k,v in fileproof(A/'fresh_cpu_spec_v1.json').items() if k!='path'}
    groups={g['id']:g for g in fresh['groups']}
    waits={};maps={};all_ids=[]
    for name in GROUPS:
        wp=A/'checks'/name/'actual_wait.json';wait=load(wp);waits[name]=wait
        rp=A/'checks'/name/'root_tool_reap_v1.json';receipt=load(rp)
        require(wait['schema']=='mr3-reach-outer-actual-wait-v1' and wait['scope']=='cpu','actualwait identity/scope differs')
        require(wait['actual_waited'] is True and type(wait['actual_returncode']) is int and wait['actual_returncode']==0 and wait['passed'] is True and wait['errors']==[],'actualwait is not complete PASS')
        require(receipt['actual_tool_reaped'] is True and type(receipt['actual_returncode']) is int and receipt['actual_returncode']==0,'Root tool was not really reaped0')
        require(wait['source_before']==wait['source_after'] and wait['source_unchanged'] is True,'actual source before/after differs')
        duration=Decimal(wait['ended_monotonic_ns']-wait['started_monotonic_ns'])/Decimal(10**9)
        require(duration==Decimal(wait['actual_child_wait_seconds']) and duration>=0,'actual wait duration inconsistent')
        current=source_map(wait['source_before']);maps[name]=current
        if name in (*groups,'readiness_cpu_v1'):
            require(current==fresh_map,'fresh/readiness source scope differs from322+spec')
        console=Path(wait['console']['path']);require(sha(read(console))==wait['console']['sha256'],'console SHA differs')
        statuses=[gone(wait[k]) for k in ('coordinator_identity','child_identity')];all_ids.extend(statuses)
        row=dict(id=name,actual_wait=fileproof(wp),root_tool_reap=fileproof(rp),actual_tool_session_id=receipt['actual_tool_session_id'],actual_returncode=0,
            actual_child_wait_seconds=str(duration),source_count=len(current),source_before_after_equal=True,current_sha_bytes_stat_equal=True,
            console=fileproof(console),saved_identities=statuses,actual_argv=wait['actual_argv'])
        if name in groups:
            g=groups[name];require(wait['actual_argv']==g['actual_argv'],'actual fresh argv differs from spec')
            row['junit']=check_junit(A/'checks'/name/'junit.xml',212 if name.startswith('fresh_ros') else 506,modules=g['test_files'])
        elif name=='admission_cpu_v1':
            require(wait['actual_argv']==admission['actual_argv'],'admission argv differs from spec')
            row['junit']=check_junit(Path(admission['pytest_junit']),33,names=admission['expected_testcase_names'])
            for relative,pin in admission['expected_source_hashes'].items():
                require(sha(read(ROOT/relative))==pin,'admission expected source pin differs: '+relative)
        else:
            row['junit']=None
        REPORT['groups'].append(row)
    require(len({(x['saved']['pid'],x['saved']['start_ticks']) for x in all_ids})==12,'duplicate/missing12 saved identities')
    recoveries={};requests=[]
    for name in ('fresh_ros_cpu_v1','fresh_learner_cpu_v1','admission_cpu_v1'):
        path=A/'checks'/(name+'_source_recovery.json');rec=load(path);by_path={}
        for row in rec['sources']:
            require(row['path'] not in by_path,'duplicate recovery source')
            by_path[row['path']]=row
            if row['kind']=='git_blob':requests.append(row['freeze']+':'+row['path'])
            else:require(row['kind']=='snapshot','unknown recovery kind')
        require(set(str(ROOT/k) for k in by_path)==set(maps[name]),'recovery set differs from actualwait')
        recoveries[name]=(path,by_path)
    blobs=git_blobs(requests)
    for name,(path,by_path) in recoveries.items():
        for relative,row in by_path.items():
            expected={'bytes':row['bytes'],'sha256':row['sha256']}
            require(expected==maps[name][str(ROOT/relative)],'recovery pin differs from actual source')
            if row['kind']=='git_blob':actual=blobs[row['freeze']+':'+relative]
            else:
                raw=read(A/row['snapshot']);actual={'bytes':len(raw),'sha256':sha(raw)}
            require(actual==expected,'actual recovery bytes differ: '+relative)
        next(r for r in REPORT['groups'] if r['id']==name)['recovery']=dict(fileproof(path),verified_sources=len(by_path),kinds=dict(collections.Counter(x['kind'] for x in by_path.values())))
    # Readiness has the exact same323-source set, not a separate recovery receipt.
    require(maps['readiness_cpu_v1']==maps['fresh_ros_cpu_v1'],'readiness cannot use exact shared recovery')
    next(r for r in REPORT['groups'] if r['id']=='readiness_cpu_v1')['recovery']={'kind':'exact-same-source-map reference to freshly verified ROS recovery','path':str(recoveries['fresh_ros_cpu_v1'][0]),'verified_sources':323,'separate_receipt_claimed':False}
    ready=load(A/'checks/device_readiness_v1.json')
    require(ready['passed'] is True and ready['world_started'] is False and ready['model_constructed'] is False and all(ready[k]==0 for k in ('forward_calls','backward_calls','optimizer_steps')),'readiness scope differs')
    for i,filename in enumerate(('device_readiness_v1_ros.json','device_readiness_v1_learner.json')):
        inner=load(A/'checks'/filename);require(inner==ready['results'][i] and inner['passed'] is True,'readiness combined/actual outputs differ')
        for module in inner['modules']:
            raw=read(module['path']);require(len(raw)==module['bytes'] and sha(raw)==module['sha256'],'readiness imported module proof differs')
    REPORT['readiness_output']=fileproof(A/'checks/device_readiness_v1.json')
    REPORT['fresh_spec']=fileproof(A/'fresh_cpu_spec_v1.json')
    REPORT['admission_spec']=fileproof(A/'admission_cpu_spec_v1.json')
    REPORT['saved_identities_checked_gone']=12
    REPORT['fresh_filesystem_python_sources']=322
    REPORT['evidence_read_count']=len(CACHE)
    for p,(_,before) in CACHE.items():
        require(stamp(p)==before,'reviewed evidence changed before verdict: '+str(p))
    REPORT['all_reviewed_inputs_stat_stable']=True
    REPORT['passed']=True


if __name__=='__main__':
    started=time.monotonic_ns()
    try:
        main()
    except Exception as exc:
        REPORT['errors'].append(type(exc).__name__+': '+str(exc))
    REPORT['review_wall_seconds']=str(Decimal(time.monotonic_ns()-started)/Decimal(10**9))
    with (OUT/'review_result_v1.json').open('x') as stream:
        json.dump(REPORT,stream,indent=2);stream.write('\n')
    print(json.dumps({'passed':REPORT['passed'],'groups':len(REPORT['groups']),'errors':REPORT['errors'],'saved_identities_checked_gone':REPORT.get('saved_identities_checked_gone')}))
    raise SystemExit(0 if REPORT['passed'] else 1)
