from types import SimpleNamespace
import pytest
from multi_robot_exploration.spawn_entity_checked import finish_spawn


@pytest.mark.parametrize('reply_done', [True, False])
def test_actual_entity_confirmation_does_not_need_a_service_reply(reply_done):
    clock = [0.]
    logs = []
    node = SimpleNamespace(entity='tb3', model_names=set(),
                           get_logger=lambda: SimpleNamespace(info=logs.append, error=logs.append))
    future = SimpleNamespace(done=lambda: reply_done,
                             result=lambda: SimpleNamespace(success=True))

    def spin(node, timeout_sec):
        clock[0] += timeout_sec
        if clock[0] >= .2:
            node.model_names = {'tb3'}

    assert finish_spawn(node, future, 1., clock=lambda: clock[0], spin=spin, okay=lambda: True)
    assert clock[0] == pytest.approx(.2)
    assert f'reply_received={reply_done}' in logs[-1]


@pytest.mark.parametrize('reply_done', [True, False])
def test_missing_entity_fails_within_wall_budget_even_with_success_reply(reply_done):
    clock = [0.]
    node = SimpleNamespace(entity='tb3', model_names={'tb1'},
                           get_logger=lambda: SimpleNamespace(info=lambda x: None, error=lambda x: None))
    future = SimpleNamespace(done=lambda: reply_done,
                             result=lambda: SimpleNamespace(success=True))
    assert not finish_spawn(node, future, .3, clock=lambda: clock[0],
                            spin=lambda node, timeout_sec: clock.__setitem__(0, clock[0]+timeout_sec),
                            okay=lambda: True)
    assert clock[0] == pytest.approx(.3)


def test_rejected_spawn_is_not_hidden_by_existing_entity():
    node = SimpleNamespace(entity='tb3', model_names={'tb3'},
                           get_logger=lambda: SimpleNamespace(error=lambda x: None))
    future = SimpleNamespace(done=lambda: True, result=lambda: SimpleNamespace(success=False))
    assert not finish_spawn(node, future, 1., clock=lambda: 0., okay=lambda: True)


@pytest.mark.parametrize('inserted', [True, False])
def test_queued_factory_timeout_requires_actual_insertion_within_wall_budget(inserted):
    clock=[0.]
    node=SimpleNamespace(entity='tb3',model_names=set(),
        get_logger=lambda: SimpleNamespace(info=lambda x: None, error=lambda x: None,warn=lambda x: None))
    response=SimpleNamespace(success=False,status_message=(
        'Entity pushed to spawn queue, but spawn service timed out'
        'waiting for entity to appear in simulation under the name [tb3]'))
    future=SimpleNamespace(done=lambda:True,result=lambda:response)
    def spin(node,timeout_sec):
        clock[0]+=timeout_sec
        if inserted and clock[0]>=.2:node.model_names={'tb3'}
    assert finish_spawn(node,future,.3,clock=lambda:clock[0],spin=spin,okay=lambda:True)==inserted
    assert clock[0]==pytest.approx(.2 if inserted else .3)


def test_other_entity_queued_timeout_cannot_confirm_our_spawn():
    node=SimpleNamespace(entity='tb3',model_names={'tb3'},
        get_logger=lambda: SimpleNamespace(error=lambda x:None))
    response=SimpleNamespace(success=False,status_message=(
        'Entity pushed to spawn queue, but spawn service timed out'
        'waiting for entity to appear in simulation under the name [tb2]'))
    future=SimpleNamespace(done=lambda:True,result=lambda:response)
    assert not finish_spawn(node,future,1.,clock=lambda:0.,okay=lambda:True)
