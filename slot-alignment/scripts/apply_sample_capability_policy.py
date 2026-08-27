#!/usr/bin/env python3
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

from contract_io import load_contract, write_contract


GROUPED_METHODS = {
    "grouped_mean_absolute_error",
    "grouped_total_variation",
    "grouped_wasserstein_1d",
}
TV_METHODS = {"total_variation", "grouped_total_variation"}
WASSERSTEIN_METHODS = {"wasserstein_1d", "grouped_wasserstein_1d"}
RESIDUAL_METHODS = {"mean_absolute_error", "grouped_mean_absolute_error"}
SOURCE_FIELDS = (
    "policy_id",
    "version",
    "source_path",
    "legacy_contracts_unchanged",
    "confidence_level",
    "covered_methods",
    "noise_budget",
    "bounds",
    "multiple_testing",
    "formulas",
    "rules",
)


def load(path):
    with Path(path).open(encoding="utf-8") as stream:
        return json.load(stream)


def canonical_sha256(value):
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def non_empty(value):
    return isinstance(value, str) and bool(value.strip())


def finite(value):
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def count(value, label):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label}必须是非负整数")
    return value


def validate_policy_definition(policy):
    if not isinstance(policy, dict) or policy.get("schema_version") != "slot-alignment.sample-capability-policy.v1":
        raise ValueError("样本能力政策schema_version无效")
    for field in ("policy_id", "version", "source_path"):
        if not non_empty(policy.get(field)):
            raise ValueError(f"样本能力政策缺少{field}")
    source = Path(policy["source_path"])
    if source.is_absolute() or ".." in source.parts:
        raise ValueError("样本能力政策source_path必须是Skill内安全相对路径")
    if policy.get("legacy_contracts_unchanged") is not True:
        raise ValueError("样本能力政策必须声明旧合同不变")
    if policy.get("confidence_level") != 0.99:
        raise ValueError("样本能力政策confidence_level必须为0.99")
    methods = policy.get("covered_methods")
    expected_methods = sorted(TV_METHODS | WASSERSTEIN_METHODS | RESIDUAL_METHODS)
    if methods != expected_methods:
        raise ValueError("样本能力政策covered_methods无效")
    expected_noise = {
        "score_source": "minimum_positive_distance_anchor_at_score_95",
        "hard_source": "effective_tolerance",
        "hard_tolerance_factor": 0.5,
        "per_side_factor": 0.5,
    }
    if policy.get("noise_budget") != expected_noise:
        raise ValueError("样本能力政策noise_budget无效")
    bounds = policy.get("bounds")
    if bounds != {
        "total_variation": "bretagnolle_huber_carol",
        "wasserstein_1d": "dkw",
        "mean_absolute_residual": "coordinate_hoeffding_union_bound",
        "residual_coordinate_range_width": 2.0,
    }:
        raise ValueError("样本能力政策bounds无效")
    multiple = policy.get("multiple_testing")
    if multiple != {"sides": ["original", "formal"], "grouped_adjustment": "bonferroni_across_sides_and_active_groups"}:
        raise ValueError("样本能力政策multiple_testing无效")
    required_rules = {
        "active_reachable_support_only",
        "zero_probability_reachable_cells_count",
        "original_and_formal_must_both_pass",
        "candidate_may_not_change_support",
        "candidate_frequency_may_not_define_groups_or_samples",
        "insufficient_capacity_blocks",
        "insufficient_capacity_may_not_become_inapplicable",
    }
    rules = policy.get("rules")
    if not isinstance(rules, dict) or any(rules.get(name) is not True for name in required_rules):
        raise ValueError("样本能力政策rules缺失或未启用")
    expected_formulas = {
        "total_variation": "ceil((support_count*ln(2)+ln(1/delta))/(2*epsilon^2))",
        "wasserstein_1d": "ceil(normalized_span^2*ln(2/delta)/(2*epsilon^2))",
        "mean_absolute_residual": "ceil(range_width^2*ln(2*coordinate_count/delta)/(2*epsilon^2))",
    }
    if policy.get("formulas") != expected_formulas:
        raise ValueError("样本能力政策formulas无效")


def profile(metric):
    field = {"score": "score_profile", "hard": "hard_gate_profile"}.get(metric.get("kind"))
    value = metric.get(field) if field else None
    return value if isinstance(value, dict) else None


def anchor_pair(anchor):
    if isinstance(anchor, list) and len(anchor) == 2:
        return anchor
    if isinstance(anchor, dict):
        return [anchor.get("distance"), anchor.get("score")]
    return [None, None]


