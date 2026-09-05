#!/usr/bin/env python3
import argparse
import hashlib
import json
import re
from copy import deepcopy
from pathlib import Path

from jsonschema import Draft202012Validator

from alignment import canonical_json_sha256, column_repeat_policy_errors, dump_json, finite_number, load_json, sha256_file


ROOT = Path(__file__).resolve().parents[1]
LIBRARY_PATH = ROOT / "references" / "指标目录" / "index.json"
HARD_POLICY_PATH = ROOT / "assets" / "policies" / "hard_gate_budget_policy.json"
EVALUATION_POLICY_PATH = ROOT / "assets" / "policies" / "alignment_evaluation_policy.json"
TARGET_EVIDENCE_POLICY_PATH = ROOT / "assets" / "policies" / "target_evidence_policy.json"
SAMPLE_POLICY_PATH = ROOT / "assets" / "policies" / "sample_execution_policy.json"


def safe_id(value):
    value = str(value).lower().replace("+", "plus")
    value = re.sub(r"[^a-z0-9_.:-]+", "-", value).strip("-.")
    if not value:
        raise ValueError("无法生成空子项ID")
    return value


def labeled_scope(scope, bindings):
    labels = {}
    maps = {
        "component": {item["component_id"]: item["name_zh"] for item in bindings["components"]},
        "feature": {item["feature_id"]: item["name_zh"] for item in bindings["features"]},
        "settlement": {item["settlement_id"]: item["name_zh"] for item in bindings["settlements"]},
        "continuous_settlement": {item["continuous_id"]: item["name_zh"] for item in bindings["continuous_settlements"]},
        "mechanic": {item["mechanic_id"]: item["name_zh"] for item in bindings["special_mechanics"]},
        "board": {item["board_scope_id"]: item["name_zh"] for item in bindings["boards"]},
    }
    for key, values in maps.items():
        if scope.get(key) in values:
            labels[key] = values[scope[key]]
    scope_names = {
        **maps["component"],
        **maps["feature"],
    }
    if scope.get("scope") in scope_names:
        labels["scope"] = scope_names[scope["scope"]]
    if "win_group" in scope:
        labels["win_group"] = next(
            (item["name_zh"] for item in bindings["win_groups"] if item["component_id"] == scope.get("component") and item["group_id"] == scope["win_group"]),
            scope["win_group"],
        )
    if "symbol_group" in scope:
        labels["symbol_group"] = next(
            (group["name_zh"] for board in bindings["boards"] if board["board_scope_id"] == scope.get("board") for group in board["symbol_groups"] if group["group_id"] == scope["symbol_group"]),
            scope["symbol_group"],
        )
    mechanic = next((item for item in bindings["special_mechanics"] if item["mechanic_id"] == scope.get("mechanic")), None)
    if mechanic:
        state_names = mechanic["result_state_names_zh"]
        if "state" in scope:
            labels["state"] = state_names.get(scope["state"], scope["state"])
        if "states" in scope:
            labels["states"] = {state: state_names.get(state, state) for state in scope["states"]}
    board = next((item for item in bindings["boards"] if item["board_scope_id"] == scope.get("board")), None)
    if board:
        labels["symbol_groups"] = {item["group_id"]: item["name_zh"] for item in board["symbol_groups"]}
    return {**scope, **({"labels_zh": labels} if labels else {})}


