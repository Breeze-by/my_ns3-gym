#!/usr/bin/env python3
"""Run one frozen P3C.5 traffic cell; retain failures, never overwrite or retry."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys

from run_p3b5_tasks import episode_command
from run_p2d_baseline import PROJECT_ROOT, file_digest


def now():
    return datetime.now(timezone.utc).isoformat()


def staging_apparatus(config):
    name=config.get('staging_apparatus_script','stage_p3b5_return_probe.py')
    if name not in ('stage_p3b5_return_probe.py','stage_p2c_return_probe.py'):
        raise ValueError('unknown staging apparatus')
    return PROJECT_ROOT/'scripts'/name


def return_probe_commands(config, scenario, directory, owner_pid, manifest_path):
    """Opt-in unchanged controlled exposure and read-only physical observer."""
    if 'return_staging' not in config:
        return {}
    if len(config['return_staging']['poses']) != scenario['robot_count']:
        raise ValueError('staging robot count differs from the declared case')
    return {
        'physics': [sys.executable,str(PROJECT_ROOT/'scripts/observe_p3b5_return_physics.py'),
                    '--output',str(directory/'physics.jsonl'),'--robot-count',str(scenario['robot_count'])],
        'staging': [sys.executable,str(staging_apparatus(config)),
                    '--owner-pid',str(owner_pid),'--config',str(manifest_path.resolve()),
                    '--output',str(directory/'staging.jsonl')],
    }


def main(default_manifest=None, log_category='p3c5'):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=default_manifest or Path(__file__).with_name("p3c5_traffic_manifest.json"))
    parser.add_argument("--case", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--domain", type=int, required=True)
    parser.add_argument("--gazebo-port", type=int, required=True)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if Path(args.run_id).name != args.run_id or not args.run_id or not 0 <= args.domain <= 232 or args.domain == 222:
        parser.error("require a single-directory run id and an isolated domain other than 222")
    config = json.loads(args.manifest.read_text())
    if args.case not in config["cases"]:
        parser.error("unknown predeclared case")
    scenario = config["cases"][args.case]
    root = PROJECT_ROOT / 'log' / log_category / args.run_id
    directory = root / (args.run_id+"_"+args.case)
    case = {"id": args.case, "scenario": args.case, "mode": "rally", "profile": "online"}
    command = episode_command(case, scenario, scenario.get("profile", {}), scenario["mode"], directory, config)
    # Export cleanup follows mission termination; it never extends native time.
    command[command.index("--shutdown-timeout")+1] = str(config.get("owner_shutdown_timeout_sec", 60))
    if scenario["admission_protocol"]:
        command.append("--gateway-admission-protocol")
    observer_command = [sys.executable, str(PROJECT_ROOT / "scripts/observe_p3b5.py"),
                        "--output", str(directory / "safety_events.jsonl"), "--robot-count", str(scenario["robot_count"])]
    if config.get('native_tf_graph_capture'):
        observer_command.extend(['--native-tf-graph-output',str(directory/'native_graph.json')])
    if config.get('navigation_input_capture'):
        observer_command.extend(['--navigation-input-output',str(directory/'navigation_inputs.jsonl.gz')])
    schedule_path = directory / "schedule.json"
    configure_command = [sys.executable, str(PROJECT_ROOT / "scripts/gateway_configure.py"),
                         "--schedule", str(schedule_path), "--output", str(directory / "configuration.jsonl")]
    probe_commands = return_probe_commands(config,scenario,directory,os.getpid(),args.manifest)
    env = os.environ.copy()
    env.update(ROS_DOMAIN_ID=str(args.domain), GAZEBO_MASTER_URI=f"http://127.0.0.1:{args.gazebo_port}",
               P3B5_OBSERVER_OWNER_PID=str(os.getpid()))
    manifest = {"case": args.case, "config": config, "command": command, "observer_command": observer_command,
                "configuration_command": configure_command if scenario["schedule"] else None,
                "environment": {key: env.get(key) for key in ("ROS_DOMAIN_ID", "GAZEBO_MASTER_URI", "ROS_DISTRO",
                    "RMW_IMPLEMENTATION", "FASTDDS_BUILTIN_TRANSPORTS", "PYTHONNOUSERSITE", "FASTRTPS_DEFAULT_PROFILES_FILE", "ROS_DISCOVERY_SERVER")},
                "cpu_affinity": sorted(os.sched_getaffinity(0)), "owner_pid": os.getpid(),
                "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
                "source_digests": {name: file_digest(PROJECT_ROOT / path) for name, path in {
                    "exploration": "src/multi_robot_exploration/multi_robot_exploration", "launch": "src/multi_robot/launch",
                    "params": "src/multi_robot/params", "worlds": "src/multi_robot/worlds", "slam": "src/slam_toolbox/src",
                    "manifest": str(args.manifest.resolve()), "runner": str(Path(__file__).resolve()),
                    "smoke": "scripts/ros_smoke_test.py", "control_cli": "scripts/gateway_configure.py",
                    'entrypoint': str(Path(sys.argv[0]).resolve()),
                    "message_schema": "src/multi_robot_interfaces/msg/GatewayEnvelope.msg",
                    "control_schema": "scripts/p3c5_control_schema.json",
                    "admission_protocol": "src/multi_robot_exploration/multi_robot_exploration/admission_protocol.py"}.items()}}
    manifest['source_digests'].update({name:file_digest(PROJECT_ROOT/'scripts'/filename)
        for name,filename in (('staging_apparatus',staging_apparatus(config).name),
                              ('physics_observer','observe_p3b5_return_physics.py'))})
    if config.get('native_tf_graph_capture'):
        manifest['source_digests'].update({name:file_digest(PROJECT_ROOT/'scripts'/filename)
            for name,filename in (('safety_observer','observe_p3b5.py'),('native_graph_reader','p2c_native_graph.py'))})
    if config.get('navigation_input_capture'):
        manifest['source_digests']['navigation_capture']=file_digest(PROJECT_ROOT/'scripts/p2c_navigation_capture.py')
    if probe_commands:
        fixture=staging_apparatus(config)
        manifest.update(staging_command=shlex.join(probe_commands['staging']),
            physics_command=probe_commands['physics'],staging_source=fixture.read_text(),
            staging_source_sha256=file_digest(fixture),
            staging_content_sha256=hashlib.sha256(fixture.read_bytes()).hexdigest())
    if args.validate_only:
        print(json.dumps(manifest, indent=2))
        return 0
    status = subprocess.check_output(["git", "-C", str(PROJECT_ROOT.parents[1]), "status", "--short", "--untracked-files=all"], text=True)
    dirty = [line for line in status.splitlines() if not (line.startswith("?? 260929_report/") or line.startswith('?? "260929_report/'))]
    if dirty:
        parser.error("freeze and push the clean source before a task run: " + str(dirty))
    upstream = subprocess.check_output(['git','rev-parse','@{u}'],text=True).strip()
    if upstream != manifest['git_commit']:
        parser.error('push the exact task freeze before a run')
    directory.mkdir(parents=True, exist_ok=False)
    schedule_path.write_text(json.dumps(scenario["schedule"], indent=2)+"\n")
    manifest["started_at_utc"] = now()
    manifest["worktree_status"] = status.splitlines()
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")
    children, streams, row = [], [], dict(manifest)
    try:
        for name, argv in (("observer", observer_command),*probe_commands.items(),
                          ("configuration", configure_command if scenario["schedule"] else None)):
            if argv:
                stream = (directory / (name+".log")).open("w")
                streams.append(stream)
                child = subprocess.Popen(argv, env=env, cwd=PROJECT_ROOT, stdout=stream, stderr=subprocess.STDOUT)
                children.append((name, child))
                row[name+"_pid"] = child.pid
        with (directory / "runner.log").open("w") as stream:
            process = subprocess.run(command, env=env, cwd=PROJECT_ROOT, stdout=stream, stderr=subprocess.STDOUT, check=False)
        row["runner_returncode"] = process.returncode
    finally:
        for name, child in children:
            if child.poll() is None:
                child.send_signal(signal.SIGINT)
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
                row[name+"_forced_shutdown"] = True
            row[name+"_returncode"] = child.returncode
        for stream in streams:
            stream.close()
        row["finished_at_utc"] = now()
        result_path = directory / (directory.name+".json")
        if result_path.is_file():
            row["result_path"] = str(result_path)
            row["result"] = json.loads(result_path.read_text())
        row["evidence_sha256"] = {str(path.relative_to(directory)): hashlib.sha256(path.read_bytes()).hexdigest()
                                  for path in directory.rglob("*") if path.is_file()}
        (directory / "summary.json").write_text(json.dumps(row, indent=2, sort_keys=True)+"\n")
    print(json.dumps({"case": args.case, "runner_returncode": row.get("runner_returncode"),
                      "task_phase": row.get("result", {}).get("task_phase"), "summary": str(directory / "summary.json")}))
    return int(row.get("runner_returncode", 1) != 0 or row.get("observer_returncode", 1) != 0
               or any(child.returncode != 0 for _,child in children))


if __name__ == "__main__":
    raise SystemExit(main())
