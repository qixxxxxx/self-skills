#!/usr/bin/env python3
import bisect
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import lil_matrix


FORMAL_STATUSES = {"通过", "不通过", "样本不足", "不适用", "计算异常"}
UNKNOWN_STATUSES = {"样本不足", "计算异常"}
GRADE_SEVERITY = {"NA": -1, "S": 0, "A": 1, "B": 2, "C": 3, "F": 4, "U": 5}


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def dump_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def finite_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _probabilities(value, positions=None):
    if isinstance(value, dict):
        if positions is None:
            keys = sorted(set(value), key=str)
            values = [float(value[key]) for key in keys]
        else:
            keys, values = [], []
            consumed = set()
            for item in positions:
                candidates = [str(item)]
                try:
                    numeric = float(item)
                except (TypeError, ValueError):
                    numeric = None
                if numeric is not None and numeric.is_integer():
                    candidates.append(str(int(numeric)))
                key = next((candidate for candidate in candidates if candidate in value), None)
                keys.append(key or candidates[0])
                values.append(float(value[key]) if key is not None else 0.0)
                if key is not None:
                    consumed.add(key)
            if set(value) - consumed:
                raise ValueError(f"分布包含合同支持之外的桶: {sorted(set(value) - consumed)}")
    elif isinstance(value, list):
        values = [float(item) for item in value]
    else:
        raise ValueError("分布必须是数组或对象")
    array = np.asarray(values, dtype=float)
    if array.ndim != 1 or len(array) == 0 or not np.all(np.isfinite(array)) or np.any(array < 0):
        raise ValueError("分布包含非法概率")
    total = float(array.sum())
    if total <= 0:
        raise ValueError("分布概率和必须大于0")
    return array / total


def absolute_probability_error(target, candidate):
    target, candidate = float(target), float(candidate)
    if not 0 <= target <= 1 or not 0 <= candidate <= 1:
        raise ValueError("概率必须位于[0,1]")
    return abs(candidate - target)


def relative_error(target, candidate, zero_floor=1e-12):
    target, candidate = float(target), float(candidate)
    return abs(candidate - target) / max(abs(target), float(zero_floor))


def range_error(target, candidate):
    if isinstance(target, dict):
        lower, upper = float(target["min"]), float(target["max"])
    else:
        lower, upper = map(float, target)
    candidate = float(candidate)
    if lower > upper:
        raise ValueError("目标区间上下界颠倒")
    return max(lower - candidate, 0.0, candidate - upper)


def total_variation(target, candidate):
    if isinstance(target, dict) and isinstance(candidate, dict):
        keys = sorted(set(target) | set(candidate), key=str)
        p = _probabilities({key: target.get(key, 0.0) for key in keys}, keys)
        q = _probabilities({key: candidate.get(key, 0.0) for key in keys}, keys)
    else:
        p, q = _probabilities(target), _probabilities(candidate)
        if len(p) != len(q):
            raise ValueError("总变差双方桶数量不一致")
    return float(0.5 * np.abs(p - q).sum())


def wasserstein_1d(target, candidate, positions, transform="identity", support_span=None):
    x = np.asarray([float(item) for item in positions], dtype=float)
    if len(x) < 2 or not np.all(np.isfinite(x)) or np.any(np.diff(x) <= 0):
        raise ValueError("有序位置必须有限且严格递增")
    if transform == "log10_1p":
        if np.any(x < 0):
            raise ValueError("log10_1p业务位置不能为负")
        x = np.log10(1.0 + x)
        scale = 1.0
    elif transform == "identity":
        scale = float(support_span if support_span is not None else x[-1] - x[0])
        if scale <= 0:
            raise ValueError("线性支持跨度必须大于0")
    else:
        raise ValueError(f"未知位置变换: {transform}")
    p, q = _probabilities(target, positions), _probabilities(candidate, positions)
    if len(p) != len(x) or len(q) != len(x):
        raise ValueError("概率桶与业务位置数量不一致")
    return float(np.sum(np.abs(np.cumsum(p - q)[:-1]) * np.diff(x)) / scale)


