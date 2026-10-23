"""Complete v2 native scientific audit; no old-profile qualification credit."""

import argparse
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time

from .audit_ppo import load_rows, require
from .preparation import identity
from .reach_audit_projection import project_module
from .reach_gates import load_native_gates
from .supervisor import (BINARY_REACH_GEOMETRY_RULE, validate_reach_geometry_rule)
from .supervisor import validate_seed_rule, validate_start_graph_rule

SOURCE_SHA256 = "b7e07ee44188b43f09a94215430fac609d6753f7be5594ce9f4b2308ccf88cab"
WIRELESS = Path(__file__).resolve().parents[1]
SYSTEM_PYTHON = "/usr/bin/python3"
EXACT_REPLAY_SCHEMA = "mr3-exact-seed-native-input-replay-v1"


def audit_exact_seed_inputs_system(directory, *, seed_rule, start_graph_rule,
                                  reach_geometry_rule=BINARY_REACH_GEOMETRY_RULE):
    """Keep the unchanged full replayer in its system NumPy/SciPy process.

    Temporary child output/console contents and actual-wait facts are embedded
    in the returned report; they are not dangling persistent-file bindings.
    A failed child or an invalid claimed PASS remains a failed archive gate.
    """
    directory = Path(directory).resolve(strict=True)
    errors, child_result, metadata, metadata_raw = [], None, {}, None
    env = dict(os.environ)
    removed = [name for name in ("PYTHONPATH", "PYTHONHOME") if name in env]
    for name in ("PYTHONPATH", "PYTHONHOME"):
        env.pop(name, None)
    env.update(PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1")
    execution = {"schema": "mr3-exact-seed-system-python-wait-v1",
        "python": SYSTEM_PYTHON, "cwd": str(WIRELESS), "argv": None,
        "environment": {"removed_variable_names": removed, "PYTHONPATH_present": False,
            "PYTHONHOME_present": False, "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1"},
        "coordinator_identity": identity(os.getpid()), "child_identity": None,
        "actual_waited": False, "returncode": None, "errors": errors}

    def parse(raw):
        def pairs(rows):
            value = {}
            for key, item in rows:
                require(key not in value, "duplicate replay JSON key: " + key)
                value[key] = item
            return value
        return json.loads(raw, object_pairs_hook=pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError("nonfinite replay JSON: " + value)))

    try:
        validate_seed_rule(seed_rule)
        validate_reach_geometry_rule(reach_geometry_rule, safety_contract="mr3-reach-v1")
        validate_start_graph_rule(start_graph_rule, seed_rule=seed_rule)
        require(seed_rule != "legacy", "system exact replay requires an explicit exact seed rule")
        metadata_raw = (directory / "metadata.json").read_bytes()
        metadata = parse(metadata_raw)
        require(type(metadata) is dict, "native metadata is not a JSON object")
        freeze = metadata.get("freeze")
        require(type(freeze) is str and re.fullmatch(r"[0-9a-f]{40}", freeze),
                "system exact replay requires an exact metadata freeze")
        require(metadata.get("seed_rule") == seed_rule
                and metadata.get("start_graph_rule", "original-seed-cell") == start_graph_rule,
                "system exact replay metadata differs from the declared seed/start rules")
        require(metadata.get("reach_geometry_rule", BINARY_REACH_GEOMETRY_RULE) == reach_geometry_rule,
                "system exact replay metadata differs from declared reach geometry rule")
        if reach_geometry_rule != BINARY_REACH_GEOMETRY_RULE:
            require(metadata.get("safety_contract") == "mr3-reach-v1",
                    "support system replay metadata lacks the reach safety contract")
            execution.update(reach_geometry_rule=reach_geometry_rule,
                             native_metadata_sha256=hashlib.sha256(metadata_raw).hexdigest())
        coordinator = execution["coordinator_identity"]
        require(type(coordinator) is dict and coordinator.get("pid") == os.getpid()
                and type(coordinator.get("start_ticks")) is int and coordinator["start_ticks"] > 0,
                "system exact replay coordinator PID/start was not captured")
        with tempfile.TemporaryDirectory(prefix="mr3-exact-seed-system-") as temporary:
            output, console = Path(temporary) / "result.json", Path(temporary) / "console.log"
            argv = [SYSTEM_PYTHON, "-B", "-m", "mr3_learning.audit_seed_inputs",
                    "--episode", str(directory), "--output", str(output)]
            execution.update(argv=argv, temporary_output=str(output),
                             started_monotonic_ns=time.monotonic_ns())
            child = None
            with console.open("xb") as stream:
                try:
                    child = subprocess.Popen(argv, cwd=WIRELESS, env=env,
                                             stdout=stream, stderr=subprocess.STDOUT)
                    execution["child_identity"] = identity(child.pid)
                    require(type(execution["child_identity"]) is dict
                            and execution["child_identity"].get("pid") == child.pid
                            and execution["child_identity"].get("parent") == coordinator["pid"]
                            and type(execution["child_identity"].get("start_ticks")) is int
                            and execution["child_identity"]["start_ticks"] > 0,
                            "system exact replay child PID/start was not captured")
                except (OSError, ValueError) as error:
                    errors.append(repr(error))
                finally:
                    if child is not None:
                        while True:
                            try:
                                execution["returncode"] = child.wait()
                                execution["actual_waited"] = True
                                break
                            except BaseException as error:
                                errors.append("system replay actual wait: " + repr(error))
            execution["ended_monotonic_ns"] = time.monotonic_ns()
            execution["actual_wait_seconds"] = str(Decimal(execution["ended_monotonic_ns"]
                - execution["started_monotonic_ns"]) / 10**9)
            console_raw = console.read_bytes()
            execution.update(stdout_stderr=console_raw.decode("utf-8", errors="replace"),
                stdout_stderr_sha256=hashlib.sha256(console_raw).hexdigest(),
                stdout_stderr_bytes=len(console_raw))
            if output.is_file():
                raw = output.read_bytes()
                execution.update(result_json=raw.decode("utf-8", errors="replace"),
                                 result_sha256=hashlib.sha256(raw).hexdigest(), result_bytes=len(raw))
                child_result = parse(raw)
            require(execution["actual_waited"] and type(execution["returncode"]) is int
                    and execution["returncode"] == 0 and not errors,
                    "system exact replay child did not complete successfully")
            require(type(child_result) is dict and child_result.get("schema") == EXACT_REPLAY_SCHEMA
                    and child_result.get("passed") is True and child_result.get("errors") == [],
                    "system exact replay did not produce a valid independent PASS")
            require(child_result.get("freeze") == freeze
                    and child_result.get("episode") == str(directory)
                    and child_result.get("seed_rule") == seed_rule
                    and child_result.get("start_graph_rule", "original-seed-cell") == start_graph_rule,
                    "system exact replay result freeze/episode/seed/start identity differs")
            count = child_result.get("exact_full_snapshot_replays")
            require(child_result.get("whole_observation_and_seven_map_replay_passed") is True
                    and type(count) is int and count > 0
                    and type(child_result.get("source_proof")) is dict and child_result["source_proof"]
                    and type(child_result.get("input_bindings")) is dict and child_result["input_bindings"],
                    "system exact replay lacks full snapshot/seven-map/source/input evidence")
        execution["temporary_files_removed"] = True
    except (OSError, ValueError, TypeError, KeyError, IndexError, RuntimeError, OverflowError,
            subprocess.SubprocessError) as error:
        errors.append(repr(error))
        execution["temporary_files_removed"] = True
    if metadata_raw is not None:
        try:
            require((directory / "metadata.json").read_bytes() == metadata_raw,
                    "native metadata changed during system exact replay")
        except (OSError, ValueError) as error:
            errors.append(repr(error))
    if not errors:
        result = dict(child_result)
    else:
        result = {"schema": EXACT_REPLAY_SCHEMA, "passed": False, "errors": list(errors),
            "freeze": metadata.get("freeze") if type(metadata) is dict else None,
            "episode": str(directory), "seed_rule": seed_rule,
            **({"start_graph_rule": start_graph_rule} if start_graph_rule != "original-seed-cell" else {})}
    if reach_geometry_rule != BINARY_REACH_GEOMETRY_RULE:
        result["reach_geometry_rule"] = reach_geometry_rule
    result["system_python_execution"] = execution
    return result


