"""Read-only V21 actual-ray load witness; original profile/driver identity checks retained."""
import hashlib
import json
import os
from pathlib import Path
import time
from xml.sax.saxutils import escape
import xml.etree.ElementTree as ET

ROBOTS = ("tb1", "tb2", "tb3")
ROOT = Path("/home/zhuyulab/ns3-workspace")
TEMPLATE = ROOT / "ros2_ws/ros2-multi-robot-automap/src/multi_robot/models/turtlebot3_waffle/model.sdf"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    path = Path(path)
    with path.open("rb") as stream:
        before = os.fstat(stream.fileno())
        raw = stream.read()
        after = os.fstat(stream.fileno())
    def ident(value):
        return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns)
    require(ident(before) == ident(after) == ident(path.stat()), "input changed: " + str(path))
    return raw, {"path": str(path), "sha256": sha(raw), "bytes": len(raw)}


def identity(pid):
    try:
        raw = Path(f"/proc/{pid}/stat").read_bytes()
        fields = raw.decode().rsplit(")", 1)[1].split()
        return {"pid": int(pid), "parent": int(fields[1]), "start_ticks": int(fields[19]),
                "state": fields[0], "stat_raw": raw.decode()}
    except (OSError, ValueError, IndexError):
        return None


def ancestry(pid, benchmark_identity):
    rows = []
    visited = set()
    while pid > 0 and pid not in visited:
        visited.add(pid)
        row = identity(pid)
        require(row is not None and row["state"] != "Z", "live ancestry unavailable")
        rows.append(row)
        if pid == benchmark_identity["pid"]:
            require(row["start_ticks"] == benchmark_identity["start_ticks"], "benchmark PID reused")
            return rows
        pid = row["parent"]
    raise ValueError("header PID is not a descendant of the owned benchmark")


def declared_gazebo_executable(spec):
    """Bind the explicit executable entity and bytes before launch."""
    require(type(spec) is dict and set(spec) == {
        "path", "resolved_path", "sha256", "bytes"},
        "gazebo executable declaration fields differ")
    declared = Path(spec["path"])
    require(declared.is_absolute() and str(declared) == spec["path"],
            "gazebo executable path must be absolute canonical syntax")
    resolved = declared.resolve(strict=True)
    require(str(resolved) == spec["resolved_path"],
            "declared gazebo executable resolved path changed")
    raw, proof = read(declared)
    require(type(spec["bytes"]) is int and spec["bytes"] > 0
            and len(raw) == spec["bytes"]
            and raw.startswith(b"\x7fELF") and proof["sha256"] == spec["sha256"],
            "declared gazebo executable ELF/SHA/size differs")
    return {**proof, "resolved_path": str(resolved),
            "package_provenance": {"available": False,
                "scope": "not needed for executable entity/SHA admission"}}


def executable_identity(actual_executable_path, spec):
    """Use the process executable entity, never a guessed executable basename."""
    declared = declared_gazebo_executable(spec)
    require(os.path.samefile(actual_executable_path, spec["path"]),
            "observer process executable differs from declared gazebo entity")
    require(str(Path(actual_executable_path).resolve(strict=True))
            == declared["resolved_path"],
            "observer process executable resolved path differs")
    raw, actual = read(actual_executable_path)
    require(actual["sha256"] == declared["sha256"],
            "observer process executable SHA differs")
    return {"declaration": declared, "actual": actual,
            "actual_resolved_path": str(Path(actual_executable_path).resolve(strict=True)),
            "samefile": True, "scope": "same live executable entity and SHA; PID/start/ancestry checked separately"}


def mapped(raw, path):
    selected = Path(path).resolve(strict=True)
    actual = selected.stat()
    records = []
    for line in raw.decode().splitlines():
        fields = line.split(None, 5)
        if len(fields) != 6 or fields[5] != str(selected):
            continue
        major, minor = (int(value, 16) for value in fields[3].split(":"))
        require(int(fields[4]) == actual.st_ino
                and (major, minor) == (os.major(actual.st_dev), os.minor(actual.st_dev)),
                "mapped library device/inode differs from actual library")
        records.append(line)
    require(records, "reviewed library absent from actual owned server maps: " + str(selected))
    return records


def header(path):
    with Path(path).open("rb") as stream:
        line = stream.readline(1024 * 1024)
    if not line.endswith(b"\n"):
        raise FileNotFoundError("configuration row not flushed yet")
    value = json.loads(line)
    return value, {"path": str(path), "first_line_sha256": sha(line), "first_line_bytes": len(line)}


