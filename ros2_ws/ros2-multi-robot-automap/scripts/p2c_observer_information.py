"""Bind one observer information dispatch to its original failed assignment."""
import json
import math


def observer_information_audit(path, declared=False):
    assignments={};used=set();count=0
    for line in path.open():
        event=json.loads(line)
        if event.get('event')=='coordinator_rally_assignment_failed':
            key=round(event['event_time']*1e9)
            assert key not in assignments,'duplicate failed-assignment source'
            assignments[key]=event
        if event.get('event')!='coordinator_navigation_decision':continue
        saved=(event.get('target_survey_selection') or {}).get('observer_connection_priority')
        if saved is None:continue
        assert declared,'undeclared observer connection information priority'
        assert event['kind']=='target_information_survey' and event['task_phase']=='FOUND'
        assert saved['strategy']=='one_observer_information_survey_before_peer_reinspection'
        assert saved['limit']=='one_dispatched_survey_per_context'
        at=saved['assignment_evaluated_at_sec'];assert math.isfinite(at) and at<=event['event_time']
        assignment=assignments.get(round(at*1e9));assert assignment is not None,'missing original failed assignment'
        diagnostics=assignment['geometry_diagnostics'];observer=saved['observer_robot'];peer=saved['disconnected_robot']
        assert diagnostics['reason']=='disconnected_rally_approach' and diagnostics['robot']==peer
        assert assignment['observer_robot']==observer==event['robot'] and observer!=peer
        names=sorted(assignment['robot_positions'])
        assert saved['participants']==names and observer in names and peer in names
        assert saved['target']==assignment['target']==event['target_survey_selection']['target']
        assert event['battery_modes'][observer]=='ACTIVE'
        context=(tuple(saved['target']),tuple(names),observer,peer)
        assert context not in used,'observer connection information survey repeated in the same context'
        used.add(context);count+=1
    return dict(status='PASS',observer_information_dispatches=count,declared=declared,
        scope='Original failed conservative assignment and one dispatched existing information survey per target/participants/observer/disconnected-peer context. Existing full survey route, body, return budget and source gates remain independent.')
