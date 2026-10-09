#!/usr/bin/env python3
"""Keep the frozen staging stimulus, waiting for a real Nav2 map first."""
import argparse
import hashlib
import json
import math
from pathlib import Path

from nav_msgs.msg import OccupancyGrid
import rclpy.action
from rclpy.action import ActionClient

import stage_p3b5_return_probe as original


def nav2_map_ready(grid, positions, now):
    if grid is None or grid.header.frame_id != "map":
        return False
    stamp=grid.header.stamp.sec+grid.header.stamp.nanosec*1e-9
    info=grid.info
    orientation=info.origin.orientation
    values=(now,stamp,info.resolution,info.origin.position.x,info.origin.position.y,
            orientation.x,orientation.y,orientation.z,orientation.w)
    if (not all(math.isfinite(v) for v in values) or not 0<=now-stamp<=2.
            or info.resolution<=0 or info.width<=0 or info.height<=0
            or len(grid.data)!=info.width*info.height
            or any(abs(v)>1e-6 for v in (orientation.x,orientation.y,orientation.z))
            or abs(abs(orientation.w)-1.)>1e-6):
        return False
    for x,y in positions:
        column=math.floor((x-info.origin.position.x)/info.resolution)
        row=math.floor((y-info.origin.position.y)/info.resolution)
        if not (0<=row<info.height and 0<=column<info.width):
            return False
    return True


def main():
    parser=argparse.ArgumentParser(add_help=False)
    parser.add_argument("--config",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    arguments,_=parser.parse_known_args()
    config=json.loads(arguments.config.read_text())
    assert hashlib.sha256(Path(original.__file__).read_bytes()).hexdigest()==config["staging_base_content_sha256"]
    positions=[pose[:2] for pose in config["return_staging"]["poses"].values()]
    evidence=arguments.output.with_name("nav2_readiness.jsonl")
    assert not evidence.exists()

    class ReadyStagingClient(ActionClient):
        def __init__(self,node,action_type,action_name):
            super().__init__(node,action_type,action_name)
            self.task_node=node
            self.robot=action_name.split("/")[2]
            self.grid=None
            self.last_ready=None
            self.map_subscription=node.create_subscription(OccupancyGrid,
                f"/{self.robot}/global_costmap/costmap",lambda message:setattr(self,"grid",message),1)

        def server_is_ready(self):
            now=self.task_node.get_clock().now().nanoseconds*1e-9
            ready=super().server_is_ready() and nav2_map_ready(self.grid,positions,now)
            if ready or ready!=self.last_ready:
                self.last_ready=ready
                row=dict(event="nav2_staging_readiness",robot=self.robot,observer_time=now,ready=ready)
                if self.grid is not None:
                    info=self.grid.info
                    row.update(map_header_time=self.grid.header.stamp.sec+self.grid.header.stamp.nanosec*1e-9,
                        frame=self.grid.header.frame_id,width=info.width,height=info.height,
                        resolution=info.resolution,origin=[info.origin.position.x,info.origin.position.y],
                        data_length=len(self.grid.data),
                        orientation=[info.origin.orientation.x,info.origin.orientation.y,
                                     info.origin.orientation.z,info.origin.orientation.w])
                with evidence.open("a") as output:
                    output.write(json.dumps(row,allow_nan=False)+"\n")
            return ready

    # The frozen fixture imports ActionClient inside main. Scope this adapter
    # to this single-process fixture invocation and restore it on every exit.
    rclpy.action.ActionClient=ReadyStagingClient
    try:
        return original.main()
    finally:
        rclpy.action.ActionClient=ActionClient


if __name__=="__main__":
    raise SystemExit(main())
