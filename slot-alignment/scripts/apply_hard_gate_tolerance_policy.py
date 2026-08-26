#!/usr/bin/env python3
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path


def load(path):
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def finite_nonnegative(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError(f"{name}必须是有限非负数")
    return float(value)


def main():
    parser = argparse.ArgumentParser(description="为新 Slot 对齐合同应用默认硬指标容差系数")
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    contract, policy = load(args.contract), load(args.policy)
    factors = policy.get("metric_factors", {})
    default_factor = finite_nonnegative(policy.get("default_factor"), "default_factor")
    if default_factor == 0:
        raise ValueError("default_factor必须大于0")
    locked = set(policy.get("locked_metrics", []))
    applied = 0
    for metric in contract.get("metrics", []):
        if metric.get("kind") != "hard" or metric.get("status") == "不适用":
            continue
        profile = metric.get("hard_gate_profile")
        if not isinstance(profile, dict):
            raise ValueError(f"硬指标缺少hard_gate_profile: {metric.get('metric_id')}")
        base = finite_nonnegative(profile.get("base_tolerance", profile.get("tolerance")), f"{metric.get('metric_id')} base_tolerance")
        factor = finite_nonnegative(factors.get(metric.get("metric_id"), default_factor), f"{metric.get('metric_id')} tolerance_factor")
        if factor == 0:
            raise ValueError(f"{metric.get('metric_id')} tolerance_factor必须大于0")
        if metric.get("metric_id") in locked and factor != 1.0:
            raise ValueError(f"锁定指标系数必须为1.0: {metric.get('metric_id')}")
        profile.update({
            "base_tolerance": base,
            "tolerance_factor": factor,
            "tolerance": base * factor,
            "tolerance_policy_id": policy["policy_id"],
        })
        applied += 1
    source_hash = hashlib.sha256(args.policy.read_bytes()).hexdigest()
    contract["hard_gate_tolerance_policy"] = {
        "policy_id": policy["policy_id"],
        "version": policy["version"],
        "source_path": policy.get("source_path", f"assets/policies/{args.policy.name}"),
        "source_sha256": source_hash,
        "default_factor": default_factor,
        "metric_factors": factors,
        "locked_metrics": sorted(locked),
        "legacy_contracts_unchanged": bool(policy.get("legacy_contracts_unchanged")),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "通过", "applied_hard_metrics": applied, "policy_id": policy["policy_id"], "output": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "失败", "error": str(exc)}, ensure_ascii=False))
        sys.exit(2)
