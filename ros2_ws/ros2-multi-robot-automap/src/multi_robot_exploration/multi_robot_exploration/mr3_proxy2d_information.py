"""Node-free access to the existing ideal map bridge for the 2D proxy.

Run under system ROS Python. Importing ROS messages is intentional; this module
does not initialize rclpy, create a Node, or reimplement map composition. The
same bridge methods, full-message serialization, transport and stores execute
on an explicitly clocked container. Synchronous futures replace only scheduling.
These local fixture deliveries do not supply DDS/native/network evidence.
"""

from concurrent.futures import Future
import copy
import json
import math
from types import SimpleNamespace

import numpy as np

from multi_robot_exploration.mr3_information import (
    IdealInformation, map_payload, state_payload,
)
from multi_robot_exploration.mr3_observation import build_snapshot
from multi_robot_exploration.mr3_transport import IdealTransport, ReceivedStore


ROBOTS = ("tb1", "tb2", "tb3")


class _Publication:
    """Capture the actual publish argument without a ROS publisher or history."""

    def __init__(self):
        self.latest = None

    def publish(self, message):
        self.latest = copy.deepcopy(message)


class _SynchronousExecutor:
    def submit(self, operation, *args):
        future = Future()
        try:
            future.set_result(operation(*args))
        except Exception as error:
            future.set_exception(error)
        return future


