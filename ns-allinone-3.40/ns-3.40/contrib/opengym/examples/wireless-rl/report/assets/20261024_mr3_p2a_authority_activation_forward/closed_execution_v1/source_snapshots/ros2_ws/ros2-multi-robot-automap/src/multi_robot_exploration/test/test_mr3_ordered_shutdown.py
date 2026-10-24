"""Exercise real launch SDK events/actions without starting native processes."""

import json
import signal

from launch import LaunchContext
from launch.actions import EmitEvent, ExecuteProcess, LogInfo, RegisterEventHandler, TimerAction
from launch.events import Shutdown
from launch.events.process import ProcessExited, ProcessStarted, SignalProcess
from launch.utilities import perform_substitutions
import pytest

from test_launch_and_smoke import MAPPING_LAUNCH, load_module, mapping_actions


def details(action, pid, name=None):
    return {"action": action, "name": name or f"node-{pid}", "pid": pid,
            "cmd": ["synthetic-sdk-event"], "cwd": None, "env": {}}


def markers(actions, context):
    result = []
    for action in actions:
        if isinstance(action, LogInfo):
            message = perform_substitutions(context, action.msg)
            if message.startswith("MR3_ORDERED_SHUTDOWN "):
                result.append(json.loads(message.split(" ", 1)[1]))
    return result


def signals(actions):
    return [action.event for action in actions if isinstance(action, EmitEvent)
            and isinstance(action.event, SignalProcess)]


def shutdowns(actions):
    return [action.event for action in actions if isinstance(action, EmitEvent)
            and isinstance(action.event, Shutdown)]


def coordinator():
    module = load_module("ordered_mapping", MAPPING_LAUNCH)
    context = LaunchContext()
    server, evaluator, first, last = [ExecuteProcess(cmd=["unused"]) for _ in range(4)]
    native_calls = []

    def stop_native(ctx):
        native_calls.append(ctx)
        return []

    state = module.OrderedRosShutdown("test-epoch", lambda event: event.action is server,
                                      stop_native)
    events = [details(action, pid) for action, pid in
              [(server, 101), (first, 102), (last, 103), (evaluator, 104)]]
    for event in events:
        state.started(ProcessStarted(**event), context)
    return state, context, events, native_calls


def begin(state, context, events):
    # Specific OnProcessExit handlers run before earlier global handlers in Humble.
    event = ProcessExited(returncode=0, **events[-1])
    actions = state.begin(event, context)
    assert state.exited(event, context) == []
    return actions


def test_reverse_actual_starts_wait_for_each_matching_clean_exit_and_cancel_old_timer():
    state, context, events, native_calls = coordinator()
    actions = begin(state, context, events)
    assert [record["pid"] for record in markers(actions, context)
            if record["event"] == "signal"] == [103]
    assert signals(actions)[0].signal == signal.SIGINT
    assert signals(actions)[0].process_matcher(events[2]["action"])
    assert not signals(actions)[0].process_matcher(events[1]["action"])
    assert native_calls == [] and not shutdowns(actions)
    old_timer = next(action for action in actions if isinstance(action, TimerAction))
    actions = state.exited(ProcessExited(returncode=0, **events[2]), context)
    assert signals(actions)[0].process_matcher(events[1]["action"])
    assert old_timer.actions[0].execute(context) == []
    assert native_calls == []
    actions = state.exited(ProcessExited(returncode=0, **events[1]), context)
    assert native_calls == [context] and not signals(actions)
    assert markers(actions, context)[0]["event"] == "process_exited"
    assert markers(actions, context)[1]["event"] == "ros_complete"


@pytest.mark.parametrize("returncode", [-11, 1, -2])
def test_noncurrent_process_nonzero_exit_aborts_instead_of_silently_removing_it(returncode):
    state, context, events, native_calls = coordinator()
    begin(state, context, events)
    actions = state.exited(ProcessExited(returncode=returncode, **events[1]), context)
    assert state.phase == "failed" and len(shutdowns(actions)) == 1
    assert markers(actions, context)[-1]["reason"] == "nonzero_process_exit"
    assert native_calls == []


def test_early_clean_exit_is_recorded_and_skipped_without_a_second_signal():
    state, context, events, native_calls = coordinator()
    begin(state, context, events)
    early = state.exited(ProcessExited(returncode=0, **events[1]), context)
    assert markers(early, context)[0]["controlled"] is False
    assert signals(early) == [] and native_calls == []
    last = state.exited(ProcessExited(returncode=0, **events[2]), context)
    assert native_calls == [context] and signals(last) == []


@pytest.mark.parametrize("changed", ["action", "pid", "name"])
def test_wrong_exit_identity_cannot_advance_or_complete_shutdown(changed):
    state, context, events, native_calls = coordinator()
    begin(state, context, events)
    foreign = dict(events[2])
    foreign[changed] = {"action": ExecuteProcess(cmd=["foreign"]),
                        "pid": 999, "name": "foreign-999"}[changed]
    actions = state.exited(ProcessExited(returncode=0, **foreign), context)
    assert state.phase == "failed" and len(shutdowns(actions)) == 1
    assert native_calls == [] and signals(actions) == []


def test_independent_wall_deadline_fails_without_native_stop_or_fabricated_exit():
    state, context, events, native_calls = coordinator()
    actions = begin(state, context, events)
    timer = next(action for action in actions if isinstance(action, TimerAction))
    assert timer.period == 10.0
    failed = timer.actions[0].execute(context)
    assert markers(failed, context)[0]["reason"] == "process_exit_timeout_10_wall_sec"
    assert len(shutdowns(failed)) == 1 and native_calls == []
    assert state.pending["returncode"] is None


