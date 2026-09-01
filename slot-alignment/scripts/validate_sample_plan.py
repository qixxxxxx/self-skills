#!/usr/bin/env python3
import argparse
from decimal import Decimal, ROUND_CEILING
from pathlib import Path

from jsonschema import Draft202012Validator

from alignment import dump_json, load_json, sha256_file


ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "assets/policies/sample_execution_policy.json"
SCHEMA_PATH = ROOT / "assets/schemas/sample-execution-plan.schema.json"


def derived_formal(plan):
    formal = plan["formal"]
    minimum = formal["minimum_conditional_sample"]
    probabilities = formal["conditional_exposure_probabilities"]
    required = {
        instance_id: int((Decimal(minimum) / Decimal(str(probability))).to_integral_value(rounding=ROUND_CEILING))
        for instance_id, probability in probabilities.items()
    }
    owner = min(required, key=lambda item: (-required[item], item)) if required else None
    maximum_required = required[owner] if owner else 0
    tiers = formal["tiers"]
    selected = next((tier for tier in tiers if tier >= maximum_required), tiers[-1])
    unresolved = sorted(instance_id for instance_id, probability in probabilities.items() if selected * probability < minimum)
    return {
        "selected_paid_entry_count": selected,
        "owner_instance_id": owner,
        "projected_owner_sample": selected * probabilities[owner] if owner else None,
        "unresolved_below_minimum": unresolved,
    }


def validate_plan(plan, policy=None):
    policy = policy or load_json(POLICY_PATH)
    Draft202012Validator(load_json(SCHEMA_PATH)).validate(plan)
    if plan["policy"]["id"] != policy["policy_id"] or plan["policy"]["version"] != policy["version"]:
        raise ValueError("样本计划绑定的策略ID或版本不一致")
    if plan["policy"]["sha256"] != sha256_file(POLICY_PATH):
        raise ValueError("样本计划绑定的策略hash不一致")
    expected = derived_formal(plan)
    actual = {key: plan["formal"][key] for key in expected}
    if actual != expected:
        raise ValueError(f"FORMAL档位或未满足实例计算不一致，期望={expected}，实际={actual}")
    return expected


def main():
    parser = argparse.ArgumentParser(description="计算并校验slot-alignment样本执行计划")
    parser.add_argument("--plan", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    plan = load_json(args.plan)
    if args.output:
        policy = load_json(POLICY_PATH)
        plan["policy"] = {"id": policy["policy_id"], "version": policy["version"], "sha256": sha256_file(POLICY_PATH)}
        plan["formal"].update(derived_formal(plan))
        dump_json(args.output, plan)
    validate_plan(plan)
    print(f"OK: FORMAL选择{plan['formal']['selected_paid_entry_count']}局，未满足实例{len(plan['formal']['unresolved_below_minimum'])}个")


if __name__ == "__main__":
    main()
