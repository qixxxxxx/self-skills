#!/usr/bin/env python3
import hashlib
import json
import math
from pathlib import Path

import numpy as np


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


def absolute_error(target, candidate):
    target, candidate = float(target), float(candidate)
    if not math.isfinite(target) or not math.isfinite(candidate):
        raise ValueError("数值必须有限")
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


def half_l1(target, candidate):
    if not isinstance(target, dict) or not isinstance(candidate, dict):
        raise ValueError("半L1双方必须是对象")
    keys = sorted(set(target) | set(candidate), key=str)
    p = np.asarray([float(target.get(key, 0.0)) for key in keys], dtype=float)
    q = np.asarray([float(candidate.get(key, 0.0)) for key in keys], dtype=float)
    if not np.all(np.isfinite(p)) or not np.all(np.isfinite(q)) or np.any(p < 0) or np.any(q < 0) or np.any(p > 1) or np.any(q > 1):
        raise ValueError("半L1占比必须位于[0,1]")
    return float(0.5 * np.abs(p - q).sum())


def calculate_distance(contract, target, candidate):
    method = contract["method"]
    if method == "absolute_probability_error":
        return absolute_probability_error(target, candidate)
    if method == "absolute_error":
        return absolute_error(target, candidate)
    if method == "relative_error":
        return relative_error(target, candidate, contract.get("zero_floor", 1e-12))
    if method == "range_error":
        return range_error(target, candidate)
    if method == "total_variation":
        return total_variation(target, candidate)
    if method == "half_l1":
        return half_l1(target, candidate)
    raise ValueError(f"不支持的距离方法: {method}")


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
    return {"C": float(evaluation_policy["formal_grading"]["hard_gate_pass_limit"])}


def grade_ratio(ratio, thresholds):
    for grade in ("S", "A", "B", "C"):
        if ratio <= float(thresholds[grade]):
            return grade
    return "F"


def grade_score(score, evaluation_policy):
    thresholds = evaluation_policy["composite_scoring"]["grade_thresholds"]
    for grade in ("S", "A", "B", "C"):
        if score >= float(thresholds[grade]):
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
            "score": None,
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
            "score": None,
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
        score = 100.0 if passed else 0.0
    else:
        ratio = distance / tolerance
        score = max(0.0, 100.0 * (1.0 - ratio))
        passed = ratio <= pass_limit
        grade = grade_score(score, evaluation_policy) if passed else "F"
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
        "score": score,
        "formal_grade": grade,
        "status": "通过" if passed else "不通过",
        "sample_evidence": _sample_evidence(measurement.get("sample_evidence")),
        "reason_zh": None,
    }


def _hierarchical_card_score(card, instance_results):
    grouped = {}
    for instance, result in zip(card["instances"], instance_results):
        aggregation = instance.get("aggregation")
        if not aggregation or not finite_number(result.get("score")):
            continue
        key = (aggregation["dimension_id"], aggregation["group_id"])
        grouped.setdefault(key, {"mode": aggregation["mode"], "items": [], "overall": []})[aggregation["role"] if aggregation["role"] == "overall" else "items"].append(result["score"])
    dimension_scores = {}
    for (dimension_id, _group_id), group in grouped.items():
        if group["mode"] == "half_overall_half_items":
            if not group["overall"] or not group["items"]:
                continue
            score = sum(group["overall"]) / len(group["overall"]) * 0.5 + sum(group["items"]) / len(group["items"]) * 0.5
        else:
            if not group["items"]:
                continue
            score = sum(group["items"]) / len(group["items"])
        dimension_scores.setdefault(dimension_id, []).append(score)
    scores = [sum(values) / len(values) for values in dimension_scores.values() if values]
    return sum(scores) / len(scores) if scores else None


