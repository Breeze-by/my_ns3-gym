#!/usr/bin/env python3
"""Reproduce frozen MR3 holdout layouts without running any policy or simulator."""

import argparse
import hashlib
import json
from pathlib import Path
import random


GENERATOR_VERSION = "mr3_box_layouts_v1"
ROI_BOUNDS = [-7.1, -5.1, 7.1, 5.1]
LAYOUTS = {
    "validation": {"rooms": 701, "corridors": 702, "open": 703},
    "test": {"rooms": 901, "corridors": 902, "open": 903},
    "confirmation": {"rooms": 1101, "corridors": 1102, "open": 1103},
}


def layout_boxes(layout_seed, family):
    """Construct connected rooms with fixed spawn clearance and full outer walls."""
    rng = random.Random(layout_seed)
    boxes = [("north", 0, 5, 14.2, .2, 0),
             ("south", 0, -5, 14.2, .2, 0),
             ("east", 7, 0, .2, 10.2, 0),
             ("west", -7, 0, .2, 10.2, 0)]

    def vertical_door(name, x, door_y, width):
        low, high = door_y-width/2, door_y+width/2
        boxes.extend([(name+"_lower", x, (-5+low)/2, .2, low+5, 0),
                      (name+"_upper", x, (high+5)/2, .2, 5-high, 0)])

    def horizontal_door(name, x0, x1, y, door_x, width):
        low, high = door_x-width/2, door_x+width/2
        boxes.extend([(name+"_west", (x0+low)/2, y, low-x0, .2, 0),
                      (name+"_east", (high+x1)/2, y, x1-high, .2, 0)])

    if family == "rooms":
        left = -3 + .25*rng.randint(-2, 2)
        right = 3 + .25*rng.randint(-2, 2)
        vertical_door("left_partition", left, .3*rng.randint(-2, 2), 1.6)
        vertical_door("right_partition", right, .3*rng.randint(-2, 2), 1.6)
        horizontal_door("left_room", -7, left, .3*rng.randint(-3, 3),
                        (-7+left)/2 + .2*rng.randint(-2, 2), 1.6)
        horizontal_door("right_room", right, 7, .3*rng.randint(-3, 3),
                        (right+7)/2 + .2*rng.randint(-2, 2), 1.6)
        boxes.extend([("north_cabinet", .2*rng.randint(-3, 3), 3.5, 1.3, .7, 0),
                      ("south_cabinet", .2*rng.randint(-3, 3), -3.5, 1.3, .7, 0)])
    elif family == "corridors":
        left = -2.3 + .2*rng.randint(-1, 1)
        right = 2.3 + .2*rng.randint(-1, 1)
        top = 3 + .2*rng.randint(-2, 2)
        bottom = -3 + .2*rng.randint(-2, 2)
        boxes.extend([("left_spine", left, (-5+top)/2, .2, top+5, 0),
                      ("right_spine", right, (bottom+5)/2, .2, 5-bottom, 0)])
        horizontal_door("left_branch", -7, left, -1.5+.2*rng.randint(-2, 2),
                        -5.0+.2*rng.randint(-2, 2), 1.6)
        horizontal_door("right_branch", right, 7, 1.5+.2*rng.randint(-2, 2),
                        5.0+.2*rng.randint(-2, 2), 1.6)
        boxes.append(("central_cabinet", .2*rng.randint(-2, 2), 3.8, 1.0, .6, 0))
    elif family == "open":
        for index, (sx, sy) in enumerate(((-1, -1), (-1, 1), (1, -1), (1, 1))):
            boxes.append((f"island_{index}", sx*(3.5+.2*rng.randint(-2, 2)),
                          sy*(2.6+.2*rng.randint(-2, 2)),
                          .9+.1*rng.randint(-2, 2), .9+.1*rng.randint(-2, 2), 0))
        boxes.extend([("north_bar", .3*rng.randint(-2, 2), 3.5, 2.4, .4,
                       .15*rng.randint(-2, 2)),
                      ("south_bar", .3*rng.randint(-2, 2), -3.5, 2.4, .4,
                       .15*rng.randint(-2, 2))])
    else:
        raise ValueError(f"Unknown MR3 layout family: {family}")
    return boxes


def render_world(split, family, layout_seed):
    """Return reproducible canonical SDF bytes for one eval-only layout."""
    if split not in LAYOUTS or LAYOUTS[split].get(family) != layout_seed:
        raise ValueError("Use a declared split/family/layout_seed combination")
    name = f"mr3_{split}_{family}"
    lines = ["<sdf version='1.7'>", f"  <world name='{name}'>",
             f"    <!-- {GENERATOR_VERSION}; layout_seed={layout_seed}; eval-only. -->",
             "    <plugin name='gazebo_ros_state' filename='libgazebo_ros_state.so'>",
             "      <ros><namespace>/gazebo</namespace></ros><update_rate>10.0</update_rate>",
             "    </plugin>", "    <include><uri>model://sun</uri></include>",
             "    <include><uri>model://ground_plane</uri></include>",
             "    <gravity>0 0 -9.8</gravity><physics type='ode'>",
             "      <max_step_size>0.001</max_step_size><real_time_factor>1</real_time_factor>",
             "      <real_time_update_rate>1000</real_time_update_rate></physics>",
             "    <model name='task_geometry'><static>true</static><link name='boxes'>"]
    for identifier, x, y, sx, sy, yaw in layout_boxes(layout_seed, family):
        pose = f"{x:.6f} {y:.6f} 1 0 0 {yaw:.6f}"
        geometry = f"<geometry><box><size>{sx:.6f} {sy:.6f} 2</size></box></geometry>"
        lines.extend([f"      <collision name='{identifier}'><pose>{pose}</pose>",
                      f"        {geometry}</collision>",
                      f"      <visual name='{identifier}_visual'><pose>{pose}</pose>",
                      f"        {geometry}</visual>"])
    lines.extend(["    </link></model>", "  </world>", "</sdf>"])
    return ("\n".join(lines) + "\n").encode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path,
                        default=Path(__file__).resolve().parents[1]/"src/multi_robot/worlds")
    parser.add_argument("--check", action="store_true", help="Verify frozen files without writing")
    args = parser.parse_args()
    receipt = {"generator_version": GENERATOR_VERSION,
               "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "roi_bounds": ROI_BOUNDS, "policy_runs": 0, "simulator_runs": 0, "layouts": []}
    for split, families in LAYOUTS.items():
        for family, seed in families.items():
            payload = render_world(split, family, seed)
            path = args.output_dir/f"mr3_{split}_{family}.world"
            if args.check:
                if not path.exists() or path.read_bytes() != payload:
                    raise ValueError(f"Frozen layout differs or is missing: {path}")
            elif path.exists():
                if path.read_bytes() != payload:
                    raise ValueError(f"Refusing to replace changed frozen layout: {path}")
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("xb") as stream:
                    stream.write(payload)
            receipt["layouts"].append({"split": split, "family": family,
                                       "layout_seed": seed, "world_file": path.name,
                                       "world_sha256": hashlib.sha256(payload).hexdigest(),
                                       "task_seeds": list(range(seed*100+1, seed*100+11))})
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
