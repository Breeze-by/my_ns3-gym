"""Explicit-freeze live native identity capture and strict closed-episode review.

This gate has no ROS imports, process signalling, physics or training operations.
It retains the original PID/start, ancestry, actual mapped-file and orderly-close
predicates. Mathematical/physical gates remain separate mandatory consumers.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import time
import xml.etree.ElementTree as ET

from .supervisor import WORKSPACE, process_identity

ROBOTS = ("tb1", "tb2", "tb3")
PROTOCOL = "nav2-finalized_then_serial-ros_then_gazebo-v1"
NAV2_NODES = {"controller_server", "planner_server", "behavior_server", "bt_navigator",
              "waypoint_follower", "velocity_smoother"}
BINARY_ROLES = {"driver", "observer", "ray_box", "ode", "smoother_core",
                "smoother_executable", "odometry_recorder_executable",
                "controller_executable", "rotation_shim", "gzserver_executable"}
COMPILED_FIELDS = {
    "driver": {"compiled_source_sha256", "compiled_header_sha256", "compiled_helper_sha256",
               "compiled_target_contract_sha256", "compiled_odometry_json_sha256"},
    "recorder": {"compiled_source_sha256", "compiled_odometry_json_sha256"},
    "observer": {"compiled_source_sha256"},
    "ray_box": {"compiled_source_sha256", "compiled_collision_source_sha256",
                "compiled_collision_header_sha256"},
}


class PendingCapture(ValueError):
    """A naturally incomplete live observation earns no identity credit."""


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def parse(raw):
    def unique(pairs):
        out = {}
        for key, value in pairs:
            require(key not in out, "duplicate JSON key: " + key)
            out[key] = value
        return out
    return json.loads(raw, object_pairs_hook=unique, parse_constant=lambda x:
                      (_ for _ in ()).throw(ValueError("nonfinite JSON: " + x)))


def stat_key(value):
    return {key: getattr(value, "st_" + key) for key in ("dev", "ino", "size", "mtime_ns", "ctime_ns")}


class Reader:
    """Bind stable closed inputs; growing live logs use first complete line only."""
    def __init__(self):
        self.bindings = {}

    def __call__(self, path):
        path = Path(path)
        with path.open("rb") as stream:
            before = stat_key(os.fstat(stream.fileno()))
            raw = stream.read()
            after = stat_key(os.fstat(stream.fileno()))
        require(before == after == stat_key(path.stat()), "input changed while read: " + str(path))
        entry = {"sha256": sha(raw), "bytes": len(raw)}
        require(self.bindings.setdefault(str(path), entry) == entry,
                "input changed across reads: " + str(path))
        return raw

    def finish(self):
        for path, expected in list(self.bindings.items()):
            raw = self(path)
            require({"sha256": sha(raw), "bytes": len(raw)} == expected,
                    "bound input changed before verdict: " + path)


def exclusive(path, value):
    with Path(path).open("x") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def write_ready_receipt(path, freeze, binding_sha256):
    value={"schema":"native-custody-ready-v1","freeze":freeze,
           "binding_sha256":binding_sha256,"watcher_identity":process_identity(os.getpid())}
    require(value["watcher_identity"] is not None,"actual watcher identity unavailable")
    exclusive(path,value)
    return value


def read_ready_receipt(read,path,freeze,binding_sha256):
    value=parse(read(path))
    require(value.get("schema")=="native-custody-ready-v1" and value.get("freeze")==freeze
            and value.get("binding_sha256")==binding_sha256,"watcher ready identity differs")
    identity=value["watcher_identity"]
    require(type(identity.get("pid"))is int and identity["pid"]>0
            and type(identity.get("start_ticks"))is int and identity["start_ticks"]>0,
            "watcher ready lacks typed real PID/start")
    return value


def read_wait_boundary(read,stop_path,launch_path,freeze):
    stop=parse(read(stop_path))
    require(stop.get("schema")=="mr3-native-custody-stop-v1" and stop.get("freeze")==freeze,
            "watch stop receipt differs")
    if stop.get("native_not_started")is True:
        require(stop.get("reason")in("watcher_ready_timeout","pre_native_admission_failure"),
                "unknown pre-native cancellation reason")
        return {"stop":stop,"launch":None}
    spec=stop["launch_receipt"]
    require(Path(spec["path"])==Path(launch_path),"stop refers to a different native wait receipt")
    raw=read(launch_path)
    launch=parse(raw)
    require(sha(raw)==spec["sha256"] and launch.get("freeze")==freeze
            and type(launch.get("returncode"))is int,"stop/native wait receipt SHA/freeze/returncode differs")
    for key in ("benchmark_parent","launcher_identity"):
        identity=launch[key]
        require(type(identity.get("pid"))is int and identity["pid"]>0
                and type(identity.get("start_ticks"))is int and identity["start_ticks"]>0,
                "native wait receipt lacks actual PID/start: "+key)
    return {"stop":stop,"launch":launch}


def read_fifo_receipts(read,path,freeze,expected_count):
    leaves=parse(read(path))
    require(type(expected_count)is int and expected_count>0
            and type(leaves)is list and len(leaves)==expected_count,"FIFO receipt inventory differs")
    result={}
    for spec in leaves:
        raw=read(spec["path"])
        leaf=parse(raw)
        require(sha(raw)==spec["sha256"] and leaf.get("passed")is True
                and leaf.get("freeze")==freeze and leaf.get("errors")==[]
                and isinstance(leaf.get("epoch"),str) and bool(leaf["epoch"]),"FIFO/phase leaf failed")
        require(Path(spec["episode_directory"]).is_absolute()
                and spec["episode_directory"]not in result,"duplicate/nonabsolute FIFO episode")
        for bound_path,expected in leaf["bindings"].items():
            content=read(bound_path)
            require(sha(content)==expected["sha256"] and len(content)==expected["bytes"],"FIFO raw binding changed")
        result[spec["episode_directory"]]=leaf
    return result


def file_proof(path):
    path = Path(path)
    with path.open("rb") as stream:
        before = stat_key(os.fstat(stream.fileno()))
        raw = stream.read()
        after = stat_key(os.fstat(stream.fileno()))
    require(before == after == stat_key(path.stat()), "ELF changed while hashed: " + str(path))
    require(raw.startswith(b"\x7fELF"), "native file is not ELF: " + str(path))
    return {"resolved_path": str(path.resolve(strict=True)), "sha256": sha(raw),
            "bytes": len(raw), "stat": after}


def git_bytes(root, freeze, relative):
    return subprocess.check_output(["git", "show", freeze + ":" + relative], cwd=root)


def load_binding(path, freeze, *, root=WORKSPACE, read=None):
    """Expected bytes come from an explicit frozen binding, never current defaults."""
    root, path = Path(root).resolve(), Path(path).resolve(strict=True)
    read = Reader() if read is None else read
    require(re.fullmatch("[0-9a-f]{40}", freeze) is not None, "exact 40hex freeze required")
    raw = read(path)
    require(git_bytes(root, freeze, str(path.relative_to(root))) == raw,
            "binding differs from Git freeze")
    binding = parse(raw)
    require(binding.get("schema") == "mr3-native-custody-binding-v1", "unknown custody binding")
    require(set(binding["binaries"]) == BINARY_ROLES, "native binary roles differ")
    require(set(binding["compiled_sources"]) == set(COMPILED_FIELDS), "compiled-source roles differ")
    require(binding.get("optional_observer_per_episode") is True,
            "per-episode optional observer mode must be explicit")

    def source(spec):
        source_path = Path(spec["path"])
        source_path = source_path if source_path.is_absolute() else root / source_path
        source_raw = read(source_path)
        relative = str(source_path.relative_to(root))
        require(re.fullmatch("[0-9a-f]{64}", spec["sha256"]) is not None
                and sha(source_raw) == spec["sha256"]
                and git_bytes(root, freeze, relative) == source_raw,
                "source differs from exact freeze: " + relative)
        return source_path, source_raw

    for role, fields in COMPILED_FIELDS.items():
        require(set(binding["compiled_sources"][role]) == fields,
                "compiled-source fields differ: " + role)
        for spec in binding["compiled_sources"][role].values():
            source(spec)
    bound_sources = {}
    for spec in binding["source_bindings"]:
        source_path, _ = source(spec)
        require(str(source_path) not in bound_sources, "duplicate source binding")
        bound_sources[str(source_path)] = spec["sha256"]
    this = Path(__file__).resolve()
    if this.is_relative_to(root):
        require(bound_sources.get(str(this)) == sha(read(this)), "new custody entry source is unbound")
    tool_path, tool_raw = source(binding["process_tools"])
    spec = importlib.util.spec_from_file_location("mr3_native_original_process_predicates", tool_path)
    tools = importlib.util.module_from_spec(spec)
    exec(compile(tool_raw, str(tool_path), "exec"), tools.__dict__)
    for name in ("proc_identity", "identity_equal", "ancestor_chain", "namespace"):
        require(callable(getattr(tools, name, None)), "original process predicate missing: " + name)
    corrector_path, corrector_raw = source(binding["corrector_tools"])
    spec = importlib.util.spec_from_file_location("mr3_native_original_corrector_predicates", corrector_path)
    corrector = importlib.util.module_from_spec(spec)
    exec(compile(corrector_raw, str(corrector_path), "exec"), corrector.__dict__)
    corrector_binding_path, _ = source(binding["corrector_binding"])
    original_corrector_binding = corrector.load_binding(corrector_binding_path, read)
    binaries = {}
    for role, expected in binding["binaries"].items():
        actual = file_proof(expected["path"])
        require(all(actual[key] == expected[key] for key in ("resolved_path", "sha256", "bytes")),
                "declared native ELF differs: " + role)
        if role == "gzserver_executable":
            require(all(type(expected["stat"][key]) is int
                        and actual["stat"][key] == expected["stat"][key] for key in ("dev", "ino")),
                    "declared gzserver ELF device/inode differs")
        binaries[role] = {**expected, **actual}
        read(expected["path"])
    for role, fields in binding["compiled_sources"].items():
        native_role = "odometry_recorder_executable" if role == "recorder" else role
        binary = Path(binaries[native_role]["resolved_path"]).read_bytes()
        require(all(value["sha256"].encode() in binary for value in fields.values()),
                "actual ELF lacks declared compiled-source SHA: " + role)
    require(bool(binding["build_receipts"]), "explicit build receipts are required")
    for spec in binding["build_receipts"]:
        receipt_path = Path(spec["path"])
        receipt_path = receipt_path if receipt_path.is_absolute() else root / receipt_path
        receipt_raw = read(receipt_path)
        receipt = parse(receipt_raw)
        require(sha(receipt_raw) == spec["sha256"] and receipt.get("passed") is True
                and receipt.get("freeze", freeze) == freeze and bool(receipt.get("commands"))
                and all(type(row.get("returncode",row.get("observed_returncode"))) is int
                        and row.get("returncode",row.get("observed_returncode")) == 0
                        and ("returncode" not in row or "observed_returncode" not in row
                             or row["returncode"] == row["observed_returncode"])
                        for row in receipt["commands"]),
                "explicit build receipt is not successful/bound")
        require(git_bytes(root, freeze, str(receipt_path.relative_to(root))) == receipt_raw,
                "build receipt differs from freeze")
        if receipt.get("schema") == "mr3-smoother-diagnostic-installed-cpu-v2":
            files=receipt["file_proof"]
            for role in ("smoother_core","smoother_executable"):
                expected=binaries[role]
                require(files[expected["path"]]["sha256"] == expected["sha256"],
                        "original smoother build receipt differs from current expected ELF")
            cpp=root/"ros2_ws/ros2-multi-robot-automap/src/nav2_velocity_smoother/src/velocity_smoother.cpp"
            require(files[str(cpp)]["sha256"] == bound_sources.get(str(cpp)),
                    "original smoother build receipt source differs from frozen source")
            test=receipt["test_result"]
            require(test.get("tests")=="23" and test.get("failures")==test.get("errors")=="0",
                    "original smoother CPU receipt is not23/0/0")
            xml=[value["sha256"] for path,value in files.items()
                 if Path(path).name=="mr3_smoother_diagnostic_tests_installed_v2.xml"]
            require(len(xml)==1 and xml[0] in bound_sources.values(),
                    "original23test XML SHA is not bound to an exact frozen source/artifact")
    return {"document": binding, "path": str(path), "sha256": sha(raw), "freeze": freeze,
            "binaries": binaries, "tools": tools, "reader": read,
            "corrector_tools": corrector, "corrector_binding": original_corrector_binding}


def verify_binding(root, freeze, binding_path):
    """Pure preflight for the fixed caller-pinned binding; no live process needed."""
    read = Reader()
    bound = load_binding(binding_path, freeze, root=root, read=read)
    read.finish()
    return {"schema":"mr3-native-custody-verified-binding-v1", "passed":True,
            "freeze":freeze, "binding_path":bound["path"], "binding_sha256":bound["sha256"],
            "binaries":bound["binaries"], "compiled_sources":bound["document"]["compiled_sources"],
            "source_bindings":bound["document"]["source_bindings"], "bindings":read.bindings,
            "smoother_scope":"Explicit frozen source/build receipt/actual ELF identity only. Normal diagnostic=false requires separate live parameter-file evidence; CPU-test results are not inferred from source hashes. No timer-only inverse claim."}


def episode_directories(run):
    """Only real Supervisor layouts; ignore archives and discover nested PPO rounds."""
    run=Path(run).resolve()
    result=[]
    for path in run.rglob("supervisor_metadata.json"):
        relative=path.parent.relative_to(run).parts
        if len(relative)<2 or re.fullmatch(r"worker\d+",relative[-2]) is None or re.fullmatch(r"episode\d+_(?:open|rooms|corridors)_\d+",relative[-1]) is None:
            continue
        prefix=relative[:-2]
        if prefix not in ((),("native",)) and not (len(prefix)==2 and prefix[0]=="native" and re.fullmatch(r"round\d+",prefix[1])):
            continue
        result.append(path.parent.resolve())
    require(len(result)==len(set(result)),"duplicate/symlink Supervisor episode directory")
    return sorted(result)


def native_parent_module(argv):
    require(bool(argv) and re.fullmatch(r"python(?:\d+(?:\.\d+)*)?",Path(argv[0]).name) is not None
            and argv.count("-m")==1,"actual native parent is not the declared Python module entry")
    index=argv.index("-m")
    require(index+1<len(argv) and argv[index+1] in (
        "mr3_learning.benchmark","mr3_learning.ppo","mr3_learning.action_trace"),
        "actual parent module is not benchmark/PPO/action_trace")
    if argv[index+1]=="mr3_learning.ppo" and "--mode"in argv:
        mode=argv.index("--mode")
        require(mode+1<len(argv) and argv[mode+1]in("train","evaluate"),"unknown PPO parent mode")
    return argv[index+1]


def first_line(path):
    with Path(path).open("rb") as stream:
        raw = stream.readline()
    if not raw.endswith(b"\n"):
        raise FileNotFoundError("first complete native configuration not yet available: " + str(path))
    return {"path": str(path), "first_line_sha256": sha(raw), "configuration": parse(raw)}


def configurations(directory, binding):
    epoch = parse((directory / "metadata.json").read_bytes())["epoch"]
    result = []
    passive = observer_binding(directory, binding)
    for role, names in (("driver", ["drive_" + r + ".jsonl" for r in ROBOTS]),
                        ("observer", ["physics_" + r + ".jsonl" for r in ROBOTS] if passive else []),
                        ("recorder", ["driver_odometry_receipts.jsonl"]),
                        ("ray_box", ["ray_box_corrector.jsonl"])):
        for name in names:
            row = first_line(directory / name)
            cfg = row["configuration"]
            require(cfg.get("kind") == "configuration" and cfg.get("epoch") == epoch,
                    "native configuration epoch/kind differs: " + name)
            require(all(cfg.get(key) == spec["sha256"] for key, spec in
                        binding["document"]["compiled_sources"][role].items()),
                    "native compiled-source configuration differs: " + name)
            if role in ("driver", "observer"):
                require(cfg.get("robot") in ROBOTS and name.endswith(cfg["robot"] + ".jsonl"),
                        "native configuration robot differs")
            if role in ("driver", "observer", "ray_box"):
                require(str(Path(cfg["loaded_library_path"]).resolve(strict=True)) ==
                        binding["binaries"][role]["resolved_path"], "native loaded path differs")
            if role == "driver":
                robot = cfg["robot"]
                require(cfg.get("command_mode") == "tagged"
                        and cfg.get("command_topic") == f"/{robot}/mr3_drive/target"
                        and cfg.get("status_topic") == f"/{robot}/mr3_drive/status", "native driver pipeline differs")
            if role == "recorder":
                require(cfg.get("output_path") == str(directory / name)
                        and cfg.get("use_sim_time") is True and cfg.get("robots") == list(ROBOTS),
                        "actual recorder configuration differs")
            if role == "observer":
                require(cfg.get("read_only") is True and cfg.get("paused_only") is True
                        and cfg.get("physics_type") == "ode" and cfg.get("max_step_size_sec") == .001
                        and cfg["native_ode"]["available"] is True
                        and cfg["native_ode"]["values"]["iters"] == 150,
                        "native observer is not passive ODE150/1ms")
            result.append(row)
    return result


def observer_binding(directory, binding):
    path = directory / "physics_diagnostic_binding.json"
    if not path.exists():
        return None
    value = parse(path.read_bytes())
    epoch = parse((directory / "metadata.json").read_bytes())["epoch"]
    require(value.get("schema") == "mr3-physics-diagnostic-binding-v2"
            and value.get("mode") == "observer_only"
            and value.get("physics_intervention") == "none_observer_only"
            and value.get("observer_paused_only") is True
            and value.get("epoch") == epoch
            and "profile_library" not in value and "profile_output_path" not in value
            and value["observer_library"]["sha256"] == binding["binaries"]["observer"]["sha256"],
            "declared observer is not the bound passive observer-only mode")
    return value


def mapped_lines(raw, expected):
    """Retain the original actual mapping path/device/inode/executable predicate."""
    selected = []
    name = Path(expected["resolved_path"]).name
    for line in raw.decode().splitlines():
        fields = line.split(maxsplit=5)
        if len(fields) != 6 or Path(fields[5]).name not in (name, name + " (deleted)"):
            continue
        major, minor = [int(x, 16) for x in fields[3].split(":")]
        require(fields[5] == expected["resolved_path"]
                and int(fields[4]) == expected["stat"]["ino"]
                and (major, minor) == (os.major(expected["stat"]["dev"]), os.minor(expected["stat"]["dev"])),
                "mapped file differs or is deleted/replaced: " + name)
        selected.append(line)
    if not selected or not any("x" in line.split()[1] for line in selected):
        raise PendingCapture("required executable mapping not yet available: " + name)
    return selected


def check_normal_parameter_records(argv, files):
    """Accept only fixed literal fields in the native generated block YAML.

    This is intentionally not a general YAML parser. Unsupported constructions
    fail closed, so an alias, scalar body or flow mapping cannot supply credit.
    """
    require(not any(x in ("-p", "--param") for x in argv), "inline smoother parameter override is undeclared")
    paths = [argv[i+1] for i,x in enumerate(argv[:-1]) if x == "--params-file"]
    require(paths, "actual smoother parameter files missing")
    require(paths == [row["path"] for row in files], "captured smoother parameter file inventory differs")
    wanted = {"mr3_diagnostic_enabled": "false", "mr3_diagnostic_epoch": "", "mr3_diagnostic_arm": ""}
    seen = {}
    for row in files:
        raw=row["raw"].encode()
        require(sha(raw) == row["sha256"], "captured actual parameter bytes SHA differs")
        for line in row["raw"].splitlines():
            stripped=line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            require("\t" not in line and stripped not in ("---","...")
                    and not stripped.startswith("%")
                    and re.search(r"(^|\s)[&*!][^\s]*",line) is None
                    and re.search(r":\s*[|>][+\-0-9]*\s*(?:#.*)?$",line) is None,
                    "unsupported YAML construction in actual normal parameters")
            if "mr3_diagnostic_" not in line:
                continue
            match=re.fullmatch(r"\s*(mr3_diagnostic_enabled|mr3_diagnostic_epoch|mr3_diagnostic_arm):\s*(false|''|\"\")\s*(?:#.*)?",line)
            require(match is not None,"actual diagnostic parameter is not an approved block literal")
            key,value=match.groups()
            require(key not in seen,"duplicate actual diagnostic parameter")
            value="" if value in ("''",'""') else value
            require(value==wanted[key],"normal diagnostic parameter differs: "+key)
            seen[key]=value
    require(seen == wanted, "explicit normal diagnostic=false configuration missing")


def normal_smoother_parameters(argv):
    """Inspect actual CLI-referenced parameter bytes, not source/default values."""
    read=Reader()
    files=[]
    for i,value in enumerate(argv[:-1]):
        if value == "--params-file":
            path=Path(argv[i+1])
            raw=read(path)
            files.append({"path":str(path),"raw":raw.decode(),"sha256":sha(raw)})
    check_normal_parameter_records(argv,files)
    read.finish()
    return files


def capture_process(identity, worker, inventory, component, binding, proc_root, passive_observer=False):
    tools = binding["tools"]
    pid = identity["pid"]
    current = tools.proc_identity(pid, proc_root)
    if current is None or current.get("state") == "Z":
        raise PendingCapture("same owned process naturally closed before capture")
    require(tools.identity_equal(current, identity), "process identity changed before capture")
    chain = tools.ancestor_chain(current, worker, inventory, proc_root)
    require(chain is not None, "actual process is not this exact worker descendant")
    parent = tools.proc_identity(worker["parent"], proc_root)
    if parent is None or parent["state"] == "Z":
        raise PendingCapture("benchmark parent naturally closed before capture")
    chain = chain + [parent]
    benchmark_argv_raw = (proc_root / str(parent["pid"]) / "cmdline").read_bytes()
    benchmark_argv = [x.decode() for x in benchmark_argv_raw.rstrip(b"\0").split(b"\0")]
    require(benchmark_argv and benchmark_argv[0], "actual benchmark argv missing")
    native_parent_module(benchmark_argv)
    coordinator=tools.proc_identity(parent["parent"],proc_root)
    coordinator_argv_raw=((proc_root/str(coordinator["pid"])/"cmdline").read_bytes()
                          if coordinator is not None and coordinator["state"]!="Z" else None)
    process = proc_root / str(pid)
    argv_raw = (process / "cmdline").read_bytes()
    argv = [x.decode() for x in argv_raw.rstrip(b"\0").split(b"\0")]
    require(bool(argv) and argv[0], "actual process argv missing")
    namespace = None
    if component in ("smoother", "controller"):
        namespace = tools.namespace(argv)
        node = "velocity_smoother" if component == "smoother" else "controller_server"
        node_overrides = [x for x in argv if "__node:=" in x or "__name:=" in x]
        require(node_overrides == ["__node:=" + node]
                or (component == "controller" and not node_overrides),
                "actual native node name differs")
    if component == "recorder":
        require(argv.count("__node:=mr3_odometry_recorder") == 1, "actual recorder node differs")
    expected_exe_role = {"gzserver": "gzserver_executable",
                         "smoother": "smoother_executable", "controller": "controller_executable",
                         "recorder": "odometry_recorder_executable"}.get(component)
    exe = file_proof(process / "exe")
    require(expected_exe_role is not None, "undeclared native executable component")
    expected = binding["binaries"][expected_exe_role]
    require(argv[0] == expected["path"] and exe == {k: expected[k] for k in exe},
            "actual proc exe/argv/device/inode/SHA differs: " + component)
    launch_alias = file_proof(argv[0]) if component == "gzserver" else None
    require(launch_alias is None or launch_alias == exe,
            "actual gzserver launch alias differs from bound proc executable")
    maps = (process / "maps").read_bytes()
    require(component != "gzserver" or b"libgazebo_ros_diff_drive.so" not in maps,
            "old untagged system driver is actually loaded")
    if component == "gzserver" and not passive_observer:
        require(b"libmr3_stop_response_observer" not in maps and
                b"libmr3_physics_diagnostic_profile" not in maps,
                "normal preparation has an undeclared physics observer/profile intervention")
    required = {"gzserver": (("driver", "ray_box", "ode", "observer") if passive_observer else ("driver", "ray_box", "ode")),
                "smoother": ("smoother_core",), "controller": ("rotation_shim",), "recorder": ()}[component]
    mappings = {role: mapped_lines(maps, binding["binaries"][role]) for role in required}
    exe_maps = mapped_lines(maps, exe)
    parameters = normal_smoother_parameters(argv) if component == "smoother" else []
    after_argv = (process / "cmdline").read_bytes()
    after_maps = (process / "maps").read_bytes()
    require(after_argv == argv_raw and file_proof(process / "exe") == exe,
            "actual argv/exe changed during capture")
    require(launch_alias is None or file_proof(argv[0]) == launch_alias,
            "actual gzserver launch alias changed during capture")
    require(all(mapped_lines(after_maps, binding["binaries"][role]) == lines for role,lines in mappings.items())
            and mapped_lines(after_maps, exe) == exe_maps, "required maps changed during capture")
    after_chain = [tools.proc_identity(x["pid"], proc_root) for x in chain]
    for before,after in zip(chain,after_chain):
        if after is None or after.get("state") == "Z":
            raise PendingCapture("same owned ancestor naturally closed during capture")
        require(tools.identity_equal(before,after), "actual ancestor PID reused/changed during capture")
    require((proc_root / str(parent["pid"]) / "cmdline").read_bytes() == benchmark_argv_raw,
            "actual benchmark argv changed during capture")
    for row in parameters:
        require(sha(Path(row["path"]).read_bytes()) == row["sha256"], "actual parameter bytes changed during capture")
    if coordinator_argv_raw is not None:
        require(tools.identity_equal(coordinator,tools.proc_identity(coordinator["pid"],proc_root))
                and (proc_root/str(coordinator["pid"])/"cmdline").read_bytes()==coordinator_argv_raw,
                "actual coordinator identity/argv changed during capture")
    return {"component": component, "robot": namespace, "identity": identity,
            "identity_after": after_chain[0], "argv": argv,
            "argv_raw_sha256": sha(argv_raw), "actual_ancestry": chain, "ancestry_after": after_chain,
            "executable": exe, "gzserver_launch_alias": launch_alias,
            "exe_maps": exe_maps, "maps_raw": maps.decode(),
            "maps_raw_sha256": sha(maps), "maps_after_raw": after_maps.decode(),
            "required_mappings": mappings, "normal_smoother_parameter_files": parameters,
            "benchmark_actual_argv":benchmark_argv,"benchmark_argv_raw_sha256":sha(benchmark_argv_raw),
            "coordinator_identity":coordinator,
            "coordinator_actual_argv":([x.decode()for x in coordinator_argv_raw.rstrip(b"\0").split(b"\0")]
                                        if coordinator_argv_raw is not None else None)}


def capture_episode(directory, binding, *, proc_root=Path("/proc")):
    """Missing live warmup evidence is pending; mismatched established facts fail."""
    directory = Path(directory).resolve()
    read = Reader()
    meta = parse(read(directory / "metadata.json"))
    saved = parse(read(directory / "supervisor_metadata.json"))
    require(meta["freeze"] == binding["freeze"] and saved["epoch"] == meta["epoch"], "episode freeze/epoch differs")
    require(not meta.get("plant_stimulus_arm"), "preparation custody cannot borrow a diagnostic stimulus arm")
    worker = saved["worker_identity"]
    tools = binding["tools"]
    inventory = {}
    for p in proc_root.iterdir():
        if p.name.isdigit():
            current = tools.proc_identity(int(p.name), proc_root)
            if current is not None:
                inventory[current["pid"]] = current
    current_worker = inventory.get(worker["pid"])
    if current_worker is None or current_worker.get("state") == "Z":
        raise PendingCapture("saved worker naturally closed; no active credit")
    require(tools.identity_equal(current_worker,worker), "saved worker PID reused/identity changed")
    worker_argv = [x.decode() for x in (proc_root / str(worker["pid"]) / "cmdline").read_bytes().rstrip(b"\0").split(b"\0")]
    expected_argv = ["/usr/bin/python3", str(WORKSPACE / "ros2_ws/ros2-multi-robot-automap/scripts/mr3_env_worker.py"), "--run-dir", str(directory)]
    require(worker_argv == expected_argv, "actual worker argv borrows another episode")
    config = configurations(directory, binding)
    passive = observer_binding(directory,binding)
    if passive:
        read(directory/"physics_diagnostic_binding.json")
    processes = []
    for identity in inventory.values():
        if identity["pid"] == worker["pid"] or identity["state"] == "Z":
            continue
        if tools.ancestor_chain(identity, worker, inventory, proc_root) is None:
            continue
        argv = (proc_root / str(identity["pid"]) / "cmdline").read_bytes().split(b"\0")
        name = Path(argv[0].decode()).name if argv and argv[0] else ""
        component = {"gzserver": "gzserver", "velocity_smoother": "smoother",
                     "controller_server": "controller", "mr3_odometry_recorder": "recorder"}.get(name)
        if component:
            processes.append(capture_process(identity, worker, inventory, component, binding, proc_root, bool(passive)))
    for component in ("gzserver","recorder"):
        count = sum(x["component"] == component for x in processes)
        require(count <= 1, "duplicate live native component: " + component)
        if count == 0:
            raise PendingCapture("awaiting native component: " + component)
    for component in ("smoother", "controller"):
        selected = [x for x in processes if x["component"] == component]
        require(len({x["robot"] for x in selected}) == len(selected) <= 3,
                "duplicate native " + component + " namespace")
        if len(selected) < 3:
            raise PendingCapture("awaiting three native " + component + " identities")
    gz_pid = next(x["identity"]["pid"] for x in processes if x["component"] == "gzserver")
    require(all(row["configuration"].get("process_id", gz_pid) == gz_pid for row in config
                if row["configuration"].get("robot") in ROBOTS and "physics_" in row["path"]),
            "observer configuration borrows another Gazebo process")
    read.finish()
    return {"directory": str(directory), "epoch": meta["epoch"], "freeze": meta["freeze"],
            "complete": True, "worker_identity": worker, "worker_actual_argv": worker_argv,
            "processes": processes, "configurations": config, "bindings": read.bindings,
            "observer_only_binding": passive,
            "wall_monotonic_ns": time.monotonic_ns()}


def watch(args):
    read = Reader()
    binding = load_binding(args.binding, args.freeze, read=read)
    for p in (args.output, args.ready_file, args.stop_file):
        require(not p.exists(), "watch path already exists: " + str(p))
    ready=write_ready_receipt(args.ready_file,args.freeze,binding["sha256"])
    own=ready["watcher_identity"]
    episodes, attempts, errors = {}, [], []
    while not args.stop_file.exists():
        for directory in episode_directories(args.run_directory):
            if str(directory) in episodes:
                continue
            attempt = {"directory": str(directory), "wall_monotonic_ns": time.monotonic_ns()}
            try:
                episodes[str(directory)] = capture_episode(directory, binding)
                attempt["status"] = "complete"
            except (FileNotFoundError, ProcessLookupError, json.JSONDecodeError, PendingCapture) as error:
                attempt.update(status="pending", error=str(error))
            except (OSError, ValueError, KeyError, TypeError) as error:
                attempt.update(status="error", error=str(error))
                errors.append({"directory":str(directory),"error":str(error)})
            attempts.append(attempt)
        time.sleep(.25)
    stop=parse(read(args.stop_file))
    boundary=read_wait_boundary(read,args.stop_file,stop.get("launch_receipt",{}).get("path",""),args.freeze)
    stop=boundary["stop"]
    if stop.get("native_not_started") is True:
        errors.append({"error":"native was never started; no custody/closure credit"})
    read.finish()
    exclusive(args.output, {"schema": "mr3-native-custody-live-v1", "freeze": args.freeze,
                            "run_directory": str(args.run_directory.resolve()),
                            "binding_sha256": binding["sha256"], "watcher_identity": own,
                            "ready_file": str(args.ready_file), "stop_file": str(args.stop_file),
                            "stop": stop, "episodes": list(episodes.values()), "attempts": attempts,
                            "errors":errors,"passed":not errors,
                            "binding_inputs": read.bindings, "closed": True})
    return 0 if not errors else 1


def strict_closed_episode(directory, freeze, read):
    """Original strict orderly-close predicates, independent of workload addresses."""
    js = lambda name: parse(read(Path(directory) / name))
    meta, worker, sup, sm, nav, native = [js(x) for x in (
        "metadata.json", "summary.json", "supervisor_shutdown.json", "supervisor_metadata.json",
        "nav2_shutdown.json", "native_stop.json")]
    epoch = meta["epoch"]
    require(meta["freeze"] == freeze and all(x.get("epoch") == epoch for x in (worker,sup,sm,nav)), "closed episode identity differs")
    closed = worker["closed"]
    require(closed.get("epoch") == epoch and closed.get("pending_goal_count") == 0
            and set(closed.get("robot_names", [])) == set(ROBOTS)
            and closed.get("navigation_failure") is False, "goal ownership closure failed")
    require(worker.get("failures") == [] and worker.get("native_failures") == []
            and worker.get("launch_returncode") == 0 and worker.get("shutdown_protocol") == PROTOCOL,
            "native worker failure/returncode/protocol differs")
    require(nav == worker.get("nav2_shutdown") and nav.get("success") is True
            and nav.get("failures") == [] and nav.get("protocol") == PROTOCOL
            and nav.get("goal_ownership_closed") == closed, "Nav2 finalization receipt differs")
    require(len(nav["robots"]) == 3 and {r["robot"] for r in nav["robots"]} == set(ROBOTS), "Nav2 robot set differs")
    for robot in nav["robots"]:
        states = robot["states"]
        require(robot["shutdown"]["response"]["success"] is True and len(states) == 6
                and {x["node"] for x in states} == NAV2_NODES
                and all(x["state"] == {"id":4,"label":"finalized"} for x in states), "Nav2 six final states incomplete")
    require(sup.get("worker_returncode") == 0 and sup.get("forced_shutdown") is False
            and sup.get("failed_sample") is False and sup.get("remaining_owned_processes") == []
            and sup.get("remaining_owned_zombies") == [], "supervisor orderly closure failed")
    require(native.get("returncode") == 0 and native.get("method") == "owned_launch_native_stop"
            and native.get("server_clean_exit_recorded") is True, "native stop receipt failed")
    if worker.get("reason") == "external_truncation":
        ack,request=worker.get("training_finalize_ack",{}),worker.get("training_finalize_request",{})
        require(ack.get("kind") == "training_finalize_ack" and ack.get("epoch") == epoch
                and request.get("epoch") == epoch and ack.get("ack_sequence") == request.get("ack_sequence")
                and ack.get("reason") == request.get("reason") == "external_truncation",
                "actual external-finalize evaluator ACK differs")
    starts, exits = {}, {}
    log = read(Path(directory) / "launch.log").decode()
    for number,line in enumerate(log.splitlines(),1):
        for pattern,found in ((r"\[INFO\] \[([^]]+)\]: process started with pid \[(\d+)\]",starts),
                              (r"\[INFO\] \[([^]]+)\]: process has finished cleanly \[pid (\d+)\]",exits)):
            match = re.search(pattern,line)
            if match:
                key = (match[1],int(match[2]))
                require(key not in found, "duplicate native launch identity line")
                found[key] = number
        require(not re.search(r"process has died|process has been terminated|escalating to SIG|killing process|failed to terminate|sending signal 'SIG(?:TERM|KILL)'|MR3_GAZEBO_NATIVE_STOP_ERROR|MR3_ROS_SHUTDOWN_ERROR",line), "native forced/failure exit line")
    require(starts and starts.keys() == exits.keys() and all(exits[k]>v for k,v in starts.items()), "native start/clean exit sets differ")
    saved = sup["owned_processes_seen"] + [sm["worker_identity"]]
    require({pid for _,pid in starts} <= {x["pid"] for x in saved}, "native start missing saved PID/start")
    for prefix,count in (("gzserver-",1),("velocity_smoother-",3),("controller_server-",3),
                         ("mr3_odometry_recorder-",1),("mr3_gazebo_native_stop-",1)):
        require(sum(name.startswith(prefix) for name,_ in starts) == count, "native component exit count differs: " + prefix)
    require(any(name.startswith("mr3_gazebo_native_stop-") and pid == native.get("native_cli_pid") for name,pid in starts), "native stop PID differs")
    return {"epoch":epoch,"saved_identities":saved,"worker_identity":sm["worker_identity"],
            "native_started":len(starts),"native_clean_exits":len(exits),"launch_starts":[{"name":n,"pid":p}for n,p in starts]}


def tagged_pipeline(directory, epoch, read):
    """Original source/SDF/native endpoint identity predicates; no new body math."""
    topology=parse(read(directory/"drive_topology.json"))
    require(topology.get("schema") == "mr3-drive-topology-v1" and topology.get("epoch") == epoch,
            "native driver topology differs")
    for robot in ROBOTS:
        driver=("/"+robot,"turtlebot3_diff_drive")
        target,status=f"/{robot}/mr3_drive/target",f"/{robot}/mr3_drive/status"
        for entries,owner in ((topology["publishers"][target],("/","motion_safety")),
                              (topology["publishers"][status],driver),
                              (topology["target_subscribers"][target],driver)):
            require(len(entries)==1 and all((x["namespace"],x["node"])==owner
                    and x["topic_type"]=="std_msgs/msg/String" for x in entries),
                    "native driver target/status endpoint differs")
        require(not any((x["namespace"],x["node"])==driver for x in topology["legacy_subscribers"][f"/{robot}/cmd_vel"]),
                "tagged driver retains unguarded legacy Twist subscription")
        plugins=ET.fromstring(read(directory/f"drive_model_{robot}.sdf")).findall(".//plugin[@name='turtlebot3_diff_drive']")
        require(len(plugins)==1,"actual tagged drive SDF plugin count differs")
        plugin=plugins[0]
        require(plugin.get("filename")=="libmr3_gazebo_diff_drive.so"
                and plugin.findtext("mr3_tagged_commands")=="true"
                and plugin.findtext("mr3_epoch")==epoch
                and plugin.findtext("mr3_audit_path")==str(directory/f"drive_{robot}.jsonl"),
                "actual tagged drive SDF source differs")


def review(args, *, proc_root=Path("/proc")):
    read = Reader()
    result = {"schema":"mr3-native-custody-closure-review-v1","freeze":args.freeze,
              "errors":[],"episodes":[],"scope":"Strict native custody/closure only; no physical, task or training PASS implied."}
    try:
        require(type(args.expected_episodes)is int and args.expected_episodes>0,"positive exact attempted episode count required")
        binding = load_binding(args.binding,args.freeze,read=read)
        capture = parse(read(args.capture))
        boundary=read_wait_boundary(read,capture["stop_file"],args.launch_receipt,args.freeze)
        launch=boundary["launch"]
        require(launch is not None,"native was never started; no closure credit")
        require(capture.get("schema") == "mr3-native-custody-live-v1" and capture.get("closed") is True
                and capture.get("errors") == [] and capture.get("passed") is True
                and capture["freeze"] == args.freeze and capture["binding_sha256"] == binding["sha256"]
                and capture["run_directory"] == str(args.run_directory.resolve()), "live capture identity differs")
        require(launch["freeze"] == args.freeze and launch["returncode"] == 0,
                "native launcher did not actually return zero")
        stop = boundary["stop"]
        require(stop == capture["stop"] and stop["launch_receipt"] == {"path":str(args.launch_receipt),"sha256":sha(read(args.launch_receipt))}, "capture not closed by exact native wait receipt")
        fifo=read_fifo_receipts(read,args.fifo_receipts,args.freeze,args.expected_episodes)
        directories = episode_directories(args.run_directory)
        require(len(directories) == args.expected_episodes, "attempted episode count differs")
        captures = {row["directory"]:row for row in capture["episodes"]}
        require(len(captures) == len(capture["episodes"]) == args.expected_episodes
                and set(captures) == {str(p.resolve()) for p in directories} == set(fifo), "per-episode capture/FIFO inventory differs")
        persistent=launch.get("launcher_identity_scope")=="persistent_coordinator_not_native_owned"
        if persistent:
            coordinator=launch["coordinator_identity"]
            require(coordinator==launch["launcher_identity"]
                    and launch["benchmark_parent"]["parent"]==coordinator["pid"],
                    "persistent coordinator identity or actual benchmark parent differs")
            current=binding["tools"].proc_identity(coordinator["pid"],proc_root)
            same=binding["tools"].identity_equal(coordinator,current)
            require(same and current["state"]!="Z","stage coordinator not currently the same live saved identity")
            result["coordinator"]={"scope":launch["launcher_identity_scope"],"saved":coordinator,
                                   "current":current,"same_identity_present":same,"live":True,
                                   "counted_native_owned":False,
                                   "final_external_coordinator_absence_required":True}
        else:
            require(launch.get("launcher_identity_scope")in(None,"finite_launcher_native_owned"),
                    "unknown launcher ownership scope")
        saved = [launch["benchmark_parent"],capture["watcher_identity"]]
        if not persistent:saved.append(launch["launcher_identity"])
        for directory in directories:
            local = []
            try:
                closed = strict_closed_episode(directory,args.freeze,read)
                tagged_pipeline(directory,closed["epoch"],read)
                cap = captures[str(directory.resolve())]
                require(cap["complete"] is True and cap["epoch"] == closed["epoch"] == fifo[str(directory.resolve())]["epoch"], "live/closed/FIFO epoch differs")
                worker = closed["worker_identity"]
                require(binding["tools"].identity_equal(worker,cap["worker_identity"])
                        and worker["parent"] == launch["benchmark_parent"]["pid"], "worker/benchmark ancestry differs")
                for path,expected in cap["bindings"].items():
                    raw = read(path)
                    require(sha(raw) == expected["sha256"] and len(raw) == expected["bytes"], "live metadata bytes changed")
                require(configurations(directory,binding) == cap["configurations"], "native compiled configuration changed")
                passive=observer_binding(directory,binding)
                require(passive == cap["observer_only_binding"], "per-episode observer mode changed")
                seen = []
                for process in cap["processes"]:
                    chain = process["actual_ancestry"]
                    require(len(process["ancestry_after"]) == len(chain) and all(
                            binding["tools"].identity_equal(x,y) and y["state"] != "Z"
                            for x,y in zip(chain,process["ancestry_after"])) and len(chain)>=3
                            and binding["tools"].identity_equal(chain[-2],worker)
                            and binding["tools"].identity_equal(chain[-1],launch["benchmark_parent"])
                            and all(chain[i]["parent"] == chain[i+1]["pid"] for i in range(len(chain)-1)), "live actual ancestor chain differs")
                    require(binding["tools"].identity_equal(process["identity"],process["identity_after"])
                            and binding["tools"].identity_equal(process["identity"],chain[0])
                            and all(x["state"] != "Z" for x in chain), "live process closed/reused during capture")
                    raw_maps = process["maps_raw"].encode()
                    require(sha(raw_maps) == process["maps_raw_sha256"], "captured raw maps SHA differs")
                    component = process["component"]
                    expected_roles = {"gzserver":({"driver","observer","ray_box","ode"} if passive else {"driver","ray_box","ode"}),"smoother":{"smoother_core"},"controller":{"rotation_shim"},"recorder":set()}[component]
                    require(set(process["required_mappings"]) == expected_roles, "required mapping role set differs")
                    if component == "gzserver":
                        require(b"libgazebo_ros_diff_drive.so" not in raw_maps and (passive or (
                            b"libmr3_stop_response_observer" not in raw_maps and
                            b"libmr3_physics_diagnostic_profile" not in raw_maps)), "captured undeclared driver/physics intervention")
                    for role,lines in process["required_mappings"].items():
                        require(mapped_lines(raw_maps,binding["binaries"][role]) == lines
                                and mapped_lines(process["maps_after_raw"].encode(),binding["binaries"][role]) == lines, "captured required mapping proof differs")
                    exe_role = {"gzserver":"gzserver_executable","smoother":"smoother_executable","controller":"controller_executable","recorder":"odometry_recorder_executable"}.get(component)
                    if exe_role:
                        expected = binding["binaries"][exe_role]
                        require(process["executable"] == {k:expected[k]for k in process["executable"]}
                                and process["argv"][0] == expected["path"], "captured actual executable differs")
                    require(process["gzserver_launch_alias"] == (process["executable"] if component == "gzserver" else None),
                            "captured gzserver launch alias differs")
                    require(mapped_lines(raw_maps,process["executable"]) == process["exe_maps"]
                            and mapped_lines(process["maps_after_raw"].encode(),process["executable"]) == process["exe_maps"],
                            "captured actual executable mappings differ")
                    require(sha(b"\0".join(x.encode() for x in process["argv"])+b"\0") == process["argv_raw_sha256"],
                            "actual argv original bytes SHA differs")
                    require(process["benchmark_actual_argv"] == launch.get("argv",launch.get("command_argv")),
                            "captured benchmark actual argv differs from native launch receipt")
                    native_parent_module(process["benchmark_actual_argv"])
                    if persistent:
                        require(binding["tools"].identity_equal(process["coordinator_identity"],coordinator)
                                and process["coordinator_actual_argv"]==launch["coordinator_actual_argv"],
                                "persistent coordinator was not the actual captured native ancestor/argv")
                    if component in ("smoother","controller"):
                        require(binding["tools"].namespace(process["argv"]) == process["robot"], "captured namespace differs")
                        node="velocity_smoother" if component=="smoother" else "controller_server"
                        node_overrides=[x for x in process["argv"] if "__node:=" in x or "__name:=" in x]
                        require(node_overrides==["__node:="+node]
                                or (component=="controller" and not node_overrides),
                                "captured native node name differs")
                    if component == "smoother":
                        check_normal_parameter_records(process["argv"],process["normal_smoother_parameter_files"])
                    if component == "recorder":
                        require(process["argv"].count("__node:=mr3_odometry_recorder")==1,"captured recorder node differs")
                    prefix = {"gzserver":"gzserver-","smoother":"velocity_smoother-","controller":"controller_server-","recorder":"mr3_odometry_recorder-"}[component]
                    require(any(row["pid"] == process["identity"]["pid"] and row["name"].startswith(prefix) for row in closed["launch_starts"]), "actual captured process is absent from native launch log")
                    seen.append((component,process["robot"]))
                    saved.extend(chain)
                require(seen.count(("gzserver",None)) == seen.count(("recorder",None)) == 1
                        and len(seen)==8 and all(seen.count((c,r))==1 for c in ("smoother","controller")for r in ROBOTS), "native captured component identities incomplete")
                gz=next(x for x in cap["processes"] if x["component"]=="gzserver")
                ledger_raw=read(directory/"ray_box_corrector.jsonl")
                config=next(x for x in cap["configurations"] if Path(x["path"]).name=="ray_box_corrector.jsonl")
                meta=parse(read(directory/"metadata.json"))
                corrector_review=binding["corrector_tools"].ledger_review(
                    ledger_raw,binding["corrector_binding"],closed["epoch"],gz["identity"]["pid"],
                    binding["corrector_binding"]["world_names"][meta["scene"]],config["first_line_sha256"])
                if args.require_parameters:
                    parameters = parse(read(directory/"actual_nav2_parameters.json"))
                    require(parameters.get("passed") is True and parameters.get("freeze") == args.freeze
                            and parameters.get("epoch") == closed["epoch"] and len(parameters.get("nodes",{})) == 9, "actual nine parameter readbacks failed")
                saved.extend(closed["saved_identities"])
                result["episodes"].append({"directory":str(directory),**closed,
                                           "corrector_closed_ledger":corrector_review,"passed":True})
            except (OSError,ValueError,KeyError,TypeError) as error:
                local.append(str(error))
                result["episodes"].append({"directory":str(directory),"passed":False,"errors":local})
                result["errors"].extend(str(directory)+": "+x for x in local)
        unique = {}
        for identity in saved:
            require(type(identity.get("pid")) is int and identity["pid"]>0
                    and type(identity.get("start_ticks")) is int and identity["start_ticks"]>0, "invalid saved PID/start")
            unique[(identity["pid"],identity["start_ticks"])] = identity
        result["identities"] = []
        for (pid,start),identity in sorted(unique.items()):
            current = binding["tools"].proc_identity(pid,proc_root)
            gone = current is None or current["start_ticks"] != start
            require(gone,"saved PID/start remains, including zombie: "+str((pid,start)))
            result["identities"].append({"saved":identity,"current":current,"gone":gone})
        read.finish()
        result["bindings"] = read.bindings
        result["all_native_owned_gone"]=True
    except (OSError,ValueError,KeyError,TypeError,IndexError) as error:
        result["errors"].append(str(error))
    result["passed"] = not result["errors"] and len(result["episodes"]) == args.expected_episodes
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    subs=parser.add_subparsers(dest="mode",required=True)
    for name in ("watch","review"):
        child=subs.add_parser(name)
        for field in ("run-directory","binding","output"):
            child.add_argument("--"+field,type=Path,required=True)
        child.add_argument("--freeze",required=True)
        if name=="watch":
            child.add_argument("--ready-file",type=Path,required=True)
            child.add_argument("--stop-file",type=Path,required=True)
        else:
            for field in ("capture","launch-receipt","fifo-receipts"):
                child.add_argument("--"+field,type=Path,required=True)
            child.add_argument("--expected-episodes",type=int,required=True)
            child.add_argument("--require-parameters",action="store_true")
    args=parser.parse_args()
    if args.output.exists():parser.error("exclusive output exists")
    if args.mode=="watch":return watch(args)
    result=review(args)
    exclusive(args.output,result)
    print(json.dumps({"passed":result["passed"],"errors":result["errors"],"output":str(args.output)}))
    return 0 if result["passed"] else 1


if __name__=="__main__":raise SystemExit(main())
