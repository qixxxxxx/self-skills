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
    _j_card_score,
    absolute_probability_error,
    evaluate_contract,
    grade_ratio,
    grade_score,
    joint_q99_tolerances,
    sha256_file,
    structural_wasserstein,
    total_variation,
    wasserstein_1d,
)
from compile_metric_contract import EVALUATION_POLICY_PATH, HARD_POLICY_PATH, LIBRARY_PATH, j_c_tolerance, n_c_tolerance, safe_id, subitems
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

    def test_formal_grade_boundaries(self):
        policy = load(ROOT / "assets/policies/alignment_evaluation_policy.json")
        grading = policy["formal_grading"]
        self.assertEqual(grading["hard_gate_pass_limit"], 1.0)
        for score, grade in [(100, "S"), (90, "S"), (89.999, "A"), (80, "A"), (79.999, "B"), (70, "B"), (69.999, "C"), (0, "C")]:
            self.assertEqual(grade_score(score, policy), grade)
        thresholds = grading["alignment_thresholds"]["P"]
        self.assertEqual(thresholds, {"S": 1.0, "A": 2.5, "B": 5.0, "C": 8.0})
        self.assertEqual(grade_ratio(8.0, thresholds), "C")
        self.assertEqual(grade_ratio(8.000000001, thresholds), "F")
        thresholds = grading["alignment_thresholds"]["B"]
        self.assertEqual(thresholds, {"S": 1.0, "A": 3.0, "B": 6.0, "C": 10.0})
        self.assertEqual(grade_ratio(10.0, thresholds), "C")
        self.assertEqual(grade_ratio(10.000000001, thresholds), "F")

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
        self.assertAlmostEqual(_j_card_score({"instances": half_group}, [{"score": 60}, {"score": 100}, {"score": 80}]), 75.0)
        dimensions = [
            {"aggregation": {"dimension_id": "primary_structure", "group_id": "ways", "mode": "mean_items", "role": "item"}},
            {"aggregation": {"dimension_id": "simultaneous_win_count", "group_id": "base", "mode": "mean_items", "role": "item"}},
            {"aggregation": {"dimension_id": "visible_step_reward", "group_id": "base", "mode": "mean_items", "role": "item"}},
        ]
        self.assertAlmostEqual(_j_card_score({"instances": dimensions}, [{"score": 80}, {"score": 60}, {"score": 100}]), 80.0)


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
                "features": [{"feature_id": "free-spin", "feature_type": "free_spin", "endogenous_entry": True}],
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
                "special_mechanics": [{"mechanic_id": "wild-multiplier", "result_states": ["not-occurred", "not-effective", "2x", "3x"], "inactive_state_ids": ["not-occurred", "not-effective"]}],
                "boards": [{
                    "board_scope_id": "base-initial",
                    "component_id": "base",
                    "visual_phase": "initial",
                    "rows": 2,
                    "columns": 2,
                    "variable_shape": True,
                    "symbols": ["a", "wild"],
                    "symbol_groups": [{"group_id": "regular", "role": "regular_other", "symbols": ["a"]}],
                    "key_symbols": ["wild"],
                    "spatial_symbols": ["wild"],
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
            record = {"value": 0.96 if card["card_id"] == "N1" else 0.2, "source": source, "base_tolerance": 0.01}
        elif method == "absolute_error":
            record = {"value": 2.0, "source": source}
        elif method == "total_variation":
            if card["card_id"] == "J2":
                value = {"1": 0.4, "2": 0.3, "3": 0.2, "4+": 0.1}
            elif card["card_id"] == "J3":
                value = {"0": 0.4, "1": 0.25, "2": 0.15, "3": 0.08, "4": 0.05, "5": 0.04, "6+": 0.03}
            else:
                value = {"not-occurred": 0.5, "not-effective": 0.2, "2x": 0.2, "3x": 0.1}
            record = {"value": value, "source": source}
        elif method == "wasserstein_1d":
            transform = facet.get("position_transform", "identity")
            record = {"value": {"0": 0.6, "1": 0.4}, "source": source, "distance": {"bin_positions": [0, 1], "position_transform": transform, **({"support_span": 1.0} if transform == "identity" else {})}}
        else:
            state_kind = extra.get("state_kind", "symbol_position_density")
            cells = [[0, 0]] if state_kind == "symbol_position_density" else [[0, 0], [0, 1], [1, 0], [1, 1]]
            record = {"value": {"board_shape": extra["board_shape"], "states": [{"cells": cells, "probability": 1.0}]}, "source": source}
        if card["category_id"] == "J":
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
        targets, tolerances = {}, {}
        bindings = profile["metric_bindings"]
        for card in library["cards"]:
            for facet in card["facets"]:
                for subitem, _scope, extra in subitems(card["card_id"], facet["facet_id"], bindings):
                    instance_id = f"{card['card_id']}.{facet['facet_id']}.{safe_id(subitem)}"
                    record = self.target_for(card, facet, extra)
                    if card["kind"] == "hard_gate" and "base_tolerance" not in record:
                        record["base_tolerance"] = 0.01
                    targets[instance_id] = record
                    if card["category_id"] in {"P", "B"}:
                        tolerances[instance_id] = 0.1
        profile_path, targets_path, joint_path, bindings_path, sample_plan_path, capabilities_path = [self.path(name) for name in ["profile.json", "targets.json", "joint.json", "bindings.json", "sample-plan.json", "runtime-capabilities.json"]]
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
        write(sample_plan_path, self.sample_plan({"P2.mechanic_result_state.wild-multiplier": 0.001}))
        write(capabilities_path, self.runtime_capabilities())
        return profile_path, targets_path, joint_path, bindings_path, sample_plan_path, capabilities_path

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
        profile, targets, joint, bindings, sample_plan, capabilities = self.build_inputs()
        contract_path = self.path("contract.json")
        self.run_script("compile_metric_contract.py", "--profile", profile, "--targets", targets, "--joint-tolerances", joint, "--bindings", bindings, "--sample-plan", sample_plan, "--runtime-capabilities", capabilities, "--output", contract_path)
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
        b1_ids = [item["instance_id"] for card in contract["cards"] if card["card_id"] == "B1" for item in card["instances"]]
        self.assertEqual(b1_ids, ["B1.symbol_group_density_per_board.base-initial.regular", "B1.key_symbol_count_per_board.base-initial.wild"])
        density = next(item for card in contract["cards"] if card["card_id"] == "B1" for item in card["instances"] if item["facet_id"] == "symbol_group_density_per_board")
        self.assertEqual(density["distance"]["support_span"], 1.0)
        b2_ids = [item["instance_id"] for card in contract["cards"] if card["card_id"] == "B2" for item in card["instances"]]
        self.assertEqual(b2_ids, ["B2.board_shape.base-initial", "B2.key_symbol_position_density.base-initial.wild"])
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
        self.assertEqual(result["summary"]["final_grade"], "S")
        self.assertEqual(result["summary"]["composite_score"], 100.0)
        self.assertEqual(result["summary"]["score_scope"], ["N"])
        self.assertEqual(result["summary"]["planned_score_scope"], ["N", "J", "P", "B"])
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
        profile, targets, joint, bindings, sample_plan, capabilities = self.build_inputs()
        data = load(targets)
        n1 = data["targets"]["N1.total_rtp.overall"]
        n1["source"].pop("confirmation_evidence_sha256")
        write(targets, data)
        command = [sys.executable, str(ROOT / "scripts/compile_metric_contract.py"), "--profile", str(profile), "--targets", str(targets), "--joint-tolerances", str(joint), "--bindings", str(bindings), "--sample-plan", str(sample_plan), "--runtime-capabilities", str(capabilities), "--output", str(self.path("invalid-contract-1.json"))]
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
        profile, targets, joint, bindings, sample_plan, capabilities = self.build_inputs()
        command = [sys.executable, str(ROOT / "scripts/compile_metric_contract.py"), "--profile", str(profile), "--targets", str(targets), "--joint-tolerances", str(joint), "--bindings", str(bindings), "--sample-plan", str(sample_plan), "--runtime-capabilities", str(capabilities), "--output", str(self.path("invalid-board-contract.json"))]

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
        self.assertIn("可见符号域未被symbol_groups和key_symbols覆盖", result.stderr)

        data = self.profile()
        data["metric_bindings"]["boards"][0]["component_id"] = "unknown"
        write(profile, data)
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("component_id不在components中", result.stderr)

    def test_win_groups_and_primary_axis_must_be_valid(self):
        profile, targets, joint, bindings, sample_plan, capabilities = self.build_inputs()
        command = [sys.executable, str(ROOT / "scripts/compile_metric_contract.py"), "--profile", str(profile), "--targets", str(targets), "--joint-tolerances", str(joint), "--bindings", str(bindings), "--sample-plan", str(sample_plan), "--runtime-capabilities", str(capabilities), "--output", str(self.path("invalid-j-contract.json"))]

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
