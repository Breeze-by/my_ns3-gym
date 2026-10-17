"""Conda parent launches exact frozen hook shell against native-profile fixture."""
import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path("/home/zhuyulab/ns3-workspace")
ROS = ROOT / "ros2_ws/ros2-multi-robot-automap"
WIRELESS = ROOT / "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl"
FREEZE = "b4e64f90391c0b4db2127e9e824118459a4288ad"
RELATIVE = ("ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/"
            "report/assets/20261017_mr3_p2a0_v4/independent/mr3_actual_nav2_parameters_v4.py")
BASE = Path("/tmp/mr3_p2a0_v4_transport_ab_v1")
assert not BASE.exists(), "do not overwrite CPU evidence"
BASE.mkdir()
sha = lambda raw: hashlib.sha256(raw).hexdigest()
parameter_payload = subprocess.check_output(["git", "show", FREEZE + ":" + RELATIVE], cwd=ROOT)
assert sha(parameter_payload) == "fe0a91eec1aaf6d45bc3aedd4de9223b53e77721be878136a96d02ef1bd5c0ae"
parameter = BASE / "frozen_mr3_actual_nav2_parameters_v4.py"
parameter.write_bytes(parameter_payload)
supervisor_source = subprocess.check_output(["git", "show", FREEZE + ":" +
    "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/mr3_learning/supervisor.py"], cwd=ROOT)
tree = ast.parse(supervisor_source)
function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                and node.name == "ros_environment")
scope = {"os": os}
exec(compile(ast.Module(body=[function], type_ignores=[]), "frozen_supervisor.ros_environment", "exec"), scope)
ros_environment = scope["ros_environment"]
profile = ROS / "src/multi_robot/config/mr3_fastdds_loopback_udp.xml"
assert sha(profile.read_bytes()) == "dd7eeadca21f0924fe721515e8dd57ac979340df8b08885bc39d2595c8caf87b"
transport = {"RMW_IMPLEMENTATION": "rmw_fastrtps_cpp", "ROS_LOCALHOST_ONLY": "0",
             "FASTRTPS_DEFAULT_PROFILES_FILE": str(profile), "SKIP_DEFAULT_XML": "1"}
keys = (*transport, "FASTDDS_DEFAULT_PROFILES_FILE", "RMW_FASTRTPS_USE_QOS_FROM_XML",
        "RMW_FASTRTPS_PUBLICATION_MODE", "ROS_DOMAIN_ID", "GAZEBO_MASTER_URI")


def identity(pid):
    try:
        raw = Path(f"/proc/{pid}/stat").read_text()
    except FileNotFoundError:
        return None
    fields = raw[raw.rfind(")") + 2:].split()
    return {"pid": pid, "parent": int(fields[1]), "start_ticks": int(fields[19]), "state": fields[0]}


def same(old):
    live = identity(old["pid"])
    return live is not None and live["start_ticks"] == old["start_ticks"]


probe = BASE / "source_shell_environment.py"
probe.write_text("import os,json\nprint(json.dumps({k:os.environ.get(k)for k in " + repr(keys) + "}))\n")
hook_shell = ('source /opt/ros/humble/setup.bash && source "$1" && shift '
              '&& exec /usr/bin/python3 "$@"')
result = {"schema": "mr3-v4-native-profile-hook-transport-ab-v1", "source_freeze": FREEZE,
          "parent_python": sys.executable, "parent_transport_environment": {k: os.environ.get(k) for k in keys},
          "parameter_script_sha256": sha(parameter_payload), "supervisor_source_sha256": sha(supervisor_source),
          "native_transport_profile_sha256": sha(profile.read_bytes()), "branches": [],
          "scope": "Two ROS CPU fixtures only, no Gazebo/control/training. Frozen b4 hook bytes and shell; "
                   "publisher sends one transient-local reliable status before client startup. "
                   "Frozen script copied to a temporary path only; matching branch changes transport env only."}
