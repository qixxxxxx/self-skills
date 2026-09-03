#!/usr/bin/env python3
import argparse
from pathlib import Path

from jsonschema import Draft202012Validator

from alignment import dump_json, evaluate_contract, load_json, sha256_file


ROOT = Path(__file__).resolve().parents[1]


def validate(schema_name, value, label):
    errors = list(Draft202012Validator(load_json(ROOT / "assets/schemas" / schema_name)).iter_errors(value))
    if errors:
        error = errors[0]
        location = ".".join(map(str, error.absolute_path)) or "$"
        raise SystemExit(f"{label}不符合Schema：{location}: {error.message}")


def main():
    parser = argparse.ArgumentParser(description="计算slot-alignment 7.0逐卡判定")
    parser.add_argument("--contract", required=True)
    parser.add_argument("--measurements", required=True)
    parser.add_argument("--phase", choices=["BASELINE", "CALIBRATION", "FORMAL"], required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    contract = load_json(args.contract)
    measurements = load_json(args.measurements)
    validate("metric-contract.schema.json", contract, "指标合同")
    validate("metric-measurements.schema.json", measurements, "测量文件")
    actual = sha256_file(args.contract)
    if measurements["metric_contract_sha256"] != actual:
        raise SystemExit("测量文件绑定的metric_contract_sha256与当前合同不一致")
    if measurements["task_id"] != contract["task_id"]:
        raise SystemExit("测量文件task_id与指标合同不一致")
    if measurements["phase"] != args.phase:
        raise SystemExit("测量文件phase与命令行阶段不一致")
    if measurements["execution"]["certified_script_sha256"] != contract["hashes"]["script_sha256"]:
        raise SystemExit("测量文件使用的认证脚本与冻结合同不一致")
    if args.phase == "FORMAL" and measurements["execution"]["independent_seed"] is not True:
        raise SystemExit("FORMAL必须使用新的独立seed")
    instance_ids = {item["instance_id"] for card in contract["cards"] for item in card["instances"]}
    extra_ids = set(measurements["measurements"]) - instance_ids
    if extra_ids:
        raise SystemExit(f"测量文件包含合同之外的实例: {sorted(extra_ids)}")
    policy_binding = contract["policies"]["alignment_evaluation"]
    policy_path = ROOT / policy_binding["path"]
    if sha256_file(policy_path) != policy_binding["sha256"]:
        raise SystemExit("指标合同绑定的评价政策SHA-256与当前文件不一致")
    policy = load_json(policy_path)
    dump_json(args.output, evaluate_contract(contract, measurements, args.phase, actual, policy))


if __name__ == "__main__":
    main()