def _cells(state):
    raw = state.get("cells") if isinstance(state, dict) else state
    cells = [tuple(map(int, cell)) for cell in raw]
    if len(set(cells)) != len(cells):
        raise ValueError("占位图存在重复格")
    return cells


def _symbol_position_ground_cost(left, right, board_shape):
    left, right = _cells(left), _cells(right)
    if len(left) != 1 or len(right) != 1:
        raise ValueError("关键符号位置状态必须且只能包含一个格")
    rows, cols = map(int, board_shape)
    diameter = max(1, rows + cols - 2)
    return (abs(left[0][0] - right[0][0]) + abs(left[0][1] - right[0][1])) / diameter


def _board_shape_ground_cost(left, right, _board_shape):
    left, right = set(_cells(left)), set(_cells(right))
    union = left | right
    return 0.0 if not union else len(left ^ right) / len(union)


def _state_distribution(value):
    if not isinstance(value, dict) or not isinstance(value.get("states"), list):
        raise ValueError("结构分布必须包含states数组")
    states, probs = [], []
    for item in value["states"]:
        states.append(item)
        probs.append(float(item.get("probability", 0.0)))
    probs = _probabilities(probs)
    return states, probs


def structural_wasserstein(target, candidate, state_kind="symbol_position_density", board_shape=None):
    target_states, p = _state_distribution(target)
    candidate_states, q = _state_distribution(candidate)
    shape = board_shape or target.get("board_shape") or candidate.get("board_shape")
    if not shape or len(shape) != 2:
        raise ValueError("结构距离缺少board_shape")
    grounds = {
        "symbol_position_density": _symbol_position_ground_cost,
        "board_shape": _board_shape_ground_cost,
    }
    if state_kind not in grounds:
        raise ValueError(f"未知结构状态类型: {state_kind}")
    ground = grounds[state_kind]
    costs = np.asarray([[ground(a, b, shape) for b in candidate_states] for a in target_states], dtype=float)
    rows, cols = len(p), len(q)
    constraints = lil_matrix((rows + cols, rows * cols), dtype=float)
    for i in range(rows):
        constraints[i, i * cols : (i + 1) * cols] = 1.0
    for j in range(cols):
        constraints[rows + j, j::cols] = 1.0
    result = linprog(
        costs.ravel(),
        A_eq=constraints.tocsr(),
        b_eq=np.concatenate([p, q]),
        bounds=(0.0, None),
        method="highs",
    )
    if not result.success:
        raise ValueError(f"结构Wasserstein求解失败: {result.message}")
    return float(result.fun)


def calculate_distance(contract, target, candidate):
    method = contract["method"]
    if method == "absolute_probability_error":
        return absolute_probability_error(target, candidate)
    if method == "relative_error":
        return relative_error(target, candidate, contract.get("zero_floor", 1e-12))
    if method == "range_error":
        return range_error(target, candidate)
    if method == "total_variation":
        return total_variation(target, candidate)
    if method == "wasserstein_1d":
        return wasserstein_1d(
            target,
            candidate,
            contract["bin_positions"],
            contract.get("position_transform", "identity"),
            contract.get("support_span"),
        )
    if method == "structural_wasserstein":
        return structural_wasserstein(
            target,
            candidate,
            contract.get("state_kind", "symbol_position_density"),
            contract.get("board_shape"),
        )
    raise ValueError(f"不支持的距离方法: {method}")


def _higher_quantile(values, quantile):
    ordered = sorted(float(value) for value in values)
    if not ordered:
        raise ValueError("分位数输入为空")
    index = max(0, min(len(ordered) - 1, math.ceil(quantile * len(ordered)) - 1))
    return ordered[index]


def joint_q99_tolerances(distances_by_instance):
    if not distances_by_instance:
        raise ValueError("缺少自对照距离")
    lengths = {len(values) for values in distances_by_instance.values()}
    if len(lengths) != 1 or 0 in lengths:
        raise ValueError("全部实例必须具有相同且非零的自对照轮数")
    base = {key: _higher_quantile(values, 0.99) for key, values in distances_by_instance.items()}
    scales = {key: value if value > 0 else max(map(float, distances_by_instance[key]), default=0.0) for key, value in base.items()}
    maxima = []
    for index in range(next(iter(lengths))):
        ratios = []
        for key, values in distances_by_instance.items():
            scale = scales[key]
            value = float(values[index])
            ratios.append(0.0 if scale == 0 and value == 0 else value / scale)
        maxima.append(max(ratios))
    factor = max(1.0, _higher_quantile(maxima, 0.99))
    return {key: value * factor for key, value in base.items()}, factor


