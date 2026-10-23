"""Reach-only native custody with an exact reversible private source projection.

The original PID/start, ancestry, alias, maps, actual-wait and orderly-close
predicates execute again on the new artifacts. No old receipt supplies credit.
Only schema identities and the sixth native compiled source are projected;
reach profile/source/producer checks are explicit additional conjunctions.
"""
import argparse
from decimal import Decimal
import hashlib
import gzip
import io
import json
from pathlib import Path
import shlex
import types
import subprocess

from .supervisor import WORKSPACE, INITIAL_ENCODER_ACTUATION_PROFILE
from .audit_reach_runtime import geometry_rule, DEFAULT_GEOMETRY_RULE, SUPPORT_GEOMETRY_RULE

CONTRACT = "mr3-reach-v1"
PROTOCOL = "mr3-controlled-execution-phase-v2"
WIRELESS = Path("ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl")
HELPER = WIRELESS / "mr3_learning/native_custody.py"
HELPER_SHA256 = "4edcdb6b33105e274c1c908c9d78e8c5d24461ff6733ed0f976e41bad3f2d928"
SCHEMA_BINDING = "mr3-reach-native-custody-binding-v1"
SCHEMA_READY = "mr3-reach-native-custody-ready-v1"
SCHEMA_STOP = "mr3-reach-native-custody-stop-v1"
SCHEMA_WAIT = "mr3-reach-native-wait-v1"
SCHEMA_CAPTURE = "mr3-reach-native-custody-live-v1"
SCHEMA_CLOSURE = "mr3-reach-native-custody-closure-review-v1"
SCHEMA_VERIFIED = "mr3-reach-native-custody-verified-binding-v1"
SCHEMA_FIFO = "mr3-reach-peer-control-fifo-review-v1"
SCHEMA_BUILD_BRIDGE = "mr3-reach-native-build-evidence-bridge-v1"
INITIAL_ENCODER_BUILD_SCOPE = "initial-zero-encoder-hold-v1; actual-new-build"
INITIAL_ENCODER_MANIFEST_SCHEMA = "mr3-initial-encoder-driver-build-manifest-v1"
INITIAL_ENCODER_BUILD_SCRIPT = WIRELESS / "report/assets/20261023_mr3_p2a_v59_encoder_profile/checks/native_build_v1/build_native_ros_v1.sh"
INITIAL_ENCODER_BUILD_SCRIPT_SHA256 = "06964d045b1e16ca9e6a51abe0ae6cce097d57dbe732b757744c8306025158b9"
INITIAL_ENCODER_HEADER = "ros2_ws/ros2-multi-robot-automap/src/multi_robot/include/multi_robot/mr3_initial_zero_encoder_servo.hpp"
INITIAL_ENCODER_SOURCE_PROFILE = WIRELESS / "report/assets/20261023_mr3_p2a_v59_encoder_profile/initial_encoder_source_profile_v1.json"
# Pending is deliberately ineligible; seal only after the concrete source inverse and CPU build.
INITIAL_ENCODER_SOURCE_PROFILE_SHA256 = 'efc6261cb38ee631ea57fe965a810b035f2bc5dc818308ed8e3448cf105271f3'
INITIAL_ENCODER_BASELINES = {
    "ros2_ws/ros2-multi-robot-automap/src/multi_robot/src/mr3_gazebo_diff_drive.cpp": (
        "1fa55bc56d5bb9e230d4b397f962d83b1604b278",
        "ros2_ws/ros2-multi-robot-automap/src/multi_robot/src/mr3_gazebo_diff_drive.cpp",
        "df307bd4d24abb588ded81752c4b2750cfbc3bb01986295b2e850561811e058a"),
    "ros2_ws/ros2-multi-robot-automap/src/multi_robot/CMakeLists.txt": (
        "1fa55bc56d5bb9e230d4b397f962d83b1604b278",
        "ros2_ws/ros2-multi-robot-automap/src/multi_robot/CMakeLists.txt",
        "e7618063e54963e91c8df1661c2fd22b413a6d09adf850b13e92c15ceac6abbf"),
    INITIAL_ENCODER_HEADER: (
        "b6af48cfe88b73a633d0e7552b88c3489900391a",
        str(WIRELESS / "report/assets/20261023_mr3_p2a_v58_encoder_hold/initial_zero_encoder_servo_v1.hpp"),
        "d7b627dd55b764c5246ad33eddb12954b50409c5bf430584a1b1126673971a97")}
V15_WAIT_SCHEMA = "mr3-v15-finite-preparation-actual-child-wait-v1"
V15_BUILD_ARGV = ["/bin/bash", "-c", "source /opt/ros/humble/setup.bash; exec /usr/bin/python3 /usr/bin/colcon build --symlink-install --packages-select multi_robot --event-handlers console_direct+ --cmake-args -DBUILD_TESTING=ON"]
V15_VERIFY_SCRIPT = WIRELESS / "report/assets/20261019_mr3_p2a_v15/verify_preparation_v1.py"
V15_FLAGS_ARCHIVE = WIRELESS / "report/assets/20261019_mr3_p2a_v15/checks/static_preparation_attempt_v2/actual_compile_flags.make"
DRIVER_FLAGS = Path("ros2_ws/ros2-multi-robot-automap/build/multi_robot/CMakeFiles/mr3_gazebo_diff_drive.dir/flags.make")
DRIVER_DEFINITIONS = {
    "MR3_DRIVE_SOURCE_SHA256":"compiled_source_sha256",
    "MR3_DRIVE_HEADER_SHA256":"compiled_header_sha256",
    "MR3_DRIVE_HELPER_SHA256":"compiled_helper_sha256",
    "MR3_DRIVE_TARGET_SHA256":"compiled_target_contract_sha256",
    "MR3_ODOMETRY_JSON_HEADER_SHA256":"compiled_odometry_json_sha256",
    "MR3_DRIVE_FEED_HEADER_SHA256":"compiled_drive_feed_sha256"}
