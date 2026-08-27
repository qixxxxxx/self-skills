#!/usr/bin/env python3
import argparse
import hashlib
import json
import sys
from pathlib import Path

from contract_io import load_contract, write_contract


ORDERED_METHODS = {"wasserstein_1d", "grouped_wasserstein_1d"}
AXIS_SEMANTICS = {"natural_linear", "nonnegative_multiplicative"}
CONTROLLED_PROFILE_FIELDS = (
    "axis_semantics",
    "ordered_distance_policy_id",
    "position_transform",
    "distance_normalization",
    "distance_scale",
    "distance_scale_source",
    "distance_unit",
)
SOURCE_FIELDS = (
    "policy_id",
    "version",
    "source_path",
    "default_axis_semantics",
    "axis_profiles",
    "fixed_nonnegative_multiplicative_metrics",
    "dynamic_axis_metrics",
    "rules",
    "legacy_contracts_unchanged",
)


def load(path):
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def non_empty(value):
    return isinstance(value, str) and bool(value.strip())


def canonical_sha256(value):
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def validate_policy_definition(policy):
    if not isinstance(policy, dict):
        raise ValueError("有序距离政策必须是对象")
    if policy.get("schema_version") != "slot-alignment.ordered-distance-policy.v1":
        raise ValueError("有序距离政策schema_version无效")
    for field in ("policy_id", "version", "source_path"):
        if not non_empty(policy.get(field)):
            raise ValueError(f"有序距离政策缺少{field}")
    source_path = Path(policy["source_path"])
    if source_path.is_absolute() or ".." in source_path.parts:
        raise ValueError("有序距离政策source_path必须是Skill内安全相对路径")
    if policy.get("legacy_contracts_unchanged") is not True:
        raise ValueError("有序距离政策必须声明旧合同不变")
    if policy.get("default_axis_semantics") != "natural_linear":
        raise ValueError("有序距离政策默认轴必须是natural_linear")
    expected_profiles = {
        "natural_linear": {
            "position_transform": "identity",
            "distance_normalization": "sealed_support_span",
            "distance_scale_source": "sealed_support_span",
            "distance_unit": "normalized_linear_support",
        },
        "nonnegative_multiplicative": {
            "position_transform": "log10_1p",
            "distance_normalization": "fixed_transform_unit",
            "distance_scale": 1.0,
            "distance_unit": "log10_decade",
        },
    }
    if policy.get("axis_profiles") != expected_profiles:
        raise ValueError("有序距离政策axis_profiles不符合v1固定定义")
    fixed = policy.get("fixed_nonnegative_multiplicative_metrics")
    if not isinstance(fixed, list) or fixed != sorted(set(fixed)) or any(not non_empty(item) for item in fixed):
        raise ValueError("固定长尾指标清单必须是排序后的非空唯一字符串列表")
    dynamic = policy.get("dynamic_axis_metrics")
    if not isinstance(dynamic, dict) or any(not non_empty(metric_id) for metric_id in dynamic):
        raise ValueError("动态轴指标定义无效")
    if set(fixed) & set(dynamic):
        raise ValueError("同一指标不能同时属于固定长尾和动态轴清单")
    for metric_id, rule in dynamic.items():
        allowed = rule.get("allowed_axis_semantics") if isinstance(rule, dict) else None
        if not isinstance(allowed, list) or set(allowed) != AXIS_SEMANTICS or len(allowed) != len(AXIS_SEMANTICS):
            raise ValueError(f"动态轴指标允许语义无效: {metric_id}")
        if not non_empty(rule.get("resolution_source")):
            raise ValueError(f"动态轴指标缺少resolution_source: {metric_id}")
    required_rules = {
        "raw_positions_must_be_finite",
        "log_positions_must_be_nonnegative",
        "economic_values_must_be_normalized_to_denominator_multiple",
        "candidate_may_not_choose_transform_or_scale",
        "candidate_may_not_add_support_bins",
        "mixed_axis_semantics_in_one_instance_blocks",
    }
    rules = policy.get("rules")
    if not isinstance(rules, dict) or any(rules.get(name) is not True for name in required_rules):
        raise ValueError("有序距离政策rules缺失或未启用")


