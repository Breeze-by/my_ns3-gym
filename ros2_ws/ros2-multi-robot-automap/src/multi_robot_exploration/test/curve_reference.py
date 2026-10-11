"""Keep historical straight comparisons and independently check new prefixes."""
import math

import pytest
from multi_robot_exploration import control as c
from p2c_outbound_routes import check_route


def preserve_straight_prefix(monkeypatch):
    original=c.exploration_leg_plans
    def straight(*args,**kwargs):
        kwargs['curved']=False
        return original(*args,**kwargs)
    monkeypatch.setattr(c,'exploration_leg_plans',straight)


def assert_full_prefix_safety(node,sent):
    local_maps=c.HeadquartersControl.delivered_return_maps(node)
    saved=c.grid_audit_evidence(node.map_data,node.resolution,node.origin,
                               'synthetic_original_planning',node.map_received_at,node.map_received_at)
    for name,a in sent:
        xy=(a['navigation_x'],a['navigation_y']) if isinstance(a,dict) else (a.navigation_x,a.navigation_y)
        route=(node.robot_positions[name],*node.goal_routes[name])
        assert route[-1]==pytest.approx(xy)
        check_route(saved,route)
        local=local_maps[name]
        check_route(c.grid_audit_evidence(local['data'],local['resolution'],local['origin'],
                    'synthetic_original_local',node.robot_map_received_at[name],node.robot_map_received_at[name]),route,local=True)
        state=node.battery_states[name]
        candidates=c.qualified_return_candidates(node.map_data,node.resolution,node.origin,xy,
            (state['charge_x'],state['charge_y']),state['charge_radius_m'],local)
        distance=min((r['path_distance_m'] for r in candidates if r['qualified']),default=None)
        assert distance is not None
        length=sum(math.dist(a,b) for a,b in zip(route,route[1:]))
        now=node.now()
        required=c.battery_assignment_required_energy(length,distance,
            state['move_cost_per_m'],state['idle_cost_per_sec'],state['return_path_factor'],
            state['nominal_speed_mps'],state['return_safety_margin'],
            state.get('return_recovery_wait_sec',c.RETURN_RECOVERY_WAIT_SEC),
            max(now-node.map_received_at,now-node.robot_map_received_at[name]),
            max(now-node.robot_odom_received_at[name],now-node.robot_tf_received_at[name]))
        assert required<state['energy']
