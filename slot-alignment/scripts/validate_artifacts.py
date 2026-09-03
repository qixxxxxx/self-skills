#!/usr/bin/env python3
import argparse

from jsonschema import Draft202012Validator

from alignment import load_json, sha256_file
from compile_metric_contract import contract_digest


def validate(schema_path, value, label):
    errors = list(Draft202012Validator(load_json(schema_path)).iter_errors(value))
    if errors:
        error = errors[0]
        location = ".".join(map(str, error.absolute_path)) or "$"
        raise SystemExit(f"{label}不符合Schema: {location}: {error.message}")


def main():
    parser = argparse.ArgumentParser(description="校验slot-alignment 7.0指标合同和评价结果")
    parser.add_argument("--contract", required=True)
    parser.add_argument("--result")
    args = parser.parse_args()
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    contract = load_json(args.contract)
    validate(root / "assets/schemas/metric-contract.schema.json", contract, "指标合同")
    if contract["hashes"]["contract_sha256"] != contract_digest(contract):
        raise SystemExit("指标合同内部hash不一致")
    if args.result:
        result = load_json(args.result)
        validate(root / "assets/schemas/alignment-result.schema.json", result, "评价结果")
        if result["metric_contract_sha256"] != sha256_file(args.contract):
            raise SystemExit("评价结果未绑定当前指标合同")
        if result["execution"]["certified_script_sha256"] != contract["hashes"]["script_sha256"]:
            raise SystemExit("评价结果使用的认证脚本与合同不一致")
    print("OK: 合同和评价结果有效")


if __name__ == "__main__":
    main()
