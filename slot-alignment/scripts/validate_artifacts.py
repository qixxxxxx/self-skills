#!/usr/bin/env python3
import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path

from jsonschema import Draft202012Validator

from alignment import _j_card_score, finite_number, grade_ratio, grade_score, grade_thresholds, sha256_file, worst_grade
from compile_metric_contract import contract_digest


ROOT = Path(__file__).resolve().parents[1]


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validate(schema_path, data_path, errors):
    schema, data = load(schema_path), load(data_path)
    for error in Draft202012Validator(schema).iter_errors(data):
        location = ".".join(map(str, error.absolute_path)) or "$"
        errors.append(f"{data_path}:{location}: {error.message}")
    return data


def walk_keys(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from walk_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk_keys(item)


def main():
    parser = argparse.ArgumentParser(description="校验slot-alignment v5合同与评价产物")
    parser.add_argument("--contract", required=True)
    parser.add_argument("--result", required=True)
    parser.add_argument("--stage3-gate")
    args = parser.parse_args()
    errors = []
    contract = validate(ROOT / "assets/schemas/metric-contract.schema.json", args.contract, errors)
    result = validate(ROOT / "assets/schemas/alignment-result.schema.json", args.result, errors)
    if args.stage3_gate:
        gate = validate(ROOT / "assets/schemas/stage3-gate.schema.json", args.stage3_gate, errors)
        if gate["alignment_result_sha256"] != sha256_file(args.result):
            errors.append("stage3_gate绑定的alignment_result_sha256不一致")
        if gate["task_id"] != result["task_id"]:
            errors.append("stage3_gate与评价结果task_id不一致")
        if gate["baseline_final_status"] != result["summary"]["final_status"]:
            errors.append("stage3_gate与评价结果最终状态不一致")
    if result["metric_contract_sha256"] != sha256_file(args.contract):
        errors.append("评价结果绑定的metric_contract_sha256不一致")
    if result["task_id"] != contract["task_id"]:
        errors.append("评价结果与指标合同task_id不一致")
    if contract["hashes"]["contract_sha256"] != contract_digest(contract):
        errors.append("metric_contract内部contract_sha256不一致")
    for binding in [contract["metric_library"], *contract["policies"].values()]:
        bound_path = ROOT / binding["path"]
        if not bound_path.is_file():
            errors.append(f"合同绑定文件不存在: {binding['path']}")
        elif binding["sha256"] != sha256_file(bound_path):
            errors.append(f"合同绑定文件hash不一致: {binding['path']}")
    expected_cards = ["N1", "N2", "N3", "N4", "N5", "N6", "J1", "J2", "J3", "P1", "P2", "B1", "B2"]
    if [item["card_id"] for item in contract["cards"]] != expected_cards:
        errors.append("metric_contract卡片集合或顺序漂移")
    if [item["card_id"] for item in result["card_results"]] != expected_cards:
        errors.append("alignment_result卡片集合或顺序漂移")
    forbidden = {"score_profile", "score_budget_key", "waiver", "waivers"}
    found = sorted(forbidden & (set(walk_keys(contract)) | set(walk_keys(result))))
    if found:
        errors.append(f"v5产物出现禁止字段: {found}")
    contract_instances = [item["instance_id"] for card in contract["cards"] for item in card["instances"]]
    result_instances = [item["instance_id"] for card in result["card_results"] for item in card["instances"]]
    if contract_instances != result_instances:
        errors.append("结果实例清单与冻结合同不一致")
    if [item["audit_id"] for item in contract["audits"]] != [item["audit_id"] for item in result["audits"]]:
        errors.append("结果审计清单与冻结合同不一致")
    policy = load(ROOT / contract["policies"]["alignment_evaluation"]["path"])
    pass_grades = set(policy["formal_grading"]["pass_grades"])
    all_results = []
    for card, card_result in zip(contract["cards"], result["card_results"]):
        thresholds = grade_thresholds(card, policy)
        for item in card_result["instances"]:
            all_results.append(item)
            if item["pass_limit"] != thresholds["C"]:
                errors.append(f"{item['instance_id']}的C级通过上限与评价政策不一致")
            if item["status"] in {"样本不足", "计算异常"}:
                expected_grade = "U"
            elif item["status"] == "不适用":
                expected_grade = "NA"
            elif item["tolerance"] == 0:
                expected_grade = "S" if item["distance"] == 0 else "F"
            elif card["category_id"] in {"N", "J"} and finite_number(item["deviation_ratio"]):
                expected_score = max(0.0, 100.0 * (1.0 - item["deviation_ratio"]))
                if not finite_number(item.get("score")) or abs(item["score"] - expected_score) > 1e-9:
                    errors.append(f"{item['instance_id']}的N/J类单项分不正确")
                expected_grade = grade_score(expected_score, policy) if item["deviation_ratio"] <= 1.0 else "F"
            elif finite_number(item["deviation_ratio"]):
                expected_grade = grade_ratio(item["deviation_ratio"], thresholds)
            else:
                expected_grade = "F"
            if item["formal_grade"] != expected_grade:
                errors.append(f"{item['instance_id']}的FORMAL等级与偏差倍数不一致")
            expected_status = "通过" if expected_grade in pass_grades else "不通过"
            if expected_grade not in {"U", "NA"} and item["status"] != expected_status:
                errors.append(f"{item['instance_id']}的状态与FORMAL等级不一致")
        expected_card_grade = worst_grade(item["formal_grade"] for item in card_result["instances"])
        if card["category_id"] == "N" and card_result["status"] == "通过":
            expected_card_score = sum(item["score"] for item in card_result["instances"]) / len(card_result["instances"])
            if not finite_number(card_result.get("score")) or abs(card_result["score"] - expected_card_score) > 1e-9:
                errors.append(f"{card['card_id']}卡分未按卡内活动子项等权平均")
            expected_card_grade = grade_score(expected_card_score, policy)
        elif card["category_id"] == "J" and card_result["status"] == "通过":
            expected_card_score = _j_card_score(card, card_result["instances"])
            if not finite_number(card_result.get("score")) or abs(card_result["score"] - expected_card_score) > 1e-9:
                errors.append(f"{card['card_id']}卡分未按J类分层规则计算")
            expected_card_grade = grade_score(expected_card_score, policy)
        elif card_result.get("score") is not None:
            errors.append(f"{card['card_id']}未全部通过或尚未落定评分，卡分必须为null")
        if card_result["formal_grade"] != expected_card_grade:
            errors.append(f"{card['card_id']}卡级FORMAL等级与当前聚合规则不一致")
    unknown = any(item["formal_grade"] == "U" for item in all_results)
    failed = any(item["formal_grade"] == "F" for item in all_results)
    n_cards = [item for item in result["card_results"] if item["category_id"] == "N" and item["status"] != "不适用"]
    expected_n_score = None
    if n_cards and all(item["status"] == "通过" and finite_number(item.get("score")) for item in n_cards):
        expected_n_score = sum(item["score"] for item in n_cards) / len(n_cards)
    j_cards = [item for item in result["card_results"] if item["category_id"] == "J" and item["status"] != "不适用"]
    expected_j_score = None
    if j_cards and all(item["status"] == "通过" and finite_number(item.get("score")) for item in j_cards):
        expected_j_score = sum(item["score"] for item in j_cards) / len(j_cards)
    summary = result["summary"]
    if summary["category_scores"] != {"N": expected_n_score, "J": expected_j_score, "P": None, "B": None}:
        errors.append("当前分类分必须包含N/J，P/B保留null槽位")
    if summary["composite_score"] != expected_n_score or summary["score_scope"] != ["N"] or summary["planned_score_scope"] != ["N", "J", "P", "B"]:
        errors.append("当前综合分必须明确为N类阶段分，并预留N/J/P/B完整范围")
    expected_final_grade = "U" if unknown else ("F" if failed else grade_score(expected_n_score, policy))
    if result["summary"]["final_grade"] != expected_final_grade:
        errors.append("最终等级未按“全项先过C线，再看N类阶段分”计算")
    expected_final_status = "无法完整判定" if unknown else ("不通过" if failed else "通过")
    if result["summary"]["final_status"] != expected_final_status:
        errors.append("最终状态与FORMAL等级不一致")
    if errors:
        print("\n".join(f"ERROR: {item}" for item in errors), file=sys.stderr)
        raise SystemExit(1)
    print(f"OK: v5产物校验通过，{len(contract_instances)}个正式实例，最终状态={result['summary']['final_status']}")


if __name__ == "__main__":
    main()
