import json

from multi_robot_exploration.task_visualizer import (
    disc_sdf,
    rally_markers,
    ring_sdf,
)


def test_disc_sdf_is_visual_only():
    sdf = disc_sdf(1.25, (0.1, 0.2, 0.3, 0.4))

    assert "<radius>1.25</radius>" in sdf
    assert "<collision" not in sdf
    assert "0.1 0.2 0.3 0.4" in sdf


def test_rally_markers_are_sorted_and_numeric():
    payload = json.dumps(
        {
            "poses": {
                "tb2": {"x": 2, "y": "3.5", "yaw": 0.0},
                "tb1": {"x": -1, "y": 0, "yaw": 1.0},
            }
        }
    )

    assert rally_markers(payload) == [
        ("tb1", -1.0, 0.0),
        ("tb2", 2.0, 3.5),
    ]


def test_ring_sdf_is_an_opaque_visual_boundary_without_collision():
    sdf = ring_sdf(1.0, (0.05, 0.3, 1.0, 1.0))

    assert sdf.count("<visual name=") == 48
    assert "<collision" not in sdf
    assert "0.05 0.3 1.0 1.0" in sdf