def subitems(card_id, facet_id, bindings):
    features = bindings["features"]
    settlements = bindings["settlements"]
    win_groups = bindings["win_groups"]
    continuous = bindings["continuous_settlements"]
    mechanics = bindings["special_mechanics"]
    boards = bindings["boards"]
    components = bindings["components"]
    component_map = {item["component_id"]: item for item in components}
    settlement_components = list(dict.fromkeys(item["component_id"] for item in settlements))
    if (card_id, facet_id) in {("N1", "total_rtp"), ("N2", "positive_return_rate"), ("N4", "return_ge_cost_rate")}:
        return [("overall", {"scope": "overall"}, {})]
    if (card_id, facet_id) == ("N3", "natural_trigger_rate"):
        return [(item["feature_id"], {"feature": item["feature_id"]}, {}) for item in features if item["endogenous_entry"]]
    if (card_id, facet_id) == ("N5", "return_sigma"):
        return [("overall", {"scope": "overall"}, {})] + [(scope, {"scope": scope}, {}) for scope in bindings["sigma_scopes"]]
    if (card_id, facet_id) == ("N6", "component_rtp"):
        return [(item["component_id"], {"component": item["component_id"]}, {}) for item in components]
    if (card_id, facet_id) == ("J1", "win_group_participation_rate"):
        return [(f"{item['component_id']}.{item['group_id']}", {
            "component": item["component_id"],
            "win_group": item["group_id"],
            "elements": item["elements"],
        }, {
            "budget_rule": "J1.participation",
            "aggregation": {"dimension_id": "participation", "group_id": item["component_id"], "mode": "mean_items", "role": "item"},
        }) for item in win_groups]
    if card_id == "J2" and facet_id in {"primary_structure_bin_rate", "primary_structure_distribution_shift"}:
        result = []
        for item in settlements:
            if not item["variable_primary_size"] or item.get("primary_size_evaluation_mode") != "categorical_distribution":
                continue
            aggregation = {"dimension_id": "primary_structure", "group_id": item["settlement_id"], "mode": "half_overall_half_items"}
            base_scope = {"component": item["component_id"], "settlement": item["settlement_id"], "primary_size_axis": item["primary_size_axis"]}
            if facet_id == "primary_structure_bin_rate":
                for bin_id in item["primary_size_bins"]:
                    result.append((f"{item['settlement_id']}.{bin_id}", {**base_scope, "bin": bin_id}, {
                        "budget_rule": "J2.primary_structure_categorical.bin",
                        "requires_bin_count": True,
                        "aggregation": {**aggregation, "role": "bin"},
                    }))
            else:
                result.append((item["settlement_id"], {**base_scope, "bins": item["primary_size_bins"]}, {
                    "budget_rule": "J2.primary_structure_categorical.overall",
                    "aggregation": {**aggregation, "role": "overall"},
                }))
        return result
    if card_id == "J2" and facet_id in {"primary_structure_mean", "primary_structure_p50", "primary_structure_p90"}:
        statistic = facet_id.rsplit("_", 1)[-1]
        return [(item["settlement_id"], {
            "component": item["component_id"],
            "settlement": item["settlement_id"],
            "primary_size_axis": item["primary_size_axis"],
            "natural_unit": item["primary_size_unit"],
            "statistic": statistic,
        }, {
            "budget_rule": f"J2.primary_structure_summary.{statistic}",
            "aggregation": {"dimension_id": "primary_structure", "group_id": item["settlement_id"], "mode": "mean_items", "role": "item"},
        }) for item in settlements if item["variable_primary_size"] and item.get("primary_size_evaluation_mode") == "summary_triplet"]
    if card_id == "J2" and facet_id in {"simultaneous_visible_win_count_bin_rate", "simultaneous_visible_win_count_distribution_shift"}:
        result = []
        for component in settlement_components:
            binding = component_map[component]
            if not binding["variable_simultaneous_win_count"]:
                continue
            bins = binding["simultaneous_win_count_bins"]
            aggregation = {"dimension_id": "simultaneous_win_count", "group_id": component, "mode": "half_overall_half_items"}
            if facet_id == "simultaneous_visible_win_count_bin_rate":
                for bin_id in bins:
                    result.append((f"{component}.{bin_id}", {"component": component, "bin": bin_id}, {
                        "budget_rule": "J2.simultaneous_win_count.bin",
                        "requires_bin_count": True,
                        "aggregation": {**aggregation, "role": "bin"},
                    }))
            else:
                result.append((component, {"component": component, "bins": bins}, {
                    "budget_rule": "J2.simultaneous_win_count.overall",
                    "aggregation": {**aggregation, "role": "overall"},
                }))
        return result
    if card_id == "J2" and facet_id in {"visible_step_reward_mean", "visible_step_reward_p50", "visible_step_reward_p90"}:
        statistic = facet_id.rsplit("_", 1)[-1]
        return [(component, {
            "component": component,
            "display_bet_basis": component_map[component]["display_bet_basis"],
            "minimum_visible_reward_unit": component_map[component]["minimum_visible_reward_unit"],
            "statistic": statistic,
        }, {
            "budget_rule": f"J2.visible_step_reward.{statistic}",
            "aggregation": {"dimension_id": "visible_step_reward", "group_id": component, "mode": "mean_items", "role": "item"},
        }) for component in settlement_components if component_map[component]["variable_visible_step_reward"]]
    if card_id == "J3" and facet_id in {"total_depth_bin_rate", "total_depth_distribution_shift"}:
        result = []
        bins = ["0", "1", "2", "3", "4", "5", "6+"]
        for item in continuous:
            if not item["variable_depth"]:
                continue
            aggregation = {"dimension_id": "depth", "group_id": item["continuous_id"], "mode": "half_overall_half_items"}
            base_scope = {"component": item["component_id"], "continuous_settlement": item["continuous_id"]}
            if facet_id == "total_depth_bin_rate":
                for bin_id in bins:
                    result.append((f"{item['continuous_id']}.{bin_id}", {**base_scope, "bin": bin_id}, {
                        "budget_rule": "J3.depth.bin",
                        "requires_bin_count": True,
                        "aggregation": {**aggregation, "role": "bin"},
                    }))
            else:
                result.append((item["continuous_id"], {**base_scope, "bins": bins}, {
                    "budget_rule": "J3.depth.overall",
                    "aggregation": {**aggregation, "role": "overall"},
                }))
        return result
    if card_id == "P1" and facet_id in {"entry_award_bin_rate", "entry_award_distribution_shift"}:
        result = []
        for item in features:
            if item["entry_award_evaluation_mode"] != "categorical_distribution":
                continue
            aggregation = {"dimension_id": item["feature_id"], "group_id": "entry_award", "mode": "half_overall_half_items"}
            base_scope = {"feature": item["feature_id"], "feature_type": item["feature_type"], "entry_award_unit": item["entry_award_unit"]}
            if facet_id == "entry_award_bin_rate":
                for bin_id in item["entry_award_bins"]:
                    result.append((f"{item['feature_id']}.{bin_id}", {**base_scope, "bin": bin_id}, {
                        "budget_rule": "P1.entry_award.bin",
                        "requires_bin_count": True,
                        "aggregation": {**aggregation, "role": "bin"},
                    }))
            else:
                result.append((item["feature_id"], {**base_scope, "bins": item["entry_award_bins"]}, {
                    "budget_rule": "P1.entry_award.overall",
                    "aggregation": {**aggregation, "role": "overall"},
                }))
        return result
    if card_id == "P1" and facet_id in {"feature_duration_mean", "feature_duration_p50", "feature_duration_p90"}:
        statistic = facet_id.rsplit("_", 1)[-1]
        return [(item["feature_id"], {
            "feature": item["feature_id"],
            "feature_type": item["feature_type"],
            "duration_unit": item["duration_unit"],
            "statistic": statistic,
        }, {
            "budget_rule": f"P1.duration.{statistic}",
            "aggregation": {"dimension_id": item["feature_id"], "group_id": "duration", "mode": "mean_items", "role": "item"},
        }) for item in features if item["duration_evaluation_mode"] == "summary_triplet"]
    if card_id == "P2" and facet_id in {"mechanic_result_bin_rate", "mechanic_result_distribution_shift"}:
        result = []
        for item in mechanics:
            if item["result_evaluation_mode"] != "categorical_distribution":
                continue
            aggregation = {"dimension_id": item["mechanic_id"], "group_id": "result", "mode": "half_overall_half_items"}
            base_scope = {
                "mechanic": item["mechanic_id"],
                "mechanic_family": item["mechanic_family"],
                "opportunity_unit": item["opportunity_unit"],
            }
            if facet_id == "mechanic_result_bin_rate":
                for state in item["result_states"]:
                    result.append((f"{item['mechanic_id']}.{state}", {**base_scope, "state": state}, {
                        "budget_rule": "P2.result.bin",
                        "requires_bin_count": True,
                        "aggregation": {**aggregation, "role": "bin"},
                    }))
            else:
                result.append((item["mechanic_id"], {**base_scope, "states": item["result_states"]}, {
                    "budget_rule": "P2.result.overall",
                    "aggregation": {**aggregation, "role": "overall"},
                }))
        return result
    if card_id == "B1" and facet_id in {"symbol_group_share_bin_rate", "symbol_group_composition_shift"}:
        result = []
        for board in boards:
            groups = board["symbol_groups"]
            aggregation = {"dimension_id": "b1-1", "group_id": f"{board['board_scope_id']}.group-composition", "mode": "half_overall_half_items"}
            base_scope = {"board": board["board_scope_id"], "component": board["component_id"], "visual_phase": board["visual_phase"]}
            if facet_id == "symbol_group_share_bin_rate":
                for group in groups:
                    result.append((f"{board['board_scope_id']}.{group['group_id']}", {**base_scope, "symbol_group": group["group_id"], "symbols": group["symbols"]}, {
                        "budget_rule": "B1.symbol_group_composition.bin",
                        "requires_bin_count": True,
                        "aggregation": {**aggregation, "role": "bin"},
                    }))
            else:
                result.append((board["board_scope_id"], {**base_scope, "groups": [item["group_id"] for item in groups]}, {
                    "budget_rule": "B1.symbol_group_composition.overall",
                    "aggregation": {**aggregation, "role": "overall"},
                }))
        return result
    if card_id == "B1" and facet_id in {"symbol_group_member_share_bin_rate", "symbol_group_member_distribution_shift"}:
        result = []
        for board in boards:
            base_scope = {"board": board["board_scope_id"], "component": board["component_id"], "visual_phase": board["visual_phase"]}
            for group in board["symbol_groups"]:
                if len(group["symbols"]) < 2:
                    continue
                aggregation = {"dimension_id": "b1-1", "group_id": f"{board['board_scope_id']}.member-balance.{group['group_id']}", "mode": "half_overall_half_items"}
                if facet_id == "symbol_group_member_share_bin_rate":
                    for symbol in group["symbols"]:
                        result.append((f"{board['board_scope_id']}.{group['group_id']}.{symbol}", {**base_scope, "symbol_group": group["group_id"], "symbol": symbol}, {
                            "budget_rule": "B1.symbol_group_member_balance.bin",
                            "requires_bin_count": True,
                            "aggregation": {**aggregation, "role": "bin"},
                        }))
                else:
                    result.append((f"{board['board_scope_id']}.{group['group_id']}", {**base_scope, "symbol_group": group["group_id"], "members": group["symbols"]}, {
                        "budget_rule": "B1.symbol_group_member_balance.overall",
                        "aggregation": {**aggregation, "role": "overall"},
                    }))
        return result
    if card_id == "B1" and facet_id in {"key_symbol_count_bin_rate", "key_symbol_count_distribution_shift"}:
        result = []
        for board in boards:
            for profile in board["key_symbol_profiles"]:
                aggregation = {"dimension_id": "b1-2", "group_id": f"{board['board_scope_id']}.{profile['symbol_id']}", "mode": "half_overall_half_items"}
                base_scope = {"board": board["board_scope_id"], "component": board["component_id"], "visual_phase": board["visual_phase"], "symbol": profile["symbol_id"], "sample_filter": profile["sample_filter"]}
                if profile.get("trigger_threshold") is not None:
                    base_scope["trigger_threshold"] = profile["trigger_threshold"]
                if facet_id == "key_symbol_count_bin_rate":
                    for bin_id in profile["count_bins"]:
                        result.append((f"{board['board_scope_id']}.{profile['symbol_id']}.{bin_id}", {**base_scope, "bin": bin_id}, {
                            "budget_rule": "B1.key_symbol_count.bin",
                            "requires_bin_count": True,
                            "aggregation": {**aggregation, "role": "bin"},
                        }))
                else:
                    result.append((f"{board['board_scope_id']}.{profile['symbol_id']}", {**base_scope, "bins": profile["count_bins"]}, {
                        "budget_rule": "B1.key_symbol_count.overall",
                        "aggregation": {**aggregation, "role": "overall"},
                    }))
        return result
    if card_id == "B1" and facet_id in {"aggregation_bin_rate", "aggregation_distribution_shift"}:
        result = []
        for board in boards:
            profile = board["aggregation_profile"]
            if profile is None:
                continue
            aggregation = {"dimension_id": "b1-3", "group_id": board["board_scope_id"], "mode": "half_overall_half_items"}
            base_scope = {"board": board["board_scope_id"], "component": board["component_id"], "visual_phase": board["visual_phase"], "aggregation_type": profile["aggregation_type"], "symbols": profile["symbol_ids"], "sample_filter": profile["sample_filter"]}
            if facet_id == "aggregation_bin_rate":
                for bin_id in profile["bins"]:
                    result.append((f"{board['board_scope_id']}.{bin_id}", {**base_scope, "bin": bin_id}, {
                        "budget_rule": "B1.aggregation.bin",
                        "requires_bin_count": True,
                        "aggregation": {**aggregation, "role": "bin"},
                    }))
            else:
                result.append((board["board_scope_id"], {**base_scope, "bins": profile["bins"]}, {
                    "budget_rule": "B1.aggregation.overall",
                    "aggregation": {**aggregation, "role": "overall"},
                }))
        return result
    if card_id == "B1" and facet_id == "column_repeat_violation_rate":
        result = []
        policies = {item["board_scope_id"]: item for item in bindings["column_repeat_policy"]["scopes"]}
        for board in boards:
            policy = policies[board["board_scope_id"]]
            if policy["applicability"] != "applicable_non_cascade":
                continue
            base_scope = {
                "board": board["board_scope_id"],
                "component": board["component_id"],
                "visual_phase": board["visual_phase"],
                "action_unit": "spin_or_respin_settlement",
                "cell_scope": "generated_this_action",
                "carried_cell_handling": "excluded",
                "minimum_comparable_cells": 2,
            }
            normal_rule = policy["normal_symbols"]
            if normal_rule["same_symbol_repeat_in_column"] == "forbidden":
                symbols = [symbol for group in board["symbol_groups"] for symbol in group["symbols"]]
                result.append((f"{board['board_scope_id']}.normal-symbols", {
                    **base_scope, "column_repeat_scope": "normal_symbols", "symbols": symbols,
                }, {"fixed_target": {
                    "target_status": "available", "value": 0.0, "deterministic_exact": True,
                    "source": {"method": f"{normal_rule['confirmed_by']}_exact_rule", "evidence_refs": normal_rule["evidence_refs"]},
                }}))
            for special_rule in policy["special_symbols"]:
                if special_rule["same_symbol_repeat_in_column"] != "forbidden":
                    continue
                result.append((f"{board['board_scope_id']}.special.{special_rule['symbol_id']}", {
                    **base_scope, "column_repeat_scope": "special_symbol", "symbol": special_rule["symbol_id"],
                }, {"fixed_target": {
                    "target_status": "available", "value": 0.0, "deterministic_exact": True,
                    "source": {"method": f"{special_rule['confirmed_by']}_exact_rule", "evidence_refs": special_rule["evidence_refs"]},
                }}))
        return result
    if card_id == "B2" and facet_id in {"reel_height_bin_rate", "reel_height_distribution_shift"}:
        result = []
        for board in boards:
            if board["shape_mode"] != "variable_reel_height":
                continue
            for reel in board["reel_height_profiles"]:
                aggregation = {"dimension_id": "reel_height", "group_id": f"{board['board_scope_id']}.{reel['reel_id']}", "mode": "half_overall_half_items"}
                base_scope = {"board": board["board_scope_id"], "component": board["component_id"], "visual_phase": board["visual_phase"], "reel": reel["reel_id"]}
                if facet_id == "reel_height_bin_rate":
                    for bin_id in reel["bins"]:
                        result.append((f"{board['board_scope_id']}.{reel['reel_id']}.{bin_id}", {**base_scope, "bin": bin_id}, {
                            "budget_rule": "B2.reel_height.bin",
                            "requires_bin_count": True,
                            "aggregation": {**aggregation, "role": "bin"},
                        }))
                else:
                    result.append((f"{board['board_scope_id']}.{reel['reel_id']}", {**base_scope, "bins": reel["bins"]}, {
                        "budget_rule": "B2.reel_height.overall",
                        "aggregation": {**aggregation, "role": "overall"},
                    }))
        return result
    if card_id == "B2" and facet_id in {"active_cell_count_mean", "active_cell_count_p50", "active_cell_count_p90"}:
        statistic = facet_id.rsplit("_", 1)[-1]
        return [(board["board_scope_id"], {"board": board["board_scope_id"], "component": board["component_id"], "visual_phase": board["visual_phase"], "statistic": statistic}, {
            "budget_rule": f"B2.active_cell_count.{statistic}",
            "aggregation": {"dimension_id": "active_cell_count", "group_id": board["board_scope_id"], "mode": "mean_items", "role": "item"},
        }) for board in boards if board["shape_mode"] == "variable_reel_height"]
    if card_id == "B2" and facet_id in {"board_unevenness_mean", "board_unevenness_p90"}:
        statistic = facet_id.rsplit("_", 1)[-1]
        return [(board["board_scope_id"], {"board": board["board_scope_id"], "component": board["component_id"], "visual_phase": board["visual_phase"], "statistic": statistic}, {
            "budget_rule": f"B2.unevenness.{statistic}",
            "aggregation": {"dimension_id": "unevenness", "group_id": board["board_scope_id"], "mode": "mean_items", "role": "item"},
        }) for board in boards if board["shape_mode"] == "variable_reel_height"]
    return []


