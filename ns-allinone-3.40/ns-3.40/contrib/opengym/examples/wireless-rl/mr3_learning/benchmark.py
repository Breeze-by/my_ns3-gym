"""Predeclared scripted sampler/reset measurements; never policy training."""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

from .env import MR3Env
from .supervisor import InfrastructureError, Supervisor, WORKSPACE, identity_alive


def probe_action(snapshot):
    """Explicit external cancellation-stress inputs, not a mapping baseline."""
    elapsed = snapshot["task_elapsed_sec"]
    mask = snapshot["joint_action_mask"]
    if elapsed < 1.5 or 10. <= elapsed < 12.:
        def order(action):
            choices = (action // 100, action // 10 % 10, action % 10)
            paths = sum(snapshot["candidates"][choice]["path_distances_m"][index] or 0.
                        for index, choice in enumerate(choices) if choice < 8)
            return (-sum(choice < 8 for choice in choices), -paths, action)
        return min((action for action, valid in enumerate(mask) if valid), key=order)
    if elapsed >= 7.:
        return next(action for action in range(999, -1, -1) if mask[action])
    return 888


def resource_sample():
    """Host counters and driver-reported GPU data, not an attribution claim."""
    stat = Path("/proc/stat").read_text().splitlines()[0].split()[1:]
    ticks = [int(value) for value in stat]
    mem = {line.split(":", 1)[0]: int(line.split()[1]) for line in
           Path("/proc/meminfo").read_text().splitlines() if len(line.split()) >= 2}
    result = {"monotonic": time.monotonic(), "cpu_total_ticks": sum(ticks),
              "cpu_idle_ticks": ticks[3] + ticks[4], "load_average": list(os.getloadavg()),
              "mem_total_kib": mem["MemTotal"], "mem_available_kib": mem["MemAvailable"]}
    try:
        response = subprocess.run([
            "nvidia-smi", "--query-gpu=index,utilization.gpu,memory.used,memory.total",
            "--format=csv,noheader,nounits"], text=True, capture_output=True, timeout=5.)
        result["gpu"] = ([[int(value.strip()) for value in row.split(",")]
                          for row in response.stdout.splitlines()]
                         if response.returncode == 0 else [])
        result["gpu_query_returncode"] = response.returncode
    except (OSError, subprocess.TimeoutExpired) as error:
        result["gpu_query_error"] = repr(error)
    return result


def run_worker(args, worker_id):
    supervisor = Supervisor(run_id=args.run_id, worker_id=worker_id,
                            domain_id=args.base_domain + worker_id,
                            gazebo_port=args.base_port + worker_id,
                            output_root=args.output_root)
    environment = MR3Env(supervisor=supervisor, max_steps=args.steps)
    result = {"worker_id": worker_id, "episodes": [], "error": None}
    started = time.monotonic()
    try:
        for episode_index, (scene, seed) in enumerate(args.schedule):
            episode_started = time.monotonic()
            observation, info = environment.reset(seed=seed, options={"scene": scene})
            initial = supervisor.last_result["snapshot"]
            episode = {"epoch": info["epoch"], "scene": scene, "seed": seed,
                       "initial_observation_digest": info["observation_digest"],
                       "output_directory": str(supervisor.episode.directory),
                       "startup_wall_sec": info["startup_wall_sec"],
                       "initial_estimated_poses": [
                           {key: robot.get(key) for key in ("name", "x", "y", "yaw")}
                           for robot in initial["robots"]], "transitions": 0,
                       "transition_wall_sec": 0., "reward_sum": 0., "dt_values": []}
            result["episodes"].append(episode)
            for step_index in range(args.steps):
                if args.fault_probe and worker_id == 0 and episode_index == 0 and step_index == 4:
                    identity = supervisor.episode.identity
                    if not identity_alive(identity):
                        raise RuntimeError("fault target no longer matches the owned worker")
                    os.kill(identity["pid"], signal.SIGKILL)
                    try:
                        environment.step(888)
                    except InfrastructureError as error:
                        episode["expected_infrastructure_fault"] = repr(error)
                        result["fault_verified"] = True
                    else:
                        raise RuntimeError("killed worker was accepted as a valid transition")
                    break
                action = (888 if args.deadline_probe else
                          probe_action(supervisor.last_result["snapshot"]))
                step_started = time.monotonic()
                observation, reward, terminated, truncated, info = environment.step(action)
                episode["transition_wall_sec"] += time.monotonic() - step_started
                episode["transitions"] += 1
                episode["reward_sum"] += reward
                episode["dt_values"].append(info["dt"])
                if terminated or truncated:
                    episode.update(terminated=terminated, truncated=truncated,
                                   reason=info.get("reason"))
                    break
            if not environment._episode_done:
                raise RuntimeError("sampler step limit did not produce explicit truncation")
            episode["wall_sec_including_startup_and_closure"] = time.monotonic() - episode_started
    except Exception as error:
        result["error"] = repr(error)
    finally:
        try:
            environment.close()
        except Exception as error:
            result["cleanup_error"] = repr(error)
        result["wall_sec"] = time.monotonic() - started
        result["shutdown_receipts"] = supervisor.receipts
        (supervisor.directory / "worker_summary.json").write_text(
            json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, choices=(1, 2, 4), required=True)
    parser.add_argument("--schedule", default="open:101,open:101")
    parser.add_argument("--steps", type=int, default=16)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--base-domain", type=int, default=120)
    parser.add_argument("--base-port", type=int, default=12001)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--fault-probe", action="store_true")
    parser.add_argument("--deadline-probe", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.steps <= 300:
        parser.error("steps must be in [1,300]")
    try:
        args.schedule = [(part.split(":")[0], int(part.split(":")[1]))
                         for part in args.schedule.split(",")]
        if any(scene not in ("open", "rooms", "corridors") or seed < 0
               for scene, seed in args.schedule):
            raise ValueError()
    except (ValueError, IndexError):
        parser.error("schedule must be a comma-separated list of declared scene:seed pairs")
    if args.fault_probe and (args.workers != 2 or len(args.schedule) != 2 or args.steps < 8):
        parser.error("fault probe requires two workers, two episodes, at least eight steps")
    if args.deadline_probe and (
            args.workers != 1 or len(args.schedule) != 1 or args.steps != 300 or args.fault_probe):
        parser.error("deadline probe requires one worker, one 300-step episode, no injected crash")
    output_root = args.output_root or (
        WORKSPACE / "ros2_ws/ros2-multi-robot-automap/log/mr3_learning")
    directory = output_root / args.run_id
    if directory.exists():
        parser.error("run directory already exists; evidence cannot be overwritten")
    directory.mkdir(parents=True)
    resources = []
    stop = threading.Event()

    def sample_resources():
        while not stop.is_set():
            resources.append(resource_sample())
            stop.wait(1.)

    sampler = threading.Thread(target=sample_resources, name="mr3_resources", daemon=True)
    started = time.monotonic()
    metadata = {"kind": "scripted_p1c_sampling_not_rl", "workers": args.workers,
                "robots_per_worker": 3, "schedule": args.schedule, "steps_per_episode": args.steps,
                "command": sys.argv, "python": sys.executable,
                "freeze": subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=WORKSPACE, text=True).strip(),
                "base_domain": args.base_domain, "base_port": args.base_port,
                "fault_probe": args.fault_probe,
                "deadline_probe": args.deadline_probe,
                "resource_scope": "host counters include unrelated activity; GPU driver reports",
                "num_logical_cpus": os.cpu_count(),
                "cpu_affinity_count": len(os.sched_getaffinity(0))}
    (directory / "benchmark_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    results = []
    sampler.start()
    try:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(run_worker, args, worker_id): worker_id
                       for worker_id in range(args.workers)}
            for future in as_completed(futures):
                try:
                    results.append(future.result())
                except Exception as error:
                    results.append({"worker_id": futures[future], "episodes": [],
                                    "shutdown_receipts": [], "error": repr(error)})
    finally:
        stop.set()
        sampler.join(timeout=10.)
        (directory / "resources.json").write_text(json.dumps(resources, indent=2) + "\n")
    wall = time.monotonic() - started
    transitions = sum(episode["transitions"]
                      for worker in results for episode in worker["episodes"])
    passed = len(results) == args.workers and all(
        not worker["error"] and not worker.get("cleanup_error")
        and len(worker["episodes"]) == len(args.schedule)
        and all((args.fault_probe and worker["worker_id"] == 0 and index == 0
                 and episode.get("expected_infrastructure_fault") and episode["transitions"] == 4)
                or (episode["transitions"] == args.steps
                    and ((args.deadline_probe and episode.get("terminated")
                          and not episode.get("truncated") and episode.get("reason") == "timeout")
                         or (not args.deadline_probe and episode.get("truncated")
                             and not episode.get("terminated"))))
                for index, episode in enumerate(worker["episodes"]))
        and all(not receipt["remaining_owned_processes"]
                and not receipt["remaining_owned_zombies"]
                and ((args.fault_probe and worker["worker_id"] == 0 and index == 0
                      and receipt["failed_sample"] and receipt["worker_returncode"] == -9)
                     or (not receipt["forced_shutdown"] and receipt["worker_returncode"] == 0))
                for index, receipt in enumerate(worker["shutdown_receipts"]))
        and (not args.fault_probe or worker["worker_id"] != 0 or worker.get("fault_verified"))
        for worker in results)
    summary = {**metadata, "passed": passed, "wall_sec_including_all_attempts": wall,
               "valid_transitions": transitions,
               "effective_transition_per_wall_sec": transitions / wall,
               "workers_results": sorted(results, key=lambda value: value["worker_id"])}
    (directory / "benchmark_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({key: value for key, value in summary.items()
                      if key != "workers_results"}, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
