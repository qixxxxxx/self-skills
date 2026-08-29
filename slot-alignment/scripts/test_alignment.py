#!/usr/bin/env python3
import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from alignment import (
    absolute_probability_error,
    joint_q99_tolerances,
    sha256_file,
    structural_wasserstein,
    total_variation,
    wasserstein_1d,
)
from compile_metric_contract import LIBRARY_PATH, subitems


ROOT = Path(__file__).resolve().parents[1]


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


class DistanceTests(unittest.TestCase):
    def test_probability_and_total_variation(self):
        self.assertAlmostEqual(absolute_probability_error(0.2, 0.25), 0.05)
        self.assertAlmostEqual(total_variation({"a": 0.7, "b": 0.3}, {"a": 0.4, "b": 0.6}), 0.3)

    def test_wasserstein_uses_real_positions(self):
        self.assertAlmostEqual(wasserstein_1d([1, 0, 0], [0, 1, 0], [0, 1, 3], support_span=3), 1 / 3)
        self.assertGreater(wasserstein_1d([1, 0], [0, 1], [0, 99], "log10_1p"), 1.9)

    def test_structural_wasserstein(self):
        target = {"board_shape": [2, 2], "states": [{"cells": [[0, 0]], "probability": 1.0}]}
        same = copy.deepcopy(target)
        shifted = {"board_shape": [2, 2], "states": [{"cells": [[1, 1]], "probability": 1.0}]}
        self.assertEqual(structural_wasserstein(target, same, "symbol_position_density"), 0.0)
        self.assertEqual(structural_wasserstein(target, shifted, "symbol_position_density"), 1.0)
        shape = {"board_shape": [2, 2], "states": [{"cells": [[0, 0], [1, 0]], "probability": 1.0}]}
        self.assertEqual(structural_wasserstein(shape, copy.deepcopy(shape), "board_shape"), 0.0)

    def test_joint_q99_is_not_below_individual_q99(self):
        values = {"a": [0.01] * 99 + [0.02], "b": [0.02] * 99 + [0.03]}
        tolerances, factor = joint_q99_tolerances(values)
        self.assertGreaterEqual(factor, 1.0)
        self.assertGreaterEqual(tolerances["a"], 0.01)
        self.assertGreaterEqual(tolerances["b"], 0.02)


