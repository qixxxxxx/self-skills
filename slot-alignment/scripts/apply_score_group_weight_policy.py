#!/usr/bin/env python3
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

from contract_io import load_contract, write_contract


def load(path):
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def positive(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name}必须是有限正数")
    return float(value)


def active_score_groups(contract):
    return sorted({
        metric["score_group"]
        for metric in contract.get("metrics", [])
        if metric.get("kind") == "score"
        and metric.get("status") != "不适用"
        and metric.get("waiver", {}).get("status") != "已批准"
    })


def active_score_budget_keys(contract):
    return sorted({
        metric["score_budget_key"]
        for metric in contract.get("metrics", [])
        if metric.get("kind") == "score"
        and metric.get("status") != "不适用"
        and metric.get("waiver", {}).get("status") != "已批准"
    })


def budget_keys_sha256(keys):
    payload = json.dumps(keys, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def normalized_weights(base_weights, groups):
    if not isinstance(base_weights, dict) or not base_weights:
        raise ValueError("政策缺少base_weights")
    base = {name: positive(value, f"评分组{name}基础权重") for name, value in base_weights.items()}
    unknown = sorted(set(groups) - set(base))
    if unknown:
        raise ValueError(f"政策未登记活动评分组: {','.join(unknown)}")
    if not groups:
        return base, {}
    total = sum(base[name] for name in groups)
    return base, {name: base[name] / total for name in groups}


def apply_policy(contract, policy, policy_path):
    if policy.get("method") != "normalize_active_base_weights":
        raise ValueError("不支持的评分组权重政策方法")
    groups = active_score_groups(contract)
    budget_keys = active_score_budget_keys(contract)
    base, weights = normalized_weights(policy.get("base_weights"), groups)
    contract["score_group_weight_policy"] = {
        "policy_id": policy["policy_id"],
        "version": policy["version"],
        "source_path": policy.get("source_path", f"assets/policies/{Path(policy_path).name}"),
        "source_sha256": hashlib.sha256(Path(policy_path).read_bytes()).hexdigest(),
        "method": policy["method"],
        "base_weights": base,
        "active_groups": groups,
        "active_score_budget_keys": budget_keys,
        "active_score_budget_keys_sha256": budget_keys_sha256(budget_keys),
        "legacy_contracts_unchanged": bool(policy.get("legacy_contracts_unchanged")),
    }
    contract["group_weights"] = weights
    return weights


def validate_embedded_policy(contract):
    policy = contract.get("score_group_weight_policy")
    if not isinstance(policy, dict):
        raise ValueError("合同缺少score_group_weight_policy")
    if policy.get("method") != "normalize_active_base_weights":
        raise ValueError("不支持的评分组权重政策方法")
    groups = active_score_groups(contract)
    budget_keys = active_score_budget_keys(contract)
    if policy.get("active_groups") != groups:
        raise ValueError("评分组权重政策的active_groups与合同活动评分组不一致")
    if policy.get("active_score_budget_keys") != budget_keys:
        raise ValueError("评分组权重政策的活动评分预算键与合同不一致")
    if policy.get("active_score_budget_keys_sha256") != budget_keys_sha256(budget_keys):
        raise ValueError("评分组权重政策的活动评分预算键SHA-256失效")
    _, expected = normalized_weights(policy.get("base_weights"), groups)
    actual = contract.get("group_weights")
    if not isinstance(actual, dict) or set(actual) != set(expected):
        raise ValueError("group_weights必须与政策活动评分组完全一致")
    for name, expected_value in expected.items():
        value = positive(actual[name], f"评分组{name}权重")
        if not math.isclose(value, expected_value, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError(f"评分组{name}权重不符合版本化政策")
    return expected


def validate_policy_source_binding(contract, skill_root):
    try:
        validate_embedded_policy(contract)
    except (TypeError, ValueError) as exc:
        return [str(exc)]
    policy = contract["score_group_weight_policy"]
    source = policy.get("source_path")
    if not isinstance(source, str) or not source or Path(source).is_absolute():
        return ["评分组权重政策来源路径无效"]
    root = Path(skill_root).resolve()
    path = (root / source).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        return ["评分组权重政策来源路径越出Skill目录"]
    if not path.is_file():
        return ["评分组权重政策来源文件不存在"]
    if hashlib.sha256(path.read_bytes()).hexdigest() != policy.get("source_sha256"):
        return ["评分组权重政策来源SHA-256失效"]
    source_policy = load(path)
    fields = ("policy_id", "version", "method", "base_weights", "legacy_contracts_unchanged")
    mismatches = [field for field in fields if policy.get(field) != source_policy.get(field)]
    return [f"评分组权重政策合同字段与来源不一致: {','.join(mismatches)}"] if mismatches else []


def main():
    parser = argparse.ArgumentParser(description="按版本化政策生成 Slot 顶层评分组权重")
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    contract, policy = load_contract(args.contract), load(args.policy)
    weights = apply_policy(contract, policy, args.policy)
    write_contract(contract, args.output)
    print(json.dumps({
        "status": "通过",
        "policy_id": policy["policy_id"],
        "active_groups": active_score_groups(contract),
        "group_weights": weights,
        "output": str(args.output),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "失败", "error": str(exc)}, ensure_ascii=False))
        sys.exit(2)