def distance_contract(facet, target_record, extra):
    result = {"method": facet["distance_method"]}
    result.update(target_record.get("distance", {}))
    return result


def target_evidence_threshold(card_id, facet_id, scope, policy):
    if card_id == "P2":
        threshold = dict(policy["p2_thresholds_by_opportunity_unit"][scope["opportunity_unit"]])
    else:
        threshold = dict(policy["metric_thresholds"][card_id])
    threshold.update(policy["facet_overrides"].get(f"{card_id}.{facet_id}", {}))
    return threshold


def classify_target_evidence(card, facet, scope, extra, target_record, policy):
    source_method = target_record.get("source", {}).get("method")
    threshold = target_evidence_threshold(card["card_id"], facet["facet_id"], scope, policy)
    exact = source_method in policy["rules"]["exact_sources_without_sample_gate"] or target_record.get("deterministic_exact") is True
    if exact:
        return "active", {
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
        }, None

    sample_count = target_record.get("sample_count")
    if not isinstance(sample_count, int) or isinstance(sample_count, bool):
        raise SystemExit(f"{card['card_id']}.{facet['facet_id']}原版目标必须记录整数sample_count")
    target_status = target_record["target_status"]
    event_count = target_record.get("event_count")
    minimum_event = threshold.get("minimum_event_count")
    recommended_event = threshold.get("recommended_event_count")
    if minimum_event is not None and (not isinstance(event_count, int) or isinstance(event_count, bool)):
        raise SystemExit(f"{card['card_id']}.{facet['facet_id']}必须记录整数event_count")
    bucket_count = target_record.get("bucket_count")
    bin_policy = policy["categorical_bin_thresholds"]
    minimum_bucket = bin_policy["minimum_observed_count"] if extra.get("requires_bin_count") else None
    recommended_bucket = bin_policy["recommended_observed_count"] if extra.get("requires_bin_count") else None
    if minimum_bucket is not None and (not isinstance(bucket_count, int) or isinstance(bucket_count, bool)):
        raise SystemExit(f"{card['card_id']}.{facet['facet_id']}分布档位必须记录整数bucket_count")

    evidence = {
        "classification": "low",
        "sample_count": sample_count,
        "minimum_usable_count": threshold["minimum_sample"],
        "recommended_count": threshold["recommended_sample"],
        "event_count": event_count,
        "minimum_event_count": minimum_event,
        "recommended_event_count": recommended_event,
        "bucket_count": bucket_count,
        "minimum_bucket_count": minimum_bucket,
        "recommended_bucket_count": recommended_bucket,
    }
    if target_status == "no_evidence":
        return "observe_no_evidence", evidence, "原版有效分母为0，无法生成可靠目标，转为观察项"

    gaps = []
    if sample_count < threshold["minimum_sample"]:
        gaps.append(f"有效样本{sample_count}<{threshold['minimum_sample']}")
    if minimum_event is not None and event_count < minimum_event:
        gaps.append(f"实际事件{event_count}<{minimum_event}")
    if minimum_bucket is not None and bucket_count < minimum_bucket:
        gaps.append(f"档位计数{bucket_count}<{minimum_bucket}")
    if gaps:
        return "observe_low_sample", evidence, "；".join(gaps) + "，低于原版证据最低可用线"

    normal = sample_count >= threshold["recommended_sample"]
    if recommended_event is not None:
        normal = normal and event_count >= recommended_event
    if recommended_bucket is not None:
        normal = normal and bucket_count >= recommended_bucket
    evidence["classification"] = "normal" if normal else "low"
    return "active", evidence, None