class EndToEndTests(unittest.TestCase):
    def setUp(self):
        self.temp = Path(tempfile.mkdtemp(prefix="slot-alignment-v5-"))
        self.created = []

    def tearDown(self):
        for path in reversed(self.created):
            if path.is_file():
                path.unlink()
        self.temp.rmdir()

    def path(self, name):
        path = self.temp / name
        self.created.append(path)
        return path

    def run_script(self, name, *args):
        subprocess.run([sys.executable, str(ROOT / "scripts" / name), *map(str, args)], check=True, cwd=ROOT, capture_output=True, text=True)

    def profile(self):
        return {
            "schema_version": "slot-alignment.game-profile.v5",
            "metric_bindings": {
                "features": [{"feature_id": "free-spin", "feature_type": "free_spin", "endogenous_entry": True}],
                "settlements": [{
                    "settlement_id": "main-ways",
                    "settlement_type": "ways",
                    "elements": ["a", "wild"],
                    "paylines": [],
                    "size_axes": ["reels", "ways"],
                    "payout_mapping": "variable",
                }],
                "continuous_settlements": [{"continuous_id": "cascade", "reachable_depths": [1, 2], "size_axes": ["reels"]}],
                "special_mechanics": [{"mechanic_id": "wild-multiplier", "result_states": ["not-occurred", "not-effective", "2x", "3x"], "inactive_state_ids": ["not-occurred", "not-effective"]}],
                "boards": [{
                    "board_scope_id": "base",
                    "rows": 2,
                    "columns": 2,
                    "variable_shape": True,
                    "symbols": ["a", "wild"],
                    "spatial_symbols": ["wild"],
                }],
                "components": ["base", "free-spin"],
                "sigma_scopes": ["free-spin"],
            },
        }

    def target_for(self, card, facet, extra):
        method = facet["distance_method"]
        if card["card_id"] == "N1":
            source = {"method": "user_confirmed_exact_rtp", "confirmation_type": "confirmed_by_user", "confirmation_evidence_sha256": "1" * 64}
        elif card["card_id"] == "N6":
            source = {"method": "original_component_share_mapped_to_user_confirmed_total_rtp"}
        else:
            source = {"method": "sealed_original_evidence"}
        if method == "range_error":
            return {"value": {"min": 0.95, "max": 0.97}, "source": source, "base_tolerance": 0.001}
        if method == "relative_error":
            return {"value": 2.0, "source": source, "base_tolerance": 0.05}
        if method == "absolute_probability_error":
            return {"value": 0.96 if card["card_id"] == "N1" else 0.2, "source": source, "base_tolerance": 0.01}
        if method == "total_variation":
            return {"value": {"not-occurred": 0.5, "not-effective": 0.2, "2x": 0.2, "3x": 0.1}, "source": source}
        if method == "wasserstein_1d":
            transform = facet.get("position_transform", "identity")
            return {"value": {"0": 0.6, "1": 0.4}, "source": source, "distance": {"bin_positions": [0, 1], "position_transform": transform, **({"support_span": 1.0} if transform == "identity" else {})}}
        state_kind = extra.get("state_kind", "symbol_position_density")
        cells = [[0, 0]] if state_kind == "symbol_position_density" else [[0, 0], [0, 1], [1, 0], [1, 1]]
        return {"value": {"board_shape": extra["board_shape"], "states": [{"cells": cells, "probability": 1.0}]}, "source": source}

    def build_inputs(self):
        profile = self.profile()
        library = load(LIBRARY_PATH)
        targets, tolerances = {}, {}
        bindings = profile["metric_bindings"]
        for card in library["cards"]:
            for facet in card["facets"]:
                for subitem, _scope, extra in subitems(card["card_id"], facet["facet_id"], bindings):
                    instance_id = f"{card['card_id']}.{facet['facet_id']}.{subitem}"
                    record = self.target_for(card, facet, extra)
                    if card["kind"] == "hard_gate" and "base_tolerance" not in record:
                        record["base_tolerance"] = 0.01
                    targets[instance_id] = record
                    if card["kind"] == "alignment":
                        tolerances[instance_id] = 0.1
        profile_path, targets_path, joint_path, bindings_path = [self.path(name) for name in ["profile.json", "targets.json", "joint.json", "bindings.json"]]
        write(profile_path, profile)
        write(targets_path, {"targets": targets})
        write(joint_path, {"schema_version": "slot-alignment.joint-self-comparison.v5", "quantile": 0.99, "joint": True, "replicates": 100, "seed": 7, "evidence_sha256": "a" * 64, "joint_factor": 1.0, "tolerances": tolerances})
        write(bindings_path, {
            "contract_version": "test-v5",
            "task_id": "test-task",
            "mode": "normal",
            "runtime_bundle_sha256": "b" * 64,
            "original_evidence_sha256": "c" * 64,
            "script_sha256": "d" * 64,
            "game_profile_sha256": "e" * 64,
            "parameter_authority_sha256": "f" * 64,
        })
        return profile_path, targets_path, joint_path, bindings_path

    def test_compile_evaluate_and_schema(self):
        profile, targets, joint, bindings = self.build_inputs()
        contract_path = self.path("contract.json")
        self.run_script("compile_metric_contract.py", "--profile", profile, "--targets", targets, "--joint-tolerances", joint, "--bindings", bindings, "--output", contract_path)
        contract = load(contract_path)
        n1 = next(item for card in contract["cards"] if card["card_id"] == "N1" for item in card["instances"])
        self.assertEqual(n1["target"], 0.96)
        self.assertEqual(n1["target_source"]["method"], "user_confirmed_exact_rtp")
        self.assertEqual(n1["distance"]["method"], "absolute_probability_error")
        b2_ids = [item["instance_id"] for card in contract["cards"] if card["card_id"] == "B2" for item in card["instances"]]
        self.assertEqual(b2_ids, ["B2.board_shape.base", "B2.key_symbol_position_density.base.wild"])
        self.assertFalse(any("count-" in item for item in b2_ids))
        contract_schema = load(ROOT / "assets/schemas/metric-contract.schema.json")
        Draft202012Validator(contract_schema).validate(contract)
        measurements = {}
        for card in contract["cards"]:
            for instance in card["instances"]:
                target = instance["target"]
                candidate = (target["min"] + target["max"]) / 2 if instance["distance"]["method"] == "range_error" else target
                measurements[instance["instance_id"]] = {"candidate": candidate, "sample_evidence": {"target_count": 1000, "candidate_count": 1000}}
        measurements_path, result_path = self.path("measurements.json"), self.path("result.json")
        write(measurements_path, {"measurements": measurements, "audits": []})
        self.run_script("evaluate_alignment.py", "--contract", contract_path, "--measurements", measurements_path, "--phase", "FORMAL", "--output", result_path)
        result = load(result_path)
        Draft202012Validator(load(ROOT / "assets/schemas/alignment-result.schema.json")).validate(result)
        if result["summary"]["final_status"] != "通过":
            bad = [(item["instance_id"], item["status"], item.get("reason_zh")) for card in result["card_results"] for item in card["instances"] if item["status"] != "通过"]
            self.fail(f"等值候选未通过: {bad}")
        gate_path, report_path = self.path("stage3_gate.json"), self.path("report.md")
        self.run_script("generate_stage3_gate.py", "--result", result_path, "--output", gate_path)
        self.run_script("validate_artifacts.py", "--contract", contract_path, "--result", result_path, "--stage3-gate", gate_path)
        self.run_script("render_alignment_report.py", "--contract", contract_path, "--result", result_path, "--output", report_path)
        self.assertIn("最终状态：**通过**", report_path.read_text(encoding="utf-8"))
        first_alignment = next(instance for card in contract["cards"] if card["kind"] == "alignment" for instance in card["instances"])
        failing = copy.deepcopy(measurements)
        failing[first_alignment["instance_id"]]["candidate"] = 1.0 if isinstance(first_alignment["target"], (int, float)) else failing[first_alignment["instance_id"]]["candidate"]
        if first_alignment["distance"]["method"] == "absolute_probability_error":
            failing[first_alignment["instance_id"]]["candidate"] = 1.0
        else:
            failing[first_alignment["instance_id"]]["status"] = "样本不足"
        write(measurements_path, {"measurements": failing, "audits": []})
        self.run_script("evaluate_alignment.py", "--contract", contract_path, "--measurements", measurements_path, "--phase", "FORMAL", "--output", result_path)
        self.assertIn(load(result_path)["summary"]["final_status"], {"不通过", "无法完整判定"})
        insufficient = copy.deepcopy(measurements)
        insufficient[first_alignment["instance_id"]] = {"status": "样本不足", "reason_zh": "测试", "sample_evidence": {"target_count": 0, "candidate_count": 1000}}
        write(measurements_path, {"measurements": insufficient, "audits": []})
        self.run_script("evaluate_alignment.py", "--contract", contract_path, "--measurements", measurements_path, "--phase", "FORMAL", "--output", result_path)
        self.assertEqual(load(result_path)["summary"]["final_status"], "无法完整判定")

    def test_n1_rejects_missing_confirmation_and_interval(self):
        profile, targets, joint, bindings = self.build_inputs()
        data = load(targets)
        n1 = data["targets"]["N1.total_rtp.overall"]
        n1["source"].pop("confirmation_evidence_sha256")
        write(targets, data)
        command = [sys.executable, str(ROOT / "scripts/compile_metric_contract.py"), "--profile", str(profile), "--targets", str(targets), "--joint-tolerances", str(joint), "--bindings", str(bindings), "--output", str(self.path("invalid-contract-1.json"))]
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("用户确认记录SHA-256", result.stderr)

        n1["source"]["confirmation_evidence_sha256"] = "1" * 64
        n1["value"] = {"min": 0.95, "max": 0.96}
        write(targets, data)
        command[-1] = str(self.path("invalid-contract-2.json"))
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("唯一数值", result.stderr)

    def test_delivery_runtime_version_must_equal_task_id(self):
        formal_path = self.path("formal-delivery.json")
        write(formal_path, {"task_id": "test-task"})
        runtime_paths = {}
        for name in ["game_core.json", "payout_config.json", "reel_config.json", "symbol_catalog.json"]:
            path = self.path(name)
            write(path, {"meta": {"version": "test-task"}} if name == "game_core.json" else {})
            runtime_paths[name] = path
        manifest_path = self.path("delivery-manifest.json")
        manifest = {
            "schema_version": "slot-alignment.delivery-manifest.v5",
            "report_contract_version": "slot-alignment.report.v5",
            "task_id": "test-task",
            "runtime_version": "test-task",
            "rtp_group": 1,
            "formal_result_sha256": sha256_file(formal_path),
            "runtime_files": [
                {"name": name, "path": f"交付物/runtime/{name}", "sha256": sha256_file(runtime_paths[name])}
                for name in ["game_core.json", "payout_config.json", "reel_config.json", "symbol_catalog.json"]
            ],
            "generated_at": "2026-08-29T00:00:00+08:00",
        }
        write(manifest_path, manifest)
        self.run_script("validate_delivery.py", "--formal-result", formal_path, "--runtime-dir", self.temp, "--manifest", manifest_path)

        write(runtime_paths["game_core.json"], {"meta": {"version": "wrong-version"}})
        command = [sys.executable, str(ROOT / "scripts/validate_delivery.py"), "--formal-result", str(formal_path), "--runtime-dir", str(self.temp), "--manifest", str(manifest_path)]
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("game_core.json.meta.version必须等于task_id", result.stderr)

        write(runtime_paths["game_core.json"], {"meta": {"version": "test-task"}})
        manifest["runtime_files"][0]["sha256"] = sha256_file(runtime_paths["game_core.json"])
        manifest["runtime_version"] = "wrong-version"
        write(manifest_path, manifest)
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("delivery_manifest.runtime_version必须等于task_id", result.stderr)


if __name__ == "__main__":
    unittest.main()