def comparison_noise_budget(metric, evaluation, policy):
    if metric.get("kind") == "score":
        distances = [
            distance
            for distance, score in map(anchor_pair, evaluation.get("anchors", []))
            if finite(distance) and distance > 0 and finite(score) and score == 95
        ]
        if not distances:
            raise ValueError("评分指标缺少95分最小正距离锚点")
        return min(distances), "score_profile.anchor_95"
    tolerance = evaluation.get("tolerance")
    if not finite(tolerance) or tolerance <= 0:
        raise ValueError("硬指标缺少有限正数生效tolerance")
    factor = policy["noise_budget"]["hard_tolerance_factor"]
    return tolerance * factor, f"hard_gate_profile.tolerance*{factor}"


def support_labels(metric, evaluation):
    method, target = evaluation.get("method"), metric.get("target")
    if method in GROUPED_METHODS:
        separator = evaluation.get("group_separator")
        if not non_empty(separator) or not isinstance(target, dict) or not target:
            raise ValueError("分组指标目标必须使用非空group_separator和对象目标")
        groups = {}
        for key in target:
            if not isinstance(key, str) or separator not in key:
                raise ValueError(f"分组指标目标字段缺少分隔符{separator}: {key}")
            group, label = key.split(separator, 1)
            if not non_empty(group) or not non_empty(label):
                raise ValueError(f"分组指标目标字段无效: {key}")
            groups.setdefault(group, []).append(label)
        return {group: labels for group, labels in sorted(groups.items())}
    if isinstance(target, list) and target:
        return {"__all__": [str(index) for index in range(len(target))]}
    if isinstance(target, dict) and target:
        return {"__all__": list(target)}
    raise ValueError("非分组指标目标必须是非空数组或对象")


def target_values(metric, evaluation, labels_by_group):
    target, method = metric.get("target"), evaluation.get("method")
    if method in GROUPED_METHODS:
        separator = evaluation["group_separator"]
        values = {
            group: [target[f"{group}{separator}{label}"] for label in labels]
            for group, labels in labels_by_group.items()
        }
    else:
        values = {"__all__": list(target if isinstance(target, list) else target.values())}
    if any(any(not finite(value) for value in group_values) for group_values in values.values()):
        raise ValueError("指标目标包含非有限数值")
    if method in TV_METHODS | WASSERSTEIN_METHODS:
        tolerance = evaluation.get("normalization_tolerance", 1e-6)
        if not finite(tolerance) or tolerance < 0 or tolerance >= 1:
            raise ValueError("分布归一化容差无效")
        for group, group_values in values.items():
            if any(value < 0 for value in group_values) or abs(sum(group_values) - 1.0) > tolerance:
                raise ValueError(f"组{group}目标必须是归一化非负概率分布")
    elif any(any(value < -1 or value > 1 for value in group_values) for group_values in values.values()):
        raise ValueError("概率残差目标必须落在[-1,1]")
    return values


def transformed_span(values, evaluation):
    if not isinstance(values, list) or len(values) < 2 or any(not finite(value) for value in values):
        raise ValueError("Wasserstein指标缺少至少两个有限bin_positions")
    raw = [float(value) for value in values]
    if any(right <= left for left, right in zip(raw, raw[1:])):
        raise ValueError("Wasserstein指标bin_positions必须严格递增")
    transform = evaluation.get("position_transform", "identity")
    if transform == "identity":
        transformed = raw
    elif transform == "log10_1p":
        if any(value < 0 for value in raw):
            raise ValueError("log10_1p位置必须大于等于0")
        transformed = [math.log10(1.0 + value) for value in raw]
    else:
        raise ValueError(f"不支持的位置变换: {transform}")
    span = transformed[-1] - transformed[0]
    normalization = evaluation.get("distance_normalization")
    if normalization == "sealed_support_span":
        scale = span
    elif normalization == "fixed_transform_unit":
        scale = evaluation.get("distance_scale")
        if not finite(scale) or scale <= 0:
            raise ValueError("fixed_transform_unit缺少有限正数distance_scale")
    else:
        raise ValueError(f"不支持的距离归一化: {normalization}")
    if span <= 0 or scale <= 0:
        raise ValueError("Wasserstein归一化跨度必须大于0")
    return span / scale


def normalized_spans(method, labels_by_group, evaluation):
    if method not in WASSERSTEIN_METHODS:
        return {}
    if method == "wasserstein_1d":
        positions = evaluation.get("bin_positions")
        if len(labels_by_group["__all__"]) != len(positions or []):
            raise ValueError("Wasserstein目标与bin_positions数量不一致")
        return {"__all__": transformed_span(positions, evaluation)}
    positions_by_group = evaluation.get("bin_positions_by_group")
    if not isinstance(positions_by_group, dict) or set(positions_by_group) != set(labels_by_group):
        raise ValueError("分组Wasserstein缺少完整bin_positions_by_group")
    result = {}
    for group, labels in labels_by_group.items():
        positions = positions_by_group[group]
        if not isinstance(positions, dict) or set(positions) != set(labels):
            raise ValueError(f"分组Wasserstein组{group}的位置键与目标支持不一致")
        result[group] = transformed_span([positions[label] for label in labels], evaluation)
    return result