ROBOTS = ("tb1", "tb2", "tb3")
BINARY_ROLES = {"driver", "observer", "ray_box", "ode", "smoother_core",
                "smoother_executable", "odometry_recorder_executable",
                "controller_executable", "rotation_shim", "gzserver_executable"}
COMPILED_FIELDS = {
    "driver": {"compiled_source_sha256", "compiled_header_sha256", "compiled_helper_sha256",
               "compiled_target_contract_sha256", "compiled_odometry_json_sha256", "compiled_drive_feed_sha256"},
    "recorder": {"compiled_source_sha256", "compiled_odometry_json_sha256"},
    "observer": {"compiled_source_sha256"},
    "ray_box": {"compiled_source_sha256", "compiled_collision_source_sha256", "compiled_collision_header_sha256"}}
SCHEMA_CHANGES = (
    ("native-custody-ready-v1", SCHEMA_READY, 2),
    ("mr3-native-custody-stop-v1", SCHEMA_STOP, 1),
    ("mr3-native-custody-binding-v1", SCHEMA_BINDING, 1),
    ("mr3-native-custody-verified-binding-v1", SCHEMA_VERIFIED, 1),
    ("mr3-native-custody-live-v1", SCHEMA_CAPTURE, 2),
    ("mr3-native-custody-closure-review-v1", SCHEMA_CLOSURE, 1),
)
SOURCE_CHANGES = SCHEMA_CHANGES + ((
    '"compiled_target_contract_sha256", "compiled_odometry_json_sha256"',
    '"compiled_target_contract_sha256", "compiled_odometry_json_sha256", "compiled_drive_feed_sha256"', 1),)
PURE = "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/"
REQUIRED_SOURCES = tuple(PURE + value for value in (
    "motion_safety.py", "mr3_reach_runtime.py", "mr3_reach_geometry.py",
    "mr3_velocity_metric.py", "mr3_safety_intent.py", "mr3_information.py",
    "peer_obstacles.py", "mr3_control_phase.py", "mr3_motion_control.py",
    "mr3_drive_phase.py", "mr3_episode.py", "mr3_motion_safety.py")) + tuple(str(WIRELESS / "mr3_learning" / value) for value in (
    "native_custody.py", "native_custody_reach.py", "audit_reach_cadence.py",
    "audit_odometry_cadence.py", "audit_reach_runtime.py", "supervisor.py")) + (
    "ros2_ws/ros2-multi-robot-automap/scripts/mr3_env_worker.py",
    "ros2_ws/ros2-multi-robot-automap/src/multi_robot/launch/gazebo_multirobot_mapping_with_nav2.launch.py",
    "ros2_ws/ros2-multi-robot-automap/src/multi_robot/CMakeLists.txt")
SUPPORT_SOURCES = (PURE+"mr3_reach_support.py", str(WIRELESS/"mr3_learning/reach_support_replay.py"))


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def project_source(raw):
    """No AST/function deletion; exact complete source recovery is mandatory."""
    require(sha(raw) == HELPER_SHA256, "immutable native custody helper differs")
    projected = raw
    for old, new, count in SOURCE_CHANGES:
        require(projected.count(old.encode()) == count, "custody projection occurrence differs: " + old)
        require(new.encode() not in projected, "projected custody token already exists")
        projected = projected.replace(old.encode(), new.encode())
    inverse = projected
    for old, new, count in reversed(SOURCE_CHANGES):
        require(inverse.count(new.encode()) == count, "custody inverse occurrence differs")
        inverse = inverse.replace(new.encode(), old.encode())
    require(inverse == raw and sha(inverse) == HELPER_SHA256, "custody whole-source inverse differs")
    return projected, {"helper_sha256": HELPER_SHA256, "projected_sha256": sha(projected),
        "inverse_sha256": sha(inverse), "exact_whole_source_inverse": True,
        "changes": [{"old":old,"new":new,"count":count} for old,new,count in SOURCE_CHANGES]}


def profile_metadata(directory, freeze, read, *, reach_geometry_rule=None, actuation_profile=None):
    meta = json.loads(read(Path(directory) / "metadata.json"))
    require(meta.get("freeze") == freeze and meta.get("safety_contract") == CONTRACT
            and meta.get("quantum_steps") == 20 and meta.get("execution_phase_protocol") == PROTOCOL
            and meta.get("reset_handshake") == "paused-controlled-state-peer-guard-storage-v2",
            "legacy profile/execution metadata cannot acquire reach custody credit")
    require(initial_encoder_profile(meta) == actuation_profile,
            "custody binding and episode actuation profiles differ")
    if actuation_profile is not None:
        saved = json.loads(read(Path(directory)/"supervisor_metadata.json"))
        require(saved.get("epoch") == meta["epoch"] and initial_encoder_profile(saved) == actuation_profile,
                "supervisor/native actuation profiles differ")
    rule = geometry_rule(meta)
    if reach_geometry_rule is not None:
        require(rule == reach_geometry_rule, "custody binding and native episode geometry rules differ")
    if rule != DEFAULT_GEOMETRY_RULE:
        saved = json.loads(read(Path(directory)/"supervisor_metadata.json"))
        require(saved.get("epoch") == meta["epoch"] and geometry_rule(saved) == rule,
                "supervisor/native custody geometry rules differ")
    return meta


