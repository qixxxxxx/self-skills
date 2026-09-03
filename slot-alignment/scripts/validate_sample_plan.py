#!/usr/bin/env python3
import argparse

from alignment import load_json


def validate_plan(plan):
    if plan.get("confirmed_by_user") is not True:
        raise ValueError("样本计划必须由用户确认")
    if plan.get("sample_unit") != "complete_paid_entry" or plan.get("rng_protocol") != "chunk_seeded":
        raise ValueError("样本单位或RNG协议不正确")
    calibration = plan["calibration"]
    tiers = [item for item in [calibration.get("probe"), calibration["screen"], calibration["refine"], calibration["final"]] if item is not None]
    if tiers != sorted(tiers):
        raise ValueError("候选样本阶梯必须递增")
    formal = plan["formal"]
    if formal["selected_paid_entry_count"] not in formal["tiers"]:
        raise ValueError("FORMAL样本数必须来自确认档位")
    if formal.get("independent_seed") is not True:
        raise ValueError("FORMAL必须使用独立seed")


def main():
    parser = argparse.ArgumentParser(description="校验slot-alignment 7.0样本计划")
    parser.add_argument("--preflight", required=True)
    args = parser.parse_args()
    plan = load_json(args.preflight)["sample_plan"]
    validate_plan(plan)
    print(f"OK: 候选FINAL {plan['calibration']['final']}局，FORMAL {plan['formal']['selected_paid_entry_count']}局")


if __name__ == "__main__":
    main()