def load_impl(plan_path):
    module, proof = project_module("audit_preparation.py", SOURCE_SHA256, (
        ("from .audit_ppo import load_native_gates, load_rows, require",
         "from .audit_ppo import load_rows, require\n# explicit new gate injected below", 1),
        ("from .audit_motion import audit_episode as audit_motion",
         "from .audit_reach_peer_control import audit_episode as audit_motion", 1),
        ("from .audit_controlled_physics import (",
         "from .audit_reach_controlled_physics import (", 1),
        ("mr3-motion-safety-status-v1", "mr3-motion-safety-status-v2", 1),
        ("mr3-p2a0-outward-cancel-v6", "mr3-p2a-reach-outward-cancel-v1", 1),
    ))
    module.load_native_gates = lambda root, freeze: load_native_gates(root, freeze, plan_path)
    from . import audit_reach_peer_control, audit_reach_controlled_physics
    module.audit_motion = lambda directory: audit_reach_peer_control.audit_episode(directory, plan_path=plan_path)
    module.dispatch_controlled_physics = lambda *args, **kwargs: audit_reach_controlled_physics.dispatch_controlled_physics(
        *args, plan_path=plan_path, **kwargs)
    module.dispatch_controlled_readiness = lambda *args, **kwargs: audit_reach_controlled_physics.dispatch_controlled_readiness(
        *args, plan_path=plan_path, **kwargs)
    plan = json.loads(Path(plan_path).read_text())
    validate_start_graph_rule(plan.get("start_graph_rule", "original-seed-cell"),
                              seed_rule=plan.get("seed_rule", "legacy"))
    geometry_rule = validate_reach_geometry_rule(
        plan.get("reach_geometry_rule", BINARY_REACH_GEOMETRY_RULE), safety_contract="mr3-reach-v1")
    if validate_seed_rule(plan.get("seed_rule", "legacy")) != "legacy":
        original_archives = module.audit_archives

        def exact_archives(directory):
            result = original_archives(directory)
            replay = audit_exact_seed_inputs_system(directory, seed_rule=plan["seed_rule"],
                start_graph_rule=plan.get("start_graph_rule", "original-seed-cell"),
                **({"reach_geometry_rule": geometry_rule} if geometry_rule != BINARY_REACH_GEOMETRY_RULE else {}))
            result["exact_seed_full_replay"] = replay
            result["passed"] = result.get("passed") is True and replay["passed"] is True
            if not replay["passed"]:
                result["errors"] = [*result.get("errors", []), "system exact seed full replay failed"]
            return result

        module.audit_archives = exact_archives
    return module, proof


