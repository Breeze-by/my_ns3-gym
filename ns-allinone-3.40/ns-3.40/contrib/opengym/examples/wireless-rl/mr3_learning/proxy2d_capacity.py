"""Bounded one/four-env uniform-action collection; no policy or optimizer."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import gzip
import hashlib
import json
import os
from pathlib import Path
import random
import resource
import signal
import sys
import threading
import time

from .env import MR3Env
from .proxy2d import ProxySupervisor
from .proxy2d_codec import canonical_bytes, tensor_proofs

CELLS = [(scene, seed) for scene in ("open", "rooms", "corridors") for seed in (101, 103)]


def activity_spec(kind):
    if kind == "full_behavior":
        return {"schema": "mr3-proxy2d-activity-spec-v1", "kind": kind,
                "groups": [3], "cells": [["open", 101], ["rooms", 101], ["corridors", 101]],
                "worker_cells": [[[["open", 101]], [["rooms", 101]], [["corridors", 101]]]],
                "steps_per_episode": 300, "max_attempts": 900, "activity_seconds": 3600}
    if kind not in ("profile", "short_capacity"):
        raise ValueError("unknown bounded proxy activity kind")
    return {"schema": "mr3-proxy2d-activity-spec-v1", "kind": kind,
            "groups": [1] if kind == "profile" else [1, 4],
            "cells": [["open", 101]] if kind == "profile" else [list(cell) for cell in CELLS],
            "steps_per_episode": 8, "max_attempts": 8 if kind == "profile" else 240,
            "activity_seconds": 600 if kind == "profile" else 1800}


def validate_activity_spec(spec):
    if not isinstance(spec, dict) or canonical_bytes(spec) != canonical_bytes(activity_spec(spec.get("kind"))):
        raise ValueError("bounded proxy activity must match one exact fixed specification")
    return spec


class StepBudget:
    def __init__(self, deadline_ns, maximum=9000):
        self.deadline_ns, self.maximum = deadline_ns, maximum
        self.attempts = self.returns = self.errors = 0
        self.lock, self.stop = threading.Lock(), threading.Event()

    def reserve(self, *, deadline_ns=None):
        with self.lock:
            limit = self.deadline_ns if deadline_ns is None else min(self.deadline_ns, deadline_ns)
            if self.stop.is_set() or self.attempts >= self.maximum or time.monotonic_ns() + 45_000_000_000 >= limit:
                return False
            self.attempts += 1
            return self.attempts

    def returned(self):
        with self.lock:
            self.returns += 1

    def failed(self):
        with self.lock:
            self.errors += 1
            self.stop.set()


class Trace:
    def __init__(self, directory, env_id, episode_index, epoch):
        self.directory = directory
        self.env_id, self.episode_index, self.epoch = env_id, episode_index, epoch
        self.stream = gzip.open(directory / "trace.jsonl.gz", "wt", compresslevel=1)
        self.sequence = 0

    def record(self, event, **fields):
        self.sequence += 1
        self.stream.write(json.dumps({"schema": "mr3-proxy2d-trace-v1", "event": event,
            "env_id": self.env_id, "episode_index": self.episode_index, "epoch": self.epoch,
            "event_sequence": self.sequence, "proxy_only": True, **fields}, separators=(",", ":"), allow_nan=False) + "\n")
        self.stream.flush()
        if event == "step_attempt":
            os.fsync(self.stream.fileno())

    def actor(self, event, payload, observation, **fields):
        encoded = canonical_bytes(payload["proxy_actor_inputs"])
        digest = hashlib.sha256(encoded).hexdigest()
        relative = Path("inputs") / (digest + ".json.gz")
        path = self.directory / relative
        path.parent.mkdir(exist_ok=True)
        if not path.exists():
            with gzip.open(path, "wb", compresslevel=1) as stream:
                stream.write(encoded)
        self.record(event, actor_input_ref={"path": str(relative), "sha256": digest},
            snapshot=payload["snapshot"], tensor_proofs=tensor_proofs(observation),
            reward=payload["reward"], dt=payload["info"]["dt"], physical_dt=payload["info"]["physical_dt"],
            terminated=payload["terminated"], truncated=payload["truncated"], reason=payload["info"]["reason"],
            reward_diagnostics=payload["info"]["reward_diagnostics"], **fields)

    def close(self):
        self.stream.close()


def collect_worker(group, env_id, budget, freeze, *, cells=None, steps_per_episode=300,
                   group_deadline_ns=None, profile=False):
    root = group / f"worker{env_id}"
    supervisor = ProxySupervisor(root, env_id=env_id, **({"profile": True} if profile else {}))
    env = MR3Env(supervisor=supervisor, max_steps=steps_per_episode)
    local_deadline = budget.deadline_ns if group_deadline_ns is None else min(budget.deadline_ns, group_deadline_ns)
    action_seed = 41 + 1_000_003 * env_id
    rng, episodes, error = random.Random(action_seed), [], None
    try:
        for episode_index, (scene, seed) in enumerate(CELLS if cells is None else cells, 1):
            if budget.stop.is_set() or time.monotonic_ns() + 90_000_000_000 >= local_deadline:
                break
            trace, directory = None, None
            begun = time.monotonic_ns()
            attempted = False
            descriptor = {"env_id": env_id, "episode_index": episode_index, "scene": scene,
                          "seed": seed, "action_seed": action_seed}
            try:
                observation, _ = env.reset(seed=seed, options={"scene": scene})
                directory = supervisor.directory
                descriptor["directory"] = str(directory)
                metadata_path = directory / "episode.json"
                metadata = json.loads(metadata_path.read_text())
                metadata.update(freeze=freeze, action_seed=action_seed,
                                action_stream=("per-group/env continuous across declared six cells" if cells is None
                                               else "per-group/env continuous across declared cells"))
                metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")
                trace = Trace(directory, env_id, episode_index, env._snapshot["epoch"])
                trace.actor("reset", supervisor.last_result, observation,
                            started_wall_ns=begun, ended_wall_ns=time.monotonic_ns())
                for _ in range(steps_per_episode):
                    ticket = budget.reserve() if group_deadline_ns is None else budget.reserve(deadline_ns=local_deadline)
                    if not ticket:
                        break
                    mask = env.action_masks().tolist()
                    action = rng.choice([index for index, valid in enumerate(mask) if valid])
                    started = time.monotonic_ns()
                    trace.record("step_attempt", global_attempt=ticket, action=action,
                        joint_action_mask=mask, preceding_digest=env._snapshot["digest"],
                        candidate_version=env._snapshot["candidate_version"], started_wall_ns=started)
                    attempted = True
                    try:
                        observation, _, terminated, truncated, _ = env.step(action)
                    except Exception as exc:
                        budget.failed()
                        trace.record("step_error", action=action, started_wall_ns=started,
                                     ended_wall_ns=time.monotonic_ns(), error=repr(exc))
                        attempted = False
                        raise
                    budget.returned()
                    trace.actor("step_return", supervisor.last_result, observation, action=action,
                                started_wall_ns=started, ended_wall_ns=time.monotonic_ns())
                    attempted = False
                    if terminated or truncated:
                        descriptor.update(reason=supervisor.last_result["info"]["reason"],
                                          terminated=terminated, truncated=truncated)
                        if terminated and descriptor["reason"] not in ("coverage_reached", "timeout"):
                            budget.stop.set()
                            if cells is not None:
                                error = "unsafe_terminal: " + str(descriptor["reason"])
                                descriptor["error"] = error
                        break
            except Exception as exc:
                error = repr(exc)
                budget.stop.set()
                descriptor["error"] = error
                directory = supervisor.directory
                if directory is not None:
                    descriptor["directory"] = str(directory)
                    (directory / "runner_failure.json").write_text(json.dumps({"error": error,
                        "step_attempt_in_flight": attempted, "freeze": freeze}, indent=2) + "\n")
            finally:
                try:
                    env.close()
                except Exception as exc:
                    error = error or repr(exc)
                    descriptor["close_error"] = repr(exc)
                    budget.stop.set()
                if trace is not None:
                    trace.record("close", started_wall_ns=time.monotonic_ns(), ended_wall_ns=time.monotonic_ns(),
                                 closed=supervisor.process is None, error=descriptor.get("close_error"))
                    trace.close()
                if directory is not None:
                    descriptor["directory"] = str(directory)
                descriptor["started_ns"], descriptor["ended_ns"] = begun, time.monotonic_ns()
                episodes.append(descriptor)
            if error or budget.stop.is_set():
                break
            # MR3Env.close is final for one Gym instance; a new one reuses only
            # the supervisor's counters, never any backend process/state.
            env = MR3Env(supervisor=supervisor, max_steps=steps_per_episode)
    finally:
        env.close()
    return {"env_id": env_id, "episodes": episodes, "error": error,
            "saved_identities": supervisor.identities}


def collect(run, freeze, source_bindings, conformity_ref, activity_started_ns, deadline_ns, *,
            activity_spec=None, group_wall_seconds=None, profile=False, collection_deadline_ns=None):
    if type(profile) is not bool:
        raise ValueError("profile flag must be boolean")
    if activity_spec is None:
        if profile or group_wall_seconds is not None or collection_deadline_ns is not None:
            raise ValueError("explicit performance flags require a bounded activity specification")
        collection_deadline = min(deadline_ns - 900_000_000_000, time.monotonic_ns() + 1_800_000_000_000)
        groups_expected, cells, steps, maximum = [1, 4], CELLS, 300, 9000
    else:
        validate_activity_spec(activity_spec)
        kind = activity_spec["kind"]
        expected_walls = [240] if kind == "profile" else [2100] if kind == "full_behavior" else [400, 800]
        if canonical_bytes(group_wall_seconds) != canonical_bytes(expected_walls) or profile != (kind == "profile"):
            raise ValueError("activity group wall reservations/profile flag differ from the fixed specification")
        if (type(deadline_ns) is not int or type(activity_started_ns) is not int
                or deadline_ns - activity_started_ns != activity_spec["activity_seconds"] * 10**9):
            raise ValueError("activity deadline differs from the exact bounded specification")
        collection_started = time.monotonic_ns()
        collection_seconds = 240 if profile else 2100 if kind == "full_behavior" else 1200
        collection_deadline = collection_started + collection_seconds * 10**9
        if collection_deadline > deadline_ns - 120 * 10**9:
            raise ValueError("collection reservation lacks the required remaining activity tail")
        if collection_deadline_ns is not None and collection_deadline_ns != collection_deadline:
            raise ValueError("collection deadline differs from the fixed reservation")
        groups_expected, cells = activity_spec["groups"], activity_spec["cells"]
        steps, maximum = activity_spec["steps_per_episode"], activity_spec["max_attempts"]
    budget = StepBudget(collection_deadline, maximum=maximum)
    previous_handler = signal.signal(signal.SIGINT, lambda *_: budget.stop.set())
    groups, all_errors, identities = [], [], []
    for group_index, workers in enumerate(groups_expected):
        group = run / "stages" / f"group{workers}"
        group.mkdir(parents=True, exist_ok=False)
        started = time.monotonic_ns()
        local_deadline = (collection_deadline if activity_spec is None else
                          min(collection_deadline, started + group_wall_seconds[group_index] * 10**9))
        results = []
        if not budget.stop.is_set() and started + 90_000_000_000 < local_deadline:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                kwargs = {} if activity_spec is None else {"cells": cells, "steps_per_episode": steps,
                    "group_deadline_ns": local_deadline, "profile": profile}
                futures = []
                for index in range(workers):
                    worker_kwargs = kwargs
                    if activity_spec is not None and activity_spec["kind"] == "full_behavior":
                        worker_kwargs = {**kwargs, "cells": activity_spec["worker_cells"][group_index][index]}
                    futures.append(executor.submit(collect_worker, group, index, budget, freeze, **worker_kwargs))
                for future in as_completed(futures):
                    try:
                        results.append(future.result())
                    except Exception as error:
                        budget.stop.set()
                        all_errors.append(repr(error))
        episodes = [episode for result in results for episode in result["episodes"]]
        all_errors.extend(result["error"] for result in results if result["error"])
        identities.extend(identity for result in results for identity in result["saved_identities"])
        groups.append({"workers": workers, "started_ns": started, "ended_ns": time.monotonic_ns(),
                       "episodes": sorted(episodes, key=lambda e: (e["env_id"], e["episode_index"]))})
        if activity_spec is not None:
            groups[-1].update(deadline_ns=local_deadline, wall_budget_seconds=group_wall_seconds[group_index])
        if budget.stop.is_set():
            break
    summary = {"schema": "mr3-proxy2d-capacity-summary-v1", "freeze": freeze,
        "source_bindings": source_bindings, "conformity": conformity_ref,
        "activity_started_ns": activity_started_ns, "activity_deadline_ns": deadline_ns,
        "collection_deadline_ns": collection_deadline, "groups": groups,
        "scheduled_cells": [list(cell) for cell in cells],
        "step_attempts": budget.attempts, "step_returns": budget.returns, "step_errors": budget.errors,
        "policy_calls": 0, "gpu_calls": 0, "optimizer_steps": 0, "closed": True,
        "qualification": False, "training_eligible": False, "native_credit": False,
        "errors": all_errors, "collection_ended_ns": time.monotonic_ns(),
        "max_rss_children_kib": resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
        "saved_identities": identities,
        "forbidden_framework_imports": [name for name in ("torch", "stable_baselines3", "sb3_contrib") if name in sys.modules],
        "scope": "short uniform-action proxy capacity, not qualified training throughput"}
    if activity_spec is not None:
        summary.update(activity_spec=activity_spec, activity_kind=activity_spec["kind"], profile_enabled=profile,
                       collection_started_ns=collection_started)
        if activity_spec["kind"] == "full_behavior":
            summary["scope"] = "bounded full-duration uniform-action proxy behavior; no training or native qualification"
    (run / "capacity_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    signal.signal(signal.SIGINT, previous_handler)
    return summary