def binding_sources(bound, root):
    """All declared bytes are checked by the original loader; require the new chain."""
    doc = bound["document"]
    require(doc.get("safety_contract") == CONTRACT and doc.get("execution_phase_protocol") == PROTOCOL,
            "binding is not the explicit reach/v2 contract")
    profile = initial_encoder_profile(doc)
    rule = geometry_rule(doc)
    required_sources = REQUIRED_SOURCES + (SUPPORT_SOURCES if rule == SUPPORT_GEOMETRY_RULE else ())
    sources = {str(Path(row["path"]) if Path(row["path"]).is_absolute()
                   else Path(root) / row["path"]): row["sha256"] for row in doc["source_bindings"]}
    require(all(str(Path(root)/name) in sources for name in required_sources),
            "complete new runtime/custody/cadence entry source chain is unbound")
    if profile is not None:
        extra = doc.get("initial_encoder_compiled_source")
        require(type(extra) is dict and extra.get("path") == INITIAL_ENCODER_HEADER and
                sources.get(str(Path(root)/INITIAL_ENCODER_HEADER)) == extra.get("sha256"),
                "new encoder helper is absent from the complete custody source chain")
    wrappers = doc.get("qualification_wrappers")
    require(type(wrappers) is list and wrappers, "actual qualification wrappers must be explicit")
    names = set()
    for row in wrappers:
        path = Path(row["path"])
        path = path if path.is_absolute() else Path(root)/path
        require(str(path) not in names and sources.get(str(path)) == row["sha256"],
                "qualification wrapper is duplicate or not bound to this whole source freeze")
        names.add(str(path))
    return {"required_source_count":len(required_sources), "declared_source_count":len(sources),
            **({"reach_geometry_rule":rule} if rule != DEFAULT_GEOMETRY_RULE else {}),
            "qualification_wrappers":wrappers,
            **({"actuation_profile":profile} if profile is not None else {})}


def frozen_artifact(spec, freeze, root, read):
    path = Path(spec["path"])
    path = path if path.is_absolute() else Path(root)/path
    relative = str(path.resolve(strict=True).relative_to(Path(root).resolve()))
    raw = read(path)
    require(sha(raw) == spec["sha256"] and
            subprocess.check_output(["git","show",freeze+":"+relative],cwd=root) == raw,
            "historical build artifact is not the exact source-bound original: "+relative)
    return raw


def actual_wait_math(value):
    """Historical wait facts are rechecked, never replaced with a new clock."""
    require(value.get("schema") == V15_WAIT_SCHEMA and value.get("actual_waited") is True
            and type(value.get("actual_returncode")) is int and value["actual_returncode"] == 0
            and value.get("passed") is True and value.get("source_unchanged") is True
            and value.get("native_admission") is False,
            "historical build/preparation wait did not actually pass")
    for key in ("started_monotonic_ns","ended_monotonic_ns"):
        require(type(value.get(key)) is int and value[key] > 0, "actual wait clock is not a positive integer")
    duration = value["ended_monotonic_ns"]-value["started_monotonic_ns"]
    declared = Decimal(str(value["actual_child_wait_seconds"]))
    require(duration > 0 and declared.is_finite() and declared == Decimal(duration)/10**9,
            "actual child wait duration differs from its original nanosecond clocks")
    for name in ("coordinator_identity","child_identity"):
        identity = value[name]
        require(all(type(identity.get(k)) is int and identity[k] > 0 for k in ("pid","start_ticks")),
                "actual historical wait lacks positive typed PID/start")
    require(value["child_identity"].get("parent") == value["coordinator_identity"]["pid"],
            "actual historical child is not its recorded waiting coordinator descendant")
    require(type(value.get("source_before")) is list and value["source_before"]
            and value["source_before"] == value.get("source_after"), "actual build source changed during wait")
    return str(Decimal(duration)/10**9)


def initial_encoder_profile(document):
    if "actuation_profile" not in document:
        require("initial_encoder_compiled_source" not in document,
                "new encoder source lacks its mandatory actuation profile")
        return None
    value = document["actuation_profile"]
    require(type(value) is str and value == INITIAL_ENCODER_ACTUATION_PROFILE,
            "unknown or empty initial encoder actuation profile")
    return value


def verify_initial_encoder_source_profile(freeze, root, read):
    expected = INITIAL_ENCODER_SOURCE_PROFILE_SHA256
    require(type(expected) is str and len(expected) == 64,
            "initial encoder source derivation has not been sealed")
    path = Path(root) / INITIAL_ENCODER_SOURCE_PROFILE
    raw = frozen_artifact({"path":str(path), "sha256":expected}, freeze, root, read)
    document = json.loads(raw)
    require(document.get("schema") == "mr3-initial-encoder-source-derivation-v1" and
            document.get("actuation_profile") == INITIAL_ENCODER_ACTUATION_PROFILE and
            type(document.get("files")) is list and
            {row["path"] for row in document["files"]} == set(INITIAL_ENCODER_BASELINES) and
            len(document["files"]) == len(INITIAL_ENCODER_BASELINES),
            "initial encoder whole-source derivation inventory differs")
    proofs = {}
    for row in document["files"]:
        previous_freeze, previous_path, previous_sha = INITIAL_ENCODER_BASELINES[row["path"]]
        require((row.get("previous_freeze"), row.get("previous_path"), row.get("previous_sha256")) ==
                (previous_freeze, previous_path, previous_sha), "encoder source baseline differs")
        current = frozen_artifact({"path":str(Path(root)/row["path"]),
                                   "sha256":row["candidate_sha256"]}, freeze, root, read)
        edits = row["inverse_edits"]
        require(type(edits) is list and edits, "encoder source inverse is absent")
        previous_end = -1
        for edit in edits:
            start, end = edit["candidate_start"], edit["candidate_end"]
            require(type(start) is int and type(end) is int and
                    0 <= start <= end <= len(current) and start >= previous_end,
                    "encoder inverse edits overlap or exceed the exact source")
            require(current[start:end] == bytes.fromhex(edit["candidate_hex"]),
                    "encoder inverse slice differs from sealed source")
            previous_end = end
        restored = current
        for edit in reversed(edits):
            restored = (restored[:edit["candidate_start"]] + bytes.fromhex(edit["previous_hex"]) +
                        restored[edit["candidate_end"]:])
        baseline = subprocess.check_output(["git", "show", previous_freeze+":"+previous_path], cwd=root)
        require(restored == baseline and sha(restored) == previous_sha,
                "encoder inverse does not recover the complete previous source")
        proofs[row["path"]] = {"sha256":sha(current), "bytes":len(current),
            "previous_freeze":previous_freeze, "previous_sha256":previous_sha,
            "whole_source_inverse":True, "inverse_edits":len(edits)}
    return {"profile_path":str(path), "sha256":sha(raw), "sources":proofs,
            "unchanged_behavior_outside_declared_source_edits":True,
            "new_actuation_requires_independent_replay":True}