for label, domain in (("default_subscriber", 228), ("matched_subscriber", 227)):
    directory = BASE / label
    directory.mkdir()
    (directory / "metadata.json").write_text(json.dumps({"freeze": FREEZE, "epoch": "transport_ab_fixture"}))
    (directory / "transitions.jsonl").write_text(json.dumps({"kind": "reset", "snapshot": {
        "epoch": "transport_ab_fixture"}, "info": {"release_time_ns": 1000000000}}) + "\n")
    base_env = ros_environment(domain, 13200 + domain)
    base_env["PYTHONDONTWRITEBYTECODE"] = "1"
    server_command = ["/usr/bin/bash", "--noprofile", "--norc", "-c",
        'source /opt/ros/humble/setup.bash && source "$1/install/setup.bash" '
        '&& source /usr/share/gazebo/setup.sh && exec /usr/bin/python3 "$2" "$3" --parameter-script "$4"',
        "mr3-worker-fixture", str(ROS), "/tmp/mr3_v4_transport_ab_server.py", str(directory), str(parameter)]
    with (directory / "server_console.log").open("x") as output:
        server = subprocess.Popen(server_command, cwd=ROS, env=base_env, stdout=output, stderr=subprocess.STDOUT)
        server_identity = identity(server.pid)
        try:
            ready_deadline = time.monotonic() + 15
            while not (directory / "server_ready.json").exists():
                assert server.poll() is None, "server exited before readiness"
                assert time.monotonic() < ready_deadline, "server fixture readiness timeout"
                time.sleep(.05)
            ready = json.loads((directory / "server_ready.json").read_text())
            environment = dict(base_env)
            if label == "matched_subscriber":
                for key in ("FASTDDS_DEFAULT_PROFILES_FILE", "RMW_FASTRTPS_USE_QOS_FROM_XML",
                            "RMW_FASTRTPS_PUBLICATION_MODE"):
                    environment.pop(key, None)
                environment.update(transport)
            shell_command = ["bash", "-c", hook_shell, "mr3_parameter_review", str(ROS / "install/setup.bash")]
            actual_env = subprocess.run([*shell_command, str(probe)], env=environment,
                capture_output=True, text=True, timeout=10, check=True)
            command = [*shell_command, str(parameter), str(directory), "--freeze", FREEZE,
                       "--output", str(directory / "actual_parameters.json"), "--wall-timeout-sec", "30"]
            started = time.monotonic()
            child = subprocess.Popen(command, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            child_identity = identity(child.pid)
            stdout, stderr = child.communicate(timeout=45)
            (directory / "client_stdout.txt").write_text(stdout)
            (directory / "client_stderr.txt").write_text(stderr)
            report = json.loads((directory / "actual_parameters.json").read_text())
            branch = {"label": label, "domain": domain, "server_command": server_command,
                      "client_command": command, "source_shell_environment": json.loads(actual_env.stdout),
                      "server_native_environment": ready["transport"], "server_identity": server_identity,
                      "client_identity": child_identity, "client_returncode": child.returncode,
                      "client_wall_sec": time.monotonic() - started, "client_result": report,
                      "stdout": stdout, "stderr": stderr, "single_status_published": ready["status_publication_count"]}
        finally:
            (directory / "stop_server").write_text("owned CPU fixture stop\n")
            server_code = server.wait(timeout=10)
        branch.update(server_returncode=server_code,
            server_final=json.loads((directory / "server_final.json").read_text()),
            server_same_identity_remaining=same(server_identity), client_same_identity_remaining=same(child_identity))
        result["branches"].append(branch)
        (BASE / "progress.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps({"branch": label, "client_returncode": child.returncode,
                          "client_passed": report["passed"], "nodes": len(report["nodes"]),
                          "server_returncode": server_code}), flush=True)
first, second = result["branches"]
result["passed"] = (first["client_returncode"] == 1 and first["client_result"]["passed"] is False
    and len(first["client_result"]["nodes"]) == 0 and "paused reset status" in str(first["client_result"]["errors"])
    and second["client_returncode"] == 0 and second["client_result"]["passed"] is True
    and len(second["client_result"]["nodes"]) == 9 and all(
        branch["server_returncode"] == 0 and not branch["server_same_identity_remaining"]
        and not branch["client_same_identity_remaining"]
        and all(branch["server_final"]["cleanup"].values())
        and all(branch["client_result"]["cleanup"].values()) for branch in result["branches"]))
(BASE / "receipt.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps({"passed": result["passed"], "receipt": str(BASE / "receipt.json")}), flush=True)
sys.exit(0 if result["passed"] else 1)
