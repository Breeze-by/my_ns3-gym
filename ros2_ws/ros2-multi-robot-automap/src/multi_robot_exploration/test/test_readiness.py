from types import SimpleNamespace
import pytest
from multi_robot_exploration.readiness import LifecycleQueries
from multi_robot_exploration.spawn_entity_checked import ModelInventory, finish_spawn


class Future:
    def __init__(self, response=None):
        self.response = response
        self.cancelled = False
    def done(self):
        return self.response is not None
    def result(self):
        return self.response
    def cancel(self):
        self.cancelled = True


class Client:
    def __init__(self):
        self.requests = []
        self.removed = []
    def service_is_ready(self):
        return True
    def call_async(self, request):
        future = Future()
        self.requests.append(future)
        return future
    def remove_pending_request(self, future):
        self.removed.append(future)


def node_and_client():
    client = Client()
    node = SimpleNamespace(model_names=None, entity='tb3',
        create_client=lambda *args: client,
        get_logger=lambda: SimpleNamespace(info=lambda x: None, error=lambda x: None, warn=lambda x: None))
    return node, client


@pytest.mark.parametrize('state_id,label,expected', [(2, 'inactive', False), (3, 'inactive', False), (2, 'active', False), (3, 'active', True)])
def test_lifecycle_requires_exact_active_state(state_id, label, expected):
    node, client = node_and_client()
    query = LifecycleQueries(node, ['/tb1/controller_server'])
    query.poll(0.)
    client.requests[0].response = SimpleNamespace(current_state=SimpleNamespace(id=state_id, label=label))
    query.poll(.1)
    assert (not query.missing()) == expected


def test_lost_lifecycle_reply_is_retired_and_requeried_without_state_mutation():
    node, client = node_and_client()
    query = LifecycleQueries(node, ['/tb1/controller_server'])
    query.poll(0.)
    query.poll(2.)
    assert client.requests[0].cancelled and client.removed == client.requests[:1]
    assert len(client.requests) == 2
    client.requests[-1].response = SimpleNamespace(current_state=SimpleNamespace(id=3, label='active'))
    query.poll(2.1)
    assert not query.missing()


def test_inventory_retries_lost_read_reply_and_accepts_empty_world():
    node, client = node_and_client()
    inventory = ModelInventory(node)
    inventory.poll(0.)
    inventory.poll(2.)
    assert client.requests[0].cancelled and len(client.requests) == 2
    client.requests[-1].response = SimpleNamespace(success=True, model_names=[])
    inventory.poll(2.1)
    assert node.model_names == set()


def test_failed_inventory_response_does_not_authorize_spawn():
    node, client = node_and_client()
    inventory = ModelInventory(node)
    inventory.poll(0.)
    client.requests[0].response = SimpleNamespace(success=False, model_names=['tb3'])
    inventory.poll(.1)
    assert node.model_names is None


def test_model_service_confirms_spawn_without_topic_or_spawn_reply():
    node, client = node_and_client()
    node.model_names = set()
    inventory = ModelInventory(node)
    clock = [0.]
    spawn_future = Future()
    def spin(node, timeout_sec):
        clock[0] += timeout_sec
        client.requests[-1].response = SimpleNamespace(success=True, model_names=['tb3'])
    assert finish_spawn(node, spawn_future, 1., inventory=inventory,
                        clock=lambda: clock[0], spin=spin, okay=lambda: True)
    assert not spawn_future.done()
    assert clock[0] == pytest.approx(.1)
