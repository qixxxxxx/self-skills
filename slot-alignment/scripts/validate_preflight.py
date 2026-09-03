#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

from alignment import load_json, sha256_file


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "assets/schemas/preflight.schema.json"
RUNTIME_FILES = ["game_core.json", "payout_config.json", "reel_config.json", "symbol_catalog.json"]


def validate_preflight(value, path=None):
    errors = []
    for error in Draft202012Validator(load_json(SCHEMA)).iter_errors(value):
        location = ".".join(map(str, error.absolute_path)) or "$"
        errors.append(f"{location}: {error.message}")
    if errors:
        return errors
    if [item["name"] for item in value["runtime"]["files"]] != RUNTIME_FILES:
        errors.append(f"Runtime文件必须按固定顺序填写: {RUNTIME_FILES}")
    parameters = value["parameter_authority"]["parameters"]
    ids = [item["parameter_id"] for item in parameters]
    if len(ids) != len(set(ids)):
        errors.append("parameter_id重复")
    unsupported = [
        item["parameter_id"]
        for item in parameters
        if item["authorization"] == "authorized" and item["script_support"] != "supported"
    ]
    if unsupported:
        errors.append(f"授权参数没有被认证脚本支持: {unsupported}")
    calibration = value["sample_plan"]["calibration"]
    tiers = [item for item in [calibration.get("probe"), calibration["screen"], calibration["refine"], calibration["final"]] if item is not None]
    if tiers != sorted(tiers):
        errors.append("候选样本阶梯必须递增")
    formal = value["sample_plan"]["formal"]
    if formal["selected_paid_entry_count"] not in formal["tiers"]:
        errors.append("FORMAL样本数必须来自用户确认的档位")
    script_path = Path(value["certified_script"]["path"])
    if script_path.is_absolute() and script_path.is_file() and sha256_file(script_path) != value["certified_script"]["sha256"]:
        errors.append("用户认证脚本SHA-256与实际文件不一致")
    return errors


def main():
    parser = argparse.ArgumentParser(description="校验slot-alignment 7.0开工合同")
    parser.add_argument("--preflight", required=True)
    args = parser.parse_args()
    value = load_json(args.preflight)
    errors = validate_preflight(value, args.preflight)
    if errors:
        print("\n".join(f"ERROR: {item}" for item in errors), file=sys.stderr)
        raise SystemExit(1)
    print("OK: 开工六项完整，可以整理样本")


if __name__ == "__main__":
    main()