def verify_initial_encoder_new_build(bridge, raw, freeze, bound, root, read, module):
    require(initial_encoder_profile(bound["document"]) == INITIAL_ENCODER_ACTUATION_PROFILE and
            bridge.get("schema") == SCHEMA_BUILD_BRIDGE and bridge.get("safety_contract") == CONTRACT and
            bridge.get("scope") == INITIAL_ENCODER_BUILD_SCOPE and bridge.get("passed") is True and
            bridge.get("actuation_profile") == INITIAL_ENCODER_ACTUATION_PROFILE and "freeze" not in bridge,
            "new driver build lacks the mandatory explicit encoder profile")
    source_proof = verify_initial_encoder_source_profile(freeze, root, read)
    extra = bound["document"].get("initial_encoder_compiled_source")
    require(type(extra) is dict and extra.get("path") == INITIAL_ENCODER_HEADER,
            "new driver requires its separate seventh compiled helper source")
    helper = frozen_artifact(extra, freeze, root, read)
    require(sha(helper) == source_proof["sources"][INITIAL_ENCODER_HEADER]["sha256"],
            "new driver helper is not the sealed candidate source")
    build_raw = frozen_artifact(bridge["actual_wait"], freeze, root, read)
    build = module.parse(build_raw)
    require(build.get("schema") == "mr3-reach-outer-actual-wait-v1" and build.get("scope") == "cpu" and
            build.get("actual_waited") is True and type(build.get("actual_returncode")) is int and
            build["actual_returncode"] == 0 and build.get("passed") is True and build.get("errors") == [] and
            build.get("source_unchanged") is True and build.get("source_before") == build.get("source_after") and
            type(build.get("source_before")) is list and build["source_before"],
            "new driver build has no actual successful unchanged-source CPU wait")
    start, end = build["started_monotonic_ns"], build["ended_monotonic_ns"]
    require(type(start) is int and type(end) is int and 0 < start < end and
            Decimal(build["actual_child_wait_seconds"]) == Decimal(end-start)/10**9,
            "new driver build actual clock arithmetic differs")
    for name in ("coordinator_identity", "child_identity"):
        identity = build[name]
        require(all(type(identity.get(k)) is int and identity[k] > 0 for k in ("pid", "start_ticks")),
                "new driver actual build lacks typed saved PID/start")
    script = Path(root)/INITIAL_ENCODER_BUILD_SCRIPT
    frozen_artifact({"path":str(script),"sha256":INITIAL_ENCODER_BUILD_SCRIPT_SHA256},freeze,root,read)
    require(build["child_identity"].get("parent") == build["coordinator_identity"]["pid"] and
            Path(build["cwd"]) == Path(root)/WIRELESS and
            build["actual_argv"] == ["/bin/bash","--noprofile","--norc",str(script)],
            "new driver receipt is not the declared actual multi_robot build")
    require(bridge.get("commands") == [{"argv":build["actual_argv"], "returncode":0, "observed_returncode":0}],
            "new build command facts differ from the actual wait")
    console = frozen_artifact(build["console"], freeze, root, read)
    require(sha(console) == build["console"]["sha256"], "new build console differs")
    inputs = {}
    for source in build["source_before"]:
        require(source["path"] not in inputs, "duplicate new-build source")
        content = read(Path(source["path"]))
        require(sha(content) == source["sha256"] and len(content) == source["bytes"],
                "new-build current source differs from actual before/after")
        path = Path(source["path"])
        if path.is_relative_to(root):
            require(subprocess.check_output(["git", "show",freeze+":"+str(path.relative_to(root))],cwd=root) == content,
                    "new-build source differs from the new exact freeze")
        inputs[source["path"]] = source
    manifest_raw = frozen_artifact(bridge["manifest"], freeze, root, read)
    manifest = module.parse(manifest_raw)
    require(manifest.get("schema") == INITIAL_ENCODER_MANIFEST_SCHEMA and manifest.get("passed") is True and
            manifest.get("source_unchanged") is True and manifest.get("actual_wait") == bridge["actual_wait"],
            "new-build manifest does not bind its actual successful wait")
    driver = bound["binaries"]["driver"]
    actual = module.file_proof(driver["path"])
    require(all(actual[k] == driver[k] for k in ("resolved_path", "sha256", "bytes")) and
            ("stat" not in driver or actual["stat"] == driver["stat"]), "new actual driver ELF identity differs")
    library = manifest["library"]
    require(library["path"] == driver["path"] and library["real_path"] == driver["resolved_path"] and
            library["sha256"] == driver["sha256"] and library["bytes"] == driver["bytes"],
            "new-build manifest library differs from this actual driver binding")
    elf = read(driver["path"])
    require(extra["sha256"].encode() in elf, "actual new ELF lacks the seventh helper SHA")
    sources = {row["path"]:row for row in manifest["sources"]}
    require(len(sources) == len(manifest["sources"]), "duplicate manifest compiled source")
    fields = bound["document"]["compiled_sources"]["driver"]
    for spec in [*fields.values(), extra]:
        path = Path(spec["path"]); path = path if path.is_absolute() else Path(root)/path
        expected = {"path":str(path), "sha256":spec["sha256"], "bytes":len(read(path))}
        require(all(name in inputs and name in sources and
                    all(inputs[name][k] == sources[name][k] == value for k,value in expected.items())
                    for name in [str(path)]), "compiled source is missing from real build and ELF manifest")
    cmake = str(Path(root)/"ros2_ws/ros2-multi-robot-automap/src/multi_robot/CMakeLists.txt")
    require(cmake in inputs and sha(read(cmake)) == inputs[cmake]["sha256"], "CMake lacks actual new-build source proof")
    archive = manifest["archived_library_gzip"]
    packed = frozen_artifact(archive, freeze, root, read)
    with gzip.GzipFile(fileobj=io.BytesIO(packed)) as stream:
        unpacked = stream.read(driver["bytes"]+1)
    require(len(unpacked) == archive["raw_bytes"] == driver["bytes"] and
            sha(unpacked) == archive["raw_sha256"] == driver["sha256"] and unpacked == elf,
            "new driver archive does not restore the exact current ELF")
    archived_flags = frozen_artifact(bridge["compiler_flags_archive"], freeze, root, read)
    flags = manifest["compiler_flags"]; flags_path = Path(root)/DRIVER_FLAGS
    require(flags["path"] == str(flags_path) and flags["real_path"] == str(flags_path.resolve(strict=True)) and
            flags["sha256"] == sha(archived_flags) and flags["bytes"] == len(archived_flags) and
            read(flags_path) == archived_flags, "new driver actual and archived compiler flags differ")
    assignments = {}
    for label in ("CXX_DEFINES", "CXX_FLAGS"):
        lines = [line.split(" = ",1)[1] for line in archived_flags.decode().splitlines() if line.startswith(label+" = ")]
        require(len(lines) == 1, "new compiler flags assignment missing or duplicated")
        assignments[label] = shlex.split(lines[0])
    tokens = assignments["CXX_DEFINES"]+assignments["CXX_FLAGS"]
    expected_macros = {macro:fields[field]["sha256"] for macro,field in DRIVER_DEFINITIONS.items()}
    expected_macros["MR3_DRIVE_ENCODER_SERVO_SHA256"] = extra["sha256"]
    for macro,digest in expected_macros.items():
        definitions = [token for token in tokens if token.split("=",1)[0] == "-D"+macro]
        require(definitions == ['-D'+macro+'="'+digest+'"'] and "-U"+macro not in tokens,
                "new actual compiler flags lack exactly one current source SHA: "+macro)
    options = assignments["CXX_FLAGS"]
    require(options.count("-fno-fast-math") == 1 and options.count("-ffp-contract=off") == 1 and
            not any(token in ("-ffast-math", "-Ofast") or
                    (token.startswith("-ffp-contract=") and token != "-ffp-contract=off") for token in tokens),
            "new driver numeric compile options differ")
    return {"schema":SCHEMA_BUILD_BRIDGE, "passed":True, "bridge_sha256":sha(raw),
        "scope":INITIAL_ENCODER_BUILD_SCOPE, "actuation_profile":INITIAL_ENCODER_ACTUATION_PROFILE,
        "driver_sha256":driver["sha256"], "initial_encoder_compiled_source":extra,
        "actual_wait_seconds":build["actual_child_wait_seconds"], "source_derivation":source_proof,
        "compiled_source_fields":sorted([*fields, "compiled_encoder_servo_sha256"]),
        "new_build_executed":True, "native_admission":False}


