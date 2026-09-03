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
                    "maximum_candidates": 20,
                    "early_stop_rules": ["完全支配时淘汰"],
                },
                "formal": {
                    "tiers": [10000000, 20000000, 50000000],
                    "selected_paid_entry_count": 10000000,
                    "minimum_conditional_sample": 2000,
                    "independent_seed": True,
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

    def test_policy_and_library_validation(self):
        self.run_script("validate_metric_library.py")


if __name__ == "__main__":
    unittest.main()