def n_c_budget(card_id, target, scope, bindings, policy):
    rule = policy["c_budget_rules"][card_id]
    method = rule["method"]
    if method == "fixed_absolute":
        return float(rule["value"])
    if method == "target_relative_clamped":
        value = abs(float(target)) * float(rule["relative"])
        return min(max(value, float(rule["minimum"])), float(rule["maximum"]))
    if method == "target_relative_by_rarity":
        target = abs(float(target))
        relative = rule["rare_relative"] if target < float(rule["rare_target_below"]) else rule["regular_relative"]
        return target * float(relative)
    if method == "scope_relative":
        scope_id = scope.get("scope")
        feature_ids = {item["feature_id"] for item in bindings["features"]}
        key = "overall" if scope_id == "overall" else ("feature" if scope_id in feature_ids else "non_feature")
        return float(rule[key])
    raise ValueError(f"{card_id}不支持的C级玩家预算规则: {method}")


def _is_feature_component(component_id, bindings):
    return component_id in {item["feature_id"] for item in bindings["features"]}


def _clamped_relative(target, rule):
    value = abs(float(target)) * float(rule["relative"])
    return min(max(value, float(rule["minimum"])), float(rule["maximum"]))


def j_c_budget(target, scope, extra, bindings, policy):
    rules = policy["j_player_budget_rules"]
    rule_id = extra["budget_rule"]
    feature = _is_feature_component(scope.get("component"), bindings)
    scene = "feature" if feature else "base"
    if rule_id == "J1.participation":
        rule = rules["J1"][scene]
        target = abs(float(target))
        floor = min(target, float(rule["ordinary_floor"]))
        return min(max(target * float(rule["relative"]), floor), float(rule["maximum"]))
    if rule_id.startswith("J2.primary_structure_categorical."):
        config = rules["J2"]["primary_structure_categorical"]
        return float(config[f"{scene}_overall"]) if rule_id.endswith("overall") else _clamped_relative(target, config[f"{scene}_bin"])
    if rule_id.startswith("J2.primary_structure_summary."):
        statistic = rule_id.rsplit(".", 1)[-1]
        relative = float(rules["J2"]["primary_structure_summary"][scene][f"{statistic}_relative"])
        return max(abs(float(target)) * relative, float(scope["natural_unit"]))
    if rule_id.startswith("J2.simultaneous_win_count."):
        config = rules["J2"]["simultaneous_win_count"]
        return float(config[f"{scene}_overall"]) if rule_id.endswith("overall") else _clamped_relative(target, config[f"{scene}_bin"])
    if rule_id.startswith("J2.visible_step_reward."):
        statistic = rule_id.rsplit(".", 1)[-1]
        relative = float(rules["J2"]["visible_step_reward"][scene][f"{statistic}_relative"])
        return max(abs(float(target)) * relative, float(scope["minimum_visible_reward_unit"]))
    if rule_id.startswith("J3.depth."):
        config = rules["J3"]
        return float(config[f"{scene}_overall"]) if rule_id.endswith("overall") else _clamped_relative(target, config[f"{scene}_bin"])
    raise ValueError(f"J类不支持的C级玩家预算规则: {rule_id}")