def test_late_process_start_and_duplicate_pid_each_fail_explicitly():
    state, context, events, _ = coordinator()
    duplicate = state.started(ProcessStarted(**details(ExecuteProcess(cmd=["new"]), 102)),
                              context)
    assert markers(duplicate, context)[0]["reason"] == "duplicate_process_identity"
    state, context, events, _ = coordinator()
    begin(state, context, events)
    late = state.started(ProcessStarted(**details(ExecuteProcess(cmd=["new"]), 105)), context)
    assert markers(late, context)[-1]["reason"] == "process_started_during_shutdown"
    assert len(shutdowns(late)) == 1


def test_evaluator_nonzero_exit_never_starts_ordered_success_path():
    state, context, events, native_calls = coordinator()
    actions = state.begin(ProcessExited(returncode=1, **events[-1]), context)
    assert state.phase == "failed" and len(shutdowns(actions)) == 1
    assert signals(actions) == [] and native_calls == []


def test_current_nonzero_exit_cannot_signal_next_node_or_start_gazebo_stop():
    state, context, events, native_calls = coordinator()
    begin(state, context, events)
    result = state.exited(ProcessExited(returncode=-11, **events[2]), context)
    assert len(shutdowns(result)) == 1 and not signals(result)
    assert state.phase == "failed" and native_calls == []


def test_native_complete_requires_real_started_and_clean_exited_server_and_cli():
    state, context, events, _ = coordinator()
    begin(state, context, events)
    for event in reversed(events[1:3]):
        state.exited(ProcessExited(returncode=0, **event), context)
    result = state.completed()
    assert state.phase == "failed" and len(shutdowns(result)) == 1
    assert markers(result, context)[0]["reason"] == "native_completion_not_verified"


def test_trackers_precede_even_the_first_information_process(monkeypatch, tmp_path):
    module, context, _ = mapping_actions(monkeypatch, tmp_path, stepped=True)
    actions = module.launch_setup(context)
    assert all(isinstance(action, RegisterEventHandler) for action in actions[:2])
    first_process = next(action for action in actions if isinstance(action, ExecuteProcess))
    earliest = ProcessStarted(**details(first_process, 301, "mr3_information-1"))
    # Exercise only the prefix: later launch handlers have not yet been registered.
    returned = [entity for action in actions[:2]
                if action.event_handler.matches(earliest)
                for entity in action.event_handler.handle(earliest, context)]
    started = markers(returned, context)
    assert len(started) == 1 and started[0]["event"] == "process_started"
    assert started[0]["process_start_index"] == 1 and started[0]["pid"] == 301
    assert started[0]["process_name"] == "mr3_information-1"


@pytest.mark.parametrize("first_exit", ["server", "cli"])
def test_actual_launch_handlers_keep_contact_guard_quiet_and_gazebo_last(
        monkeypatch, tmp_path, first_exit):
    module, context, _ = mapping_actions(monkeypatch, tmp_path, stepped=True)
    context.launch_configurations.update({
        "evaluation_contract_path": "explicit-contract", "enable_task_evaluator": "true",
    })
    nodes = []
    original = module.Node

    def capture(**arguments):
        node = original(**arguments)
        nodes.append((node, arguments["executable"]))
        return node

    monkeypatch.setattr(module, "Node", capture)
    actions = module.launch_setup(context)
    handlers = []

    def register(entities):
        for action in entities:
            if isinstance(action, RegisterEventHandler) and (
                    action.condition is None or action.condition.evaluate(context)):
                handlers.insert(0, action.event_handler)

    register(actions)
    receipts = []

    def dispatch(event):
        result = []
        for handler in tuple(handlers):
            if handler.matches(event):
                returned = handler.handle(event, context) or []
                result.extend(returned)
                register(returned)
        receipts.extend(markers(result, context))
        return result

    server = next(action for action in actions if type(action) is ExecuteProcess)
    server_event = details(server, 201, "gzserver-4")
    server_event["cmd"] = [perform_substitutions(context, token) for token in server.cmd]
    reducer = details(next(node for node, name in nodes if name == "mr3_contact_reducer"),
                      202, "mr3_contact_reducer-2")
    evaluator = details(next(node for node, name in nodes if name == "task_evaluator"),
                        203, "task_evaluator-37")
    for event in [server_event, reducer, evaluator]:
        dispatch(ProcessStarted(**event))
    result = dispatch(ProcessExited(returncode=0, **evaluator))
    assert len(signals(result)) == 1 and not shutdowns(result)
    result = dispatch(ProcessExited(returncode=0, **reducer))
    assert not shutdowns(result)  # Existing contact-reducer OnExit guard must coalesce.
    stop = next(action for action in result if isinstance(action, ExecuteProcess))
    assert [record["event"] for record in markers(result, context)] == [
        "process_exited", "ros_complete", "gz_stop"]
    cli = details(stop, 204, "mr3_gazebo_native_stop-38")
    dispatch(ProcessStarted(**cli))
    exits = {"server": server_event, "cli": cli}
    assert not shutdowns(dispatch(ProcessExited(returncode=0, **exits[first_exit])))
    last = "cli" if first_exit == "server" else "server"
    result = dispatch(ProcessExited(returncode=0, **exits[last]))
    assert len(shutdowns(result)) == 1
    assert receipts[-1]["event"] == "complete"
    assert [record["receipt_index"] for record in receipts] == list(range(1, len(receipts) + 1))
    assert all(record["protocol"] == module.OrderedRosShutdown.protocol for record in receipts)
    assert sorted(record["wall_monotonic_ns"] for record in receipts) == [
        record["wall_monotonic_ns"] for record in receipts]
    assert receipts[-1]["server_pid"] == 201 and receipts[-1]["stop_cli_pid"] == 204