def sample_counts(metric, labels_by_group, grouped):
    raw = metric.get("sample_capability_input")
    if not isinstance(raw, dict):
        raise ValueError("活动受检指标缺少sample_capability_input")
    original_total = count(raw.get("original_sample_count"), "original_sample_count")
    formal_total = count(raw.get("formal_sample_count"), "formal_sample_count")
    if not grouped:
        if "original_group_sample_counts" in raw or "formal_group_sample_counts" in raw:
            raise ValueError("非分组指标不得提供group_sample_counts")
        return {"__all__": original_total}, {"__all__": formal_total}, original_total, formal_total
    result = []
    for field, total in (("original_group_sample_counts", original_total), ("formal_group_sample_counts", formal_total)):
        values = raw.get(field)
        if not isinstance(values, dict) or set(values) != set(labels_by_group):
            raise ValueError(f"{field}必须与活动条件组完全一致")
        values = {group: count(value, f"{field}.{group}") for group, value in values.items()}
        if sum(values.values()) != total:
            raise ValueError(f"{field}合计必须等于对应sample_count")
        result.append(values)
    return result[0], result[1], original_total, formal_total


def required_count(method, support_count, delta, epsilon, normalized_span, residual_width):
    if support_count < 1:
        raise ValueError("活动评分支持不能为空")
    if method in TV_METHODS | WASSERSTEIN_METHODS and support_count < 2:
        raise ValueError("活动分布评分支持至少需要2项")
    if method in TV_METHODS:
        raw = (support_count * math.log(2.0) + math.log(1.0 / delta)) / (2.0 * epsilon * epsilon)
        return math.ceil(raw), "bretagnolle_huber_carol"
    if method in WASSERSTEIN_METHODS:
        raw = normalized_span * normalized_span * math.log(2.0 / delta) / (2.0 * epsilon * epsilon)
        return math.ceil(raw), "dkw"
    if method in RESIDUAL_METHODS:
        raw = residual_width * residual_width * math.log(2.0 * support_count / delta) / (2.0 * epsilon * epsilon)
        return math.ceil(raw), "coordinate_hoeffding_union_bound"
    raise ValueError(f"不支持的样本能力方法: {method}")


def metric_capability(metric, policy):
    metric_id, scope = metric.get("metric_id"), metric.get("scope")
    evaluation = profile(metric)
    if not non_empty(metric_id) or not non_empty(scope) or evaluation is None:
        raise ValueError("受检指标缺少metric_id、scope或评价Profile")
    method = evaluation.get("method")
    if method not in policy["covered_methods"]:
        raise ValueError(f"指标方法不受样本能力政策支持: {method}")
    if metric.get("status") == "不适用":
        raise ValueError("包含sample_capability_input的指标不得标记不适用")
    labels = support_labels(metric, evaluation)
    target_values(metric, evaluation, labels)
    grouped = method in GROUPED_METHODS
    original, formal, original_total, formal_total = sample_counts(metric, labels, grouped)
    spans = normalized_spans(method, labels, evaluation)
    budget, budget_source = comparison_noise_budget(metric, evaluation, policy)
    epsilon = budget * policy["noise_budget"]["per_side_factor"]
    if not finite(epsilon) or epsilon <= 0:
        raise ValueError("逐侧噪声预算必须为有限正数")
    group_count = len(labels)
    delta = (1.0 - policy["confidence_level"]) / (2.0 * group_count)
    width = policy["bounds"]["residual_coordinate_range_width"]
    required, family = {}, None
    for group, group_labels in labels.items():
        required[group], current_family = required_count(
            method,
            len(group_labels),
            delta,
            epsilon,
            spans.get(group, 1.0),
            width,
        )
        family = family or current_family
    blockers = []
    for side, actual in (("原版", original), ("FORMAL", formal)):
        for group in labels:
            if actual[group] < required[group]:
                blockers.append({
                    "side": side,
                    "group": group,
                    "required": required[group],
                    "actual": actual[group],
                    "shortfall": required[group] - actual[group],
                })
    support_counts = {group: len(group_labels) for group, group_labels in labels.items()}
    original_ratio = original_total / sum(support_counts.values())
    formal_ratio = formal_total / sum(support_counts.values())
    return {
        "policy_id": policy["policy_id"],
        "method": method,
        "bound_family": family,
        "confidence_level": policy["confidence_level"],
        "comparison_noise_budget": budget,
        "comparison_noise_budget_source": budget_source,
        "per_side_error_budget": epsilon,
        "per_side_group_failure_probability": delta,
        "active_group_count": group_count,
        "active_support_count": sum(support_counts.values()),
        "max_support_per_group": max(support_counts.values()),
        "support_count_by_group": support_counts,
        "support_sha256": canonical_sha256(labels),
        "normalized_span_by_group": spans,
        "required_sample_count_by_group": required,
        "original_required_sample_count": sum(required.values()),
        "original_actual_sample_count": original_total,
        "original_sample_count_by_group": original,
        "original_min_group_sample_count": min(original.values()),
        "original_samples_per_active_support": original_ratio,
        "original_min_group_samples_per_support": min(original[group] / support_counts[group] for group in labels),
        "formal_required_sample_count": sum(required.values()),
        "formal_actual_sample_count": formal_total,
        "formal_sample_count_by_group": formal,
        "formal_min_group_sample_count": min(formal.values()),
        "formal_samples_per_active_support": formal_ratio,
        "formal_min_group_samples_per_support": min(formal[group] / support_counts[group] for group in labels),
        "blocking_reasons": blockers,
        "status": "通过" if not blockers else "阻塞",
        "input_sha256": canonical_sha256(metric["sample_capability_input"]),
    }