def verify_build_bridge(bridge_path, freeze, bound, *, root=WORKSPACE, read=None):
    """Revalidate preserved V15 execution against the current actual driver ELF.

    This bridge is not a new build receipt. Its command row must be the exact
    recorded original command/returncode; original artifacts, compiler flags
    and console bytes remain frozen inputs. CMake is bound by the actual build
    source inventory, not invented as an entry of the old Python/CPP/HPP-only
    manifest. A current driver bridge is mandatory, while
    unchanged historical smoother/corrector receipts keep their original gates.
    """
    module, _ = load_implementation(root)
    own_reader = read is None
    read = module.Reader() if read is None else read
    path = Path(bridge_path)
    raw = read(path)
    bridge = module.parse(raw)
    if bridge.get("scope") == INITIAL_ENCODER_BUILD_SCOPE:
        frozen_artifact({"path":str(path),"sha256":sha(raw)},freeze,root,read)
        result = verify_initial_encoder_new_build(bridge, raw, freeze, bound, root, read, module)
        if own_reader:
            read.finish()
        return result
    require(initial_encoder_profile(bound["document"]) is None,
            "new initial encoder driver cannot borrow the historical no-new-build bridge")
    require(bridge.get("schema") == SCHEMA_BUILD_BRIDGE and bridge.get("safety_contract") == CONTRACT
            and bridge.get("passed") is True and "freeze" not in bridge
            and bridge.get("scope") == "existing-v15-build-revalidated; no-new-build",
            "unknown or mislabelled historical build evidence bridge")
    frozen_artifact({"path":str(path),"sha256":sha(raw)},freeze,root,read)

    def original(name):
        return module.parse(frozen_artifact(bridge[name],freeze,root,read))

    build, check, result, manifest = [original(k) for k in
        ("actual_wait","manifest_actual_wait","manifest_result","manifest")]
    durations = [actual_wait_math(value) for value in (build,check)]
    require(build["actual_argv"] == V15_BUILD_ARGV
            and Path(build["cwd"]) == Path(root)/"ros2_ws/ros2-multi-robot-automap",
            "historical receipt is not the declared actual multi_robot build")
    require(json.dumps(bridge.get("commands"),sort_keys=True) == json.dumps([{"argv":build["actual_argv"],
            "returncode":build["actual_returncode"],"observed_returncode":build["actual_returncode"]}],
            sort_keys=True),
            "bridge commands are not exact facts extracted from the original build wait")
    for wait in (build,check):
        console = frozen_artifact(wait["console"],freeze,root,read)
        require(len(console) == wait["console"]["bytes"], "original actual-wait console bytes differ")
        seen = set()
        for source in wait["source_before"]:
            require(source["path"] not in seen, "duplicate original build source")
            seen.add(source["path"])
            content = frozen_artifact(source,freeze,root,read)
            require(len(content) == source["bytes"], "original build source snapshot size differs")
    verifier = str(Path(root)/V15_VERIFY_SCRIPT)
    require(check["actual_argv"] == ["/usr/bin/python3","-B",verifier,bridge["manifest_result"]["path"]]
            and verifier in {s["path"] for s in check["source_before"]}
            and result.get("schema") == "mr3-v15-static-preparation-review-v1"
            and result.get("passed") is True and result.get("actual_library_source_and_feed_sha_match") is True,
            "manifest lacks its actual successful V15 preparation producer wait")
    manifest_raw = read(bridge["manifest"]["path"])
    require(result["source_manifest"]["path"] == bridge["manifest"]["path"]
            and result["source_manifest"]["sha256"] == sha(manifest_raw)
            and result["source_manifest"]["bytes"] == len(manifest_raw)
            and manifest.get("schema") == "mr3-v15-static-source-and-built-library-preparation-v1",
            "actual static result is not bound to this original ELF/source manifest")
    driver, fields = bound["binaries"]["driver"], bound["document"]["compiled_sources"]["driver"]
    actual = module.file_proof(driver["path"])
    require(all(actual[k] == driver[k] for k in ("resolved_path","sha256","bytes"))
            and ("stat" not in driver or actual["stat"] == driver["stat"]),
            "current actual driver ELF changed from the validated binding")
    read(driver["path"])
    library = manifest["library"]
    require(library["path"] == driver["path"] and library["real_path"] == driver["resolved_path"]
            and library["sha256"] == driver["sha256"] and library["bytes"] == driver["bytes"]
            and manifest["compiled_source_sha256"] == fields["compiled_source_sha256"]["sha256"]
            and manifest["compiled_feed_header_sha256"] == fields["compiled_drive_feed_sha256"]["sha256"],
            "original built driver ELF/compiled source does not match this current binding")
    original_sources = {s["path"]:s for s in build["source_before"]}
    manifest_sources = {s["path"]:s for s in manifest["sources"]}
    required = [fields[k] for k in ("compiled_source_sha256","compiled_drive_feed_sha256")]
    for spec in required:
        source_path = Path(spec["path"])
        source_path = source_path if source_path.is_absolute() else Path(root)/source_path
        name = str(source_path)
        require(name in original_sources and name in manifest_sources
                and original_sources[name]["sha256"] == manifest_sources[name]["sha256"] == spec["sha256"]
                and original_sources[name]["bytes"] == manifest_sources[name]["bytes"] == len(read(source_path)),
                "changed native source/feed header is absent from the original actual build and ELF manifest")
    cmake = Path(root)/"ros2_ws/ros2-multi-robot-automap/src/multi_robot/CMakeLists.txt"
    cmake_raw = read(cmake)
    require(str(cmake) in original_sources
            and original_sources[str(cmake)]["sha256"] == sha(cmake_raw)
            and original_sources[str(cmake)]["bytes"] == len(cmake_raw),
            "CMake is not bound by the original unchanged actual build and current frozen bytes")

    archive_spec = bridge["compiler_flags_archive"]
    require(archive_spec["path"] == str(Path(root)/V15_FLAGS_ARCHIVE),
            "compiler flags archive is not the original canonical V15 artifact")
    archived_flags = frozen_artifact(archive_spec,freeze,root,read)
    flags = manifest["compiler_flags"]
    flags_path = Path(root)/DRIVER_FLAGS
    require(flags["path"] == str(flags_path) and flags["real_path"] == str(flags_path.resolve(strict=True)),
            "compiler flags manifest does not name the current actual driver flags.make")
    require(sha(archived_flags) == flags["sha256"] and len(archived_flags) == flags["bytes"]
            and read(flags_path) == archived_flags,
            "archived compiler flags, original ELF manifest and current actual flags differ")
    assignments = {}
    for label in ("CXX_DEFINES", "CXX_FLAGS"):
        lines = [line.split(" = ",1)[1] for line in archived_flags.decode("utf-8").splitlines()
                 if line.startswith(label+" = ")]
        require(len(lines) == 1, "compiler flags assignment is missing or repeated: "+label)
        assignments[label] = shlex.split(lines[0])
    tokens = assignments["CXX_DEFINES"]+assignments["CXX_FLAGS"]
    for macro, field in DRIVER_DEFINITIONS.items():
        definitions = [token for token in tokens if token.split("=",1)[0] == "-D"+macro]
        require(definitions == ['-D'+macro+'="'+fields[field]["sha256"]+'"']
                and "-U"+macro not in tokens,
                "actual compiler flags do not bind exactly one current native source SHA: "+macro)
    options = assignments["CXX_FLAGS"]
    require(options.count("-fno-fast-math") == 1 and options.count("-ffp-contract=off") == 1
            and not any(token in ("-ffast-math", "-Ofast")
                        or (token.startswith("-ffp-contract=") and token != "-ffp-contract=off")
                        for token in tokens),
            "actual driver compiler flags violate no-fast-math/fp-contract=off")
    if own_reader:
        read.finish()
    return {"schema":SCHEMA_BUILD_BRIDGE,"passed":True,"bridge_sha256":sha(raw),
            "original_wait_seconds":durations,"driver_sha256":driver["sha256"],
            "source_scope":{"cpp_and_feed_header":"actual_build_before_after AND actual_ELF_manifest.sources",
                "cmake":"actual_build_before_after AND current_frozen_bytes; not required in old manifest.sources",
                "cmake_present_in_original_manifest":str(cmake) in manifest_sources},
            "compiler_flags_archive":{"path":archive_spec["path"],"sha256":sha(archived_flags),"bytes":len(archived_flags)},
            "actual_compiler_flags":{"path":str(flags_path),"sha256":sha(archived_flags),"bytes":len(archived_flags)},
            "compiled_source_fields":sorted(DRIVER_DEFINITIONS.values()),
            "numeric_compile_options":["-fno-fast-math","-ffp-contract=off"],
            "new_build_executed":False,"native_admission":False}


