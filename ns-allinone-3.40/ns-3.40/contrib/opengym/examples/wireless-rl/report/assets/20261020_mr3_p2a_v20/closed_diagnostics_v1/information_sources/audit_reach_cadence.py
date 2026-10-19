"""Reach-only20ms WORLD/TF,34ms actual and selected-source conjunction.

The immutable cadence mathematics is executed in a fresh private module after
an exact reversible source projection. A passing public result also requires
the current source-bound reach runtime reader (wheel/application, v2 status,
three storage ACKs, all guard decisions and complete physical tail). It never
replaces live loaded-ELF custody or proves a continuous plant assumption.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import types

from . import audit_reach_runtime as runtime

WORKSPACE = Path(__file__).resolve().parents[7]
WIRELESS = Path("ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl")
HELPER = WIRELESS / "mr3_learning/audit_odometry_cadence.py"
HELPER_SHA256 = "14519650bc7bab8fbea3d1a0d8407dbd75b8fb32c9c504d8864202bac81b2a6b"
SCHEMA = "mr3-reach-independent-world-odometry-cadence-v1"
CONTRACT = "mr3-reach-v1"
ROBOTS = ("tb1", "tb2", "tb3")
PERIOD, ACTUATION = 20_000_000, 34_000_000
COMPILED = ("compiled_source_sha256", "compiled_header_sha256", "compiled_helper_sha256",
            "compiled_target_contract_sha256", "compiled_odometry_json_sha256", "compiled_drive_feed_sha256")
SOURCE_CHANGES = (
    ('"compiled_target_contract_sha256", "compiled_odometry_json_sha256")',
     '"compiled_target_contract_sha256", "compiled_odometry_json_sha256", "compiled_drive_feed_sha256")', 1),
    ('row["kind"] == "decision"', 'row["kind"] == "reach_decision"', 1),
    ('mr3-independent-world-odometry-cadence-v1', SCHEMA, 1),
    ('    epoch = meta["epoch"]\n',
     '    epoch = meta["epoch"]\n'
     '    require(meta.get("safety_contract") == "mr3-reach-v1" and meta.get("quantum_steps") == 20\n'
     '            and meta.get("execution_phase_protocol") == "mr3-controlled-execution-phase-v2"\n'
     '            and meta.get("reset_handshake") == "paused-controlled-state-peer-guard-storage-v2",\n'
     '            "legacy profile cannot acquire reach cadence credit")\n', 1),
)


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def project_source(raw):
    require(sha(raw) == HELPER_SHA256, "immutable odometry cadence helper differs")
    projected = raw
    for old, new, count in SOURCE_CHANGES:
        require(projected.count(old.encode()) == count, "cadence projection occurrence differs: " + old)
        require(new.encode() not in projected, "projected cadence block already exists")
        projected = projected.replace(old.encode(),new.encode())
    inverse = projected
    for old,new,count in reversed(SOURCE_CHANGES):
        require(inverse.count(new.encode()) == count, "cadence inverse occurrence differs")
        inverse = inverse.replace(new.encode(),old.encode())
    require(inverse == raw and sha(inverse) == HELPER_SHA256, "cadence complete source inverse differs")
    return projected,{"helper_sha256":HELPER_SHA256,"projected_sha256":sha(projected),
        "inverse_sha256":sha(inverse),"exact_whole_source_inverse":True,
        "changes":[{"old":old,"new":new,"count":count} for old,new,count in SOURCE_CHANGES]}


def load_implementation(root=WORKSPACE):
    root = Path(root).resolve()
    projected, proof = project_source((root/HELPER).read_bytes())
    module = types.ModuleType("mr3_learning._reach_private_cadence")
    module.__package__ = "mr3_learning"
    module.__file__ = __file__
    exec(compile(projected,str(root/HELPER),"exec"),module.__dict__)
    require(module.COMPILED == COMPILED and module.PERIOD == PERIOD and module.ACTUATION == ACTUATION,
            "projected cadence constants differ")
    provenance={"schema":"mr3-reach-cadence-implementation-v1",
        "effective_entry":{"path":str(Path(__file__).resolve()),"sha256":sha(Path(__file__).read_bytes())},
        "helper":{"path":str(HELPER),"sha256":HELPER_SHA256},"projection":proof,
        "scope":"Original publication/packet GID/20ms source/34ms update/selected-causal-source mathematics execute on new artifacts; only explicit profile, schema and six-source identities change."}
    return module,provenance


def source_proof(freeze, root=WORKSPACE):
    result = runtime.source_proof(Path(root),freeze)
    for relative in (HELPER,Path(__file__).resolve().relative_to(root)):
        raw=(Path(root)/relative).read_bytes()
        frozen=subprocess.check_output(["git","show",freeze+":"+str(relative)],cwd=root)
        require(raw == frozen,"reach cadence entry/helper differs from current source freeze")
        result[str(relative)]={"git_source":freeze+":"+str(relative),"sha256":sha(raw)}
    return result


def audit_episode(directory, freeze, inputs):
    """Public episode role is a conjunction, never the old cadence result alone."""
    module,proof=load_implementation()
    result=module.audit_episode(Path(directory),freeze,inputs)
    report=runtime.audit_episode(Path(directory),freeze)
    require(report.get("passed") is True and report.get("independent_necessary_replay") is True
            and report.get("continuous_physical_model_proved") is False,
            "reach cadence requires the complete new runtime/drive necessary replay")
    result.update(safety_contract=CONTRACT,implementation_provenance=proof,
                  runtime_drive_conjunction=report,continuous_physical_model_proved=False,
                  actual_loaded_elf_custody_required=True)
    return result


def audit(directory, freeze):
    module,proof=load_implementation()
    # Keep original episode discovery, exception-to-FAIL/INCOMPLETE behavior,
    # stable inputs and finite window logic. Only its per-episode conjunction is
    # strengthened; no original artifact or metadata is rewritten or stripped.
    module.audit_episode=audit_episode
    result=module.audit(directory,freeze)
    result.update(safety_contract=CONTRACT,implementation_provenance=proof,
        continuous_physical_model_proved=False,actual_loaded_elf_custody_required=True,
        scope="New source-bound reach/v2 runtime+wheel/application and independent20ms WORLD/driverTF packet receipts, latest selected sources and34ms actual updates; live actual ELF/process custody remains separately mandatory, continuous plant remains conditional.")
    try:
        result["source_proof"]=source_proof(freeze)
    except (OSError,ValueError,subprocess.SubprocessError) as error:
        result["errors"].append({"error":repr(error)})
        result["status"],result["passed"]="FAIL",False
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory",type=Path)
    parser.add_argument("--freeze",required=True)
    parser.add_argument("--output",required=True,type=Path)
    args=parser.parse_args(argv)
    if args.output.exists():parser.error("output exists; preserve the original result")
    result=audit(args.directory,args.freeze)
    with args.output.open("x") as stream:
        json.dump(result,stream,indent=2,allow_nan=False);stream.write("\n")
    print(json.dumps({"passed":result["passed"],"status":result["status"],"output":str(args.output)}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
