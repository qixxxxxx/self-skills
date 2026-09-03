#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

from alignment import load_json


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "assets/schemas/source-summary.schema.json"


def validate_source_summary(value):
    errors = []
    for error in Draft202012Validator(load_json(SCHEMA)).iter_errors(value):
        location = ".".join(map(str, error.absolute_path)) or "$"
        errors.append(f"{location}: {error.message}")
    if errors:
        return errors
    if value["sample_counts"]["complete_paid_entries"] != sum(item.get("sample_count", 0) for item in value["sources"]):
        errors.append("完整付费入口数与各来源sample_count之和不一致")
    return errors


def main():
    parser = argparse.ArgumentParser(description="校验slot-alignment 7.0原版样本汇总")
    parser.add_argument("--summary", required=True)
    parser.add_argument("--preflight")
    args = parser.parse_args()
    value = load_json(args.summary)
    errors = validate_source_summary(value)
    if args.preflight and load_json(args.preflight)["task_id"] != value.get("task_id"):
        errors.append("source_summary.task_id与preflight不一致")
    if errors:
        print("\n".join(f"ERROR: {item}" for item in errors), file=sys.stderr)
        raise SystemExit(1)
    print(f"OK: 原版样本汇总有效，目标{len(value['targets'])}项")


if __name__ == "__main__":
    main()
