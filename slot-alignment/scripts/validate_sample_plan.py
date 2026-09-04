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
    if calibration.get("candidate_batch_size", 0) < 1 or calibration.get("candidate_total_limit") is not None:
        raise ValueError("候选必须按正整数批大小持续搜索，不能设置固定总数上限")
    if calibration.get("continuation_rule") != "continue_until_formal_pass_or_authorized_space_exhausted":
        raise ValueError("候选未配置持续搜索到FORMAL通过或授权空间穷尽")
    if calibration.get("formal_failure_action") != "resume_search_with_new_candidate":
        raise ValueError("FORMAL失败后必须返回搜索并生成新候选")
    formal = plan["formal"]
    if formal["selected_paid_entry_count"] not in formal["tiers"]:
        raise ValueError("FORMAL样本数必须来自确认档位")
    if formal.get("independent_seed") is not True:
        raise ValueError("FORMAL必须使用独立seed")
    if formal.get("attempt_seed_rule") != "pre_frozen_sequence_by_formal_attempt" or formal.get("same_candidate_retry") is not False:
        raise ValueError("FORMAL必须按预冻结序列分配seed，且同一候选不得重试")


def main():
    parser = argparse.ArgumentParser(description="校验slot-alignment 7.0样本计划")
    parser.add_argument("--preflight", required=True)
    args = parser.parse_args()
    plan = load_json(args.preflight)["sample_plan"]
    validate_plan(plan)
    print(f"OK: 候选每批{plan['calibration']['candidate_batch_size']}组持续搜索，FORMAL {plan['formal']['selected_paid_entry_count']}局")


if __name__ == "__main__":
    main()
