#!/usr/bin/env python3
import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path

from jsonschema import Draft202012Validator

from alignment import sha256_file
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
    forbidden = {"weight", "weights", "score", "scores", "score_profile", "score_budget_key", "waiver", "waivers"}
    found = sorted(forbidden & (set(walk_keys(contract)) | set(walk_keys(result))))
    if found:
        errors.append(f"v5产物出现禁止字段: {found}")
    contract_instances = [item["instance_id"] for card in contract["cards"] for item in card["instances"]]
    result_instances = [item["instance_id"] for card in result["card_results"] for item in card["instances"]]
    if contract_instances != result_instances:
        errors.append("结果实例清单与冻结合同不一致")
    if [item["audit_id"] for item in contract["audits"]] != [item["audit_id"] for item in result["audits"]]:
        errors.append("结果审计清单与冻结合同不一致")
    if errors:
        print("\n".join(f"ERROR: {item}" for item in errors), file=sys.stderr)
        raise SystemExit(1)
    print(f"OK: v5产物校验通过，{len(contract_instances)}个正式实例，最终状态={result['summary']['final_status']}")


if __name__ == "__main__":
    main()
