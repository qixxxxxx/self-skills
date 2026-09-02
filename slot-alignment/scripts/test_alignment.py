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
    _hierarchical_card_score,
    absolute_probability_error,
    evaluate_contract,
    grade_score,
    half_l1,
    sha256_file,
    total_variation,
)
from compile_metric_contract import EVALUATION_POLICY_PATH, HARD_POLICY_PATH, LIBRARY_PATH, b_c_tolerance, j_c_tolerance, n_c_tolerance, p_c_tolerance, safe_id, subitems
from validate_sample_plan import POLICY_PATH as SAMPLE_POLICY_PATH, derived_formal, validate_plan


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_CAPABILITY_POLICY_PATH = ROOT / "assets/policies/runtime_capability_policy.json"


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


class DistanceTests(unittest.TestCase):
    def test_probability_and_total_variation(self):
        self.assertAlmostEqual(absolute_probability_error(0.2, 0.25), 0.05)
        self.assertAlmostEqual(total_variation({"a": 0.7, "b": 0.3}, {"a": 0.4, "b": 0.6}), 0.3)
        self.assertAlmostEqual(half_l1({"high": 0.5, "low": 0.4}, {"high": 0.45, "low": 0.35}), 0.05)

    def test_formal_grade_boundaries(self):
        policy = load(ROOT / "assets/policies/alignment_evaluation_policy.json")
        grading = policy["formal_grading"]
        self.assertEqual(grading["hard_gate_pass_limit"], 1.0)
        for score, grade in [(100, "S"), (90, "S"), (89.999, "A"), (80, "A"), (79.999, "B"), (70, "B"), (69.999, "C"), (0, "C")]:
            self.assertEqual(grade_score(score, policy), grade)
        self.assertNotIn("alignment_thresholds", grading)

    def test_n_c_tolerance_rules(self):
        policy = load(HARD_POLICY_PATH)
        bindings = {"features": [{"feature_id": "free-spin"}]}
        self.assertEqual(n_c_tolerance("N1", 0.96, {"scope": "overall"}, bindings, policy), 0.003)
        self.assertAlmostEqual(n_c_tolerance("N2", 0.2, {"scope": "overall"}, bindings, policy), 0.012)
        self.assertAlmostEqual(n_c_tolerance("N3", 0.001, {"feature": "free-spin"}, bindings, policy), 0.00012)
        self.assertAlmostEqual(n_c_tolerance("N3", 0.0001, {"feature": "free-spin"}, bindings, policy), 0.00002)
        self.assertEqual(n_c_tolerance("N4", 0.2, {"scope": "overall"}, bindings, policy), 0.015)
        self.assertEqual(n_c_tolerance("N5", 10, {"scope": "overall"}, bindings, policy), 0.08)
        self.assertEqual(n_c_tolerance("N5", 10, {"scope": "base"}, bindings, policy), 0.08)
        self.assertEqual(n_c_tolerance("N5", 10, {"scope": "free-spin"}, bindings, policy), 0.12)
        self.assertEqual(n_c_tolerance("N6", 0.2, {"component": "base"}, bindings, policy), 0.015)

    def test_n_category_uses_equal_card_weight(self):
        policy = load(ROOT / "assets/policies/alignment_evaluation_policy.json")
        def instance(instance_id):
            return {
                "instance_id": instance_id,
                "facet_id": "value",
                "subitem_id": instance_id.rsplit(".", 1)[-1],
                "target": 0.5,
                "distance": {"method": "absolute_probability_error"},
                "tolerance": {"effective": 0.1},
                "status": "active",
            }
        contract = {
            "task_id": "equal-card-weight",
            "cards": [
                {"card_id": "N1", "name_zh": "N1", "category_id": "N", "kind": "hard_gate", "instances": [instance("N1.value.one")]},
                {"card_id": "N5", "name_zh": "N5", "category_id": "N", "kind": "hard_gate", "instances": [instance("N5.value.one"), instance("N5.value.two")]},
            ],
            "audits": [],
        }
        measurements = {"measurements": {
            "N1.value.one": {"candidate": 0.5},
            "N5.value.one": {"candidate": 0.52},
            "N5.value.two": {"candidate": 0.52},
        }}
        result = evaluate_contract(contract, measurements, "FORMAL", "a" * 64, policy)
        self.assertAlmostEqual(result["card_results"][0]["score"], 100.0)
        self.assertAlmostEqual(result["card_results"][1]["score"], 80.0)
        self.assertAlmostEqual(result["summary"]["composite_score"], 90.0)
        self.assertEqual(result["summary"]["final_grade"], "S")

    def test_j_c_tolerance_rules(self):
        policy = load(EVALUATION_POLICY_PATH)
        bindings = {"features": [{"feature_id": "free-spin"}]}
        base, feature = {"component": "base"}, {"component": "free-spin"}
        self.assertAlmostEqual(j_c_tolerance(0.0017, base, {"budget_rule": "J1.participation"}, bindings, policy), 0.0017)
        self.assertAlmostEqual(j_c_tolerance(0.3, base, {"budget_rule": "J1.participation"}, bindings, policy), 0.025)
        self.assertAlmostEqual(j_c_tolerance(0.3, feature, {"budget_rule": "J1.participation"}, bindings, policy), 0.03)
        self.assertAlmostEqual(j_c_tolerance(0.01, base, {"budget_rule": "J2.primary_structure_categorical.bin"}, bindings, policy), 0.005)
        self.assertAlmostEqual(j_c_tolerance(0.01, feature, {"budget_rule": "J2.primary_structure_categorical.bin"}, bindings, policy), 0.01)
        self.assertAlmostEqual(j_c_tolerance(0.5, {**base, "natural_unit": 1}, {"budget_rule": "J2.primary_structure_summary.mean"}, bindings, policy), 1.0)
        self.assertAlmostEqual(j_c_tolerance(0.01, base, {"budget_rule": "J2.simultaneous_win_count.bin"}, bindings, policy), 0.002)
        self.assertAlmostEqual(j_c_tolerance(2.0, {**feature, "minimum_visible_reward_unit": 0.01}, {"budget_rule": "J2.visible_step_reward.p90"}, bindings, policy), 0.3)
        self.assertAlmostEqual(j_c_tolerance(0.01, base, {"budget_rule": "J3.depth.bin"}, bindings, policy), 0.002)
        self.assertAlmostEqual(j_c_tolerance({}, feature, {"budget_rule": "J3.depth.overall"}, bindings, policy), 0.04)

    def test_j_card_hierarchical_scoring(self):
        half_group = [
            {"aggregation": {"dimension_id": "depth", "group_id": "base", "mode": "half_overall_half_items", "role": "overall"}},
            {"aggregation": {"dimension_id": "depth", "group_id": "base", "mode": "half_overall_half_items", "role": "bin"}},
            {"aggregation": {"dimension_id": "depth", "group_id": "base", "mode": "half_overall_half_items", "role": "bin"}},
        ]
        self.assertAlmostEqual(_hierarchical_card_score({"instances": half_group}, [{"score": 60}, {"score": 100}, {"score": 80}]), 75.0)
        dimensions = [
            {"aggregation": {"dimension_id": "primary_structure", "group_id": "ways", "mode": "mean_items", "role": "item"}},
            {"aggregation": {"dimension_id": "simultaneous_win_count", "group_id": "base", "mode": "mean_items", "role": "item"}},
            {"aggregation": {"dimension_id": "visible_step_reward", "group_id": "base", "mode": "mean_items", "role": "item"}},
        ]
        self.assertAlmostEqual(_hierarchical_card_score({"instances": dimensions}, [{"score": 80}, {"score": 60}, {"score": 100}]), 80.0)
        b1_dimensions = [
            {"aggregation": {"dimension_id": "b1-1", "group_id": "group-composition", "mode": "mean_items", "role": "item"}},
            {"aggregation": {"dimension_id": "b1-1", "group_id": "member-balance", "mode": "mean_items", "role": "item"}},
            {"aggregation": {"dimension_id": "b1-2", "group_id": "key-count", "mode": "mean_items", "role": "item"}},
            {"aggregation": {"dimension_id": "b1-3", "group_id": "aggregation", "mode": "mean_items", "role": "item"}},
        ]
        self.assertAlmostEqual(_hierarchical_card_score({"instances": b1_dimensions}, [{"score": 60}, {"score": 100}, {"score": 40}, {"score": 100}]), (80 + 40 + 100) / 3)

    def test_p_c_tolerance_rules(self):
        policy = load(EVALUATION_POLICY_PATH)
        self.assertAlmostEqual(p_c_tolerance(0.003, {"budget_rule": "P1.entry_award.bin"}, policy), 0.003)
        self.assertAlmostEqual(p_c_tolerance(0.1, {"budget_rule": "P1.entry_award.bin"}, policy), 0.02)
        self.assertAlmostEqual(p_c_tolerance({}, {"budget_rule": "P1.entry_award.overall"}, policy), 0.04)
        self.assertAlmostEqual(p_c_tolerance(10, {"budget_rule": "P1.duration.mean"}, policy), 1.2)
        self.assertAlmostEqual(p_c_tolerance(3, {"budget_rule": "P1.duration.p50"}, policy), 1.0)
        self.assertAlmostEqual(p_c_tolerance(5, {"budget_rule": "P1.duration.p90"}, policy), 2.0)
        self.assertAlmostEqual(p_c_tolerance(0.1, {"budget_rule": "P2.result.bin"}, policy), 0.015)
        self.assertAlmostEqual(p_c_tolerance({}, {"budget_rule": "P2.result.overall"}, policy), 0.04)

    def test_b_c_tolerance_rules(self):
        policy = load(EVALUATION_POLICY_PATH)
        self.assertAlmostEqual(b_c_tolerance(0.2, {"budget_rule": "B1.symbol_group_composition.bin"}, policy), 0.03)
        self.assertAlmostEqual(b_c_tolerance({}, {"budget_rule": "B1.symbol_group_composition.overall"}, policy), 0.05)
        self.assertAlmostEqual(b_c_tolerance(0.1, {"budget_rule": "B1.key_symbol_count.bin"}, policy), 0.012)
        self.assertAlmostEqual(b_c_tolerance(10, {"budget_rule": "B2.active_cell_count.mean"}, policy), 1.0)
        self.assertAlmostEqual(b_c_tolerance(5, {"budget_rule": "B2.unevenness.p90"}, policy), 1.0)


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
        result = subprocess.run([sys.executable, str(ROOT / "scripts" / name), *map(str, args)], cwd=ROOT, capture_output=True, text=True)
        if result.returncode:
            self.fail(result.stderr or result.stdout)

    def profile(self):
        return {
            "schema_version": "slot-alignment.game-profile.v5",
            "metric_bindings": {
                "features": [{
                    "feature_id": "free-spin",
                    "feature_type": "free_spin",
                    "endogenous_entry": True,
                    "entry_award_evaluation_mode": "categorical_distribution",
                    "entry_award_unit": "free-spin-count",
                    "entry_award_bins": ["8", "12", "20"],
                    "duration_evaluation_mode": "summary_triplet",
                    "duration_unit": "spin",
                }],
                "settlements": [{
                    "settlement_id": "main-ways",
                    "component_id": "base",
                    "settlement_type": "ways",
                    "elements": ["a", "wild"],
                    "primary_size_axis": "ways",
                    "variable_primary_size": True,
                    "primary_size_evaluation_mode": "summary_triplet",
                    "primary_size_unit": 1,
                }],
                "win_groups": [
                    {"component_id": "base", "group_id": "regular", "role": "regular_other", "elements": ["a"]},
                    {"component_id": "base", "group_id": "special", "role": "special", "elements": ["wild"]},
                ],
                "continuous_settlements": [{"continuous_id": "cascade", "component_id": "base", "variable_depth": True}],
                "special_mechanics": [{
                    "mechanic_id": "wild-multiplier",
                    "mechanic_family": "multiplier_modifier",
                    "opportunity_unit": "feature_spin",
                    "result_evaluation_mode": "categorical_distribution",
                    "guaranteed_resolution": False,
                    "result_states": ["not-occurred", "not-effective", "2x", "3x"],
                    "inactive_state_ids": ["not-occurred", "not-effective"],
                }],
                "boards": [{
                    "board_scope_id": "base-initial",
                    "component_id": "base",
                    "visual_phase": "initial",
                    "rows": 3,
                    "columns": 2,
                    "shape_mode": "variable_reel_height",
                    "symbols": ["a", "b", "c", "wild"],
                    "symbol_groups": [
                        {"group_id": "regular-high", "role": "regular_high", "symbols": ["a", "b"]},
                        {"group_id": "regular-low", "role": "regular_low", "symbols": ["c"]},
                    ],
                    "key_symbol_profiles": [{"symbol_id": "wild", "count_bins": ["0", "1"], "sample_filter": "all_stable_boards"}],
                    "aggregation_profile": {"aggregation_type": "vertical_run", "symbol_ids": ["a", "b", "c"], "bins": ["none", "single", "two-plus"], "sample_filter": "all_stable_boards"},
                    "reel_height_profiles": [
                        {"reel_id": "r1", "bins": ["2", "3"]},
                        {"reel_id": "r2", "bins": ["2", "3"]},
                    ],
                }],
                "components": [
                    {"component_id": "base", "display_bet_basis": "total-bet", "variable_simultaneous_win_count": True, "simultaneous_win_count_bins": ["1", "2", "3", "4+"], "variable_visible_step_reward": True, "minimum_visible_reward_unit": 0.01},
                    {"component_id": "free-spin", "display_bet_basis": "total-bet", "variable_simultaneous_win_count": False, "variable_visible_step_reward": False},
                ],
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
            record = {"value": {"min": 0.95, "max": 0.97}, "source": source, "base_tolerance": 0.001}
        elif method == "relative_error":
            record = {"value": 2.0, "source": source, "base_tolerance": 0.05}
        elif method == "absolute_probability_error":
            value = 0.96 if card["card_id"] == "N1" else 0.2
            scope = extra.get("scope", {})
            if card["card_id"] == "P1" and "bin" in scope:
                value = {"8": 0.7, "12": 0.2, "20": 0.1}[scope["bin"]]
            elif card["card_id"] == "P2" and "state" in scope:
                value = {"not-occurred": 0.5, "not-effective": 0.2, "2x": 0.2, "3x": 0.1}[scope["state"]]
            elif card["card_id"] == "B1" and "symbol_group" in scope and "symbol" not in scope:
                value = {"regular-high": 0.6, "regular-low": 0.3}[scope["symbol_group"]]
            elif card["card_id"] == "B1" and "symbol" in scope and "symbol_group" in scope:
                value = 0.5
            elif card["card_id"] == "B1" and "symbol" in scope and "bin" in scope:
                value = {"0": 0.8, "1": 0.2}[scope["bin"]]
            elif card["card_id"] == "B1" and "aggregation_type" in scope:
                value = {"none": 0.2, "single": 0.5, "two-plus": 0.3}[scope["bin"]]
            elif card["card_id"] == "B2" and "reel" in scope:
                value = {"2": 0.4, "3": 0.6}[scope["bin"]]
            record = {"value": value, "source": source, "base_tolerance": 0.01}
        elif method == "absolute_error":
            scope = extra.get("scope", {})
            if card["card_id"] == "B2" and "statistic" in scope:
                if facet["facet_id"].startswith("active_cell_count"):
                    value = {"mean": 5.0, "p50": 5.0, "p90": 6.0}[scope["statistic"]]
                else:
                    value = {"mean": 0.8, "p90": 1.0}[scope["statistic"]]
            else:
                value = 2.0
            record = {"value": value, "source": source}
        elif method == "half_l1":
            record = {"value": {"regular-high": 0.6, "regular-low": 0.3}, "source": source}
        elif method == "total_variation":
            scope = extra.get("scope", {})
            if card["card_id"] == "J2":
                value = {"1": 0.4, "2": 0.3, "3": 0.2, "4+": 0.1}
            elif card["card_id"] == "J3":
                value = {"0": 0.4, "1": 0.25, "2": 0.15, "3": 0.08, "4": 0.05, "5": 0.04, "6+": 0.03}
            elif card["card_id"] == "P1":
                value = {"8": 0.7, "12": 0.2, "20": 0.1}
            elif card["card_id"] == "B1" and "members" in scope:
                value = {"a": 0.5, "b": 0.5}
            elif card["card_id"] == "B1" and scope.get("symbol") == "wild":
                value = {"0": 0.8, "1": 0.2}
            elif card["card_id"] == "B1":
                value = {"none": 0.2, "single": 0.5, "two-plus": 0.3}
            elif card["card_id"] == "B2":
                value = {"2": 0.4, "3": 0.6}
            else:
                value = {"not-occurred": 0.5, "not-effective": 0.2, "2x": 0.2, "3x": 0.1}
            record = {"value": value, "source": source}
        else:
            raise AssertionError(f"测试未覆盖距离方法: {method}")
        if card["category_id"] in {"J", "P", "B"}:
            record["sample_count"] = 1000
            if extra.get("requires_bin_count"):
                record["bucket_count"] = 100
        return record

    def sample_plan(self, probabilities=None):
        plan = {
            "schema_version": "slot-alignment.sample-execution-plan.v1",
            "task_id": "test-task",
            "frozen_before_candidate": True,
            "rtp_group": 1,
            "sample_unit": "complete_paid_entry",
            "policy": {
                "id": "slot-alignment-fixed-sample-execution-v1",
                "version": "1.1.0",
                "sha256": sha256_file(SAMPLE_POLICY_PATH),
            },
            "rng_protocol": "chunk_seeded",
            "shard_size": 250000,
            "calibration": {
                "screen": 100000,
                "review": 500000,
                "finalist": 2000000,
                "independent_recheck": 2000000,
                "independent_recheck_top_candidates": 2,
            },
            "formal": {
                "tiers": [10000000, 20000000, 50000000],
                "minimum_conditional_sample": 2000,
                "conditional_probability_semantics": "whole_metric_instance_denominator_exposure_per_paid_entry",
                "conditional_exposure_probabilities": probabilities or {},
                "selected_paid_entry_count": 10000000,
                "owner_instance_id": None,
                "projected_owner_sample": None,
                "unresolved_below_minimum": [],
            },
        }
        plan["formal"].update(derived_formal(plan))
        return plan

    def runtime_capabilities(self, simulator_max=10, generator_status="supported"):
        layer = lambda maximum=10, status="supported": {
            "status": status,
            "min_cardinality": 1,
            "max_cardinality": maximum,
            "evidence": ["测试证据"],
        }
        capability = {
            "capability_id": "refill-profile-count",
            "name_zh": "按Tumble深度补位档",
            "category": "refill",
            "certified_script": layer(),
            "server_runtime": layer(),
            "authorization": {
                "status": "authorized",
                "min_cardinality": 1,
                "max_cardinality": 10,
                "operations": ["change_profile_count", "change_symbol_weights"],
                "evidence": ["用户授权"],
            },
            "candidate_generator": layer(10, generator_status),
            "calibration_simulator": layer(simulator_max),
            "formal_simulator": layer(simulator_max),
            "optimizer": {
                "status": "supported",
                "min_cardinality": 1,
                "max_cardinality": 10,
                "exposed_parameters": ["refill_profile_count", "refill_symbol_weights"],
                "sensitivity_plan_ids": ["refill-depth-escalation"],
                "evidence": ["测试计划"],
            },
            "equivalence": {
                "status": "passed",
                "evidence_sha256": "9" * 64,
                "evidence": ["逐局与RNG终态一致"],
            },
        }
        required = [
            ("state-reel-set-pool-cardinality", "routing"),
            ("reel-set-selection-scope", "routing"),
            ("reel-strip-symbol-count-and-order", "reel_generation"),
            ("stop-weights", "reel_generation"),
            ("refill-profile-count", "refill"),
            ("refill-symbol-weights", "refill"),
            ("height-weights", "height"),
            ("feature-mechanic-weights", "feature_weight"),
        ]
        capabilities = []
        for capability_id, category in required:
            item = copy.deepcopy(capability)
            item["capability_id"] = capability_id
            item["name_zh"] = capability_id
            item["category"] = category
            if capability_id != "refill-profile-count":
                item["candidate_generator"] = layer()
                item["calibration_simulator"] = layer()
                item["formal_simulator"] = layer()
            capabilities.append(item)
        covered = 7 + int(simulator_max >= 10 and generator_status == "supported")
        return {
            "schema_version": "slot-alignment.runtime-capability-matrix.v1",
            "task_id": "test-task",
            "mode": "normal",
            "rtp_group": 1,
            "frozen_before_candidate": True,
            "policy": {
                "id": "slot-alignment-runtime-capability-coverage-v1",
                "version": "1.0.0",
                "path": "assets/policies/runtime_capability_policy.json",
                "sha256": sha256_file(RUNTIME_CAPABILITY_POLICY_PATH),
            },
            "runtime_bundle_sha256": "b" * 64,
            "certified_script_sha256": "d" * 64,
            "parameter_authority_sha256": "f" * 64,
            "capabilities": capabilities,
            "summary": {
                "total_capabilities": 8,
                "authorized_capabilities": 8,
                "fully_covered_capabilities": covered,
                "coverage_status": "通过" if covered == 8 else "不通过",
            },
        }

    def build_inputs(self):
        profile = self.profile()
        library = load(LIBRARY_PATH)
        targets = {}
        bindings = profile["metric_bindings"]
        for card in library["cards"]:
            for facet in card["facets"]:
                for subitem, scope, extra in subitems(card["card_id"], facet["facet_id"], bindings):
                    instance_id = f"{card['card_id']}.{facet['facet_id']}.{safe_id(subitem)}"
                    record = self.target_for(card, facet, {**extra, "scope": scope})
                    if card["kind"] == "hard_gate" and "base_tolerance" not in record:
                        record["base_tolerance"] = 0.01
                    targets[instance_id] = record
        profile_path, targets_path, bindings_path, sample_plan_path, capabilities_path = [self.path(name) for name in ["profile.json", "targets.json", "bindings.json", "sample-plan.json", "runtime-capabilities.json"]]
        write(profile_path, profile)
        write(targets_path, {"targets": targets})
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
        write(sample_plan_path, self.sample_plan({"P2.mechanic_result_distribution_shift.wild-multiplier": 0.001}))
        write(capabilities_path, self.runtime_capabilities())
        return profile_path, targets_path, bindings_path, sample_plan_path, capabilities_path

    def test_runtime_capability_coverage_rejects_narrow_fast_layer(self):
        valid = self.path("runtime-capabilities-valid.json")
        write(valid, self.runtime_capabilities())
        self.run_script("validate_runtime_capability_coverage.py", "--matrix", valid)
        invalid = self.path("runtime-capabilities-invalid.json")
        write(invalid, self.runtime_capabilities(simulator_max=1))
        command = [sys.executable, str(ROOT / "scripts/validate_runtime_capability_coverage.py"), "--matrix", str(invalid)]
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("最大能力1小于授权上限10", result.stderr)

    def test_sample_execution_tiers_and_maximum_behavior(self):
        cases = [
            (0.0003, 10000000, []),
            (0.0002, 10000000, []),
            (0.00015, 20000000, []),
            (0.0001, 20000000, []),
            (0.00005, 50000000, []),
            (0.00004, 50000000, []),
            (0.00002, 50000000, ["P2.mechanic_result_state.wild-multiplier"]),
        ]
        for probability, expected_tier, expected_unresolved in cases:
            plan = self.sample_plan({"P2.mechanic_result_state.wild-multiplier": probability})
            validate_plan(plan)
            self.assertEqual(plan["formal"]["selected_paid_entry_count"], expected_tier)
            self.assertEqual(plan["formal"]["unresolved_below_minimum"], expected_unresolved)

    def test_sample_execution_policy_is_chunk_seeded_and_non_blocking(self):
        policy = load(SAMPLE_POLICY_PATH)
        self.assertEqual(policy["rng_protocol"]["calibration_default"], "chunk_seeded")
        self.assertEqual(policy["rng_protocol"]["formal_default"], "chunk_seeded")
        self.assertEqual(policy["rng_protocol"]["diagnostics_only"], ["crn_v1"])
        self.assertFalse(policy["execution"]["benchmark_is_blocking_gate"])
        self.assertEqual(policy["execution"]["benchmark_profiles"], ["core_simulation", "formal_full_observation"])
        self.assertTrue(policy["execution"]["internal_micro_batches_allowed"])
        self.assertTrue(policy["execution"]["internal_micro_batch_must_preserve_rng_stream"])
        self.assertTrue(policy["execution"]["worker_static_context_loads_once"])
        self.assertTrue(policy["execution"]["candidate_context_builds_once_per_worker"])
        self.assertEqual(policy["execution"]["parallelism_layer_count"], 1)
        self.assertTrue(policy["execution"]["nested_parallelism_forbidden"])
        self.assertIn("per_entry_tdigest_update", policy["execution"]["hot_path_forbidden"])
        self.assertIn("unbounded_exact_value_counts", policy["execution"]["hot_path_forbidden"])
        self.assertEqual(policy["execution"]["accumulator_cardinality"], "bounded_by_frozen_metric_support")
        self.assertTrue(policy["formal"]["state_frequency_must_not_drive_tier"])
        self.assertEqual(policy["calibration"]["stages"][2]["cumulative_paid_entries"], 2000000)
        self.assertEqual(policy["calibration"]["independent_recheck"]["additional_paid_entries"], 2000000)

    def test_compile_evaluate_and_schema(self):
        profile, targets, bindings, sample_plan, capabilities = self.build_inputs()
        contract_path = self.path("contract.json")
        self.run_script("compile_metric_contract.py", "--profile", profile, "--targets", targets, "--bindings", bindings, "--sample-plan", sample_plan, "--runtime-capabilities", capabilities, "--output", contract_path)
        contract = load(contract_path)
        self.assertEqual(contract["policies"]["sample_execution"]["version"], "1.1.0")
        self.assertEqual(contract["hashes"]["sample_execution_plan_sha256"], sha256_file(sample_plan))
        self.assertEqual(contract["hashes"]["runtime_capability_matrix_sha256"], sha256_file(capabilities))
        n1 = next(item for card in contract["cards"] if card["card_id"] == "N1" for item in card["instances"])
        self.assertEqual(n1["target"], 0.96)
        self.assertEqual(n1["target_source"]["method"], "user_confirmed_exact_rtp")
        self.assertEqual(n1["distance"]["method"], "absolute_probability_error")
        self.assertEqual(n1["tolerance"], {"source": "hard_gate_player_budget", "base": 0.003, "factor": 1.0, "effective": 0.003})
        j1_ids = [item["instance_id"] for card in contract["cards"] if card["card_id"] == "J1" for item in card["instances"]]
        self.assertEqual(j1_ids, ["J1.win_group_participation_rate.base.regular", "J1.win_group_participation_rate.base.special"])
        j2_ids = [item["instance_id"] for card in contract["cards"] if card["card_id"] == "J2" for item in card["instances"]]
        self.assertEqual(j2_ids, [
            "J2.primary_structure_mean.main-ways",
            "J2.primary_structure_p50.main-ways",
            "J2.primary_structure_p90.main-ways",
            "J2.simultaneous_visible_win_count_bin_rate.base.1",
            "J2.simultaneous_visible_win_count_bin_rate.base.2",
            "J2.simultaneous_visible_win_count_bin_rate.base.3",
            "J2.simultaneous_visible_win_count_bin_rate.base.4plus",
            "J2.simultaneous_visible_win_count_distribution_shift.base",
            "J2.visible_step_reward_mean.base",
            "J2.visible_step_reward_p50.base",
            "J2.visible_step_reward_p90.base",
        ])
        j3_ids = [item["instance_id"] for card in contract["cards"] if card["card_id"] == "J3" for item in card["instances"]]
        self.assertEqual(j3_ids, [
            "J3.total_depth_bin_rate.cascade.0",
            "J3.total_depth_bin_rate.cascade.1",
            "J3.total_depth_bin_rate.cascade.2",
            "J3.total_depth_bin_rate.cascade.3",
            "J3.total_depth_bin_rate.cascade.4",
            "J3.total_depth_bin_rate.cascade.5",
            "J3.total_depth_bin_rate.cascade.6plus",
            "J3.total_depth_distribution_shift.cascade",
        ])
        self.assertFalse(any("element_win_participation_rate" in item or "win_scale_by_depth" in item for item in j1_ids + j2_ids + j3_ids))
        reward = next(item for card in contract["cards"] if card["card_id"] == "J2" for item in card["instances"] if item["facet_id"] == "visible_step_reward_mean")
        self.assertEqual(reward["scope"]["display_bet_basis"], "total-bet")
        self.assertEqual(reward["tolerance"]["source"], "j_player_visible_budget")
        p1_ids = [item["instance_id"] for card in contract["cards"] if card["card_id"] == "P1" for item in card["instances"]]
        self.assertEqual(p1_ids, [
            "P1.entry_award_bin_rate.free-spin.8",
            "P1.entry_award_bin_rate.free-spin.12",
            "P1.entry_award_bin_rate.free-spin.20",
            "P1.entry_award_distribution_shift.free-spin",
            "P1.feature_duration_mean.free-spin",
            "P1.feature_duration_p50.free-spin",
            "P1.feature_duration_p90.free-spin",
        ])
        p2_ids = [item["instance_id"] for card in contract["cards"] if card["card_id"] == "P2" for item in card["instances"]]
        self.assertEqual(p2_ids, [
            "P2.mechanic_result_bin_rate.wild-multiplier.not-occurred",
            "P2.mechanic_result_bin_rate.wild-multiplier.not-effective",
            "P2.mechanic_result_bin_rate.wild-multiplier.2x",
            "P2.mechanic_result_bin_rate.wild-multiplier.3x",
            "P2.mechanic_result_distribution_shift.wild-multiplier",
        ])
        p_duration = next(item for card in contract["cards"] if card["card_id"] == "P1" for item in card["instances"] if item["facet_id"] == "feature_duration_mean")
        self.assertEqual(p_duration["scope"]["duration_unit"], "spin")
        self.assertEqual(p_duration["tolerance"]["source"], "p_player_visible_budget")
        b1_ids = [item["instance_id"] for card in contract["cards"] if card["card_id"] == "B1" for item in card["instances"]]
        self.assertEqual(b1_ids, [
            "B1.symbol_group_share_bin_rate.base-initial.regular-high",
            "B1.symbol_group_share_bin_rate.base-initial.regular-low",
            "B1.symbol_group_composition_shift.base-initial",
            "B1.symbol_group_member_share_bin_rate.base-initial.regular-high.a",
            "B1.symbol_group_member_share_bin_rate.base-initial.regular-high.b",
            "B1.symbol_group_member_distribution_shift.base-initial.regular-high",
            "B1.key_symbol_count_bin_rate.base-initial.wild.0",
            "B1.key_symbol_count_bin_rate.base-initial.wild.1",
            "B1.key_symbol_count_distribution_shift.base-initial.wild",
            "B1.aggregation_bin_rate.base-initial.none",
            "B1.aggregation_bin_rate.base-initial.single",
            "B1.aggregation_bin_rate.base-initial.two-plus",
            "B1.aggregation_distribution_shift.base-initial",
        ])
        self.assertTrue(all(item["tolerance"]["source"] == "b_player_visible_budget" for card in contract["cards"] if card["card_id"] == "B1" for item in card["instances"]))
        b2_ids = [item["instance_id"] for card in contract["cards"] if card["card_id"] == "B2" for item in card["instances"]]
        self.assertEqual(b2_ids, [
            "B2.reel_height_bin_rate.base-initial.r1.2",
            "B2.reel_height_bin_rate.base-initial.r1.3",
            "B2.reel_height_bin_rate.base-initial.r2.2",
            "B2.reel_height_bin_rate.base-initial.r2.3",
            "B2.reel_height_distribution_shift.base-initial.r1",
            "B2.reel_height_distribution_shift.base-initial.r2",
            "B2.active_cell_count_mean.base-initial",
            "B2.active_cell_count_p50.base-initial",
            "B2.active_cell_count_p90.base-initial",
            "B2.board_unevenness_mean.base-initial",
            "B2.board_unevenness_p90.base-initial",
        ])
        self.assertFalse(any("position" in item for item in b2_ids))
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
        self.assertEqual(result["summary"]["final_grade"], "S")
        self.assertEqual(result["summary"]["composite_score"], 100.0)
        self.assertEqual(result["summary"]["score_scope"], ["N"])
        self.assertEqual(result["summary"]["planned_score_scope"], ["N", "J", "P", "B"])
        self.assertEqual(result["summary"]["score_status"], "NJPB_READY_TOTAL_N_ONLY")
        self.assertEqual(result["summary"]["category_scores"]["P"], 100.0)
        self.assertEqual(result["summary"]["category_scores"]["B"], 100.0)
        self.assertTrue(all(item["formal_grade"] == "S" for card in result["card_results"] for item in card["instances"]))
        if result["summary"]["final_status"] != "通过":
            bad = [(item["instance_id"], item["status"], item.get("reason_zh")) for card in result["card_results"] for item in card["instances"] if item["status"] != "通过"]
            self.fail(f"等值候选未通过: {bad}")
        gate_path, report_path = self.path("stage3_gate.json"), self.path("report.md")
        self.run_script("generate_stage3_gate.py", "--result", result_path, "--output", gate_path)
        self.run_script("validate_artifacts.py", "--contract", contract_path, "--result", result_path, "--stage3-gate", gate_path)
        self.run_script("render_alignment_report.py", "--contract", contract_path, "--result", result_path, "--output", report_path)
        self.assertIn("最终状态：**通过**", report_path.read_text(encoding="utf-8"))
        n1_failure = copy.deepcopy(measurements)
        n1_failure[n1["instance_id"]]["candidate"] = n1["target"] + 0.004
        write(measurements_path, {"measurements": n1_failure, "audits": []})
        self.run_script("evaluate_alignment.py", "--contract", contract_path, "--measurements", measurements_path, "--phase", "FORMAL", "--output", result_path)
        failed_result = load(result_path)
        self.assertEqual(failed_result["summary"]["final_status"], "不通过")
        self.assertEqual(failed_result["summary"]["final_grade"], "F")
        self.assertIsNone(failed_result["summary"]["composite_score"])
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
        profile, targets, bindings, sample_plan, capabilities = self.build_inputs()
        data = load(targets)
        n1 = data["targets"]["N1.total_rtp.overall"]
        n1["source"].pop("confirmation_evidence_sha256")
        write(targets, data)
        command = [sys.executable, str(ROOT / "scripts/compile_metric_contract.py"), "--profile", str(profile), "--targets", str(targets), "--bindings", str(bindings), "--sample-plan", str(sample_plan), "--runtime-capabilities", str(capabilities), "--output", str(self.path("invalid-contract-1.json"))]
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

    def test_board_symbol_partition_must_be_valid(self):
        profile, targets, bindings, sample_plan, capabilities = self.build_inputs()
        command = [sys.executable, str(ROOT / "scripts/compile_metric_contract.py"), "--profile", str(profile), "--targets", str(targets), "--bindings", str(bindings), "--sample-plan", str(sample_plan), "--runtime-capabilities", str(capabilities), "--output", str(self.path("invalid-board-contract.json"))]

        data = load(profile)
        data["metric_bindings"]["boards"][0]["symbol_groups"].append({"group_id": "duplicate", "role": "regular_other", "symbols": ["a"]})
        write(profile, data)
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("视觉符号组之间存在重复符号", result.stderr)

        data = self.profile()
        data["metric_bindings"]["boards"][0]["symbols"].append("bonus")
        write(profile, data)
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("可见符号域未被symbol_groups和key_symbol_profiles覆盖", result.stderr)

        data = self.profile()
        data["metric_bindings"]["boards"][0]["component_id"] = "unknown"
        write(profile, data)
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("component_id不在components中", result.stderr)

    def test_win_groups_and_primary_axis_must_be_valid(self):
        profile, targets, bindings, sample_plan, capabilities = self.build_inputs()
        command = [sys.executable, str(ROOT / "scripts/compile_metric_contract.py"), "--profile", str(profile), "--targets", str(targets), "--bindings", str(bindings), "--sample-plan", str(sample_plan), "--runtime-capabilities", str(capabilities), "--output", str(self.path("invalid-j-contract.json"))]

        data = self.profile()
        data["metric_bindings"]["win_groups"][1]["elements"] = ["a", "wild"]
        write(profile, data)
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("win_groups之间存在重复元素", result.stderr)

        data = self.profile()
        data["metric_bindings"]["settlements"][0]["elements"].append("bonus")
        write(profile, data)
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("派奖元素未被win_groups覆盖", result.stderr)

        data = self.profile()
        data["metric_bindings"]["settlements"][0]["primary_size_axis"] = "matched_reels"
        write(profile, data)
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("primary_size_axis必须为ways", result.stderr)

    def test_fixed_j_dimensions_do_not_generate_instances(self):
        bindings = self.profile()["metric_bindings"]
        bindings["settlements"][0]["variable_primary_size"] = False
        bindings["components"][0]["variable_simultaneous_win_count"] = False
        bindings["components"][0]["variable_visible_step_reward"] = False
        bindings["continuous_settlements"][0]["variable_depth"] = False
        for card_id, facet_id in [
            ("J2", "primary_structure_bin_rate"),
            ("J2", "primary_structure_distribution_shift"),
            ("J2", "primary_structure_mean"),
            ("J2", "primary_structure_p50"),
            ("J2", "primary_structure_p90"),
            ("J2", "simultaneous_visible_win_count_bin_rate"),
            ("J2", "simultaneous_visible_win_count_distribution_shift"),
            ("J2", "visible_step_reward_mean"),
            ("J2", "visible_step_reward_p50"),
            ("J2", "visible_step_reward_p90"),
            ("J3", "total_depth_bin_rate"),
            ("J3", "total_depth_distribution_shift"),
        ]:
            self.assertEqual(subitems(card_id, facet_id, bindings), [])

    def test_fixed_p_dimensions_do_not_generate_instances(self):
        bindings = self.profile()["metric_bindings"]
        bindings["features"][0]["entry_award_evaluation_mode"] = "fixed_rule"
        bindings["features"][0].pop("entry_award_unit")
        bindings["features"][0].pop("entry_award_bins")
        bindings["features"][0]["duration_evaluation_mode"] = "fixed_rule"
        bindings["special_mechanics"][0]["result_evaluation_mode"] = "fixed_rule"
        for card_id, facet_id in [
            ("P1", "entry_award_bin_rate"),
            ("P1", "entry_award_distribution_shift"),
            ("P1", "feature_duration_mean"),
            ("P1", "feature_duration_p50"),
            ("P1", "feature_duration_p90"),
            ("P2", "mechanic_result_bin_rate"),
            ("P2", "mechanic_result_distribution_shift"),
        ]:
            self.assertEqual(subitems(card_id, facet_id, bindings), [])

    def test_removed_j3_field_is_rejected(self):
        profile = self.profile()
        profile["metric_bindings"]["continuous_settlements"][0]["variable_" + "chain_" + "reward"] = True
        errors = list(Draft202012Validator(load(ROOT / "assets/schemas/game-profile-metric-bindings.schema.json")).iter_errors(profile))
        self.assertTrue(errors)

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
