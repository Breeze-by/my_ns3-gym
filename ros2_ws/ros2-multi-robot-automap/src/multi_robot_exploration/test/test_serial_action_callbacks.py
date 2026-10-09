"""Future completion only queues work; the original state callback owns mutation."""
import queue
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from rclpy.task import Future
from multi_robot_exploration.control import HeadquartersControl


def node():
    return SimpleNamespace(shutdown_requested=False,action_done_callbacks=queue.SimpleQueue(),
        action_done_guard=SimpleNamespace(trigger=Mock()),context=SimpleNamespace(ok=lambda:True))


def test_real_futures_queue_exactly_once_in_receipt_order_until_state_group_drains():
    n=node();done=[];a=Future();b=Future()
    for future in (a,b):
        HeadquartersControl.defer_action_done_callback(n,future,lambda f:done.append(f.result()))
    b.set_result('second');a.set_result('first')
    assert done==[] and n.action_done_guard.trigger.call_count==2
    HeadquartersControl.drain_action_done_callbacks(n)
    HeadquartersControl.drain_action_done_callbacks(n)
    assert done==['second','first']


def test_shutdown_discards_late_completion_before_guard_or_owner_change():
    n=node();future=Future();done=[]
    HeadquartersControl.defer_action_done_callback(n,future,lambda f:done.append(f.result()))
    n.shutdown_requested=True;future.set_result('late')
    assert n.action_done_callbacks.empty() and not done
    n.action_done_guard.trigger.assert_not_called()


def test_shutdown_during_drain_stops_remaining_state_work():
    n=node();done=[]
    def stop(future):n.shutdown_requested=True;done.append('stop')
    n.action_done_callbacks.put((stop,Future()))
    n.action_done_callbacks.put((lambda f:done.append('late'),Future()))
    HeadquartersControl.drain_action_done_callbacks(n)
    assert done==['stop'] and not n.action_done_callbacks.empty()


def test_callback_errors_remain_visible_in_state_group():
    n=node()
    def fail(future):raise ValueError('real response error')
    n.action_done_callbacks.put((fail,Future()))
    with pytest.raises(ValueError,match='real response error'):
        HeadquartersControl.drain_action_done_callbacks(n)


@pytest.mark.parametrize('closing',[False,True])
def test_guard_errors_are_suppressed_only_for_closed_context(closing):
    n=node();n.context.ok=lambda:not closing
    n.action_done_guard.trigger.side_effect=RuntimeError('guard invalid')
    future=Future();HeadquartersControl.defer_action_done_callback(n,future,lambda f:None)
    # Executor-independent Future reports callback errors as warnings.
    if closing:future.set_result('closed')
    else:
        with pytest.warns(UserWarning,match='guard invalid'):future.set_result('active')
