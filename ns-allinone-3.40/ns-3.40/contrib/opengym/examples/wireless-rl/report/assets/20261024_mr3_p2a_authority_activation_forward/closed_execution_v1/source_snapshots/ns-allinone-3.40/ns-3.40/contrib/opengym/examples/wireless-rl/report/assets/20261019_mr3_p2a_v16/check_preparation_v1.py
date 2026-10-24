"""Read-only V16 static closure; never imports or executes a research consumer.

The validation index selects final CPU checks; all failed attempts remain
historical failures. Raw ordinal snapshots and consoles are checked against
their own actual receipts. --staged additionally verifies exact Git index bytes.
"""
import argparse
import ast
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote, urlsplit


ROOT = Path("/home/zhuyulab/ns3-workspace")
WIRELESS = Path("ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl")
W = ROOT / WIRELESS
ROS = ROOT / "ros2_ws/ros2-multi-robot-automap"
A = Path(__file__).resolve().parent
OPENING = "17920bc6b9d4b20a32adcffad04afe3c24f068b6"
WAIT_SCHEMA = "mr3-v15-finite-preparation-actual-child-wait-v1"
SCHEMA = "mr3-v16-static-preparation-review-v1"
INDEX_SCHEMA = "mr3-p2a-v16-cpu-validation-index-v1"
KNOWN_FAILED_ATTEMPTS = {"qualification_cpu_attempt_v1"}
OLD_ASSETS = tuple(WIRELESS / "report/assets" / name for name in (
    "20261019_mr3_p2a_v14", "20261019_mr3_p2a_v15"))
DOCS = (ROOT / "AGENTS.md", W / "AGENTS.md", W / "RESEARCH_PLAN.md",
        W / "IMPLEMENTATION_PLAN.md", W / "MR3_ENV_CONTRACT.md", W / "MR3_REACH_CONTRACT.md",
        W / "MR3_TASK_CONTRACT.md", W / "report/README.md", W / "report/20261019_mr3_p2a_v16.md",
        ROS / "AGENTS.md", ROS / "user_guide.md", ROS / "launch_commands.md")


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def git(*argv):
    return subprocess.check_output(["git", *map(str, argv)], cwd=ROOT)


def split_paths(raw):
    return [Path(name.decode()) for name in raw.split(b"\0") if name]


def decode(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "duplicate JSON member: " + key)
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError("nonfinite JSON: " + value)))


class Inputs:
    def __init__(self):
        self.bindings = {}

    @staticmethod
    def stat(path):
        s = path.stat()
        return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)

    def read(self, path):
        path = Path(path)
        before = self.stat(path)
        raw = path.read_bytes()
        require(before == self.stat(path), "input changed while read: " + str(path))
        value = {"sha256": sha(raw), "bytes": len(raw)}
        require(self.bindings.setdefault(str(path.resolve()), value) == value,
                "input changed across reads: " + str(path))
        return raw

    def finish(self):
        for name, expected in tuple(self.bindings.items()):
            require(sha(self.read(name)) == expected["sha256"], "input changed before verdict: " + name)


def index_exact(path, raw):
    relative = Path(path).resolve().relative_to(ROOT)
    actual = git("show", ":" + str(relative))
    require(actual == raw, "Git index changed original raw evidence bytes: " + str(relative))
    return {"path": str(relative), "sha256": sha(actual), "bytes": len(actual)}