def initial_encoder_configuration(path, *, epoch, robot, helper_sha256, parse=json.loads):
    """Bind the real early producer prefix; later growing rows are not read here."""
    prefix = bytearray()
    with Path(path).open("rb") as stream:
        for _ in range(64):
            raw = stream.readline(65537)
            require(len(raw) <= 65536, "initial encoder producer prefix line exceeds its bound")
            if not raw.endswith(b"\n"):
                raise FileNotFoundError("initial encoder producer configuration is not yet complete")
            prefix.extend(raw)
            row = parse(raw)
            if row.get("kind") != "initial_encoder_configuration":
                continue
            require(row.get("epoch") == epoch and row.get("robot") == robot and
                    row.get("actuation_profile") == INITIAL_ENCODER_ACTUATION_PROFILE and
                    row.get("compiled_encoder_servo_sha256") == helper_sha256 and
                    row.get("position_gain_per_second") == 1.0 and row.get("feedback_rim_limit_mps") == .005 and
                    row.get("capture_rim_limit_mps") == .01 and row.get("capture_consecutive_samples") == 3 and
                    row.get("update_period_ns") == 34000000 and row.get("reference_capture_count_limit") == 1 and
                    row.get("received_nonzero_latch") == "first successfully validated stored target; not consumption" and
                    row.get("reference_lifetime") == "one fresh plugin object/epoch; Reset does not rearm",
                    "actual encoder producer profile/helper/parameters differ")
            return {"path":str(path), "prefix_sha256":sha(prefix), "prefix_bytes":len(prefix),
                    "initial_encoder_configuration_sha256":sha(raw), "configuration":row}
    raise ValueError("initial encoder producer configuration missing from bounded startup prefix")