def apply_policy(contract, policy, policy_path):
    validate_policy_definition(policy)
    active, blockers = [], []
    metrics = contract.get("metrics")
    if not isinstance(metrics, list):
        raise ValueError("metric_contract.metrics必须是数组")
    for metric in metrics:
        evaluation = profile(metric) if isinstance(metric, dict) else None
        if not isinstance(metric, dict) or evaluation is None or evaluation.get("method") not in policy["covered_methods"]:
            continue
        inactive = metric.get("status") == "不适用" or metric.get("waiver", {}).get("status") == "已批准"
        if inactive:
            if "sample_capability_input" in metric:
                raise ValueError(f"不适用或已豁免指标不得提供sample_capability_input: {metric.get('metric_id')}")
            continue
        try:
            capability = metric_capability(metric, policy)
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"样本能力输入无效: {metric.get('metric_id')} / {metric.get('scope')} / {exc}") from exc
        metric["sample_capability"] = capability
        row = {
            "metric_id": metric.get("metric_id"),
            "scope": metric.get("scope"),
            "source_node_ids": sorted(metric.get("source_node_ids", [])),
            "instance_dimensions": metric.get("instance_dimensions", {}),
            "kind": metric.get("kind"),
            "method": evaluation.get("method"),
            "sample_capability_sha256": canonical_sha256(capability),
        }
        active.append(row)
        blockers.extend({
            "metric_id": row["metric_id"],
            "scope": row["scope"],
            "source_node_ids": row["source_node_ids"],
            "instance_dimensions": row["instance_dimensions"],
            **item,
        } for item in capability["blocking_reasons"])
    active.sort(key=lambda item: (
        item["metric_id"],
        item["source_node_ids"],
        sorted(item["instance_dimensions"].items()),
    ))
    contract["sample_capability_policy"] = {
        "source_schema_version": policy["schema_version"],
        **{field: policy[field] for field in SOURCE_FIELDS},
        "source_sha256": hashlib.sha256(Path(policy_path).read_bytes()).hexdigest(),
        "active_metric_instances": active,
        "active_metric_instances_sha256": canonical_sha256(active),
        "blocking_reasons": blockers,
        "status": "通过" if not blockers else "阻塞",
    }
    contract["status"] = "已完成" if not blockers else "阻塞"
    return blockers


def main():
    parser = argparse.ArgumentParser(description="按版本化统计上界生成指标样本能力门禁")
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--automatic-waiver-policy", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    contract, policy = load_contract(args.contract), load(args.policy)
    blockers = apply_policy(contract, policy, args.policy)
    automatic_waivers = []
    if args.automatic_waiver_policy:
        from apply_automatic_waiver_policy import apply_insufficient_data_waivers

        automatic_policy = load(args.automatic_waiver_policy)
        automatic_waivers = apply_insufficient_data_waivers(
            contract,
            automatic_policy,
            args.automatic_waiver_policy,
            Path(__file__).resolve().parent.parent,
        )
        blockers = contract.get("sample_capability_policy", {}).get("blocking_reasons", [])
    write_contract(contract, args.output)
    result = {
        "status": "通过" if not blockers else "阻塞",
        "policy_id": policy.get("policy_id"),
        "metric_instances": len(contract["sample_capability_policy"]["active_metric_instances"]),
        "automatic_waiver_count": len(automatic_waivers),
        "blocking_reasons": blockers,
        "output": str(args.output),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not blockers else 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError, OverflowError) as exc:
        print(json.dumps({"status": "失败", "error": str(exc)}, ensure_ascii=False))
        sys.exit(2)