def receipt_review(path, read, *, final, staged=False):
    path = Path(path)
    raw = read(path)
    value = decode(raw)
    require(value.get("schema") == WAIT_SCHEMA and value.get("actual_waited") is True
            and value.get("native_admission") is False,
            "receipt is not an actual finite CPU/build wait: " + str(path))
    require(type(value.get("actual_returncode")) is int, "actual returncode must be an integer")
    for name in ("started_monotonic_ns", "ended_monotonic_ns"):
        require(type(value.get(name)) is int and value[name] > 0, "invalid actual wait clock")
    duration_ns = value["ended_monotonic_ns"] - value["started_monotonic_ns"]
    duration = Decimal(str(value["actual_child_wait_seconds"]))
    require(duration_ns > 0 and duration.is_finite() and duration == Decimal(duration_ns) / 10**9,
            "recorded seconds differ from original actual nanosecond wait: " + str(path))
    for name in ("coordinator_identity", "child_identity"):
        identity = value[name]
        require(all(type(identity.get(k)) is int and identity[k] > 0 for k in ("pid", "start_ticks")),
                "actual wait lacks positive real PID/start identity")
    require(value["child_identity"].get("parent") == value["coordinator_identity"]["pid"],
            "actual wait child is not its recorded coordinator descendant")
    before, after = value["source_before"], value["source_after"]
    require(type(before) is list and before and type(after) is list
            and len(before) == len(after), "actual source snapshot inventory differs")
    stable = before == after
    require(type(value.get("source_unchanged")) is bool and value["source_unchanged"] is stable,
            "receipt source-unchanged claim differs from original before/after records")
    require(value.get("passed") is (value["actual_returncode"] == 0 and stable),
            "actual receipt passed flag hides failure or source mutation")
    require(not final or value["actual_returncode"] == 0 and stable and value["passed"] is True,
            "a failed attempt was selected for final PASS: " + str(path))
    names, source_paths, staged_proofs = [], set(), []
    for ordinal, (left, right) in enumerate(zip(before, after)):
        source_path = Path(left["path"])
        require(source_path.is_absolute() and source_path.is_relative_to(ROOT)
                and source_path not in source_paths and right["path"] == left["path"],
                "source ownership/order/identity differs")
        source_paths.add(source_path)
        name = f"{ordinal:02d}_{source_path.name}"
        names.append(name)
        snapshot = path.parent / "source_snapshots" / name
        content = read(snapshot)
        require(sha(content) == left["sha256"] and len(content) == left["bytes"],
                "exact ordinal source snapshot differs: " + str(snapshot))
        if staged:
            staged_proofs.append(index_exact(snapshot, content))
    actual_names = {p.name for p in (path.parent / "source_snapshots").iterdir() if p.is_file()}
    require(actual_names == set(names), "ordinal snapshot inventory has missing/extra files")
    console_spec = value["console"]
    console_path = path.parent / "console.log"
    require(Path(console_spec["path"]) == console_path, "receipt refers to another attempt console")
    console = read(console_path)
    require(sha(console) == console_spec["sha256"] and len(console) == console_spec["bytes"],
            "actual raw console differs from its receipt")
    if staged:
        staged_proofs.extend((index_exact(console_path, console), index_exact(path, raw)))
    if final:
        for spec in after:
            current = read(spec["path"])
            require(sha(current) == spec["sha256"] and len(current) == spec["bytes"],
                    "selected final source differs from actual source-after bytes: " + spec["path"])
    return value, {"receipt": str(path), "sha256": sha(raw), "final_selected": final,
        "actual_returncode": value["actual_returncode"], "actual_child_wait_ns": duration_ns,
        "original_seconds": str(duration), "snapshots": len(names),
        "selected_current_source_count": len(source_paths) if final else 0,
        "staged_raw_evidence": staged_proofs}


def validation_review(index_path, read, staged):
    index = decode(read(index_path))
    require(index.get("schema") == INDEX_SCHEMA and index.get("opening_commit") == OPENING,
            "validation index schema/opening commit differs")
    require(index.get("native_admission") is False and index.get("native_runs") == 0
            and index.get("gpu_calls") == 0, "static validation index implies native/GPU admission")
    runs = index["runs"]
    require(type(runs) is list and runs, "validation index has no original attempts")
    rows = {r["name"]: r for r in runs}
    finals = index["final_required"]
    require(len(rows) == len(runs) and type(finals) is list and finals
            and len(finals) == len(set(finals)) and set(finals) <= rows.keys(),
            "duplicate/missing final attempt inventory")
    require(KNOWN_FAILED_ATTEMPTS <= rows.keys(), "known failed attempts were removed from validation history")
    receipts, indexed_paths, failures = [], set(), []
    for name, row in rows.items():
        path = A / row["receipt"]
        require(path.resolve().is_relative_to(A) and path == A / "checks" / name / "actual_wait.json",
                "validation index borrows another ordinal attempt receipt")
        require("selected_final_sources" not in row, "final source-after checks cannot be narrowed by an override")
        value, proof = receipt_review(path, read, final=name in finals, staged=staged)
        require(proof["sha256"] == row["receipt_sha256"], "index receipt raw SHA differs")
        for key in ("actual_returncode", "passed", "actual_child_wait_seconds", "actual_argv", "cwd", "source_unchanged"):
            if key in row:
                require(json.dumps(row[key], sort_keys=True) == json.dumps(value[key], sort_keys=True),
                        "validation index changes actual receipt fact: " + key)
        if value["passed"] is False:
            failures.append(name)
            require(name not in finals, "historical FAIL was relabelled final PASS")
        indexed_paths.add(path.resolve())
        receipts.append(proof)
    require(KNOWN_FAILED_ATTEMPTS <= set(failures), "known failed attempt no longer retains its true FAIL")
    # A static checker cannot include its own unfinished receipt in the index it
    # is checking. Later staged checks may inspect that completed observer as an
    # additional non-credit receipt, using its exact script argv (not a suffix).
    observers = []
    for path in (A / "checks").glob("*/actual_wait.json"):
        if path.resolve() in indexed_paths:
            continue
        value = decode(read(path))
        command = value.get("actual_argv", [])
        cursor = 0
        if command and Path(command[0]).name == "env":
            cursor = 1
            while cursor < len(command) and re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*=.*", command[cursor]):
                cursor += 1
        require(cursor < len(command) and re.fullmatch(r"python(?:\d+(?:\.\d+)*)?", Path(command[cursor]).name),
                "unindexed static observer is not a Python script invocation")
        cursor += 1
        while cursor < len(command) and command[cursor] in ("-B", "-I", "-E", "-s"):
            cursor += 1
        require(cursor < len(command) and command[cursor] == str(Path(__file__).resolve()),
                "completed attempt is omitted from validation index: " + str(path))
        _, proof = receipt_review(path, read, final=False, staged=staged)
        observers.append(proof)
    return {"attempts": receipts, "retained_failures": failures, "final_required": finals,
            "additional_static_observers": observers}