def p_c_budget(target, extra, policy):
    rules = policy["p_player_budget_rules"]
    rule_id = extra["budget_rule"]
    if rule_id == "P1.entry_award.bin":
        rule = rules["P1"]["entry_award"]["bin"]
        target = abs(float(target))
        floor = min(target, float(rule["ordinary_floor"]))
        return min(max(target * float(rule["relative"]), floor), float(rule["maximum"]))
    if rule_id == "P1.entry_award.overall":
        return float(rules["P1"]["entry_award"]["overall"])
    if rule_id.startswith("P1.duration."):
        statistic = rule_id.rsplit(".", 1)[-1]
        rule = rules["P1"]["duration"][statistic]
        return max(abs(float(target)) * float(rule["relative"]), float(rule["minimum_actions"]))
    if rule_id == "P2.result.bin":
        rule = rules["P2"]["result_bin"]
        target = abs(float(target))
        floor = min(target, float(rule["ordinary_floor"]))
        return min(max(target * float(rule["relative"]), floor), float(rule["maximum"]))
    if rule_id == "P2.result.overall":
        return float(rules["P2"]["overall"])
    raise ValueError(f"P类不支持的C级玩家预算规则: {rule_id}")


def _rare_clamped_relative(target, rule):
    target = abs(float(target))
    floor = min(target, float(rule["ordinary_floor"]))
    return min(max(target * float(rule["relative"]), floor), float(rule["maximum"]))


def b_c_budget(target, extra, policy):
    rules = policy["b_player_budget_rules"]
    rule_id = extra["budget_rule"]
    parts = rule_id.split(".")
    if parts[-1] == "overall":
        return float(rules[parts[0]][parts[1]]["overall"])
    if parts[-1] == "bin":
        return _rare_clamped_relative(target, rules[parts[0]][parts[1]]["bin"])
    statistic = parts[-1]
    rule = rules[parts[0]][parts[1]][statistic]
    minimum_key = "minimum_cells" if parts[1] == "active_cell_count" else "minimum_levels"
    return max(abs(float(target)) * float(rule["relative"]), float(rule[minimum_key]))


