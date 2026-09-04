#!/usr/bin/env python3
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from validate_workspace_layout import validate_candidate_ledger


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
SHA = "0" * 64


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class AlignmentV7Test(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.task_id = "aln-normal-20260903-001"
        self.base = Path(self.temp.name)
        self.root = self.base / self.task_id
        self.root.mkdir()
        self.script = self.base / "certified.py"
        self.script.write_text("def simulate(runtime, seed, count, observer):\\n    return None\\n", encoding="utf-8")
        self.runtime = self.root / "work/baseline/runtime"
        self.runtime.mkdir(parents=True)
        self.runtime_files = []
        for name in ["game_core.json", "payout_config.json", "reel_config.json", "symbol_catalog.json"]:
            path = self.runtime / name
            value = {"name": name}
            if name == "game_core.json":
                value["meta"] = {"version": self.task_id}
            write(path, value)
            self.runtime_files.append({"name": name, "sha256": sha256(path)})

    def tearDown(self):
        self.temp.cleanup()

    def run_script(self, name, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPTS / name), *map(str, args)],
            check=True,
            capture_output=True,
            text=True,
        )

    def preflight(self):
        return {
            "schema_version": "slot-alignment.preflight.v7",
            "task_id": self.task_id,
            "mode": "normal",
            "status": "READY_FOR_SAMPLES",
            "rtp_group": 1,
            "runtime_environment": "test",
            "python_bin": sys.executable,
            "workspace": {"task_root": f"slot-math-workbench:test/alignments/normal/{self.task_id}/"},
            "game": {"game_code": "test", "game_name_zh": "测试游戏"},
            "target_rtp": {
                "value": 0.96,
                "confirmation_type": "confirmed_by_user",
                "confirmation_evidence_sha256": SHA,
            },
            "certified_script": {
                "path": str(self.script),
                "sha256": sha256(self.script),
                "entrypoint": "simulate",
                "status": "user_confirmed",
                "adapter_path": None,
                "adapter_sha256": None,
            },
            "runtime": {
                "source_path": "config-test:pragmatic/test/hash",
                "sealed_path": "work/baseline/runtime",
                "bundle_sha256": "1" * 64,
                "files": self.runtime_files,
            },
            "parameter_authority": {
                "status": "READY",
                "parameters": [{
                    "parameter_id": "base-weight",
                    "runtime_path": "reel_config.base.weight",
                    "authorization": "authorized",
                    "script_support": "supported",
                }],
                "locked_semantics": ["玩法、状态机、结算和RNG顺序"],
            },
            "sample_plan": {
                "confirmed_by_user": True,
                "sample_unit": "complete_paid_entry",
                "rng_protocol": "chunk_seeded",
                "calibration": {
                    "probe": 20000,
                    "screen": 100000,
                    "refine": 500000,
                    "final": 2000000,
                    "candidate_batch_size": 20,
                    "candidate_total_limit": None,
                    "continuation_rule": "continue_until_formal_pass_or_authorized_space_exhausted",
                    "formal_failure_action": "resume_search_with_new_candidate",
                    "early_stop_rules": ["完全支配时淘汰"],
                },
                "formal": {
                    "tiers": [10000000, 20000000, 50000000],
                    "selected_paid_entry_count": 10000000,
                    "minimum_conditional_sample": 2000,
                    "independent_seed": True,
                    "attempt_seed_rule": "pre_frozen_sequence_by_formal_attempt",
                    "same_candidate_retry": False,
                    "conditional_exposure_probabilities": {},
                },
            },
            "game_profile": {
                "metric_bindings": {
                    "components": [{
                        "component_id": "base",
                        "name_zh": "基础游戏",
                        "evidence_refs": ["rule:base"],
                        "display_bet_basis": "total-bet",
                        "variable_simultaneous_win_count": False,
                        "simultaneous_win_count_bins": [],
                        "variable_visible_step_reward": False,
                        "minimum_visible_reward_unit": None,
                    }],
                    "features": [],
                    "settlements": [],
                    "win_groups": [],
                    "continuous_settlements": [],
                    "special_mechanics": [],
                    "boards": [],
                    "sigma_scopes": [],
                },
                "column_repeat_policy": {"scopes": []},
                "evidence_refs": ["rule:test"],
            },
            "smoke_check": {"status": "passed", "seed": 1, "entry_count": 100, "evidence_sha256": SHA},
            "placeholders": [],
            "generated_at": datetime.now().astimezone().isoformat(),
        }

    def source_summary(self):
        exact = {
            "method": "user_confirmed_exact_rtp",
            "confirmation_type": "confirmed_by_user",
            "confirmation_evidence_sha256": SHA,
        }
        sealed = {"method": "sealed_original_evidence", "evidence_refs": ["source:one"]}
        mapped = {"method": "original_component_share_mapped_to_user_confirmed_total_rtp", "evidence_refs": ["source:one"]}
        return {
            "schema_version": "slot-alignment.source-summary.v7",
            "task_id": self.task_id,
            "status": "READY_FOR_CONTRACT",
            "frozen_before_candidate": True,
            "source_bundle_sha256": "2" * 64,
            "sources": [{"path": "capture-summary/source.json", "sha256": "3" * 64, "sample_count": 5000}],
            "sample_counts": {"complete_paid_entries": 5000},
            "targets": {
                "N1.total_rtp.overall": {"target_status": "available", "value": 0.96, "source": exact},
                "N2.positive_return_rate.overall": {"target_status": "available", "value": 0.25, "source": sealed, "sample_count": 5000},
                "N4.return_ge_cost_rate.overall": {"target_status": "available", "value": 0.20, "source": sealed, "sample_count": 5000},
                "N5.return_sigma.overall": {"target_status": "available", "value": 5.0, "source": sealed, "sample_count": 5000},
                "N6.component_rtp.base": {"target_status": "available", "value": 0.96, "source": mapped, "sample_count": 5000},
            },
            "generated_at": datetime.now().astimezone().isoformat(),
        }

    def board_preflight(self, normal="forbidden", scatter="forbidden", wild="forbidden"):
        value = self.preflight()
        value["game_profile"]["metric_bindings"]["boards"] = [{
            "board_scope_id": "base.initial",
            "name_zh": "基础游戏初始盘面",
            "component_id": "base",
            "visual_phase": "initial",
            "columns": 5,
            "symbols": ["low-1", "high-1", "scatter", "wild"],
            "symbol_groups": [
                {"group_id": "low", "name_zh": "低值符号", "symbols": ["low-1"]},
                {"group_id": "high", "name_zh": "高值符号", "symbols": ["high-1"]},
            ],
            "key_symbol_profiles": [
                {"symbol_id": "scatter", "sample_filter": "untriggered_only", "trigger_threshold": 3, "count_bins": ["0", "1"]},
                {"symbol_id": "wild", "sample_filter": "all", "trigger_threshold": None, "count_bins": ["0", "1"]},
            ],
            "aggregation_profile": None,
            "shape_mode": "fixed",
            "reel_height_profiles": [],
        }]
        value["game_profile"]["column_repeat_policy"]["scopes"] = [{
            "board_scope_id": "base.initial",
            "applicability": "applicable_non_cascade",
            "normal_symbols": {
                "same_symbol_repeat_in_column": normal,
                "confirmed_by": "user_confirmed",
                "evidence_refs": ["user:normal-repeat"],
            },
            "special_symbols": [
                {"symbol_id": "scatter", "same_symbol_repeat_in_column": scatter, "confirmed_by": "specification", "evidence_refs": ["spec:scatter-repeat"]},
                {"symbol_id": "wild", "same_symbol_repeat_in_column": wild, "confirmed_by": "user_confirmed", "evidence_refs": ["user:wild-repeat"]},
            ],
        }]
        return value

    def board_source_summary(self):
        value = self.source_summary()
        source = {"method": "sealed_original_evidence", "evidence_refs": ["source:board"]}
        def scalar(number, bucket_count=None):
            result = {"target_status": "available", "value": number, "source": source, "sample_count": 5000}
            if bucket_count is not None:
                result["bucket_count"] = bucket_count
            return result
        value["targets"].update({
            "B1.symbol_group_share_bin_rate.base.initial.low": scalar(0.4, 2000),
            "B1.symbol_group_share_bin_rate.base.initial.high": scalar(0.4, 2000),
            "B1.symbol_group_composition_shift.base.initial": scalar({"low": 0.4, "high": 0.4}),
            "B1.key_symbol_count_bin_rate.base.initial.scatter.0": scalar(0.8, 4000),
            "B1.key_symbol_count_bin_rate.base.initial.scatter.1": scalar(0.2, 1000),
            "B1.key_symbol_count_distribution_shift.base.initial.scatter": scalar({"0": 0.8, "1": 0.2}),
            "B1.key_symbol_count_bin_rate.base.initial.wild.0": scalar(0.9, 4500),
            "B1.key_symbol_count_bin_rate.base.initial.wild.1": scalar(0.1, 500),
            "B1.key_symbol_count_distribution_shift.base.initial.wild": scalar({"0": 0.9, "1": 0.1}),
        })
        return value

    def compile_board_contract(self, preflight=None):
        preflight_path = self.root / "board-preflight.json"
        source_path = self.root / "board-source.json"
        contract_path = self.root / "board-contract.json"
        write(preflight_path, preflight or self.board_preflight())
        write(source_path, self.board_source_summary())
        self.run_script("validate_preflight.py", "--preflight", preflight_path)
        self.run_script("validate_source_summary.py", "--summary", source_path, "--preflight", preflight_path)
        self.run_script("compile_metric_contract.py", "--preflight", preflight_path, "--source-summary", source_path, "--output", contract_path)
        return preflight_path, contract_path

    def compile_and_evaluate(self, artifacts=False):
        parent = self.root / "artifacts" if artifacts else self.root
        preflight_path = parent / "preflight.json"
        source_path = parent / "source_summary.json"
        contract_path = parent / "metric_contract.json"
        measurements_path = self.root / "work/formal_measurements.json"
        result_path = parent / ("formal_result.json" if artifacts else "result.json")
        write(preflight_path, self.preflight())
        write(source_path, self.source_summary())
        self.run_script("validate_preflight.py", "--preflight", preflight_path)
        self.run_script("validate_source_summary.py", "--summary", source_path, "--preflight", preflight_path)
        self.run_script("compile_metric_contract.py", "--preflight", preflight_path, "--source-summary", source_path, "--output", contract_path)
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        measurements = {
            "schema_version": "slot-alignment.metric-measurements.v7",
            "task_id": self.task_id,
            "phase": "FORMAL",
            "metric_contract_sha256": sha256(contract_path),
            "execution": {
                "candidate_id": "candidate-1",
                "runtime_bundle_sha256": "4" * 64,
                "certified_script_sha256": sha256(self.script),
                "adapter_sha256": None,
                "seed_plan_sha256": "5" * 64,
                "paid_entry_count": 10000000,
                "independent_seed": True,
            },
            "measurements": {},
            "audits": [],
        }
        for card in contract["cards"]:
            for instance in card["instances"]:
                measurements["measurements"][instance["instance_id"]] = {
                    "candidate": instance["target"],
                    "sample_evidence": {
                        "target_count": instance["target_evidence"]["sample_count"] or 0,
                        "candidate_count": 10000,
                        "required_target_count": instance["target_evidence"]["minimum_usable_count"],
                        "required_candidate_count": 1,
                        "gap_zh": None,
                    },
                }
        for audit in contract["audits"]:
            measurements["audits"].append({"audit_id": audit["audit_id"], "status": "符合", "details": {}})
        write(measurements_path, measurements)
        self.run_script("evaluate_alignment.py", "--contract", contract_path, "--measurements", measurements_path, "--phase", "FORMAL", "--output", result_path)
        return preflight_path, contract_path, result_path

    def test_compile_and_evaluate(self):
        _, _, result_path = self.compile_and_evaluate()
        result = json.loads(result_path.read_text(encoding="utf-8"))
        self.assertEqual(result["summary"]["final_status"], "通过")
        self.assertEqual(result["execution"]["candidate_id"], "candidate-1")

    def test_full_lightweight_delivery(self):
        preflight_path, contract_path, formal_path = self.compile_and_evaluate(artifacts=True)
        ledger_path = self.root / "work/candidate_ledger.jsonl"
        ledger_path.write_text(json.dumps({
            "candidate_id": "candidate-1",
            "parameter_sha256": "6" * 64,
            "runtime_bundle_sha256": "4" * 64,
            "certified_script_sha256": sha256(self.script),
            "metric_contract_sha256": sha256(contract_path),
            "status": "selected",
        }) + "\n", encoding="utf-8")

        selected_runtime = self.root / "work/selected/runtime"
        delivery_runtime = self.root / "交付物/runtime"
        selected_files = []
        delivery_files = []
        for item in self.runtime_files:
            value = json.loads((self.runtime / item["name"]).read_text(encoding="utf-8"))
            selected_path = selected_runtime / item["name"]
            delivery_path = delivery_runtime / item["name"]
            write(selected_path, value)
            write(delivery_path, value)
            digest = sha256(selected_path)
            selected_files.append({"name": item["name"], "sha256": digest})
            delivery_files.append({"name": item["name"], "source_sha256": digest, "delivery_sha256": sha256(delivery_path)})

        now = datetime.now().astimezone().isoformat()
        manifest_path = self.root / "artifacts/alignment_manifest.json"
        write(manifest_path, {
            "schema_version": "slot-alignment.alignment-manifest.v7",
            "task_id": self.task_id,
            "mode": "normal",
            "status": "COMPLETED",
            "metric_contract_sha256": sha256(contract_path),
            "certified_script_sha256": sha256(self.script),
            "adapter_sha256": None,
            "baseline_runtime_bundle_sha256": "1" * 64,
            "candidate_ledger": {"path": "work/candidate_ledger.jsonl", "sha256": sha256(ledger_path), "candidate_count": 1},
            "search": {
                "stages_used": ["SCREEN"],
                "authorized_parameter_ids": ["base-weight"],
                "attempted_parameter_ids": ["base-weight"],
                "ranking_rule": "failures_then_unknown_then_deviation_then_candidate_id",
                "termination_reason_zh": "唯一候选满足合同",
            },
            "selected_candidate": {
                "candidate_id": "candidate-1",
                "parameter_sha256": "6" * 64,
                "runtime_bundle_sha256": "4" * 64,
                "runtime_path": "work/selected/runtime",
                "runtime_files": selected_files,
            },
            "formal_plan": {
                "paid_entry_count": 10000000,
                "seed_plan_sha256": "5" * 64,
                "independent_seed": True,
                "uses_candidate_measurements": False,
            },
            "generated_at": now,
        })
        delivery_path = self.root / "artifacts/delivery_manifest.json"
        write(delivery_path, {
            "schema_version": "slot-alignment.delivery-manifest.v7",
            "report_contract_version": "slot-alignment.report.v7",
            "task_id": self.task_id,
            "runtime_version": self.task_id,
            "rtp_group": 1,
            "metric_contract_sha256": sha256(contract_path),
            "alignment_manifest_sha256": sha256(manifest_path),
            "formal_result_sha256": sha256(formal_path),
            "certified_script_sha256": sha256(self.script),
            "source_runtime_bundle_sha256": "4" * 64,
            "delivery_runtime_bundle_sha256": "4" * 64,
            "runtime_files": delivery_files,
            "checks": {
                "same_certified_script": True,
                "same_metric_contract": True,
                "formal_independent_seed": True,
                "runtime_files_match": True,
                "runtime_version_matches_task_id": True,
                "rtp_group_is_one": True,
            },
            "generated_at": now,
        })
        report_path = self.root / "交付物/报告文档/对齐报告.md"
        self.run_script(
            "render_alignment_report.py",
            "--preflight", preflight_path,
            "--contract", contract_path,
            "--result", formal_path,
            "--output", report_path,
            "--task-root", self.root,
        )
        self.run_script("validate_workspace_layout.py", "--task-root", self.root, "--through-stage", 4)
        self.run_script("validate_delivery.py", "--task-root", self.root)
        self.assertIn("完整范围通过", report_path.read_text(encoding="utf-8"))

    def test_candidate_ledger_rejects_non_certified_script(self):
        ledger_path = self.root / "work/candidate_ledger.jsonl"
        ledger_path.write_text(json.dumps({
            "candidate_id": "candidate-1",
            "parameter_sha256": "6" * 64,
            "runtime_bundle_sha256": "4" * 64,
            "certified_script_sha256": "9" * 64,
            "metric_contract_sha256": "8" * 64,
        }) + "\n", encoding="utf-8")
        manifest = {
            "candidate_ledger": {"candidate_count": 1},
            "selected_candidate": {
                "candidate_id": "candidate-1",
                "parameter_sha256": "6" * 64,
                "runtime_bundle_sha256": "4" * 64,
            },
        }
        errors = []
        validate_candidate_ledger(ledger_path, manifest, sha256(self.script), "8" * 64, errors)
        self.assertTrue(any("未使用用户认证脚本" in item for item in errors))

    def test_fixed_candidate_total_limit_is_rejected(self):
        preflight = self.preflight()
        preflight["sample_plan"]["calibration"]["candidate_total_limit"] = 100
        path = self.root / "fixed-limit-preflight.json"
        write(path, preflight)
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "validate_preflight.py"), "--preflight", str(path)],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("candidate_total_limit", result.stderr)

    def test_column_repeat_forbidden_becomes_zero_budget_b1_gate(self):
        preflight_path, contract_path = self.compile_board_contract()
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        instances = [
            item for card in contract["cards"] for item in card["instances"]
            if item["facet_id"] == "column_repeat_violation_rate"
        ]
        self.assertEqual([item["subitem_id"] for item in instances], [
            "base.initial.normal-symbols", "base.initial.special.scatter", "base.initial.special.wild",
        ])
        self.assertTrue(all(item["target"] == 0 and item["c_budget"]["value"] == 0 for item in instances))
        self.assertTrue(all(item["scope"]["cell_scope"] == "generated_this_action" for item in instances))
        self.assertTrue(all(item["scope"]["carried_cell_handling"] == "excluded" for item in instances))
        self.assertTrue(all(item["scope"]["minimum_comparable_cells"] == 2 for item in instances))
        measurements = {
            "schema_version": "slot-alignment.metric-measurements.v7",
            "task_id": self.task_id,
            "phase": "FORMAL",
            "metric_contract_sha256": sha256(contract_path),
            "execution": {
                "candidate_id": "candidate-repeat-test", "runtime_bundle_sha256": "4" * 64,
                "certified_script_sha256": sha256(self.script), "adapter_sha256": None,
                "seed_plan_sha256": "5" * 64, "paid_entry_count": 10000000, "independent_seed": True,
            },
            "measurements": {},
            "audits": [],
        }
        for card in contract["cards"]:
            for instance in card["instances"]:
                measurements["measurements"][instance["instance_id"]] = {
                    "candidate": instance["target"],
                    "sample_evidence": {"target_count": 5000, "candidate_count": 10000, "required_target_count": None, "required_candidate_count": 1, "gap_zh": None},
                }
        for audit in contract["audits"]:
            measurements["audits"].append({"audit_id": audit["audit_id"], "status": "符合", "details": {}})
        measurement_path = self.root / "repeat-measurements.json"
        result_path = self.root / "repeat-result.json"
        write(measurement_path, measurements)
        self.run_script("evaluate_alignment.py", "--contract", contract_path, "--measurements", measurement_path, "--phase", "FORMAL", "--output", result_path)
        self.assertEqual(json.loads(result_path.read_text(encoding="utf-8"))["summary"]["final_status"], "通过")
        measurements["measurements"]["B1.column_repeat_violation_rate.base.initial.special.scatter"]["candidate"] = 0.001
        write(measurement_path, measurements)
        self.run_script("evaluate_alignment.py", "--contract", contract_path, "--measurements", measurement_path, "--phase", "FORMAL", "--output", result_path)
        self.assertEqual(json.loads(result_path.read_text(encoding="utf-8"))["summary"]["final_status"], "不通过")
        report_path = self.root / "repeat-report.md"
        self.run_script("render_alignment_report.py", "--preflight", preflight_path, "--contract", contract_path, "--result", result_path, "--output", report_path)
        report = report_path.read_text(encoding="utf-8")
        self.assertIn("本次新落符号同列重复违规率", report)
        self.assertIn("Scatter符号", report)
        self.assertIn("Wild符号", report)
        self.assertIn("本次新产生（历史保留除外）", report)

    def test_column_repeat_confirmation_must_cover_every_special_symbol(self):
        preflight = self.board_preflight()
        preflight["game_profile"]["column_repeat_policy"]["scopes"][0]["special_symbols"].pop()
        path = self.root / "missing-special-confirmation.json"
        write(path, preflight)
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "validate_preflight.py"), "--preflight", str(path)],
            check=False, capture_output=True, text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("必须逐个确认全部特殊符号", result.stderr)

    def test_allowed_column_repeat_adds_no_gate(self):
        _, contract_path = self.compile_board_contract(self.board_preflight(normal="allowed", scatter="allowed", wild="allowed"))
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        self.assertFalse(any(
            item["facet_id"] == "column_repeat_violation_rate"
            for card in contract["cards"] for item in card["instances"]
        ))

    def test_policy_and_library_validation(self):
        self.run_script("validate_metric_library.py")


if __name__ == "__main__":
    unittest.main()