def project_actual_model(actual_raw, binding, robot, base):
    actual = actual_raw.decode()
    require(actual.count("</model>") == 1, "effective model count differs")
    model = ET.fromstring(actual).find("model")
    require(model is not None, "effective model missing")
    links = model.findall("link[@name='base_scan']")
    sensors = links[0].findall("sensor[@name='hls_lfcd_lds']") if len(links) == 1 else []
    require(len(sensors) == 1 and sensors[0].attrib == {
        "name": "hls_lfcd_lds", "type": "ray"}, "unique reviewed ray sensor differs")
    ray = binding["ray_provenance"]
    specifications = [
        (model, "  ", "mr3_stop_response_observer_" + robot, binding["observer_library"]["path"],
         {"epoch": binding["epoch"], "robot": robot,
          "output_path": binding["observer_outputs"][robot], "base_link": "base_link",
          "right_joint": "wheel_right_joint", "left_joint": "wheel_left_joint",
          "start_ns": str(binding["capture_start_ns"]), "end_ns": str(binding["capture_end_ns"])}),
        (sensors[0], "        ", "mr3_ray_provenance_observer_" + robot, ray["library"],
         {"output_path": ray["outputs"][robot], "epoch": binding["epoch"], "robot": robot,
          "sensor_link": "base_scan", "sensor_name": "hls_lfcd_lds",
          "start_ns": "0", "end_ns": "300000000000"})]
    for parent, indent, name, filename, fields in specifications:
        all_instances = [node for node in model.iter("plugin") if node.attrib.get("name") == name]
        plugins = [node for node in parent.findall("plugin") if node.attrib.get("name") == name]
        require(len(all_instances) == len(plugins) == 1, "effective plugin instance or parent differs")
        plugin = plugins[0]
        require(plugin.attrib == {"name": name, "filename": filename}, "effective plugin attributes differ")
        require(len(plugin) == len(fields) and {child.tag for child in plugin} == set(fields),
                "effective plugin missing/duplicate/extra tags")
        for child in plugin:
            require(not child.attrib and len(child) == 0 and child.text == fields[child.tag],
                    "effective plugin field differs: " + child.tag)
        marker = indent + '<plugin name="' + name + '"'
        require(actual.count(marker) == 1, "effective plugin raw instance differs")
        start = actual.index(marker)
        end = actual.index(indent + "</plugin>\n", start) + len(indent + "</plugin>\n")
        actual = actual[:start] + actual[end:]
    require(actual == base, "two diagnostic plugins changed original rendered model bytes")
    return actual.encode()


def validate_ray_configuration(value, ray, robot, epoch):
    require(value["schema"] == "mr3-ray-provenance-audit-v1" and value["kind"] == "configuration"
            and value["plugin_type"] == "SensorPlugin"
            and value["robot"] == robot and value["epoch"] == epoch
            and value["scope"] == "Passive diagnostic only; no publish, physics/sensor setter, ray update/recast, actor input or task credit.",
            "ray configuration identity/scope mismatch")
    require(type(value["process_id"]) is int and value["process_id"] > 0,
            "ray configuration PID must be positive integer")
    require(value["compiled_source_sha256"] == ray["source_sha256"]
            and value["loaded_library_path"] == ray["resolved_path"],
            "ray compiled source or loaded library differs")


def verify_ray_library(ray, expected):
    require(ray["enabled"] is True and ray["library"] == expected["installed_path"]
            and ray["resolved_path"] == expected["installed_resolved_path"]
            and str(Path(ray["library"]).resolve(strict=True)) == ray["resolved_path"]
            and ray["source_sha256"] == expected["source_sha256"]
            and ray["library_sha256"] == expected["library_sha256"],
            "actual ray library differs from frozen declaration")
    raw, proof = read(ray["resolved_path"])
    require(raw.startswith(b"\x7fELF") and proof["sha256"] == ray["library_sha256"]
            and type(expected["library_bytes"]) is int and len(raw) == expected["library_bytes"],
            "actual ray ELF SHA/size differs")
    return {"source_sha256": ray["source_sha256"], "library_sha256": proof["sha256"],
            "library_bytes": len(raw), "installed_path": ray["library"],
            "loaded_library_realpath": ray["resolved_path"]}