def active_ordered_metrics(contract):
    result = []
    for metric in contract.get("metrics", []):
        profile = ordered_profile(metric)
        if (
            profile is not None
            and metric.get("status") != "不适用"
            and metric.get("waiver", {}).get("status") != "已批准"
            and profile.get("method") in ORDERED_METHODS
        ):
            result.append(metric)
    return result


def profile_field(metric):
    return {"hard": "hard_gate_profile", "score": "score_profile"}.get(metric.get("kind"))


def ordered_profile(metric):
    field = profile_field(metric)
    profile = metric.get(field) if field else None
    return profile if isinstance(profile, dict) else None


def ordered_instance_rows(metrics):
    rows, identities = [], set()
    for metric in metrics:
        metric_id, scope = metric.get("metric_id"), metric.get("scope")
        if not non_empty(metric_id) or not non_empty(scope):
            raise ValueError("活动有序指标缺少metric_id或scope")
        source_node_ids = metric.get("source_node_ids")
        instance_dimensions = metric.get("instance_dimensions")
        if not isinstance(source_node_ids, list) or not isinstance(instance_dimensions, dict):
            raise ValueError("活动有序指标缺少完整实例来源或维度")
        identity = (
            metric_id,
            tuple(sorted(source_node_ids)),
            tuple(sorted(instance_dimensions.items())),
        )
        if identity in identities:
            raise ValueError(f"活动有序指标实例重复: {metric_id} / {source_node_ids} / {instance_dimensions}")
        identities.add(identity)
        rows.append({
            "metric_id": metric_id,
            "scope": scope,
            "source_node_ids": sorted(source_node_ids),
            "instance_dimensions": instance_dimensions,
            "kind": metric.get("kind"),
            "profile_field": profile_field(metric),
            "axis_semantics": ordered_profile(metric).get("axis_semantics"),
        })
    return sorted(rows, key=lambda item: (
        item["metric_id"],
        item["source_node_ids"],
        sorted(item["instance_dimensions"].items()),
    ))


def resolve_axis(metric, policy):
    metric_id = metric.get("metric_id")
    profile = ordered_profile(metric)
    if profile is None:
        raise ValueError(f"有序指标缺少受支持的距离Profile: {metric_id}")
    fixed = set(policy["fixed_nonnegative_multiplicative_metrics"])
    dynamic = policy["dynamic_axis_metrics"]
    if metric_id in fixed:
        expected = "nonnegative_multiplicative"
        if profile.get("axis_semantics") not in {None, expected}:
            raise ValueError(f"固定长尾指标轴语义被改写: {metric_id}")
        return expected
    if metric_id in dynamic:
        semantics = profile.get("axis_semantics")
        if semantics not in dynamic[metric_id]["allowed_axis_semantics"]:
            raise ValueError(f"动态有序指标缺少受控axis_semantics: {metric_id}")
        return semantics
    expected = policy["default_axis_semantics"]
    if profile.get("axis_semantics") not in {None, expected}:
        raise ValueError(f"自然线性指标轴语义被改写: {metric_id}")
    return expected


def apply_profile(metric, policy):
    profile = ordered_profile(metric)
    if profile is None:
        raise ValueError(f"有序指标缺少受支持的距离Profile: {metric.get('metric_id')}")
    semantics = resolve_axis(metric, policy)
    axis = policy["axis_profiles"][semantics]
    profile.update({
        "axis_semantics": semantics,
        "ordered_distance_policy_id": policy["policy_id"],
        "position_transform": axis["position_transform"],
        "distance_normalization": axis["distance_normalization"],
        "distance_unit": axis["distance_unit"],
    })
    if semantics == "nonnegative_multiplicative":
        profile["distance_scale"] = axis["distance_scale"]
        profile.pop("distance_scale_source", None)
    else:
        profile["distance_scale_source"] = axis["distance_scale_source"]
        profile.pop("distance_scale", None)


