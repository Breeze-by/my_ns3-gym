"""Complete v2 native scientific audit; no old-profile qualification credit."""

import argparse
import json
from pathlib import Path

from .audit_ppo import load_rows, require
from .reach_audit_projection import project_module
from .reach_gates import load_native_gates
from .supervisor import validate_seed_rule

SOURCE_SHA256 = "b7e07ee44188b43f09a94215430fac609d6753f7be5594ce9f4b2308ccf88cab"


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
    plan = json.loads(Path(plan_path).read_text())
    if validate_seed_rule(plan.get("seed_rule", "legacy")) != "legacy":
        from .audit_seed_inputs import audit_episode
        original_archives = module.audit_archives

        def exact_archives(directory):
            result = original_archives(directory)
            metadata = json.loads((Path(directory) / "metadata.json").read_text())
            result["exact_seed_full_replay"] = audit_episode(directory, metadata["freeze"])
            return result

        module.audit_archives = exact_archives
    return module, proof


def audit(directory, root, freeze, plan_path):
    directory, root = Path(directory), Path(root)
    paths = ([directory / "metadata.json"] if (directory / "metadata.json").is_file()
             else sorted(directory.glob("worker*/episode*/metadata.json")))
    require(paths, "no actual reach episodes")
    plan = json.loads(Path(plan_path).read_text())
    for path in paths:
        metadata = json.loads(path.read_text())
        require(metadata.get("safety_contract") == "mr3-reach-v1"
                and metadata.get("execution_phase_protocol") == "mr3-controlled-execution-phase-v2"
                and metadata.get("reset_handshake") == "paused-controlled-state-peer-guard-storage-v2"
                and metadata.get("freeze") == freeze, "missing/mixed new-profile declaration")
        require(metadata.get("seed_rule", "legacy") == plan.get("seed_rule", "legacy"),
                "native preparation seed rule differs from the qualification plan")
    module, proof = load_impl(plan_path)
    result = module.audit(directory, root, freeze)
    result.update(schema="mr3-reach-preparation-full-audit-v1", safety_contract="mr3-reach-v1",
                  immutable_reader_projection=proof,
                  scope="Native/contact/clock/protocol/scalar/evaluator/archive/activity/topology/costmap and complete v2 release. Joint qualification additionally requires every independently declared reach role.")
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
