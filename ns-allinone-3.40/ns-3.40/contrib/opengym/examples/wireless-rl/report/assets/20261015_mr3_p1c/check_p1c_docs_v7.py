#!/usr/bin/env python3
"""Check active P1C Markdown links, shell syntax and source scope offline."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess


WIRELESS = "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/"
ROS = "ros2_ws/ros2-multi-robot-automap/"
DOCUMENTS = ["README.md", "AGENTS.md", "ns-allinone-3.40/AGENTS.md"] + [
    WIRELESS + name for name in (
        "AGENTS.md", "RESEARCH_PLAN.md", "IMPLEMENTATION_PLAN.md", "MR3_TASK_CONTRACT.md",
        "MR3_ADAPTER_CONTRACT.md", "MR3_ENV_CONTRACT.md", "USER_GUIDE.md",
        "report/20261015_mr3_p1c.md", "report/README.md", "report/20261015_mr3_2d_option.md")
] + [ROS + name for name in (
    "README.md", "AGENTS.md", "user_guide.md", "launch_commands.md", "Technical_Manual.md")]


def check(root):
    links, blocks = 0, 0
    hashes = {}
    for relative in DOCUMENTS:
        path = root / relative
        body = path.read_text()
        hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        fences = re.findall(r"^```[^\n]*$", body, re.M)
        if len(fences) % 2:
            raise ValueError("unbalanced Markdown fences: " + relative)
        for target in re.findall(r"(?<!!)\[[^\]\n]+\]\(([^)\n]+)\)", body):
            if "://" in target or target.startswith("#"):
                continue
            target = target.split("#", 1)[0].strip("<>")
            if target and not (path.parent / target).exists():
                raise ValueError("missing local link: " + relative + " -> " + target)
            links += bool(target)
        for block in re.findall(r"```(?:bash|sh)\n(.*?)```", body, re.S):
            result = subprocess.run(["bash", "-n"], input=block, text=True, capture_output=True)
            if result.returncode:
                raise ValueError("shell syntax: " + relative + ": " + result.stderr)
            blocks += 1
    expected = "8fe1495b6624cd9136f3ce160acaa274428e54ae"
    for ref in ("p2c1/global-mission-20261012", "origin/p2c1/global-mission-20261012"):
        actual = subprocess.check_output(["git", "rev-parse", ref], cwd=root).decode().strip()
        if actual != expected:
            raise ValueError("original-route backup changed: " + ref)
    branches = subprocess.check_output(
        ["git", "for-each-ref", "--format=%(refname:short)", "refs/heads"], cwd=root
    ).decode().splitlines()
    if set(branches) != {"main", "p2c1/global-mission-20261012"}:
        raise ValueError("unexpected local branch inventory")
    return {
        "schema": "mr3-p1c-doc-static-checks-v7", "passed": True,
        "checked_at": datetime.now(timezone.utc).isoformat(), "markdown_files": len(DOCUMENTS),
        "local_links_checked": links, "balanced_fences": True,
        "bash_blocks_syntax_checked": blocks, "document_commands_executed": False,
        "original_route_backup_unchanged": True, "only_two_local_branches": True,
        "file_sha256": hashes,
        "checker_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "scope": "static documentation only; no native, GPU, training or acceptance credit",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output exists; choose a new path")
    root = next(parent for parent in Path(__file__).resolve().parents if (parent / ".git").exists())
    result = check(root)
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps({key: value for key, value in result.items() if key != "file_sha256"}))


if __name__ == "__main__":
    main()