class ProxyInformation:
    """Reuse the actual map bridge, with explicit ideal source/delivery calls.

    ``receive_local_map`` admits only a robot's own simulated sensor map.
    ``publish_maps`` then invokes the original explicit uplink/merge/downlink
    path; a raw callback alone never advances hub or peer navigation evidence.
    ``transport``/``received`` expose the original state Envelope path as well.
    New episodes require a new instance, including stores and source sequences.
    """

    now = IdealInformation.now
    receive_local_map = IdealInformation.receive_local_map
    publish_maps = IdealInformation.publish_maps
    submit_map_job = IdealInformation.submit_map_job
    finish_maps = IdealInformation.finish_maps
    publish_navigation_map = IdealInformation.publish_navigation_map

    def __init__(self, epoch):
        # Epoch validation is delegated to the actual transport/store classes.
        self.names, self.epoch = ROBOTS, epoch
        self.transport, self.received = IdealTransport(epoch), ReceivedStore(epoch)
        self.edges = {name: ReceivedStore(epoch) for name in ROBOTS}
        self.downlinks = {name: IdealTransport(epoch) for name in ROBOTS}
        self.local_maps, self.local_map_versions = {}, {}
        self.navigation_maps, self.navigation_sources = {}, {}
        self.received_map_digests, self.published_map_records = {}, {}
        self.navigation_publishers = {name: _Publication() for name in ROBOTS}
        self.received_map_publishers = {name: _Publication() for name in ROBOTS}
        self.map_publisher, self.map_metadata_publisher = _Publication(), _Publication()
        self.map_failure_publisher = _Publication()
        self.map_executor = _SynchronousExecutor()
        self.map_future, self.queued_map_job = None, None
        self.map_signature, self.hub_map, self.map_payload_sha256 = None, None, None
        self.hub_map_source_stamp, self.hub_map_received_stamp = None, None
        self.map_version, self.state_sequence = 0, 0
        self.map_diagnostics = {
            "submitted": 0, "completed": 0, "replaced_queued": 0,
            "capture_wall_sec": 0., "publish_wall_sec": 0.,
            "worker_wall_sec": 0., "state_wall_sec": 0.,
        }
        self.clock_ns, self.last_now, self.clock_failed = 0, None, False
        self.errors = []

    def get_clock(self):
        return SimpleNamespace(now=lambda: SimpleNamespace(nanoseconds=self.clock_ns))

    def get_logger(self):
        return SimpleNamespace(error=self.errors.append)

    def set_time(self, now):
        value = float(now)
        if not math.isfinite(value) or value < 0:
            raise ValueError("proxy information time must be finite and nonnegative")
        self.clock_ns = round(value * 1_000_000_000)

    def send_estimated_state(self, name, odometry, transform, *, tf_validity_lead_sec=0.):
        """Queue the existing complete estimated-state payload; no implicit receipt.

        The caller owns odom/TF generation. This method never accepts evaluator
        state and never claims real ROS safety/status/phase publication.
        """
        if name not in ROBOTS:
            raise ValueError("proxy information requires tb1/tb2/tb3")
        now = self.now()
        if now is None:
            raise ValueError("estimated-state send requires a positive monotonic clock")
        payload = state_payload(name, odometry, transform, tf_validity_lead_sec)
        sources = (payload["odom_source_stamp"], payload["tf_source_stamp"])
        if (min(sources) < 0 or max(round(value * 1e9) for value in sources) > self.clock_ns
                or not all(math.isfinite(payload[key]) for key in ("x", "y", "yaw", "v", "w"))):
            raise ValueError("estimated-state sources must be finite and causal")
        return self.transport.send("state", name, payload,
                                   source_stamp=min(sources), now=now)

    def deliver(self):
        """Explicitly service existing ideal uplink queues at the selected clock."""
        now = self.now()
        if now is None:
            raise ValueError("delivery requires a positive monotonic clock")
        return self.transport.deliver(self.received, now, sampled=True)

    @staticmethod
    def _raster(message, metadata):
        return {
            "grid": np.asarray(message.data, dtype=np.int16).reshape(
                message.info.height, message.info.width).copy(),
            "resolution": message.info.resolution,
            "origin": (message.info.origin.position.x, message.info.origin.position.y),
            **copy.deepcopy(metadata),
        }

    def snapshot_inputs(self):
        """Detach the same delivered maps/metadata supplied to the native adapter.

        Require all three actual received own maps and navigation compositions;
        startup cannot silently select the fused-map legacy observation API.
        """
        if (self.clock_failed or self.map_failure_publisher.latest is not None
                or self.hub_map is None or self.map_metadata_publisher.latest is None):
            raise ValueError("proxy information has no healthy completed map bundle")
        metadata = json.loads(self.map_metadata_publisher.latest.data)
        maps, navigation = {}, {}
        for name in ROBOTS:
            own = self.received_map_publishers[name].latest
            nav = self.navigation_publishers[name].latest
            if (own is None or nav is None or name not in metadata["map_sources"]
                    or name not in metadata["navigation_sources"]):
                raise ValueError("all three delivered own/navigation maps are required")
            maps[name] = self._raster(own, {"epoch": self.epoch, **metadata["map_sources"][name]})
            navigation[name] = self._raster(nav, {
                "epoch": self.epoch, **metadata["navigation_sources"][name]})
        hub = self.hub_map
        return {
            "raw_grid": np.asarray(hub.data, dtype=np.int16).reshape(
                hub.info.height, hub.info.width).copy(),
            "resolution": hub.info.resolution,
            "origin": (hub.info.origin.position.x, hub.info.origin.position.y),
            "map_version": metadata["map_version"],
            "map_source_stamp": metadata["map_source_stamp"],
            "map_received_stamp": metadata["map_received_stamp"],
            "map_sources": copy.deepcopy(metadata["map_sources"]),
            "robot_maps": maps, "navigation_maps": navigation,
        }

    def snapshot_payloads(self):
        """Original complete message payloads, for detached snapshot archives."""
        self.snapshot_inputs()  # Apply the same actual-delivery readiness gate.
        return {"fused": map_payload(self.hub_map),
                **{name: map_payload(self.received_map_publishers[name].latest) for name in ROBOTS},
                **{"navigation:" + name: map_payload(self.navigation_publishers[name].latest)
                   for name in ROBOTS}}

    def build_snapshot(self, robots, now, sequence, *, task_start=None):
        """Invoke the original navigation-map staging-v5 snapshot builder."""
        inputs = self.snapshot_inputs()
        return build_snapshot(
            inputs.pop("raw_grid"), inputs.pop("resolution"), inputs.pop("origin"),
            robots, now, self.epoch, inputs.pop("map_version"), sequence,
            task_start=task_start, **inputs)
