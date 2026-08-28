#!/usr/bin/env python3
"""按用户预授权政策自动豁免样本不足或已证明结构不可达的精确指标实例，含禁止变更边界不可达。"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path

from contract_io import canonical_json_bytes, load_contract, metric_instance_id, write_contract


POLICY_SCHEMA = "slot-alignment.automatic-metric-waiver-policy.v1"
POLICY_ID = "automatic-metric-waiver-v1"
INSUFFICIENT = "AUTO_WAIVED_INSUFFICIENT_DATA"
UNATTAINABLE = "AUTO_WAIVED_STRUCTURALLY_UNATTAINABLE"
AUTO_REASONS = {INSUFFICIENT, UNATTAINABLE}
PROOF_FIELDS = {
    "authorized_space_static_check",
    "direction_perturbation",
    "independent_and_joint_validation",
    "stable_unattainability_evidence",
    "sample_qualification_valid",
}


def load(path):
    with Path(path).open(encoding="utf-8") as stream:
        return json.load(stream)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical_sha256(value):
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def non_empty(value):
    return isinstance(value, str) and bool(value.strip())


def validate_policy_definition(policy):
    if not isinstance(policy, dict) or policy.get("schema_version") != POLICY_SCHEMA:
        raise ValueError("自动豁免政策schema_version无效")
    expected = {
        "policy_id": POLICY_ID,
        "version": "1.0.0",
        "source_path": "assets/policies/automatic_metric_waiver_policy.v1.json",
        "legacy_contracts_unchanged": True,
        "authorization_source": "user_pre_authorized_skill_policy",
        "allowed_reason_codes": [INSUFFICIENT, UNATTAINABLE],
        "allowed_metric_kinds": ["hard", "score", "audit"],
    }
    for field, value in expected.items():
        if policy.get(field) != value:
            raise ValueError(f"自动豁免政策{field}无效")
    rules = policy.get("rules")
    required = {
        "bind_exact_metric_instance",
        "retain_target_gap_and_evidence",
        "hard_metric_must_show_waived",
        "score_metric_removed_and_weights_renormalized",
        "ordinary_pass_forbidden_when_any_required_waiver_exists",
        "missing_definition_is_not_insufficient_data",
        "implementation_error_is_not_insufficient_data",
        "configuration_error_is_not_insufficient_data",
        "budget_exhaustion_is_not_structural_unattainability",
        "structural_unattainability_requires_sealed_proof",
    }
    if not isinstance(rules, dict) or any(rules.get(field) is not True for field in required):
        raise ValueError("自动豁免政策rules缺失或未启用")


def instance_id(metric):
    expected = metric_instance_id(
        metric.get("metric_id"),
        metric.get("source_node_ids", []),
        metric.get("instance_dimensions", {}),
    )
    actual = metric.get("instance_id")
    if actual is not None and actual != expected:
        raise ValueError(f"指标实例ID失效: {actual}")
    return expected


def metric_map(contract):
    result = {}
    for metric in contract.get("metrics", []):
        if not isinstance(metric, dict):
            raise ValueError("metric_contract.metrics必须为对象数组")
        value = instance_id(metric)
        if value in result:
            raise ValueError(f"指标实例ID重复: {value}")
        result[value] = metric
    return result


def policy_summary(policy, policy_path, records):
    auto_records = sorted(
        (item for item in records if item.get("reason_code") in AUTO_REASONS),
        key=lambda item: item.get("waiver_id", ""),
    )
    identities = [
        {
            "waiver_id": item.get("waiver_id"),
            "instance_id": item.get("instance_id"),
            "reason_code": item.get("reason_code"),
            "evidence_sha256": item.get("evidence_sha256"),
        }
        for item in auto_records
    ]
    return {
        "source_schema_version": policy["schema_version"],
        "policy_id": policy["policy_id"],
        "version": policy["version"],
        "source_path": policy["source_path"],
        "source_sha256": sha(policy_path),
        "authorization_source": policy["authorization_source"],
        "allowed_reason_codes": policy["allowed_reason_codes"],
        "decision_count": len(auto_records),
        "decision_bindings_sha256": canonical_sha256(identities),
        "status": "已应用" if auto_records else "无自动豁免",
    }


def waiver_reason(reason_code, evidence):
    if reason_code == INSUFFICIENT:
        return "原版目标样本或FORMAL样本未达到密封的99%样本能力要求，按用户预授权政策自动豁免"
    affected = evidence.get("affected_metric_instance", {}) if isinstance(evidence, dict) else {}
    boundary = str(affected.get("minimal_authority_expansion", ""))
    if "禁止扩权" in boundary:
        return f"完成该指标必须越过禁止变更边界（{boundary}），已证明结构不可达并按用户预授权政策自动豁免"
    return "授权参数空间已由密封证据证明结构不可达，按用户预授权政策自动豁免"


def build_record(metric, reason_code, policy, policy_path, evidence, decision_stage):
    evidence_sha = canonical_sha256(evidence)
    identity = instance_id(metric)
    waiver_id = f"mw_{canonical_sha256({'instance_id': identity, 'reason_code': reason_code, 'evidence_sha256': evidence_sha})[:24]}"
    return {
        "waiver_id": waiver_id,
        "instance_id": identity,
        "metric_id": metric.get("metric_id"),
        "scope": metric.get("scope"),
        "source_node_ids": sorted(metric.get("source_node_ids", [])),
        "instance_dimensions": metric.get("instance_dimensions", {}),
        "kind": metric.get("kind"),
        "status": "已批准",
        "reason_code": reason_code,
        "reason": waiver_reason(reason_code, evidence),
        "decision_stage": decision_stage,
        "authorization_source": policy["authorization_source"],
        "policy_id": policy["policy_id"],
        "policy_sha256": sha(policy_path),
        "target": copy.deepcopy(metric.get("target")),
        "target_sha256": canonical_sha256(metric.get("target")),
        "evidence": evidence,
        "evidence_sha256": evidence_sha,
        "audit_retained": True,
        "approval": {
            "status": "自动批准",
            "approved_by": "user_pre_authorized_policy",
            "authorization_source": policy["authorization_source"],
            "policy_id": policy["policy_id"],
            "policy_sha256": sha(policy_path),
        },
    }


def apply_record(contract, metric, record):
    records = contract.setdefault("waivers", [])
    if not isinstance(records, list):
        raise ValueError("metric_contract.waivers必须是数组")
    records[:] = [item for item in records if not (isinstance(item, dict) and item.get("waiver_id") == record["waiver_id"])]
    conflicting = [
        item for item in records
        if isinstance(item, dict)
        and item.get("instance_id") == record["instance_id"]
        and item.get("reason_code") in AUTO_REASONS
    ]
    if conflicting:
        raise ValueError(f"同一指标实例已存在不同自动豁免记录: {record['instance_id']}")
    records.append(record)
    records.sort(key=lambda item: (str(item.get("metric_id", "")), str(item.get("instance_id", "")), str(item.get("waiver_id", ""))))
    metric["waiver"] = {
        key: copy.deepcopy(record[key])
        for key in (
            "waiver_id", "instance_id", "status", "reason_code", "reason",
            "decision_stage", "authorization_source", "policy_id", "policy_sha256",
            "evidence", "evidence_sha256", "audit_retained", "approval",
        )
    }
    metric.pop("sample_capability_input", None)
    metric.pop("sample_capability", None)


def safe_policy_path(skill_root, source_path, label):
    if not non_empty(source_path):
        raise ValueError(f"{label}缺少source_path")
    relative = Path(source_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"{label}source_path无效")
    root = Path(skill_root).resolve()
    path = (root / relative).resolve()
    path.relative_to(root)
    if not path.is_file():
        raise ValueError(f"{label}源文件不存在")
    return path


def refresh_downstream_policies(contract, skill_root):
    from apply_ordered_distance_policy import apply_policy as apply_ordered
    from apply_sample_capability_policy import apply_policy as apply_sample
    from apply_score_group_weight_policy import apply_policy as apply_score_groups

    ordered = contract.get("ordered_distance_policy", {})
    ordered_path = safe_policy_path(skill_root, ordered.get("source_path"), "有序距离政策")
    if ordered.get("source_sha256") != sha(ordered_path):
        raise ValueError("有序距离政策源hash失效")
    apply_ordered(contract, load(ordered_path), ordered_path)

    score_policy = contract.get("score_group_weight_policy", {})
    score_path = safe_policy_path(skill_root, score_policy.get("source_path"), "评分组权重政策")
    if score_policy.get("source_sha256") != sha(score_path):
        raise ValueError("评分组权重政策源hash失效")
    apply_score_groups(contract, load(score_path), score_path)

    sample_policy = contract.get("sample_capability_policy", {})
    sample_path = safe_policy_path(skill_root, sample_policy.get("source_path"), "样本能力政策")
    if sample_policy.get("source_sha256") != sha(sample_path):
        raise ValueError("样本能力政策源hash失效")
    contract.pop("sample_capability_policy", None)
    for metric in contract.get("metrics", []):
        if metric.get("waiver", {}).get("status") != "已批准":
            metric.pop("sample_capability", None)
    apply_sample(contract, load(sample_path), sample_path)


def seal_automatic_policy(contract, policy, policy_path):
    contract["automatic_waiver_policy"] = policy_summary(policy, policy_path, contract.get("waivers", []))


def apply_insufficient_data_waivers(contract, policy, policy_path, skill_root, decision_stage="阶段2样本能力"):
    validate_policy_definition(policy)
    created = []
    for metric in contract.get("metrics", []):
        capability = metric.get("sample_capability")
        blockers = capability.get("blocking_reasons") if isinstance(capability, dict) else None
        if not blockers:
            continue
        if metric.get("kind") not in {"hard", "score"}:
            raise ValueError("样本能力自动豁免只允许硬指标或评分指标")
        if not isinstance(metric.get("sample_capability_input"), dict):
            raise ValueError("样本不足指标缺少可复算sample_capability_input")
        if any(
            not isinstance(item, dict)
            or item.get("side") not in {"原版", "FORMAL"}
            or not isinstance(item.get("required"), int)
            or not isinstance(item.get("actual"), int)
            or item["actual"] >= item["required"]
            or item.get("shortfall") != item["required"] - item["actual"]
            for item in blockers
        ):
            raise ValueError("样本能力阻塞原因不是可证明的纯计数不足")
        evidence = {
            "sample_capability_input": copy.deepcopy(metric["sample_capability_input"]),
            "sample_capability": copy.deepcopy(capability),
            "blocking_reasons": copy.deepcopy(blockers),
        }
        record = build_record(metric, INSUFFICIENT, policy, policy_path, evidence, decision_stage)
        apply_record(contract, metric, record)
        created.append(record)
    if created:
        refresh_downstream_policies(contract, skill_root)
    seal_automatic_policy(contract, policy, policy_path)
    contract["status"] = "已完成"
    return created


def validate_attainability_evidence(evidence, contract):
    if not isinstance(evidence, dict) or evidence.get("schema_version") != "slot-alignment.attainability-evidence.v1":
        raise ValueError("结构不可达证据Schema无效")
    if evidence.get("task_id") != contract.get("task_id") or evidence.get("status") != "结构不可达":
        raise ValueError("结构不可达证据任务或状态不一致")
    if evidence.get("budget_expansion_allowed") is not False:
        raise ValueError("结构不可达证据必须禁止继续扩张预算")
    proof = evidence.get("proof")
    if not isinstance(proof, dict) or set(proof) != PROOF_FIELDS or any(proof.get(field) is not True for field in PROOF_FIELDS):
        raise ValueError("结构不可达证据缺少完整静态、扰动、联合、稳定性或样本资格证明")
    affected = evidence.get("affected_metric_instances")
    if not isinstance(affected, list) or not affected:
        raise ValueError("结构不可达证据缺少受影响指标实例")
    files = evidence.get("evidence_files")
    if not isinstance(files, list) or not files or any(
        not isinstance(item, dict) or not non_empty(item.get("path")) or not isinstance(item.get("sha256"), str) or len(item["sha256"]) != 64
        for item in files
    ):
        raise ValueError("结构不可达证据缺少证据文件路径或SHA-256")


def apply_structural_unattainability_waivers(contract, evidence, evidence_path, policy, policy_path, skill_root):
    validate_policy_definition(policy)
    validate_attainability_evidence(evidence, contract)
    metrics = metric_map(contract)
    created = []
    evidence_file_sha = sha(evidence_path)
    for affected in evidence["affected_metric_instances"]:
        identity = affected.get("instance_id")
        metric = metrics.get(identity)
        if metric is None or metric.get("metric_id") != affected.get("metric_id") or metric.get("scope") != affected.get("scope"):
            raise ValueError(f"结构不可达证据未精确绑定合同指标实例: {identity}")
        if any(not non_empty(affected.get(field)) for field in ("conflict_evidence", "minimal_authority_expansion")):
            raise ValueError(f"结构不可达指标缺少冲突证据或最小扩权方向: {identity}")
        record_evidence = {
            "attainability_evidence_path": str(Path(evidence_path)),
            "attainability_evidence_file_sha256": evidence_file_sha,
            "attainability_evidence_snapshot_sha256": canonical_sha256(evidence),
            "proof": copy.deepcopy(evidence["proof"]),
            "affected_metric_instance": copy.deepcopy(affected),
            "evidence_files": copy.deepcopy(evidence["evidence_files"]),
        }
        record = build_record(metric, UNATTAINABLE, policy, policy_path, record_evidence, "阶段4结构可达性")
        apply_record(contract, metric, record)
        created.append(record)
    refresh_downstream_policies(contract, skill_root)
    seal_automatic_policy(contract, policy, policy_path)
    contract["status"] = "已完成"
    return created


def formal_count_rows(formal):
    rows = formal.get("sample", {}).get("metric_sample_counts") if isinstance(formal, dict) else None
    if not isinstance(rows, list):
        raise ValueError("FORMAL缺少逐指标实际样本计数")
    result = {}
    for row in rows:
        key = (row.get("metric_id"), row.get("scope")) if isinstance(row, dict) else (None, None)
        if not all(non_empty(value) for value in key) or key in result:
            raise ValueError("FORMAL逐指标样本计数缺失或重复")
        result[key] = row
    return result


def apply_formal_sample_waivers(contract, formal, policy, policy_path, skill_root):
    from apply_sample_capability_policy import GROUPED_METHODS, metric_capability

    validate_policy_definition(policy)
    rows = formal_count_rows(formal)
    sample_policy = contract.get("sample_capability_policy", {})
    sample_path = safe_policy_path(skill_root, sample_policy.get("source_path"), "样本能力政策")
    sample_definition = load(sample_path)
    created = []
    for metric in contract.get("metrics", []):
        if metric.get("waiver", {}).get("status") == "已批准" or not isinstance(metric.get("sample_capability_input"), dict):
            continue
        profile = metric.get("hard_gate_profile") or metric.get("score_profile") or {}
        if profile.get("method") not in sample_definition.get("covered_methods", []):
            continue
        row = rows.get((metric.get("metric_id"), metric.get("scope")))
        if row is None:
            raise ValueError(f"FORMAL缺少指标实际样本计数，属于输出缺失而非数据不足: {metric.get('metric_id')} / {metric.get('scope')}")
        candidate = copy.deepcopy(metric)
        inputs = candidate["sample_capability_input"]
        inputs["formal_sample_count"] = row.get("sample_count")
        if profile.get("method") in GROUPED_METHODS:
            inputs["formal_group_sample_counts"] = row.get("group_sample_counts")
        elif row.get("group_sample_counts") not in (None, {}):
            raise ValueError(f"非分组指标出现FORMAL条件组计数: {metric.get('metric_id')} / {metric.get('scope')}")
        capability = metric_capability(candidate, sample_definition)
        blockers = capability.get("blocking_reasons", [])
        if not blockers:
            continue
        if any(item.get("side") != "FORMAL" for item in blockers):
            raise ValueError("FORMAL复验发现原版侧仍不足，必须先修复阶段2合同")
        evidence = {
            "sample_capability_input": copy.deepcopy(inputs),
            "sample_capability": capability,
            "blocking_reasons": copy.deepcopy(blockers),
            "formal_metric_sample_count": copy.deepcopy(row),
        }
        record = build_record(metric, INSUFFICIENT, policy, policy_path, evidence, "阶段4 FORMAL实际样本能力")
        apply_record(contract, metric, record)
        created.append(record)
    if created:
        refresh_downstream_policies(contract, skill_root)
    seal_automatic_policy(contract, policy, policy_path)
    contract["status"] = "已完成"
    return created


def validate_automatic_waiver_binding(contract, skill_root):
    records = [item for item in contract.get("waivers", []) if isinstance(item, dict) and item.get("reason_code") in AUTO_REASONS]
    summary = contract.get("automatic_waiver_policy")
    if not records and summary is None:
        return []
    errors = []
    try:
        if not isinstance(summary, dict):
            raise ValueError("合同存在自动豁免但缺少automatic_waiver_policy")
        policy_path = safe_policy_path(skill_root, summary.get("source_path"), "自动豁免政策")
        policy = load(policy_path)
        validate_policy_definition(policy)
        if summary != policy_summary(policy, policy_path, contract.get("waivers", [])):
            raise ValueError("自动豁免政策摘要或决策绑定hash失效")
        metrics = metric_map(contract)
        ids = set()
        for record in records:
            waiver_id = record.get("waiver_id")
            if not non_empty(waiver_id) or waiver_id in ids:
                raise ValueError(f"自动豁免ID无效或重复: {waiver_id}")
            ids.add(waiver_id)
            metric = metrics.get(record.get("instance_id"))
            if metric is None:
                raise ValueError(f"自动豁免引用未知指标实例: {record.get('instance_id')}")
            if record.get("metric_id") != metric.get("metric_id") or record.get("scope") != metric.get("scope"):
                raise ValueError(f"自动豁免指标身份不一致: {waiver_id}")
            if record.get("kind") != metric.get("kind") or record.get("kind") not in policy["allowed_metric_kinds"]:
                raise ValueError(f"自动豁免指标类型无效: {waiver_id}")
            if record.get("status") != "已批准" or record.get("authorization_source") != policy["authorization_source"]:
                raise ValueError(f"自动豁免授权状态无效: {waiver_id}")
            if record.get("policy_id") != policy["policy_id"] or record.get("policy_sha256") != sha(policy_path):
                raise ValueError(f"自动豁免政策绑定无效: {waiver_id}")
            evidence = record.get("evidence")
            if record.get("evidence_sha256") != canonical_sha256(evidence):
                raise ValueError(f"自动豁免证据hash失效: {waiver_id}")
            if record.get("target_sha256") != canonical_sha256(metric.get("target")):
                raise ValueError(f"自动豁免目标绑定失效: {waiver_id}")
            metric_waiver = metric.get("waiver", {})
            if metric_waiver.get("waiver_id") != waiver_id or metric_waiver.get("reason_code") != record.get("reason_code") or metric_waiver.get("status") != "已批准":
                raise ValueError(f"指标内自动豁免与合同清单不一致: {waiver_id}")
            if record.get("reason_code") == INSUFFICIENT:
                from apply_sample_capability_policy import metric_capability

                if not isinstance(evidence, dict) or not isinstance(evidence.get("sample_capability_input"), dict):
                    raise ValueError(f"样本不足豁免缺少复算输入: {waiver_id}")
                sample_path = safe_policy_path(skill_root, contract.get("sample_capability_policy", {}).get("source_path"), "样本能力政策")
                candidate = copy.deepcopy(metric)
                candidate.pop("waiver", None)
                candidate["sample_capability_input"] = copy.deepcopy(evidence["sample_capability_input"])
                expected = metric_capability(candidate, load(sample_path))
                if expected != evidence.get("sample_capability") or not expected.get("blocking_reasons"):
                    raise ValueError(f"样本不足豁免无法确定性复算: {waiver_id}")
            else:
                affected = evidence.get("affected_metric_instance") if isinstance(evidence, dict) else None
                proof = evidence.get("proof") if isinstance(evidence, dict) else None
                if not isinstance(affected, dict) or affected.get("instance_id") != record.get("instance_id"):
                    raise ValueError(f"结构不可达豁免未绑定受影响实例: {waiver_id}")
                if not isinstance(proof, dict) or set(proof) != PROOF_FIELDS or any(proof.get(field) is not True for field in PROOF_FIELDS):
                    raise ValueError(f"结构不可达豁免缺少完整证明: {waiver_id}")
    except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError) as exc:
        errors.append(str(exc))
    return errors


def main():
    parser = argparse.ArgumentParser(description="按用户预授权政策自动豁免精确指标实例")
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--source", required=True, choices=["sample-capability", "formal-sample-capability", "structural-unattainability"])
    parser.add_argument("--formal-result", type=Path)
    parser.add_argument("--attainability-evidence", type=Path)
    parser.add_argument("--skill-root", type=Path, default=Path(__file__).resolve().parent.parent)
    args = parser.parse_args()
    contract, policy = load_contract(args.contract), load(args.policy)
    if args.source == "sample-capability":
        records = apply_insufficient_data_waivers(contract, policy, args.policy, args.skill_root)
    elif args.source == "formal-sample-capability":
        if args.formal_result is None:
            raise ValueError("FORMAL样本自动豁免必须提供--formal-result")
        records = apply_formal_sample_waivers(contract, load(args.formal_result), policy, args.policy, args.skill_root)
    else:
        if args.attainability_evidence is None:
            raise ValueError("结构不可达自动豁免必须提供--attainability-evidence")
        evidence = load(args.attainability_evidence)
        records = apply_structural_unattainability_waivers(contract, evidence, args.attainability_evidence, policy, args.policy, args.skill_root)
    write_contract(contract, args.output)
    print(json.dumps({
        "status": "通过",
        "source": args.source,
        "automatic_waiver_count": len(records),
        "requires_stage3_regeneration": bool(records),
        "output": str(args.output),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "失败", "error": str(exc)}, ensure_ascii=False))
        sys.exit(2)