def preserve_history(read, staged):
    old_count = 0
    for prefix in OLD_ASSETS:
        originals = set(split_paths(git("ls-tree", "-r", "--name-only", "-z", OPENING, "--", prefix)))
        require(originals, "original asset inventory is empty: " + str(prefix))
        current = set(split_paths(git("ls-files", "--cached", "--others", "--exclude-standard", "-z", "--", prefix)))
        require(current == originals, "old V14/V15 original asset inventory changed")
        for relative in sorted(originals):
            raw = read(ROOT / relative)
            require(raw == git("show", OPENING + ":" + str(relative)),
                    "old native/CPU failure or original artifact changed: " + str(relative))
            if staged:
                index_exact(ROOT / relative, raw)
            old_count += 1
    log_path = W / "log.md"
    old_log = git("show", OPENING + ":" + str(log_path.relative_to(ROOT)))
    require(read(log_path).startswith(old_log), "shared experiment log is not append-only")
    archive_path = W / "report/ARCHIVE_INDEX.json"
    prior = decode(git("show", OPENING + ":" + str(archive_path.relative_to(ROOT))))
    current = decode(read(archive_path))
    require(type(prior) is dict and all(key in current and current[key] == value for key, value in prior.items()),
            "an old ARCHIVE_INDEX entry was changed or removed")
    return {"opening_commit": OPENING, "old_v14_v15_originals": old_count,
            "shared_log_append_only": True, "unchanged_archive_entries": len(prior)}


def selected_files(staged):
    if staged:
        return set(split_paths(git("diff", "--cached", "--name-only", "-z", "--diff-filter=ACDMRTUXB")))
    return set(split_paths(git("diff", "HEAD", "--name-only", "-z"))) | set(
        split_paths(git("ls-files", "--others", "--exclude-standard", "-z")))


def artifact_sanity(selected, read, staged):
    banned_parts = {"build", "install", "runtime", "runs", "checkpoints", "__pycache__", ".pytest_cache", "node_modules", "bags"}
    banned_suffixes = {".so", ".o", ".a", ".elf", ".bag", ".db3", ".mcap", ".pt", ".pth", ".ckpt", ".onnx", ".pyc"}
    for relative in sorted(selected):
        require(not (set(relative.parts) & banned_parts) and relative.suffix not in banned_suffixes
                and not re.search(r"\.so(?:\.\d+)+$", relative.name),
                "accidental build/runtime/checkpoint/bag artifact selected: " + str(relative))
        path = ROOT / relative
        if not path.exists():
            continue  # A deliberate deletion remains visible in selected paths.
        raw = read(path)
        require(not raw.startswith(b"\x7fELF"), "actual ELF selected for Git: " + str(relative))
        if staged:
            index_exact(path, raw)
    return len(selected)


