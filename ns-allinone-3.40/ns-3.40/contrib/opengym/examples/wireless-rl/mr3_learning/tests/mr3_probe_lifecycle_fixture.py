"""Synthetic received observations; current real dispatcher/masks, no World."""
import ast
import builtins
import hashlib
from pathlib import Path
import symtable
import sys
ROOT=Path(__file__).resolve().parents[8]
COMP=ROOT/'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration'
# Pure Python protocol/observation dependency only; no ROS nodes or binaries.
sys.path.insert(0,str(COMP))
from multi_robot_exploration.mr3_protocol import GoalDispatcher

def _canonical_action_masks():
    """Execute the exact canonical mask/dependency AST without importing SLAM.

    The complete original file is read once and SHA-bound; all constants are
    extracted from its original assignments, never copied/replaced in tests.
    Unexpected dependencies fail rather than inventing an alternate mask.
    """
    path=COMP/'multi_robot_exploration/mr3_observation.py'
    data=path.read_bytes();text=data.decode();tree=ast.parse(text,filename=str(path))
    declarations={}
    for statement in tree.body:
        if isinstance(statement,ast.FunctionDef):declarations[statement.name]=statement
        elif isinstance(statement,ast.Assign):
            for target in statement.targets:
                if isinstance(target,ast.Name):declarations[target.id]=statement
        elif isinstance(statement,(ast.Import,ast.ImportFrom)):
            for alias in statement.names:declarations[alias.asname or alias.name.split('.')[0]]=statement
    required=['_action_masks'];selected={};seen=set()
    def globals_in(table):
        names={symbol.get_name() for symbol in table.get_symbols()
               if symbol.is_referenced() and symbol.is_global()}
        for child in table.get_children():names.update(globals_in(child))
        return names
    while required:
        name=required.pop()
        if name in seen or name in vars(builtins):continue
        seen.add(name)
        if name not in declarations:raise AssertionError('unbound canonical mask dependency: '+name)
        statement=declarations[name];selected[id(statement)]=statement
        if isinstance(statement,(ast.Import,ast.ImportFrom)):
            if name not in {'math','np','timestamp_ns'}:
                raise AssertionError('unexpected canonical mask import: '+name)
        elif isinstance(statement,ast.FunctionDef):
            required.extend(globals_in(symtable.symtable(ast.get_source_segment(text,statement),str(path),'exec')))
        else:
            required.extend(n.id for n in ast.walk(statement.value)
                            if isinstance(n,ast.Name) and isinstance(n.ctx,ast.Load))
    body=[n for n in tree.body if id(n) in selected]
    namespace={'__name__':'canonical_action_mask_fixture','__file__':str(path)}
    exec(compile(ast.Module(body=body,type_ignores=[]),str(path),'exec'),namespace)
    assert namespace['_action_masks'].__code__.co_filename==str(path)
    return namespace['_action_masks'],str(path),hashlib.sha256(data).hexdigest(),tuple(sorted(seen))


_action_masks,ACTION_MASK_SOURCE_PATH,ACTION_MASK_WHOLE_FILE_SHA256,ACTION_MASK_DEPENDENCIES=_canonical_action_masks()
NAMES=('tb1','tb2','tb3')
class Lifecycle:
    def __init__(self):
        self.events = []
        self.clock = 0.
        self.dispatcher = GoalDispatcher('synthetic-lifecycle', self.events.append)

    def advance(self, when):
        while self.clock < when:
            self.clock = min(when, self.clock + .25)
            for name, state in self.dispatcher.states.items():
                if state.goal_id is not None and not state.cancel_requested:
                    self.dispatcher.renew(name, state.goal_id, self.dispatcher.epoch,
                                          self.clock, self.clock + 1.5)
            self.dispatcher.tick(self.clock)

    def snapshot(self, when, *, x=0., speed=0., path=0., long_available=True):
        self.advance(when)
        nav = self.dispatcher.navigation(when)
        robots = [dict(name=name, x=x, y=float(index * 4), yaw=0.,
            fresh=True, valid=True, v=speed, w=0., epoch=self.dispatcher.epoch,
            source_stamp=when, odom_source_stamp=when, path_map_available=True,
            activity={'estimated_path_m':path, 'path_observation_complete':True},
            navigation=nav[name]) for index, name in enumerate(NAMES)]
        candidates = []
        for index in range(8):
            owner = index % 3
            distance = .8 if index < 3 else 1.6
            candidates.append(dict(index=index, x=distance, y=float(owner * 4),
                valid=index < 6 and (index < 3 or long_available),
                reachable=[robot == owner for robot in range(3)],
                path_distances_m=[distance if robot == owner else None for robot in range(3)]))
        per, joint, reasons = _action_masks(robots, candidates, when)
        return dict(epoch=self.dispatcher.epoch, sequence=round(when*10)+1,
            digest='synthetic-'+str(when), task_elapsed_sec=when, robots=robots,
            candidates=candidates, per_robot_action_mask=per, joint_action_mask=joint,
            mask_reasons=reasons)

    def apply(self, snapshot, action):
        assert snapshot['joint_action_mask'][action]
        statuses = []
        for index, choice in enumerate((action//100, action//10%10, action%10)):
            goal = snapshot['candidates'][choice] if choice < 8 else None
            statuses.append(self.dispatcher.submit(NAMES[index],
                'GOAL' if choice < 8 else 'KEEP' if choice == 8 else 'WAIT',
                self.clock, snapshot['sequence'], snapshot['sequence'], self.clock+1.5,
                goal=None if goal is None else {'x':goal['x'], 'y':goal['y']},
                command_epoch=self.dispatcher.epoch, created_at=self.clock))
        return {'command':dict(epoch=snapshot['epoch'], observation_sequence=snapshot['sequence'],
            observation_digest=snapshot['digest'], action=action, command_id=snapshot['sequence']),
            'synthetic_dispatch_status':statuses}

    def accept_all(self, when=.1):
        self.advance(when)
        for name, state in self.dispatcher.states.items():
            self.dispatcher.on_accept(name, state.goal_id, True, when)

    def complete_all(self, status, when):
        self.advance(when)
        for name, state in self.dispatcher.states.items():
            self.dispatcher.on_result(name, state.goal_id, status, when)