def witness(plan_path, stage, freeze, benchmark_identity, destination):
    """Called while actual gzserver lives; caller retries only incomplete-file absence."""
    plan_raw, plan_proof = read(plan_path)
    plan = json.loads(plan_raw)
    specification = next(row for row in plan["stages"] if row["stage"] == stage)
    run = Path(specification["run_directory"])
    episode = run / f"worker0/episode001_{specification['scene']}_{specification['seed']}"
    try:
        binding_raw, binding_proof = read(episode / "physics_diagnostic_binding.json")
    except ValueError as error:
        # Launch creates this known single-line file exclusively, then writes
        # it once. A changed stat during that initial write is not a retry of
        # native execution. Final consumed binding_json must still match bytes.
        raise FileNotFoundError("exclusive launch binding still being published") from error
    if not binding_raw.endswith(b"\n"):
        raise FileNotFoundError("exclusive launch binding not flushed yet")
    binding = json.loads(binding_raw)
    require(binding["episode_directory"] == str(episode), "runtime episode differs from declaration")
    headers = {}
    for robot in ROBOTS:
        value, proof = header(binding["observer_outputs"][robot])
        require(value["kind"] == "configuration" and value["robot"] == robot
                and value["epoch"] == binding["epoch"] and value["read_only"] is True,
                "observer header identity or read-only scope mismatch")
        require(value["compiled_source_sha256"] == binding["observer_library"]["source_sha256"],
                "observer compiled source differs from declared binding")
        require(value["loaded_library_path"] == binding["observer_library"]["resolved_path"],
                "observer loaded library differs from runtime binding")
        headers[robot] = (value, proof)
    ray = binding["ray_provenance"]
    expected_ray = plan["ray_library"]
    ray_library = verify_ray_library(ray, expected_ray)
    ray_headers = {}
    for robot in ROBOTS:
        value, proof = header(ray["outputs"][robot])
        validate_ray_configuration(value, ray, robot, binding["epoch"])
        ray_headers[robot] = (value, proof)
    pids = {row[0]["process_id"] for row in headers.values()}
    pids.update(row[0]["process_id"] for row in ray_headers.values())
    require(len(pids) == 1 and type(next(iter(pids))) is int, "observer server PID mismatch")
    pid = next(iter(pids))
    chain = ancestry(pid, benchmark_identity)
    before = chain[0]
    executable_proof = executable_identity(f"/proc/{pid}/exe", plan["gazebo_executable"])
    maps_raw = Path(f"/proc/{pid}/maps").read_bytes()
    mapped_rows = {name: mapped(maps_raw, binding[name + "_library"]["resolved_path"])
                   for name in ("observer", "profile")}
    driver = plan["original_driver"]
    driver_raw, driver_proof = read(driver["installed_path"])
    require(driver_proof["sha256"] == driver["library_sha256"], "original driver binary changed")
    mapped_rows["original_driver"] = mapped(maps_raw, str(Path(driver["installed_path"]).resolve(strict=True)))
    mapped_rows["ray_provenance"] = mapped(maps_raw, ray["resolved_path"])
    require(b"libgazebo_ros_diff_drive.so" not in maps_raw, "legacy stock drive library also mapped")
    after = identity(pid)
    require(after is not None and before["start_ticks"] == after["start_ticks"]
            and after["state"] != "Z", "owned gzserver changed while maps read")
    ledger_raw, ledger_proof = read(binding["profile_output_path"])
    if not ledger_raw.endswith(b"\n"):
        raise FileNotFoundError("first-boundary profile row not flushed yet")
    rows = [json.loads(row) for row in ledger_raw.splitlines()]
    require(len(rows) == 1, "profile must have exactly one first-boundary record")
    ledger = rows[0]
    require(ledger["process_id"] == pid and ledger["epoch"] == binding["epoch"]
            and ledger["binding_json"].encode() == binding_raw
            and ledger["compiled_source_sha256"] == binding["profile_library"]["source_sha256"]
            and ledger["loaded_library_path"] == binding["profile_library"]["resolved_path"],
            "actual first-boundary profile source/PID/runtime binding mismatch")
    expected = 150 if stage == "iters150" else 50
    require(ledger["mode"] == binding["mode"] == stage
            and type(ledger["setter_call_count"]) is int
            and ledger["setter_call_count"] == (1 if expected == 150 else 0)
            and type(ledger["sim_time_ns"]) is int and ledger["sim_time_ns"] == 1000000
            and type(ledger["world_iterations"]) is int and ledger["world_iterations"] == 1
            and type(ledger["before"]["native_ode"]["iters"]) is int
            and type(ledger["after"]["native_ode"]["iters"]) is int
            and ledger["before"]["native_ode"]["iters"] == 50
            and ledger["after"]["native_ode"]["iters"] == expected,
            "native actual profile boundary/iteration differs from declaration")
    libraries = {}
    for name in ("observer", "profile"):
        spec = binding[name + "_library"]
        raw, file_proof = read(spec["resolved_path"])
        require(file_proof["sha256"] == spec["sha256"], "actual loaded library SHA mismatch")
        libraries[name] = {"source_sha256": spec["source_sha256"],
            "library_sha256": file_proof["sha256"], "library_bytes": len(raw),
            "installed_path": spec["path"], "loaded_library_realpath": spec["resolved_path"]}
    libraries["ray_provenance"] = verify_ray_library(ray, expected_ray)
    require(libraries["ray_provenance"] == ray_library, "ray library changed during witness")
    # Recheck actual map inode/dev against the same hashed paths after file reads.
    current_maps = Path(f"/proc/{pid}/maps").read_bytes()
    for name in ("observer", "profile"):
        mapped(current_maps, binding[name + "_library"]["resolved_path"])
        mapped(maps_raw, binding[name + "_library"]["resolved_path"])
    mapped(current_maps, driver["installed_path"])
    mapped(current_maps, ray["resolved_path"])
    mapped(maps_raw, ray["resolved_path"])
    require(identity(pid)["start_ticks"] == before["start_ticks"], "server changed during library hashing")
    template_raw, template_proof = read(TEMPLATE)
    generated = {}
    # Nothing is written until every native identity above has been verified.
    destination = Path(destination)
    destination.mkdir(exist_ok=False)
    maps_path = destination / "owned_gzserver.maps"
    maps_path.write_bytes(maps_raw)
    ancestry_path = destination / "owned_ancestry.json"
    ancestry_path.write_text(json.dumps({"schema": "mr3-live-owned-ancestry-v1", "benchmark_identity": benchmark_identity,
                                       "before": chain, "after": after,
                                       "maps_library_rows": mapped_rows}, indent=2) + "\n")
    for robot in ROBOTS:
        actual_path = episode / f"drive_model_{robot}.sdf"
        actual_raw, actual_proof = read(actual_path)
        base = template_raw.decode()
        for tag, value in {"mr3_audit_path": str(episode / f"drive_{robot}.jsonl"),
                           "mr3_epoch": binding["epoch"], "mr3_tagged_commands": "true"}.items():
            placeholder = f"<{tag}/>"
            require(base.count(placeholder) == 1, "original model placeholder count differs")
            base = base.replace(placeholder, f"<{tag}>{escape(value)}</{tag}>")
        name = "mr3_stop_response_observer_" + robot
        project_actual_model(actual_raw, binding, robot, base)
        base_path = destination / f"before_observer_{robot}.sdf"
        base_raw = base.encode()
        base_path.write_bytes(base_raw)
        generated[robot] = {**actual_proof, "observer_plugin_name": name,
            "observer_library": binding["observer_library"]["path"],
            "before_observer_path": str(base_path), "before_observer_sha256": sha(base_raw),
            "original_template": template_proof, "original_render_rule": "exact three original driver placeholders after both fully validated diagnostic plugins removed",
            "original_body_bytes_preserved": True}
    proof = {"schema": "mr3-ray-provenance-admission-proof-v1", "passed": True,
        "freeze": freeze, "plan_sha256": plan_proof["sha256"], "stage": stage,
        "run_directory": str(run), "episode_directory": str(episode), "epoch": binding["epoch"],
        "robot_order": list(ROBOTS), "observer": libraries["observer"],
        "ray_provenance": {**libraries["ray_provenance"],
            "configuration_files": {robot: ray_headers[robot][1] for robot in ROBOTS},
            "mapped": True, "read_only": True},
        "profile": {**libraries["profile"], "mode": stage, "expected_iters": expected,
                    "ledger_path": ledger_proof["path"], "ledger_sha256": ledger_proof["sha256"]},
        "owned_gzserver": {"pid": pid, "start_ticks": before["start_ticks"],
            "executable": executable_proof,
            "maps_path": str(maps_path), "maps_sha256": sha(maps_raw),
            "observer_mapped": True, "profile_mapped": True,
            "ancestry_path": str(ancestry_path), "ancestry_sha256": sha(ancestry_path.read_bytes())},
        "generated_models": generated, "runtime_binding": binding_proof,
        "original_driver": {**driver_proof, "mapped": True},
        "observer_files": {robot: headers[robot][1] for robot in ROBOTS},
        "witness_wall_monotonic_ns": time.monotonic_ns(),
        "scope": "live owned process/source/binary/config/model binding; no task or physical response acceptance"}
    path = destination / "admission_proof.json"
    path.write_text(json.dumps(proof, indent=2, allow_nan=False) + "\n")
    return path, proof
