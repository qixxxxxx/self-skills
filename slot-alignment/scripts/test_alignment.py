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
    evaluate_instance,
    sha256_file,
    total_variation,
)
from compile_metric_contract import EVALUATION_POLICY_PATH, HARD_POLICY_PATH, LIBRARY_PATH, TARGET_EVIDENCE_POLICY_PATH, b_c_budget, j_c_budget, n_c_budget, p_c_budget, safe_id, subitems
from validate_sample_plan import POLICY_PATH as SAMPLE_POLICY_PATH, derived_formal, validate_plan
from validate_workspace_layout import canonical_shard_sha256, validate_promoted_hash, validate_shards, validate_skill_contract


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_CAPABILITY_POLICY_PATH = ROOT / "assets/policies/runtime_capability_policy.json"


def exact_target_evidence():
    return {
        "classification": "exact",
        "sample_count": None,
        "minimum_usable_count": None,
        "recommended_count": None,
        "event_count": None,
        "minimum_event_count": None,
        "recommended_event_count": None,
        "bucket_count": None,
        "minimum_bucket_count": None,
        "recommended_bucket_count": None,
    }


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
        for score, grade in [(100, "S"), (90, "S"), (89.999, "A"), (80, "A"), (79.999, "B"), (70, "B"), (69.999, "C"), (0, "C")]:
            self.assertEqual(grade_score(score, policy), grade)
        contract = policy["c_budget_contract"]
        self.assertEqual(contract["pass_rule"], "distance_lte_c_budget")
        self.assertEqual(contract["c_budget_role"], "sole_maximum_pass_distance")
        self.assertEqual(contract["deviation_ratio_role"], "comparison_scoring_ranking_and_reporting_only")

    def test_sample_evidence_shortfall_forces_u(self):
        policy = load(ROOT / "assets/policies/alignment_evaluation_policy.json")
        card = {"category_id": "N"}
        instance = {
            "instance_id": "N2.positive_return_rate.overall",
            "facet_id": "positive_return_rate",
            "subitem_id": "overall",
            "target": 0.2,
            "target_evidence": exact_target_evidence(),
            "distance": {"method": "absolute_probability_error"},
            "c_budget": {"source": "hard_gate_player_budget", "value": 0.02},
            "status": "active",
        }
        result = evaluate_instance(card, instance, {
            "candidate": 0.2,
            "sample_evidence": {
                "target_count": 1000,
                "candidate_count": 1000,
                "required_target_count": 500,
                "required_candidate_count": 2000,
            },
        }, policy)
        self.assertEqual((result["status"], result["formal_grade"]), ("样本不足", "U"))

    def test_c_budget_is_the_only_pass_boundary(self):
        policy = load(ROOT / "assets/policies/alignment_evaluation_policy.json")
        card = {"category_id": "N"}
        instance = {
            "instance_id": "N2.positive_return_rate.overall",
            "facet_id": "positive_return_rate",
            "subitem_id": "overall",
            "target": 0.2,
            "target_evidence": exact_target_evidence(),
            "distance": {"method": "absolute_probability_error"},
            "c_budget": {"source": "hard_gate_player_budget", "value": 0.02},
            "status": "active",
        }
        passed = evaluate_instance(card, instance, {"candidate": 0.219}, policy)
        failed = evaluate_instance(card, instance, {"candidate": 0.221}, policy)
        self.assertEqual((passed["status"], passed["formal_grade"]), ("通过", "C"))
        self.assertEqual((failed["status"], failed["formal_grade"]), ("不通过", "F"))
        self.assertAlmostEqual(passed["deviation_ratio"], passed["distance"] / passed["c_budget"])

        exact = {**instance, "target": 1.0, "distance": {"method": "absolute_error"}, "c_budget": {"source": "deterministic_exact", "value": 0.0}}
        exact_passed = evaluate_instance(card, exact, {"candidate": 1.0}, policy)
        exact_failed = evaluate_instance(card, exact, {"candidate": 1.1}, policy)
        self.assertEqual((exact_passed["status"], exact_passed["deviation_ratio"], exact_passed["score"]), ("通过", 0.0, 100.0))
        self.assertEqual((exact_failed["status"], exact_failed["deviation_ratio"], exact_failed["score"]), ("不通过", None, 0.0))

    def test_n_c_budget_rules(self):
        policy = load(HARD_POLICY_PATH)
        self.assertEqual(policy["calculation"]["policy_role"], "calculate_and_freeze_N_c_budget_before_candidate_only")
        self.assertNotIn("pass_rule", policy["calculation"])
        bindings = {"features": [{"feature_id": "free-spin"}]}
        self.assertEqual(n_c_budget("N1", 0.96, {"scope": "overall"}, bindings, policy), 0.003)
        self.assertAlmostEqual(n_c_budget("N2", 0.2, {"scope": "overall"}, bindings, policy), 0.012)
        self.assertAlmostEqual(n_c_budget("N3", 0.001, {"feature": "free-spin"}, bindings, policy), 0.00012)
        self.assertAlmostEqual(n_c_budget("N3", 0.0001, {"feature": "free-spin"}, bindings, policy), 0.00002)
        self.assertEqual(n_c_budget("N4", 0.2, {"scope": "overall"}, bindings, policy), 0.015)
        self.assertEqual(n_c_budget("N5", 10, {"scope": "overall"}, bindings, policy), 0.08)
        self.assertEqual(n_c_budget("N5", 10, {"scope": "base"}, bindings, policy), 0.08)
        self.assertEqual(n_c_budget("N5", 10, {"scope": "free-spin"}, bindings, policy), 0.12)
        self.assertEqual(n_c_budget("N6", 0.2, {"component": "base"}, bindings, policy), 0.015)

    def test_n_category_uses_equal_card_weight(self):
        policy = load(ROOT / "assets/policies/alignment_evaluation_policy.json")
        def instance(instance_id):
            return {
                "instance_id": instance_id,
                "facet_id": "value",
                "subitem_id": instance_id.rsplit(".", 1)[-1],
                "target": 0.5,
                "target_evidence": exact_target_evidence(),
                "distance": {"method": "absolute_probability_error"},
                "c_budget": {"source": "hard_gate_player_budget", "value": 0.1},
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

    def test_j_c_budget_rules(self):
        policy = load(EVALUATION_POLICY_PATH)
        bindings = {"features": [{"feature_id": "free-spin"}]}
        base, feature = {"component": "base"}, {"component": "free-spin"}
        self.assertAlmostEqual(j_c_budget(0.0017, base, {"budget_rule": "J1.participation"}, bindings, policy), 0.0017)
        self.assertAlmostEqual(j_c_budget(0.3, base, {"budget_rule": "J1.participation"}, bindings, policy), 0.025)
        self.assertAlmostEqual(j_c_budget(0.3, feature, {"budget_rule": "J1.participation"}, bindings, policy), 0.03)
        self.assertAlmostEqual(j_c_budget(0.01, base, {"budget_rule": "J2.primary_structure_categorical.bin"}, bindings, policy), 0.005)
        self.assertAlmostEqual(j_c_budget(0.01, feature, {"budget_rule": "J2.primary_structure_categorical.bin"}, bindings, policy), 0.01)
        self.assertAlmostEqual(j_c_budget(0.5, {**base, "natural_unit": 1}, {"budget_rule": "J2.primary_structure_summary.mean"}, bindings, policy), 1.0)
        self.assertAlmostEqual(j_c_budget(0.01, base, {"budget_rule": "J2.simultaneous_win_count.bin"}, bindings, policy), 0.002)
        self.assertAlmostEqual(j_c_budget(2.0, {**feature, "minimum_visible_reward_unit": 0.01}, {"budget_rule": "J2.visible_step_reward.p90"}, bindings, policy), 0.3)
        self.assertAlmostEqual(j_c_budget(0.01, base, {"budget_rule": "J3.depth.bin"}, bindings, policy), 0.002)
        self.assertAlmostEqual(j_c_budget({}, feature, {"budget_rule": "J3.depth.overall"}, bindings, policy), 0.04)

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

    def test_p_c_budget_rules(self):
        policy = load(EVALUATION_POLICY_PATH)
        self.assertAlmostEqual(p_c_budget(0.003, {"budget_rule": "P1.entry_award.bin"}, policy), 0.003)
        self.assertAlmostEqual(p_c_budget(0.1, {"budget_rule": "P1.entry_award.bin"}, policy), 0.02)
        self.assertAlmostEqual(p_c_budget({}, {"budget_rule": "P1.entry_award.overall"}, policy), 0.04)
        self.assertAlmostEqual(p_c_budget(10, {"budget_rule": "P1.duration.mean"}, policy), 1.2)
        self.assertAlmostEqual(p_c_budget(3, {"budget_rule": "P1.duration.p50"}, policy), 1.0)
        self.assertAlmostEqual(p_c_budget(5, {"budget_rule": "P1.duration.p90"}, policy), 2.0)
        self.assertAlmostEqual(p_c_budget(0.1, {"budget_rule": "P2.result.bin"}, policy), 0.015)
        self.assertAlmostEqual(p_c_budget({}, {"budget_rule": "P2.result.overall"}, policy), 0.04)

    def test_b_c_budget_rules(self):
        policy = load(EVALUATION_POLICY_PATH)
        self.assertAlmostEqual(b_c_budget(0.2, {"budget_rule": "B1.symbol_group_composition.bin"}, policy), 0.03)
        self.assertAlmostEqual(b_c_budget({}, {"budget_rule": "B1.symbol_group_composition.overall"}, policy), 0.05)
        self.assertAlmostEqual(b_c_budget(0.1, {"budget_rule": "B1.key_symbol_count.bin"}, policy), 0.012)
        self.assertAlmostEqual(b_c_budget(10, {"budget_rule": "B2.active_cell_count.mean"}, policy), 1.0)
        self.assertAlmostEqual(b_c_budget(5, {"budget_rule": "B2.unevenness.p90"}, policy), 1.0)


class EndToEndTests(unittest.TestCase):
    def setUp(self):
        self.temp = Path(tempfile.mkdtemp(prefix="slot-alignment-v6-"))
        self.created = []

    def tearDown(self):
        for path in reversed(self.created):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
        self.temp.rmdir()

    def path(self, name):
        path = self.temp / name
        self.created.append(path)
        return path

    def directory(self, name):
        path = self.temp
        for part in Path(name).parts:
            path /= part
            if not path.exists():
                path.mkdir()
                self.created.append(path)
        return path

    def nested_path(self, name):
        path = Path(name)
        parent = self.directory(path.parent) if path.parent != Path(".") else self.temp
        result = parent / path.name
        self.created.append(result)
        return result

    def run_script(self, name, *args):
        result = subprocess.run([sys.executable, str(ROOT / "scripts" / name), *map(str, args)], cwd=ROOT, capture_output=True, text=True)
        if result.returncode:
            self.fail(result.stderr or result.stdout)

    def measurement_document(self, contract_path, measurements, phase="FORMAL", audits=None):
        contract = load(contract_path)
        return {
            "schema_version": "slot-alignment.metric-measurements.v6",
            "task_id": contract["task_id"],
            "phase": phase,
            "metric_contract_sha256": sha256_file(contract_path),
            "measurements": measurements,
            "audits": audits or [],
        }

    def report_input_manifest(self, task_id="test-task"):
        path = self.path(f"{task_id}-input-manifest.json")
        write(path, {
            "task_id": task_id,
            "game_code": "test-game",
            "game_name_zh": "测试游戏",
            "mode": "normal",
            "runtime_environment": "test",
            "target_rtp": {"value": 0.96},
        })
        return path

    def profile(self):
        return {
            "schema_version": "slot-alignment.game-profile.v6",
            "metric_bindings": {
                "features": [{
                    "feature_id": "free-spin",
                    "name_zh": "免费旋转",
                    "evidence_refs": ["test:feature"],
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
                    "name_zh": "主Ways结算",
                    "evidence_refs": ["test:settlement"],
                    "component_id": "base",
                    "settlement_type": "ways",
                    "elements": ["a", "wild"],
                    "primary_size_axis": "ways",
                    "variable_primary_size": True,
                    "primary_size_evaluation_mode": "summary_triplet",
                    "primary_size_unit": 1,
                }],
                "win_groups": [
                    {"component_id": "base", "group_id": "regular", "name_zh": "普通中奖", "evidence_refs": ["test:group"], "role": "regular_other", "elements": ["a"]},
                    {"component_id": "base", "group_id": "special", "name_zh": "特殊中奖", "evidence_refs": ["test:group"], "role": "special", "elements": ["wild"]},
                ],
                "continuous_settlements": [{"continuous_id": "cascade", "name_zh": "连续消除", "evidence_refs": ["test:cascade"], "component_id": "base", "variable_depth": True}],
                "special_mechanics": [{
                    "mechanic_id": "wild-multiplier",
                    "name_zh": "Wild倍数",
                    "evidence_refs": ["test:mechanic"],
                    "mechanic_family": "multiplier_modifier",
                    "opportunity_unit": "feature_spin",
                    "result_evaluation_mode": "categorical_distribution",
                    "guaranteed_resolution": False,
                    "result_states": ["not-occurred", "not-effective", "2x", "3x"],
                    "result_state_names_zh": {
                        "not-occurred": "没有出现",
                        "not-effective": "出现但未生效",
                        "2x": "2倍生效",
                        "3x": "3倍生效",
                    },
                    "inactive_state_ids": ["not-occurred", "not-effective"],
                }],
                "boards": [{
                    "board_scope_id": "base-initial",
                    "name_zh": "Base初始盘面",
                    "evidence_refs": ["test:board"],
                    "component_id": "base",
                    "visual_phase": "initial",
                    "rows": 3,
                    "columns": 2,
                    "shape_mode": "variable_reel_height",
                    "symbols": ["a", "b", "c", "wild"],
                    "symbol_groups": [
                        {"group_id": "regular-high", "name_zh": "高值普通符号", "role": "regular_high", "symbols": ["a", "b"]},
                        {"group_id": "regular-low", "name_zh": "低值普通符号", "role": "regular_low", "symbols": ["c"]},
                    ],
                    "key_symbol_profiles": [{"symbol_id": "wild", "count_bins": ["0", "1"], "sample_filter": "all_stable_boards"}],
                    "aggregation_profile": {"aggregation_type": "vertical_run", "symbol_ids": ["a", "b", "c"], "bins": ["none", "single", "two-plus"], "sample_filter": "all_stable_boards"},
                    "reel_height_profiles": [
                        {"reel_id": "r1", "bins": ["2", "3"]},
                        {"reel_id": "r2", "bins": ["2", "3"]},
                    ],
                }],
                "components": [
                    {"component_id": "base", "name_zh": "基础游戏", "evidence_refs": ["test:component"], "display_bet_basis": "total-bet", "variable_simultaneous_win_count": True, "simultaneous_win_count_bins": ["1", "2", "3", "4+"], "variable_visible_step_reward": True, "minimum_visible_reward_unit": 0.01},
                    {"component_id": "free-spin", "name_zh": "免费旋转", "evidence_refs": ["test:component"], "display_bet_basis": "total-bet", "variable_simultaneous_win_count": False, "variable_visible_step_reward": False},
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
            record = {"value": {"min": 0.95, "max": 0.97}, "source": source}
        elif method == "relative_error":
            record = {"value": 2.0, "source": source}
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
            record = {"value": value, "source": source}
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
        record["target_status"] = "available"
        if card["card_id"] != "N1":
            record["sample_count"] = 10000
            if card["card_id"] == "N3":
                record["event_count"] = 100
        if card["category_id"] in {"J", "P", "B"}:
            record["sample_count"] = 1000
            if extra.get("requires_bin_count"):
                record["bucket_count"] = 100
        return record

    def sample_plan(self, probabilities=None):
        plan = {
            "schema_version": "slot-alignment.sample-execution-plan.v6",
            "task_id": "test-task",
            "frozen_before_candidate": True,
            "rtp_group": 1,
            "sample_unit": "complete_paid_entry",
            "policy": {
                "id": "slot-alignment-fixed-sample-execution-v6",
                "version": "6.0.0",
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
            "schema_version": "slot-alignment.runtime-capability-matrix.v6",
            "task_id": "test-task",
            "mode": "normal",
            "rtp_group": 1,
            "frozen_before_candidate": True,
            "policy": {
                "id": "slot-alignment-runtime-capability-coverage-v6",
                "version": "6.0.0",
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
                    targets[instance_id] = record
        profile_path, targets_path, bindings_path, sample_plan_path, capabilities_path = [self.path(name) for name in ["profile.json", "targets.json", "bindings.json", "sample-plan.json", "runtime-capabilities.json"]]
        write(profile_path, profile)
        write(targets_path, {
            "schema_version": "slot-alignment.metric-targets.v6",
            "task_id": "test-task",
            "frozen_before_candidate": True,
            "targets": targets,
        })
        write(bindings_path, {
            "schema_version": "slot-alignment.contract-bindings.v6",
            "contract_version": "test-v6",
            "task_id": "test-task",
            "mode": "normal",
            "rtp_group": 1,
            "frozen_before_candidate": True,
            "runtime_bundle_sha256": "b" * 64,
            "original_evidence_sha256": "c" * 64,
            "script_sha256": "d" * 64,
            "game_profile_sha256": sha256_file(profile_path),
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

    def test_target_evidence_thresholds_are_separate_from_candidate_samples(self):
        policy = load(TARGET_EVIDENCE_POLICY_PATH)
        self.assertEqual(policy["metric_thresholds"]["N2"], {"minimum_sample": 200, "recommended_sample": 5000})
        self.assertEqual(policy["metric_thresholds"]["N3"]["minimum_event_count"], 5)
        self.assertEqual(policy["metric_thresholds"]["J1"], {"minimum_sample": 50, "recommended_sample": 200})
        self.assertEqual(policy["metric_thresholds"]["P1"], {"minimum_sample": 30, "recommended_sample": 100})
        self.assertEqual(policy["metric_thresholds"]["B1"], {"minimum_sample": 100, "recommended_sample": 300})
        self.assertEqual(policy["categorical_bin_thresholds"]["minimum_observed_count"], 5)
        self.assertEqual(load(EVALUATION_POLICY_PATH)["sample_insufficiency"]["scope"], "candidate_measurements_only")

    def test_low_original_sample_becomes_observation_and_limited_pass(self):
        profile, targets, bindings, sample_plan, capabilities = self.build_inputs()
        data = load(targets)
        low_id = "J1.win_group_participation_rate.base.regular"
        data["targets"][low_id]["sample_count"] = 10
        write(targets, data)
        contract_path = self.path("limited-contract.json")
        self.run_script("compile_metric_contract.py", "--profile", profile, "--targets", targets, "--bindings", bindings, "--sample-plan", sample_plan, "--runtime-capabilities", capabilities, "--output", contract_path)
        contract = load(contract_path)
        self.assertEqual(contract["coverage"]["status"], "有限")
        self.assertIn(low_id, {item["instance_id"] for item in contract["coverage"]["observational_instances"]})
        self.assertNotIn(low_id, {item["instance_id"] for card in contract["cards"] for item in card["instances"]})
        measurements = {
            instance["instance_id"]: {"candidate": instance["target"], "sample_evidence": {"target_count": 1, "candidate_count": 2000}}
            for card in contract["cards"] for instance in card["instances"]
        }
        measurements_path, result_path = self.path("limited-measurements.json"), self.path("limited-result.json")
        write(measurements_path, self.measurement_document(contract_path, measurements))
        self.run_script("evaluate_alignment.py", "--contract", contract_path, "--measurements", measurements_path, "--phase", "FORMAL", "--output", result_path)
        result = load(result_path)
        Draft202012Validator(load(ROOT / "assets/schemas/alignment-result.schema.json")).validate(result)
        self.assertEqual(result["summary"]["final_status"], "通过")
        self.assertEqual(result["summary"]["conclusion"], "有限范围通过")
        self.assertEqual(result["summary"]["observational_instance_count"], 1)
        baseline_result = copy.deepcopy(result)
        baseline_result["phase"] = "BASELINE"
        baseline_result_path = self.path("limited-baseline-result.json")
        gate_path = self.path("limited-stage3-gate.json")
        report_path = self.path("limited-report.md")
        write(baseline_result_path, baseline_result)
        self.run_script("generate_stage3_gate.py", "--result", baseline_result_path, "--output", gate_path)
        self.run_script("validate_artifacts.py", "--contract", contract_path, "--result", baseline_result_path, "--stage3-gate", gate_path)
        self.run_script("render_alignment_report.py", "--input-manifest", self.report_input_manifest(), "--contract", contract_path, "--result", result_path, "--output", report_path)
        report = report_path.read_text(encoding="utf-8")
        self.assertIn("对齐结论：有限范围通过", report)
        self.assertNotIn(low_id, report)
        self.assertIn("略过（原版样本不足）", report)
        self.assertIn("原版有效样本10，最低50，建议200", report)

    def test_low_distribution_bin_observes_entire_group(self):
        profile, targets, bindings, sample_plan, capabilities = self.build_inputs()
        data = load(targets)
        low_id = "P1.entry_award_bin_rate.free-spin.8"
        data["targets"][low_id]["bucket_count"] = 4
        write(targets, data)
        contract_path = self.path("low-bin-contract.json")
        self.run_script("compile_metric_contract.py", "--profile", profile, "--targets", targets, "--bindings", bindings, "--sample-plan", sample_plan, "--runtime-capabilities", capabilities, "--output", contract_path)
        observed = {item["instance_id"] for item in load(contract_path)["coverage"]["observational_instances"]}
        self.assertTrue({
            "P1.entry_award_bin_rate.free-spin.8",
            "P1.entry_award_bin_rate.free-spin.12",
            "P1.entry_award_bin_rate.free-spin.20",
            "P1.entry_award_distribution_shift.free-spin",
        }.issubset(observed))
        self.assertNotIn("P1.feature_duration_mean.free-spin", observed)

    def test_compile_evaluate_and_schema(self):
        profile, targets, bindings, sample_plan, capabilities = self.build_inputs()
        contract_path = self.path("contract.json")
        self.run_script("compile_metric_contract.py", "--profile", profile, "--targets", targets, "--bindings", bindings, "--sample-plan", sample_plan, "--runtime-capabilities", capabilities, "--output", contract_path)
        contract = load(contract_path)
        self.assertEqual(contract["policies"]["sample_execution"]["version"], "6.0.0")
        self.assertEqual(contract["policies"]["target_evidence"]["version"], "6.0.0")
        self.assertEqual(contract["coverage"]["status"], "完整")
        self.assertEqual(contract["hashes"]["sample_execution_plan_sha256"], sha256_file(sample_plan))
        self.assertEqual(contract["hashes"]["runtime_capability_matrix_sha256"], sha256_file(capabilities))
        self.assertEqual(contract["hashes"]["targets_sha256"], sha256_file(targets))
        self.assertEqual(contract["hashes"]["contract_bindings_sha256"], sha256_file(bindings))
        n1 = next(item for card in contract["cards"] if card["card_id"] == "N1" for item in card["instances"])
        self.assertEqual(n1["target"], 0.96)
        self.assertEqual(n1["target_source"]["method"], "user_confirmed_exact_rtp")
        self.assertEqual(n1["distance"]["method"], "absolute_probability_error")
        self.assertEqual(n1["c_budget"], {"source": "hard_gate_player_budget", "value": 0.003})
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
        self.assertEqual(reward["c_budget"]["source"], "j_player_visible_budget")
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
        p2_state = next(item for card in contract["cards"] if card["card_id"] == "P2" for item in card["instances"] if item["scope"].get("state") == "not-occurred")
        p2_distribution = next(item for card in contract["cards"] if card["card_id"] == "P2" for item in card["instances"] if "states" in item["scope"])
        self.assertEqual(p2_state["scope"]["labels_zh"]["state"], "没有出现")
        self.assertEqual(p2_distribution["scope"]["labels_zh"]["states"]["not-effective"], "出现但未生效")
        p_duration = next(item for card in contract["cards"] if card["card_id"] == "P1" for item in card["instances"] if item["facet_id"] == "feature_duration_mean")
        self.assertEqual(p_duration["scope"]["duration_unit"], "spin")
        self.assertEqual(p_duration["c_budget"]["source"], "p_player_visible_budget")
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
        self.assertTrue(all(item["c_budget"]["source"] == "b_player_visible_budget" for card in contract["cards"] if card["card_id"] == "B1" for item in card["instances"]))
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
        write(measurements_path, self.measurement_document(contract_path, measurements))
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
        recheck_measurements, recheck_result = self.path("recheck-measurements.json"), self.path("recheck-result.json")
        write(recheck_measurements, self.measurement_document(contract_path, measurements, phase="INDEPENDENT_RECHECK"))
        self.run_script("evaluate_alignment.py", "--contract", contract_path, "--measurements", recheck_measurements, "--phase", "INDEPENDENT_RECHECK", "--output", recheck_result)
        self.assertEqual(load(recheck_result)["phase"], "INDEPENDENT_RECHECK")
        gate_path, report_path = self.path("stage3_gate.json"), self.path("report.md")
        baseline_result_path = self.path("baseline-result.json")
        baseline_result = copy.deepcopy(result)
        baseline_result["phase"] = "BASELINE"
        write(baseline_result_path, baseline_result)
        self.run_script("generate_stage3_gate.py", "--result", baseline_result_path, "--output", gate_path)
        self.run_script("validate_artifacts.py", "--contract", contract_path, "--result", baseline_result_path, "--stage3-gate", gate_path)
        self.run_script("render_alignment_report.py", "--input-manifest", self.report_input_manifest(), "--contract", contract_path, "--result", result_path, "--output", report_path)
        report = report_path.read_text(encoding="utf-8")
        self.assertIn("对齐结论：完整范围通过", report)
        self.assertIn("## 二、指标详情", report)
        self.assertIn("N 数值指标", report)
        self.assertNotIn("N1.total_rtp.overall", report)
        attention = report.split("## 三、需要关注的指标", 1)[1].split("## 四、样本与覆盖说明", 1)[0]
        self.assertIn("当前没有需要继续处理的正式指标。", attention)
        for label in ["没有出现", "出现但未生效", "2倍生效", "3倍生效", "无聚集", "2个以上聚集", "第1轴"]:
            self.assertIn(label, report)
        for technical in ["not-occurred", "not-effective", "regular-high", "regular-low", "two-plus", "第r1轴", "instance_id", "facet_id"]:
            self.assertNotIn(technical, report)
        self.assertEqual([path.name for path in (ROOT / "assets/templates/reports").glob("*.md")], ["对齐报告.md"])

        task_root = self.directory("test-task")
        canonical_input = self.nested_path("test-task/artifacts/01-input-profile/input_manifest.json")
        canonical_contract = self.nested_path("test-task/artifacts/02-metric-matching/metric_contract.json")
        canonical_result = self.nested_path("test-task/artifacts/04-alignment/formal_result.json")
        canonical_report = self.nested_path("test-task/交付物/报告文档/对齐报告.md")
        write(canonical_input, load(self.report_input_manifest("test-task-canonical")) | {"task_id": "test-task"})
        write(canonical_contract, contract)
        write(canonical_result, result)
        self.run_script(
            "render_alignment_report.py",
            "--input-manifest", canonical_input,
            "--contract", canonical_contract,
            "--result", canonical_result,
            "--output", canonical_report,
            "--task-root", task_root,
        )
        report_manifest_path = task_root / "交付物/报告文档/report_manifest.json"
        self.created.append(report_manifest_path)
        report_manifest = load(report_manifest_path)
        Draft202012Validator(load(ROOT / "assets/schemas/alignment-report-manifest.schema.json")).validate(report_manifest)
        self.assertEqual(report_manifest["task_id"], "test-task")
        self.assertEqual(report_manifest["report_file"]["sha256"], sha256_file(canonical_report))
        n1_failure = copy.deepcopy(measurements)
        n1_failure[n1["instance_id"]]["candidate"] = n1["target"] + 0.004
        write(measurements_path, self.measurement_document(contract_path, n1_failure))
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
        write(measurements_path, self.measurement_document(contract_path, failing))
        self.run_script("evaluate_alignment.py", "--contract", contract_path, "--measurements", measurements_path, "--phase", "FORMAL", "--output", result_path)
        self.assertIn(load(result_path)["summary"]["final_status"], {"不通过", "无法完整判定"})
        insufficient = copy.deepcopy(measurements)
        insufficient[first_alignment["instance_id"]] = {"status": "样本不足", "reason_zh": "测试", "sample_evidence": {"target_count": 0, "candidate_count": 1000}}
        write(measurements_path, self.measurement_document(contract_path, insufficient))
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

    def test_evaluate_requires_measurement_contract_and_phase_binding(self):
        profile, targets, bindings, sample_plan, capabilities = self.build_inputs()
        contract_path = self.path("bound-contract.json")
        self.run_script("compile_metric_contract.py", "--profile", profile, "--targets", targets, "--bindings", bindings, "--sample-plan", sample_plan, "--runtime-capabilities", capabilities, "--output", contract_path)
        contract = load(contract_path)
        instance = next(item for card in contract["cards"] for item in card["instances"])
        measurement = {
            instance["instance_id"]: {
                "candidate": instance["target"],
                "sample_evidence": {"target_count": 1000, "candidate_count": 2000},
            }
        }
        measurements_path = self.path("unbound-measurements.json")
        document = self.measurement_document(contract_path, measurement)
        document["metric_contract_sha256"] = "0" * 64
        write(measurements_path, document)
        command = [sys.executable, str(ROOT / "scripts/evaluate_alignment.py"), "--contract", str(contract_path), "--measurements", str(measurements_path), "--phase", "FORMAL", "--output", str(self.path("unbound-result.json"))]
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("metric_contract_sha256与当前合同不一致", result.stderr)

        document = self.measurement_document(contract_path, measurement, phase="BASELINE")
        write(measurements_path, document)
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("phase与命令行阶段不一致", result.stderr)

    def test_compile_rejects_game_profile_hash_drift(self):
        profile, targets, bindings, sample_plan, capabilities = self.build_inputs()
        data = load(profile)
        data["metric_bindings"]["components"][0]["name_zh"] = "被修改的基础游戏"
        write(profile, data)
        command = [sys.executable, str(ROOT / "scripts/compile_metric_contract.py"), "--profile", str(profile), "--targets", str(targets), "--bindings", str(bindings), "--sample-plan", str(sample_plan), "--runtime-capabilities", str(capabilities), "--output", str(self.path("profile-hash-drift.json"))]
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("game_profile_sha256与当前画像不一致", result.stderr)

    def test_compile_rejects_runtime_capability_binding_hash_drift(self):
        binding_pairs = [
            ("runtime_bundle_sha256", "runtime_bundle_sha256"),
            ("certified_script_sha256", "script_sha256"),
            ("parameter_authority_sha256", "parameter_authority_sha256"),
        ]
        for matrix_key, binding_key in binding_pairs:
            with self.subTest(matrix_key=matrix_key):
                profile, targets, bindings, sample_plan, capabilities = self.build_inputs()
                data = load(capabilities)
                data[matrix_key] = "0" * 64
                write(capabilities, data)
                command = [sys.executable, str(ROOT / "scripts/compile_metric_contract.py"), "--profile", str(profile), "--targets", str(targets), "--bindings", str(bindings), "--sample-plan", str(sample_plan), "--runtime-capabilities", str(capabilities), "--output", str(self.path(f"{binding_key}-drift.json"))]
                result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(f"{matrix_key}与合同绑定不一致", result.stderr)

    def test_board_symbol_partition_must_be_valid(self):
        profile, targets, bindings, sample_plan, capabilities = self.build_inputs()
        command = [sys.executable, str(ROOT / "scripts/compile_metric_contract.py"), "--profile", str(profile), "--targets", str(targets), "--bindings", str(bindings), "--sample-plan", str(sample_plan), "--runtime-capabilities", str(capabilities), "--output", str(self.path("invalid-board-contract.json"))]

        data = load(profile)
        data["metric_bindings"]["boards"][0]["symbol_groups"].append({"group_id": "duplicate", "name_zh": "重复组", "role": "regular_other", "symbols": ["a"]})
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
        profile = self.profile()
        bindings = profile["metric_bindings"]
        bindings["settlements"][0]["variable_primary_size"] = False
        bindings["components"][0]["variable_simultaneous_win_count"] = False
        bindings["components"][0]["variable_visible_step_reward"] = False
        bindings["continuous_settlements"][0]["variable_depth"] = False
        Draft202012Validator(load(ROOT / "assets/schemas/game-profile-metric-bindings.schema.json")).validate(profile)
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

    def test_profile_requires_p2_labels_and_trigger_threshold(self):
        schema = load(ROOT / "assets/schemas/game-profile-metric-bindings.schema.json")
        profile = self.profile()
        profile["metric_bindings"]["special_mechanics"][0].pop("result_state_names_zh")
        self.assertTrue(list(Draft202012Validator(schema).iter_errors(profile)))

        profile = self.profile()
        key = profile["metric_bindings"]["boards"][0]["key_symbol_profiles"][0]
        key["sample_filter"] = "untriggered_only"
        self.assertTrue(list(Draft202012Validator(schema).iter_errors(profile)))
        key["trigger_threshold"] = 3
        Draft202012Validator(schema).validate(profile)

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
        formal_path = self.nested_path("artifacts/04-alignment/formal_result.json")
        source_formal_path = self.nested_path("work/formal/fv0001/alignment_result.json")
        formal = {"task_id": "test-task"}
        write(formal_path, formal)
        write(source_formal_path, formal)
        source_runtime = self.directory("work/formal/fv0001/runtime")
        delivery_runtime = self.directory("交付物/runtime")
        runtime_paths, source_runtime_paths = {}, {}
        for name in ["game_core.json", "payout_config.json", "reel_config.json", "symbol_catalog.json"]:
            value = {"meta": {"version": "test-task"}} if name == "game_core.json" else {}
            source = source_runtime / name
            delivery = delivery_runtime / name
            self.created.extend([source, delivery])
            write(source, value)
            write(delivery, value)
            source_runtime_paths[name], runtime_paths[name] = source, delivery
        parameter_path = self.nested_path("work/candidate-freeze/candidate-1/parameter_record.json")
        parameters = [{"parameter_id": "weight", "runtime_path": "reel_config.json:weight", "value": 1}]
        write(parameter_path, {"complete_parameters": parameters})
        freeze_path = self.nested_path("work/candidate-freeze/candidate-1/freeze_manifest.json")
        write(freeze_path, {"candidate_id": "candidate-1", "runtime_bundle_sha256": "b" * 64})
        aligned_path = self.nested_path("artifacts/04-alignment/aligned_parameters.json")
        aligned = {
            "task_id": "test-task",
            "candidate_id": "candidate-1",
            "freeze_manifest_sha256": sha256_file(freeze_path),
            "parameter_record": {"path": "work/candidate-freeze/candidate-1/parameter_record.json", "sha256": sha256_file(parameter_path)},
            "runtime_bundle_sha256": "b" * 64,
            "parameters": parameters,
        }
        write(aligned_path, aligned)
        alignment_path = self.nested_path("artifacts/04-alignment/alignment_manifest.json")
        alignment_manifest = {
            "task_id": "test-task",
            "candidate_freezes": [{
                "candidate_id": "candidate-1",
                "path": "work/candidate-freeze/candidate-1/freeze_manifest.json",
                "sha256": sha256_file(freeze_path),
                "selected_for_formal": True,
            }],
            "formal_batches": [{
                "batch_id": "fv0001",
                "candidate_id": "candidate-1",
                "result": {"path": "work/formal/fv0001/alignment_result.json", "sha256": sha256_file(source_formal_path)},
                "promoted_to_artifact": True,
            }],
        }
        write(alignment_path, alignment_manifest)
        manifest_path = self.nested_path("artifacts/05-delivery/delivery_manifest.json")
        manifest = {
            "schema_version": "slot-alignment.delivery-manifest.v6",
            "report_contract_version": "slot-alignment.report.v6",
            "task_id": "test-task",
            "runtime_version": "test-task",
            "rtp_group": 1,
            "source_formal_result": {"batch_id": "fv0001", "path": "work/formal/fv0001/alignment_result.json", "sha256": sha256_file(source_formal_path)},
            "formal_result_sha256": sha256_file(formal_path),
            "alignment_manifest_sha256": sha256_file(alignment_path),
            "aligned_parameters_sha256": sha256_file(aligned_path),
            "runtime_files": [
                {"name": name, "source_path": f"work/formal/fv0001/runtime/{name}", "path": f"交付物/runtime/{name}", "sha256": sha256_file(runtime_paths[name])}
                for name in ["game_core.json", "payout_config.json", "reel_config.json", "symbol_catalog.json"]
            ],
            "checks": {
                "formal_source_matches_artifact": True,
                "formal_runtime_matches_delivery": True,
                "runtime_version_matches_task": True,
                "rtp_group_is_one": True,
                "aligned_parameters_match_freeze": True,
            },
            "generated_at": "2026-08-29T00:00:00+08:00",
        }
        write(manifest_path, manifest)
        args = ["--task-root", self.temp, "--formal-result", formal_path, "--alignment-manifest", alignment_path, "--aligned-parameters", aligned_path, "--runtime-dir", delivery_runtime, "--manifest", manifest_path]
        self.run_script("validate_delivery.py", *args)

        write(runtime_paths["game_core.json"], {"meta": {"version": "wrong-version"}})
        command = [sys.executable, str(ROOT / "scripts/validate_delivery.py"), *map(str, args)]
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

    def test_workspace_policy_is_closed(self):
        errors = []
        self.assertIsNotNone(validate_skill_contract(errors))
        self.assertEqual(errors, [])

    def test_shard_filename_must_match_index(self):
        shard_dir = self.directory("shards")
        path = shard_dir / "shard-000001.json"
        self.created.append(path)
        shard = {
            "schema_version": "slot-alignment.execution-shard.v6",
            "task_id": "test-task",
            "mode": "default",
            "rtp_group": 1,
            "phase": "BASELINE",
            "shard_index": 0,
            "entry_start": 0,
            "entry_count": 100000,
            "metric_contract_sha256": "a" * 64,
            "candidate_parameter_sha256": None,
            "runtime_bundle_sha256": "b" * 64,
            "script_bundle_sha256": "c" * 64,
            "base_seed": 0,
            "shard_seed": 1,
            "aggregate_measurements": {},
            "accumulator_checkpoint": {},
            "hash_scope": "canonical_json_without_output_sha256",
            "output_sha256": "0" * 64,
            "status": "completed",
        }
        shard["output_sha256"] = canonical_shard_sha256(shard)
        write(path, shard)
        errors = []
        validate_shards(shard_dir, errors, phase="BASELINE")
        self.assertTrue(any("分片文件名与shard_index不一致" in item for item in errors))

    def test_baseline_promotion_hash_mismatch_is_rejected(self):
        source, target = self.path("baseline-source.json"), self.path("baseline-target.json")
        write(source, {"value": 1})
        write(target, {"value": 2})
        errors = []
        validate_promoted_hash(source, target, "BASELINE测量", errors)
        self.assertIn("BASELINE测量晋级前后SHA-256不一致", errors)

    def test_formal_promotion_hash_mismatch_is_rejected(self):
        source, target = self.path("formal-source.json"), self.path("formal-target.json")
        write(source, {"value": 1})
        write(target, {"value": 2})
        errors = []
        validate_promoted_hash(source, target, "FORMAL结果", errors)
        self.assertIn("FORMAL结果晋级前后SHA-256不一致", errors)


if __name__ == "__main__":
    unittest.main()