def _sample_evidence(value):
    evidence = value if isinstance(value, dict) else {}
    return {
        "target_count": int(evidence.get("target_count", 0)),
        "candidate_count": int(evidence.get("candidate_count", 0)),
        "required_target_count": evidence.get("required_target_count"),
        "required_candidate_count": evidence.get("required_candidate_count"),
        "gap_zh": evidence.get("gap_zh"),
    }


def grade_thresholds(card, evaluation_policy):
    grading = evaluation_policy["formal_grading"]
    if card["category_id"] == "N":
        return grading["hard_gate_thresholds"][card["card_id"]]
    return grading["alignment_thresholds"][card["category_id"]]


def grade_ratio(ratio, thresholds):
    for grade in ("S", "A", "B", "C"):
        if ratio <= float(thresholds[grade]):
            return grade
    return "F"


def worst_grade(grades):
    values = [grade for grade in grades if grade != "NA"]
    return max(values, key=GRADE_SEVERITY.__getitem__) if values else "NA"


def _worst_instance(instance_results):
    def key(item):
        ratio, limit = item.get("deviation_ratio"), item.get("pass_limit")
        normalized = ratio / limit if finite_number(ratio) and finite_number(limit) and limit > 0 else -1.0
        return GRADE_SEVERITY[item["formal_grade"]], normalized

    return max(instance_results, key=key, default=None)


def evaluate_instance(card, instance, measurement, evaluation_policy):
    thresholds = grade_thresholds(card, evaluation_policy)
    pass_limit = float(thresholds["C"])
    status = measurement.get("status")
    if status in {"样本不足", "计算异常"}:
        return {
            "instance_id": instance["instance_id"],
            "facet_id": instance["facet_id"],
            "subitem_id": instance["subitem_id"],
            "target": instance.get("target"),
            "candidate": measurement.get("candidate"),
            "distance_method": instance["distance"]["method"],
            "distance": None,
            "tolerance": instance["tolerance"]["effective"],
            "deviation_ratio": None,
            "pass_limit": pass_limit,
            "formal_grade": "U",
            "status": status,
            "sample_evidence": _sample_evidence(measurement.get("sample_evidence")),
            "reason_zh": measurement.get("reason_zh"),
        }
    if instance.get("status") == "不适用":
        return {
            "instance_id": instance["instance_id"],
            "facet_id": instance["facet_id"],
            "subitem_id": instance["subitem_id"],
            "target": instance.get("target"),
            "candidate": None,
            "distance_method": instance["distance"]["method"],
            "distance": None,
            "tolerance": instance["tolerance"]["effective"],
            "deviation_ratio": None,
            "pass_limit": pass_limit,
            "formal_grade": "NA",
            "status": "不适用",
            "sample_evidence": _sample_evidence(measurement.get("sample_evidence")),
            "reason_zh": instance.get("inapplicability_reason"),
        }
    candidate = measurement["candidate"]
    distance = calculate_distance(instance["distance"], instance["target"], candidate)
    tolerance = float(instance["tolerance"]["effective"])
    if tolerance == 0:
        passed = distance == 0
        ratio = 0.0 if passed else None
        grade = evaluation_policy["formal_grading"]["deterministic_exact"]["pass_grade" if passed else "fail_grade"]
    else:
        ratio = distance / tolerance
        grade = grade_ratio(ratio, thresholds)
        passed = grade in evaluation_policy["formal_grading"]["pass_grades"]
    return {
        "instance_id": instance["instance_id"],
        "facet_id": instance["facet_id"],
        "subitem_id": instance["subitem_id"],
        "target": instance["target"],
        "candidate": candidate,
        "distance_method": instance["distance"]["method"],
        "distance": distance,
        "tolerance": tolerance,
        "deviation_ratio": ratio,
        "pass_limit": pass_limit,
        "formal_grade": grade,
        "status": "通过" if passed else "不通过",
        "sample_evidence": _sample_evidence(measurement.get("sample_evidence")),
        "reason_zh": None,
    }