def aggregate_card(card, instance_results, evaluation_policy):
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
    score = None
    grade = worst_grade(item["formal_grade"] for item in instance_results)
    if card["category_id"] == "N" and status == "通过":
        scores = [item["score"] for item in instance_results if finite_number(item.get("score"))]
        score = sum(scores) / len(scores) if scores else None
        grade = grade_score(score, evaluation_policy) if score is not None else "U"
    elif card["category_id"] in {"J", "P", "B"} and status == "通过":
        score = _hierarchical_card_score(card, instance_results)
        grade = grade_score(score, evaluation_policy) if score is not None else "U"
    return {
        "card_id": card["card_id"],
        "name_zh": card["name_zh"],
        "category_id": card["category_id"],
        "kind": card["kind"],
        "status": status,
        "score": score,
        "formal_grade": grade,
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
                "score": None,
                "formal_grade": "NA",
                "maximum_deviation_ratio": None,
                "worst_instance_id": None,
                "instances": [],
            })
        else:
            card_results.append(aggregate_card(card, results, evaluation_policy))
    all_instances = [item for card in card_results for item in card["instances"]]
    unknown = sum(item["status"] in UNKNOWN_STATUSES for item in all_instances)
    hard_failures = sum(item["status"] == "不通过" for card in card_results if card["kind"] == "hard_gate" for item in card["instances"])
    alignment_failures = sum(item["status"] == "不通过" for card in card_results if card["kind"] == "alignment" for item in card["instances"])
    ranked = [item for item in all_instances if finite_number(item.get("deviation_ratio"))]
    maximum = max(ranked, key=lambda item: item["deviation_ratio"], default=None)
    worst = _worst_instance(all_instances)
    final_status = "无法完整判定" if unknown else ("不通过" if hard_failures or alignment_failures else "通过")
    category_scores = {category: None for category in ("N", "J", "P", "B")}
    n_cards = [card for card in card_results if card["category_id"] == "N" and card["status"] != "不适用"]
    if n_cards and all(card["status"] == "通过" and finite_number(card.get("score")) for card in n_cards):
        category_scores["N"] = sum(card["score"] for card in n_cards) / len(n_cards)
    j_cards = [card for card in card_results if card["category_id"] == "J" and card["status"] != "不适用"]
    if j_cards and all(card["status"] == "通过" and finite_number(card.get("score")) for card in j_cards):
        category_scores["J"] = sum(card["score"] for card in j_cards) / len(j_cards)
    p_cards = [card for card in card_results if card["category_id"] == "P" and card["status"] != "不适用"]
    if p_cards and all(card["status"] == "通过" and finite_number(card.get("score")) for card in p_cards):
        category_scores["P"] = sum(card["score"] for card in p_cards) / len(p_cards)
    b_cards = [card for card in card_results if card["category_id"] == "B" and card["status"] != "不适用"]
    if b_cards and all(card["status"] == "通过" and finite_number(card.get("score")) for card in b_cards):
        category_scores["B"] = sum(card["score"] for card in b_cards) / len(b_cards)
    scoped_scores = [category_scores[category] for category in evaluation_policy["composite_scoring"]["score_scope"]]
    composite_score = sum(scoped_scores) / len(scoped_scores) if scoped_scores and all(finite_number(item) for item in scoped_scores) else None
    final_grade = "U" if unknown else ("F" if hard_failures or alignment_failures else grade_score(composite_score, evaluation_policy))
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
            "composite_score": composite_score,
            "category_scores": category_scores,
            "score_scope": evaluation_policy["composite_scoring"]["score_scope"],
            "planned_score_scope": evaluation_policy["composite_scoring"]["planned_score_scope"],
            "score_status": evaluation_policy["composite_scoring"]["score_status"],
            "hard_gate_failures": hard_failures,
            "alignment_failures": alignment_failures,
            "insufficient_or_error_instances": unknown,
            "maximum_deviation_ratio": maximum.get("deviation_ratio") if maximum else None,
            "worst_instance_id": worst.get("instance_id") if worst else None,
        },
    }
