#!/usr/bin/env python3
import argparse
import json
import math
import sys
from pathlib import Path


def load(path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def key(item):
    return item.get("metric_id", ""), item.get("scope", "")


def scalar(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("需要有限数值")
    return float(value)


def distance(method, target, value, zero_floor=1e-12):
    if method == "absolute_error":
        return abs(scalar(value) - scalar(target))
    if method == "relative_error":
        t = scalar(target)
        return abs(scalar(value) - t) / max(abs(t), float(zero_floor))
    if method == "range_error":
        low, high, val = scalar(target["min"]), scalar(target["max"]), scalar(value)
        if low <= val <= high:
            return 0.0
        return low - val if val < low else val - high
    if method == "total_variation":
        if not isinstance(target, list) or not isinstance(value, list) or len(target) != len(value):
            raise ValueError("分布桶不一致")
        return 0.5 * sum(abs(scalar(a) - scalar(b)) for a, b in zip(target, value))
    raise ValueError(f"不支持的距离方法: {method}")


def anchors(profile):
    result = []
    for item in profile.get("anchors", []):
        if isinstance(item, dict):
            result.append((float(item["distance"]), float(item["score"])))
        else:
            result.append((float(item[0]), float(item[1])))
    result.sort()
    if len(result) < 2:
        raise ValueError("评分锚点不足")
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


def main():
    parser = argparse.ArgumentParser(description="确定性复算 Slot 对齐评分")
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--measurements", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    contract, measured = load(args.contract), load(args.measurements)
    measurements = {key(x): x for x in measured.get("measurements", [])}
    hard_gates, scores, blockers = [], [], []
    waiver_count = 0
    for metric in sorted(contract.get("metrics", []), key=key):
        kind = metric.get("kind")
        if kind not in {"hard", "score"}:
            continue
        item_key = key(metric)
        measurement = measurements.get(item_key)
        waiver = metric.get("waiver", {})
        waived = waiver.get("status") == "已批准"
        not_applicable = metric.get("status") == "不适用"
        if waived:
            waiver_count += 1
        if not_applicable:
            continue
        if not measurement or measurement.get("status", "有效") != "有效":
            blockers.append({"metric_id": item_key[0], "scope": item_key[1], "reason": "测量缺失或无效"})
            continue
        try:
            profile = metric["hard_gate_profile"] if kind == "hard" else metric["score_profile"]
            gap = distance(profile["method"], metric["target"], measurement["value"], profile.get("zero_floor", 1e-12))
        except (KeyError, TypeError, ValueError) as exc:
            blockers.append({"metric_id": item_key[0], "scope": item_key[1], "reason": str(exc)})
            continue
        base = {"metric_id": item_key[0], "name_zh": metric.get("name_zh", item_key[0]), "scope": item_key[1], "target": metric["target"], "candidate": measurement["value"], "distance": gap, "waiver": waiver}
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
            base.update({"status": "有效", "score": value, "band": band(value), "group": metric.get("score_group", "default"), "weight": float(metric.get("weight", metric.get("default_weight", 1.0)))})
            scores.append(base)
    group_map = {}
    for item in scores:
        if item.get("score") is None:
            continue
        group = item["group"]
        acc = group_map.setdefault(group, [0.0, 0.0])
        acc[0] += item["score"] * item["weight"]
        acc[1] += item["weight"]
    group_weights = contract.get("group_weights", {})
    groups, total, total_weight = [], 0.0, 0.0
    for name in sorted(group_map):
        numerator, weight_sum = group_map[name]
        value = numerator / weight_sum
        weight = float(group_weights.get(name, 1.0))
        groups.append({"group": name, "score": value, "band": band(value), "weight": weight})
        total += value * weight
        total_weight += weight
    overall = total / total_weight if total_weight else None
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
        "schema_version": "1.0",
        "task_id": contract.get("task_id", ""),
        "status": "已完成" if not blockers else "阻塞",
        "hard_gates": hard_gates,
        "scores": scores,
        "groups": groups,
        "overall_score": overall,
        "overall_band": band(overall),
        "alignment_status": status,
        "blocking_reasons": blockers,
        "waiver_count": waiver_count,
        "input_hashes": contract.get("input_hashes", {})
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": status, "overall_score": overall, "output": str(args.output)}, ensure_ascii=False))
    return 0 if not blockers else 2


if __name__ == "__main__":
    sys.exit(main())
