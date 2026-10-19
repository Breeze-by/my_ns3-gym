import hashlib
import json
from pathlib import Path
import runpy
import subprocess
from types import SimpleNamespace

import pytest

from multi_robot_exploration.mr3_task_contract import (
    diagnose_contract_geometry,
    inspect_world_geometry,
    load_contract_truth,
    load_task_contract,
)


ROS_ROOT = Path(__file__).resolve().parents[3]
GENERATOR_PATH = ROS_ROOT / "scripts/generate_mr3_worlds.py"
GENERATOR = SimpleNamespace(**runpy.run_path(str(GENERATOR_PATH)))
WORLD_DIR = ROS_ROOT / "src/multi_robot/worlds"


def test_frozen_worlds_are_byte_reproducible_and_distinct_geometries():
    geometries, seeds = set(), set()
    for split, families in GENERATOR.LAYOUTS.items():
        for family, seed in families.items():
            assert seed not in seeds
            seeds.add(seed)
            geometry = tuple(GENERATOR.layout_boxes(seed, family))
            assert geometry not in geometries
            geometries.add(geometry)
            payload = GENERATOR.render_world(split, family, seed)
            assert payload == GENERATOR.render_world(split, family, seed)
            assert payload == (WORLD_DIR/f"mr3_{split}_{family}.world").read_bytes()
    assert len(geometries) == 9


@pytest.mark.parametrize("split,family,seed", [
    (split, family, seed) for split, families in GENERATOR.LAYOUTS.items()
    for family, seed in families.items()
])
def test_holdout_static_task_geometry_is_valid_without_policy_runs(
        tmp_path, split, family, seed):
    world = WORLD_DIR/f"mr3_{split}_{family}.world"
    _, audit = inspect_world_geometry(world)
    assert audit["unsupported_collision_count"] == 0
    # Reuse the already predeclared physical task gates; only the layout identity changes.
    data = json.loads((ROS_ROOT/"src/multi_robot/config/mr3_p1a/open.json").read_text())
    data["world_file"] = world.name
    data["world_sha256"] = hashlib.sha256(world.read_bytes()).hexdigest()
    data["roi"]["bounds"] = GENERATOR.ROI_BOUNDS
    data["roi"]["rationale"] = "Complete outer-wall envelope of frozen heldout box room"
    data["split_role"] = "static_check_only; no policy run"
    path = tmp_path/"holdout_static_contract.json"
    path.write_text(json.dumps(data))
    contract = load_task_contract(path, world)
    report = diagnose_contract_geometry(load_contract_truth(world, contract), contract)
    assert report["free_component_count"] == 1
    assert report["traversable_center_component_count"] == 1
    assert all(entry["traversable"] for entry in report["starts"].values())
    assert report["visible_free_fraction_lower_bound"] >= .95
    assert report["denominator_trimmed_by_diagnostic"] is False


def test_generator_check_refuses_changed_holdout_without_overwriting(tmp_path):
    output = tmp_path/"worlds"
    result = subprocess.run(["/usr/bin/python3", str(GENERATOR_PATH),
                             "--output-dir", str(output)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    receipt = json.loads(result.stdout)
    assert receipt["policy_runs"] == receipt["simulator_runs"] == 0
    assert receipt["layouts"][0]["task_seeds"] == list(range(70101, 70111))
    target = output/"mr3_validation_rooms.world"
    original = target.read_bytes()
    target.write_bytes(original.replace(b"14.200000", b"14.300000"))
    changed = target.read_bytes()
    for flags in ([], ["--check"]):
        result = subprocess.run(["/usr/bin/python3", str(GENERATOR_PATH),
                                 "--output-dir", str(output), *flags],
                                capture_output=True, text=True)
        assert result.returncode != 0
        assert target.read_bytes() == changed


def test_generator_rejects_relabeling_a_seed_as_a_different_split():
    with pytest.raises(ValueError, match="declared split"):
        GENERATOR.render_world("test", "rooms", 701)