def audit(directory, root, freeze, plan_path):
    directory, root = Path(directory), Path(root)
    paths = ([directory / "metadata.json"] if (directory / "metadata.json").is_file()
             else sorted(directory.glob("worker*/episode*/metadata.json")))
    require(paths, "no actual reach episodes")
    plan = json.loads(Path(plan_path).read_text())
    geometry_rule = validate_reach_geometry_rule(
        plan.get("reach_geometry_rule", BINARY_REACH_GEOMETRY_RULE), safety_contract="mr3-reach-v1")
    for path in paths:
        metadata = json.loads(path.read_text())
        require(metadata.get("safety_contract") == "mr3-reach-v1"
                and metadata.get("execution_phase_protocol") == "mr3-controlled-execution-phase-v2"
                and metadata.get("reset_handshake") == "paused-controlled-state-peer-guard-storage-v2"
                and metadata.get("freeze") == freeze, "missing/mixed new-profile declaration")
        require(metadata.get("seed_rule", "legacy") == plan.get("seed_rule", "legacy"),
                "native preparation seed rule differs from the qualification plan")
        require(metadata.get("start_graph_rule", "original-seed-cell") == plan.get("start_graph_rule", "original-seed-cell"),
                "native preparation start graph rule differs from the qualification plan")
        require(metadata.get("reach_geometry_rule", BINARY_REACH_GEOMETRY_RULE) == geometry_rule,
                "native preparation reach geometry rule differs from qualification plan")
        supervisor_path = path.parent / "supervisor_metadata.json"
        if geometry_rule != BINARY_REACH_GEOMETRY_RULE:
            supervisor = json.loads(supervisor_path.read_text())
            require(supervisor.get("reach_geometry_rule", BINARY_REACH_GEOMETRY_RULE) == geometry_rule,
                    "native preparation supervisor reach geometry rule differs")
    module, proof = load_impl(plan_path)
    result = module.audit(directory, root, freeze)
    result.update(schema="mr3-reach-preparation-full-audit-v1", safety_contract="mr3-reach-v1",
                  immutable_reader_projection=proof,
                  scope="Native/contact/clock/protocol/scalar/evaluator/archive/activity/topology/costmap and complete v2 release. Joint qualification additionally requires every independently declared reach role.")
    if geometry_rule != BINARY_REACH_GEOMETRY_RULE:
        result["reach_geometry_rule"] = geometry_rule
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    root = next(p for p in Path(__file__).resolve().parents if (p / ".git").exists())
    result = audit(args.directory, root, args.freeze, args.plan)
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"passed": result["passed"], "output": str(args.output)}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