def embedded_definition(sealed):
    return {
        "schema_version": sealed.get("source_schema_version"),
        **{field: sealed.get(field) for field in SOURCE_FIELDS},
    }


def validate_embedded_policy(contract):
    sealed = contract.get("ordered_distance_policy")
    if not isinstance(sealed, dict):
        raise ValueError("合同缺少ordered_distance_policy")
    definition = embedded_definition(sealed)
    validate_policy_definition(definition)
    metrics = active_ordered_metrics(contract)
    rows = ordered_instance_rows(metrics)
    if sealed.get("active_ordered_metric_instances") != rows:
        raise ValueError("有序距离政策活动指标实例清单与合同不一致")
    if sealed.get("active_ordered_metric_instances_sha256") != canonical_sha256(rows):
        raise ValueError("有序距离政策活动指标实例SHA-256失效")
    for metric in metrics:
        expected = json.loads(json.dumps(metric, ensure_ascii=False))
        apply_profile(expected, definition)
        expected_profile = ordered_profile(expected)
        actual_profile = ordered_profile(metric)
        for field in CONTROLLED_PROFILE_FIELDS:
            if expected_profile.get(field) != actual_profile.get(field):
                raise ValueError(f"有序指标距离字段不符合政策: {metric.get('metric_id')} / {field}")
    return rows


def validate_policy_source_binding(contract, skill_root):
    errors = []
    try:
        validate_embedded_policy(contract)
        sealed = contract["ordered_distance_policy"]
        source = sealed.get("source_path")
        if not non_empty(source) or Path(source).is_absolute() or ".." in Path(source).parts:
            raise ValueError("有序距离政策来源路径无效")
        root = Path(skill_root).resolve()
        path = (root / source).resolve()
        path.relative_to(root)
        if not path.is_file():
            raise ValueError("有序距离政策来源文件不存在")
        if hashlib.sha256(path.read_bytes()).hexdigest() != sealed.get("source_sha256"):
            raise ValueError("有序距离政策来源SHA-256失效")
        source_policy = load(path)
        validate_policy_definition(source_policy)
        expected = {
            "source_schema_version": source_policy["schema_version"],
            **{field: source_policy[field] for field in SOURCE_FIELDS},
        }
        mismatches = [field for field, value in expected.items() if sealed.get(field) != value]
        if mismatches:
            raise ValueError(f"有序距离政策合同字段与来源不一致: {','.join(mismatches)}")
    except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError) as exc:
        errors.append(str(exc))
    return errors


def apply_policy(contract, policy, policy_path):
    validate_policy_definition(policy)
    metrics = active_ordered_metrics(contract)
    for metric in metrics:
        apply_profile(metric, policy)
    rows = ordered_instance_rows(metrics)
    contract["ordered_distance_policy"] = {
        "source_schema_version": policy["schema_version"],
        **{field: policy[field] for field in SOURCE_FIELDS},
        "source_sha256": hashlib.sha256(Path(policy_path).read_bytes()).hexdigest(),
        "active_ordered_metric_instances": rows,
        "active_ordered_metric_instances_sha256": canonical_sha256(rows),
    }
    return rows


def main():
    parser = argparse.ArgumentParser(description="按轴语义政策解析 Slot 有序分布距离")
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    contract, policy = load_contract(args.contract), load(args.policy)
    rows = apply_policy(contract, policy, args.policy)
    errors = validate_policy_source_binding(contract, Path(__file__).resolve().parent.parent)
    if errors:
        raise ValueError("；".join(errors))
    write_contract(contract, args.output)
    print(json.dumps({
        "status": "通过",
        "policy_id": policy["policy_id"],
        "ordered_metric_instances": len(rows),
        "output": str(args.output),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "失败", "error": str(exc)}, ensure_ascii=False))
        sys.exit(2)
