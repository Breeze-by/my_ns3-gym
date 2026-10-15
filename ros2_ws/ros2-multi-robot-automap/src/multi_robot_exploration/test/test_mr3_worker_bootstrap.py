"""A visible ROS node cannot substitute for delivery before physical pause."""

import copy
import importlib.util
from pathlib import Path
import sys
from unittest.mock import patch

import pytest


SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("mr3_env_worker", SCRIPTS / "mr3_env_worker.py")
WORKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(WORKER)


def worker():
    instance = WORKER.Worker.__new__(WORKER.Worker)
    instance.epoch = "current"
    instance.monitor_ready = True
    instance.initial_inputs_ready = None
    return instance


def acknowledgement():
    return {"schema": "mr3-initial-inputs-ready-v1", "epoch": "current", "stamp": 10.,
            "state_sequence": 100, "map_payload_sha256": "a" * 64,
            "robots": [{"name": name, "source_stamp": 9.9, "received_stamp": 10.}
                       for name in ("tb1", "tb2", "tb3")]}


def test_initial_reset_does_not_pause_without_actual_delivered_input_ack():
    instance = worker()

    def wait(predicate, timeout, label):
        assert not predicate()
        raise TimeoutError(label)

    instance._wait = wait
    with patch.object(WORKER.subprocess, "Popen") as process:
        with pytest.raises(TimeoutError, match="delivered-input startup"):
            instance.reset()
        process.assert_not_called()


def test_same_epoch_ack_is_idempotent_and_does_not_release_the_task():
    instance = worker()
    value = acknowledgement()
    instance.receive_initial_inputs(value)
    instance.receive_initial_inputs(copy.deepcopy(value))
    assert instance.initial_inputs_ready == value
    assert not hasattr(instance, "start_ns")
    assert not hasattr(instance, "snapshot")


def test_previous_epoch_input_ack_cannot_unlock_reset():
    instance = worker()
    value = acknowledgement()
    value["epoch"] = "previous"
    instance.receive_initial_inputs(value)
    assert instance.initial_inputs_ready is None


@pytest.mark.parametrize("key,value", [
    ("schema", "other"), ("state_sequence", 0), ("state_sequence", True),
    ("stamp", float("nan")), ("map_payload_sha256", "a" * 63),
    ("robots", [{"name": "tb1"}]),
])
def test_invalid_delivery_ack_is_an_infrastructure_error(key, value):
    instance = worker()
    payload = acknowledgement()
    payload[key] = value
    with pytest.raises(ValueError, match="invalid initial"):
        instance.receive_initial_inputs(payload)
    assert instance.initial_inputs_ready is None


def test_future_robot_source_and_changed_same_epoch_ack_are_rejected():
    instance = worker()
    payload = acknowledgement()
    payload["robots"][0]["source_stamp"] = 10.1
    with pytest.raises(ValueError, match="source time"):
        instance.receive_initial_inputs(payload)
    instance.receive_initial_inputs(acknowledgement())
    payload = acknowledgement()
    payload["state_sequence"] += 1
    with pytest.raises(ValueError, match="changed within epoch"):
        instance.receive_initial_inputs(payload)