def load_implementation(root=WORKSPACE):
    """Each invocation owns a fresh module; legacy module globals are untouched."""
    root = Path(root).resolve()
    raw = (root/HELPER).read_bytes()
    projected, proof = project_source(raw)
    module = types.ModuleType("mr3_learning._reach_private_native_custody")
    module.__package__ = "mr3_learning"
    module.__file__ = __file__
    exec(compile(projected, str(root/HELPER), "exec"), module.__dict__)
    require(module.COMPILED_FIELDS == COMPILED_FIELDS and module.BINARY_ROLES == BINARY_ROLES,
            "private compiled source or binary role inventory differs")
    provenance = {"schema":"mr3-reach-native-custody-implementation-v1",
        "effective_entry":{"path":str(Path(__file__).resolve()),"sha256":sha(Path(__file__).read_bytes())},
        "helper":{"path":str(HELPER),"sha256":HELPER_SHA256},"projection":proof,
        "scope":"Original process/file/closure predicates execute on current artifacts; new schemas, six-source driver and explicit reach/v2 checks. No old result or continuous plant credit."}
    original_load, original_configs = module.load_binding, module.configurations
    original_capture, original_closed = module.capture_episode, module.strict_closed_episode
    original_exclusive, original_boundary = module.exclusive, module.read_wait_boundary
    original_fifo = module.read_fifo_receipts
    original_review = module.review

    def load_binding(path, freeze, *, root=root, read=None):
        bound = original_load(path, freeze, root=root, read=read)
        bound["reach_source_proof"] = binding_sources(bound, root)
        module._reach_geometry_rule = geometry_rule(bound["document"])
        profile = initial_encoder_profile(bound["document"])
        module._reach_actuation_profile = profile
        bridges = []
        for spec in bound["document"]["build_receipts"]:
            receipt_path = Path(spec["path"])
            receipt_path = receipt_path if receipt_path.is_absolute() else Path(root)/receipt_path
            if module.parse(bound["reader"](receipt_path)).get("schema") == SCHEMA_BUILD_BRIDGE:
                bridges.append(verify_build_bridge(receipt_path,freeze,bound,root=root,read=bound["reader"]))
        require(len(bridges) == 1, "exactly one strict current-driver build bridge is required")
        if profile is not None:
            require(bridges[0].get("new_build_executed") is True and
                    bridges[0].get("actuation_profile") == profile,
                    "new encoder profile did not pass its actual new-build bridge")
        bound["reach_build_bridge_proof"] = bridges[0]
        module._reach_verified_binding = {"reach_source_proof":bound["reach_source_proof"],
                                         "reach_build_bridge_proof":bridges[0],
                                         **({"actuation_profile":profile} if profile is not None else {})}
        return bound

    def configurations(directory, binding):
        rule = geometry_rule(binding["document"])
        profile = initial_encoder_profile(binding["document"])
        meta = profile_metadata(directory, binding["freeze"], binding["reader"], reach_geometry_rule=rule,
                                actuation_profile=profile)
        result = original_configs(directory, binding)
        if rule != DEFAULT_GEOMETRY_RULE:
            entry = module.first_line(Path(directory)/"motion_safety.jsonl")
            row = entry["configuration"]
            require(row.get("kind") == "configuration" and row.get("epoch") == meta["epoch"]
                    and geometry_rule(row["payload"]) == rule
                    and row["payload"].get("controlled_execution") is True
                    and row["payload"].get("robots") == list(ROBOTS),
                    "live motion configuration did not select the bound support geometry")
            result.append(entry)
        for entry in result:
            cfg = entry["configuration"]
            if Path(entry["path"]).name.startswith("drive_"):
                require(cfg.get("native_feeds_enabled") is True
                        and cfg.get("applied_feed_schema") == "mr3-drive-applied-v1"
                        and cfg.get("applied_feed_scope") == "all_wheel_SetParam_calls_returned_true; not_body_response"
                        and cfg.get("odometry_calibration_schema") == "mr3-odom-calibration-v1"
                        and cfg.get("odometry_conversion_contract") == "float32-trig-binary64-rn-v1"
                        and cfg.get("odometry_producer_frame") == "world-common-model-origin-v1"
                        and cfg.get("native_feed_qos") == {"depth":256,"reliability":"reliable","durability":"volatile"},
                        "actual loaded driver lacks the new typed feed contract")
        if profile is not None:
            extra = binding["document"]["initial_encoder_compiled_source"]
            for robot in ROBOTS:
                main = next(row["configuration"] for row in result
                            if Path(row["path"]).name == "drive_"+robot+".jsonl")
                require(main.get("actuation_algorithm") ==
                        "initial_zero_encoder_hold_then_paired_common_fraction_v1",
                        "actual driver did not select the compound encoder law")
                result.append(initial_encoder_configuration(Path(directory)/("drive_"+robot+".jsonl"),
                    epoch=meta["epoch"], robot=robot, helper_sha256=extra["sha256"], parse=module.parse))
        for robot in ROBOTS:
            entry = module.first_line(Path(directory)/("odometry_"+robot+".jsonl"))
            cfg = entry["configuration"]
            require(cfg.get("epoch") == meta["epoch"]
                    and cfg.get("schema") == "mr3-world-odometry-publication-v1" and cfg.get("kind") == "configuration"
                    and cfg.get("robot") == robot and cfg.get("provider") == "WORLD"
                    and all(cfg.get(key) == spec["sha256"] for key,spec in
                            binding["document"]["compiled_sources"]["driver"].items())
                    and str(Path(cfg["loaded_library_path"]).resolve(strict=True)) == binding["binaries"]["driver"]["resolved_path"]
                    and cfg.get("odometry_calibration_schema") == "mr3-odom-calibration-v1",
                    "actual odometry producer lacks this six-source loaded driver binding")
            result.append(entry)
        return result

    def capture_episode(directory, binding, *, proc_root=Path("/proc")):
        profile_metadata(directory,binding["freeze"],module.Reader(),
                         reach_geometry_rule=geometry_rule(binding["document"]),
                         actuation_profile=initial_encoder_profile(binding["document"]))
        return original_capture(directory,binding,proc_root=proc_root)

    def strict_closed_episode(directory, freeze, read):
        profile_metadata(directory,freeze,read,
                         reach_geometry_rule=getattr(module,"_reach_geometry_rule",None),
                         actuation_profile=getattr(module,"_reach_actuation_profile",None))
        return original_closed(directory,freeze,read)

    def exclusive(path, value):
        value.update(safety_contract=CONTRACT,implementation_provenance=provenance)
        return original_exclusive(path,value)

    def read_wait_boundary(read, stop_path, launch_path, freeze):
        value = original_boundary(read,stop_path,launch_path,freeze)
        require(value["stop"].get("safety_contract") == CONTRACT, "old stop receipt cannot close reach watcher")
        if value["launch"] is not None:
            require(value["launch"].get("schema") == SCHEMA_WAIT
                    and value["launch"].get("safety_contract") == CONTRACT,
                    "actual wait is not a new reach native launch receipt")
        return value

    def read_fifo_receipts(read,path,freeze,expected_count):
        result = original_fifo(read,path,freeze,expected_count)
        require(all(v.get("safety_contract") == CONTRACT and v.get("schema") == SCHEMA_FIFO for v in result.values()),
                "legacy FIFO/phase result cannot acquire reach closure credit")
        return result

    def review(args, *, proc_root=Path("/proc")):
        try:
            capture = module.parse(module.Reader()(args.capture))
            require(capture.get("safety_contract") == CONTRACT
                    and capture.get("implementation_provenance") == provenance,
                    "live capture is not bound to this effective reach wrapper source/projection")
        except (OSError,ValueError,KeyError,TypeError) as error:
            return {"schema":SCHEMA_CLOSURE,"freeze":args.freeze,"passed":False,
                    "episodes":[],"errors":[str(error)],"safety_contract":CONTRACT,
                    "implementation_provenance":provenance}
        result = original_review(args,proc_root=proc_root)
        result.update(safety_contract=CONTRACT,implementation_provenance=provenance)
        return result

    module.load_binding, module.configurations = load_binding, configurations
    module.capture_episode, module.strict_closed_episode = capture_episode, strict_closed_episode
    module.exclusive, module.read_wait_boundary = exclusive, read_wait_boundary
    module.read_fifo_receipts = read_fifo_receipts
    module.review = review
    return module, provenance