def markdown_targets(text):
    lines, fence = [], None
    for line in text.splitlines():
        match = re.match(r"\s*(`{3,}|~{3,})", line)
        if match:
            marker = match[1][0]
            if fence is None:
                fence = marker
            elif fence == marker:
                fence = None
            continue
        if fence is None:
            lines.append(re.sub(r"`+[^`]*`+", "", line))
    plain = "\n".join(lines)
    values = re.findall(r"(?<!!)\[[^\]]*\]\(([^)\n]+)\)", plain)
    values += re.findall(r"(?m)^\s*\[[^\]]+\]:\s*(<[^>]+>|\S+)", plain)
    for value in values:
        value = value.strip()
        if value.startswith("<"):
            value = value[1:value.index(">")]
        else:
            value = re.split(r"\s+[\"']", value, 1)[0]
        yield value


def syntax_and_links(selected, read):
    candidates = {ROOT / p for p in selected if (ROOT / p).exists()}
    candidates.update(p for p in A.rglob("*") if p.is_file() and p.suffix in (".py", ".json"))
    for base in (W / "mr3_learning", ROS / "src/multi_robot_exploration"):
        candidates.update(p for p in base.rglob("*.py") if "__pycache__" not in p.parts)
    parsed = {"python": 0, "json": 0, "local_markdown_links": 0}
    for path in sorted(candidates):
        if path.suffix == ".py":
            ast.parse(read(path), filename=str(path)); parsed["python"] += 1
        elif path.suffix == ".json":
            decode(read(path)); parsed["json"] += 1
    log_path = W / "log.md"
    documents = (set(DOCS) | {p for p in candidates if p.suffix == ".md"} | set(A.glob("*.md"))) - {log_path}
    texts = [(path, read(path).decode("utf-8")) for path in sorted(documents)]
    old_log = git("show", OPENING + ":" + str(log_path.relative_to(ROOT)))
    current_log = read(log_path)
    require(current_log.startswith(old_log), "shared log prefix changed before link review")
    # Historical prose remains byte-identical under its original path/scope.
    # Only this session's appended Markdown belongs to the new active link scan.
    texts.append((log_path, current_log[len(old_log):].decode("utf-8")))
    for path, text in texts:
        for target in markdown_targets(text):
            parts = urlsplit(target)
            if not target or target.startswith("#") or parts.scheme not in ("", "file"):
                continue
            local = Path(unquote(parts.path))
            local = local if local.is_absolute() else path.parent / local
            require(local.exists(), "broken active local Markdown link: " + str(path) + " -> " + target)
            parsed["local_markdown_links"] += 1
    return parsed


def check(index_path, staged=False):
    read = Inputs()
    selected = selected_files(staged)
    staged_before = git("ls-files", "--stage", "-z") if staged else None
    validation = validation_review(index_path, read.read, staged)
    history = preserve_history(read.read, staged)
    count = artifact_sanity(selected, read.read, staged)
    syntax = syntax_and_links(selected, read.read)
    subprocess.run(["git", "diff", "--check"], cwd=ROOT, check=True)
    if staged:
        subprocess.run(["git", "diff", "--cached", "--check"], cwd=ROOT, check=True)
        require(git("ls-files", "--stage", "-z") == staged_before, "Git staged source inventory changed during check")
    read.finish()
    return {"schema": SCHEMA, "passed": True, "opening_commit": OPENING,
        "staged": staged, "validation": validation, "history": history,
        "selected_files_checked": count, "syntax": syntax, "bindings": read.bindings,
        "scope": "Static source/evidence/index/history/docs checks only; recorded CPU waits are revalidated, never native scientific or policy reliability credit.",
        "native_runs": 0, "gpu_calls": 0, "native_admission": False,
        "full_new_profile_qualification": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_path", nargs="?", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--index", type=Path, default=A / "validation_index_v1.json")
    parser.add_argument("--staged", action="store_true")
    args = parser.parse_args(argv)
    require((args.output is None) != (args.output_path is None), "give exactly one new output path")
    output = args.output if args.output is not None else args.output_path
    require(not output.exists(), "exclusive output already exists")
    try:
        result = check(args.index, args.staged)
    except Exception as error:
        result = {"schema": SCHEMA, "passed": False, "staged": args.staged,
            "error_type": type(error).__name__, "error": str(error), "native_admission": False}
    # Create only after the closed input scan, so an empty reserved report
    # cannot accidentally be parsed as an input JSON. O_EXCL still refuses races.
    with output.open("x") as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"passed": result["passed"], "output": str(output)}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
