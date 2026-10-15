#!/usr/bin/env python3
"""Verify finalized v7 evidence offline, with explicit source and execution binding.

Run only after all eight stages and canonical archives have closed. No native,
ROS, GPU, policy, process-control, or historical-verdict modification occurs.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import time


WIRELESS = "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/"
ASSETS = WIRELESS + "report/assets/20261015_mr3_p1c/"
LEGACY_NAME = "verify_mr3_p1c_v6_evidence.py"
LEGACY_SHA = "ab038db30458f42876525db90d9760ec9fb0d6c8e6790f78c72a638e307fcb69"
PRIOR_FAILURES = {
    "workers2_v6_benchmark_audit.json":
        "227fe6bcba7d4dfa21a5359761e9a3159cd1d19704649f4d7fcfc31c61762f35",
    "worker2_w0_e2_v6_audit.json":
        "173d45b2366a6b6bcab9f805976ab02a4f739ec3a88c1f713f8b3a6d7bfc8f5d",
    "deadline_v6_command_time_v7_negative_audit.json":
        "393dbc8c85655bf3c7333a48b5cd4a0d859a8324f8e6db48dc709c9b5dd40ee9",
}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_legacy(root):
    path = root / ASSETS / LEGACY_NAME
    require(hashlib.sha256(path.read_bytes()).hexdigest() == LEGACY_SHA,
            "immutable v6 verifier changed")
    return load_module("mr3_v7_integrity_base_v6", path)


class Verifier:
    def __init__(self, root, freeze, binding_path):
        require(isinstance(freeze, str) and re.fullmatch(r"[0-9a-f]{40}", freeze),
                "--freeze requires the exact40-hex v7 source commit")
        self.root, self.freeze = Path(root).resolve(), freeze
        self.assets, self.native = self.root / ASSETS, self.root / ASSETS / "native_v7"
        self.base = load_legacy(self.root)
        self.binding_path = Path(binding_path).resolve()
        require(self.binding_path.is_relative_to(self.root), "binding escapes repository")
        self.binding_sha = self.base.digest(self.binding_path)
        self.binding = self.base.read_json(self.binding_path)
        self.git_hashes = {}

    def verify_source(self, relative, expected):
        path = self.base.repository_path(self.root, relative)
        relative = str(path.relative_to(self.root))
        require(isinstance(expected, str) and re.fullmatch(r"[0-9a-f]{64}", expected),
                "invalid bound source SHA: " + relative)
        if relative not in self.git_hashes:
            blob = subprocess.check_output(["git", "show", self.freeze + ":" + relative],
                                           cwd=self.root)
            self.git_hashes[relative] = hashlib.sha256(blob).hexdigest()
        require(self.git_hashes[relative] == expected, "frozen Git source differs: " + relative)
        editorial = path.suffix == ".md"
        if not editorial:
            self.base.verify_hash(self.root, relative, expected)
        return {"path": relative, "sha256": expected, "git_freeze": self.freeze,
                "current_bytes_checked": not editorial,
                "scope": ("frozen normative Markdown blob" if editorial else
                          "Git and current bytes")}

    def verify_sources(self):
        binding = self.binding
        require(binding.get("schema") == "mr3-p1c-v7-execution-binding-v1"
                and binding.get("freeze") == self.freeze, "wrong execution binding identity")
        driver_item = binding["files"]["driver"]
        require(driver_item["path"] == ASSETS + "v7_execution_driver.py",
                "wrong bound driver")
        self.verify_source(driver_item["path"], driver_item["sha256"])
        self.driver = load_module("mr3_integrity_bound_v7_driver", self.root / driver_item["path"])
        for alias, relative in self.driver.FILES.items():
            require(self.base.repository_path(self.root, binding["files"][alias]["path"]) ==
                    self.root / relative, "wrong bound alias: " + alias)
        records = [self.verify_source(item["path"], item["sha256"]) for item in
                   [*binding["files"].values(), *binding.get("additional_files", [])]]
        require(binding["files"]["scalar_auditor"]["sha256"] == self.driver.SCALAR_SHA and
                binding["files"]["scalar_fault_subset"]["sha256"] == self.driver.SUBSET_SHA,
                "immutable scalar helper differs")
        self.verify_source(ASSETS + "audit_mr3_env_contact_phase_v2.py", self.driver.BASE_SHA)
        self.plan = self.base.read_json(self.root / self.driver.FILES["plan"])
        checks = self.base.read_json(self.root / self.driver.FILES["implementation_checks"])
        require(checks["prospective_native_plan_sha256"] == binding["files"]["plan"]["sha256"],
                "implementation/plan binding differs")
        sources = checks["source_sha256"]
        require(isinstance(sources, dict) and sources, "empty implementation source inventory")
        source_records = [self.verify_source(path, expected) for path, expected in sources.items()]
        implementation_refs = [self.verify_source(item["path"], item["sha256"])
                               for item in checks.get("additional_files", [])]
        documents = [self.verify_source(path, expected) for path, expected in
                     checks.get("documentation", {}).get("file_sha256", {}).items()]
        bound_hashes = {item["path"]: item["sha256"] for item in
                        [*binding["files"].values(), *binding.get("additional_files", [])]}
        for field, name in (("independent_reward_auditor_v3_sha256", "reward_gate_audit_v3.py"),
                            ("offline_phase_auditor_v3_sha256",
                             "audit_mr3_env_contact_phase_v3.py"),
                            ("independent_command_time_auditor_v7_sha256",
                             "audit_command_time_v7.py"),
                            ("independent_resource_analysis_v2_sha256",
                             "resource_analysis_v2.py")):
            require(checks[field] == bound_hashes[ASSETS + name],
                    "implementation helper pin differs: " + field)
        self.profile_sha = binding["files"]["profile"]["sha256"]
        require(self.plan["transport_profile"]["sha256"] == self.profile_sha,
                "plan/profile binding differs")
        phase_item = binding["files"]["phase_auditor"]
        self.phase = load_module("mr3_integrity_bound_v7_phase", self.root / phase_item["path"])
        _, self.audit, self.command, self.phase_proof = self.phase.load_components(
            self.freeze, self.root)
        require(binding["files"]["command_time_auditor"]["sha256"] == self.phase.COMMAND_SHA256,
                "phase/command-time helper binding differs")
        self.stages = self.driver.build_stages(self.root, self.plan, self.freeze)
        self.stage_by_name = {row["name"]: row for row in self.stages}
        require(len(self.stages) == 8, "eight stage declarations required")
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.root,
                                       text=True).strip()
        subprocess.check_call(["git", "merge-base", "--is-ancestor", self.freeze, head],
                              cwd=self.root)
        history = []
        for name, expected in PRIOR_FAILURES.items():
            item = self.base.verify_hash(self.root, ASSETS + name, expected)
            require(self.base.read_json(self.assets / name)["passed"] is False,
                    "historical FAIL relabeled: " + name)
            history.append(item)
        return {"passed": True, "binding": str(self.binding_path.relative_to(self.root)),
                "binding_sha256": self.binding_sha, "current_HEAD": head,
                "HEAD_is_source_or_descendant": True, "bound_files": records,
                "source_count": len(source_records), "source_files": source_records,
                "implementation_additional_files": implementation_refs,
                "frozen_document_blobs": documents,
                "legacy_verifier_sha256": LEGACY_SHA, "historical_failures_retained": history,
                "old_native_PASS_transferred": False}

    def verify_manifest(self, path, stage):
        value = self.base.read_json(path)
        selected_root = self.base.repository_path(self.root, value["selected_root"])
        original_root = self.base.repository_path(self.root, value["original_root"])
        relative = path.parent.relative_to(self.native / stage["name"])
        require(selected_root == path.parent and original_root == stage["directory"] / relative,
                "manifest original/selected stage roots differ")
        require(value["schema"] == "mr3-selected-native-evidence-manifest-v1"
                and value["source_freeze"] == self.freeze and value["originals_modified"] is False,
                "manifest identity differs: " + str(path))
        files = value["files"]
        require(isinstance(files, list) and files and value["original_file_count"] == len(files),
                "manifest count differs")
        for row in files:
            original = self.base.repository_path(self.root, row["original"])
            selected = self.base.repository_path(self.root, row["selected"])
            require(original.is_relative_to(original_root)
                    and selected.is_relative_to(selected_root),
                    "manifest file crosses its stage/root")
            self.base.verify_hash(self.root, row["original"], row["original_sha256"])
            self.base.verify_hash(self.root, row["selected"], row["selected_sha256"])
            require(original.stat().st_size == row["original_bytes"] and
                    selected.stat().st_size == row["selected_bytes"], "manifest size differs")
            encoding = row["encoding"]
            require(encoding == "identity" or encoding.startswith("gzip"), "unknown encoding")
            decoded = self.base.digest(selected, decoded=encoding.startswith("gzip"))
            require(decoded == row["decoded_selected_sha256"] == row["original_sha256"]
                    and row["decoded_matches_original"] is True, "decoded evidence bytes differ")
            previous = self.manifest_originals.setdefault(str(original), row["original_sha256"])
            require(previous == row["original_sha256"], "original hash differs across manifests")
            self.selected_artifacts.add(str(selected))
        count = value.get("selected_artifact_count", value.get("selected_original_artifact_count"))
        require(count == len({row["selected"] for row in files}), "selected count differs")
        self.base.verify_manifest_references(self.root, value)
        return {"path": str(path.relative_to(self.root)), "sha256": self.base.digest(path),
                "original_records": len(files), "selected_artifacts": count}

    def verify_manifests(self):
        require({path.name for path in self.native.iterdir() if path.is_dir()} ==
                set(self.stage_by_name), "canonical stage set differs")
        self.manifest_originals, self.selected_artifacts = {}, set()
        results, expected = [], set()
        for stage in self.stages:
            selected = self.native / stage["name"]
            expected.add(selected / "manifest.json")
            if stage["name"] != "clock":
                count = stage["declaration"]["workers"] * len(
                    stage["declaration"]["schedule"].split(","))
                metadata = sorted(selected.glob("worker*/episode*/metadata.json"))
                require(len(metadata) == count,
                        "canonical episode count differs: " + stage["name"])
                expected.update(path.with_name("manifest.json") for path in metadata)
        actual = set(self.native.rglob("manifest.json"))
        require(actual == expected, "missing or unexpected canonical episode manifest")
        for path in sorted(actual):
            stage_name = path.relative_to(self.native).parts[0]
            results.append(self.verify_manifest(path, self.stage_by_name[stage_name]))
        return {"passed": True, "manifests": results,
                "unique_original_files": len(self.manifest_originals),
                "unique_selected_artifacts": len(self.selected_artifacts),
                "decoded_hashes_verified": True}

    def verify_method(self, row):
        proof = row["offline_contact_phase_audit"]
        require(row["schema"] == "mr3-p1c-contact-phase-audit-v3" and
                row["passed"] is True and row["errors"] == [], "phase3 audit did not pass")
        require(proof["freeze"] == self.freeze and proof["method"] == self.phase.METHOD
                and proof["wrapper_sha256"] == self.binding["files"]["phase_auditor"]["sha256"]
                and proof["only_overridden_functions"] == ["audit_contacts", "audit_protocol"]
                and proof["original_results_modified"] is False
                and proof["base_v2"]["sha256"] == self.phase.BASE_SHA256
                and proof["base_v2"]["contact_logic_modified"] is False
                and proof["command_time_gate"]["sha256"] == self.phase.COMMAND_SHA256,
                "phase3 method/helper binding differs")
        require({key: value["sha256"] for key, value in proof["frozen_sources"].items()} ==
                {key: value["sha256"] for key, value in self.phase_proof.items()},
                "phase3 source pins differ")

    def verify_episode_audit(self, row, expected_fault=False):
        require(type(expected_fault) is bool, "fault scope flag must be boolean")
        require(row["passed"] is True and row["errors"] == [] and row["freeze"] == self.freeze,
                "episode audit failed or has another freeze")
        require(row["expected_infrastructure_fault"] is expected_fault
                and row["complete_episode_credit"] is (not expected_fault)
                and row["transitions"]["complete"] is (not expected_fault),
                "normal/fault episode scope differs")
        require(row["ordered_shutdown"]["proven"] is (not expected_fault),
                "fault/normal ordered shutdown credit differs")
        timing = row["protocol"]["command_time"]
        require(timing["passed"] is True and timing["errors"] == []
                and timing["method"] == self.command.METHOD
                and timing["complete_episode_credit"] is False
                and timing["commands_checked"] == row["transitions"]["submitted_action_count"]
                and timing["accepted_commands"] == row["protocol"]["accepted_action_count"]
                and timing["rejected_commands"] == row["protocol"]["rejected_action_count"]
                and len(timing["bindings"]) == timing["commands_checked"]
                and all(item["epoch"] == row["epoch"] and item["failure"] is None
                        for item in timing["bindings"]),
                "command-time gate failed or lost coverage")
        if expected_fault:
            require(row["transitions"]["transition_count"] == 4 and "contacts" not in row,
                    "killed prefix acquired complete contact/episode credit")
        else:
            require(row["contacts"]["passed"] is True, "normal contact audit missing")

    def verify_raw_coverage(self, row):
        self.base.verify_audit_evidence(self.root, row)
        directory = self.base.repository_path(self.root, row["directory"])
        for name, expected in row["evidence_sha256"].items():
            require(self.manifest_originals.get(str(directory / name)) == expected,
                    "audited raw evidence lacks canonical manifest coverage: " + name)
        for episode in row.get("episodes", []):
            self.verify_raw_coverage(episode)

    def verify_scalar(self, stage, top):
        scalar = self.base.read_json(stage["scalar_output"])
        fault = stage["name"] == "fault"
        require(scalar["freeze"] == self.freeze and scalar["reset_epoch_and_pid_unique"] is True,
                "scalar freeze/reset binding differs")
        field = "completed_subset_scalar_checks_passed" if fault else "passed_scalar_checks"
        require(scalar[field] is True, "scalar v3 audit did not pass")
        normal = {row["epoch"]: row for row in top["episodes"]
                  if row["expected_infrastructure_fault"] is False}
        require({row["epoch"] for row in scalar["episodes"]} == set(normal)
                and len(scalar["episodes"]) == len(normal), "scalar epoch scope differs")
        for row in scalar["episodes"]:
            primary = normal[row["epoch"]]
            require(row["errors"] == [] and row["transitions"] ==
                    primary["transitions"]["transition_count"],
                    "scalar episode count/error differs")
            rejected = {item["command_id"] for item in
                        primary["protocol"]["command_time"]["bindings"]
                        if item["receipt_kind"] == "action_rejected"}
            require({item["command_id"] for item in row["rejected_action_bindings"]} == rejected,
                    "scalar rejection/command-time receipt coverage differs")
        if fault:
            excluded = scalar["excluded_killed_prefix"]
            prefix = next(row for row in top["episodes"] if row["expected_infrastructure_fault"])
            require(scalar["schema"] == "mr3-reward-fault-completed-subset-audit-v3"
                    and scalar["helper_sha256"] == self.driver.SCALAR_SHA
                    and scalar["driver_sha256"] == self.driver.SUBSET_SHA
                    and scalar["errors"] == [] and scalar["completed_subset_transitions"] == 24
                    and scalar["whole_fault_benchmark_reward_audit_performed"] is False
                    and len(excluded) == 1 and excluded[0]["epoch"] == prefix["epoch"]
                    and excluded[0]["primary_prefix_transition_count"] == 4
                    and excluded[0]["complete_episode_credit"] is False
                    and excluded[0]["aux_complete_reward_contact_clean_closure_credit"] is False,
                    "fault scalar subset gained complete-prefix credit")
            references = excluded[0]["primary_prefix_audit_sources"]
            require(any(self.base.repository_path(self.root, item["path"]) ==
                        stage["prefix_output"] and item["sha256"] ==
                        self.base.digest(stage["prefix_output"]) for item in references),
                    "fault subset lacks its actual prefix audit reference")
        else:
            require(scalar["schema"] == "mr3-reward-scalar-audit-v3", "wrong scalar schema")
        return scalar

    def verify_audits(self, matrix_path):
        tops, results, epochs = {}, [], set()
        for stage in self.stages:
            name = stage["name"]
            if name == "clock":
                continue
            top = self.base.read_json(stage["primary_output"])
            self.verify_method(top)
            require(top["freeze"] == self.freeze and
                    self.base.repository_path(self.root, top["directory"]) == stage["directory"],
                    "wrong benchmark stage/freeze")
            self.verify_raw_coverage(top)
            expected_count = stage["declaration"]["workers"] * len(
                stage["declaration"]["schedule"].split(","))
            require(len(top["episodes"]) == expected_count, "primary episode count differs")
            fault_rows = [row for row in top["episodes"] if row["expected_infrastructure_fault"]]
            require(len(fault_rows) == int(name == "fault"), "unexpected fault scope")
            for row in top["episodes"]:
                self.verify_episode_audit(row, row["expected_infrastructure_fault"])
                require(row["epoch"] not in epochs, "episode epoch reused across stages")
                epochs.add(row["epoch"])
            if name == "fault":
                prefix = self.base.read_json(stage["prefix_output"])
                self.verify_method(prefix)
                self.verify_episode_audit(prefix, True)
                require(self.base.original_result(prefix) == fault_rows[0],
                        "separate fault-prefix audit differs from its benchmark")
                manifest = self.base.read_json(self.native / name / "worker0" /
                                               "episode001_open_101/manifest.json")
                no_credit = ("complete_episode_credit", "normal_native_shutdown_credit",
                             "complete_contact_monitoring_credit")
                require(all(manifest[key] is False for key in no_credit),
                        "canonical killed prefix acquired full credit")
            scalar = self.verify_scalar(stage, top)
            if name == "deadline":
                row, scalar_row = top["episodes"][0], scalar["episodes"][0]
                require(row["transitions"]["transition_count"] == 300
                        and row["transitions"]["sampled_physical_time_sec"] == 300.
                        and row["protocol"]["goal_count"] == 0
                        and row["protocol"]["rejected_action_count"] == 0
                        and all(item["action"] == 888 and item["receipt_kind"] == "action"
                                for item in row["protocol"]["command_time"]["bindings"])
                        and scalar_row["evaluation_reason"] == "timeout"
                        and scalar_row["reward_term_sums"]["failure"] == -20.
                        and scalar_row["reward_term_sums"]["invalid"] == 0.,
                        "deadline KEEP/time/reward semantics differ")
                records = self.audit.Evidence(Path(row["directory"])).rows("transitions.jsonl")
                last = records[-1]
                require(last["terminated"] is True and last["truncated"] is False
                        and last["info"]["reward_diagnostics"]["reason"] == "timeout"
                        and last["info"]["reward_diagnostics"]["remaining_sim_time"] == 0.,
                        "finite deadline incorrectly truncates or changes reason")
            if name == "terminal":
                require([row["transitions"]["final_dt"] for row in top["episodes"]] == [.02, 0.]
                        and [row["transitions"]["zero_duration_terminal_count"]
                             for row in top["episodes"]] == [0, 1]
                        and all(row["reward_term_sums"]["failure"] == -20.
                                for row in scalar["episodes"]),
                        "terminal short/zero scope differs")
            tops[name] = top
            results.append({"stage": name, "primary": str(stage["primary_output"]),
                            "primary_sha256": self.base.digest(stage["primary_output"]),
                            "scalar": str(stage["scalar_output"]),
                            "scalar_sha256": self.base.digest(stage["scalar_output"]),
                            "passed": True})
        matrix = self.base.read_json(matrix_path)
        self.verify_method(matrix)
        require(len(matrix["benchmarks"]) == len(self.driver.MATRIX) == 6,
                "matrix group count differs")
        seen = set()
        for row in matrix["benchmarks"]:
            name = Path(row["directory"]).name.removeprefix("mr3_p1c_v7_")
            require(name in self.driver.MATRIX and name not in seen and
                    self.base.original_result(tops[name]) == row,
                    "matrix/top phase3 results differ")
            seen.add(name)
        require(seen == set(self.driver.MATRIX), "matrix omits a declared group/deadline")
        self.tops = tops
        return {"passed": True, "seven_top_and_scalar_audits": results,
                "episode_count": len(epochs),
                "normal_complete_episodes": len(epochs) - 1, "fault_prefixes": 1,
                "matrix": str(matrix_path), "matrix_sha256": self.base.digest(matrix_path),
                "scope": "existing phase3/command-time/scalar verdicts and raw hashes; "
                         "no truth replay"}

    def verify_journal(self):
        path = self.assets / "v7_execution.jsonl"
        records = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        require(records and records[0]["kind"] == "execution_binding_verified" and
                records[0]["binding_sha256"] == self.binding_sha and
                records[-1]["kind"] == "all_eight_stages_and_declared_audits_complete",
                "execution journal is incomplete or uses another binding")
        require(all(row["freeze"] == self.freeze for row in records)
                and all(left["monotonic_ns"] <= right["monotonic_ns"]
                        for left, right in zip(records, records[1:])),
                "journal freeze/time regression")
        require(not any(row["kind"] in ("stopped_after_failure", "command_interrupted_or_failed")
                        for row in records), "journal contains a failure/interrupt")
        expected = []
        for stage in self.stages:
            name = stage["name"]
            expected.append((name, "native", stage["native"]))
            if name != "clock":
                if name == "fault":
                    expected.append((name, "prefix_phase3", stage["prefix"]))
                expected.extend(((name, "primary_phase3", stage["primary"]),
                                 (name, "scalar_v3", stage["scalar"])))
        matrix = self.assets / "matrix_v7_contact_phase_v3_audit.json"
        argv = self.driver.phase_command(self.assets, self.freeze,
                                         [self.stage_by_name[name]["directory"]
                                          for name in self.driver.MATRIX], matrix, "--matrix")
        expected.append(("matrix", "primary_phase3", argv))
        started = [(index, row) for index, row in enumerate(records)
                   if row["kind"] == "command_started"]
        completed = [(index, row) for index, row in enumerate(records)
                     if row["kind"] == "command_complete"]
        require(len(started) == len(completed) == len(expected) == 24,
                "journal command count differs")
        previous_end, results = -1, []
        for (start_index, start), (end_index, end), (stage, role, command) in zip(
                started, completed, expected):
            require(previous_end < start_index < end_index and
                    (start["stage"], start["role"]) == (end["stage"], end["role"]) == (stage, role)
                    and start["argv"] == command and start["binding_sha256"] == self.binding_sha
                    and end["returncode"] == 0, "journal command order/exit/binding differs")
            previous_end = end_index
            self.base.verify_hash(self.root, start["stdout"], end["stdout_sha256"])
            self.base.verify_hash(self.root, start["stderr"], end["stderr_sha256"])
            results.append({"stage": stage, "role": role, "returncode": 0,
                            "stdout_sha256": end["stdout_sha256"],
                            "stderr_sha256": end["stderr_sha256"]})
        require([row["stage"] for row in records
                 if row["kind"] == "stage_all_declared_gates_passed"]
                == [row["name"] for row in self.stages if row["name"] != "clock"]
                and records[-1]["matrix_sha256"] == self.base.digest(matrix),
                "journal stage/matrix completion differs")
        return {"passed": True, "path": str(path.relative_to(self.root)),
                "sha256": self.base.digest(path), "commands": results,
                "all_eight_stages_completed": True, "automatic_retry": False}

    def verify_owned_identities(self):
        identities, bare, receipts = {}, {}, []

        def add(identity, source):
            pid, ticks = identity["pid"], identity["start_ticks"]
            require(type(pid) is int and pid > 0 and type(ticks) is int and ticks > 0,
                    "invalid saved process identity")
            identities.setdefault((pid, ticks), set()).add(str(source.relative_to(self.root)))

        metadata_paths = sorted(self.native.glob("*/worker*/episode*/supervisor_metadata.json"))
        expected = sum(row["declaration"]["workers"] *
                       len(row["declaration"]["schedule"].split(","))
                       for row in self.stages if row["name"] != "clock")
        require(len(metadata_paths) == expected, "ownership receipt episode count differs")
        for path in metadata_paths:
            value = self.base.read_json(path)
            metadata = self.base.read_json(path.with_name("metadata.json"))
            self.verify_metadata(metadata)
            require(metadata["epoch"] == value["epoch"], "canonical ownership epoch differs")
            add(value["worker_identity"], path)
            receipt_path = path.with_name("supervisor_shutdown.json")
            receipt = self.base.read_json(receipt_path)
            require(receipt["epoch"] == value["epoch"] and
                    receipt["remaining_owned_processes"] == [] and
                    receipt["remaining_owned_zombies"] == [], "saved ownership cleanup not empty")
            for identity in receipt["owned_processes_seen"]:
                add(identity, receipt_path)
            receipts.append({"path": str(receipt_path.relative_to(self.root)),
                             "sha256": self.base.digest(receipt_path)})
        for path in self.native.glob("*/worker*/episode*/native_stop.json"):
            pid = self.base.read_json(path)["native_cli_pid"]
            require(type(pid) is int and pid > 0, "invalid native stop PID")
            bare.setdefault(pid, set()).add(str(path.relative_to(self.root)))
        clock_path = self.native / "clock/summary.json"
        clock = self.base.read_json(clock_path)
        self.verify_metadata(clock)
        require(clock["passed"] is True and clock["error"] is None and
                clock["server_returncode"] == clock["stop_cli_returncode"] == 0,
                "clock native fixture did not close successfully")
        for key in ("server_pid", "helper_pid", "stop_cli_pid"):
            pid = clock[key]
            require(type(pid) is int and pid > 0, "invalid clock PID")
            bare.setdefault(pid, set()).add(str(clock_path.relative_to(self.root)) + ":" + key)
        journal = self.assets / "v7_execution.jsonl"
        for line in journal.read_text().splitlines():
            record = json.loads(line)
            if record.get("kind") == "command_complete":
                pid = record.get("pid")
                require(type(pid) is int and pid > 0, "invalid recorded Popen child PID")
                source = str(journal.relative_to(self.root))
                label = source + ":" + record["stage"] + "/" + record["role"]
                bare.setdefault(pid, set()).add(label)
        started, observed, unbound, violations = time.monotonic_ns(), [], [], []
        for (pid, ticks), sources in sorted(identities.items()):
            current = self.base.proc_identity(pid)
            same = current is not None and current["start_ticks"] == ticks
            row = {"pid": pid, "recorded_start_ticks": ticks, "sources": sorted(sources),
                   "current_proc": current, "recorded_identity_still_exists": same}
            observed.append(row)
            if same:
                violations.append(row)
        for pid, sources in sorted(bare.items()):
            current = self.base.proc_identity(pid)
            row = {"pid": pid, "recorded_start_ticks": None, "sources": sorted(sources),
                   "current_proc": current,
                   "ambiguity": "current same-number PID lacks historical identity"
                   if current is not None else None,
                   "scope": "bare PID; no historical start fabricated; wait/exit receipt "
                            "is the recorded reap proof"}
            unbound.append(row)
            if current is not None:
                violations.append(row)
        return {"passed": not violations, "snapshot_started_monotonic_ns": started,
                "snapshot_finished_monotonic_ns": time.monotonic_ns(), "identities": observed,
                "bare_pids_without_recorded_start_ticks": unbound, "violations": violations,
                "cleanup_receipts": receipts, "recorded_identity_count": len(identities),
                "scope": "current /proc snapshot; saved identity including zombie must be absent; "
                         "different start ticks mean PID reuse; bare PID must be absent"}

    def verify_metadata(self, value):
        require(value["freeze"] == self.freeze and
                value["transport_environment"]["profile_sha256"] == self.profile_sha and
                value["transport_environment"]["RMW_IMPLEMENTATION"] == "rmw_fastrtps_cpp",
                "canonical metadata source/profile/backend differs")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--binding", required=True, type=Path)
    parser.add_argument("--matrix-audit", type=Path)
    parser.add_argument("--extra-evidence", action="append", default=[], type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("output exists; choose a new evidence filename")
    root = next(path for path in Path(__file__).resolve().parents if (path / ".git").exists())
    verifier = Verifier(root, args.freeze, args.binding)
    matrix = (args.matrix_audit.resolve() if args.matrix_audit else
              verifier.assets / "matrix_v7_contact_phase_v3_audit.json")
    report = {"schema": "mr3-p1c-v7-final-evidence-verification-v1", "source_freeze": args.freeze,
              "created_at_utc": datetime.now(timezone.utc).isoformat(),
              "verifier_sha256": verifier.base.digest(Path(__file__)),
              "sections": {}, "errors": [],
              "scope": "offline evidence integrity/completeness and saved identity cleanup; "
                       "no new native, truth replay, GPU, training, or automatic acceptance"}
    operations = (("bound_sources_and_history", verifier.verify_sources),
                  ("canonical_manifests", verifier.verify_manifests),
                  ("formal_audits", lambda: verifier.verify_audits(matrix)),
                  ("execution_journal", verifier.verify_journal),
                  ("owned_identity_snapshot", verifier.verify_owned_identities))
    for name, operation in operations:
        try:
            result = operation()
            report["sections"][name] = result
            if result.get("passed") is False:
                report["errors"].append(name + ": saved owned identity survives or is ambiguous")
        except (OSError, ValueError, TypeError, KeyError, IndexError, EOFError, AttributeError,
                subprocess.SubprocessError) as error:
            report["sections"][name] = {"passed": False, "error": str(error)}
            report["errors"].append(name + ": " + str(error))
    report["extra_evidence"] = []
    for path in args.extra_evidence:
        try:
            verifier.base.read_json(path)
            report["extra_evidence"].append({"path": str(path.resolve()),
                                             "sha256": verifier.base.digest(path),
                                             "scope": "JSON parses; no verdict inferred"})
        except (OSError, ValueError) as error:
            report["errors"].append("extra evidence " + str(path) + ": " + str(error))
    report["passed"] = not report["errors"]
    with args.output.open("x") as output:
        json.dump(report, output, indent=2, sort_keys=True, allow_nan=False)
        output.write("\n")
    print(json.dumps({"passed": report["passed"], "errors": report["errors"],
                      "output": str(args.output)}, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
