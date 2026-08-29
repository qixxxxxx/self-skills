#!/usr/bin/env python3
import argparse
import hashlib
import json
import re
from copy import deepcopy
from pathlib import Path

from jsonschema import Draft202012Validator

from alignment import dump_json, finite_number, load_json, sha256_file


ROOT = Path(__file__).resolve().parents[1]
LIBRARY_PATH = ROOT / "references" / "指标目录" / "index.json"
HARD_POLICY_PATH = ROOT / "assets" / "policies" / "hard_gate_tolerance_policy.json"
EVALUATION_POLICY_PATH = ROOT / "assets" / "policies" / "alignment_evaluation_policy.json"


def safe_id(value):
    value = re.sub(r"[^a-z0-9_.:-]+", "-", str(value).lower()).strip("-.")
    if not value:
        raise ValueError("无法生成空子项ID")
    return value


def subitems(card_id, facet_id, bindings):
    features = bindings["features"]
    settlements = bindings["settlements"]
    continuous = bindings["continuous_settlements"]
    mechanics = bindings["special_mechanics"]
    boards = bindings["boards"]
    if (card_id, facet_id) in {("N1", "total_rtp"), ("N2", "positive_return_rate"), ("N4", "return_ge_cost_rate")}:
        return [("overall", {"scope": "overall"}, {})]
    if (card_id, facet_id) == ("N3", "natural_trigger_rate"):
        return [(item["feature_id"], {"feature": item["feature_id"]}, {}) for item in features if item["endogenous_entry"]]
    if (card_id, facet_id) == ("N5", "return_sigma"):
        return [("overall", {"scope": "overall"}, {})] + [(scope, {"scope": scope}, {}) for scope in bindings["sigma_scopes"]]
    if (card_id, facet_id) == ("N6", "component_rtp"):
        return [(component, {"component": component}, {}) for component in bindings["components"]]
    if (card_id, facet_id) == ("J1", "element_win_participation_rate"):
        return [(f"{item['settlement_id']}.{element}", {"settlement": item["settlement_id"], "element": element}, {}) for item in settlements for element in item["elements"]]
    if (card_id, facet_id) == ("J1", "payline_win_participation_rate"):
        return [(f"{item['settlement_id']}.{line}", {"settlement": item["settlement_id"], "payline": line}, {}) for item in settlements if item["settlement_type"] == "payline" for line in item["paylines"]]
    if (card_id, facet_id) == ("J2", "single_win_structure_size"):
        return [(f"{item['settlement_id']}.{element}.{axis}", {"settlement": item["settlement_id"], "element": element, "axis": axis}, {}) for item in settlements for element in item["elements"] for axis in item["size_axes"]]
    if (card_id, facet_id) == ("J2", "simultaneous_win_count"):
        return [(item["settlement_id"], {"settlement": item["settlement_id"]}, {}) for item in settlements]
    if (card_id, facet_id) == ("J2", "actual_reward_size"):
        return [(f"{item['settlement_id']}.{element}", {"settlement": item["settlement_id"], "element": element}, {}) for item in settlements if item["payout_mapping"] == "variable" for element in item["elements"]]
    if (card_id, facet_id) == ("J3", "total_depth"):
        return [(item["continuous_id"], {"continuous_settlement": item["continuous_id"]}, {}) for item in continuous]
    if (card_id, facet_id) == ("J3", "win_scale_by_depth"):
        return [(f"{item['continuous_id']}.depth-{depth}.{axis}", {"continuous_settlement": item["continuous_id"], "depth": depth, "axis": axis}, {}) for item in continuous for depth in item["reachable_depths"] for axis in item["size_axes"]]
    if (card_id, facet_id) == ("P1", "initial_free_spin_count"):
        return [(item["feature_id"], {"feature": item["feature_id"]}, {}) for item in features if item["feature_type"] == "free_spin"]
    if (card_id, facet_id) == ("P1", "feature_duration"):
        return [(item["feature_id"], {"feature": item["feature_id"], "feature_type": item["feature_type"]}, {}) for item in features]
    if (card_id, facet_id) == ("P2", "mechanic_result_state"):
        return [(item["mechanic_id"], {"mechanic": item["mechanic_id"]}, {"sealed_states": item["result_states"]}) for item in mechanics]
    if (card_id, facet_id) == ("B1", "symbol_count_per_board"):
        return [(f"{board['board_scope_id']}.{symbol}", {"board": board["board_scope_id"], "symbol": symbol}, {}) for board in boards for symbol in board["symbols"]]
    if (card_id, facet_id) == ("B2", "board_shape"):
        return [(board["board_scope_id"], {"board": board["board_scope_id"]}, {"state_kind": "board_shape", "board_shape": [board["rows"], board["columns"]]}) for board in boards if board["variable_shape"]]
    if (card_id, facet_id) == ("B2", "key_symbol_position_density"):
        return [(f"{board['board_scope_id']}.{symbol}", {"board": board["board_scope_id"], "symbol": symbol}, {"state_kind": "symbol_position_density", "board_shape": [board["rows"], board["columns"]]}) for board in boards for symbol in board["spatial_symbols"]]
    return []


