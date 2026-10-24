"""Read-only received-input/activity/execution audit of native PPO attempts.

Reuse the existing episode consumers without scripted probe activity gates.
This supplement does not replace audit_ppo, the scientific preparation gates,
or the evaluator's task-success decision.
"""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

from .audit_activity import audit_episode as audit_activity
from .audit_motion import audit_episode as audit_motion
from .audit_preparation import audit_archives, audit_execution_inputs


def verify_sources(freeze):
    """Bind this supplement and the directly reused consumers to Git bytes."""
    module_directory = Path(__file__).resolve().parent
    root = next(parent for parent in module_directory.parents if (parent / ".git").exists())
    proof = {}
    for filename in ("audit_policy_inputs.py", "audit_preparation.py", "audit_activity.py",
                     "audit_motion.py", "audit_ppo.py", "audit_controlled_physics.py",
                     "navigation_archive.py"):
        path = module_directory / filename
        relative = path.relative_to(root).as_posix()
        payload = subprocess.check_output(["git", "show", freeze + ":" + relative],
                                          cwd=root, stderr=subprocess.PIPE)
        if payload != path.read_bytes():
            raise ValueError("policy input consumer differs from freeze: " + relative)
        proof[relative] = {"sha256": hashlib.sha256(payload).hexdigest(),
                           "git_source": freeze + ":" + relative}
    return proof


def audit_run(directory, freeze):
    directory = Path(directory).resolve()
    result = {
        "schema": "mr3-policy-inputs-audit-v1", "directory": str(directory),
        "freeze": freeze, "errors": [], "episodes": [],
        "scope": ("actual PPO received-input archives, activity integrity and execution "
                  "causality only; no scripted motion coverage, audit_ppo replacement, "
                  "34-gate equivalence or task-success credit"),
    }

    def check(label, operation, errors):
        try:
            return operation()
        except Exception as error:
            errors.append(label + ": " + repr(error))
            return None

    def require(condition, message):
        if not condition:
            raise ValueError(message)

    def load_document(path):
        document = json.loads(path.read_text())
        require(isinstance(document, dict), "expected a JSON object: " + str(path))
        return document

    require(re.fullmatch(r"[0-9a-f]{40}", freeze) is not None,
            "freeze must be an exact 40-hex Git commit identity")
    result["source_proof"] = check("consumer source binding", lambda: verify_sources(freeze),
                                   result["errors"])
    documents = {}
    for name in ("metadata", "summary"):
        document = check(name, lambda name=name: load_document(
            directory / (name + ".json")), result["errors"])
        if document is not None:
            check(name + " freeze", lambda document=document: require(
                isinstance(document, dict) and document.get("freeze") == freeze,
                "run source freeze mismatch"), result["errors"])
        documents[name] = document

    native = directory / "native"
    attempts = sorted(path.resolve() for path in native.glob("round*/worker*/episode*")
                      if path.is_dir())
    metadata_attempts = {path.parent.resolve() for path in native.glob(
        "round*/worker*/episode*/metadata.json")}

    def inventory():
        summary = documents["summary"]
        require(isinstance(summary, dict) and isinstance(summary.get("episodes"), list),
                "summary lacks the complete native episode inventory")
        listed = [Path(row["directory"]).resolve() for row in summary["episodes"]]
        require(attempts, "no native attempts found")
        require(len(attempts) == len(set(attempts))
                and all(path.is_relative_to(native.resolve()) for path in attempts),
                "duplicate or out-of-tree native attempt")
        require(len(listed) == len(set(listed)), "duplicate summary native attempt")
        require(set(attempts) == metadata_attempts == set(listed),
                "unknown, unlisted or missing native attempt/metadata")
        require(not summary.get("active_attempts") and not summary.get("active_episodes"),
                "active native attempts remain; inventory is not closed")

    check("native attempts", inventory, result["errors"])
    for episode in attempts:
        row = {"directory": str(episode), "errors": []}
        metadata = check("metadata", lambda: load_document(
            episode / "metadata.json"), row["errors"])
        if metadata is not None:
            check("metadata freeze", lambda: require(
                isinstance(metadata, dict) and metadata.get("freeze") == freeze,
                "episode source freeze mismatch"), row["errors"])
        for name, operation in (
                ("observation_archives", lambda: audit_archives(episode)),
                ("activity", lambda: audit_activity(episode)),
                ("motion", lambda: audit_motion(episode)),
                ("execution_inputs", lambda: audit_execution_inputs(
                    episode, motion_review=row.get("motion") or {"passed": False}))):
            prior_errors = len(row["errors"])
            review = check(name, operation, row["errors"])
            row[name] = review
            if len(row["errors"]) == prior_errors:
                check(name + " result", lambda review=review: require(
                    isinstance(review, dict) and review.get("passed") is True,
                    "episode consumer did not pass"), row["errors"])
        row["passed"] = not row["errors"]
        result["errors"].extend(str(episode) + ": " + error for error in row["errors"])
        result["episodes"].append(row)
    result["native_attempts"] = len(attempts)
    result["passed"] = not result["errors"]
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    if re.fullmatch(r"[0-9a-f]{40}", args.freeze) is None:
        parser.error("freeze must be an exact 40-hex Git commit identity")
    if args.output.exists():
        parser.error("audit output exists; choose a new path")
    result = audit_run(args.directory, args.freeze)
    with args.output.open("x") as destination:
        destination.write(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"passed": result["passed"], "errors": result["errors"],
                      "native_attempts": result["native_attempts"],
                      "output": str(args.output)}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
