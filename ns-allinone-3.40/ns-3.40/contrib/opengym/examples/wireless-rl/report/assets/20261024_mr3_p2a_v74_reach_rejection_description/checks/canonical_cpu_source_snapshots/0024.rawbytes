"""Explicit Reach workload dispatch to unchanged V17 reset mathematics.

The two immutable sources remain byte-for-byte unchanged. Only their unique
PROBE_VERSION assignment is projected in a fresh private module; the complete
inverse and this actual entry's source identity accompany every result.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

from .reach_audit_projection import project_file


WORKSPACE = Path(__file__).resolve().parents[7]
WIRELESS = Path("ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl")
PROFILE = "mr3-reach-reset-outward-cancel-v1"
PROBE_VERSION = "mr3-p2a-reach-outward-cancel-v1"
PROFILE_V2 = "mr3-reach-reset-outward-cancel-v2"
PROBE_VERSION_V2 = "mr3-p2a-reach-outward-cancel-v2"
PROFILE_V3 = "mr3-reach-reset-outward-cancel-v3"
PROBE_VERSION_V3 = "mr3-p2a-reach-outward-cancel-v3"
PROFILE_MASKED = "mr3-reach-reset-masked-cancel-v1"
PROBE_VERSION_MASKED = "mr3-p2a-reach-masked-cancel-v1"
CONTRACT = "mr3-reach-v1"
SCHEMA = "mr3-reach-reset-workload-audit-v1"
ENTRY = WIRELESS / "mr3_learning/audit_reach_reset_workload.py"
SOURCES = {
    "angular": (WIRELESS / "report/assets/20261017_mr3_p2a0_v17/independent/"
                "mr3_independent_angular_reset_matrix_v17.py",
                "8c9f04929cd9a52df0bea22106d64756c42c51350adae9ee20823e0054028901"),
    "physics": (WIRELESS / "report/assets/20261017_mr3_p2a0_v17/independent/"
                "mr3_independent_physics_matrix_v17.py",
                "50651f8b8ed5bee161f4c44a18e1ce68f7d8a27cda88fc466756b91f0f35cee8"),
}
EXPECTED_SCHEMAS = {"angular": "mr3-independent-angular-reset-matrix-v1",
                    "physics": "mr3-independent-reset-physics-matrix-v2"}
LEAVES = {
    "angular": (WIRELESS / "report/assets/20261017_mr3_p2a0_v4/independent/"
                "mr3_independent_angular_interface_v1.py",
                "7a472ba7efdd55addc710b98c66c89feff7f5092f214f76fd76cd4ca526343d0"),
    "physics": (WIRELESS / "report/assets/20261017_mr3_p2a0_v3/independent/"
                "mr3_independent_physics_review.py",
                "2516e394f60eac5dd24fd66b51c4c48fc37245090eb1626ebe1c7a3a23f8bafb"),
}
SOURCE_PATHS = {str(ENTRY), str(WIRELESS / "mr3_learning/reach_audit_projection.py"),
                *(str(path) for path, _ in SOURCES.values()),
                *(str(path) for path, _ in LEAVES.values())}
CHANGE = ('PROBE_VERSION = "mr3-p2a0-outward-cancel-v6"\n',
          'PROBE_VERSION = "' + PROBE_VERSION + '"\n', 1)


def require(value, message):
    if not value:
        raise ValueError(message)


def profile_spec(workload_profile=PROFILE):
    require(type(workload_profile) is str and workload_profile in (PROFILE,PROFILE_V2,PROFILE_V3,PROFILE_MASKED),
            "unknown fixed Reach reset workload profile")
    probe = {PROFILE:PROBE_VERSION,PROFILE_V2:PROBE_VERSION_V2,PROFILE_V3:PROBE_VERSION_V3,PROFILE_MASKED:PROBE_VERSION_MASKED}[workload_profile]
    change = (CHANGE[0], 'PROBE_VERSION = "' + probe + '"\n', 1)
    return workload_profile,probe,change


def profile_from_plan(plan):
    selected = profile_spec(plan.get("reset_workload_reader_profile"))
    if selected[0] in (PROFILE_V2,PROFILE_V3,PROFILE_MASKED):
        require(plan.get("preparation_probe_version") == selected[1],
                "v2 reset plan lacks its exact producer/reader pair")
    return selected


def episode_probe_profiles(directory, freeze, *, workload_profile):
    """v2 actual worker and supervisor declarations; no telemetry or physics credit."""
    _,probe,_ = profile_spec(workload_profile)
    require(workload_profile in (PROFILE_V2,PROFILE_V3,PROFILE_MASKED), "episode check requires an explicit v2/v3 profile")
    directory=Path(directory)
    paths=([directory/"metadata.json"] if (directory/"metadata.json").is_file()
           else sorted(directory.glob("worker*/episode*/metadata.json")))
    require(paths, "v2 probe has no actual episode metadata")
    result={}
    for path in paths:
        epoch = None
        for actual in (path,path.parent/"supervisor_metadata.json"):
            raw=actual.read_bytes(); value=json.loads(raw)
            require((actual.name == "supervisor_metadata.json" or value.get("freeze") == freeze)
                    and value.get("freeze",freeze) == freeze and value.get("safety_contract") == CONTRACT
                    and value.get("preparation_probe_version") == probe,
                    "actual worker/supervisor probe profile differs from its plan")
            require(type(value.get("epoch")) is str and bool(value["epoch"])
                    and (epoch is None or value["epoch"] == epoch),
                    "v2 worker/supervisor epoch differs")
            epoch = value["epoch"]
            result[str(actual)]={"sha256":hashlib.sha256(raw).hexdigest(),"bytes":len(raw)}
    return result


def independent_replayer(workload_profile):
    profile_spec(workload_profile)
    if workload_profile == PROFILE_V3:
        from . import reach_probe_v3_replay
        return reach_probe_v3_replay
    if workload_profile == PROFILE_MASKED:
        from . import reach_probe_masked_cancel_replay
        return reach_probe_masked_cancel_replay
    return None


def stimulus_replay_key(workload_profile):
    profile_spec(workload_profile)
    if workload_profile == PROFILE_V3:return "probe_v3_stimulus_replay"
    if workload_profile == PROFILE_MASKED:return "probe_masked_cancel_stimulus_replay"
    raise ValueError("this historical workload has no independent stimulus proof")


def source_paths(workload_profile=PROFILE):
    independent=independent_replayer(workload_profile)
    return set(SOURCE_PATHS) if independent is None else SOURCE_PATHS | independent.SOURCE_PATHS


def load_reader(kind, *, workload_profile=PROFILE):
    """Fixed source selection; no caller/CLI-supplied mathematical source path."""
    require(type(kind) is str and kind in SOURCES, "unknown reset workload reader kind")
    relative, expected = SOURCES[kind]
    _,probe,change = profile_spec(workload_profile)
    module, proof = project_file(WORKSPACE / relative, expected, (change,))
    require(module.PROBE_VERSION == probe, "projected reset probe version differs")
    return module, proof



def verify_reader_readiness(plan, freeze):
    """Fixed source-only preflight: really load both readers, never audit inputs.

    This receipt does not imply any episode, physics or qualification PASS.
    Caller must keep the complete new plan/outer source gates and retain it.
    """
    require(type(freeze) is str and re.fullmatch(r"[0-9a-f]{40}", freeze),
            "exact preflight execution freeze required")
    profile,probe,change = profile_from_plan(plan)
    bindings = plan["source_bindings"]
    selected_sources = source_paths(profile)
    require(selected_sources <= bindings.keys(), "reset reader preflight source inventory incomplete")
    pins = {str(path): expected for path, expected in (*SOURCES.values(), *LEAVES.values())}
    sources = []
    for relative in sorted(selected_sources):
        path = WORKSPACE / relative
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        require(bindings[relative] == digest and pins.get(relative, digest) == digest,
                "reset reader preflight source pin differs: " + relative)
        frozen = subprocess.check_output(["git", "show", freeze + ":" + relative],
                                        cwd=WORKSPACE, timeout=10)
        require(raw == frozen, "reset reader preflight current/Git differs: " + relative)
        sources.append({"path": relative, "bytes": len(raw), "sha256": digest})
    readers = []
    for kind in ("angular", "physics"):
        module, proof = load_reader(kind, **({"workload_profile":profile} if profile != PROFILE else {}))
        relative, expected = SOURCES[kind]
        require(module.PROBE_VERSION == probe and module.__file__ == str(WORKSPACE / relative)
                and proof["source_sha256"] == proof["inverse_sha256"] == expected
                and proof["whole_source_inverse_equal"] is True
                and proof["literal_changes"] == [{"before": change[0], "after": change[1], "count": 1}],
                "reset reader preflight actual load/inverse differs: " + kind)
        leaf_relative, leaf_expected = LEAVES[kind]
        require(module.CONSUMER_SHA256 == leaf_expected, "reset reader leaf declaration differs")
        if kind == "physics":
            require(module.CONSUMER_PATH == WORKSPACE / leaf_relative, "physical leaf path differs")
        else:
            actual_leaf = Path(module.__file__).resolve().parents[2] / "20261017_mr3_p2a0_v4" / "independent" / "mr3_independent_angular_interface_v1.py"
            require(actual_leaf == WORKSPACE / leaf_relative, "angular default leaf path differs")
        leaf, leaf_proof = project_file(WORKSPACE / leaf_relative, leaf_expected, ())
        require(callable(module.audit) and callable(leaf.audit_episode), "fixed reader/leaf audit definitions missing")
        readers.append({"kind": kind, "probe_version": module.PROBE_VERSION,
                        "immutable_reader_projection": proof, "unchanged_leaf_source": leaf_proof})
    result = {"schema": "mr3-reach-reset-reader-entry-readiness-v1", "passed": True,
            "execution_freeze": freeze, "workload_profile": profile, "sources": sources,
            "readers": readers, "audit_calls": 0, "native_inputs_read": False,
            "scientific_qualification_credit": False}
    independent=independent_replayer(profile)
    if independent is not None:
        require(independent.PROFILE == profile and independent.PROBE == probe
                and callable(independent.replay_episode) and callable(independent.replay_stage),
                "independent v3 definitions/profile absent")
        result["probe_v3_replay_definition" if profile == PROFILE_V3 else "probe_masked_cancel_replay_definition"] = dict(path=str(independent.SOURCE),
            sha256=hashlib.sha256(Path(independent.__file__).read_bytes()).hexdigest(),
            replay_episode_callable=True,replay_stage_callable=True,audit_calls=0)
    return result


def command_argv(kind, directory, freeze, output, per_episode_report=None, *, workload_profile=PROFILE):
    require(type(kind) is str and kind in SOURCES, "unknown reset workload reader kind")
    require((per_episode_report is not None) is (kind == "physics"),
            "only physics requires the original per-episode report")
    profile_spec(workload_profile)
    argv = ["/usr/bin/python3", "-m", "mr3_learning.audit_reach_reset_workload", str(directory),
            "--kind", kind, "--workload-profile", workload_profile, "--freeze", str(freeze)]
    if kind == "physics":
        argv += ["--per-episode-report", str(per_episode_report)]
    return [*argv, "--output", str(output)]


def audit(directory, freeze, *, kind, workload_profile, per_episode_report=None):
    directory = Path(directory)
    result = {"schema": SCHEMA, "directory": str(directory), "freeze": freeze,
              "kind": kind, "workload_profile": workload_profile, "safety_contract": CONTRACT,
              "preparation_probe_version": PROBE_VERSION, "passed": False, "errors": [],
              "original_reader_result": None, "benchmark_inputs": {},
              "entry": {"path": str(Path(__file__).resolve()),
                        "sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
              "scope": "Explicit Reach reset workload registration; unchanged original angular/physical predicates. No retrospective native qualification or task-success credit.",
              "native_inputs_modified": False, "immutable_sources_modified": False}
    stable = {}
    independent,replay_key = None,None
    try:
        profile,probe,change = profile_spec(workload_profile)
        result["preparation_probe_version"] = probe
        require(type(freeze) is str and re.fullmatch(r"[0-9a-f]{40}", freeze),
                "exact 40-hex source freeze required")
        require(type(kind) is str and kind in SOURCES, "unknown reset workload reader kind")
        require((per_episode_report is not None) is (kind == "physics"),
                "only physics requires the original per-episode report")
        module, result["immutable_reader_projection"] = load_reader(kind,
            **({"workload_profile":profile} if profile != PROFILE else {}))
        for name in ("benchmark_metadata.json", "benchmark_summary.json"):
            path = directory / name
            raw = path.read_bytes()
            stable[path] = raw
            result["benchmark_inputs"][str(path)] = {
                "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
            value = json.loads(raw)
            require(type(value) is dict and value.get("safety_contract") == CONTRACT
                    and value.get("preparation_probe_version") == probe,
                    "reset input lacks the explicit Reach workload declaration")
        if profile in (PROFILE_V2,PROFILE_V3,PROFILE_MASKED):
            result["episode_probe_profiles"] = episode_probe_profiles(directory,freeze,workload_profile=profile)
        independent=independent_replayer(profile)
        if independent is not None:
            replay_key=stimulus_replay_key(profile)
            result[replay_key] = independent.replay_stage(directory,freeze)
        original = (module.audit(directory, freeze) if kind == "angular" else
                    module.audit(directory, Path(per_episode_report), freeze))
        result["original_reader_result"] = original
        require(type(original) is dict and original.get("schema") == EXPECTED_SCHEMAS[kind]
                and type(original.get("passed")) is bool
                and type(original.get("errors")) is list,
                "original reset reader returned an invalid result identity")
        require(original["passed"] is True and original["errors"] == [],
                "original reset reader failed; complete result retained")
    except (OSError, ValueError, TypeError, KeyError, IndexError, RuntimeError, OverflowError) as error:
        result["errors"].append(repr(error))
    finally:
        for path, raw in stable.items():
            try:
                require(path.read_bytes() == raw, "benchmark input changed during reset audit: " + str(path))
            except (OSError, ValueError) as error:
                result["errors"].append(repr(error))
    for name,spec in result.get("episode_probe_profiles",{}).items():
        try:
            require(hashlib.sha256(Path(name).read_bytes()).hexdigest() == spec["sha256"],
                    "v2 episode profile metadata changed during audit")
        except (OSError,ValueError) as error:
            result["errors"].append(repr(error))
    if independent is not None and replay_key is not None and replay_key in result:
        try:
            independent.verify_stage_inputs(result[replay_key])
        except (OSError,ValueError) as error:result["errors"].append(repr(error))
    result["passed"] = not result["errors"]
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--kind", choices=tuple(SOURCES), required=True)
    parser.add_argument("--workload-profile", choices=(PROFILE,PROFILE_V2,PROFILE_V3,PROFILE_MASKED), required=True)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--per-episode-report", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("output exists; preserve the original result")
    if (args.per_episode_report is not None) is not (args.kind == "physics"):
        parser.error("only physics requires --per-episode-report")
    result = audit(args.directory, args.freeze, kind=args.kind,
                   workload_profile=args.workload_profile, per_episode_report=args.per_episode_report)
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"passed": result["passed"], "kind": args.kind, "output": str(args.output)}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