def distance_contract(facet, target_record, extra):
    result = {"method": facet["distance_method"]}
    if facet.get("axis_semantics") not in {None, "from_J2"}:
        result["axis_semantics"] = facet["axis_semantics"]
    if facet.get("position_transform"):
        result["position_transform"] = facet["position_transform"]
    result.update(target_record.get("distance", {}))
    if result["method"] == "structural_wasserstein":
        result.update(extra)
        result["ground_cost"] = {
            "symbol_position_density": "normalized_grid_manhattan",
            "board_shape": "normalized_active_cell_change",
        }[extra["state_kind"]]
    return result


def contract_digest(contract):
    clone = deepcopy(contract)
    clone["hashes"]["contract_sha256"] = "0" * 64
    raw = json.dumps(clone, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def main():
    parser = argparse.ArgumentParser(description="编译slot-alignment v5指标合同")
    parser.add_argument("--profile", required=True)
    parser.add_argument("--targets", required=True)
    parser.add_argument("--joint-tolerances", required=True)
    parser.add_argument("--bindings", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    profile = load_json(args.profile)
    targets = load_json(args.targets).get("targets", {})
    joint = load_json(args.joint_tolerances)
    bindings_file = load_json(args.bindings)
    library = load_json(LIBRARY_PATH)
    hard_policy = load_json(HARD_POLICY_PATH)
    evaluation_policy = load_json(EVALUATION_POLICY_PATH)
    bindings = profile["metric_bindings"]
    profile_schema = load_json(ROOT / "assets/schemas/game-profile-metric-bindings.schema.json")
    Draft202012Validator(profile_schema).validate(profile)
    joint_schema = load_json(ROOT / "assets/schemas/joint-self-comparison.schema.json")
    Draft202012Validator(joint_schema).validate(joint)
    for mechanic in bindings["special_mechanics"]:
        unknown = set(mechanic["inactive_state_ids"]) - set(mechanic["result_states"])
        if unknown:
            raise SystemExit(f"{mechanic['mechanic_id']} inactive_state_ids不在result_states中: {sorted(unknown)}")
    for board in bindings["boards"]:
        unknown = set(board["spatial_symbols"]) - set(board["symbols"])
        if unknown:
            raise SystemExit(f"{board['board_scope_id']} spatial_symbols不在symbols中: {sorted(unknown)}")
    cards, missing = [], []
    used_targets, used_tolerances = set(), set()
    for card in library["cards"]:
        instances = []
        for facet in card["facets"]:
            for subitem_id, scope, extra in subitems(card["card_id"], facet["facet_id"], bindings):
                instance_id = f"{card['card_id']}.{facet['facet_id']}.{safe_id(subitem_id)}"
                target_record = targets.get(instance_id)
                if target_record is None:
                    missing.append(instance_id)
                    continue
                used_targets.add(instance_id)
                target_source = target_record.get("source", {})
                target_method = target_source.get("method")
                if card["card_id"] == "N1":
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
                if card["kind"] == "hard_gate":
                    base = float(target_record["base_tolerance"])
                    factor = float(hard_policy["metric_factors"][card["card_id"]])
                    tolerance = {"source": "hard_gate_task_contract", "base": base, "factor": factor, "effective": base * factor}
                elif target_record.get("deterministic_exact"):
                    tolerance = {"source": "deterministic_exact", "base": 0.0, "factor": 1.0, "effective": 0.0}
                else:
                    value = joint["tolerances"].get(instance_id)
                    if value is None:
                        missing.append(f"{instance_id}:joint_tolerance")
                        continue
                    used_tolerances.add(instance_id)
                    tolerance = {
                        "source": "sealed_original_joint_self_comparison",
                        "base": float(value),
                        "factor": 1.0,
                        "effective": float(value),
                        "self_comparison": {
                            "quantile": 0.99,
                            "joint": True,
                            "replicates": int(joint["replicates"]),
                            "seed": int(joint["seed"]),
                            "evidence_sha256": joint["evidence_sha256"],
                        },
                    }
                instances.append({
                    "instance_id": instance_id,
                    "facet_id": facet["facet_id"],
                    "subitem_id": safe_id(subitem_id),
                    "scope": scope,
                    "sample_unit": facet["sample_unit"],
                    "measurement": facet["measurement"],
                    "target_source": target_record["source"],
                    "target": target_record["value"],
                    "distance": distance_contract(facet, target_record, extra),
                    "tolerance": tolerance,
                    "status": "active",
                })
        cards.append({
            "card_id": card["card_id"],
            "name_zh": card["name_zh"],
            "category_id": card["category_id"],
            "kind": card["kind"],
            "status": "active" if instances else "不适用",
            "instances": instances,
        })
    if missing:
        raise SystemExit("缺少目标或联合容差: " + ", ".join(sorted(missing)))
    extra_targets = set(targets) - used_targets
    extra_tolerances = set(joint.get("tolerances", {})) - used_tolerances
    if extra_targets or extra_tolerances:
        raise SystemExit(f"存在未绑定的目标或容差: targets={sorted(extra_targets)}, tolerances={sorted(extra_tolerances)}")
    audits = [{
        "audit_id": item["audit_id"],
        "name_zh": item["name_zh"],
        "source_cards": item["source_cards"],
        "measurement": ",".join(item["includes"]),
        "required": True,
    } for item in library["audits"]]
    hashes = {key: bindings_file[key] for key in ["runtime_bundle_sha256", "original_evidence_sha256", "script_sha256", "game_profile_sha256", "parameter_authority_sha256"]}
    hashes["contract_sha256"] = "0" * 64
    contract = {
        "schema_version": "slot-alignment.metric-contract.v5",
        "contract_version": bindings_file["contract_version"],
        "report_contract_version": "slot-alignment.report.v5",
        "task_id": bindings_file["task_id"],
        "mode": bindings_file["mode"],
        "rtp_group": 1,
        "frozen_before_candidate": True,
        "metric_library": {"id": library["library_id"], "version": library["version"], "path": "references/指标目录/index.json", "sha256": sha256_file(LIBRARY_PATH)},
        "policies": {
            "hard_gate_tolerance": {"id": hard_policy["policy_id"], "version": hard_policy["version"], "path": "assets/policies/hard_gate_tolerance_policy.json", "sha256": sha256_file(HARD_POLICY_PATH)},
            "alignment_evaluation": {"id": evaluation_policy["policy_id"], "version": evaluation_policy["version"], "path": "assets/policies/alignment_evaluation_policy.json", "sha256": sha256_file(EVALUATION_POLICY_PATH)},
        },
        "cards": cards,
        "audits": audits,
        "hashes": hashes,
    }
    contract["hashes"]["contract_sha256"] = contract_digest(contract)
    dump_json(args.output, contract)


if __name__ == "__main__":
    main()