def contract_digest(contract):
    clone = deepcopy(contract)
    clone["hashes"]["contract_sha256"] = "0" * 64
    raw = json.dumps(clone, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def main():
    parser = argparse.ArgumentParser(description="编译slot-alignment 7.0轻量指标合同")
    parser.add_argument("--preflight", required=True)
    parser.add_argument("--source-summary", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    preflight = load_json(args.preflight)
    source_summary = load_json(args.source_summary)
    profile = preflight["game_profile"]
    targets = source_summary.get("targets", {})
    sample_plan = preflight["sample_plan"]
    library = load_json(LIBRARY_PATH)
    hard_policy = load_json(HARD_POLICY_PATH)
    evaluation_policy = load_json(EVALUATION_POLICY_PATH)
    target_evidence_policy = load_json(TARGET_EVIDENCE_POLICY_PATH)
    sample_policy = load_json(SAMPLE_POLICY_PATH)
    for schema_name, value in [
        ("preflight.schema.json", preflight),
        ("source-summary.schema.json", source_summary),
        ("target-evidence-policy.schema.json", target_evidence_policy),
    ]:
        Draft202012Validator(load_json(ROOT / "assets/schemas" / schema_name)).validate(value)
    if source_summary["task_id"] != preflight["task_id"]:
        raise SystemExit("source_summary.task_id与preflight不一致")
    n1_target = targets.get("N1.total_rtp.overall", {})
    if n1_target.get("value") != preflight["target_rtp"]["value"]:
        raise SystemExit("N1目标与preflight中用户确认的唯一RTP不一致")
    calibration = sample_plan["calibration"]
    tiers = [value for value in [calibration.get("probe"), calibration["screen"], calibration["refine"], calibration["final"]] if value is not None]
    if tiers != sorted(tiers):
        raise SystemExit("候选样本阶梯必须按累计样本递增")
    formal = sample_plan["formal"]
    if formal["selected_paid_entry_count"] not in formal["tiers"]:
        raise SystemExit("FORMAL初始样本数必须来自用户确认的检查点")
    if formal["tier_role"] != "initial_checkpoints_not_upper_limit" or formal["maximum_paid_entry_count"] is not None:
        raise SystemExit("FORMAL检查点不得作为固定样本上限")
    if (
        formal["insufficient_sample_action"] != "extend_same_formal_attempt"
        or formal["extension_rule"] != "double_cumulative_paid_entries_until_all_active_instances_decidable"
        or formal["extension_uses_same_seed_stream"] is not True
        or formal["extension_requires_user_confirmation"] is not False
    ):
        raise SystemExit("FORMAL样本不足时必须沿同一正式seed序列自动扩展到可判定")
    parameter_authority = preflight["parameter_authority"]
    invalid_parameters = [
        item["parameter_id"]
        for item in parameter_authority["parameters"]
        if item["authorization"] == "authorized" and item["script_support"] != "supported"
    ]
    if invalid_parameters:
        raise SystemExit(f"授权参数未被认证脚本支持: {invalid_parameters}")
    bindings_file = {
        "task_id": preflight["task_id"],
        "mode": preflight["mode"],
        "contract_version": "7.0.0",
        "runtime_bundle_sha256": preflight["runtime"]["bundle_sha256"],
        "original_evidence_sha256": source_summary["source_bundle_sha256"],
        "script_sha256": preflight["certified_script"]["sha256"],
        "game_profile_sha256": canonical_json_sha256(preflight["game_profile"]),
        "parameter_authority_sha256": canonical_json_sha256(parameter_authority),
    }
    repeat_errors = column_repeat_policy_errors(profile)
    if repeat_errors:
        raise SystemExit("；".join(repeat_errors))
    bindings = deepcopy(profile["metric_bindings"])
    bindings["column_repeat_policy"] = deepcopy(profile["column_repeat_policy"])
    component_ids = [item["component_id"] for item in bindings["components"]]
    component_set = set(component_ids)
    if len(component_ids) != len(component_set):
        raise SystemExit("components.component_id重复")
    feature_ids = [item["feature_id"] for item in bindings["features"]]
    if len(feature_ids) != len(set(feature_ids)):
        raise SystemExit("features.feature_id重复")
    invalid_sigma_scopes = set(bindings["sigma_scopes"]) - (component_set | set(feature_ids))
    if "overall" in bindings["sigma_scopes"] or invalid_sigma_scopes:
        raise SystemExit(f"sigma_scopes只能引用组件或Feature且不得重复overall: {sorted(invalid_sigma_scopes | ({'overall'} & set(bindings['sigma_scopes'])))}")
    for feature in bindings["features"]:
        entry_mode = feature["entry_award_evaluation_mode"]
        if entry_mode == "categorical_distribution":
            if not feature.get("entry_award_unit") or not feature.get("entry_award_bins"):
                raise SystemExit(f"{feature['feature_id']}可变入场奖励必须冻结单位和档位")
        elif feature.get("entry_award_bins"):
            raise SystemExit(f"{feature['feature_id']}固定或不适用的入场奖励不得配置分布档位")
    settlement_ids = [item["settlement_id"] for item in bindings["settlements"]]
    if len(settlement_ids) != len(set(settlement_ids)):
        raise SystemExit("settlements.settlement_id重复")
    primary_axes = {
        "payline": "matched_reels",
        "ways": "ways",
        "count_pay": "symbol_count",
        "cluster": "cluster_cells",
        "full_screen": "cleared_cells",
        "other": "custom",
    }
    elements_by_component = {component: set() for component in component_ids}
    settlement_components = set()
    for settlement in bindings["settlements"]:
        component = settlement["component_id"]
        if component not in component_set:
            raise SystemExit(f"{settlement['settlement_id']} component_id不在components中")
        settlement_components.add(component)
        elements_by_component[component].update(settlement["elements"])
        expected_axis = primary_axes[settlement["settlement_type"]]
        if settlement["primary_size_axis"] != expected_axis:
            raise SystemExit(f"{settlement['settlement_id']} primary_size_axis必须为{expected_axis}")
        if settlement["variable_primary_size"]:
            mode = settlement.get("primary_size_evaluation_mode")
            if mode not in {"categorical_distribution", "summary_triplet"}:
                raise SystemExit(f"{settlement['settlement_id']}必须冻结primary_size_evaluation_mode")
            if mode == "categorical_distribution" and not settlement.get("primary_size_bins"):
                raise SystemExit(f"{settlement['settlement_id']}自然档位模式必须冻结primary_size_bins")
            if mode == "summary_triplet" and not finite_number(settlement.get("primary_size_unit")):
                raise SystemExit(f"{settlement['settlement_id']}三值模式必须冻结primary_size_unit")
    for component in bindings["components"]:
        if component["component_id"] not in settlement_components and (component["variable_simultaneous_win_count"] or component["variable_visible_step_reward"]):
            raise SystemExit(f"{component['component_id']}没有结算，不得声明可变J2指标")
        if component["variable_simultaneous_win_count"] and not component.get("simultaneous_win_count_bins"):
            raise SystemExit(f"{component['component_id']}必须冻结simultaneous_win_count_bins")
        if component["variable_visible_step_reward"] and not finite_number(component.get("minimum_visible_reward_unit")):
            raise SystemExit(f"{component['component_id']}必须冻结minimum_visible_reward_unit")
    continuous_ids = [item["continuous_id"] for item in bindings["continuous_settlements"]]
    if len(continuous_ids) != len(set(continuous_ids)):
        raise SystemExit("continuous_settlements.continuous_id重复")
    for item in bindings["continuous_settlements"]:
        if item["component_id"] not in settlement_components:
            raise SystemExit(f"{item['continuous_id']} component_id必须引用存在结算的组件")
    groups_by_component = {component: [] for component in component_ids}
    for group in bindings["win_groups"]:
        if group["component_id"] not in component_set:
            raise SystemExit(f"{group['group_id']} component_id不在components中")
        groups_by_component[group["component_id"]].append(group)
    for component, elements in elements_by_component.items():
        groups = groups_by_component[component]
        if not elements:
            if groups:
                raise SystemExit(f"{component}没有派奖元素，不得配置win_groups")
            continue
        if len(elements) == 1:
            if groups:
                raise SystemExit(f"{component}只有一个派奖元素，不得生成常量win_groups")
            continue
        if not 2 <= len(groups) <= 5:
            raise SystemExit(f"{component}必须冻结2至5个互斥win_groups")
        group_ids = [item["group_id"] for item in groups]
        grouped = [element for item in groups for element in item["elements"]]
        if len(group_ids) != len(set(group_ids)):
            raise SystemExit(f"{component} win_groups.group_id重复")
        if len(grouped) != len(set(grouped)):
            raise SystemExit(f"{component} win_groups之间存在重复元素")
        unknown = set(grouped) - elements
        if unknown:
            raise SystemExit(f"{component} win_groups元素不在settlements中: {sorted(unknown)}")
        uncovered = elements - set(grouped)
        if uncovered:
            raise SystemExit(f"{component}派奖元素未被win_groups覆盖: {sorted(uncovered)}")
    for mechanic in bindings["special_mechanics"]:
        if set(mechanic["result_state_names_zh"]) != set(mechanic["result_states"]):
            raise SystemExit(f"{mechanic['mechanic_id']} result_state_names_zh必须完整对应result_states")
        unknown = set(mechanic["inactive_state_ids"]) - set(mechanic["result_states"])
        if unknown:
            raise SystemExit(f"{mechanic['mechanic_id']} inactive_state_ids不在result_states中: {sorted(unknown)}")
        if mechanic["result_evaluation_mode"] == "categorical_distribution":
            if len(mechanic["result_states"]) < 2:
                raise SystemExit(f"{mechanic['mechanic_id']}可变机制结果至少需要两个玩家可见状态")
            if not mechanic["guaranteed_resolution"] and not mechanic["inactive_state_ids"]:
                raise SystemExit(f"{mechanic['mechanic_id']}非必然机制必须包含没发生或没生效状态")
        elif len(mechanic["result_states"]) != 1 or mechanic["inactive_state_ids"]:
            raise SystemExit(f"{mechanic['mechanic_id']}固定机制必须只有一个结果且不得配置无效状态")
    board_keys = [(item["component_id"], item["visual_phase"]) for item in bindings["boards"]]
    if len(board_keys) != len(set(board_keys)):
        raise SystemExit("每个组件的initial/cascade_visible正式盘面只能各有一个")
    initial_components = {item["component_id"] for item in bindings["boards"] if item["visual_phase"] == "initial"}
    continuous_components = {item["component_id"] for item in bindings["continuous_settlements"]}
    for board in bindings["boards"]:
        if board["component_id"] not in component_set:
            raise SystemExit(f"{board['board_scope_id']} component_id不在components中")
        if board["visual_phase"] == "cascade_visible" and board["component_id"] not in continuous_components:
            raise SystemExit(f"{board['board_scope_id']}没有连续结算，不得声明cascade_visible盘面")
        if board["visual_phase"] == "cascade_visible" and board["component_id"] not in initial_components:
            raise SystemExit(f"{board['board_scope_id']}声明cascade_visible前必须先冻结同组件initial盘面")
        symbols = set(board["symbols"])
        key_profiles = board["key_symbol_profiles"]
        key_symbols = {item["symbol_id"] for item in key_profiles}
        if len(key_symbols) != len(key_profiles):
            raise SystemExit(f"{board['board_scope_id']} key_symbol_profiles.symbol_id重复")
        group_ids = [item["group_id"] for item in board["symbol_groups"]]
        grouped = [symbol for item in board["symbol_groups"] for symbol in item["symbols"]]
        if len(group_ids) != len(set(group_ids)):
            raise SystemExit(f"{board['board_scope_id']} symbol_groups.group_id重复")
        if len(grouped) != len(set(grouped)):
            raise SystemExit(f"{board['board_scope_id']}视觉符号组之间存在重复符号")
        unknown = (set(grouped) | key_symbols) - symbols
        if unknown:
            raise SystemExit(f"{board['board_scope_id']}画像符号不在symbols中: {sorted(unknown)}")
        if set(grouped) & key_symbols:
            raise SystemExit(f"{board['board_scope_id']}普通符号组不得与关键符号重叠")
        uncovered = symbols - set(grouped) - key_symbols
        if uncovered:
            raise SystemExit(f"{board['board_scope_id']}可见符号域未被symbol_groups和key_symbol_profiles覆盖: {sorted(uncovered)}")
        aggregation = board["aggregation_profile"]
        if aggregation is not None:
            aggregation_symbols = set(aggregation["symbol_ids"])
            if not aggregation_symbols <= set(grouped):
                raise SystemExit(f"{board['board_scope_id']}聚集指标只能使用普通符号组成员")
        reel_profiles = board["reel_height_profiles"]
        reel_ids = [item["reel_id"] for item in reel_profiles]
        if len(reel_ids) != len(set(reel_ids)):
            raise SystemExit(f"{board['board_scope_id']} reel_height_profiles.reel_id重复")
        if board["shape_mode"] == "variable_reel_height" and len(reel_profiles) != board["columns"]:
            raise SystemExit(f"{board['board_scope_id']}可变卷轴高度必须逐列冻结高度档位")
    if bindings_file["game_profile_sha256"] != canonical_json_sha256(profile):
        raise SystemExit("合同绑定的game_profile_sha256与当前画像不一致")
    pending, missing = [], []
    used_targets = set()
    for card in library["cards"]:
        for facet in card["facets"]:
            for subitem_id, scope, extra in subitems(card["card_id"], facet["facet_id"], bindings):
                instance_id = f"{card['card_id']}.{facet['facet_id']}.{safe_id(subitem_id)}"
                target_record = targets.get(instance_id)
                fixed_target = extra.get("fixed_target")
                if fixed_target is not None and target_record is not None:
                    raise SystemExit(f"{instance_id}由开工确认生成，不得在source_summary重复提供")
                if fixed_target is not None:
                    target_record = fixed_target
                elif target_record is None:
                    missing.append(instance_id)
                    continue
                else:
                    used_targets.add(instance_id)
                target_source = target_record.get("source", {})
                target_method = target_source.get("method")
                if card["card_id"] == "N1":
                    if target_record["target_status"] != "available":
                        raise SystemExit("N1目标不得标记为无证据")
                    if target_method != "user_confirmed_exact_rtp":
                        raise SystemExit("N1目标必须由用户直接提供或明确确认")
                    if target_source.get("confirmation_type") not in {"provided_by_user", "confirmed_by_user"}:
                        raise SystemExit("N1缺少有效用户确认类型")
                    if not re.fullmatch(r"[a-f0-9]{64}", str(target_source.get("confirmation_evidence_sha256", ""))):
                        raise SystemExit("N1缺少用户确认记录SHA-256")
                    target_value = target_record.get("value")
                    if not finite_number(target_value) or not 0 < float(target_value) <= 1:
                        raise SystemExit("N1目标必须是(0,1]内的唯一数值，禁止区间")
                if card["card_id"] == "N6" and target_method != "original_component_share_mapped_to_user_confirmed_total_rtp":
                    raise SystemExit("N6目标必须按原版组件占比映射用户确认总RTP")
                decision, target_evidence, reason = classify_target_evidence(card, facet, scope, extra, target_record, target_evidence_policy)
                if decision == "active":
                    if card["card_id"] == "J1" and (not finite_number(target_record.get("value")) or not 0 < float(target_record["value"]) < 1):
                        raise SystemExit(f"{instance_id}活动J1参与率必须在(0,1)内")
                    if card["category_id"] in {"P", "B"} and extra.get("requires_bin_count") and (not finite_number(target_record.get("value")) or not 0 < float(target_record["value"]) < 1):
                        raise SystemExit(f"{instance_id}活动档位占比必须在(0,1)内")
                    if facet["facet_id"].startswith("feature_duration_") and (not finite_number(target_record.get("value")) or float(target_record["value"]) <= 0):
                        raise SystemExit(f"{instance_id}玩法长度目标必须大于0")
                pending.append({
                    "card": card,
                    "facet": facet,
                    "subitem_id": safe_id(subitem_id),
                    "scope": scope,
                    "extra": extra,
                    "instance_id": instance_id,
                    "target_record": target_record,
                    "decision": decision,
                    "target_evidence": target_evidence,
                    "reason_zh": reason,
                })
    if missing:
        raise SystemExit("缺少目标或显式无证据记录: " + ", ".join(sorted(missing)))
    extra_targets = set(targets) - used_targets
    if extra_targets:
        raise SystemExit(f"存在未绑定的目标: {sorted(extra_targets)}")

    incomplete_groups = set()
    for item in pending:
        aggregation = item["extra"].get("aggregation")
        if (
            item["decision"] != "active"
            and aggregation
            and aggregation["mode"] == "half_overall_half_items"
            and aggregation["role"] == "bin"
        ):
            incomplete_groups.add((item["card"]["card_id"], aggregation["dimension_id"], aggregation["group_id"]))
    for item in pending:
        aggregation = item["extra"].get("aggregation")
        key = (item["card"]["card_id"], aggregation["dimension_id"], aggregation["group_id"]) if aggregation else None
        if key in incomplete_groups and aggregation["role"] == "overall":
            item["decision"] = "observe_distribution_group"
            item["reason_zh"] = "同一分布组存在证据不足档位，无法正式评价完整分布；证据达标档位仍单独评价"

    cards, observational = [], []
    for card in library["cards"]:
        expected = [item for item in pending if item["card"]["card_id"] == card["card_id"]]
        instances = []
        for item in expected:
            target_record, scope, extra = item["target_record"], item["scope"], item["extra"]
            if item["decision"] != "active":
                observational.append({
                    "instance_id": item["instance_id"],
                    "card_id": card["card_id"],
                    "facet_id": item["facet"]["facet_id"],
                    "subitem_id": item["subitem_id"],
                    "scope": labeled_scope(scope, bindings),
                    "sample_unit": item["facet"]["sample_unit"],
                    "target_source": target_record["source"],
                    "target": target_record["value"],
                    "decision": item["decision"],
                    "target_evidence": item["target_evidence"],
                    "reason_zh": item["reason_zh"],
                })
                continue
            if card["card_id"] == "N1":
                budget = n_c_budget(card["card_id"], target_record["value"], scope, bindings, hard_policy)
                c_budget = {"source": "hard_gate_player_budget", "value": budget}
            elif target_record.get("deterministic_exact"):
                c_budget = {"source": "deterministic_exact", "value": 0.0}
            elif card["kind"] == "hard_gate":
                budget = n_c_budget(card["card_id"], target_record["value"], scope, bindings, hard_policy)
                c_budget = {"source": "hard_gate_player_budget", "value": budget}
            elif card["category_id"] == "J":
                budget = j_c_budget(target_record["value"], scope, extra, bindings, evaluation_policy)
                c_budget = {"source": "j_player_visible_budget", "value": budget}
            elif card["category_id"] == "P":
                budget = p_c_budget(target_record["value"], extra, evaluation_policy)
                c_budget = {"source": "p_player_visible_budget", "value": budget}
            elif card["category_id"] == "B":
                budget = b_c_budget(target_record["value"], extra, evaluation_policy)
                c_budget = {"source": "b_player_visible_budget", "value": budget}
            else:
                raise SystemExit(f"{item['instance_id']}没有可用的C级通过值规则")
            instance = {
                "instance_id": item["instance_id"],
                "facet_id": item["facet"]["facet_id"],
                "subitem_id": item["subitem_id"],
                "scope": labeled_scope(scope, bindings),
                "sample_unit": item["facet"]["sample_unit"],
                "measurement": item["facet"]["measurement"],
                "target_source": target_record["source"],
                "target": target_record["value"],
                "target_evidence": item["target_evidence"],
                "distance": distance_contract(item["facet"], target_record, extra),
                "c_budget": c_budget,
                "status": "active",
            }
            if extra.get("aggregation"):
                instance["aggregation"] = extra["aggregation"]
            instances.append(instance)
        cards.append({
            "card_id": card["card_id"],
            "name_zh": card["name_zh"],
            "category_id": card["category_id"],
            "kind": card["kind"],
            "status": "active" if instances else ("观察" if expected else "不适用"),
            "instances": instances,
        })
    active_count = sum(len(card["instances"]) for card in cards)
    coverage = {
        "status": "有限" if observational else "完整",
        "expected_instance_count": len(pending),
        "active_instance_count": active_count,
        "observational_instance_count": len(observational),
        "active_low_sample_instance_count": sum(item["target_evidence"]["classification"] == "low" for card in cards for item in card["instances"]),
        "observational_instances": observational,
    }
    audits = [{
        "audit_id": item["audit_id"],
        "name_zh": item["name_zh"],
        "source_cards": item["source_cards"],
        "measurement": ",".join(item["includes"]),
        "required": True,
    } for item in library["audits"]]
    hashes = {key: bindings_file[key] for key in ["runtime_bundle_sha256", "original_evidence_sha256", "script_sha256", "game_profile_sha256", "parameter_authority_sha256"]}
    hashes["preflight_sha256"] = sha256_file(args.preflight)
    hashes["source_summary_sha256"] = sha256_file(args.source_summary)
    hashes["sample_plan_sha256"] = canonical_json_sha256(sample_plan)
    hashes["contract_sha256"] = "0" * 64
    contract = {
        "schema_version": "slot-alignment.metric-contract.v7",
        "contract_version": bindings_file["contract_version"],
        "report_contract_version": "slot-alignment.report.v7",
        "task_id": bindings_file["task_id"],
        "mode": bindings_file["mode"],
        "rtp_group": 1,
        "frozen_before_candidate": True,
        "metric_library": {"id": library["library_id"], "version": library["version"], "path": "references/指标目录/index.json", "sha256": sha256_file(LIBRARY_PATH)},
        "policies": {
            "hard_gate_budget": {"id": hard_policy["policy_id"], "version": hard_policy["version"], "path": "assets/policies/hard_gate_budget_policy.json", "sha256": sha256_file(HARD_POLICY_PATH)},
            "alignment_evaluation": {"id": evaluation_policy["policy_id"], "version": evaluation_policy["version"], "path": "assets/policies/alignment_evaluation_policy.json", "sha256": sha256_file(EVALUATION_POLICY_PATH)},
            "target_evidence": {"id": target_evidence_policy["policy_id"], "version": target_evidence_policy["version"], "path": "assets/policies/target_evidence_policy.json", "sha256": sha256_file(TARGET_EVIDENCE_POLICY_PATH)},
            "sample_execution": {"id": sample_policy["policy_id"], "version": sample_policy["version"], "path": "assets/policies/sample_execution_policy.json", "sha256": sha256_file(SAMPLE_POLICY_PATH)}
        },
        "coverage": coverage,
        "cards": cards,
        "audits": audits,
        "hashes": hashes,
    }
    contract["hashes"]["contract_sha256"] = contract_digest(contract)
    dump_json(args.output, contract)


if __name__ == "__main__":
    main()
