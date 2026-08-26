#!/usr/bin/env python3
import argparse
import copy
import hashlib
import json
import math
import sys
from pathlib import Path

from apply_ordered_distance_policy import validate_policy_source_binding as validate_ordered_distance_policy
from apply_sample_capability_policy import apply_policy as apply_sample_capability_policy
from apply_sample_capability_policy import metric_capability, validate_policy_definition
from apply_score_group_weight_policy import validate_embedded_policy


DISTRIBUTION_SCORE_METHODS = {
    "total_variation",
    "grouped_total_variation",
    "wasserstein_1d",
    "grouped_wasserstein_1d",
}

SAMPLE_CAPABILITY_SUMMARY_FIELDS = (
    "policy_id",
    "version",
    "source_path",
    "source_sha256",
    "active_metric_instances_sha256",
    "status",
)


def load(path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def schema_is(contract, version):
    return str(contract.get("schema_version", "")) == version


def safe_policy_path(skill_root, source_path):
    if not isinstance(source_path, str) or not source_path.strip():
        raise ValueError("样本能力政策缺少source_path")
    relative = Path(source_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("样本能力政策source_path必须是Skill内安全相对路径")
    root = Path(skill_root).resolve()
    path = (root / relative).resolve()
    if path != root and root not in path.parents:
        raise ValueError("样本能力政策source_path越出Skill目录")
    if not path.is_file():
        raise ValueError("样本能力政策源文件不存在")
    return path


def sample_capability_summary(contract):
    policy = contract.get("sample_capability_policy")
    if not isinstance(policy, dict):
        return None
    return {field: policy.get(field) for field in SAMPLE_CAPABILITY_SUMMARY_FIELDS}


def validate_sample_capability_binding(contract, skill_root):
    """复算1.3合同的政策绑定和逐指标样本能力；1.2及更早版本保持原行为。"""
    if not schema_is(contract, "1.3"):
        return []
    actual_policy = contract.get("sample_capability_policy")
    if not isinstance(actual_policy, dict):
        return ["1.3指标合同缺少sample_capability_policy"]
    try:
        policy_path = safe_policy_path(skill_root, actual_policy.get("source_path"))
        policy = load(policy_path)
        validate_policy_definition(policy)
        if actual_policy.get("source_sha256") != sha(policy_path):
            raise ValueError("样本能力政策源hash失效")
        expected = copy.deepcopy(contract)
        expected.pop("sample_capability_policy", None)
        for metric in expected.get("metrics", []):
            if isinstance(metric, dict):
                metric.pop("sample_capability", None)
        apply_sample_capability_policy(expected, policy, policy_path)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return [f"样本能力政策复算失败: {exc}"]
    errors = []
    if actual_policy != expected.get("sample_capability_policy"):
        errors.append("样本能力政策摘要、活动实例或阻塞结果被篡改")
    actual_metrics = {key(item): item for item in contract.get("metrics", []) if isinstance(item, dict)}
    expected_metrics = {key(item): item for item in expected.get("metrics", []) if isinstance(item, dict)}
    for item_key in sorted(set(actual_metrics) | set(expected_metrics)):
        actual = actual_metrics.get(item_key, {}).get("sample_capability")
        wanted = expected_metrics.get(item_key, {}).get("sample_capability")
        if actual != wanted:
            errors.append(f"逐指标样本能力被篡改或缺失: {item_key[0]} / {item_key[1]}")
    if expected.get("sample_capability_policy", {}).get("status") != "通过":
        errors.append("指标合同计划样本能力不足")
    return errors


def validate_formal_sample_capability(contract, formal, skill_root):
    """用FORMAL实际逐指标、逐组样本复验1.3合同，不信任阶段2计划中的FORMAL计数。"""
    if not schema_is(contract, "1.3"):
        return []
    if not isinstance(formal, dict) or formal.get("schema_version") != "1.2":
        return ["1.3指标合同必须使用formal_result.schema_version=1.2"]
    errors = validate_sample_capability_binding(contract, skill_root)
    if errors:
        return errors
    policy_summary = sample_capability_summary(contract)
    formal_scorecard = formal.get("scorecard") if isinstance(formal, dict) else None
    if not isinstance(formal_scorecard, dict) or formal_scorecard.get("sample_capability_policy") != policy_summary:
        errors.append("FORMAL内嵌scorecard的样本能力政策摘要与合同不一致")
    sample = formal.get("sample") if isinstance(formal, dict) else None
    rows = sample.get("metric_sample_counts") if isinstance(sample, dict) else None
    if not isinstance(rows, list):
        return errors + ["FORMAL缺少逐指标实际样本计数"]
    row_map = {}
    for row in rows:
        if not isinstance(row, dict):
            errors.append("FORMAL逐指标样本计数必须是对象")
            continue
        row_key = key(row)
        if not all(isinstance(value, str) and value.strip() for value in row_key):
            errors.append("FORMAL逐指标样本计数缺少metric_id或scope")
        elif row_key in row_map:
            errors.append(f"FORMAL逐指标样本计数重复: {row_key[0]} / {row_key[1]}")
        else:
            row_map[row_key] = row
    active = {
        (item["metric_id"], item["scope"])
        for item in contract["sample_capability_policy"].get("active_metric_instances", [])
    }
    for missing in sorted(active - set(row_map)):
        errors.append(f"FORMAL缺少指标实际样本计数: {missing[0]} / {missing[1]}")
    for extra in sorted(set(row_map) - active):
        errors.append(f"FORMAL存在额外指标样本计数: {extra[0]} / {extra[1]}")
    if errors:
        return errors
    policy_path = safe_policy_path(skill_root, contract["sample_capability_policy"]["source_path"])
    policy = load(policy_path)
    metric_map = {key(item): item for item in contract.get("metrics", []) if isinstance(item, dict)}
    for item_key in sorted(active):
        metric = copy.deepcopy(metric_map[item_key])
        row = row_map[item_key]
        inputs = metric.get("sample_capability_input")
        if not isinstance(inputs, dict):
            errors.append(f"指标缺少原版样本能力输入: {item_key[0]} / {item_key[1]}")
            continue
        inputs["formal_sample_count"] = row.get("sample_count")
        method = (metric.get("hard_gate_profile") or metric.get("score_profile") or {}).get("method")
        grouped = method in {"grouped_mean_absolute_error", "grouped_total_variation", "grouped_wasserstein_1d"}
        group_counts = row.get("group_sample_counts")
        if grouped:
            inputs["formal_group_sample_counts"] = group_counts
        elif group_counts not in (None, {}):
            errors.append(f"非分组指标不得提供FORMAL组样本计数: {item_key[0]} / {item_key[1]}")
            continue
        try:
            capability = metric_capability(metric, policy)
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            errors.append(f"FORMAL实际样本能力输入无效: {item_key[0]} / {item_key[1]} / {exc}")
            continue
        if capability.get("status") != "通过":
            shortfall = sum(item.get("shortfall", 0) for item in capability.get("blocking_reasons", []))
            errors.append(f"FORMAL实际样本能力不足: {item_key[0]} / {item_key[1]} / 缺少{shortfall}个样本")
    return errors


def key(item):
    return item.get("metric_id", ""), item.get("scope", "")


def scalar(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("需要有限数值")
    try:
        result = float(value)
    except (OverflowError, TypeError, ValueError) as exc:
        raise ValueError("需要有限数值") from exc
    if not math.isfinite(result):
        raise ValueError("需要有限数值")
    return result


def positive_finite(value, name):
    result = scalar(value)
    if result <= 0:
        raise ValueError(f"{name}必须是有限正数")
    return result


def normalization_tolerance(profile):
    value = scalar(profile.get("normalization_tolerance", 1e-6))
    if value < 0 or value >= 1:
        raise ValueError("normalization_tolerance必须在[0,1)内")
    return value


def numeric_items(target, value):
    if isinstance(target, list) and isinstance(value, list):
        if len(target) != len(value) or not target:
            raise ValueError("向量维度不一致或为空")
        return [(str(index), scalar(a), scalar(b)) for index, (a, b) in enumerate(zip(target, value))]
    if isinstance(target, dict) and isinstance(value, dict):
        if set(target) != set(value) or not target:
            raise ValueError("对象字段不一致或为空")
        return [(str(name), scalar(target[name]), scalar(value[name])) for name in sorted(target)]
    raise ValueError("需要同结构的数值数组或对象")


def probability_vector(value, tolerance=1e-6):
    if not isinstance(value, list) or not value:
        raise ValueError("概率分布必须是非空数组")
    result = [scalar(item) for item in value]
    if any(item < 0 for item in result):
        raise ValueError("概率分布不能包含负数")
    total = sum(result)
    if total <= 0:
        raise ValueError("概率分布总和必须大于0")
    if abs(total - 1.0) > tolerance:
        raise ValueError("概率分布未归一化")
    return [item / total for item in result]


def ordered_wasserstein(expected, actual, positions, profile, label="wasserstein_1d"):
    if not isinstance(expected, list) or not isinstance(actual, list) or len(expected) != len(actual):
        raise ValueError(f"{label}有序分布桶不一致")
    if not isinstance(positions, list) or len(positions) != len(expected) or len(positions) < 2:
        raise ValueError(f"{label}需要与分布等长且至少两个值的已密封bin_positions")
    raw_positions = [scalar(item) for item in positions]
    if any(right <= left for left, right in zip(raw_positions, raw_positions[1:])):
        raise ValueError(f"{label}的bin_positions必须严格递增")
    transform = profile.get("position_transform", "identity")
    if transform == "identity":
        transformed_positions = raw_positions
    elif transform == "log10_1p":
        if any(item < 0 for item in raw_positions):
            raise ValueError(f"{label}的log10_1p原始位置必须大于等于0")
        transformed_positions = [math.log10(1.0 + item) for item in raw_positions]
    else:
        raise ValueError(f"{label}不支持的位置变换: {transform}")
    if any(right <= left for left, right in zip(transformed_positions, transformed_positions[1:])):
        raise ValueError(f"{label}变换后的位置必须严格递增")
    normalization = profile.get("distance_normalization", "sealed_support_span")
    if normalization == "sealed_support_span":
        if transform != "identity":
            raise ValueError(f"{label}的sealed_support_span只允许identity位置变换")
        scale = transformed_positions[-1] - transformed_positions[0]
        if scale <= 0:
            raise ValueError(f"{label}的sealed_support_span必须大于0")
    elif normalization == "fixed_transform_unit":
        if transform != "log10_1p":
            raise ValueError(f"{label}的fixed_transform_unit只允许log10_1p位置变换")
        scale = positive_finite(profile.get("distance_scale"), f"{label}.distance_scale")
        if not math.isclose(scale, 1.0, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError(f"{label}的fixed_transform_unit距离尺度必须为1")
    else:
        raise ValueError(f"{label}不支持的距离归一化: {normalization}")
    tolerance = normalization_tolerance(profile)
    expected = probability_vector(expected, tolerance)
    actual = probability_vector(actual, tolerance)
    cumulative = result = 0.0
    widths = (right - left for left, right in zip(transformed_positions, transformed_positions[1:]))
    for index, width in enumerate(widths):
        cumulative += expected[index] - actual[index]
        result += abs(cumulative) * width
    return result / scale


def sealed_group_weights(profile, groups, method):
    if profile.get("group_weight_source") != "task_contract":
        raise ValueError(f"{method}必须从task_contract密封group_weights")
    weights = profile.get("group_weights")
    if not isinstance(weights, dict) or set(weights) != set(groups):
        raise ValueError(f"{method}的group_weights必须与条件组完全一致")
    weights = {group: positive_finite(weights[group], f"{method}的组{group}权重") for group in groups}
    total = sum(weights.values())
    if total <= 0:
        raise ValueError(f"{method}的group_weights总和必须大于0")
    if abs(total - 1.0) > normalization_tolerance(profile):
        raise ValueError(f"{method}的group_weights未归一化")
    return {group: weight / total for group, weight in weights.items()}


def sealed_group_separator(profile, method):
    separator = profile.get("group_separator")
    if not isinstance(separator, str) or not separator.strip():
        raise ValueError(f"{method}需要非空group_separator")
    return separator


def grouped_support_counts(target, profile, method):
    if not isinstance(target, dict) or not target:
        raise ValueError(f"{method}目标必须是非空对象")
    separator = sealed_group_separator(profile, method)
    groups = {}
    for field in target:
        if separator not in field:
            raise ValueError(f"分组字段缺少分隔符{separator}: {field}")
        group, bin_name = field.split(separator, 1)
        if not group.strip() or not bin_name.strip():
            raise ValueError(f"分组字段格式无效: {field}")
        groups.setdefault(group, set()).add(bin_name)
    return {group: len(bins) for group, bins in groups.items()}


def validate_reachable_support(metric):
    profile = metric.get("score_profile", {})
    method = profile.get("method")
    if method not in DISTRIBUTION_SCORE_METHODS:
        return
    support_status = profile.get("reachable_support_status")
    if support_status == "all_degenerate":
        if metric.get("status") != "不适用" or metric.get("inapplicability_reason_code") != "degenerate_reachable_support":
            raise ValueError("全部退化支持集的评分指标必须标记不适用")
        if profile.get("reachable_support_source") != "task_contract":
            raise ValueError("退化支持集必须由task_contract密封")
        return
    if metric.get("status") == "不适用":
        return
    if profile.get("reachable_support_source") != "task_contract" or support_status != "active":
        raise ValueError("评分分布缺少task_contract密封的有效可达支持")
    target = metric.get("target")
    if method in {"total_variation", "wasserstein_1d"}:
        if not isinstance(target, list) or len(target) < 2:
            raise ValueError("评分分布的有效可达支持至少需要2项")
    else:
        counts = grouped_support_counts(target, profile, method)
        degenerate = sorted(group for group, count in counts.items() if count < 2)
        if degenerate:
            raise ValueError(f"分组评分只允许保留支持至少2项的活动组: {','.join(degenerate)}")
    distance(method, target, target, profile.get("zero_floor", 1e-12), profile)


def distance(method, target, value, zero_floor=1e-12, profile=None):
    profile = profile or {}
    if method == "absolute_error":
        return abs(scalar(value) - scalar(target))
    if method == "relative_error":
        t = scalar(target)
        floor = positive_finite(zero_floor, "relative_error.zero_floor")
        return abs(scalar(value) - t) / max(abs(t), floor)
    if method == "range_error":
        low, high, val = scalar(target["min"]), scalar(target["max"]), scalar(value)
        if low > high:
            raise ValueError("range_error目标区间min不能大于max")
        if low <= val <= high:
            return 0.0
        return low - val if val < low else val - high
    if method == "total_variation":
        if not isinstance(target, list) or not isinstance(value, list) or len(target) != len(value):
            raise ValueError("分布桶不一致")
        tolerance = normalization_tolerance(profile)
        expected = probability_vector(target, tolerance)
        actual = probability_vector(value, tolerance)
        return 0.5 * sum(abs(a - b) for a, b in zip(expected, actual))
    if method == "wasserstein_1d":
        return ordered_wasserstein(target, value, profile.get("bin_positions"), profile)
    if method == "mean_absolute_error":
        items = numeric_items(target, value)
        return sum(abs(a - b) for _, a, b in items) / len(items)
    if method == "max_absolute_error":
        return max(abs(a - b) for _, a, b in numeric_items(target, value))
    if method == "grouped_mean_absolute_error":
        if not isinstance(target, dict) or not isinstance(value, dict):
            raise ValueError("分组平均绝对差需要对象目标和对象测量")
        items = numeric_items(target, value)
        separator = sealed_group_separator(profile, method)
        groups = {}
        for name, expected, actual in items:
            if separator not in name:
                raise ValueError(f"分组字段缺少分隔符{separator}: {name}")
            group, field = name.split(separator, 1)
            if not group.strip() or not field.strip():
                raise ValueError(f"分组字段格式无效: {name}")
            groups.setdefault(group, []).append((expected, actual))
        weights = sealed_group_weights(profile, groups, method)
        return sum(
            weights[group] * sum(abs(expected - actual) for expected, actual in values) / len(values)
            for group, values in groups.items()
        )
    if method == "grouped_total_variation":
        if not isinstance(target, dict) or not isinstance(value, dict):
            raise ValueError("分组总变差需要对象目标和对象测量")
        items = numeric_items(target, value)
        separator = sealed_group_separator(profile, method)
        tolerance = normalization_tolerance(profile)
        groups = {}
        for name, expected, actual in items:
            if separator not in name:
                raise ValueError(f"分组字段缺少分隔符{separator}: {name}")
            group = name.split(separator, 1)[0]
            groups.setdefault(group, []).append((expected, actual))
        weights = sealed_group_weights(profile, groups, method)
        weighted_sum = weight_sum = 0.0
        for group, values in groups.items():
            if any(a < 0 or b < 0 for a, b in values):
                raise ValueError(f"分组概率包含负数: {group}")
            target_sum = sum(a for a, _ in values)
            value_sum = sum(b for _, b in values)
            if target_sum <= 0 or value_sum <= 0:
                raise ValueError(f"分组概率总和必须大于0: {group}")
            if abs(target_sum - 1.0) > tolerance or abs(value_sum - 1.0) > tolerance:
                raise ValueError(f"分组概率未归一化: {group}")
            group_distance = 0.5 * sum(abs(a / target_sum - b / value_sum) for a, b in values)
            weighted_sum += group_distance * weights[group]
            weight_sum += weights[group]
        return weighted_sum / weight_sum
    if method == "grouped_wasserstein_1d":
        if not isinstance(target, dict) or not isinstance(value, dict):
            raise ValueError("分组Wasserstein需要对象目标和对象测量")
        numeric_items(target, value)
        separator = sealed_group_separator(profile, method)
        groups = {}
        for field in sorted(target):
            if separator not in field:
                raise ValueError(f"分组字段缺少分隔符{separator}: {field}")
            group, bin_name = field.split(separator, 1)
            if not group.strip() or not bin_name.strip():
                raise ValueError(f"分组字段格式无效: {field}")
            groups.setdefault(group, {})[bin_name] = (scalar(target[field]), scalar(value[field]))
        if profile.get("bin_positions_source") != "task_contract":
            raise ValueError("grouped_wasserstein_1d必须从task_contract密封bin_positions_by_group")
        positions_by_group = profile.get("bin_positions_by_group")
        if not isinstance(positions_by_group, dict) or set(positions_by_group) != set(groups):
            raise ValueError("bin_positions_by_group必须与条件组完全一致")
        group_weights = sealed_group_weights(profile, groups, method)
        weighted_sum = weight_sum = 0.0
        for group in sorted(groups):
            position_map = positions_by_group[group]
            if not isinstance(position_map, dict) or set(position_map) != set(groups[group]):
                raise ValueError(f"组{group}的bin_positions必须与实际档位完全一致")
            ordered_bins = sorted(position_map, key=lambda name: scalar(position_map[name]))
            positions = [position_map[name] for name in ordered_bins]
            expected = [groups[group][name][0] for name in ordered_bins]
            actual = [groups[group][name][1] for name in ordered_bins]
            group_distance = ordered_wasserstein(
                expected, actual, positions, profile, f"grouped_wasserstein_1d组{group}"
            )
            weight = group_weights[group]
            weighted_sum += group_distance * weight
            weight_sum += weight
        return weighted_sum / weight_sum
    raise ValueError(f"不支持的距离方法: {method}")


def anchors(profile):
    result = []
    for item in profile.get("anchors", []):
        if isinstance(item, dict):
            pair = item.get("distance"), item.get("score")
        elif isinstance(item, list) and len(item) == 2:
            pair = item
        else:
            raise ValueError("评分锚点格式无效")
        result.append((scalar(pair[0]), scalar(pair[1])))
    if len(result) < 2:
        raise ValueError("评分锚点不足")
    if any(distance_value < 0 for distance_value, _ in result):
        raise ValueError("评分锚点距离不能小于0")
    if any(score < 0 or score > 100 for _, score in result):
        raise ValueError("评分锚点分数必须在0至100之间")
    if any(right[0] <= left[0] for left, right in zip(result, result[1:])):
        raise ValueError("评分锚点距离必须严格递增")
    if any(right[1] >= left[1] for left, right in zip(result, result[1:])):
        raise ValueError("评分锚点分数必须严格递减")
    if result[0] != (0.0, 100.0):
        raise ValueError("评分锚点首点必须为距离0、得分100")
    return result


def score_from_distance(value, profile):
    points = anchors(profile)
    if value <= points[0][0]:
        return points[0][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if value <= x1:
            return y0 + (value - x0) * (y1 - y0) / (x1 - x0)
    return points[-1][1]


def band(score):
    if score is None:
        return "无有效评分"
    if score >= 95:
        return "高度对齐"
    if score >= 85:
        return "对齐通过"
    if score >= 70:
        return "轻度偏差"
    if score >= 50:
        return "明显偏差"
    return "严重偏差"


def hard_tolerance(contract, metric, profile):
    effective = profile.get("tolerance")
    if effective is None:
        raise ValueError("硬指标缺少已解析容差")
    effective = scalar(effective)
    policy = contract.get("hard_gate_tolerance_policy")
    if not policy:
        return effective, 1.0, effective, None
    metric_id = metric.get("metric_id", "")
    base = scalar(profile.get("base_tolerance"))
    expected_factor = float(policy.get("metric_factors", {}).get(metric_id, policy.get("default_factor", 1.0)))
    actual_factor = scalar(profile.get("tolerance_factor"))
    if profile.get("tolerance_policy_id") != policy.get("policy_id"):
        raise ValueError("硬指标政策ID与合同不一致")
    if metric_id in policy.get("locked_metrics", []) and actual_factor != 1.0:
        raise ValueError("锁定硬指标系数必须为1.0")
    if not math.isclose(actual_factor, expected_factor, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError("硬指标系数与政策不一致")
    expected = base * actual_factor
    if not math.isclose(effective, expected, rel_tol=1e-12, abs_tol=1e-15):
        raise ValueError("生效容差不等于基础容差乘系数")
    return base, actual_factor, effective, policy.get("policy_id")


def field_consistency_issues(profile, target, candidate):
    if profile.get("method") != "field_consistency_gate":
        return None, None
    if not isinstance(target, dict) or not target:
        return "逐字段一致性门禁缺少目标对象", None
    if not isinstance(candidate, dict):
        return "逐字段一致性门禁缺少候选对象", None
    missing_fields = sorted(set(target) - set(candidate))
    if missing_fields:
        return f"逐字段一致性门禁缺少字段: {','.join(missing_fields)}", None
    failed = []
    exact_fields = profile.get("exact_match_fields", [])
    if not isinstance(exact_fields, list) or any(not isinstance(field, str) or not field.strip() for field in exact_fields):
        return "逐字段一致性门禁的exact_match_fields无效", None
    missing_exact = sorted(field for field in exact_fields if field not in target or field not in candidate)
    if missing_exact:
        return f"逐字段一致性门禁缺少精确比对字段: {','.join(missing_exact)}", None
    for field in exact_fields:
        if candidate[field] != target[field]:
            failed.append(f"{field}:期望{target[field]},实际{candidate[field]}")
    allowed = {"符合", "有证据不适用"}
    for field in sorted(set(target) | set(candidate)):
        if not field.endswith("_status"):
            continue
        expected, actual = target.get(field), candidate.get(field)
        if actual not in allowed or (expected is not None and actual != expected):
            failed.append(f"{field}={actual}")
    return None, (f"逐字段一致性门禁不符合: {','.join(failed)}" if failed else None)


def main():
    parser = argparse.ArgumentParser(description="确定性复算 Slot 对齐评分")
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--measurements", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    contract, measured = load(args.contract), load(args.measurements)
    measurement_items = measured.get("measurements", [])
    measurements = {key(x): x for x in measurement_items}
    hard_gates, scores, audits, blockers = [], [], [], []
    if len(measurements) != len(measurement_items):
        blockers.append({"metric_id": "*", "scope": "*", "reason": "测量中存在重复metric_id+scope"})
    contract_keys = [key(item) for item in contract.get("metrics", [])]
    if len(set(contract_keys)) != len(contract_keys):
        blockers.append({"metric_id": "*", "scope": "*", "reason": "指标合同中存在重复metric_id+scope"})
    modern_contract = contract.get("schema_version") not in {"1.0", "1.1"}
    ordered_policy = contract.get("ordered_distance_policy")
    skill_root = Path(__file__).resolve().parent.parent
    if modern_contract:
        for reason in validate_ordered_distance_policy(contract, skill_root):
            blockers.append({"metric_id": "*", "scope": "*", "reason": reason})
    for reason in validate_sample_capability_binding(contract, skill_root):
        blockers.append({"metric_id": "*", "scope": "*", "reason": reason})
    waiver_count = 0
    for metric in sorted(contract.get("metrics", []), key=key):
        kind = metric.get("kind")
        if kind not in {"hard", "score", "audit"}:
            continue
        item_key = key(metric)
        measurement = measurements.get(item_key)
        waiver = metric.get("waiver", {})
        waived = waiver.get("status") == "已批准"
        not_applicable = metric.get("status") == "不适用"
        if waived:
            waiver_count += 1
        if kind == "score" and contract.get("schema_version") not in {"1.0", "1.1"}:
            try:
                validate_reachable_support(metric)
            except (TypeError, ValueError) as exc:
                blockers.append({"metric_id": item_key[0], "scope": item_key[1], "reason": str(exc)})
                continue
        if not_applicable:
            continue
        if kind == "audit":
            profile = metric.get("audit_profile", {})
            audit_status = measurement.get("status", "有效") if measurement else "缺失"
            candidate = measurement.get("value") if measurement else None
            result = {
                "metric_id": item_key[0],
                "name_zh": metric.get("name_zh", item_key[0]),
                "scope": item_key[1],
                "target": metric.get("target"),
                "candidate": candidate,
                "status": "已豁免" if waived else audit_status,
                "waiver": waiver,
                "blocking_on_missing": bool(profile.get("blocking_on_missing")),
                "blocking_on_mismatch": bool(profile.get("blocking_on_mismatch")),
            }
            audits.append(result)
            if waived:
                continue
            insufficient_status = profile.get("insufficient_sample_status", "置信不足")
            insufficient = audit_status in {insufficient_status, "样本不足", "置信不足"}
            missing = measurement is None or audit_status in {"缺失", "无效", "计算异常"} or (candidate is None and not insufficient)
            required_status = profile.get("required_result_status")
            field_missing, field_mismatch = field_consistency_issues(profile, metric.get("target"), candidate) if not missing else (None, None)
            mismatch = (
                audit_status in {"不符合", "不通过", "失败", "阻塞"}
                or (required_status is not None and audit_status != required_status and not insufficient and not missing)
            )
            if (missing or field_missing) and profile.get("blocking_on_missing"):
                blockers.append({"metric_id": item_key[0], "scope": item_key[1], "reason": field_missing or "必需审计测量缺失或无效"})
            elif insufficient and profile.get("insufficient_sample_blocks_formal"):
                blockers.append({"metric_id": item_key[0], "scope": item_key[1], "reason": "审计样本或置信资格不足"})
            elif (mismatch or field_mismatch) and profile.get("blocking_on_mismatch"):
                blockers.append({"metric_id": item_key[0], "scope": item_key[1], "reason": field_mismatch or f"审计结果不符合要求: 期望{required_status or '符合'}，实际{audit_status}"})
            continue
        if not measurement or measurement.get("status", "有效") != "有效":
            blockers.append({"metric_id": item_key[0], "scope": item_key[1], "reason": "测量缺失或无效"})
            continue
        try:
            profile = metric["hard_gate_profile"] if kind == "hard" else metric["score_profile"]
            gap = distance(profile["method"], metric["target"], measurement["value"], profile.get("zero_floor", 1e-12), profile)
        except (KeyError, TypeError, ValueError) as exc:
            blockers.append({"metric_id": item_key[0], "scope": item_key[1], "reason": str(exc)})
            continue
        base = {"metric_id": item_key[0], "name_zh": metric.get("name_zh", item_key[0]), "scope": item_key[1], "target": metric["target"], "candidate": measurement["value"], "distance": gap, "waiver": waiver}
        if kind in {"hard", "score"} and profile.get("method") in {"wasserstein_1d", "grouped_wasserstein_1d"}:
            base["distance_profile"] = {
                field: profile.get(field)
                for field in (
                    "axis_semantics",
                    "ordered_distance_policy_id",
                    "position_transform",
                    "distance_normalization",
                    "distance_scale",
                    "distance_scale_source",
                    "distance_unit",
                )
                if profile.get(field) is not None
            }
        if kind == "hard":
            try:
                base_tolerance, tolerance_factor, tolerance, policy_id = hard_tolerance(contract, metric, profile)
            except (TypeError, ValueError) as exc:
                blockers.append({"metric_id": item_key[0], "scope": item_key[1], "reason": str(exc)})
                continue
            passed = gap <= tolerance
            base.update({"base_tolerance": base_tolerance, "tolerance_factor": tolerance_factor, "tolerance": tolerance, "tolerance_policy_id": policy_id, "status": "硬指标已豁免" if waived else ("通过" if passed else "不通过")})
            hard_gates.append(base)
        elif waived:
            base.update({"status": "已豁免", "score": None, "band": "不适用", "weight": 0})
            scores.append(base)
        else:
            value = max(0.0, min(100.0, score_from_distance(gap, profile)))
            aggregation = metric.get("scope_aggregation", "weighted_mean")
            try:
                if modern_contract and "weight" not in metric:
                    raise ValueError("评分指标缺少已密封weight")
                weight = positive_finite(metric.get("weight", metric.get("default_weight", 1.0)), "评分权重")
                if aggregation == "weighted_mean":
                    if modern_contract and "scope_weight" not in metric:
                        raise ValueError("weighted_mean评分指标缺少已密封scope_weight")
                    scope_weight = positive_finite(metric.get("scope_weight", 1.0), "作用域权重")
                else:
                    scope_weight = 1.0
            except ValueError as exc:
                blockers.append({"metric_id": item_key[0], "scope": item_key[1], "reason": str(exc)})
                continue
            base.update({
                "status": "有效",
                "score": value,
                "band": band(value),
                "group": metric.get("score_group", "default"),
                "weight": weight,
                "score_budget_key": metric.get("score_budget_key", item_key[0]),
                "scope_aggregation": aggregation,
                "scope_weight": scope_weight,
            })
            scores.append(base)
    budget_map = {}
    for item in scores:
        if item.get("score") is None:
            continue
        budget_map.setdefault(item["score_budget_key"], []).append(item)
    budget_scores = []
    group_map = {}
    for budget_key, items in sorted(budget_map.items()):
        groups_in_budget = {item["group"] for item in items}
        aggregations = {item["scope_aggregation"] for item in items}
        weights = {item["weight"] for item in items}
        scope_keys = {(item["metric_id"], item["scope"]) for item in items}
        if len(groups_in_budget) != 1 or len(aggregations) != 1 or len(weights) != 1:
            blockers.append({"metric_id": budget_key, "scope": "*", "reason": "同一评分预算的评分组、聚合方式或权重不一致"})
            continue
        if len(scope_keys) != len(items):
            blockers.append({"metric_id": budget_key, "scope": "*", "reason": "同一评分预算存在重复作用域实例"})
            continue
        group = next(iter(groups_in_budget))
        aggregation = next(iter(aggregations))
        if aggregation == "weighted_mean":
            scope_weight_sum = sum(item["scope_weight"] for item in items)
            value = sum(item["score"] * item["scope_weight"] for item in items) / scope_weight_sum
        elif aggregation == "minimum":
            value = min(item["score"] for item in items)
        else:
            blockers.append({"metric_id": budget_key, "scope": "*", "reason": f"不支持的作用域聚合方式: {aggregation}"})
            continue
        weight = next(iter(weights))
        budget_scores.append({
            "group": group,
            "score_budget_key": budget_key,
            "score": value,
            "band": band(value),
            "weight": weight,
            "scope_aggregation": aggregation,
            "scope_count": len(items),
        })
        acc = group_map.setdefault(group, [0.0, 0.0, 0])
        acc[0] += value * weight
        acc[1] += weight
        acc[2] += 1
    group_weights = contract.get("group_weights", {})
    active_groups = set(group_map)
    if modern_contract:
        try:
            group_weights = validate_embedded_policy(contract)
            if set(group_weights) != active_groups:
                raise ValueError("group_weights必须与全部有效测量评分组完全一致")
        except (TypeError, ValueError) as exc:
            blockers.append({"metric_id": "*", "scope": "*", "reason": str(exc)})
            group_weights = {}
    groups, total, total_weight = [], 0.0, 0.0
    for name in sorted(group_map):
        numerator, weight_sum, metric_count = group_map[name]
        value = numerator / weight_sum
        try:
            if modern_contract and name not in group_weights:
                raise ValueError(f"评分组{name}缺少已密封权重")
            weight = positive_finite(group_weights.get(name, 1.0), f"评分组{name}权重")
        except ValueError as exc:
            blockers.append({"metric_id": "*", "scope": name, "reason": str(exc)})
            continue
        groups.append({
            "group": name,
            "score": value,
            "band": band(value),
            "weight": weight,
            "budget_count": metric_count,
            "metric_count": metric_count,
            "method": "先按score_budget_key聚合作用域，再按指标权重汇总",
        })
        total += value * weight
        total_weight += weight
    overall = total / total_weight if total_weight else None
    if overall is not None and not math.isfinite(overall):
        blockers.append({"metric_id": "*", "scope": "*", "reason": "综合分不是有限数值"})
        overall = None
    hard_failed = any(x["status"] == "不通过" for x in hard_gates)
    if blockers:
        status = "无法判定"
    elif hard_failed or overall is None or overall < 80:
        status = "不通过"
    elif waiver_count:
        status = "豁免后通过"
    else:
        status = "通过"
    result = {
        "schema_version": "1.3" if schema_is(contract, "1.3") else "1.2",
        "report_contract_version": contract.get("report_contract_version"),
        "task_id": contract.get("task_id", ""),
        "status": "已完成" if not blockers else "阻塞",
        "hard_gates": hard_gates,
        "scores": scores,
        "audits": audits,
        "budget_scores": budget_scores,
        "groups": groups,
        "overall_score": overall,
        "overall_band": band(overall),
        "alignment_status": status,
        "blocking_reasons": blockers,
        "waiver_count": waiver_count,
        "input_hashes": contract.get("input_hashes", {}),
        "source_paths": {"metric_contract": str(args.contract.resolve()), "measurements": str(args.measurements.resolve())},
        "source_hashes": {"metric_contract": sha(args.contract), "measurements": sha(args.measurements)},
        "generator": "score_alignment.py"
    }
    if isinstance(ordered_policy, dict):
        result["ordered_distance_policy"] = {
            field: ordered_policy.get(field)
            for field in (
                "policy_id",
                "version",
                "source_path",
                "source_sha256",
                "active_ordered_metric_instances_sha256",
            )
        }
    if schema_is(contract, "1.3"):
        result["sample_capability_policy"] = sample_capability_summary(contract)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": status, "overall_score": overall, "output": str(args.output)}, ensure_ascii=False))
    return 0 if not blockers else 2


if __name__ == "__main__":
    sys.exit(main())