def verify_binding(root, freeze, binding_path):
    module, proof = load_implementation(root)
    result = module.verify_binding(root, freeze, binding_path)
    result.update(safety_contract=CONTRACT,implementation_provenance=proof,
                  **module._reach_verified_binding)
    return result


def load_binding(path, freeze, *, root=WORKSPACE, read=None):
    module, _ = load_implementation(root)
    return module.load_binding(path,freeze,root=root,read=read)


def Reader():
    module, _ = load_implementation()
    return module.Reader()


def write_ready_receipt(path, freeze, binding_sha256):
    module, _ = load_implementation()
    return module.write_ready_receipt(path,freeze,binding_sha256)


def read_ready_receipt(read,path,freeze,binding_sha256):
    module, proof = load_implementation()
    value = module.read_ready_receipt(read,path,freeze,binding_sha256)
    require(value.get("safety_contract") == CONTRACT and value.get("implementation_provenance") == proof,
            "ready receipt has no current effective wrapper provenance")
    return value


def review(args, *, proc_root=Path("/proc")):
    module, proof = load_implementation()
    result = module.review(args,proc_root=proc_root)
    result.update(safety_contract=CONTRACT,implementation_provenance=proof)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="mode",required=True)
    for name in ("watch","review","closure","verify"):
        child = subs.add_parser(name)
        for field in ("binding","output"):
            child.add_argument("--"+field,type=Path,required=True)
        child.add_argument("--freeze",required=True)
        if name != "verify":child.add_argument("--run-directory",type=Path,required=True)
        if name == "watch":
            child.add_argument("--ready-file",type=Path,required=True)
            child.add_argument("--stop-file",type=Path,required=True)
        elif name != "verify":
            for field in ("capture","launch-receipt","fifo-receipts"):
                child.add_argument("--"+field,type=Path,required=True)
            child.add_argument("--expected-episodes",type=int,required=True)
            child.add_argument("--require-parameters",action="store_true")
    args = parser.parse_args(argv)
    if args.output.exists():parser.error("exclusive output exists")
    module, proof = load_implementation()
    if args.mode == "watch":return module.watch(args)
    if args.mode == "verify":result = verify_binding(WORKSPACE,args.freeze,args.binding)
    else:result = review(args)
    result.update(safety_contract=CONTRACT,implementation_provenance=proof)
    module.exclusive(args.output,result)
    print(json.dumps({"passed":result["passed"],"output":str(args.output)}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