def aggregate_card(card, instance_results):
    statuses = [item["status"] for item in instance_results]
    if "计算异常" in statuses:
        status = "计算异常"
    elif "样本不足" in statuses:
        status = "样本不足"
    elif "不通过" in statuses:
        status = "不通过"
    elif "通过" in statuses:
        status = "通过"
    else:
        status = "不适用"
    ranked = [item for item in instance_results if finite_number(item.get("deviation_ratio"))]
    maximum = max(ranked, key=lambda item: item["deviation_ratio"], default=None)
    worst = _worst_instance(instance_results)
    return {
        "card_id": card["card_id"],
        "name_zh": card["name_zh"],
        "category_id": card["category_id"],
        "kind": card["kind"],
        "status": status,
        "formal_grade": worst_grade(item["formal_grade"] for item in instance_results),
        "maximum_deviation_ratio": maximum.get("deviation_ratio") if maximum else None,
        "worst_instance_id": worst.get("instance_id") if worst else None,
        "instances": instance_results,
    }


def evaluate_contract(contract, measurements, phase, contract_sha256, evaluation_policy):
    by_id = measurements.get("measurements", {})
    card_results = []
    for card in contract["cards"]:
        results = []
        for instance in card.get("instances", []):
            measurement = by_id.get(instance["instance_id"])
            if measurement is None:
                measurement = {"status": "计算异常", "reason_zh": "缺少候选测量"}
            try:
                results.append(evaluate_instance(card, instance, measurement, evaluation_policy))
            except Exception as exc:
                results.append(evaluate_instance(card, instance, {"status": "计算异常", "reason_zh": str(exc)}, evaluation_policy))
        if not results and card.get("status") == "不适用":
            card_results.append({
                "card_id": card["card_id"],
                "name_zh": card["name_zh"],
                "category_id": card["category_id"],
                "kind": card["kind"],
                "status": "不适用",
                "formal_grade": "NA",
                "maximum_deviation_ratio": None,
                "worst_instance_id": None,
                "instances": [],
            })
        else:
            card_results.append(aggregate_card(card, results))
    all_instances = [item for card in card_results for item in card["instances"]]
    unknown = sum(item["status"] in UNKNOWN_STATUSES for item in all_instances)
    hard_failures = sum(item["status"] == "不通过" for card in card_results if card["kind"] == "hard_gate" for item in card["instances"])
    alignment_failures = sum(item["status"] == "不通过" for card in card_results if card["kind"] == "alignment" for item in card["instances"])
    ranked = [item for item in all_instances if finite_number(item.get("deviation_ratio"))]
    maximum = max(ranked, key=lambda item: item["deviation_ratio"], default=None)
    worst = _worst_instance(all_instances)
    final_grade = "U" if unknown else worst_grade(item["formal_grade"] for item in all_instances)
    final_status = "无法完整判定" if unknown else ("不通过" if hard_failures or alignment_failures else "通过")
    audit_measurements = {item.get("audit_id"): item for item in measurements.get("audits", [])}
    audit_results = []
    for audit in contract.get("audits", []):
        measured = audit_measurements.get(audit["audit_id"])
        audit_results.append(measured or {
            "audit_id": audit["audit_id"],
            "name_zh": audit["name_zh"],
            "status": "缺失",
            "details": {"reason_zh": "测量文件未提供该审计结果"},
        })
    return {
        "schema_version": "slot-alignment.alignment-result.v5",
        "task_id": contract["task_id"],
        "phase": phase,
        "metric_contract_sha256": contract_sha256,
        "card_results": card_results,
        "audits": audit_results,
        "summary": {
            "final_status": final_status,
            "final_grade": final_grade,
            "hard_gate_failures": hard_failures,
            "alignment_failures": alignment_failures,
            "insufficient_or_error_instances": unknown,
            "maximum_deviation_ratio": maximum.get("deviation_ratio") if maximum else None,
            "worst_instance_id": worst.get("instance_id") if worst else None,
        },
    }
