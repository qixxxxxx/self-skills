#!/usr/bin/env python3
"""从阶段1玩法画像确定性编译指标实例计划，并在生成大合同前检查统计能力。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from contract_io import load_json_strict, metric_instance_id, sha256_file
from semantic_contract_validation import (
    catalog_maps,
    expected_metrics,
    measurement_contract_sha256,
    required_package_ids,
    validate_profile,
    validate_scope_instances,
)


CAPABILITY_SCHEMA_VERSION = "slot-alignment.measurement-capabilities.v1"
PLAN_SCHEMA_VERSION = "slot-alignment.metric-instance-plan.v1"
SAMPLE_CAPABILITY_METHODS = {
    "total_variation",
    "wasserstein_1d",
    "grouped_total_variation",
    "grouped_wasserstein_1d",
    "mean_absolute_error",
    "grouped_mean_absolute_error",
}


def metric_library_gap(gap_id, gap_type, package_id, mechanic_ids, source_node_ids, reason, proposed_action, extension_targets):
    return {
        "gap_id": gap_id,
        "gap_type": gap_type,
        "package_id": package_id,
        "mechanic_ids": sorted(set(mechanic_ids)),
        "source_node_ids": sorted(set(source_node_ids)),
        "reason": reason,
        "proposed_action": proposed_action,
        "extension_targets": extension_targets,
        "decision_status": "待用户决定",
    }


def unknown_mechanic_gaps(game_profile, catalog):
    gaps = []
    for node in game_profile.get("mechanics", []):
        if not isinstance(node, dict):
            continue
        mechanic_id = node.get("mechanic_id")
        if not isinstance(mechanic_id, str) or not mechanic_id or mechanic_id in catalog["mechanics"]:
            continue
        gaps.append(metric_library_gap(
            f"metric-gap-{len(gaps) + 1:03d}",
            "unknown_mechanic_profile",
            None,
            [mechanic_id],
            [node.get("node_id")] if isinstance(node.get("node_id"), str) and node.get("node_id") else [],
            "玩法画像包含当前语义目录无法识别的玩法，因而无法证明存在对应指标Owner",
            "开工前先扩展玩法语义目录，再提出并实现对应指标包、Owner、测量合同和报告展示",
            ["mechanic_catalog", "metric_library", "measurement_contract", "report_display"],
        ))
    return gaps


def required_capabilities(metric):
    kind = metric.get("kind")
    profile = metric.get("score_profile") if kind == "score" else metric.get("hard_gate_profile")
    profile = profile if isinstance(profile, dict) else metric.get("audit_profile", {})
    method = profile.get("method") if isinstance(profile, dict) else None
    result = {"target_value", "candidate_measurement", "target_evidence_binding"}
    if kind == "audit":
        result.add("audit_result_fields")
    else:
        result.add("metric_sample_count")
    if kind == "score":
        result.add("sealed_event_set")
    if method in SAMPLE_CAPABILITY_METHODS:
        result.add("sample_capability_counts")
    if isinstance(method, str) and method.startswith("grouped_"):
        result.update({"conditional_group_ids", "conditional_group_sample_counts", "conditional_group_weight_evidence"})
    if method in {"wasserstein_1d", "grouped_wasserstein_1d"}:
        result.update({"business_axis_positions", "business_axis_labels"})
    if metric.get("metric_id") == "core.rtp.component_contribution":
        result.add("original_component_share")
    return sorted(result)


def _capability_map(capabilities):
    if capabilities is None:
        return None, []
    errors = []
    if not isinstance(capabilities, dict) or capabilities.get("schema_version") != CAPABILITY_SCHEMA_VERSION:
        return {}, ["measurement_capabilities Schema无效"]
    rows = capabilities.get("instances")
    if not isinstance(rows, list):
        return {}, ["measurement_capabilities.instances必须是数组"]
    result = {}
    for row in rows:
        instance_id = row.get("instance_id") if isinstance(row, dict) else None
        values = row.get("capabilities") if isinstance(row, dict) else None
        if (
            not isinstance(instance_id, str)
            or instance_id in result
            or not isinstance(values, list)
            or any(not isinstance(value, str) or not value for value in values)
        ):
            errors.append(f"measurement_capabilities实例无效或重复: {instance_id}")
            continue
        result[instance_id] = row
    return result, errors


def compile_instance_plan(game_profile, input_manifest, task_root, skill_root, capabilities=None):
    catalog = catalog_maps(skill_root)
    errors = list(catalog["errors"])
    metric_library_gaps = unknown_mechanic_gaps(game_profile, catalog)
    profile_errors, active_nodes, _ = validate_profile(game_profile, catalog, task_root, input_manifest)
    errors += profile_errors
    scope_errors, scope_instances = validate_scope_instances(game_profile, active_nodes, task_root, input_manifest)
    errors += scope_errors
    packages = required_package_ids(active_nodes, catalog)
    expected, _, bindings = expected_metrics(active_nodes, scope_instances, packages, catalog, errors, metric_library_gaps)
    provided, capability_errors = _capability_map(capabilities)
    errors += capability_errors
    instances, missing = [], []
    for metric_id, source_ids, dimension_items in sorted(expected):
        metric = catalog["metrics"][metric_id]
        dimensions = dict(dimension_items)
        source_ids = list(source_ids)
        instance_id = metric_instance_id(metric_id, source_ids, dimensions)
        requirements = required_capabilities(metric)
        binding = bindings.get((metric_id, tuple(source_ids), dimension_items))
        row = {
            "instance_id": instance_id,
            "metric_id": metric_id,
            "owner": metric.get("owner"),
            "kind": metric.get("kind"),
            "source_node_ids": source_ids,
            "instance_dimensions": dimensions,
            "scope_instance_id": binding.get("scope_instance_id") if isinstance(binding, dict) else None,
            "scope": binding.get("scope") if isinstance(binding, dict) else None,
            "measurement_contract_sha256": measurement_contract_sha256(metric),
            "required_capabilities": requirements,
        }
        if provided is not None:
            actual = provided.get(instance_id)
            actual_values = set(actual.get("capabilities", [])) if isinstance(actual, dict) else set()
            missing_values = sorted(set(requirements) - actual_values)
            measurement_hash = actual.get("measurement_contract_sha256") if isinstance(actual, dict) else None
            if measurement_hash != row["measurement_contract_sha256"]:
                missing_values.append("measurement_contract_sha256_match")
            row["capability_status"] = "通过" if not missing_values else "缺失"
            if missing_values:
                missing.append({
                    "instance_id": instance_id,
                    "metric_id": metric_id,
                    "source_node_ids": source_ids,
                    "instance_dimensions": dimensions,
                    "missing": sorted(set(missing_values)),
                })
        instances.append(row)
    expected_ids = {row["instance_id"] for row in instances}
    unknown = sorted(set(provided or {}) - expected_ids)
    if unknown:
        errors.append(f"measurement_capabilities包含未知实例: {','.join(unknown)}")
    if errors:
        status = "阻塞"
    elif provided is None:
        status = "待能力声明"
    elif missing:
        status = "阻塞"
    else:
        status = "通过"
    return {
        "schema_version": PLAN_SCHEMA_VERSION,
        "task_id": game_profile.get("task_id"),
        "status": status,
        "catalogs": {
            "mechanics_version": catalog["mechanics_index"].get("version"),
            "metrics_version": catalog["metrics_index"].get("version"),
            "hashes": {
                "mechanics": sha256_file(catalog["mechanics_index_path"]),
                "metrics": sha256_file(catalog["metrics_index_path"]),
            },
        },
        "required_packages": sorted(packages),
        "preflight_decision_gate": {
            "status": "待用户决定" if metric_library_gaps else "通过",
            "business_decision_window": "preflight",
            "metric_library_gap_count": len(metric_library_gaps),
            "extension_proposal_required": bool(metric_library_gaps),
            "stage_execution_allowed": not metric_library_gaps,
            "formal_execution_allowed": not metric_library_gaps,
        },
        "metric_library_gaps": metric_library_gaps,
        "expected_instance_count": len(instances),
        "capability_check": {
            "status": "未执行" if provided is None else ("通过" if not missing and not errors else "阻塞"),
            "provided_instance_count": 0 if provided is None else len(provided),
            "missing_instance_count": len(missing),
            "unknown_instance_ids": unknown,
        },
        "instances": instances,
        "missing_capabilities": missing,
        "errors": errors,
    }


def build_extension_proposal(plan):
    gaps = plan["metric_library_gaps"]
    return {
        "schema_version": "slot-alignment.metric-extension-proposal.v1",
        "task_id": plan["task_id"],
        "status": "待用户决定" if gaps else "无需扩展",
        "decision_window": "preflight",
        "blocks_stage_execution": bool(gaps),
        "blocks_formal_execution": bool(gaps),
        "gaps": gaps,
        "required_deliverables": [
            "更新玩法语义目录（存在未知玩法时）",
            "更新指标包与唯一Owner",
            "更新测量合同与Python统计能力",
            "通过目录、Schema、Owner和正反例校验",
            "自动生成或修正观测/输出派生脚本",
            "与用户认证原始脚本执行等价校验，失败时按差异自动修复并重跑",
        ] if gaps else [],
        "approval": {
            "status": "待确认" if gaps else "不适用",
            "user_decision": "",
            "decided_at": "",
        },
    }


def main():
    parser = argparse.ArgumentParser(description="编译通用指标实例计划并执行统计能力前置检查")
    parser.add_argument("--game-profile", required=True, type=Path)
    parser.add_argument("--input-manifest", required=True, type=Path)
    parser.add_argument("--task-root", required=True, type=Path)
    parser.add_argument("--measurement-capabilities", type=Path)
    parser.add_argument("--skill-root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--extension-proposal", type=Path)
    args = parser.parse_args()
    plan = compile_instance_plan(
        load_json_strict(args.game_profile),
        load_json_strict(args.input_manifest),
        args.task_root.resolve(),
        args.skill_root.resolve(),
        load_json_strict(args.measurement_capabilities) if args.measurement_capabilities else None,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.extension_proposal:
        proposal = build_extension_proposal(plan)
        args.extension_proposal.parent.mkdir(parents=True, exist_ok=True)
        args.extension_proposal.write_text(json.dumps(proposal, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": plan["status"], "expected_instance_count": plan["expected_instance_count"], "output": str(args.output)}, ensure_ascii=False))
    raise SystemExit(0 if plan["status"] in {"通过", "待能力声明"} else 2)


if __name__ == "__main__":
    main()
