#!/usr/bin/env python3
import copy
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from jsonschema import Draft202012Validator

from contract_io import ContractIOError, clear_contract_cache, contract_cache_stats, contract_content_identity, load_contract, metric_instance_id
from compact_metric_contract import write_compact_contract
from compile_metric_instances import build_extension_proposal, compile_instance_plan, required_capabilities
from apply_automatic_waiver_policy import (
    INSUFFICIENT,
    UNATTAINABLE,
    apply_insufficient_data_waivers,
    apply_structural_unattainability_waivers,
    validate_automatic_waiver_binding,
)
from apply_ordered_distance_policy import apply_policy as apply_ordered_distance_policy
from validate_artifacts import validate_attainability_ceiling, validate_component_rtp_targets
from report_common import TEMPLATE_PATHS, apply_metric_display_metadata, canonical_json_sha256, detail_rows, metric_blocks, metric_item_labels, metric_stage2_table, validate_continuous_execution_policy, validate_execution_qualification, validate_preflight_input_confirmation, validate_report_against_template, validate_template_text, validate_templates
from apply_sample_capability_policy import apply_policy as apply_sample_capability_policy
from apply_score_group_weight_policy import apply_policy as apply_score_group_weight_policy
from score_alignment import anchors, distance, sample_capability_summary, validate_formal_sample_capability, validate_reachable_support, validate_sample_capability_binding
from seal_delivery import delivery_report_contract_version
from catalog_tool import METRIC_CATEGORIES, condition_implies, validate_grouped_distribution_degeneracy, validate_matched_position_joint_contract, validate_owner_direction_contracts, validate_relationships, validate_score_profile
from semantic_contract_validation import (
    canonical_sha256,
    catalog_maps,
    condition_matches,
    expected_metrics,
    format_instance,
    measurement_contract_sha256,
    metric_instance_key,
    required_package_ids,
    resolve_derived_facts,
    sha as semantic_sha,
    validate_cascade_multiplier_derivation,
    validate_cascade_multiplier_ownership,
    validate_cascade_multiplier_profile_bindings,
    validate_conditional_group_weight_binding,
    validate_contract as validate_semantic_contract,
    validate_declared_derivation_projection,
    validate_feature_buy_contract,
    validate_feature_path_contract,
    validate_feature_return_zero_bucket,
    validate_hold_spin_capacity_ownership,
    validate_inapplicability,
    validate_matched_position_transition_bindings,
    validate_matched_position_transition_contract,
    validate_metric_target,
    validate_mode_contract,
    validate_multiplier_return_contract,
    validate_persistent_position_contract,
    validate_profile,
    validate_profile_links,
    validate_respin_persistent_derivation,
    validate_respin_position_contract,
    validate_step_return_owner_partitions,
    validate_transform_target_coherence_contract,
    validate_value_symbol_multiplier_derivation,
    validate_value_symbol_multiplier_ownership,
    validate_value_symbol_multiplier_profile_bindings,
)


ROOT = Path(__file__).resolve().parent
SKILL_ROOT = ROOT.parent


def dump(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def contract_io_case(root):
    root.mkdir(parents=True, exist_ok=True)
    legacy = {"schema_version": "1.3", "task_id": "legacy", "metrics": []}
    legacy_path = root / "legacy.json"
    dump(legacy_path, legacy)
    assert load_contract(legacy_path, SKILL_ROOT) == legacy

    duplicate_path = root / "duplicate.json"
    duplicate_path.write_text('{"schema_version":"1.4","schema_version":"1.4"}\n', encoding="utf-8")
    try:
        load_contract(duplicate_path, SKILL_ROOT)
        raise AssertionError("重复JSON键未阻塞")
    except ContractIOError as exc:
        assert "重复键" in str(exc)

    source_nodes = ["node-b", "node-a", "node-a"]
    dimensions = {"state": "base_game", "component": "base"}
    instance_id = metric_instance_id("core.rtp.total", source_nodes, dimensions)
    assert instance_id == metric_instance_id("core.rtp.total", list(reversed(source_nodes)), dimensions)

    external_dir = root / "metric_contract_data"
    external_dir.mkdir()
    external_path = external_dir / "metric-tensors.json"
    dump(external_path, {
        "schema_version": "slot-alignment.contract-data.v1",
        "records": [{
            "ref_id": f"target:{instance_id}",
            "instance_id": instance_id,
            "value": [0.95, 0.96],
        }],
    })
    metric_index = SKILL_ROOT / "references/指标目录/index.json"
    compact = {
        "schema_version": "1.4",
        "task_id": "compact",
        "catalogs": {
            "metrics_version": load_json(metric_index)["version"],
            "hashes": {"metrics": sha(metric_index)},
        },
        "contract_storage": {
            "layout": "compact_metric_instances_v1",
            "instance_id_algorithm": "metric-instance-id-v1",
        },
        "metrics": [{
            "instance_id": instance_id,
            "metric_id": "core.rtp.total",
            "source_node_ids": source_nodes,
            "instance_dimensions": dimensions,
            "scope": "normal:g1|component=base|mode=normal|state=base_game",
            "status": "适用",
            "target": {"$data_ref": f"target:{instance_id}"},
            "hard_gate_profile_patch": {"tolerance": 0},
        }],
        "external_data": [{
            "data_id": "metric-tensors",
            "path": "metric_contract_data/metric-tensors.json",
            "schema_version": "slot-alignment.contract-data.v1",
            "sha256": sha(external_path),
            "record_count": 1,
            "instance_count": 1,
        }],
    }
    compact_path = root / "metric_contract.json"
    dump(compact_path, compact)
    expanded = load_contract(compact_path, SKILL_ROOT)
    assert expanded["metrics"][0]["name_zh"] == "总RTP"
    assert expanded["metrics"][0]["target"] == [0.95, 0.96]
    assert expanded["metrics"][0]["hard_gate_profile"]["method"] == "range_error"
    assert expanded["metrics"][0]["hard_gate_profile"]["tolerance"] == 0
    assert len(contract_content_identity(compact_path)) == 64
    clear_contract_cache()
    first = load_contract(compact_path, SKILL_ROOT)
    second = load_contract(compact_path, SKILL_ROOT)
    assert contract_cache_stats() == {"hits": 1, "misses": 1, "entries": 1, "max_entries": 4}
    first["metrics"][0]["target"] = [0, 0]
    assert second["metrics"][0]["target"] == [0.95, 0.96]
    assert load_contract(compact_path, SKILL_ROOT)["metrics"][0]["target"] == [0.95, 0.96]

    roundtrip_source = copy.deepcopy(expanded)
    roundtrip_source["schema_version"] = "1.3"
    roundtrip_source["report_contract_version"] = "slot-alignment.reports.v3.3"
    roundtrip_path = root / "roundtrip/metric_contract.json"
    write_compact_contract(roundtrip_source, roundtrip_path, SKILL_ROOT, threshold=1)
    roundtrip = load_contract(roundtrip_path, SKILL_ROOT)
    assert roundtrip["metrics"] == expanded["metrics"]
    compact_roundtrip = load_json(roundtrip_path)
    assert "name_zh" not in compact_roundtrip["metrics"][0]
    assert compact_roundtrip["metrics"][0]["target"].keys() == {"$data_ref"}
    compact_schema = load_json(SKILL_ROOT / "assets/schemas/metric-contract-compact.schema.json")
    data_schema = load_json(SKILL_ROOT / "assets/schemas/contract-data.schema.json")
    assert list(Draft202012Validator(compact_schema).iter_errors(compact_roundtrip)) == []
    assert list(Draft202012Validator(data_schema).iter_errors(load_json(roundtrip_path.parent / "metric_contract_data/metric-data.json"))) == []
    policy_output = root / "roundtrip/policy_metric_contract.json"
    run(
        ROOT / "apply_hard_gate_tolerance_policy.py",
        "--contract", roundtrip_path,
        "--policy", SKILL_ROOT / "assets/policies/hard_gate_tolerance_policy.v2.json",
        "--output", policy_output,
    )
    assert load_json(policy_output)["schema_version"] == "1.4"
    assert load_contract(policy_output, SKILL_ROOT)["hard_gate_tolerance_policy"]["policy_id"] == "future-default-hard-gate-tolerance-factors-v2"

    tampered = load_json(external_path)
    tampered["records"][0]["value"] = [0.94, 0.97]
    dump(external_path, tampered)
    try:
        load_contract(compact_path, SKILL_ROOT)
        raise AssertionError("外部数据Hash失效未阻塞")
    except ContractIOError as exc:
        assert "SHA-256失效" in str(exc)

    compact["external_data"][0]["path"] = "../escape.json"
    dump(compact_path, compact)
    try:
        load_contract(compact_path, SKILL_ROOT)
        raise AssertionError("外部数据越界路径未阻塞")
    except ContractIOError as exc:
        assert "path不安全" in str(exc)


def instance_compiler_case(root):
    valid_root = root / "valid"
    profile = load_json(valid_root / "game_profile.json")
    manifest = load_json(valid_root / "input_manifest.json")
    plan = compile_instance_plan(profile, manifest, valid_root, SKILL_ROOT)
    contract = load_json(valid_root / "metric_contract.json")
    assert plan["status"] == "待能力声明", plan["errors"]
    plan_schema = load_json(SKILL_ROOT / "assets/schemas/metric-instance-plan.schema.json")
    proposal_schema = load_json(SKILL_ROOT / "assets/schemas/metric-extension-proposal.schema.json")
    capability_schema = load_json(SKILL_ROOT / "assets/schemas/measurement-capabilities.schema.json")
    assert list(Draft202012Validator(plan_schema).iter_errors(plan)) == []
    assert plan["preflight_decision_gate"] == {
        "status": "通过",
        "business_decision_window": "preflight",
        "metric_library_gap_count": 0,
        "extension_proposal_required": False,
        "stage_execution_allowed": True,
        "formal_execution_allowed": True,
    }
    no_extension = build_extension_proposal(plan)
    assert list(Draft202012Validator(proposal_schema).iter_errors(no_extension)) == []
    assert no_extension["status"] == "无需扩展" and no_extension["required_deliverables"] == []
    assert plan["expected_instance_count"] == len(contract["metrics"])
    assert len({item["instance_id"] for item in plan["instances"]}) == len(plan["instances"])
    capabilities = {
        "schema_version": "slot-alignment.measurement-capabilities.v1",
        "instances": [{
            "instance_id": item["instance_id"],
            "measurement_contract_sha256": item["measurement_contract_sha256"],
            "capabilities": item["required_capabilities"],
        } for item in plan["instances"]],
    }
    assert list(Draft202012Validator(capability_schema).iter_errors(capabilities)) == []
    passed = compile_instance_plan(profile, manifest, valid_root, SKILL_ROOT, capabilities)
    assert passed["status"] == "通过"
    capabilities["instances"][0]["capabilities"] = capabilities["instances"][0]["capabilities"][1:]
    blocked = compile_instance_plan(profile, manifest, valid_root, SKILL_ROOT, capabilities)
    assert blocked["status"] == "阻塞" and blocked["missing_capabilities"]
    unknown_profile = copy.deepcopy(profile)
    unknown_profile["mechanics"][0]["mechanic_id"] = "feature.future-bonus"
    unknown_plan = compile_instance_plan(unknown_profile, manifest, valid_root, SKILL_ROOT)
    assert unknown_plan["status"] == "阻塞"
    assert unknown_plan["preflight_decision_gate"] == {
        "status": "待用户决定",
        "business_decision_window": "preflight",
        "metric_library_gap_count": 1,
        "extension_proposal_required": True,
        "stage_execution_allowed": False,
        "formal_execution_allowed": False,
    }
    assert unknown_plan["metric_library_gaps"][0]["gap_type"] == "unknown_mechanic_profile"
    assert list(Draft202012Validator(plan_schema).iter_errors(unknown_plan)) == []
    proposal = build_extension_proposal(unknown_plan)
    assert list(Draft202012Validator(proposal_schema).iter_errors(proposal)) == []
    assert proposal["decision_window"] == "preflight"
    assert proposal["blocks_stage_execution"] is True and proposal["blocks_formal_execution"] is True
    assert "metric_library" in proposal["gaps"][0]["extension_targets"]
    continuous_path = SKILL_ROOT / "assets/policies/continuous_execution_policy.v1.json"
    continuous = load_json(continuous_path)
    sealed_continuous = {**continuous, "source_sha256": sha(continuous_path)}
    assert validate_continuous_execution_policy(sealed_continuous, SKILL_ROOT) == []
    invalid_continuous = copy.deepcopy(sealed_continuous)
    invalid_continuous["business_decision_windows"] = ["runtime"]
    assert any("字段与来源不一致" in error for error in validate_continuous_execution_policy(invalid_continuous, SKILL_ROOT))
    for field in (
        "preflight_sample_count_confirmation_required",
        "full_recount_when_user_requested",
        "preflight_python_script_identity_confirmation_required",
    ):
        invalid_continuous = copy.deepcopy(sealed_continuous)
        invalid_continuous[field] = False
        assert any(field in error for error in validate_continuous_execution_policy(invalid_continuous, SKILL_ROOT))
    compact_path = valid_root / "metric_contract-1.4.json"
    write_compact_contract(contract, compact_path, SKILL_ROOT, threshold=1)
    compact_errors = validate_semantic_contract(
        valid_root / "game_profile.json",
        compact_path,
        SKILL_ROOT,
        valid_root / "parameter_authority.json",
        valid_root / "input_manifest.json",
        task_root_path=valid_root,
    )
    assert compact_errors == [], compact_errors
    compact_report = valid_root / "compact-stage2.md"
    run(ROOT / "render_metric_matching_report.py", "--contract", compact_path, "--output", compact_report)
    assert "阶段2-指标匹配报告" in compact_report.read_text(encoding="utf-8")
    measurements_path = valid_root / "compact-measurements.json"
    dump(measurements_path, {"measurements": [{
        "metric_id": item["metric_id"],
        "scope": item["scope"],
        "status": "符合" if item["kind"] == "audit" else "有效",
        "value": item["target"],
    } for item in contract["metrics"] if item.get("status") != "不适用"]})
    scorecard_path = valid_root / "compact-scorecard.json"
    score_process = run_result(ROOT / "score_alignment.py", "--contract", compact_path, "--measurements", measurements_path, "--output", scorecard_path)
    assert score_process.returncode in {0, 2} and scorecard_path.is_file()
    assert load_json(scorecard_path)["schema_version"] == "1.3"
    scoring_report = valid_root / "compact-stage3.md"
    run(ROOT / "render_scoring_report.py", "--contract", compact_path, "--scorecard", scorecard_path, "--output", scoring_report)
    assert "阶段3-评分报告" in scoring_report.read_text(encoding="utf-8")


def preflight_input_confirmation_case(root):
    root.mkdir(parents=True, exist_ok=True)
    samples = [
        {"batch_id": "source-a", "paid_entry_count": 12, "status": "completed", "unit": "完整付费入口", "qualification": "合格"},
        {"batch_id": "source-b", "paid_entry_count": 8, "status": "completed", "unit": "完整付费入口", "qualification": "合格"},
    ]
    script_path = "/tmp/demo_simulator.py"
    script_sha = "b" * 64
    manifest = {
        "schema_version": "1.2",
        "report_contract_version": "slot-alignment.reports.v3.3",
        "task_id": "preflight-input-test",
        "status": "已完成",
        "scope": {"game_code": "demo", "mode": "normal", "rtp_group": 1, "target_rtp": {"min": 0.95, "max": 0.96}},
        "paths": {"simulation_script": script_path},
        "hashes": {"simulation_script": script_sha},
        "source_samples": samples,
        "preflight_input_confirmation": {
            "status": "通过",
            "decision_window": "preflight",
            "confirmed_by": "user",
            "confirmed_at": "2026-08-27T00:00:00Z",
            "confirmation_evidence_path": "evidence/preflight-input-approval.json",
            "confirmation_evidence_sha256": "a" * 64,
            "sample_count": {
                "discovered_source_count": 2,
                "discovered_entry_count": 20,
                "source_samples_sha256": canonical_json_sha256(samples),
                "recount_requested": False,
                "recount_scope": "all_discovered_sources",
                "recount_status": "不要求",
                "all_discovered_sources_processed": False,
                "processed_source_count": 0,
                "recounted_entry_count": None,
                "recount_result_path": "",
                "recount_result_sha256": "",
                "effective_entry_count": 20,
                "user_confirmed_entry_count": 20,
            },
            "python_script": {
                "status": "通过",
                "confirmed_name": "demo_simulator.py",
                "confirmed_path": script_path,
                "confirmed_sha256": script_sha,
            },
        },
        "preflight_decision_gate": {
            "status": "通过",
            "business_decision_window": "preflight",
            "metric_library_gap_count": 0,
            "extension_decision_status": "无需扩展",
        },
        "script_qualification": {
            "status": "通过",
            "certified_execution_path": "python",
            "certification_method": "user_direct",
            "user_certification": {
                "status": "通过",
                "certified_by": "user",
                "approved_at": "2026-08-27T00:00:00Z",
                "evidence_path": "evidence/script-approval.json",
                "evidence_sha256": "c" * 64,
                "certified_script_sha256": script_sha,
                "certified_scope": ["RTP与派奖账本", "玩法状态与统计输出"],
            },
        },
        "blockers": [],
    }
    schema = load_json(SKILL_ROOT / "assets/schemas/preflight-input-confirmation.schema.json")
    assert list(Draft202012Validator(schema).iter_errors(manifest["preflight_input_confirmation"])) == []
    assert validate_preflight_input_confirmation(manifest) == []
    assert validate_execution_qualification(manifest) == []

    def errors_after(mutate):
        invalid = copy.deepcopy(manifest)
        mutate(invalid)
        return validate_preflight_input_confirmation(invalid)

    assert "用户要求重新统计但全量重算未完成" in errors_after(
        lambda item: item["preflight_input_confirmation"]["sample_count"].update({"recount_requested": True, "recount_status": "进行中"})
    )

    def partial_recount(item):
        sample = item["preflight_input_confirmation"]["sample_count"]
        sample.update({
            "recount_requested": True,
            "recount_status": "已完成",
            "all_discovered_sources_processed": True,
            "processed_source_count": 1,
            "recounted_entry_count": 18,
            "recount_result_path": "evidence/recount.json",
            "recount_result_sha256": "d" * 64,
            "effective_entry_count": 18,
            "user_confirmed_entry_count": 18,
        })

    assert "全量重算处理源数量与发现源数量不一致" in errors_after(partial_recount)

    def mismatched_user_count(item):
        partial_recount(item)
        sample = item["preflight_input_confirmation"]["sample_count"]
        sample["processed_source_count"] = 2
        sample["user_confirmed_entry_count"] = 17

    assert "用户确认样本数与最终有效入口数不一致" in errors_after(mismatched_user_count)
    assert "确认的Python脚本文件名与执行路径不一致" in errors_after(
        lambda item: item["preflight_input_confirmation"]["python_script"].update({"confirmed_name": "other.py"})
    )

    def relative_script_path(item):
        item["paths"]["simulation_script"] = "demo_simulator.py"
        item["preflight_input_confirmation"]["python_script"]["confirmed_path"] = "demo_simulator.py"

    assert "确认的Python脚本路径必须是绝对.py路径" in errors_after(relative_script_path)
    assert "确认的Python脚本hash与当前脚本不一致" in errors_after(
        lambda item: item["preflight_input_confirmation"]["python_script"].update({"confirmed_sha256": "e" * 64})
    )

    artifacts = root / "artifacts"
    stage1 = artifacts / "01-input-profile"
    reports = root / "reports"
    dump(stage1 / "input_manifest.json", manifest)
    dump(stage1 / "game_profile.json", {
        "schema_version": "1.2",
        "report_contract_version": "slot-alignment.reports.v3.3",
        "task_id": manifest["task_id"],
        "status": "已完成",
        "scope": manifest["scope"],
        "mechanics_catalog": {"version": "test", "sha256": "f" * 64},
        "mechanics": [],
        "required_node_count": 0,
        "semantic_gap_count": 0,
        "gaps": [],
    })
    dump(stage1 / "parameter_authority.json", {
        "schema_version": "1.1",
        "report_contract_version": "slot-alignment.reports.v3.3",
        "task_id": manifest["task_id"],
        "status": "已完成",
        "scope": manifest["scope"],
        "parameters": [],
        "forbidden_categories": [],
        "conflicts": [],
    })
    report_path = reports / "阶段1-资料确认与玩法画像.md"
    run(ROOT / "render_input_profile_report.py", "--artifacts", artifacts, "--output", report_path)
    report = report_path.read_text(encoding="utf-8")
    assert "发现付费入口" in report and "Python脚本绝对路径" in report
    assert "| 最终准入 | 允许 |" in report
    blocked_manifest = copy.deepcopy(manifest)
    blocked_manifest["preflight_input_confirmation"]["sample_count"].update({"recount_requested": True, "recount_status": "进行中"})
    dump(stage1 / "input_manifest.json", blocked_manifest)
    run(ROOT / "render_input_profile_report.py", "--artifacts", artifacts, "--output", report_path)
    blocked_report = report_path.read_text(encoding="utf-8")
    assert "用户要求重新统计但全量重算未完成" in blocked_report
    assert "| 最终准入 | 禁止 |" in blocked_report


def full_catalog_matrix_case(root):
    catalog = catalog_maps(SKILL_ROOT)
    assert catalog["errors"] == []
    assert len(catalog["mechanics"]) == 24
    assert len(catalog["metric_packages"]) == 24
    assert len(catalog["metrics"]) == 104

    metrics = []
    for metric_id, definition in sorted(catalog["metrics"].items()):
        item = copy.deepcopy(definition)
        source_ids = [] if definition["owner"] == "core.general" else [f"node-{definition['owner']}"]
        dimensions = {"matrix_case": metric_id}
        item.update({
            "source_node_ids": source_ids,
            "instance_dimensions": dimensions,
            "scope": f"matrix|metric={metric_id}",
            "status": "适用",
            "target": {"低": 0.5, "高": 0.5},
        })
        assert required_capabilities(definition)
        metrics.append(item)
    full = {
        "schema_version": "1.3",
        "report_contract_version": "slot-alignment.reports.v3.3",
        "task_id": "full-catalog-matrix",
        "catalogs": {
            "mechanics_version": catalog["mechanics_index"]["version"],
            "metrics_version": catalog["metrics_index"]["version"],
            "hashes": {
                "mechanics": semantic_sha(catalog["mechanics_index_path"]),
                "metrics": semantic_sha(catalog["metrics_index_path"]),
            },
        },
        "metrics": metrics,
    }
    compact_path = root / "metric_contract.json"
    write_compact_contract(full, compact_path, SKILL_ROOT, threshold=1)
    expanded = load_contract(compact_path, SKILL_ROOT)
    expected = copy.deepcopy(metrics)
    for item in expected:
        item["instance_id"] = metric_instance_id(item["metric_id"], item["source_node_ids"], item["instance_dimensions"])
    assert expanded["metrics"] == expected
    source_path = root / "source-1.3.json"
    dump(source_path, full)
    benchmark_path = root / "benchmark.json"
    run(
        ROOT / "benchmark_contract_io.py",
        "--contract", source_path,
        "--work-dir", root / "benchmark-work",
        "--repetitions", 1,
        "--output", benchmark_path,
    )
    assert load_json(benchmark_path)["status"] == "通过"
    compact_benchmark_path = root / "benchmark-compact.json"
    run(
        ROOT / "benchmark_contract_io.py",
        "--contract", compact_path,
        "--work-dir", root / "benchmark-compact-work",
        "--repetitions", 1,
        "--output", compact_benchmark_path,
    )
    compact_benchmark = load_json(compact_benchmark_path)
    assert compact_benchmark["status"] == "通过" and compact_benchmark["sizes"]["main_ratio"] is None

    def mechanic_node(mechanic_id, suffix):
        return {"node_id": f"{mechanic_id}-{suffix}", "mechanic_id": mechanic_id, "attributes": {}}

    witness_count = 0
    for package_id, package in sorted(catalog["metric_packages"].items()):
        condition = package.get("applies_when", {})
        if condition.get("always") is True:
            assert package_id in required_package_ids([], catalog)
            witness_count += 1
            continue
        any_ids = condition.get("mechanic_id_any") or [condition.get("mechanic_id")]
        any_ids = [value for value in any_ids if value]
        branches = any_ids or [None]
        for branch_index, branch in enumerate(branches):
            mechanic_ids = [branch] if branch else []
            mechanic_ids += condition.get("mechanic_id_all", [])
            mechanic_ids += [
                row["mechanic_id"] for row in condition.get("attribute_conditions", [])
                if isinstance(row, dict) and row.get("mechanic_id")
            ]
            mechanic_ids = list(dict.fromkeys(mechanic_ids))
            nodes = [mechanic_node(mechanic_id, branch_index) for mechanic_id in mechanic_ids]
            for attribute in condition.get("required_attributes", []):
                target = next((
                    node for node in nodes
                    if attribute in set(catalog["mechanics"][node["mechanic_id"]].get("required_attributes", []))
                    | set(catalog["mechanics"][node["mechanic_id"]].get("optional_attributes", []))
                ), nodes[0])
                target["attributes"][attribute] = True
            for row in condition.get("attribute_conditions", []):
                target = next(node for node in nodes if node["mechanic_id"] == row["mechanic_id"])
                target["attributes"][row["attribute"]] = row.get("value", True)
            for node in nodes:
                if node["mechanic_id"].startswith("feature."):
                    node["attributes"].update({
                        "entry_sources": ["natural"],
                        "entry_source_semantics": {"natural": {"origin": "endogenous", "source_kind": "game_rule"}},
                    })
            assert condition_matches(condition, nodes), (package_id, branch)
            assert package_id in required_package_ids(nodes, catalog), (package_id, branch)
            witness_count += 1
    assert witness_count >= len(catalog["metric_packages"])


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(*args):
    return subprocess.run([sys.executable, *map(str, args)], check=True, capture_output=True, text=True)


def run_result(*args):
    return subprocess.run([sys.executable, *map(str, args)], check=False, capture_output=True, text=True)


def seal_modern_policies(contract_path):
    run(
        ROOT / "apply_ordered_distance_policy.py",
        "--contract", contract_path,
        "--policy", SKILL_ROOT / "assets/policies/ordered_distance_policy.v1.json",
        "--output", contract_path,
    )
    run(
        ROOT / "apply_score_group_weight_policy.py",
        "--contract", contract_path,
        "--policy", SKILL_ROOT / "assets/policies/score_group_weight_policy.v1.json",
        "--output", contract_path,
    )


def normal_mode_contract(mode="base", evidence_sha256="a" * 64):
    return {
        "mode_id": mode,
        "feature_mode_selections": [],
        "paid_configuration": {
            "configuration_id": "normal",
            "configuration_type": "normal",
            "actual_economic_bet_field": "paid_entry.actual_economic_bet",
            "actual_economic_bet_definition": "每个完整付费入口实际扣除的投注金额",
            "sample_partition_field": "paid_configuration_id",
            "sample_partition_value": "normal",
            "fixed_for_task": True,
            "evidence_sha256": evidence_sha256,
        },
        "mixed_sample_forbidden": True,
    }


def sample_capability_case(root):
    root.mkdir(parents=True, exist_ok=True)
    policy_path = SKILL_ROOT / "assets/policies/sample_capability_policy.v1.json"
    policy = load_json(policy_path)
    contract = {
        "schema_version": "1.3",
        "task_id": "sample-capability-test",
        "metrics": [
            {
                "metric_id": "demo.tv",
                "scope": "base",
                "kind": "score",
                "status": "适用",
                "target": [0.5, 0.5],
                "score_group": "feature_experience",
                "score_budget_key": "demo.tv",
                "scope_aggregation": "weighted_mean",
                "scope_weight": 1.0,
                "weight": 1.0,
                "score_profile": {"method": "total_variation", "anchors": [[0, 100], [0.02, 95], [0.1, 0]], "reachable_support_source": "task_contract", "reachable_support_status": "active"},
                "sample_capability_input": {"original_sample_count": 40000, "formal_sample_count": 40000},
            },
            {
                "metric_id": "demo.grouped-residual",
                "scope": "feature",
                "kind": "score",
                "status": "适用",
                "target": {"g1::a": 0.0, "g2::a": 0.0},
                "score_group": "feature_experience",
                "score_budget_key": "demo.grouped-residual",
                "scope_aggregation": "weighted_mean",
                "scope_weight": 1.0,
                "weight": 1.0,
                "score_profile": {
                    "method": "grouped_mean_absolute_error",
                    "anchors": [[0, 100], [0.02, 95], [0.1, 0]],
                    "group_separator": "::",
                    "group_weight_source": "task_contract",
                    "group_weights": {"g1": 0.5, "g2": 0.5},
                    "normalization_tolerance": 1e-6,
                },
                "sample_capability_input": {
                    "original_sample_count": 280000,
                    "formal_sample_count": 280000,
                    "original_group_sample_counts": {"g1": 140000, "g2": 140000},
                    "formal_group_sample_counts": {"g1": 140000, "g2": 140000},
                },
            },
        ],
    }
    legacy = copy.deepcopy(contract)
    legacy["schema_version"] = "1.2"
    for metric in legacy["metrics"]:
        metric.pop("sample_capability_input", None)
    assert validate_sample_capability_binding(legacy, SKILL_ROOT) == []
    assert any("缺少sample_capability_policy" in error for error in validate_sample_capability_binding(contract, SKILL_ROOT))
    apply_sample_capability_policy(contract, policy, policy_path)
    assert validate_sample_capability_binding(contract, SKILL_ROOT) == []
    tampered_hash = copy.deepcopy(contract)
    tampered_hash["sample_capability_policy"]["source_sha256"] = "0" * 64
    assert any("hash失效" in error for error in validate_sample_capability_binding(tampered_hash, SKILL_ROOT))
    tampered_metric = copy.deepcopy(contract)
    tampered_metric["metrics"][0]["sample_capability"]["formal_actual_sample_count"] += 1
    assert any("逐指标样本能力被篡改" in error or "政策摘要" in error for error in validate_sample_capability_binding(tampered_metric, SKILL_ROOT))
    insufficient = copy.deepcopy(contract)
    insufficient.pop("sample_capability_policy")
    for metric in insufficient["metrics"]:
        metric.pop("sample_capability")
    insufficient["metrics"][0]["sample_capability_input"]["formal_sample_count"] = 1
    apply_sample_capability_policy(insufficient, policy, policy_path)
    assert any("计划样本能力不足" in error for error in validate_sample_capability_binding(insufficient, SKILL_ROOT))
    summary = sample_capability_summary(contract)
    formal = {
        "schema_version": "1.2",
        "scorecard": {"sample_capability_policy": summary},
        "sample": {
            "metric_sample_counts": [
                {"metric_id": "demo.tv", "scope": "base", "sample_count": 40000, "group_sample_counts": {}},
                {"metric_id": "demo.grouped-residual", "scope": "feature", "sample_count": 280000, "group_sample_counts": {"g1": 140000, "g2": 140000}},
            ]
        },
    }
    assert validate_formal_sample_capability(contract, formal, SKILL_ROOT) == []
    missing = copy.deepcopy(formal)
    missing["sample"]["metric_sample_counts"].pop()
    assert any("缺少指标实际样本计数" in error for error in validate_formal_sample_capability(contract, missing, SKILL_ROOT))
    duplicate = copy.deepcopy(formal)
    duplicate["sample"]["metric_sample_counts"].append(copy.deepcopy(duplicate["sample"]["metric_sample_counts"][0]))
    assert any("样本计数重复" in error for error in validate_formal_sample_capability(contract, duplicate, SKILL_ROOT))
    bad_groups = copy.deepcopy(formal)
    bad_groups["sample"]["metric_sample_counts"][1]["group_sample_counts"] = {"g1": 280000}
    assert any("活动条件组完全一致" in error for error in validate_formal_sample_capability(contract, bad_groups, SKILL_ROOT))
    actual_insufficient = copy.deepcopy(formal)
    actual_insufficient["sample"]["metric_sample_counts"][0]["sample_count"] = 1
    assert any("FORMAL实际样本能力不足" in error for error in validate_formal_sample_capability(contract, actual_insufficient, SKILL_ROOT))
    policy_mismatch = copy.deepcopy(formal)
    policy_mismatch["scorecard"]["sample_capability_policy"]["source_sha256"] = "f" * 64
    assert any("政策摘要与合同不一致" in error for error in validate_formal_sample_capability(contract, policy_mismatch, SKILL_ROOT))
    contract_path = root / "metric_contract.json"
    dump(contract_path, contract)
    import validate_stage_transition as stage_transition
    original_validator = stage_transition.validate_semantic_contract
    observed = {}
    def fake_validator(_, legacy_path, *__args, **__kwargs):
        observed["version"] = load_json(legacy_path)["schema_version"]
        observed["path"] = Path(legacy_path)
        return ["旧语义门禁已执行"]
    stage_transition.validate_semantic_contract = fake_validator
    try:
        result = stage_transition.validate_semantic_compatible(
            root / "game_profile.json", contract_path, SKILL_ROOT,
            root / "parameter_authority.json", root / "input_manifest.json",
            "stage_transition", root,
        )
    finally:
        stage_transition.validate_semantic_contract = original_validator
    assert result == ["旧语义门禁已执行"] and observed["version"] == "1.3"
    assert observed["path"] == contract_path and observed["path"].exists()
    scored_contract_path = root / "scored_contract.json"
    dump(scored_contract_path, contract)
    run(ROOT / "apply_ordered_distance_policy.py", "--contract", scored_contract_path, "--policy", SKILL_ROOT / "assets/policies/ordered_distance_policy.v1.json", "--output", scored_contract_path)
    run(ROOT / "apply_score_group_weight_policy.py", "--contract", scored_contract_path, "--policy", SKILL_ROOT / "assets/policies/score_group_weight_policy.v1.json", "--output", scored_contract_path)
    measurements_path = root / "measurements.json"
    dump(measurements_path, {"measurements": [
        {"metric_id": "demo.tv", "scope": "base", "status": "有效", "value": [0.5, 0.5]},
        {"metric_id": "demo.grouped-residual", "scope": "feature", "status": "有效", "value": {"g1::a": 0.0, "g2::a": 0.0}},
    ]})
    scorecard_path = root / "scorecard.json"
    run(ROOT / "score_alignment.py", "--contract", scored_contract_path, "--measurements", measurements_path, "--output", scorecard_path)
    scorecard = load_json(scorecard_path)
    assert scorecard["schema_version"] == "1.3"
    assert scorecard["sample_capability_policy"] == sample_capability_summary(load_json(scored_contract_path))
    assert scorecard["alignment_status"] == "通过" and not scorecard["blocking_reasons"]

    automatic_policy_path = SKILL_ROOT / "assets/policies/automatic_metric_waiver_policy.v1.json"
    automatic_policy = load_json(automatic_policy_path)
    ordered_policy_path = SKILL_ROOT / "assets/policies/ordered_distance_policy.v1.json"
    score_policy_path = SKILL_ROOT / "assets/policies/score_group_weight_policy.v1.json"
    auto_contract = copy.deepcopy(contract)
    auto_contract.pop("sample_capability_policy", None)
    for metric in auto_contract["metrics"]:
        metric.pop("sample_capability", None)
    auto_contract["metrics"][0]["sample_capability_input"]["formal_sample_count"] = 1
    apply_ordered_distance_policy(auto_contract, load_json(ordered_policy_path), ordered_policy_path)
    apply_score_group_weight_policy(auto_contract, load_json(score_policy_path), score_policy_path)
    apply_sample_capability_policy(auto_contract, policy, policy_path)
    created = apply_insufficient_data_waivers(auto_contract, automatic_policy, automatic_policy_path, SKILL_ROOT)
    assert len(created) == 1 and created[0]["reason_code"] == INSUFFICIENT
    assert created[0]["evidence"]["blocking_reasons"][0]["actual"] == 1
    assert auto_contract["metrics"][0]["waiver"]["status"] == "已批准"
    assert auto_contract["sample_capability_policy"]["status"] == "通过"
    assert validate_automatic_waiver_binding(auto_contract, SKILL_ROOT) == []

    structural_contract = copy.deepcopy(contract)
    apply_ordered_distance_policy(structural_contract, load_json(ordered_policy_path), ordered_policy_path)
    apply_score_group_weight_policy(structural_contract, load_json(score_policy_path), score_policy_path)
    affected_metric = structural_contract["metrics"][0]
    affected_instance = metric_instance_id(
        affected_metric["metric_id"],
        affected_metric.get("source_node_ids", []),
        affected_metric.get("instance_dimensions", {}),
    )
    evidence = {
        "schema_version": "slot-alignment.attainability-evidence.v1",
        "task_id": structural_contract["task_id"],
        "status": "结构不可达",
        "budget_expansion_allowed": False,
        "proof": {
            "authorized_space_static_check": True,
            "direction_perturbation": True,
            "independent_and_joint_validation": True,
            "stable_unattainability_evidence": True,
            "sample_qualification_valid": True,
        },
        "affected_metric_instances": [{
            "instance_id": affected_instance,
            "metric_id": affected_metric["metric_id"],
            "scope": affected_metric["scope"],
            "conflict_evidence": "边界扫描证明目标交集为空",
            "minimal_authority_expansion": "扩大demo控制簇授权范围",
        }],
        "evidence_files": [{"path": "attainability-scan.json", "sha256": "a" * 64}],
    }
    evidence_path = root / "attainability-evidence.json"
    dump(evidence_path, evidence)
    structural = apply_structural_unattainability_waivers(
        structural_contract,
        evidence,
        evidence_path,
        automatic_policy,
        automatic_policy_path,
        SKILL_ROOT,
    )
    assert len(structural) == 1 and structural[0]["reason_code"] == UNATTAINABLE
    assert validate_automatic_waiver_binding(structural_contract, SKILL_ROOT) == []
    invalid_evidence = copy.deepcopy(evidence)
    invalid_evidence["proof"]["stable_unattainability_evidence"] = False
    try:
        apply_structural_unattainability_waivers(
            copy.deepcopy(contract),
            invalid_evidence,
            evidence_path,
            automatic_policy,
            automatic_policy_path,
            SKILL_ROOT,
        )
        raise AssertionError("缺少结构不可达完整证明时不应自动豁免")
    except ValueError as exc:
        assert "缺少完整" in str(exc)


def assert_distance_error(method, target, candidate, profile, expected):
    try:
        distance(method, target, candidate, profile=profile)
        raise AssertionError(f"{method}未阻塞非法输入")
    except ValueError as exc:
        assert expected in str(exc), str(exc)


def assert_anchor_error(profile, expected):
    try:
        anchors(profile)
        raise AssertionError("非法评分锚点未阻塞")
    except ValueError as exc:
        assert expected in str(exc), str(exc)


def assert_report_display(path):
    def split_cells(line):
        return [cell.replace("\\|", "|").strip() for cell in re.split(r"(?<!\\)\|", line.strip("|"))]

    lines = path.read_text(encoding="utf-8").splitlines()
    assert not any(line.lstrip().startswith(("`{", "`[")) for line in lines)
    index = 0
    while index < len(lines) - 1:
        header, separator = lines[index], lines[index + 1].strip()
        cells = split_cells(separator) if separator.startswith("|") else []
        if header.startswith("|") and cells and all(cell.strip() and set(cell.strip()) <= {"-", ":"} for cell in cells):
            header_cells = split_cells(header)
            assert not {"目标", "目标分布", "映射目标"}.intersection(header_cells)
            columns = len(header_cells)
            index += 2
            while index < len(lines) and lines[index].startswith("|"):
                assert len(split_cells(lines[index])) == columns
                index += 1
            continue
        index += 1


def score_case(base, waiver=False, hard_fail=False):
    contract = {
        "schema_version": "1.0", "task_id": "self-test", "input_hashes": {}, "group_weights": {"experience": 1},
        "metrics": [
            {"metric_id": "core.rtp.total", "name_zh": "总RTP", "owner": "core.general", "kind": "hard", "scope": "base", "target": 0.96, "hard_gate_profile": {"method": "absolute_error", "tolerance": 0.002}},
            {"metric_id": "demo.a", "name_zh": "体验A", "owner": "demo", "kind": "score", "scope": "base", "target": 0.10, "score_group": "experience", "weight": 0.5, "score_profile": {"method": "absolute_error", "anchors": [[0,100],[0.01,85],[0.10,0]]}},
            {"metric_id": "demo.b", "name_zh": "体验B", "owner": "demo", "kind": "score", "scope": "base", "target": 0.20, "score_group": "experience", "weight": 0.5, "score_profile": {"method": "absolute_error", "anchors": [[0,100],[0.01,85],[0.10,0]]}, "waiver": {"status": "已批准" if waiver else "无"}}
        ]
    }
    measurements = {"measurements": [
        {"metric_id": "core.rtp.total", "scope": "base", "status": "有效", "value": 0.95 if hard_fail else 0.959},
        {"metric_id": "demo.a", "scope": "base", "status": "有效", "value": 0.103},
        {"metric_id": "demo.b", "scope": "base", "status": "有效", "value": 0.204}
    ]}
    dump(base / "contract.json", contract)
    dump(base / "measurements.json", measurements)
    run(ROOT / "score_alignment.py", "--contract", base / "contract.json", "--measurements", base / "measurements.json", "--output", base / "scorecard.json")
    return json.loads((base / "scorecard.json").read_text(encoding="utf-8"))


def score_budget_case(base):
    contract = {
        "schema_version": "1.2",
        "task_id": "budget-test",
        "input_hashes": {},
        "group_weights": {"feature_experience": 1},
        "metrics": [
            {"metric_id": "demo.a", "name_zh": "体验A", "owner": "demo", "kind": "score", "scope": "base", "target": 0.10, "score_group": "feature_experience", "score_budget_key": "demo.a", "scope_aggregation": "weighted_mean", "scope_weight": 0.6, "weight": 1.0, "score_profile": {"method": "absolute_error", "anchors": [[0, 100], [0.01, 85], [0.10, 0]]}},
            {"metric_id": "demo.a", "name_zh": "体验A", "owner": "demo", "kind": "score", "scope": "feature", "target": 0.10, "score_group": "feature_experience", "score_budget_key": "demo.a", "scope_aggregation": "weighted_mean", "scope_weight": 0.4, "weight": 1.0, "score_profile": {"method": "absolute_error", "anchors": [[0, 100], [0.01, 85], [0.10, 0]]}},
            {"metric_id": "demo.b", "name_zh": "体验B", "owner": "demo", "kind": "score", "scope": "base", "target": 0.20, "score_group": "feature_experience", "score_budget_key": "demo.b", "scope_aggregation": "weighted_mean", "scope_weight": 1.0, "weight": 1.0, "score_profile": {"method": "absolute_error", "anchors": [[0, 100], [0.01, 85], [0.10, 0]]}},
        ],
    }
    measurements = {"measurements": [
        {"metric_id": "demo.a", "scope": "base", "status": "有效", "value": 0.10},
        {"metric_id": "demo.a", "scope": "feature", "status": "有效", "value": 0.10},
        {"metric_id": "demo.b", "scope": "base", "status": "有效", "value": 0.21},
    ]}
    dump(base / "contract.json", contract)
    seal_modern_policies(base / "contract.json")
    dump(base / "measurements.json", measurements)
    run(ROOT / "score_alignment.py", "--contract", base / "contract.json", "--measurements", base / "measurements.json", "--output", base / "scorecard.json")
    return json.loads((base / "scorecard.json").read_text(encoding="utf-8"))


def degenerate_support_case(base):
    contract = {
        "schema_version": "1.2",
        "task_id": "degenerate-support-test",
        "input_hashes": {},
        "group_weights": {"feature_experience": 1},
        "metrics": [
            {"metric_id": "demo.active", "name_zh": "有效体验", "kind": "score", "scope": "base", "target": 0.1, "score_group": "feature_experience", "score_budget_key": "demo.active", "scope_aggregation": "weighted_mean", "scope_weight": 1, "weight": 1, "score_profile": {"method": "absolute_error", "anchors": [[0, 100], [1, 0]]}},
            {"metric_id": "demo.degenerate", "name_zh": "退化分布", "kind": "score", "scope": "base", "status": "不适用", "inapplicability_reason_code": "degenerate_reachable_support", "target": [1.0], "score_group": "feature_experience", "score_budget_key": "demo.degenerate", "scope_aggregation": "weighted_mean", "weight": 1, "score_profile": {"method": "total_variation", "reachable_support_source": "task_contract", "reachable_support_status": "all_degenerate", "anchors": [[0, 100], [1, 0]]}},
        ],
    }
    measurements = {"measurements": [{"metric_id": "demo.active", "scope": "base", "status": "有效", "value": 0.1}]}
    dump(base / "contract.json", contract)
    seal_modern_policies(base / "contract.json")
    contract = load_json(base / "contract.json")
    dump(base / "measurements.json", measurements)
    run(ROOT / "score_alignment.py", "--contract", base / "contract.json", "--measurements", base / "measurements.json", "--output", base / "scorecard.json")
    result = json.loads((base / "scorecard.json").read_text(encoding="utf-8"))
    assert not result["blocking_reasons"]
    assert {item["score_budget_key"] for item in result["budget_scores"]} == {"demo.active"}
    tampered = json.loads(json.dumps(contract))
    tampered["metrics"][1].pop("status")
    dump(base / "tampered-contract.json", tampered)
    failed = run_result(ROOT / "score_alignment.py", "--contract", base / "tampered-contract.json", "--measurements", base / "measurements.json", "--output", base / "tampered-scorecard.json")
    failed_scorecard = json.loads((base / "tampered-scorecard.json").read_text(encoding="utf-8"))
    assert failed.returncode == 2 and any("必须标记不适用" in item["reason"] for item in failed_scorecard["blocking_reasons"])


def rerun_budget_case(base, mutate):
    source = base / "source"
    score_budget_case(source)
    contract = json.loads((source / "contract.json").read_text(encoding="utf-8"))
    measurements = json.loads((source / "measurements.json").read_text(encoding="utf-8"))
    mutate(contract)
    dump(base / "contract.json", contract)
    dump(base / "measurements.json", measurements)
    completed = run_result(
        ROOT / "score_alignment.py",
        "--contract", base / "contract.json",
        "--measurements", base / "measurements.json",
        "--output", base / "scorecard.json",
    )
    return completed, json.loads((base / "scorecard.json").read_text(encoding="utf-8"))


def audit_gate_case(base):
    contract = {
        "schema_version": "1.2",
        "task_id": "audit-gate-test",
        "input_hashes": {},
        "group_weights": {"feature_experience": 1},
        "metrics": [
            {"metric_id": "demo.score", "name_zh": "体验", "kind": "score", "scope": "base", "target": 0.1, "score_group": "feature_experience", "score_budget_key": "demo.score", "scope_aggregation": "weighted_mean", "scope_weight": 1, "weight": 1, "score_profile": {"method": "absolute_error", "anchors": [[0, 100], [1, 0]]}},
            {"metric_id": "demo.rule.audit", "name_zh": "规则一致性", "kind": "audit", "scope": "base", "target": {"cap": 5000, "rule_status": "符合"}, "audit_profile": {"method": "field_consistency_gate", "blocking_on_missing": True, "blocking_on_mismatch": True, "required_result_status": "符合", "exact_match_fields": ["cap"]}},
        ],
    }
    score_measurement = {"metric_id": "demo.score", "scope": "base", "status": "有效", "value": 0.1}

    def execute(name, audit_measurement=None, profile_update=None):
        case = base / name
        current = json.loads(json.dumps(contract))
        if profile_update:
            current["metrics"][1]["audit_profile"].update(profile_update)
        measurements = [score_measurement]
        if audit_measurement:
            measurements.append(audit_measurement)
        dump(case / "contract.json", current)
        seal_modern_policies(case / "contract.json")
        dump(case / "measurements.json", {"measurements": measurements})
        process = run_result(ROOT / "score_alignment.py", "--contract", case / "contract.json", "--measurements", case / "measurements.json", "--output", case / "scorecard.json")
        return process, json.loads((case / "scorecard.json").read_text(encoding="utf-8"))

    missing_process, missing = execute("missing")
    mismatch_process, mismatch = execute("mismatch", {"metric_id": "demo.rule.audit", "scope": "base", "status": "不符合", "value": {"cap": 5000, "rule_status": "符合"}})
    contradictory_process, contradictory = execute("contradictory", {"metric_id": "demo.rule.audit", "scope": "base", "status": "符合", "value": {"cap": 5000, "rule_status": "不符合"}})
    wrong_exact_process, wrong_exact = execute("wrong-exact", {"metric_id": "demo.rule.audit", "scope": "base", "status": "符合", "value": {"cap": 4000, "rule_status": "符合"}})
    missing_field_process, missing_field = execute("missing-field", {"metric_id": "demo.rule.audit", "scope": "base", "status": "符合", "value": {}})
    empty_value_process, empty_value = execute(
        "empty-value",
        {"metric_id": "demo.rule.audit", "scope": "base", "status": "有效", "value": None},
        {"method": "low_frequency_statistical_audit", "blocking_on_mismatch": False, "required_result_status": None},
    )
    passed_process, passed = execute("passed", {"metric_id": "demo.rule.audit", "scope": "base", "status": "符合", "value": {"cap": 5000, "rule_status": "符合"}})
    confidence_process, confidence = execute(
        "confidence",
        {"metric_id": "demo.rule.audit", "scope": "base", "status": "置信不足", "value": {"sample_count": 1}},
        {"method": "low_frequency_statistical_audit", "blocking_on_mismatch": False, "required_result_status": None, "insufficient_sample_status": "置信不足", "insufficient_sample_blocks_formal": False},
    )
    assert missing_process.returncode == 2 and any("必需审计测量缺失" in item["reason"] for item in missing["blocking_reasons"])
    assert mismatch_process.returncode == 2 and any("审计结果不符合要求" in item["reason"] for item in mismatch["blocking_reasons"])
    assert contradictory_process.returncode == 2 and any("逐字段一致性门禁不符合" in item["reason"] for item in contradictory["blocking_reasons"])
    assert wrong_exact_process.returncode == 2 and any("cap:期望5000,实际4000" in item["reason"] for item in wrong_exact["blocking_reasons"])
    assert missing_field_process.returncode == 2 and any("逐字段一致性门禁缺少字段" in item["reason"] for item in missing_field["blocking_reasons"])
    assert empty_value_process.returncode == 2 and any("必需审计测量缺失" in item["reason"] for item in empty_value["blocking_reasons"])
    assert passed_process.returncode == 0 and passed["alignment_status"] == "通过" and passed["audits"][0]["status"] == "符合"
    assert confidence_process.returncode == 0 and confidence["alignment_status"] == "通过" and confidence["audits"][0]["status"] == "置信不足"


def catalog_summary_case(base):
    for relative in ("references/玩法画像", "references/指标目录", "assets/schemas", "assets/policies"):
        shutil.copytree(SKILL_ROOT / relative, base / relative)
    (base / "scripts").mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "generate_metric_summary.py", base / "scripts/generate_metric_summary.py")
    generator = base / "scripts/generate_metric_summary.py"
    metrics_index_path = base / "references/指标目录/index.json"
    summary = base / "references/指标目录/指标汇总.md"

    def refresh_metric_hash(catalog_path):
        index = json.loads(metrics_index_path.read_text(encoding="utf-8"))
        relative = catalog_path.relative_to(base / "references/指标目录").as_posix()
        next(item for item in index["packages"] if item["path"] == relative)["sha256"] = sha(catalog_path)
        dump(metrics_index_path, index)

    run(generator, "--skill-root", base)
    valid = run_result(ROOT / "catalog_tool.py", "validate", "--skill-root", base)
    assert valid.returncode == 0, valid.stdout
    index = json.loads(metrics_index_path.read_text(encoding="utf-8"))
    categories = sorted(index["categories"], key=lambda item: item["display_order"])
    source_categories = [source for item in categories for source in item["source_categories"]]
    assert len(source_categories) == len(set(source_categories))
    assert set(source_categories) == METRIC_CATEGORIES
    text = summary.read_text(encoding="utf-8")
    assert "slot-alignment.metric-summary.v8" in text
    assert re.findall(r"^### 4\.\d+ (.+)$", text, re.MULTILINE) == [item["name_zh"] for item in categories]
    assert all(item["description_zh"] in text for item in categories)
    assert text.count("| 指标ID | 中文名 | 类型 | 指标包 |") == len(categories)
    assert "### 2.1 评价方法与评分方案" in text
    assert "同一评分方案只在本节展开一次" in text
    score_section = text.split("### 2.1 评价方法与评分方案", 1)[1].split("### 2.2 顶层评分组固定政策", 1)[0]
    score_rows = [line for line in score_section.splitlines() if re.match(r"^\| S\d{2} \|", line)]
    visible_schemes = [tuple(cell.strip() for cell in line.strip("|").split("|")[1:]) for line in score_rows]
    assert len(visible_schemes) == len(set(visible_schemes))
    assert "公共指标目录只解释目标统计语义、目标结构和来源约束；单游戏实际标量、区间或分布目标保存在任务指标合同及阶段2/3/4报告中，不在公共目录预填。" in text
    assert "## 三、玩法画像目录承接" in text and "玩法画像覆盖矩阵" not in text
    assert "任务实际覆盖率与指标可测率只由阶段2任务指标合同判定" in text
    assert "| 机器分类 | 玩法画像 | 固定承接包 | 条件候选包（仅命中后） | 候选主/守卫目录项 | 候选审计/派生目录项 | 目录引用状态 |" in text
    assert "审计/派生目录项数量不属于Primary/Guard正式数值覆盖" in text and "Jackpot命中率、动态奖值" in text
    for responsibility in ("Primary / Guard", "Audit / 派生", "条件命中", "退化 / 不适用", "可测性与100%"):
        assert responsibility in text
    index_md = (base / "references/指标目录/index.md").read_text(encoding="utf-8")
    assert "packages[].category" in index_md and "真实玩法语义" in index_md
    assert "目录引用完整不等于某个任务已实际覆盖" in index_md and "只以阶段2任务指标合同为准" in index_md
    for package_row in (
        "| modifier | atomic | `atomic.collect`", "| award | atomic | `atomic.value-symbol`",
        "| award | atomic | `atomic.jackpot`", "| state | atomic | `atomic.persistent-state`",
        "| interaction | interaction | `interaction.cascade-multiplier`",
        "| interaction | interaction | `interaction.multiplier-return`",
    ):
        assert package_row in index_md
    metric_catalogs = [
        (entry, json.loads((base / "references/指标目录" / entry["path"]).read_text(encoding="utf-8")))
        for entry in index["packages"]
    ]
    assert all(entry["category"] == catalog["category"] for entry, catalog in metric_catalogs)
    metrics = [metric for _, catalog in metric_catalogs for metric in catalog["metrics"]]
    if any(metric.get("display", {}).get("item_labels") for metric in metrics):
        assert "分布项标签：" in text and "| 序号 | 业务标签 |" in text
    if any(metric.get("display", {}).get("object_labels") or metric.get("display", {}).get("object_units") for metric in metrics):
        assert "对象字段展示：" in text and "| 机器字段 | 业务标签 | 业务单位 |" in text
    audit_labels = {
        "blocking_on_mismatch": "结果不一致是否阻塞",
        "required_result_status": "要求规则核对状态",
        "exact_match_fields": "精确比对字段",
        "insufficient_sample_status": "样本不足状态",
        "insufficient_sample_blocks_formal": "样本不足是否阻塞FORMAL",
    }
    for field, label in audit_labels.items():
        if any(field in metric.get("audit_profile", {}) for metric in metrics):
            assert label in text
    if any(metric.get("audit_profile", {}).get("method") == "field_consistency_gate" for metric in metrics):
        assert "逐字段一致性门禁" in text
    catalog_ids = {metric["metric_id"] for metric in metrics}
    summary_ids = re.findall(r"^##### `([^`]+)`｜", text, re.MULTILINE)
    assert len(summary_ids) == len(set(summary_ids)) == len(catalog_ids)
    assert set(summary_ids) == catalog_ids
    package_ids = {entry["package_id"] for entry, _ in metric_catalogs}
    summary_package_ids = set(re.findall(r"^#### 4\.\d+\.\d+ `([^`]+)`$", text, re.MULTILINE))
    assert summary_package_ids == package_ids
    metric_sections = re.findall(r"(^##### `[^`]+`｜.*?)(?=^##### `|^#### 4\.|^## 五、)", text, re.MULTILINE | re.DOTALL)
    assert len(metric_sections) == len(summary_ids)
    required_labels = (
        "指标说明", "使用场景", "目标值统计", "业务单位", "匹配画像", "精确匹配条件",
        "样本与作用域", "统计与归一化", "评价方式", "语义归属", "派生与防重复", "适用与缺失边界",
    )
    for section in metric_sections:
        assert all(label in section for label in required_labels)
        assert section.count("| 阅读项 | 内容 |") == 1
        assert not re.search(r'^\s*[\{\[]\s*"', section, re.MULTILINE)
        assert '"metric_id":' not in section

    original_index_text = metrics_index_path.read_text(encoding="utf-8")
    duplicate_index_text = original_index_text.replace(
        '"version": "2.6.0",',
        '"version": "2.5.9",\n  "version": "2.6.0",',
        1,
    )
    metrics_index_path.write_text(duplicate_index_text, encoding="utf-8")
    duplicate_catalog = run_result(ROOT / "catalog_tool.py", "validate", "--skill-root", base)
    duplicate_summary = run_result(generator, "--skill-root", base)
    assert duplicate_catalog.returncode == 1 and "重复键" in duplicate_catalog.stdout
    assert duplicate_summary.returncode == 1 and "重复键" in duplicate_summary.stdout
    metrics_index_path.write_text(original_index_text, encoding="utf-8")
    run(generator, "--skill-root", base)

    wrong_category = json.loads(original_index_text)
    reading_by_source = {
        source: category["category_id"]
        for category in wrong_category["categories"]
        for source in category["source_categories"]
    }
    wrong_entry = next(item for item in wrong_category["packages"] if reading_by_source[item["category"]] != item["category"])
    wrong_entry["category"] = reading_by_source[wrong_entry["category"]]
    dump(metrics_index_path, wrong_category)
    category_failed = run_result(ROOT / "catalog_tool.py", "validate", "--skill-root", base)
    assert category_failed.returncode == 1 and "category与索引不一致" in category_failed.stdout
    metrics_index_path.write_text(original_index_text, encoding="utf-8")
    run(generator, "--skill-root", base)

    dynamic = json.loads(original_index_text)
    dynamic["categories"][0]["name_zh"] = "动态分类名称"
    dynamic["categories"][0]["description_zh"] = "动态分类说明"
    dynamic["categories"][0]["display_order"], dynamic["categories"][1]["display_order"] = (
        dynamic["categories"][1]["display_order"], dynamic["categories"][0]["display_order"]
    )
    dump(metrics_index_path, dynamic)
    run(generator, "--skill-root", base)
    dynamic_text = summary.read_text(encoding="utf-8")
    dynamic_categories = sorted(dynamic["categories"], key=lambda item: item["display_order"])
    assert re.findall(r"^### 4\.\d+ (.+)$", dynamic_text, re.MULTILINE) == [item["name_zh"] for item in dynamic_categories]
    assert "动态分类说明" in dynamic_text
    metrics_index_path.write_text(original_index_text, encoding="utf-8")
    run(generator, "--skill-root", base)

    summary.write_text(summary.read_text(encoding="utf-8") + "\n已过期\n", encoding="utf-8")
    stale = run_result(ROOT / "catalog_tool.py", "validate", "--skill-root", base)
    assert stale.returncode == 1 and "指标汇总文档已过期" in stale.stdout
    run(generator, "--skill-root", base)
    regenerated = run_result(ROOT / "catalog_tool.py", "validate", "--skill-root", base)
    assert regenerated.returncode == 0, regenerated.stdout

    first_metric_md = (base / "references/指标目录" / index["packages"][0]["path"]).with_name("catalog.md")
    original_metric_md = first_metric_md.read_text(encoding="utf-8")
    first_metric_md.write_text(re.sub(r"^版本：[^\s]+$", "版本：0.0.0", original_metric_md, count=1, flags=re.MULTILINE), encoding="utf-8")
    md_version_failed = run_result(ROOT / "catalog_tool.py", "validate", "--skill-root", base)
    assert md_version_failed.returncode == 1 and "指标中文目录版本与JSON不一致" in md_version_failed.stdout
    first_metric_md.write_text(original_metric_md, encoding="utf-8")

    metric_schema_path = base / "assets/schemas/metric-catalog.schema.json"
    original_schema_text = metric_schema_path.read_text(encoding="utf-8")
    schema = json.loads(original_schema_text)
    schema["description"] = "Schema指纹变化自测"
    dump(metric_schema_path, schema)
    schema_stale = run_result(ROOT / "catalog_tool.py", "validate", "--skill-root", base)
    assert schema_stale.returncode == 1 and "指标汇总文档已过期" in schema_stale.stdout
    metric_schema_path.write_text(original_schema_text, encoding="utf-8")
    run(generator, "--skill-root", base)

    index = json.loads(metrics_index_path.read_text(encoding="utf-8"))
    catalog_path = base / "references/指标目录" / index["packages"][0]["path"]
    original_catalog_text = catalog_path.read_text(encoding="utf-8")
    malformed = json.loads(original_catalog_text)
    malformed["metrics"][0].pop("name_zh")
    dump(catalog_path, malformed)
    refresh_metric_hash(catalog_path)
    schema_failed = run_result(ROOT / "catalog_tool.py", "validate", "--skill-root", base)
    assert schema_failed.returncode == 1
    assert "不符合Schema" in schema_failed.stdout and catalog_path.relative_to(base).as_posix() in schema_failed.stdout and "metrics.0" in schema_failed.stdout
    catalog_path.write_text(original_catalog_text, encoding="utf-8")
    metrics_index_path.write_text(original_index_text, encoding="utf-8")
    run(generator, "--skill-root", base)

    for forbidden_path in ("/mnt/alignment/metric.json", "/srv/alignment/metric.json", r"\\server\share\metric.json"):
        catalog = json.loads(original_catalog_text)
        catalog["metrics"][0]["display"]["description_zh"] = forbidden_path
        dump(catalog_path, catalog)
        refresh_metric_hash(catalog_path)
        run(generator, "--skill-root", base)
        blocked = run_result(ROOT / "catalog_tool.py", "validate", "--skill-root", base)
        assert blocked.returncode == 1 and "指标汇总包含机器绝对路径" in blocked.stdout, (forbidden_path, blocked.stdout)
        catalog_path.write_text(original_catalog_text, encoding="utf-8")
        metrics_index_path.write_text(original_index_text, encoding="utf-8")
    run(generator, "--skill-root", base)
    final_valid = run_result(ROOT / "catalog_tool.py", "validate", "--skill-root", base)
    assert final_valid.returncode == 0, final_valid.stdout


def mainstream_chain_metric_case():
    def catalog(relative):
        return json.loads((SKILL_ROOT / relative).read_text(encoding="utf-8"))

    award_metrics = {
        item["metric_id"]: item
        for item in catalog("references/指标目录/atomic/award-draw/catalog.json")["metrics"]
    }
    assert "award_draw.outcome_distribution_by_draw_index" not in award_metrics
    award_metric = award_metrics["award_draw.outcome_distribution_given_draw_state"]
    assert award_metric["score_profile"]["method"] == "grouped_total_variation"
    assert all(value in award_metric["profile_match"]["required_attributes"] for value in (
        "replacement_rule", "draw_dependency_rule", "guarantee_rule", "draw_state_definition"
    ))
    award_mechanic = catalog("references/玩法画像/feature/award-draw/catalog.json")["mechanics"][0]
    assert all(value in award_mechanic["required_attributes"] for value in (
        "stage_graph", "path_signature_definition", "replacement_rule", "draw_dependency_rule",
        "guarantee_rule", "draw_state_definition", "outcome_return_equivalence",
    ))

    old_position_ids = {
        "persistent_state.position_occupancy_probability",
        "persistent_state.position_transition_distribution",
        "respin.rerolled_position_pattern_given_retained_state_distribution",
        "persistent_state.position_role_share_given_count_transition_distribution",
    }
    persistent_catalog = catalog("references/指标目录/atomic/persistent-state/catalog.json")
    persistent_metrics = {item["metric_id"]: item for item in persistent_catalog["metrics"]}
    assert not old_position_ids.intersection(persistent_metrics)
    persistent_position_metric_ids = {
        "persistent_state.occupied_position_count_distribution",
        "persistent_state.position_share_given_occupied_count_distribution",
        "persistent_state.position_count_transition_distribution",
        "persistent_state.position_role_dependence_residual_given_count_transition",
    }
    assert persistent_position_metric_ids <= set(persistent_metrics)
    residual = persistent_metrics["persistent_state.position_role_dependence_residual_given_count_transition"]
    assert residual["score_profile"]["method"] == "grouped_mean_absolute_error"
    assert "role in removed|added" in residual["measurement"]
    assert "retained不评分" in residual["normalization"]
    assert "残差合计为0" in residual["normalization"]
    assert {
        "hold_spin.initial_occupancy_distribution",
        "hold_spin.occupancy_transition_distribution",
        "hold_spin.terminal_occupied_cell_count_distribution",
    } <= set(persistent_metrics["persistent_state.occupied_position_count_distribution"]["relationships"]["exclusive_with"])

    respin_metrics = {
        item["metric_id"]: item
        for item in catalog("references/指标目录/atomic/respin/catalog.json")["metrics"]
    }
    assert not old_position_ids.intersection(respin_metrics)
    respin_position_ids = {
        "respin.retained_position_count_distribution_by_step",
        "respin.rerolled_position_count_distribution_given_retained_count",
        "respin.rerolled_position_share_given_counts_distribution",
    }
    assert respin_position_ids <= set(respin_metrics)
    assert all(respin_metrics[metric_id]["capability_ids"] == ["feature.respin"] for metric_id in respin_position_ids)
    assert "deterministic_rule_result" in respin_metrics["respin.rerolled_position_count_distribution_given_retained_count"]["inapplicability_reason_codes"]
    assert all(
        "deterministically_derived_from_primary" not in respin_metrics[metric_id].get("inapplicability_reason_codes", [])
        for metric_id in (
            "respin.retained_position_count_distribution_by_step",
            "respin.rerolled_position_share_given_counts_distribution",
        )
    )
    assert respin_metrics["respin.rerolled_position_share_given_counts_distribution"]["score_profile"]["method"] == "grouped_total_variation"
    assert "步骤暴露" in respin_metrics["respin.rerolled_position_share_given_counts_distribution"]["normalization"]
    respin_mechanic = next(
        item for item in catalog("references/玩法画像/feature/respin/catalog.json")["mechanics"]
        if item["mechanic_id"] == "feature.respin"
    )
    assert all(value in respin_mechanic["required_attributes"] for value in (
        "position_domain", "held_position_rule", "rerolled_scope", "step_index_semantics"
    ))
    respin_conditional_packages = {
        item["package_id"]: item["when"]
        for item in respin_mechanic["metric_requirements"]["conditional_packages"]
    }
    assert "atomic.persistent-state" in respin_conditional_packages
    assert "position_set" in respin_conditional_packages["atomic.persistent-state"]

    hold_spin_mechanic = next(
        item for item in catalog("references/玩法画像/feature/respin/catalog.json")["mechanics"]
        if item["mechanic_id"] == "feature.hold-and-spin"
    )
    hold_spin_conditional_packages = {
        item["package_id"]: item["when"]
        for item in hold_spin_mechanic["metric_requirements"]["conditional_packages"]
    }
    assert "position_domain" in hold_spin_mechanic["optional_attributes"]
    assert "atomic.persistent-state" in hold_spin_conditional_packages
    assert "atomic.hold-and-spin" in hold_spin_conditional_packages["atomic.persistent-state"]

    settlement_metrics = {
        item["metric_id"]: item
        for item in catalog("references/指标目录/atomic/settlement-diversity/catalog.json")["metrics"]
    }
    settlement_mechanics = catalog("references/玩法画像/settlement/standard/catalog.json")["mechanics"]
    for mechanic in settlement_mechanics:
        if mechanic["mechanic_id"] == "settlement.effective-ways-capacity":
            continue
        assert "winning_scale_dimension" in mechanic["required_attributes"]
        assert "winning_scale_dimension" not in mechanic["optional_attributes"]
    settlement_scale = settlement_metrics["settlement.scale_given_symbol_distribution"]
    assert "winning_scale_dimension" in settlement_scale["profile_match"]["required_attributes"]
    assert "退化支持" in settlement_scale["applicability_rule"]
    assert "cluster.connected_group_size_given_symbol_distribution" not in settlement_metrics
    cluster = settlement_metrics["cluster.nonwinning_connected_group_size_given_symbol_distribution"]
    assert cluster["semantic_group"] == "cluster_near_miss_structure"
    assert cluster["sample_unit"] == "eligible_board_snapshot×declared_cluster_symbol"
    assert "没有剩余连通块时记0" in cluster["condition_on"]
    assert "取剩余连通块的实际最大格数" in cluster["condition_on"]
    assert cluster["relationships"]["conditional_on_metric"] == ["board.symbol_count_per_board_distribution"]
    assert "避免碎块多的盘面被重复加权" in cluster["display"]["usage_scene_zh"]
    assert "settlement.scale_given_symbol_distribution" in cluster["relationships"]["cross_checks_with"]

    multiplier_mechanic = catalog("references/玩法画像/modifier/multiplier/catalog.json")["mechanics"][0]
    assert "value_domain" in multiplier_mechanic["required_attributes"]
    assert "value_domain" not in multiplier_mechanic["optional_attributes"]
    multiplier_metrics = {
        item["metric_id"]: item
        for item in catalog("references/指标目录/atomic/modifier/catalog.json")["metrics"]
    }
    effective_multiplier = multiplier_metrics["multiplier.effective_value_distribution"]
    assert "value_domain" in effective_multiplier["profile_match"]["required_attributes"]
    assert "退化支持" in effective_multiplier["applicability_rule"]

    cascade_metrics = {
        item["metric_id"]: item
        for item in catalog("references/指标目录/atomic/cascade/catalog.json")["metrics"]
    }
    capacity = cascade_metrics["cascade.effective_capacity_distribution_by_depth"]
    step_return = cascade_metrics["cascade.step_return_distribution_by_depth"]
    refill_partition = cascade_metrics["cascade.refill_partition_count_vector_given_total_distribution"]
    assert "非退化depth" in capacity["normalization"]
    assert "P(D_total>=depth)" in capacity["normalization"]
    assert "P(reached depth)" in step_return["normalization"]
    assert "P(effective_capacity|depth)" in step_return["normalization"]
    assert refill_partition["score_profile"]["method"] == "grouped_total_variation"
    assert "P(reached depth)×P(refill_count|depth)" in refill_partition["normalization"]
    assert "refill_partition_rule" in refill_partition["profile_match"]["required_attributes"]

    collect_metrics = {
        item["metric_id"]: item
        for item in catalog("references/指标目录/atomic/collect/catalog.json")["metrics"]
    }
    category_output = collect_metrics["collect.output_category_given_input_count_distribution"]
    assert category_output["score_profile"]["method"] == "grouped_total_variation"
    assert "output_category_domains_by_output" in category_output["profile_match"]["required_attributes"]

    wild_metrics = {
        item["metric_id"]: item
        for item in catalog("references/指标目录/atomic/wild-effect/catalog.json")["metrics"]
    }
    assisting_count = wild_metrics["wild.assisting_cell_count_given_assistance_distribution"]
    assert assisting_count["score_profile"]["method"] == "grouped_wasserstein_1d"
    assert "assisting_cell_identity_rule" in assisting_count["profile_match"]["required_attributes"]
    assert "盘面Wild总数" in assisting_count["missing_policy"]

    all_metrics = {}
    for path in (SKILL_ROOT / "references/指标目录").glob("**/catalog.json"):
        all_metrics.update({item["metric_id"]: item for item in load_json(path)["metrics"]})
    for metric in all_metrics.values():
        if "deterministically_derived_from_primary" in metric.get("inapplicability_reason_codes", []):
            assert metric["relationships"].get("conditional_derivation_sources"), metric["metric_id"]
        if metric.get("kind") == "score":
            assert not metric["relationships"].get("derived_from"), metric["metric_id"]


def position_semantic_contract_case():
    state = {
        "node_id": "state-pos",
        "mechanic_id": "state.persistent-state",
        "semantic_event_set_ids": ["position-event"],
        "attributes": {
            "state_shape": "position_set",
            "position_domain": ["P1", "P2", "P3"],
            "observation_points": ["before", "after"],
            "position_transition_bindings": [{
                "transition_event": "spin",
                "from_observation_point": "before",
                "to_observation_point": "after",
                "semantic_event_set_id": "position-event",
            }],
        },
    }
    source = ["state-pos"]
    occupancy = {
        "metric_id": "persistent_state.occupied_position_count_distribution",
        "kind": "score",
        "status": "适用",
        "source_node_ids": source,
        "instance_dimensions": {"state_id": "sticky", "observation_point": "before"},
        "target": {"0": 0.1, "1": 0.4, "2": 0.4, "3": 0.1},
        "score_profile": {"method": "wasserstein_1d", "bin_positions": [0, 1, 2, 3]},
    }
    position_share = {
        "metric_id": "persistent_state.position_share_given_occupied_count_distribution",
        "kind": "score",
        "status": "适用",
        "source_node_ids": source,
        "instance_dimensions": {"state_id": "sticky", "observation_point": "before"},
        "target": {
            "count1::P1": 0.5, "count1::P2": 0.3, "count1::P3": 0.2,
            "count2::P1": 0.2, "count2::P2": 0.3, "count2::P3": 0.5,
        },
        "score_profile": {
            "method": "grouped_total_variation", "group_separator": "::",
            "group_weights": {"count1": 0.5, "count2": 0.5},
        },
    }
    transition = {
        "metric_id": "persistent_state.position_count_transition_distribution",
        "kind": "score",
        "status": "适用",
        "source_node_ids": source,
        "instance_dimensions": {"state_id": "sticky", "transition_event": "spin"},
        "target": {
            "current0::0|1": 1.0,
            "current1::0|1": 0.5, "current1::1|0": 0.5,
            "current2::1|1": 1.0,
            "current3::1|0": 1.0,
        },
        "score_profile": {
            "method": "grouped_total_variation", "group_separator": "::",
            "group_weights": {"current0": 0.1, "current1": 0.4, "current2": 0.4, "current3": 0.1},
        },
    }
    residual_groups = (
        "current0|removed0|added1|added",
        "current1|removed0|added1|added",
        "current2|removed1|added1|removed",
        "current3|removed1|added0|removed",
    )
    residual_target = {}
    for group in residual_groups:
        residual_target.update({f"{group}::P1": 0.1, f"{group}::P2": -0.05, f"{group}::P3": -0.05})
    residual = {
        "metric_id": "persistent_state.position_role_dependence_residual_given_count_transition",
        "kind": "score",
        "status": "适用",
        "source_node_ids": source,
        "instance_dimensions": {"state_id": "sticky", "transition_event": "spin"},
        "target": residual_target,
        "score_profile": {
            "method": "grouped_mean_absolute_error", "group_separator": "::",
            "group_weights": dict(zip(residual_groups, (0.125, 0.25, 0.5, 0.125))),
            "residual_baselines_by_group": {
                group: {"P1": 1 / 3, "P2": 1 / 3, "P3": 1 / 3}
                for group in residual_groups
            },
        },
    }
    persistent_items = {metric_instance_key(item): item for item in (occupancy, position_share, transition, residual)}
    for item in persistent_items.values():
        assert validate_persistent_position_contract(item, [state], persistent_items) == [], item["metric_id"]
    bad_transition = json.loads(json.dumps(transition))
    bad_transition["target"]["current2::1|1"] = 0
    bad_transition["target"]["current2::1|2"] = 1
    bad_items = dict(persistent_items)
    bad_items[metric_instance_key(bad_transition)] = bad_transition
    assert any("added≤N-current" in error for error in validate_persistent_position_contract(bad_transition, [state], bad_items))
    bad_residual = json.loads(json.dumps(residual))
    bad_residual["target"][f"{residual_groups[0]}::P1"] = 0.2
    assert any("残差和必须为0" in error for error in validate_persistent_position_contract(bad_residual, [state], persistent_items))
    bad_baseline = json.loads(json.dumps(residual))
    bad_baseline["score_profile"]["residual_baselines_by_group"][residual_groups[0]] = {
        "P1": 0.95, "P2": 0.03, "P3": 0.02,
    }
    assert any("baseline+residual超出[0,1]" in error for error in validate_persistent_position_contract(bad_baseline, [state], persistent_items))

    respin = {
        "node_id": "respin-main",
        "mechanic_id": "feature.respin",
        "semantic_event_set_ids": ["respin-step"],
        "attributes": {
            "position_domain": ["P1", "P2", "P3"],
            "step_index_semantics": "executed_respin_action_index_1_based",
            "rerolled_position_binding": "random_subset_of_unretained_positions",
        },
    }
    respin_source = ["respin-main"]
    dimensions = {"entry_source": "natural", "state": "base"}
    retained_probabilities = {
        "step1": [0.2, 0.4, 0.3, 0.1],
        "step2": [0.1, 0.3, 0.4, 0.2],
    }
    retained_weights = {"step1": 0.6, "step2": 0.4}
    retained_target, retained_positions = {}, {}
    for group, probabilities in retained_probabilities.items():
        retained_positions[group] = {}
        for count, probability in enumerate(probabilities):
            retained_target[f"{group}::{count}"] = probability
            retained_positions[group][str(count)] = count
    retained = {
        "metric_id": "respin.retained_position_count_distribution_by_step",
        "kind": "score",
        "status": "适用", "source_node_ids": respin_source, "instance_dimensions": dimensions,
        "target": retained_target,
        "score_profile": {
            "method": "grouped_wasserstein_1d", "group_separator": "::",
            "group_weights": retained_weights, "bin_positions_by_group": retained_positions,
        },
    }
    rerolled_probabilities = {
        0: [0.1, 0.3, 0.4, 0.2],
        1: [0.2, 0.4, 0.4, 0.0],
        2: [0.4, 0.6, 0.0, 0.0],
        3: [1.0, 0.0, 0.0, 0.0],
    }
    rerolled_target, rerolled_positions, rerolled_weights = {}, {}, {}
    for step_group, retained_distribution in retained_probabilities.items():
        step = int(step_group.removeprefix("step"))
        for retained_count, retained_probability in enumerate(retained_distribution):
            group = f"step{step}|retained{retained_count}"
            rerolled_positions[group] = {}
            rerolled_weights[group] = retained_weights[step_group] * retained_probability
            for count, probability in enumerate(rerolled_probabilities[retained_count]):
                rerolled_target[f"{group}::{count}"] = probability
                rerolled_positions[group][str(count)] = count
    rerolled = {
        "metric_id": "respin.rerolled_position_count_distribution_given_retained_count",
        "kind": "score",
        "status": "适用", "source_node_ids": respin_source, "instance_dimensions": dimensions,
        "target": rerolled_target,
        "score_profile": {
            "method": "grouped_wasserstein_1d", "group_separator": "::",
            "group_weights": rerolled_weights, "bin_positions_by_group": rerolled_positions,
        },
    }
    share_target, share_raw_weights = {}, {}
    for rerolled_group, rerolled_group_weight in rerolled_weights.items():
        step_part, retained_part = rerolled_group.split("|")
        retained_count = int(retained_part.removeprefix("retained"))
        for rerolled_count, probability in enumerate(rerolled_probabilities[retained_count]):
            if probability <= 0 or rerolled_count in {0, 3}:
                continue
            group = f"{step_part}|{retained_part}|rerolled{rerolled_count}"
            share_raw_weights[group] = rerolled_group_weight * probability * rerolled_count
            share_target.update({f"{group}::P1": 0.4, f"{group}::P2": 0.35, f"{group}::P3": 0.25})
    share_total = sum(share_raw_weights.values())
    share = {
        "metric_id": "respin.rerolled_position_share_given_counts_distribution",
        "kind": "score",
        "status": "适用", "source_node_ids": respin_source, "instance_dimensions": dimensions,
        "target": share_target,
        "score_profile": {
            "method": "grouped_total_variation", "group_separator": "::",
            "group_weights": {group: weight / share_total for group, weight in share_raw_weights.items()},
        },
    }
    respin_items = {metric_instance_key(item): item for item in (retained, rerolled, share)}
    for item in respin_items.values():
        assert validate_respin_position_contract(item, [respin], respin_items) == [], item["metric_id"]
    bad_rerolled = json.loads(json.dumps(rerolled))
    bad_rerolled["score_profile"]["group_weights"]["step1|retained0"] += 0.01
    bad_items = dict(respin_items)
    bad_items[metric_instance_key(bad_rerolled)] = bad_rerolled
    assert any("group_weights未由步骤暴露" in error for error in validate_respin_position_contract(bad_rerolled, [respin], bad_items))
    bad_share = json.loads(json.dumps(share))
    first_group = next(iter(bad_share["score_profile"]["group_weights"]))
    bad_share["score_profile"]["group_weights"][first_group] += 0.01
    assert any("上游两层目标" in error for error in validate_respin_position_contract(bad_share, [respin], respin_items))

    state["semantic_event_set_ids"] = ["position-event"]
    respin["semantic_event_set_ids"] = ["respin-step", "position-event"]
    respin["attributes"]["retained_position_state_binding"] = {
        "state_node_id": "state-pos",
        "state_id": "sticky",
        "observation_point": "before",
        "semantic_event_set_id": "position-event",
    }
    respin["attributes"]["rerolled_position_binding"] = "position_domain_minus_retained_set"
    derived_occupancy = json.loads(json.dumps(occupancy))
    derived_occupancy["status"] = "不适用"
    derived_occupancy["target"] = {"0": 0.16, "1": 0.36, "2": 0.34, "3": 0.14}
    assert validate_respin_persistent_derivation(derived_occupancy, [retained], [state, respin]) == []
    derived_occupancy["target"]["1"] = 0.35
    assert any("精确边际化" in error for error in validate_respin_persistent_derivation(derived_occupancy, [retained], [state, respin]))

    complement_share = json.loads(json.dumps(share))
    complement_share["target"] = {}
    complement_share["score_profile"]["group_weights"] = {
        "step1|retained1|rerolled2": 0.5,
        "step1|retained2|rerolled1": 0.5,
        "step2|retained1|rerolled2": 0.5,
        "step2|retained2|rerolled1": 0.5,
    }
    for step in (1, 2):
        for retained_count in (1, 2):
            group = f"step{step}|retained{retained_count}|rerolled{3-retained_count}"
            complement_share["target"].update({f"{group}::{position}": 1 / 3 for position in ("P1", "P2", "P3")})
    derived_share = json.loads(json.dumps(position_share))
    derived_share["status"] = "不适用"
    derived_share["target"] = {
        "count1::P1": 1 / 3, "count1::P2": 1 / 3, "count1::P3": 1 / 3,
        "count2::P1": 1 / 3, "count2::P2": 1 / 3, "count2::P3": 1 / 3,
    }
    derived_share["score_profile"]["group_weights"] = {"count1": 0.36 / 0.70, "count2": 0.34 / 0.70}
    assert validate_respin_persistent_derivation(derived_share, [retained, complement_share], [state, respin]) == []

    state["attributes"]["matched_position_transition_bindings"] = [{
        "transition_event": "spin",
        "from_observation_point": "before",
        "to_observation_point": "after",
        "semantic_event_set_id": "position-event",
        "object_identity_rule": "stable_object_id",
        "pairing_rule": "same_object_id_before_after",
        "complete_bijective_matching": True,
        "birth_or_death_possible": False,
        "reachable_position_pairs": [
            {"pair_id": "P1_P2", "origin_position_id": "P1", "destination_position_id": "P2"},
            {"pair_id": "P1_P3", "origin_position_id": "P1", "destination_position_id": "P3"},
            {"pair_id": "P2_P1", "origin_position_id": "P2", "destination_position_id": "P1"},
            {"pair_id": "P2_P3", "origin_position_id": "P2", "destination_position_id": "P3"},
            {"pair_id": "P3_P1", "origin_position_id": "P3", "destination_position_id": "P1"},
            {"pair_id": "P3_P2", "origin_position_id": "P3", "destination_position_id": "P2"},
        ],
        "all_reachable_pairs_covered": True,
        "rule_evidence_sha256": "b" * 64,
    }]
    assert validate_matched_position_transition_bindings(state) == []
    movement_transition = {
        "metric_id": "persistent_state.position_count_transition_distribution",
        "kind": "score",
        "status": "适用",
        "source_node_ids": source,
        "instance_dimensions": {"state_id": "sticky", "transition_event": "spin"},
        "target": {"current1::1|1": 1.0, "current2::1|1": 1.0},
        "score_profile": {"method": "grouped_total_variation", "group_separator": "::", "group_weights": {"current1": 0.5, "current2": 0.5}},
    }
    pair_residuals = {
        "P1_P2": 0.1, "P1_P3": -0.1,
        "P2_P1": -0.1, "P2_P3": 0.1,
        "P3_P1": 0.1, "P3_P2": -0.1,
    }
    movement_target = {
        f"{group}::{pair_id}": value
        for group in ("current1|removed1|added1", "current2|removed1|added1")
        for pair_id, value in pair_residuals.items()
    }
    movement = {
        "metric_id": "persistent_state.matched_position_pairing_residual_given_count_transition",
        "kind": "score",
        "status": "适用",
        "source_node_ids": source,
        "instance_dimensions": {"state_id": "sticky", "transition_event": "spin"},
        "target": movement_target,
        "score_profile": {
            "method": "grouped_mean_absolute_error",
            "group_separator": "::",
            "normalization_tolerance": 1e-6,
            "group_weight_source": "task_contract",
            "group_weights": {
                "current1|removed1|added1": 0.5,
                "current2|removed1|added1": 0.5,
            },
        },
    }
    movement_position_shares = []
    for observation_point in ("before", "after"):
        active_share = json.loads(json.dumps(position_share))
        active_share["instance_dimensions"] = {
            "state_id": "sticky",
            "observation_point": observation_point,
        }
        movement_position_shares.append(active_share)
    movement_items = {
        metric_instance_key(item): item
        for item in (movement_transition, movement, residual, *movement_position_shares)
    }
    assert validate_matched_position_transition_contract(movement, [state], movement_items) == []
    bad_movement = json.loads(json.dumps(movement))
    first_group = "current1|removed1|added1"
    reordered = {
        f"{first_group}::{pair_id}": pair_residuals[pair_id]
        for pair_id in reversed(list(pair_residuals))
    }
    reordered.update({key: value for key, value in movement_target.items() if not key.startswith(first_group + "::")})
    bad_movement["target"] = reordered
    assert any("Binding顺序" in error for error in validate_matched_position_transition_contract(bad_movement, [state], movement_items))
    bad_residual_sum = json.loads(json.dumps(movement))
    bad_residual_sum["target"][f"{first_group}::P1_P2"] = 0.11
    assert any("行和必须为0" in error or "组总和必须为0" in error for error in validate_matched_position_transition_contract(bad_residual_sum, [state], movement_items))


def conditional_group_weight_binding_case():
    node = {"node_id": "node-1", "semantic_event_set_ids": ["event-set-1"]}
    source = {
        "metric_id": "source.metric",
        "kind": "score",
        "status": "适用",
        "source_node_ids": ["node-1"],
        "instance_dimensions": {},
        "scope": "shared",
        "target": {"低": 0.75, "高": 0.25},
        "target_evidence": {"evidence_sha256": "a" * 64},
    }
    consumer = {
        "metric_id": "consumer.metric",
        "kind": "score",
        "status": "适用",
        "source_node_ids": ["node-1"],
        "instance_dimensions": {},
        "scope": "shared",
        "target": {"低组::A": 0.5, "低组::B": 0.5, "高组::A": 0.5, "高组::B": 0.5},
        "score_profile": {
            "method": "grouped_total_variation",
            "group_separator": "::",
            "group_weights": {"低组": 0.75, "高组": 0.25},
        },
        "conditional_group_weight_binding": {
            "method": "source_metric_factors",
            "source_metric_instances": {
                "parent": {
                    "metric_id": "source.metric",
                    "source_node_ids": ["node-1"],
                    "instance_dimensions": {},
                    "target_evidence_sha256": "a" * 64,
                }
            },
            "group_factor_rules": {
                "低组": [{"source_alias": "parent", "source_field": "target", "source_keys": ["低"], "aggregation": "sum"}],
                "高组": [{"source_alias": "parent", "source_field": "target", "source_keys": ["高"], "aggregation": "sum"}],
            },
            "normalization": "normalize_positive_active_groups",
        },
    }
    items = {metric_instance_key(item): item for item in (source, consumer)}
    assert validate_conditional_group_weight_binding(consumer, items, {"node-1": node}, None, {}) == []
    bad = json.loads(json.dumps(consumer))
    bad["score_profile"]["group_weights"] = {"低组": 0.5, "高组": 0.5}
    assert any("来源指标目标" in error for error in validate_conditional_group_weight_binding(bad, items, {"node-1": node}, None, {}))

    root = Path(tempfile.mkdtemp(prefix="slot-group-weight-"))
    evidence = root / "evidence/groups.json"
    dump(evidence, {"events": [
        {"event_id": "e1", "conditional_group_id": "G1"},
        {"event_id": "e2", "conditional_group_id": "G1"},
        {"event_id": "e3", "conditional_group_id": "G1"},
        {"event_id": "e4", "conditional_group_id": "G2"},
    ]})
    direct = json.loads(json.dumps(consumer))
    direct["score_profile"]["group_weights"] = {"G1": 0.75, "G2": 0.25}
    direct["target"] = {"G1::A": 0.5, "G1::B": 0.5, "G2::A": 0.5, "G2::B": 0.5}
    direct["conditional_group_weight_binding"] = {
        "method": "sealed_original_exposure",
        "source_event_set_id": "group-exposure",
        "source_evidence_path": "evidence/groups.json",
        "source_evidence_sha256": sha(evidence),
        "source_event_count": 4,
        "group_exposure_counts": {"G1": 3, "G2": 1},
        "token_multipliers": {"G1": 1, "G2": 1},
        "normalization": "normalize_positive_active_groups",
    }
    manifest = {"hashes": {"evidence/groups.json": sha(evidence)}}
    assert validate_conditional_group_weight_binding(direct, items, {"node-1": node}, root, manifest) == []
    direct["conditional_group_weight_binding"]["group_exposure_counts"] = {"G1": 2, "G2": 2}
    assert any("逐事件复算一致" in error for error in validate_conditional_group_weight_binding(direct, items, {"node-1": node}, root, manifest))


def hold_spin_capacity_contract_case():
    binding = {
        "derived_metric_id": "hold_spin.actual_capacity_distribution_by_observation",
        "derived_instance_dimensions": {"entry_source": "feature_buy", "capacity_observation_point": "entry"},
        "primary_owner_metric_instance": {
            "metric_id": "variable_grid.reel_height_layout_distribution",
            "source_node_ids": ["variable-grid"],
            "instance_dimensions": {"component": "feature", "state": "entry", "board_phase": "initial"},
        },
        "shared_semantic_event_set_id": "hold-capacity-entry",
        "source_value_to_actual_capacity": {"layout-9": 9, "layout-15": 15},
        "mapping_total_and_deterministic": True,
        "same_observation_event_universe": True,
        "extra_random_or_state_dependency": False,
        "rule_evidence_sha256": "a" * 64,
    }
    hold_spin = {
        "node_id": "hold-spin",
        "mechanic_id": "feature.hold-and-spin",
        "semantic_event_set_ids": ["hold-capacity-entry"],
        "attributes": {
            "entry_sources": ["feature_buy"],
            "entry_source_semantics": {"feature_buy": {"origin": "external", "source_kind": "feature_buy"}},
            "capacity_owner_bindings": [json.loads(json.dumps(binding))],
        },
    }
    variable_grid = {
        "node_id": "variable-grid",
        "mechanic_id": "board.variable-grid",
        "semantic_event_set_ids": ["hold-capacity-entry"],
        "attributes": {"ways_capacity_mode": "none"},
    }
    source = {
        "metric_id": "variable_grid.reel_height_layout_distribution",
        "status": "适用",
        "source_node_ids": ["variable-grid"],
        "instance_dimensions": {"component": "feature", "state": "entry", "board_phase": "initial"},
        "sealed_event_set_id": "hold-capacity-entry",
        "target": {"layout-9": 0.6, "layout-15": 0.4},
        "target_evidence": {"evidence_sha256": "b" * 64},
    }
    capacity = {
        "metric_id": "hold_spin.actual_capacity_distribution_by_observation",
        "kind": "score",
        "status": "不适用",
        "inapplicability_reason_code": "deterministically_derived_from_primary",
        "source_node_ids": ["hold-spin"],
        "instance_dimensions": {"entry_source": "feature_buy", "capacity_observation_point": "entry"},
        "target": {"9格": 0.6, "15格": 0.4},
        "score_profile": {"method": "wasserstein_1d", "bin_positions": [9, 15]},
        "inapplicability_evidence": [{"_claim": {"capacity_owner_binding_sha256": canonical_sha256(binding)}}],
    }
    active = {metric_instance_key(source): source}
    expected_binding = {"semantic_event_set_id": "hold-capacity-entry"}
    assert validate_profile_links([hold_spin, variable_grid]) == []
    assert validate_hold_spin_capacity_ownership(capacity, [hold_spin, variable_grid], active, expected_binding) == []
    duplicate = json.loads(json.dumps(capacity))
    duplicate["status"] = "适用"
    duplicate.pop("inapplicability_reason_code")
    assert any("不得重复评分" in error for error in validate_hold_spin_capacity_ownership(duplicate, [hold_spin, variable_grid], active, expected_binding))
    wrong_target = json.loads(json.dumps(capacity))
    wrong_target["target"] = {"9格": 0.4, "15格": 0.6}
    assert any("精确复算" in error for error in validate_hold_spin_capacity_ownership(wrong_target, [hold_spin, variable_grid], active, expected_binding))


def derivation_projection_case():
    def clone(value):
        return json.loads(json.dumps(value))

    source = {
        "metric_id": "board.symbol_count_per_board_distribution",
        "source_node_ids": ["board-main"],
        "instance_dimensions": {"component": "base", "state": "default"},
        "target": {"0个": 0.5, "3个": 0.3, "4个": 0.2},
    }
    derived = {
        "metric_id": "trigger.symbol_count_distribution",
        "source_node_ids": ["trigger-main"],
        "instance_dimensions": {"component": "base", "state": "default"},
        "target": {"3个": 0.6, "4个": 0.4},
    }
    projection = {
        "projector_id": "exact_board_count_to_trigger_count_v1",
        "source_field_to_target_field": {"0个": None, "3个": "3个", "4个": "4个"},
        "normalization": "condition_on_retained_mass",
    }
    records = [{"_claim": {"projection": projection}}]
    assert validate_declared_derivation_projection(derived, [source], records) == []

    bad_target = clone(derived)
    bad_target["target"] = {"3个": 0.5, "4个": 0.5}
    assert any("逐值精确复算" in error for error in validate_declared_derivation_projection(bad_target, [source], records))

    missing_source = clone(records)
    missing_source[0]["_claim"]["projection"]["source_field_to_target_field"].pop("0个")
    assert any("完整且仅覆盖来源" in error for error in validate_declared_derivation_projection(derived, [source], missing_source))

    extra_source = clone(records)
    extra_source[0]["_claim"]["projection"]["source_field_to_target_field"]["5个"] = "4个"
    assert any("完整且仅覆盖来源" in error for error in validate_declared_derivation_projection(derived, [source], extra_source))

    missing_target = clone(records)
    missing_target[0]["_claim"]["projection"]["source_field_to_target_field"]["4个"] = None
    assert any("覆盖全部且仅覆盖目标" in error for error in validate_declared_derivation_projection(derived, [source], missing_target))

    assert any("精确绑定唯一登记来源集合" in error for error in validate_declared_derivation_projection(derived, [source, clone(source)], records))

    root = Path(tempfile.mkdtemp(prefix="slot-derived-chain-")).resolve()
    manifest = {"hashes": {}}

    def record(name, claim):
        path = root / f"{name}.json"
        dump(path, {"claim": claim})
        relative = path.relative_to(root).as_posix()
        digest = sha(path)
        manifest["hashes"][relative] = digest
        return {
            "evidence_path": relative,
            "evidence_sha256": digest,
            "json_pointer": "/claim",
            "expected_value": claim,
        }

    board = {
        **source,
        "scope": "feature-entry",
        "status": "适用",
        "sealed_event_set_id": "chain-events",
        "target_evidence": {"evidence_sha256": "a" * 64},
    }
    board_ref = {
        "metric_id": board["metric_id"],
        "source_node_ids": board["source_node_ids"],
        "instance_dimensions": board["instance_dimensions"],
    }
    trigger = {
        **derived,
        "scope": "feature-entry",
        "kind": "score",
        "status": "不适用",
        "sealed_event_set_id": "chain-events",
        "inapplicability_reason_code": "deterministically_derived_from_primary",
    }
    trigger_claim = {
        "derivation_rule": "同一盘面精确数量筛选触发成功子集",
        "source_metric_instances": [board_ref],
        "source_target_evidence_sha256": {format_instance(metric_instance_key(board)): "a" * 64},
        "projection": projection,
    }
    trigger["inapplicability_evidence"] = [record("trigger", trigger_claim)]
    trigger_ref = {
        "metric_id": trigger["metric_id"],
        "source_node_ids": trigger["source_node_ids"],
        "instance_dimensions": trigger["instance_dimensions"],
    }
    grant = {
        "metric_id": "free_spin.initial_grant_distribution",
        "source_node_ids": ["free-spin-main"],
        "instance_dimensions": {"component": "base", "state": "default"},
        "scope": "feature-entry",
        "kind": "score",
        "status": "不适用",
        "sealed_event_set_id": "chain-events",
        "target": {"5次": 0.6, "10次": 0.4},
        "inapplicability_reason_code": "deterministically_derived_from_primary",
    }
    grant_claim = {
        "derivation_rule": "触发数量到初始赠送次数的完整确定映射",
        "source_metric_instances": [trigger_ref],
        "source_target_evidence_sha256": {format_instance(metric_instance_key(trigger)): None},
    }
    grant["inapplicability_evidence"] = [record("grant", grant_claim)]
    grant_ref = {
        "metric_id": grant["metric_id"],
        "source_node_ids": grant["source_node_ids"],
        "instance_dimensions": grant["instance_dimensions"],
    }
    duration_projection = {
        "projector_id": "initial_resource_or_draw_chain_to_duration_v1",
        "source_field_to_target_field": {"5次": "5次", "10次": "10次"},
        "normalization": "none",
    }
    duration = {
        "metric_id": "feature_cycle.duration_distribution",
        "source_node_ids": ["free-spin-main"],
        "instance_dimensions": {"component": "base", "state": "default"},
        "scope": "feature-entry",
        "kind": "score",
        "status": "不适用",
        "sealed_event_set_id": "chain-events",
        "target": {"5次": 0.6, "10次": 0.4},
        "inapplicability_reason_code": "deterministically_derived_from_primary",
    }
    duration_claim = {
        "derivation_rule": "初始赠送次数与最终主要动作次数一一对应",
        "source_metric_instances": [grant_ref],
        "source_target_evidence_sha256": {format_instance(metric_instance_key(grant)): None},
        "projection": duration_projection,
    }
    duration["inapplicability_evidence"] = [record("duration", duration_claim)]
    for item in (trigger, grant, duration):
        evidence = item["inapplicability_evidence"][0]
        assert sha(root / evidence["evidence_path"]) == evidence["evidence_sha256"]
    nodes = [
        {"node_id": "board-main", "mechanic_id": "board.fixed-grid", "semantic_event_set_ids": ["chain-events"], "attributes": {}},
        {"node_id": "trigger-main", "mechanic_id": "trigger.scatter-count", "semantic_event_set_ids": ["chain-events"], "attributes": {}},
        {"node_id": "free-spin-main", "mechanic_id": "feature.free-spin", "semantic_event_set_ids": ["chain-events"], "attributes": {}},
    ]
    catalog = catalog_maps(SKILL_ROOT)
    active = {metric_instance_key(board): board}
    facts, results = resolve_derived_facts([trigger, grant, duration], nodes, active, catalog, root, manifest)
    assert all(not errors for errors in results.values()), results
    assert metric_instance_key(duration) in facts


def transform_target_coherence_case():
    node = {
        "node_id": "transform-main",
        "mechanic_id": "modifier.symbol-transform",
        "attributes": {"source_domain": ["A", "B", "C"]},
    }
    item = {
        "metric_id": "transform.target_coherence_residual_given_count",
        "kind": "score",
        "status": "适用",
        "source_node_ids": ["transform-main"],
        "target": {
            "2|A+B::same_target_residual": 0.25,
            "3|B+B::same_target_residual": -0.10,
        },
        "score_profile": {"method": "grouped_mean_absolute_error", "group_separator": "::"},
    }
    assert validate_transform_target_coherence_contract(item, {"transform-main": node}) == []

    reversed_pair = json.loads(json.dumps(item))
    reversed_pair["target"] = {"2|B+A::same_target_residual": 0.25}
    assert any(
        "source_domain顺序规范化" in error
        for error in validate_transform_target_coherence_contract(reversed_pair, {"transform-main": node})
    )

    out_of_range = json.loads(json.dumps(item))
    out_of_range["target"] = {"2|A+B::same_target_residual": 1.01}
    assert any(
        "[-1,1]" in error
        for error in validate_transform_target_coherence_contract(out_of_range, {"transform-main": node})
    )

    ambiguous_node = json.loads(json.dumps(node))
    ambiguous_node["attributes"]["source_domain"] = ["A+B", "C"]
    assert any(
        "保留分隔符" in error
        for error in validate_transform_target_coherence_contract(item, {"transform-main": ambiguous_node})
    )


def mode_and_owner_semantic_contract_case():
    def clone(value):
        return json.loads(json.dumps(value))

    base_mode = normal_mode_contract()
    profile = {"scope": {"mode": "base", "mode_contract": clone(base_mode)}}
    contract = {"scope": {"mode": "base", "mode_contract": clone(base_mode)}}
    assert validate_mode_contract(profile, contract, []) == []
    bad_mode = clone(profile)
    bad_mode["scope"]["mode_contract"]["mixed_sample_forbidden"] = False
    assert any("mixed_sample_forbidden" in error for error in validate_mode_contract(bad_mode, contract, []))

    free_spin = {
        "node_id": "free-spin-main",
        "mechanic_id": "feature.free-spin",
        "attributes": {
            "feature_mode_domain": ["10次免费旋转", "5次免费旋转且初始倍率2x"],
            "selected_feature_mode_id": "10次免费旋转",
            "mode_selection_rule": {
                "selection_type": "player_choice_before_feature",
                "selection_timing": "before_feature_start",
                "evidence_sha256": "b" * 64,
            },
            "player_input_role": "select_math_mode",
        },
    }
    choice_mode = normal_mode_contract()
    choice_mode["feature_mode_selections"] = [{
        "feature_node_id": "free-spin-main",
        "mode_domain": ["10次免费旋转", "5次免费旋转且初始倍率2x"],
        "selected_mode_id": "10次免费旋转",
        "selection_rule": "before_feature_start",
        "player_input_role": "select_math_mode",
        "fixed_for_task": True,
        "evidence_sha256": "b" * 64,
    }]
    choice_profile = {"scope": {"mode": "base", "mode_contract": clone(choice_mode)}}
    choice_contract = {"scope": {"mode": "base", "mode_contract": clone(choice_mode)}}
    assert validate_mode_contract(choice_profile, choice_contract, [free_spin]) == []
    wrong_choice = clone(choice_contract)
    wrong_choice["scope"]["mode_contract"]["feature_mode_selections"][0]["selected_mode_id"] = "5次免费旋转且初始倍率2x"
    assert any("阶段1画像不一致" in error for error in validate_mode_contract(choice_profile, wrong_choice, [free_spin]))

    value_binding = {
        "value_symbol_node_id": "value-symbol-main",
        "multiplier_node_id": "multiplier-value",
        "shared_semantic_event_set_id": "value-multiplier-pair",
        "value_symbol_instance_id_field": "value_symbol_instance_id",
        "multiplier_application_event_id_field": "multiplier_application_event_id",
        "event_pairing_bijective": True,
        "all_assignments_realized_exactly_once": True,
        "same_event_universe": True,
        "no_additional_multiplier_source": True,
        "value_to_effective_multiplier_mapping": {"10": 2, "20": 4},
        "mapping_total_and_bijective": True,
        "primary_owner_metric_id": "value_symbol.assignment_value_distribution",
        "rule_evidence_sha256": "c" * 64,
    }
    value_nodes = [
        {
            "node_id": "value-symbol-main",
            "mechanic_id": "award.value-symbol",
            "semantic_event_set_ids": ["value-multiplier-pair"],
            "attributes": {"value_domain": [10, 20], "linked_multiplier_node_ids": ["multiplier-value"]},
        },
        {
            "node_id": "multiplier-value",
            "mechanic_id": "modifier.win-multiplier",
            "semantic_event_set_ids": ["value-multiplier-pair"],
            "attributes": {"value_domain": [2, 4], "value_symbol_effective_multiplier_binding": clone(value_binding)},
        },
    ]
    assert validate_value_symbol_multiplier_profile_bindings(value_nodes) == []
    bad_value_nodes = clone(value_nodes)
    bad_value_nodes[1]["attributes"]["value_symbol_effective_multiplier_binding"]["value_to_effective_multiplier_mapping"]["20"] = 2
    assert any("完整双射" in error for error in validate_value_symbol_multiplier_profile_bindings(bad_value_nodes))

    upgrade_binding = {
        "persistent_state_id": "value-symbol-state",
        "initial_assignment_semantic_event_set_id": "value-symbol-initial-assignment",
        "shared_semantic_event_set_id": "value-symbol-upgrade",
        "value_symbol_instance_id_field": "value_symbol_instance_id",
        "persistent_state_instance_id_field": "state_instance_id",
        "upgrade_check_event_id_field": "upgrade_check_event_id",
        "state_observation_point": "before_each_eligible_upgrade_check",
        "state_transition_event": "upgrade",
        "same_instance_bijective": True,
        "initial_assignment_maps_to_state_initial_value": True,
        "each_eligible_upgrade_check_maps_to_one_transition_opportunity": True,
        "no_upgrade_outcome_maps_to_self_transition": True,
        "initial_assignment_excluded_from_upgrade_observation": True,
        "value_domain_equal": True,
        "rule_evidence_sha256": "d" * 64,
    }
    upgrade_nodes = [
        {
            "node_id": "upgradable-value-symbol",
            "mechanic_id": "award.value-symbol",
            "semantic_event_set_ids": ["value-symbol-initial-assignment", "value-symbol-upgrade"],
            "attributes": {
                "value_domain": [1, 2, 5, 10],
                "value_upgrade_rule": "same_instance_value_increases_on_upgrade_event",
                "value_upgrade_state_binding": clone(upgrade_binding),
            },
        },
        {
            "node_id": "value-symbol-state-node",
            "mechanic_id": "state.persistent-state",
            "semantic_event_set_ids": ["value-symbol-upgrade"],
            "attributes": {
                "state_id": "value-symbol-state",
                "state_shape": "ordered_scalar",
                "value_domain": [1, 2, 5, 10],
                "ordered_axis_semantics": "nonnegative_multiplicative",
                "observation_points": ["before_each_eligible_upgrade_check"],
                "transition_event_domain": ["upgrade"],
            },
        },
    ]
    assert validate_profile_links(upgrade_nodes) == []
    bad_upgrade_nodes = clone(upgrade_nodes)
    bad_upgrade_nodes[1]["attributes"]["value_domain"] = [1, 2, 5]
    assert any("值域必须与奖值域完全一致" in error for error in validate_profile_links(bad_upgrade_nodes))
    missing_upgrade_binding = clone(upgrade_nodes)
    missing_upgrade_binding[0]["attributes"].pop("value_upgrade_state_binding")
    assert any("存在升级规则但缺少" in error for error in validate_profile_links(missing_upgrade_binding))
    missing_self_transition = clone(upgrade_nodes)
    missing_self_transition[0]["attributes"]["value_upgrade_state_binding"]["no_upgrade_outcome_maps_to_self_transition"] = False
    assert any("未升级自环" in error for error in validate_profile_links(missing_self_transition))

    def catalog_metric(relative, metric_id):
        data = load_json(SKILL_ROOT / relative)
        return clone(next(item for item in data["metrics"] if item["metric_id"] == metric_id))

    value_source = catalog_metric("references/指标目录/atomic/value-symbol/catalog.json", "value_symbol.assignment_value_distribution")
    value_source.update({"source_node_ids": ["value-symbol-main"], "target": {"10x": 0.75, "20x": 0.25}})
    value_source["score_profile"]["bin_positions"] = [10, 20]
    multiplier_derived = catalog_metric("references/指标目录/atomic/modifier/catalog.json", "multiplier.effective_value_distribution")
    multiplier_derived.update({
        "source_node_ids": ["multiplier-value"],
        "status": "不适用",
        "inapplicability_reason_code": "deterministically_derived_from_primary",
        "owner_derivation_binding": clone(value_binding),
        "target": {"2x": 0.75, "4x": 0.25},
    })
    multiplier_derived["score_profile"]["bin_positions"] = [2, 4]
    assert validate_value_symbol_multiplier_derivation(multiplier_derived, [value_source], value_nodes) == []
    assert validate_value_symbol_multiplier_ownership(multiplier_derived, value_nodes) == []
    active_non_owner = clone(multiplier_derived)
    active_non_owner["status"] = "适用"
    active_non_owner.pop("inapplicability_reason_code")
    assert any("非Owner项必须确定性派生" in error for error in validate_value_symbol_multiplier_ownership(active_non_owner, value_nodes))
    wrong_multiplier_target = clone(multiplier_derived)
    wrong_multiplier_target["target"] = {"2x": 0.25, "4x": 0.75}
    assert any("精确复算" in error for error in validate_value_symbol_multiplier_derivation(wrong_multiplier_target, [value_source], value_nodes))

    cascade_binding = {
        "cascade_node_id": "cascade-main",
        "multiplier_node_id": "multiplier-cascade",
        "shared_semantic_event_set_id": "cascade-multiplier-steps",
        "terminal_depth_semantics": "completed_cascade_settlement_count_0_based",
        "settlement_step_index_semantics": "initial_settlement_0_then_cascade_step_1_based",
        "terminal_depth_to_step_states": {
            "0": [
                {"settlement_step_index": 0, "multiplier_state_id": "未出现", "multiplier_occurred": False, "multiplier_applied": False, "effective_multiplier": None},
            ],
            "1": [
                {"settlement_step_index": 0, "multiplier_state_id": "未出现", "multiplier_occurred": False, "multiplier_applied": False, "effective_multiplier": None},
                {"settlement_step_index": 1, "multiplier_state_id": "2x", "multiplier_occurred": True, "multiplier_applied": True, "effective_multiplier": 2},
            ],
            "2": [
                {"settlement_step_index": 0, "multiplier_state_id": "未出现", "multiplier_occurred": False, "multiplier_applied": False, "effective_multiplier": None},
                {"settlement_step_index": 1, "multiplier_state_id": "2x", "multiplier_occurred": True, "multiplier_applied": True, "effective_multiplier": 2},
                {"settlement_step_index": 2, "multiplier_state_id": "3x", "multiplier_occurred": True, "multiplier_applied": True, "effective_multiplier": 3},
            ],
        },
        "all_reachable_depths_covered": True,
        "mapping_total_and_deterministic": True,
        "extra_random_or_state_dependency": False,
        "rule_evidence_sha256": "d" * 64,
    }
    cascade_nodes = [
        {"node_id": "cascade-main", "mechanic_id": "evolution.cascade", "semantic_event_set_ids": ["cascade-multiplier-steps"], "attributes": {}},
        {
            "node_id": "multiplier-cascade",
            "mechanic_id": "modifier.win-multiplier",
            "semantic_event_set_ids": ["cascade-multiplier-steps"],
            "attributes": {
                "progression_driver": "cascade_depth",
                "same_depth_multiplier_randomness": False,
                "cascade_node_id": "cascade-main",
                "value_domain": [2, 3],
                "cascade_depth_multiplier_binding": clone(cascade_binding),
            },
        },
    ]
    assert validate_cascade_multiplier_profile_bindings(cascade_nodes) == []
    inconsistent_cascade = clone(cascade_nodes)
    inconsistent_state = inconsistent_cascade[1]["attributes"]["cascade_depth_multiplier_binding"]["terminal_depth_to_step_states"]["2"][1]
    inconsistent_state.update({"multiplier_state_id": "3x", "effective_multiplier": 3})
    assert any("同一实际结算步骤" in error for error in validate_cascade_multiplier_profile_bindings(inconsistent_cascade))

    depth_source = catalog_metric("references/指标目录/atomic/cascade/catalog.json", "cascade.depth_distribution")
    depth_source.update({"source_node_ids": ["cascade-main"], "target": {"0次": 0.5, "1次": 0.3, "2次": 0.2}})
    depth_source["score_profile"]["bin_positions"] = [0, 1, 2]
    occurrence = catalog_metric("references/指标目录/atomic/modifier/catalog.json", "multiplier.occurrence_rate")
    occurrence.update({"source_node_ids": ["cascade-main", "multiplier-cascade"], "cascade_derivation_binding": clone(cascade_binding), "target": 7 / 17})
    application = catalog_metric("references/指标目录/atomic/modifier/catalog.json", "multiplier.application_rate_given_occurrence")
    application.update({"source_node_ids": ["cascade-main", "multiplier-cascade"], "cascade_derivation_binding": clone(cascade_binding), "target": 1.0})
    effective = catalog_metric("references/指标目录/atomic/modifier/catalog.json", "multiplier.effective_value_distribution")
    effective.update({
        "source_node_ids": ["cascade-main", "multiplier-cascade"],
        "cascade_derivation_binding": clone(cascade_binding),
        "target": {"2x": 5 / 7, "3x": 2 / 7},
    })
    effective["score_profile"]["bin_positions"] = [2, 3]
    dependence = catalog_metric("references/指标目录/interaction/cascade-multiplier/catalog.json", "cascade_multiplier.dependence_by_depth")
    dependence.update({
        "source_node_ids": ["cascade-main", "multiplier-cascade"],
        "cascade_derivation_binding": clone(cascade_binding),
        "target": {
            "0::未出现": 7 / 17, "0::2x": -5 / 17, "0::3x": -2 / 17,
            "1::未出现": -10 / 17, "1::2x": 12 / 17, "1::3x": -2 / 17,
            "2::未出现": -10 / 17, "2::2x": -5 / 17, "2::3x": 15 / 17,
        },
    })
    dependence["score_profile"]["group_weights"] = {"0": 10 / 17, "1": 5 / 17, "2": 2 / 17}
    for item in (occurrence, application, effective, dependence):
        assert validate_cascade_multiplier_derivation(item, [depth_source], cascade_nodes) == [], item["metric_id"]
    wrong_occurrence = clone(occurrence)
    wrong_occurrence["target"] = 0.5
    assert any("倍率出现率" in error for error in validate_cascade_multiplier_derivation(wrong_occurrence, [depth_source], cascade_nodes))


def catalog_semantic_contract_case():
    def metrics(relative):
        catalog = json.loads((SKILL_ROOT / relative).read_text(encoding="utf-8"))
        return {item["metric_id"]: item for item in catalog["metrics"]}

    jackpot = metrics("references/指标目录/atomic/jackpot/catalog.json")
    rule_audit = jackpot["jackpot.rule_consistency.audit"]
    rule_profile = rule_audit["audit_profile"]
    assert rule_profile == {
        "method": "field_consistency_gate",
        "blocking_on_missing": True,
        "blocking_on_mismatch": True,
        "required_result_status": "符合",
    }
    assert all(text in rule_audit["missing_policy"] for text in ("机会定义与分母", "奖值来源或固定值", "重置规则", "不一致时阻塞FORMAL"))
    rule_fields = {
        "tier_domain_status",
        "trigger_rule_status",
        "tier_resolution_rule_status",
        "opportunity_definition_and_denominator_status",
        "value_model_and_source_or_fixed_value_status",
        "payout_scope_status",
        "reset_rule_status",
        "external_pool_contract_status",
        "award_cap_rule_status",
    }
    assert rule_fields == set(rule_audit["display"]["object_labels"])
    assert rule_fields == set(rule_audit["display"]["object_units"])
    assert set(rule_audit["display"]["object_units"].values()) == {"状态（符合/不符合/无法证明/有证据不适用）"}
    for metric_id in ("jackpot.hit_rate_by_tier", "jackpot.award_value_distribution_by_tier"):
        metric = jackpot[metric_id]
        profile = metric["audit_profile"]
        assert profile["blocking_on_missing"] is True
        assert profile["insufficient_sample_status"] == "置信不足"
        assert profile["insufficient_sample_blocks_formal"] is False
        assert all(text in metric["missing_policy"] for text in ("阻塞FORMAL", "置信不足", "不作为资料缺失", "不阻塞FORMAL"))
    assert "机会分母" in jackpot["jackpot.hit_rate_by_tier"]["missing_policy"]
    assert "奖值来源" in jackpot["jackpot.award_value_distribution_by_tier"]["missing_policy"]
    assert all("正式数值覆盖" in jackpot[metric_id]["display"]["usage_scene_zh"] for metric_id in (
        "jackpot.hit_rate_by_tier", "jackpot.award_value_distribution_by_tier"
    ))

    metric_schema = json.loads((SKILL_ROOT / "assets/schemas/metric-catalog.schema.json").read_text(encoding="utf-8"))
    audit_profile_schema = metric_schema["$defs"]["audit_profile"]
    assert {
        "blocking_on_mismatch",
        "required_result_status",
        "exact_match_fields",
        "insufficient_sample_status",
        "insufficient_sample_blocks_formal",
    } <= set(audit_profile_schema["properties"])
    assert len(audit_profile_schema["allOf"]) >= 2

    core = metrics("references/指标目录/core/general/catalog.json")
    natural = core["core.feature.natural_trigger_rate"]
    assert "count(distinct eligible_paid_entry_id" in natural["measurement"]
    assert "at least one endogenous game-rule entry" in natural["measurement"]
    assert "全部合格付费入口" in natural["condition_on"]
    assert "同一入口" in natural["normalization"] and "进入多次仍只计1" in natural["normalization"]
    assert "唯一付费入口" in natural["missing_policy"]

    long_tail = core["core.long_tail.audit"]
    assert "eligible_paid_entry_count" in long_tail["measurement"]
    assert "全部合格付费入口" in long_tail["condition_on"]
    assert "贡献0" in long_tail["condition_on"]
    assert "全部合格付费入口" in long_tail["normalization"]
    assert "P(return>=200x)" in long_tail["normalization"]
    assert "不在长尾内部重新归一" in long_tail["normalization"]

    max_win = core["core.max_win.audit"]
    assert max_win["unit"] == "status_object"
    assert max_win["audit_profile"] == {
        "method": "field_consistency_gate",
        "blocking_on_missing": True,
        "blocking_on_mismatch": True,
        "required_result_status": "符合",
        "exact_match_fields": ["theoretical_max", "cap"],
    }
    assert all(text in max_win["missing_policy"] for text in ("无法证明", "不一致", "阻塞FORMAL"))
    assert "复合审计" in max_win["display"]["display_unit"]

    duration = metrics("references/指标目录/composite/feature-cycle/catalog.json")["feature_cycle.duration_distribution"]
    expected_cross_checks = {
        "free_spin.initial_grant_distribution",
        "free_spin.retrigger_grant_distribution",
        "respin.initial_grant_distribution",
        "respin.extension_grant_distribution",
        "hold_spin.initial_occupancy_distribution",
        "hold_spin.current_occupancy_distribution",
        "hold_spin.occupancy_transition_distribution",
        "award_draw.outcome_distribution_given_draw_state",
    }
    assert duration["default_weight"] == 0.5
    assert expected_cross_checks <= set(duration["relationships"]["cross_checks_with"])
    assert duration["relationships"]["derived_from"] == []
    assert all(text in duration["relationships"]["overlap_reason_zh"] for text in ("结构化布尔合同", "逐次重触发或延长赠送数量的边际分布不能恢复完整周期总次数", "0.5权重"))

    feature_return = metrics("references/指标目录/composite/feature-cycle/catalog.json")["feature_cycle.return_distribution"]
    assert feature_return["audit_profile"] == {"method": "deterministic_derivation", "blocking_on_missing": False}
    assert "由上游主指标阻塞FORMAL" in feature_return["missing_policy"] and "不要求独立测量" in feature_return["missing_policy"]

    variable_capacity = metrics("references/指标目录/atomic/variable-grid/catalog.json")["variable_grid.capacity_distribution"]
    assert variable_capacity["audit_profile"] == {"method": "deterministic_derivation", "blocking_on_missing": False}
    assert "由上游主指标阻塞FORMAL" in variable_capacity["missing_policy"] and "不要求独立测量" in variable_capacity["missing_policy"]
    assert "非确定性续命" in duration["display"]["description_zh"]

    from report_common import LEGACY_METRIC_DISPLAY_DEFAULTS
    assert "主要动作" in LEGACY_METRIC_DISPLAY_DEFAULTS["feature_cycle.duration_distribution"]["target_meaning_zh"]
    assert "全部合格付费入口" in LEGACY_METRIC_DISPLAY_DEFAULTS["core.long_tail.audit"]["target_meaning_zh"]

    jackpot_text = (SKILL_ROOT / "references/指标目录/atomic/jackpot/catalog.md").read_text(encoding="utf-8")
    prize_text = (SKILL_ROOT / "references/玩法画像/award/prize/catalog.md").read_text(encoding="utf-8")
    core_text = (SKILL_ROOT / "references/指标目录/core/general/catalog.md").read_text(encoding="utf-8")
    duration_text = (SKILL_ROOT / "references/指标目录/composite/feature-cycle/catalog.md").read_text(encoding="utf-8")
    profile_text = (SKILL_ROOT / "references/01-资料确认与玩法画像.md").read_text(encoding="utf-8")
    matching_text = (SKILL_ROOT / "references/02-指标匹配.md").read_text(encoding="utf-8")
    index_text = (SKILL_ROOT / "references/指标目录/index.md").read_text(encoding="utf-8")
    assert all(text in jackpot_text for text in ("规则一致性门禁", "资料缺失", "置信不足", "正式数值覆盖"))
    assert all(text in prize_text for text in ("机会定义与分母", "奖值来源或固定值", "重置规则", "置信不足", "正式数值覆盖"))
    assert "core.multiplier_distribution.lt200" not in core_text
    assert all(text in core_text for text in ("付费入口", "P(return>=200x)"))
    assert all(text in duration_text for text in ("最终动作数", "0.5"))
    assert "付费入口二元归并" in profile_text
    assert all(text in matching_text for text in ("P(return>=200x)", "端到端复合约束", "0.5", "jackpot.rule_consistency.audit", "正式评分"))
    assert all(text in index_text for text in ("Jackpot命中率", "Primary/Guard正式数值覆盖"))

    catalog = catalog_maps(SKILL_ROOT)
    owner_errors = []
    validate_owner_direction_contracts(catalog["metrics"], owner_errors)
    assert owner_errors == []
    bad_owner_map = json.loads(json.dumps(catalog["metrics"]))
    bad_owner_map["hold_spin.initial_occupancy_distribution"]["inapplicability_reason_codes"].append("semantic_owner_exclusive")
    bad_owner_errors = []
    validate_owner_direction_contracts(bad_owner_map, bad_owner_errors)
    assert any("不得反向让位" in error for error in bad_owner_errors)

    movement_owner_errors = []
    validate_matched_position_joint_contract(catalog["metrics"], movement_owner_errors)
    assert movement_owner_errors == []
    bad_movement_owner_map = json.loads(json.dumps(catalog["metrics"]))
    bad_movement_owner_map["persistent_state.matched_position_pairing_residual_given_count_transition"]["score_profile"]["method"] = "grouped_total_variation"
    bad_movement_owner_errors = []
    validate_matched_position_joint_contract(bad_movement_owner_map, bad_movement_owner_errors)
    assert any("grouped_mean_absolute_error" in error for error in bad_movement_owner_errors)

    degeneracy_errors = []
    validate_grouped_distribution_degeneracy(catalog["metrics"], degeneracy_errors)
    assert degeneracy_errors == []
    bad_degeneracy_map = json.loads(json.dumps(catalog["metrics"]))
    bad_degeneracy_map["persistent_state.ordered_transition_distribution"]["applicability_rule"] = "存在状态转移时评分。"
    bad_degeneracy_errors = []
    validate_grouped_distribution_degeneracy(bad_degeneracy_map, bad_degeneracy_errors)
    assert any("局部移除" in error for error in bad_degeneracy_errors)


def step_return_owner_partition_case(base):
    clone = copy.deepcopy
    dimensions = {"component": "base", "state": "normal"}
    active_nodes = [
        {"node_id": "cascade-main", "mechanic_id": "evolution.cascade"},
        {"node_id": "variable-grid-main", "mechanic_id": "board.variable-grid"},
        {"node_id": "fixed-grid-main", "mechanic_id": "board.fixed-grid"},
        {"node_id": "ways-main", "mechanic_id": "settlement.ways"},
        {"node_id": "effective-ways-main", "mechanic_id": "settlement.effective-ways-capacity"},
        {"node_id": "payline-main", "mechanic_id": "settlement.payline"},
    ]
    owner_specs = (
        ("cascade.step_return_distribution_by_depth", "cascade-steps", ["cascade-main"], "e1"),
        ("variable_grid.return_distribution_by_capacity", "variable-grid-steps", ["variable-grid-main", "ways-main"], "e2"),
        ("effective_ways.return_distribution_by_capacity", "effective-ways-steps", ["effective-ways-main", "fixed-grid-main", "ways-main"], "e3"),
        ("settlement.step_return_distribution", "settlement-steps", ["payline-main"], "e4"),
    )
    source_nodes_by_event = {
        "e1": ["cascade-main", "effective-ways-main", "fixed-grid-main", "variable-grid-main", "ways-main"],
        "e2": ["effective-ways-main", "fixed-grid-main", "variable-grid-main", "ways-main"],
        "e3": ["effective-ways-main", "fixed-grid-main", "ways-main"],
        "e4": ["payline-main"],
    }

    def event(event_id):
        return {
            "event_id": event_id,
            "settlement_step_id": event_id,
            "sample_unit": "complete_settlement_step",
            "dimensions": clone(dimensions),
            "source_node_ids": clone(source_nodes_by_event[event_id]),
        }

    def build(root):
        universe_events = [event(event_id) for event_id in source_nodes_by_event]
        universe_path = root / "events/universe.json"
        dump(universe_path, universe_events)
        scope_instances = [{
            "scope_instance_id": "all-complete-steps",
            "semantic_event_set_id": "all-complete-steps",
            "event_set_path": "events/universe.json",
            "event_set_sha256": semantic_sha(universe_path),
            "event_count": len(universe_events),
            "sample_unit": "complete_settlement_step",
            "dimensions": clone(dimensions),
        }]
        active_items_by_key = {}
        owner_bindings = []
        for metric_id, scope_id, source_node_ids, event_id in owner_specs:
            event_path = root / f"events/{scope_id}.json"
            dump(event_path, [event(event_id)])
            scope = {
                "scope_instance_id": scope_id,
                "semantic_event_set_id": scope_id,
                "event_set_path": f"events/{scope_id}.json",
                "event_set_sha256": semantic_sha(event_path),
                "event_count": 1,
                "sample_unit": "complete_settlement_step",
                "dimensions": clone(dimensions),
            }
            scope_instances.append(scope)
            metric = {
                "metric_id": metric_id,
                "source_node_ids": source_node_ids,
                "instance_dimensions": clone(dimensions),
                "kind": "score",
                "status": "适用",
                "sealed_event_set_id": scope_id,
                "sealed_event_set_path": scope["event_set_path"],
                "sealed_event_set_sha256": scope["event_set_sha256"],
                "sealed_event_count": 1,
            }
            active_items_by_key[metric_instance_key(metric)] = metric
            owner_bindings.append({
                "metric_instance": {
                    "metric_id": metric_id,
                    "source_node_ids": clone(source_node_ids),
                    "instance_dimensions": clone(dimensions),
                },
                "subset_scope_instance_id": scope_id,
            })
        profile = {
            "schema_version": "1.2",
            "step_return_partitions": [{
                "partition_id": "complete-steps",
                "universe_scope_instance_id": "all-complete-steps",
                "step_identity_field": "settlement_step_id",
                "partition_rule_id": "complete-step-return-owner-v1",
            }],
        }
        contract = {
            "schema_version": "1.3",
            "step_return_owner_partitions": [{
                "partition_id": "complete-steps",
                "owner_bindings": list(reversed(owner_bindings)),
            }],
        }
        return profile, contract, active_items_by_key, scope_instances

    def validate(root, profile, contract, active_items_by_key, scope_instances):
        return validate_step_return_owner_partitions(
            profile,
            contract,
            active_items_by_key,
            scope_instances,
            active_nodes,
            root,
        )

    def scope_by_id(scope_instances, scope_id):
        return next(scope for scope in scope_instances if scope["scope_instance_id"] == scope_id)

    def reseal(root, scope_instances, active_items_by_key, scope_id, events):
        scope = scope_by_id(scope_instances, scope_id)
        path = root / scope["event_set_path"]
        dump(path, events)
        scope["event_set_sha256"] = semantic_sha(path)
        scope["event_count"] = len(events)
        for item in active_items_by_key.values():
            if item.get("sealed_event_set_id") == scope["semantic_event_set_id"]:
                item["sealed_event_set_sha256"] = scope["event_set_sha256"]
                item["sealed_event_count"] = scope["event_count"]

    valid_root = base / "valid"
    valid = build(valid_root)
    valid_errors = validate(valid_root, *valid)
    assert valid_errors == [], valid_errors
    assert validate_step_return_owner_partitions(
        {"schema_version": "1.1"},
        {"schema_version": "1.2"},
        {},
        [],
        [],
        None,
    ) == []

    def check(name, mutate, expected):
        root = base / name
        profile, contract, active_items_by_key, scope_instances = build(root)
        mutate(root, profile, contract, active_items_by_key, scope_instances)
        errors = validate(root, profile, contract, active_items_by_key, scope_instances)
        assert any(expected in error for error in errors), (name, errors)
        return errors

    check(
        "missing-profile-partition",
        lambda _, profile, __, ___, ____: profile.pop("step_return_partitions"),
        "game_profile 1.2缺少step_return_partitions",
    )
    check(
        "missing-contract-partition",
        lambda _, __, contract, ___, ____: contract.pop("step_return_owner_partitions"),
        "metric_contract 1.3缺少step_return_owner_partitions",
    )

    def add_outside_event(root, _, __, active_items_by_key, scope_instances):
        outside = event("e1")
        outside["event_id"] = "outside"
        outside["settlement_step_id"] = "outside"
        reseal(
            root,
            scope_instances,
            active_items_by_key,
            "cascade-steps",
            [event("e1"), outside],
        )

    check("outside-parent", add_outside_event, "步骤回报Owner子集超出父全集")

    def overlap(root, _, __, active_items_by_key, scope_instances):
        reseal(
            root,
            scope_instances,
            active_items_by_key,
            "variable-grid-steps",
            [event("e1"), event("e2")],
        )

    overlap_errors = check("overlap", overlap, "步骤回报Owner子集不互斥")
    assert any(
        "settlement_step_id=e1" in error
        and "高优先级Owner=cascade.step_return_distribution_by_depth" in error
        and "低优先级Owner=variable_grid.return_distribution_by_capacity" in error
        for error in overlap_errors
    ), overlap_errors

    def add_uncovered_parent(root, _, __, ___, scope_instances):
        uncovered = event("e4")
        uncovered["event_id"] = "uncovered"
        uncovered["settlement_step_id"] = "uncovered"
        universe = scope_by_id(scope_instances, "all-complete-steps")
        path = root / universe["event_set_path"]
        dump(path, [event(event_id) for event_id in source_nodes_by_event] + [uncovered])
        universe["event_set_sha256"] = semantic_sha(path)
        universe["event_count"] = 5

    check("incomplete-union", add_uncovered_parent, "步骤回报Owner子集并集不完整")

    def swap_bindings(_, __, contract, ___, ____, left, right):
        bindings = contract["step_return_owner_partitions"][0]["owner_bindings"]
        left_binding = next(item for item in bindings if item["metric_instance"]["metric_id"] == left)
        right_binding = next(item for item in bindings if item["metric_instance"]["metric_id"] == right)
        left_binding["subset_scope_instance_id"], right_binding["subset_scope_instance_id"] = (
            right_binding["subset_scope_instance_id"],
            left_binding["subset_scope_instance_id"],
        )

    check(
        "cascade-priority",
        lambda *args: swap_bindings(
            *args,
            "cascade.step_return_distribution_by_depth",
            "settlement.step_return_distribution",
        ),
        "步骤回报Owner优先级复算不一致",
    )
    check(
        "variable-grid-priority",
        lambda *args: swap_bindings(
            *args,
            "variable_grid.return_distribution_by_capacity",
            "effective_ways.return_distribution_by_capacity",
        ),
        "步骤回报Owner优先级复算不一致",
    )

    def duplicate_binding(_, __, contract, ___, ____):
        contract["step_return_owner_partitions"][0]["owner_bindings"].append(
            clone(contract["step_return_owner_partitions"][0]["owner_bindings"][-1])
        )

    check("duplicate-binding", duplicate_binding, "活动步骤回报Owner指标实例重复绑定")
    check(
        "missing-active-binding",
        lambda _, __, contract, ___, ____: contract["step_return_owner_partitions"][0]["owner_bindings"].pop(),
        "活动步骤回报Owner指标实例未绑定",
    )
    check(
        "non-owner-metric",
        lambda _, __, contract, ___, ____: contract["step_return_owner_partitions"][0]["owner_bindings"][0]["metric_instance"].update({"metric_id": "core.rtp.total"}),
        "步骤回报Owner绑定引用非四类指标",
    )
    check(
        "sealed-set-mismatch",
        lambda _, __, contract, ___, ____: contract["step_return_owner_partitions"][0]["owner_bindings"][0].update({"subset_scope_instance_id": "cascade-steps"}),
        "步骤回报Owner指标实例与子集密封事件集不一致",
    )

    def tamper(root, _, __, ___, ____):
        path = root / "events/cascade-steps.json"
        path.write_text(path.read_text(encoding="utf-8") + " ", encoding="utf-8")

    check("tampered-event-file", tamper, "密封事件集hash失效")

    def unknown_source(root, _, __, ___, scope_instances):
        universe = scope_by_id(scope_instances, "all-complete-steps")
        events = [event(event_id) for event_id in source_nodes_by_event]
        events[0]["source_node_ids"].append("unknown-node")
        path = root / universe["event_set_path"]
        dump(path, events)
        universe["event_set_sha256"] = semantic_sha(path)

    check("unknown-parent-source", unknown_source, "引用未知source_node_ids")

    profile_schema = load_json(SKILL_ROOT / "assets/schemas/game-profile.schema.json")
    contract_schema = load_json(SKILL_ROOT / "assets/schemas/metric-contract.schema.json")

    def requires(schema, version, field):
        return any(
            error.validator == "required" and field in error.validator_value
            for error in Draft202012Validator(schema).iter_errors({"schema_version": version})
        )

    assert requires(profile_schema, "1.2", "step_return_partitions")
    assert not requires(profile_schema, "1.1", "step_return_partitions")
    assert requires(contract_schema, "1.3", "step_return_owner_partitions")
    assert not requires(contract_schema, "1.2", "step_return_owner_partitions")

    def def_errors(schema, definition, value):
        wrapper = {
            "$schema": schema["$schema"],
            "$defs": schema["$defs"],
            "$ref": f"#/$defs/{definition}",
        }
        return list(Draft202012Validator(wrapper).iter_errors(value))

    profile_partition = valid[0]["step_return_partitions"][0]
    contract_partition = valid[1]["step_return_owner_partitions"][0]
    assert def_errors(profile_schema, "stepReturnPartition", profile_partition) == []
    assert def_errors(contract_schema, "stepReturnOwnerPartition", contract_partition) == []
    assert any(
        error.validator == "additionalProperties"
        for error in def_errors(profile_schema, "stepReturnPartition", dict(profile_partition, complete=True))
    )
    assert any(
        error.validator == "additionalProperties"
        for error in def_errors(contract_schema, "stepReturnOwnerPartition", dict(contract_partition, disjoint=True))
    )
    invalid_binding = clone(contract_partition["owner_bindings"][0])
    invalid_binding["metric_instance"]["metric_id"] = "core.rtp.total"
    assert def_errors(contract_schema, "stepReturnOwnerBinding", invalid_binding)


def semantic_contract_gate_case(base):
    catalog = catalog_maps(SKILL_ROOT)
    report_version = "slot-alignment.reports.v3.3"

    def clone(value):
        return json.loads(json.dumps(value))

    def target_for(metric):
        metric_id = metric["metric_id"]
        if metric_id == "core.max_win.audit":
            return {
                "observed_max": 1000,
                "theoretical_max": 5000,
                "cap": 5000,
                "cap_hit_count": 0,
                "overflow_event_count": 0,
                "overflow_rule_status": "符合",
            }
        if metric_id == "core.long_tail.audit":
            return {"probability_ge_200x": 0.001}
        kind = metric["kind"]
        method = metric.get("score_profile", {}).get("method") if kind == "score" else metric.get("hard_gate_profile", {}).get("method")
        if method in {"absolute_error", "relative_error"}:
            return 0.5
        if method == "range_error":
            return {"min": 0.4, "max": 0.6}
        if method == "total_variation":
            return {"0x": 0.5, "正回报": 0.5}
        if method == "wasserstein_1d":
            profile = metric["score_profile"] if kind == "score" else metric["hard_gate_profile"]
            profile.update({"bin_positions": [2, 3]})
            return {"2x": 0.5, "3x": 0.5}
        if method in {"grouped_total_variation", "grouped_wasserstein_1d"}:
            metric["score_profile"].update({"group_weights": {"普通状态": 1.0}})
            if method == "grouped_wasserstein_1d":
                metric["score_profile"]["bin_positions_by_group"] = {"普通状态": {"低": 0, "高": 1}}
            return {"普通状态::低": 0.5, "普通状态::高": 0.5}
        if method in {"mean_absolute_error", "max_absolute_error"}:
            return [0.5, 0.5]
        exact_fields = metric.get("audit_profile", {}).get("exact_match_fields", [])
        if exact_fields:
            return {field: "符合" if field.endswith("_status") else 1 for field in exact_fields}
        return {"status": "符合"}

    def build_valid_case(root):
        root.mkdir(parents=True, exist_ok=True)
        manifest_hashes = {}
        multiplier_event_ids = ["multiplier-occurrence", "multiplier-application", "multiplier-value"]
        multiplier = {
            "node_id": "multiplier-main",
            "mechanic_id": "modifier.win-multiplier",
            "name_zh": catalog["mechanics"]["modifier.win-multiplier"]["name_zh"],
            "scope": "modifier:main",
            "status": "必需",
            "semantic_event_set_ids": multiplier_event_ids,
            "attributes": {
                "application_scope": "all_wins",
                "value_source": "sealed_rule",
                "combine_rule": "multiply",
                "application_timing": "after_base_settlement",
                "value_domain": [2, 3],
                "application_may_be_skipped": True,
                "progression_driver": "none",
            },
            "evidence": ["evidence/profile-source.json"],
        }
        payline_event_ids = [
            "payline-winning-block",
            "payline-symbol-rtp",
            "payline-step-return",
            "payline-winning-step",
            "payline-geometry",
        ]
        payline = {
            "node_id": "payline-main",
            "mechanic_id": "settlement.payline",
            "name_zh": catalog["mechanics"]["settlement.payline"]["name_zh"],
            "scope": "settlement:payline",
            "status": "必需",
            "semantic_event_set_ids": payline_event_ids,
            "attributes": {
                "line_count": 1,
                "line_definitions": [{"line_id": "L1", "coordinates": [[0, 0], [1, 0], [2, 0]]}],
                "direction": "left_to_right",
                "min_reels": 3,
                "aggregation_unit": "per_line",
                "winning_scale_dimension": "matched_reel_count",
                "winning_scale_axis_semantics": "natural_linear",
            },
            "evidence": ["evidence/profile-source.json"],
        }
        profile = {
            "schema_version": "1.2",
            "report_contract_version": report_version,
            "task_id": "semantic-gate-test",
            "status": "已完成",
            "scope": {"game_code": "demo", "mode": "base", "rtp_group": 1, "mode_contract": normal_mode_contract()},
            "mechanics_catalog": {
                "version": catalog["mechanics_index"]["version"],
                "sha256": semantic_sha(catalog["mechanics_index_path"]),
            },
            "scope_instances": [],
            "mechanics": [multiplier, payline],
            "mechanic_tree": "- multiplier-main: modifier.win-multiplier\n- payline-main: settlement.payline",
            "gaps": [],
            "required_node_count": 2,
            "semantic_gap_count": 0,
        }

        def add_scope(scope_id, role, source_ids, sample_unit, event_set_id, dimensions, scope_prefix):
            relative = f"evidence/events/{scope_id}.json"
            events = [{
                "event_id": f"{scope_id}-{index}",
                "settlement_step_id": f"{scope_id}-{index}",
                "conditional_group_id": "普通状态",
                "sample_unit": sample_unit,
                "dimensions": dimensions,
                "source_node_ids": source_ids,
            } for index in (1, 2)]
            dump(root / relative, {"events": events})
            event_hash = semantic_sha(root / relative)
            manifest_hashes[relative] = event_hash
            suffix = "|".join(f"{name}={value}" for name, value in sorted(dimensions.items()))
            scope = f"{scope_prefix}|{suffix}" if suffix else scope_prefix
            profile["scope_instances"].append({
                "scope_instance_id": scope_id,
                "scope_role": role,
                "scope": scope,
                "source_node_ids": source_ids,
                "sample_unit": sample_unit,
                "semantic_event_set_id": event_set_id,
                "event_set_path": relative,
                "event_set_sha256": event_hash,
                "event_count": len(events),
                "dimensions": dimensions,
            })

        add_scope("core-paid-overall", "core", [], "paid_entry", "core-paid-overall", {"mode": "base", "rtp_group": 1, "component": "overall"}, "core:overall")
        add_scope("core-paid-base", "core", [], "paid_entry", "core-paid-base", {"mode": "base", "rtp_group": 1, "component": "base"}, "core:base")
        add_scope("core-return", "core", [], "paid_entry_below_200x", "core-return", {"mode": "base", "rtp_group": 1}, "core:base")
        add_scope("core-sigma-overall", "core", [], "paid_entry_or_sealed_component_entry", "core-sigma-overall", {"component": "overall"}, "core:overall")
        add_scope("core-sigma-base", "core", [], "paid_entry_or_sealed_component_entry", "core-sigma-base", {"component": "base"}, "core:base")
        add_scope("core-max-win", "core", [], "paid_entry_and_rule", "core-max-win", {"mode": "base", "rtp_group": 1}, "core:base")
        for scope_id, sample_unit, event_set_id in (
            ("multiplier-occurrence", "multiplier_occurrence_opportunity", "multiplier-occurrence"),
            ("multiplier-application", "multiplier_occurrence_event", "multiplier-application"),
            ("multiplier-value", "applied_multiplier_event", "multiplier-value"),
        ):
            add_scope(scope_id, "mechanic", ["multiplier-main"], sample_unit, event_set_id, {"component": "base", "state": "normal"}, "modifier:main")
        settlement_dimensions = {
            "component": "base", "state": "normal", "board_phase": "initial", "settlement_type": "payline",
        }
        add_scope("payline-winning-block", "mechanic", ["payline-main"], "independent_paid_result_block", "payline-winning-block", settlement_dimensions, "settlement:payline")
        add_scope("payline-symbol-rtp", "mechanic", ["payline-main"], "paid_entry_and_winning_symbol_event", "payline-symbol-rtp", {"component": "base", "state": "normal", "settlement_type": "payline"}, "settlement:payline")
        add_scope("payline-step-return", "mechanic", ["payline-main"], "complete_non_cascade_settlement_step", "payline-step-return", {"component": "base", "state": "normal", "board_phase": "initial"}, "settlement:payline")
        add_scope("payline-winning-step", "mechanic", ["payline-main"], "winning_settlement_step", "payline-winning-step", settlement_dimensions, "settlement:payline")
        add_scope("payline-geometry", "mechanic", ["payline-main"], "winning_line_event", "payline-geometry", {"component": "base", "state": "normal", "board_phase": "initial"}, "settlement:payline")
        profile["step_return_partitions"] = [{
            "partition_id": "complete-steps",
            "universe_scope_instance_id": "payline-step-return",
            "step_identity_field": "settlement_step_id",
            "partition_rule_id": "complete-step-return-owner-v1",
        }]

        profile_path = root / "game_profile.json"
        authority_path = root / "parameter_authority.json"
        manifest_path = root / "input_manifest.json"
        contract_path = root / "metric_contract.json"
        dump(profile_path, profile)
        dump(authority_path, {
            "schema_version": "1.1",
            "report_contract_version": report_version,
            "task_id": "semantic-gate-test",
            "status": "已完成",
            "scope": {"game_code": "demo", "mode": "base", "rtp_group": 1},
            "parameters": [],
        })
        package_ids = required_package_ids(profile["mechanics"], catalog)
        expectation_errors = []
        expected_instances, package_metrics, expected_bindings = expected_metrics(
            profile["mechanics"], profile["scope_instances"], package_ids, catalog, expectation_errors
        )
        assert expectation_errors == [], expectation_errors
        metrics = []
        for metric_id, source_ids, dimension_items in sorted(expected_instances):
            item = clone(catalog["metrics"][metric_id])
            dimensions = dict(dimension_items)
            binding = expected_bindings.get((metric_id, source_ids, dimension_items))
            item.update({
                "scope": binding["scope"] if binding else "core:base",
                "source_node_ids": list(source_ids),
                "instance_dimensions": dimensions,
                "status": "适用",
            })
            item["target"] = target_for(item)
            if item["kind"] == "hard":
                item["hard_gate_profile"]["base_tolerance"] = 0.01
                if item["hard_gate_profile"]["method"] in {"total_variation", "wasserstein_1d"}:
                    item["sample_capability_input"] = {
                        "original_sample_count": 1_000_000_000,
                        "formal_sample_count": 1_000_000_000,
                    }
            if item["metric_id"] == "settlement.scale_given_symbol_distribution":
                item["score_profile"]["axis_semantics"] = "natural_linear"
            if item["kind"] == "score":
                method = item["score_profile"]["method"]
                item["weight"] = item["default_weight"]
                if item["scope_aggregation"] == "weighted_mean":
                    item["scope_weight"] = 1.0
                if method in {
                    "total_variation", "wasserstein_1d", "grouped_total_variation", "grouped_wasserstein_1d",
                }:
                    item["score_profile"].update({
                        "reachable_support_source": "task_contract",
                        "reachable_support_status": "active",
                    })
                assert binding is not None
                item.update({
                    "sealed_event_set_id": binding["semantic_event_set_id"],
                    "sealed_event_set_path": binding["event_set_path"],
                    "sealed_event_set_sha256": binding["event_set_sha256"],
                    "sealed_event_count": binding["event_count"],
                })
                if method.startswith("grouped_"):
                    groups = sorted({key.split("::", 1)[0] for key in item["target"]})
                    item["conditional_group_weight_binding"] = {
                        "method": "sealed_original_exposure",
                        "source_event_set_id": binding["semantic_event_set_id"],
                        "source_evidence_path": binding["event_set_path"],
                        "source_evidence_sha256": binding["event_set_sha256"],
                        "source_event_count": binding["event_count"],
                        "group_exposure_counts": {group: binding["event_count"] for group in groups},
                        "token_multipliers": {group: 1 for group in groups},
                        "normalization": "normalize_positive_active_groups",
                    }
                if method in {
                    "total_variation", "grouped_total_variation", "wasserstein_1d",
                    "grouped_wasserstein_1d", "mean_absolute_error", "grouped_mean_absolute_error",
                }:
                    item["sample_capability_input"] = {
                        "original_sample_count": 1_000_000_000,
                        "formal_sample_count": 1_000_000_000,
                    }
                    if method.startswith("grouped_"):
                        counts = {group: 1_000_000_000 for group in groups}
                        item["sample_capability_input"].update({
                            "original_group_sample_counts": counts,
                            "formal_group_sample_counts": counts,
                        })
            metrics.append(item)

        target_bindings = []
        for item in metrics:
            key = (
                item["metric_id"],
                tuple(sorted(item["source_node_ids"])),
                tuple(sorted(item["instance_dimensions"].items())),
            )
            binding = expected_bindings.get(key)
            assert binding is not None and binding.get("virtual_na") is not True, key
            target_bindings.append({
                "metric_instance": {
                    "metric_id": item["metric_id"],
                    "source_node_ids": sorted(item["source_node_ids"]),
                    "instance_dimensions": item["instance_dimensions"],
                },
                "measurement_contract_sha256": measurement_contract_sha256(catalog["metrics"][item["metric_id"]]),
                "parent_event_set": {
                    "scope_instance_id": binding["scope_instance_id"],
                    "semantic_event_set_id": binding["semantic_event_set_id"],
                    "event_set_path": binding["event_set_path"],
                    "event_set_sha256": binding["event_set_sha256"],
                    "event_count": binding["event_count"],
                },
            })
        target_path = "evidence/targets.json"
        dump(root / target_path, {
            "targets": [item["target"] for item in metrics],
            "bindings": target_bindings,
        })
        target_hash = semantic_sha(root / target_path)
        manifest_hashes[target_path] = target_hash
        for index, item in enumerate(metrics):
            item["target_evidence"] = {
                "evidence_path": target_path,
                "evidence_sha256": target_hash,
                "json_pointer": f"/targets/{index}",
                "binding_json_pointer": f"/bindings/{index}",
            }

        package_matches = []
        node_map = {node["node_id"]: node for node in profile["mechanics"]}
        for (package_id, source_ids, dimension_items), metric_ids in sorted(package_metrics.items()):
            if package_id == "core.general":
                continue
            scopes = {
                expected_bindings[(metric_id, source_ids, dimension_items)]["scope"]
                for metric_id in metric_ids
                if (metric_id, source_ids, dimension_items) in expected_bindings
            }
            assert len(scopes) == 1, (package_id, source_ids, dimension_items, scopes)
            package_matches.append({
                "mechanic_id": node_map[source_ids[0]]["mechanic_id"],
                "source_node_ids": list(source_ids),
                "instance_dimensions": dict(dimension_items),
                "scope": next(iter(scopes)),
                "package_id": package_id,
                "owner": package_id,
                "metric_ids": sorted(metric_ids),
                "evidence": {"method": "画像与目录条件确定性匹配"},
                "status": "已匹配",
            })
        score_groups = sorted({item["score_group"] for item in metrics if item["kind"] == "score"})
        group_weights = {name: 1 / len(score_groups) for name in score_groups}
        manifest = {
            "schema_version": "1.1",
            "report_contract_version": report_version,
            "task_id": "semantic-gate-test",
            "status": "已完成",
            "scope": {"game_code": "demo", "mode": "base", "rtp_group": 1},
            "hashes": manifest_hashes,
        }
        dump(manifest_path, manifest)
        metric_count = len(expected_instances)
        contract = {
            "schema_version": "1.3",
            "report_contract_version": report_version,
            "task_id": "semantic-gate-test",
            "status": "已完成",
            "scope": {"game_code": "demo", "mode": "base", "rtp_group": 1, "target_rtp": 0.96, "mode_contract": normal_mode_contract()},
            "input_hashes": {
                "input_manifest": semantic_sha(manifest_path),
                "game_profile": semantic_sha(profile_path),
                "parameter_authority": semantic_sha(authority_path),
            },
            "catalogs": {
                "mechanics_version": catalog["mechanics_index"]["version"],
                "metrics_version": catalog["metrics_index"]["version"],
                "hashes": {
                    "mechanics": semantic_sha(catalog["mechanics_index_path"]),
                    "metrics": semantic_sha(catalog["metrics_index_path"]),
                },
            },
            "component_rtp_target_policy": {
                "method": "original_component_share_mapped_to_authoritative_total_rtp",
                "original_absolute_rtp_as_target": False,
                "authoritative_total_rtp_required": True,
                "share_sum_target": 1.0,
                "legacy_contracts_unchanged": True,
            },
            "coverage": {
                "mechanic_required": 2,
                "mechanic_owned": 2,
                "mechanic_coverage": 1.0,
                "metric_required": metric_count,
                "metric_measurable": metric_count,
                "metric_measurability": 1.0,
                "metric_resolved": metric_count,
                "metric_resolution": 1.0,
            },
            "group_weights": group_weights,
            "metrics": metrics,
            "package_matches": package_matches,
            "coupling_clusters": [],
            "gaps": [],
            "owner_conflicts": [],
            "waivers": [],
            "step_return_owner_partitions": [{
                "partition_id": "complete-steps",
                "owner_bindings": [{
                    "metric_instance": {
                        "metric_id": "settlement.step_return_distribution",
                        "source_node_ids": ["payline-main"],
                        "instance_dimensions": {"component": "base", "state": "normal", "board_phase": "initial"},
                    },
                    "subset_scope_instance_id": "payline-step-return",
                }],
            }],
        }
        base_contract_path = root / "base_metric_contract.json"
        ordered_contract_path = root / "ordered_metric_contract.json"
        dump(base_contract_path, contract)
        run(
            ROOT / "apply_hard_gate_tolerance_policy.py",
            "--contract", base_contract_path,
            "--policy", SKILL_ROOT / "assets/policies/hard_gate_tolerance_policy.v2.json",
            "--output", base_contract_path,
        )
        run(
            ROOT / "apply_jackpot_materiality_policy.py",
            "--contract", base_contract_path,
            "--game-profile", profile_path,
            "--policy", SKILL_ROOT / "assets/policies/jackpot_materiality_policy.v1.json",
            "--output", base_contract_path,
        )
        run(
            ROOT / "apply_ordered_distance_policy.py",
            "--contract", base_contract_path,
            "--policy", SKILL_ROOT / "assets/policies/ordered_distance_policy.v1.json",
            "--output", ordered_contract_path,
        )
        run(
            ROOT / "apply_score_group_weight_policy.py",
            "--contract", ordered_contract_path,
            "--policy", SKILL_ROOT / "assets/policies/score_group_weight_policy.v1.json",
            "--output", contract_path,
        )
        run(
            ROOT / "apply_sample_capability_policy.py",
            "--contract", contract_path,
            "--policy", SKILL_ROOT / "assets/policies/sample_capability_policy.v1.json",
            "--output", contract_path,
        )
        contract = load_json(contract_path)
        return profile, manifest, contract

    valid_root = base / "valid"
    build_valid_case(valid_root)

    def validate_case(root, validation_mode="stage_transition"):
        return validate_semantic_contract(
            root / "game_profile.json",
            root / "metric_contract.json",
            SKILL_ROOT,
            root / "parameter_authority.json",
            root / "input_manifest.json",
            validation_mode=validation_mode,
            task_root_path=root,
        )

    def without_catalog_state_errors(errors):
        return [error for error in errors if not error.startswith(("目录包hash失效:", "目录校验失败:"))]

    valid_errors = without_catalog_state_errors(validate_case(valid_root))
    assert valid_errors == [], valid_errors

    def check(name, mutate, expected, validation_mode="stage_transition"):
        root = base / name
        shutil.copytree(valid_root, root)
        profile_path = root / "game_profile.json"
        manifest_path = root / "input_manifest.json"
        authority_path = root / "parameter_authority.json"
        contract_path = root / "metric_contract.json"
        profile, manifest, contract = map(load_json, (profile_path, manifest_path, contract_path))
        mutate(root, profile, manifest, contract)
        dump(profile_path, profile)
        dump(manifest_path, manifest)
        contract["input_hashes"].update({
            "input_manifest": semantic_sha(manifest_path),
            "game_profile": semantic_sha(profile_path),
            "parameter_authority": semantic_sha(authority_path),
        })
        dump(contract_path, contract)
        errors = validate_case(root, validation_mode)
        assert any(expected in error for error in errors), (name, errors)

    def remove_metric(_, __, ___, contract):
        contract["metrics"].pop(next(index for index, item in enumerate(contract["metrics"]) if item["metric_id"] == "core.rtp.total"))

    check("empty-profile", lambda _, profile, __, ___: profile.update({"mechanics": [], "required_node_count": 0}), "玩法画像不能为空")
    check("unknown-attribute", lambda _, profile, __, ___: profile["mechanics"][0]["attributes"].update({"unknown": 1}), "包含未知属性")
    check("missing-core", remove_metric, "缺少画像命中指标实例")
    check("tampered-owner", lambda _, __, ___, contract: contract["metrics"][0].update({"owner": "tampered"}), "篡改目录语义")
    check("fake-coverage", lambda _, __, ___, contract: contract["coverage"].update({"metric_required": 1}), "coverage自报不一致")
    check("stale-catalog", lambda _, __, ___, contract: contract["catalogs"]["hashes"].update({"metrics": "0" * 64}), "目录hash失效")
    check("missing-report-version", lambda _, __, manifest, ___: manifest.pop("report_contract_version"), "input_manifest必须使用slot-alignment.reports.v3.3")
    check("future-report-version", lambda _, __, ___, contract: contract.update({"report_contract_version": "slot-alignment.reports.v3.4"}), "metric_contract必须使用slot-alignment.reports.v3.3")

    def duplicate_node(root, profile, manifest, _):
        source = profile["mechanics"][0]
        duplicate = clone(source)
        duplicate.update({"node_id": "multiplier-secondary", "scope": "modifier:secondary"})
        event_id_map = {event_id: f"{event_id}-secondary" for event_id in source["semantic_event_set_ids"]}
        duplicate["semantic_event_set_ids"] = list(event_id_map.values())
        profile["mechanics"].append(duplicate)
        profile["required_node_count"] = 2
        for scope in clone([
            item for item in profile["scope_instances"]
            if item["scope_role"] == "mechanic" and item["source_node_ids"] == ["multiplier-main"]
        ]):
            old_path = root / scope["event_set_path"]
            data = load_json(old_path)
            for event in data["events"]:
                event["event_id"] += "-secondary"
            scope["scope_instance_id"] += "-secondary"
            scope["scope"] = scope["scope"].replace("modifier:main", "modifier:secondary")
            scope["source_node_ids"] = ["multiplier-secondary"]
            scope["semantic_event_set_id"] = event_id_map[scope["semantic_event_set_id"]]
            scope["event_set_path"] = scope["event_set_path"].replace(".json", "-secondary.json")
            dump(root / scope["event_set_path"], data)
            scope["event_set_sha256"] = semantic_sha(root / scope["event_set_path"])
            manifest["hashes"][scope["event_set_path"]] = scope["event_set_sha256"]
            profile["scope_instances"].append(scope)

    check("same-mechanic-missing-node-instance", duplicate_node, "缺少画像命中指标实例")

    score_metric = next(item for item in load_json(valid_root / "metric_contract.json")["metrics"] if item["kind"] == "score")
    score_event_id = score_metric["sealed_event_set_id"]

    def missing_manifest_hash(_, __, manifest, ___):
        manifest["hashes"].pop(score_metric["sealed_event_set_path"])

    check("missing-event-manifest-hash", missing_manifest_hash, "未写入input_manifest.hashes")
    check("invalid-event-hash", lambda _, profile, __, ___: next(item for item in profile["scope_instances"] if item["semantic_event_set_id"] == score_event_id).update({"event_set_sha256": "0" * 64}), "事件集hash失效")

    def wrong_event_count(_, profile, __, contract):
        scope = next(item for item in profile["scope_instances"] if item["semantic_event_set_id"] == score_event_id)
        scope["event_count"] += 1
        for item in contract["metrics"]:
            if item.get("sealed_event_set_id") == score_event_id:
                item["sealed_event_count"] = scope["event_count"]

    check("wrong-event-count", wrong_event_count, "事件数与密封文件不一致")

    def tamper_event_content(field, value):
        def mutate(root, profile, manifest, contract):
            scope = next(item for item in profile["scope_instances"] if item["semantic_event_set_id"] == score_event_id)
            path = root / scope["event_set_path"]
            data = load_json(path)
            for event in data["events"]:
                if field == "sample_unit":
                    event[field] = value
                else:
                    event["dimensions"][field] = value
            dump(path, data)
            event_hash = semantic_sha(path)
            scope["event_set_sha256"] = event_hash
            manifest["hashes"][scope["event_set_path"]] = event_hash
            for item in contract["metrics"]:
                if item.get("sealed_event_set_id") == score_event_id:
                    item["sealed_event_set_sha256"] = event_hash
        return mutate

    check("event-sample-unit-mismatch", tamper_event_content("sample_unit", "wrong_sample_unit"), "sample_unit")
    check("event-dimensions-mismatch", tamper_event_content("state", "wrong_state"), "dimensions")
    check("score-event-path-mismatch", lambda _, __, ___, contract: next(item for item in contract["metrics"] if item.get("sealed_event_set_id") == score_event_id).update({"sealed_event_set_path": "evidence/events/not-the-bound-event.json"}), "事件集绑定与scope_instance不一致")
    check("target-evidence-pointer", lambda _, __, ___, contract: contract["metrics"][0]["target_evidence"].update({"json_pointer": "/targets/999"}), "target_evidence无法核验")
    check("target-evidence-hash", lambda _, __, ___, contract: contract["metrics"][0]["target_evidence"].update({"evidence_sha256": "0" * 64}), "target_evidence文件hash失效")

    def tamper_target_binding(update):
        def mutate(root, _, manifest, contract):
            evidence = contract["metrics"][0]["target_evidence"]
            path = root / evidence["evidence_path"]
            data = load_json(path)
            update(data["bindings"][0])
            dump(path, data)
            evidence_hash = semantic_sha(path)
            manifest["hashes"][evidence["evidence_path"]] = evidence_hash
            for item in contract["metrics"]:
                item["target_evidence"]["evidence_sha256"] = evidence_hash
        return mutate

    check(
        "target-binding-metric-instance",
        tamper_target_binding(lambda binding: binding["metric_instance"].update({"metric_id": "tampered.metric"})),
        "target_evidence未绑定当前指标实例",
    )
    check(
        "target-binding-measurement-contract",
        tamper_target_binding(lambda binding: binding.update({"measurement_contract_sha256": "0" * 64})),
        "target_evidence未绑定当前指标实例",
    )
    check(
        "target-binding-parent-event",
        tamper_target_binding(lambda binding: binding["parent_event_set"].update({"event_set_sha256": "0" * 64})),
        "target_evidence未绑定当前指标实例",
    )

    inactive_root = base / "inactive-score-without-event-binding"
    shutil.copytree(valid_root, inactive_root)
    inactive_profile = load_json(inactive_root / "game_profile.json")
    inactive_manifest = load_json(inactive_root / "input_manifest.json")
    inactive_contract = load_json(inactive_root / "metric_contract.json")
    inactive_profile["mechanics"][0]["attributes"]["application_may_be_skipped"] = False
    inactive_item = next(item for item in inactive_contract["metrics"] if item["metric_id"] == "multiplier.application_rate_given_occurrence")
    evidence_path = "evidence/inapplicability.json"
    evidence_claim = {"application_may_be_skipped": False}
    dump(inactive_root / evidence_path, {"claims": {"deterministic_application": evidence_claim}})
    evidence_hash = semantic_sha(inactive_root / evidence_path)
    inactive_manifest["hashes"][evidence_path] = evidence_hash
    inactive_item.update({
        "status": "不适用",
        "target": 1.0,
        "inapplicability_reason_code": "deterministic_rule_result",
        "inapplicability_evidence": [{
            "evidence_path": evidence_path,
            "evidence_sha256": evidence_hash,
            "json_pointer": "/claims/deterministic_application",
            "expected_value": evidence_claim,
        }],
    })
    for field in ("target_evidence", "sealed_event_set_id", "sealed_event_set_path", "sealed_event_set_sha256", "sealed_event_count", "scope_weight"):
        inactive_item.pop(field, None)
    dump(inactive_root / "game_profile.json", inactive_profile)
    dump(inactive_root / "input_manifest.json", inactive_manifest)
    inactive_contract["input_hashes"].update({
        "input_manifest": semantic_sha(inactive_root / "input_manifest.json"),
        "game_profile": semantic_sha(inactive_root / "game_profile.json"),
    })
    inactive_base_path = inactive_root / "inactive_metric_contract.json"
    dump(inactive_base_path, inactive_contract)
    run(
        ROOT / "apply_score_group_weight_policy.py",
        "--contract", inactive_base_path,
        "--policy", SKILL_ROOT / "assets/policies/score_group_weight_policy.v1.json",
        "--output", inactive_root / "metric_contract.json",
    )
    inactive_errors = without_catalog_state_errors(validate_case(inactive_root))
    assert inactive_errors == [], inactive_errors

    legacy_root = base / "historical-replay"
    legacy_root.mkdir(parents=True, exist_ok=True)
    legacy_profile = {
        "schema_version": "1.1", "report_contract_version": "slot-alignment.reports.v2.6", "task_id": "legacy",
        "status": "已完成", "scope": {"game_code": "demo", "mode": "base", "rtp_group": 1, "target_rtp": 0.96},
        "mechanics_catalog": {"version": "2.0.0", "sha256": "a" * 64},
        "mechanics": [{
            "node_id": "legacy-free-spin", "mechanic_id": "feature.free-spin", "name_zh": "免费旋转", "status": "必需", "scope": "feature:free-spin",
            "semantic_event_set_ids": ["legacy-feature"],
            "attributes": {"initial_spins": 10, "retrigger": True}, "evidence": ["legacy-profile.json"],
        }],
        "required_node_count": 1, "semantic_gap_count": 0,
    }
    legacy_contract = {
        "schema_version": "1.2", "report_contract_version": "slot-alignment.reports.v2.6", "task_id": "legacy",
        "status": "已完成", "sealed_at": "2026-01-01T00:00:00Z",
        "scope": {"game_code": "demo", "mode": "base", "rtp_group": 1, "target_rtp": 0.96},
        "catalogs": {
            "mechanics_version": "2.0.0", "metrics_version": "2.0.0",
            "hashes": {"mechanics": "a" * 64, "metrics": "b" * 64},
        },
        "coverage": {
            "mechanic_required": 1, "mechanic_owned": 1, "mechanic_coverage": 1.0,
            "metric_required": 1, "metric_measurable": 1, "metric_measurability": 1.0,
        },
        "metrics": [{
            "metric_id": "core.rtp.total", "kind": "hard", "scope": "base", "status": "适用",
            "unit": "ratio", "measurement": "sum(total_win)/sum(real_bet)", "target": 0.96,
        }],
        "coupling_clusters": [], "waivers": [], "gaps": [], "owner_conflicts": [],
    }
    legacy_manifest = {
        "schema_version": "1.1", "report_contract_version": "slot-alignment.reports.v2.6", "task_id": "legacy", "status": "已完成",
        "scope": {"game_code": "demo", "mode": "base", "rtp_group": 1, "target_rtp": 0.96},
    }
    legacy_profile_path = legacy_root / "game_profile.json"
    legacy_contract_path = legacy_root / "metric_contract.json"
    legacy_manifest_path = legacy_root / "input_manifest.json"
    legacy_authority_path = legacy_root / "parameter_authority.json"
    dump(legacy_profile_path, legacy_profile)
    dump(legacy_manifest_path, legacy_manifest)
    dump(legacy_authority_path, {
        "schema_version": "1.1", "report_contract_version": "slot-alignment.reports.v2.6",
        "task_id": "legacy", "status": "已完成", "parameters": [],
    })
    legacy_contract["input_hashes"] = {
        "game_profile": semantic_sha(legacy_profile_path),
        "input_manifest": semantic_sha(legacy_manifest_path),
        "parameter_authority": semantic_sha(legacy_authority_path),
    }
    dump(legacy_contract_path, legacy_contract)
    assert validate_case(legacy_root, "historical_replay") == []
    assert any("新任务" in error or "v3.1" in error for error in validate_case(legacy_root))

    legacy_v32_root = base / "historical-replay-v3.2"
    legacy_v32_root.mkdir(parents=True, exist_ok=True)
    v32_profile = copy.deepcopy(legacy_profile)
    v32_contract = copy.deepcopy(legacy_contract)
    v32_manifest = copy.deepcopy(legacy_manifest)
    v32_authority = {
        "schema_version": "1.1", "report_contract_version": "slot-alignment.reports.v3.2",
        "task_id": "legacy-v32", "status": "已完成", "parameters": [],
    }
    for document in (v32_profile, v32_contract, v32_manifest):
        document["report_contract_version"] = "slot-alignment.reports.v3.2"
        document["task_id"] = "legacy-v32"
    v32_profile["schema_version"] = "1.2"
    v32_contract["schema_version"] = "1.3"
    v32_manifest["schema_version"] = "1.1"
    dump(legacy_v32_root / "game_profile.json", v32_profile)
    dump(legacy_v32_root / "input_manifest.json", v32_manifest)
    dump(legacy_v32_root / "parameter_authority.json", v32_authority)
    v32_contract["input_hashes"] = {
        "game_profile": semantic_sha(legacy_v32_root / "game_profile.json"),
        "input_manifest": semantic_sha(legacy_v32_root / "input_manifest.json"),
        "parameter_authority": semantic_sha(legacy_v32_root / "parameter_authority.json"),
    }
    dump(legacy_v32_root / "metric_contract.json", v32_contract)
    assert validate_case(legacy_v32_root, "historical_replay") == []

    v32_contract["schema_version"] = "1.2"
    dump(legacy_v32_root / "metric_contract.json", v32_contract)
    assert any("metric_contract 1.3" in error for error in validate_case(legacy_v32_root, "historical_replay"))

    v32_contract["schema_version"] = "1.3"
    for document in (v32_profile, v32_contract, v32_manifest, v32_authority):
        document["report_contract_version"] = "slot-alignment.reports.v3.3"
    dump(legacy_v32_root / "game_profile.json", v32_profile)
    dump(legacy_v32_root / "input_manifest.json", v32_manifest)
    dump(legacy_v32_root / "parameter_authority.json", v32_authority)
    v32_contract["input_hashes"] = {
        "game_profile": semantic_sha(legacy_v32_root / "game_profile.json"),
        "input_manifest": semantic_sha(legacy_v32_root / "input_manifest.json"),
        "parameter_authority": semantic_sha(legacy_v32_root / "parameter_authority.json"),
    }
    dump(legacy_v32_root / "metric_contract.json", v32_contract)
    assert any("v2.5至v2.9或v3.2" in error for error in validate_case(legacy_v32_root, "historical_replay"))

    empty_history_root = base / "empty-historical-replay"
    empty_history_root.mkdir(parents=True, exist_ok=True)
    dump(empty_history_root / "game_profile.json", {"schema_version": "1.0", "report_contract_version": "slot-alignment.reports.v2.6"})
    dump(empty_history_root / "metric_contract.json", {"schema_version": "1.0", "report_contract_version": "slot-alignment.reports.v2.6"})
    dump(empty_history_root / "input_manifest.json", {"report_contract_version": "slot-alignment.reports.v2.6"})
    dump(empty_history_root / "parameter_authority.json", {"schema_version": "1.0", "task_id": "legacy", "status": "已完成", "parameters": []})
    assert validate_case(empty_history_root, "historical_replay")

    legacy_manifest.pop("report_contract_version")
    dump(legacy_root / "input_manifest.json", legacy_manifest)
    assert validate_case(legacy_root, "historical_replay")
    legacy_manifest["report_contract_version"] = "slot-alignment.reports.v3.3"
    dump(legacy_root / "input_manifest.json", legacy_manifest)
    assert validate_case(legacy_root, "historical_replay")

    def scope_stub(scope_id, source_ids, sample_unit, event_set_id, dimensions):
        suffix = "|".join(f"{name}={value}" for name, value in sorted(dimensions.items()))
        return {
            "scope_instance_id": scope_id,
            "scope_role": "mechanic",
            "scope": f"test:{source_ids[0]}|{suffix}",
            "source_node_ids": source_ids,
            "sample_unit": sample_unit,
            "semantic_event_set_id": event_set_id,
            "event_set_path": f"evidence/events/{scope_id}.json",
            "event_set_sha256": "a" * 64,
            "event_count": 2,
            "dimensions": dimensions,
        }

    def core_scope_stub(scope_id, sample_unit, dimensions):
        suffix = "|".join(f"{name}={value}" for name, value in sorted(dimensions.items()))
        return {
            "scope_instance_id": scope_id,
            "scope_role": "core",
            "scope": f"core:{scope_id}|{suffix}",
            "source_node_ids": [],
            "sample_unit": sample_unit,
            "semantic_event_set_id": scope_id,
            "event_set_path": f"evidence/events/{scope_id}.json",
            "event_set_sha256": "a" * 64,
            "event_count": 2,
            "dimensions": dimensions,
        }

    free_spin = {
        "node_id": "free-spin-main", "mechanic_id": "feature.free-spin", "name_zh": "免费旋转", "scope": "feature:free-spin",
        "status": "必需", "semantic_event_set_ids": ["fs-natural", "fs-buy", "fs-step", "fs-endogenous", "fs-paid-endogenous"],
        "attributes": {
            "entry_sources": ["natural", "feature_buy"],
            "entry_source_semantics": {
                "natural": {"origin": "endogenous", "source_kind": "symbol_rule"},
                "feature_buy": {"origin": "exogenous", "source_kind": "feature_buy"},
            },
            "stage_graph": {
                "entry_stage": "free_spin",
                "stages": ["free_spin", "completed"],
                "transitions": [{"from_stage": "free_spin", "to_stage": "completed", "branch_id": "normal_exit"}],
                "terminal_stages": ["completed"],
            },
            "path_signature_definition": {
                "path_id_domain": ["standard_path"],
                "included_fields": ["control_stage_id", "branch_id"],
                "excluded_fields": ["award_outcome", "state_value", "duration", "return_bucket"],
                "canonicalization_rule": "按控制阶段和分支顺序生成路径签名",
            },
            "initial_spin_grant_rule": "fixed:10",
            "spin_consumption_rule": "one_per_spin",
            "exit_condition": "remaining=0",
            "retrigger_rule": "scatter>=3:add5",
        },
        "evidence": ["profile.json"],
    }
    free_spin_scopes = [
        core_scope_stub("core-paid-overall", "paid_entry", {"mode": "base", "rtp_group": 1, "component": "overall"}),
        core_scope_stub("core-paid-base", "paid_entry", {"mode": "base", "rtp_group": 1, "component": "base"}),
        core_scope_stub("core-paid-feature", "paid_entry", {"mode": "base", "rtp_group": 1, "component": "feature:free-spin-main"}),
        core_scope_stub("core-return", "paid_entry_below_200x", {"mode": "base", "rtp_group": 1, "component": "overall"}),
        core_scope_stub("core-sigma-overall", "paid_entry_or_sealed_component_entry", {"component": "overall"}),
        core_scope_stub("core-sigma-base", "paid_entry_or_sealed_component_entry", {"component": "base"}),
        core_scope_stub("core-sigma-feature", "paid_entry_or_sealed_component_entry", {"component": "feature:free-spin-main"}),
        core_scope_stub("core-max-win", "paid_entry_and_rule", {"mode": "base", "rtp_group": 1, "component": "overall"}),
        scope_stub("fs-entry-natural", ["free-spin-main"], "free_spin_entry_event", "fs-natural", {"entry_source": "natural"}),
        scope_stub("fs-entry-buy", ["free-spin-main"], "free_spin_entry_event", "fs-buy", {"entry_source": "feature_buy"}),
        scope_stub("fs-entry-endogenous", ["free-spin-main"], "feature_entry_event", "fs-endogenous", {"entry_source_domain": "endogenous"}),
        scope_stub("fs-paid-endogenous", ["free-spin-main"], "paid_entry", "fs-paid-endogenous", {"entry_source_domain": "endogenous"}),
        scope_stub("fs-step", ["free-spin-main"], "eligible_free_spin_step", "fs-step", {"state": "active"}),
        scope_stub("fs-cycle-natural", ["free-spin-main"], "completed_feature_cycle", "fs-natural", {"entry_source": "natural"}),
        scope_stub("fs-cycle-buy", ["free-spin-main"], "completed_feature_cycle", "fs-buy", {"entry_source": "feature_buy"}),
        scope_stub("fs-paid-natural", ["free-spin-main"], "paid_entry", "fs-natural", {"entry_source": "natural"}),
    ]
    free_spin_expectation_errors = []
    free_spin_expected, _, _ = expected_metrics(
        [free_spin], free_spin_scopes, required_package_ids([free_spin], catalog), catalog, free_spin_expectation_errors
    )
    assert free_spin_expectation_errors == [], free_spin_expectation_errors
    for metric_id in ("free_spin.initial_grant_distribution", "feature_cycle.stage_path_distribution"):
        metric_instances = {item for item in free_spin_expected if item[0] == metric_id}
        entries = {dict(dimensions)["entry_source"] for _, _, dimensions in metric_instances}
        assert entries == {"natural", "feature_buy"}
        natural_only = {item for item in metric_instances if dict(item[2]).get("entry_source") == "natural"}
        assert any(dict(dimensions).get("entry_source") == "feature_buy" for _, _, dimensions in metric_instances - natural_only)

    natural_only_feature = clone(free_spin)
    natural_only_feature["attributes"]["entry_sources"] = ["natural"]
    natural_only_feature["attributes"]["entry_source_semantics"] = {
        "natural": {"origin": "endogenous", "source_kind": "symbol_rule"},
    }
    natural_only_feature["semantic_event_set_ids"] = ["fs-natural", "fs-step", "fs-endogenous", "fs-paid-endogenous"]
    natural_only_scopes = [
        scope for scope in free_spin_scopes
        if scope.get("dimensions", {}).get("entry_source") != "feature_buy"
    ]
    natural_only_errors = []
    natural_only_expected, _, natural_only_bindings = expected_metrics(
        [natural_only_feature], natural_only_scopes,
        required_package_ids([natural_only_feature], catalog), catalog, natural_only_errors,
    )
    assert natural_only_errors == [], natural_only_errors
    buy_audit_key = next(
        key for key in natural_only_expected
        if key[0] == "feature_cycle.base_bet_equivalent_return_distribution"
    )
    assert dict(buy_audit_key[2]) == {"entry_source": "feature_buy"}
    assert natural_only_bindings[buy_audit_key]["virtual_na"] is True

    missing_feature_component_errors = []
    scopes_without_feature_component = [
        scope for scope in free_spin_scopes
        if scope.get("dimensions", {}).get("component") != "feature:free-spin-main"
    ]
    expected_metrics(
        [free_spin], scopes_without_feature_component,
        required_package_ids([free_spin], catalog), catalog, missing_feature_component_errors,
    )
    assert sum("缺少画像推导的组件scope_instance: feature:free-spin-main" in error for error in missing_feature_component_errors) == 2

    multiplier_nodes, multiplier_scopes = [], []
    for index in (1, 2):
        node = clone(load_json(valid_root / "game_profile.json")["mechanics"][0])
        node["node_id"] = f"multiplier-{index}"
        node["semantic_event_set_ids"] = [f"m{index}-occ", f"m{index}-app", f"m{index}-value"]
        multiplier_nodes.append(node)
        for suffix, sample_unit, event_id in (
            ("occ", "multiplier_occurrence_opportunity", f"m{index}-occ"),
            ("app", "multiplier_occurrence_event", f"m{index}-app"),
            ("value", "applied_multiplier_event", f"m{index}-value"),
        ):
            multiplier_scopes.append(scope_stub(f"m{index}-{suffix}", [node["node_id"]], sample_unit, event_id, {"component": "base", "state": "normal"}))
    multi_expected, _, _ = expected_metrics(
        multiplier_nodes, multiplier_scopes, required_package_ids(multiplier_nodes, catalog), catalog, []
    )
    occurrence_sources = {source_ids for metric_id, source_ids, _ in multi_expected if metric_id == "multiplier.occurrence_rate"}
    assert occurrence_sources == {("multiplier-1",), ("multiplier-2",)}

    wild_multiplier = clone(multiplier_nodes[0])
    wild_multiplier["node_id"] = "wild-linked-multiplier"
    wild_multiplier["semantic_event_set_ids"] = ["wild-multiplier-joint"]
    wild_multiplier["attributes"]["linked_symbol_domain"] = ["W"]
    unlinked_multiplier = clone(multiplier_nodes[1])
    unlinked_multiplier["node_id"] = "wild-unlinked-multiplier"
    unlinked_multiplier["semantic_event_set_ids"] = ["wild-unlinked-joint"]
    unlinked_multiplier["attributes"]["linked_symbol_domain"] = ["W"]
    wild = {
        "node_id": "wild-main", "mechanic_id": "modifier.wild-substitute", "name_zh": "Wild替代",
        "scope": "modifier:wild", "status": "必需", "semantic_event_set_ids": ["wild-multiplier-joint"],
        "attributes": {
            "wild_effect_id": "wild-effect-main", "effect_owner_node_id": "wild-main",
            "wild_symbol_domain": ["W"], "substitution_scope": "settlement", "eligible_target_domain": ["H1"],
            "resolution_priority": "before_pay", "assistance_resolution_rule": "逐中奖结果对照无Wild反事实",
            "incremental_payout_rule": "实际派奖减无Wild反事实派奖", "wild_effect_scope": "settlement_step",
            "linked_multiplier_id": "wild-linked-multiplier",
            "wild_multiplier_dependency_evidence": {
                "linked_multiplier_node_id": "wild-linked-multiplier",
                "shared_semantic_event_set_id": "wild-multiplier-joint",
                "wild_assistance_state_domain": ["none", "assisted"],
                "multiplier_state_domain": ["not_occurred", "not_applied", "1x", "2x"],
                "joint_observation_rule": "同一结算步骤联合记录Wild辅助状态与最终倍率状态",
            },
        },
        "evidence": ["profile.json"],
    }
    wild_multiplier_nodes = [wild, wild_multiplier, unlinked_multiplier]
    assert validate_profile_links(wild_multiplier_nodes) == []
    assert "interaction.wild-multiplier" in required_package_ids(wild_multiplier_nodes, catalog)
    wild_multiplier_errors = []
    wild_multiplier_expected, _, wild_multiplier_bindings = expected_metrics(
        wild_multiplier_nodes,
        [scope_stub(
            "wild-multiplier-joint", ["wild-main", "wild-linked-multiplier"],
            "eligible_joint_wild_multiplier_settlement_step", "wild-multiplier-joint",
            {"component": "base", "state": "normal", "settlement_type": "ways"},
        )],
        {"interaction.wild-multiplier"}, catalog, wild_multiplier_errors,
    )
    assert wild_multiplier_errors == [], wild_multiplier_errors
    wild_multiplier_instances = {
        item for item in wild_multiplier_expected if item[0] == "wild_multiplier.dependence_residual"
    }
    assert wild_multiplier_instances == {(
        "wild_multiplier.dependence_residual", ("wild-linked-multiplier", "wild-main"),
        (("component", "base"), ("settlement_type", "ways"), ("state", "normal")),
    )}
    assert wild_multiplier_bindings[next(iter(wild_multiplier_instances))]["scope_instance_id"] == "wild-multiplier-joint"

    bad_wild = clone(wild)
    bad_wild["attributes"]["linked_multiplier_id"] = "missing-multiplier"
    bad_wild["attributes"]["wild_multiplier_dependency_evidence"]["linked_multiplier_node_id"] = "missing-multiplier"
    assert any("玩法节点引用未知倍率节点" in error for error in validate_profile_links([bad_wild, wild_multiplier]))
    bad_wild = clone(wild)
    bad_wild["attributes"]["wild_multiplier_dependency_evidence"]["shared_semantic_event_set_id"] = "not-shared"
    assert any("Wild倍率专属依赖证据未绑定双方共享语义事件集" in error for error in validate_profile_links([bad_wild, wild_multiplier]))
    bad_wild = clone(wild)
    bad_wild["attributes"]["wild_multiplier_dependency_evidence"]["wild_assistance_state_domain"] = ["assisted"]
    assert any("Wild倍率专属依赖证据的Wild状态域必须唯一且包含none" in error for error in validate_profile_links([bad_wild, wild_multiplier]))
    for required_state in ("not_occurred", "not_applied", "1x"):
        bad_wild = clone(wild)
        states = bad_wild["attributes"]["wild_multiplier_dependency_evidence"]["multiplier_state_domain"]
        states.remove(required_state)
        assert any(
            "Wild倍率专属依赖证据的倍率状态域必须唯一且包含not_occurred、not_applied、1x" in error
            for error in validate_profile_links([bad_wild, wild_multiplier])
        )

    board = {
        "node_id": "board-main", "mechanic_id": "board.fixed-grid", "name_zh": "固定网格", "scope": "board:main",
        "status": "必需", "semantic_event_set_ids": ["board-entry", "board-cascade"],
        "attributes": {
            "reels": 5, "rows": 3, "valid_cell_definition": "5x3", "spatial_partitions": ["reel"],
            "symbol_role_map": {"H1": "high"}, "board_phase_domain": ["entry", "cascade"],
            "generation_model": "reel_strip", "generator_partitions": ["base-strip"], "stack_axis": "reel",
        },
        "evidence": ["profile.json"],
    }
    board_scopes = []
    for phase, event_id in (("entry", "board-entry"), ("cascade", "board-cascade")):
        dimensions = {"component": "base", "state": "normal", "board_phase": phase}
        board_scopes.append(scope_stub(f"board-{phase}", ["board-main"], "board_snapshot×declared_symbol", event_id, dimensions))
        board_scopes.append(scope_stub(f"board-draw-{phase}", ["board-main"], "ordered_pair_of_generator_draws", event_id, dict(dimensions, generator_partition="base-strip")))
    board_expected, _, _ = expected_metrics([board], board_scopes, required_package_ids([board], catalog), catalog, [])
    board_instances = {item for item in board_expected if item[0] == "board.symbol_count_per_board_distribution"}
    board_phases = {dict(dimensions)["board_phase"] for _, _, dimensions in board_instances}
    assert board_phases == {"entry", "cascade"}
    entry_only = {item for item in board_instances if dict(item[2]).get("board_phase") == "entry"}
    assert any(dict(dimensions).get("board_phase") == "cascade" for _, _, dimensions in board_instances - entry_only)

    cascade = {
        "node_id": "cascade", "mechanic_id": "evolution.cascade", "semantic_event_set_ids": ["cascade-multiplier"],
        "attributes": {
            "continuation_condition": "win", "resolved_cell_rule": "remove", "refill_rule": "gravity",
            "max_steps_policy": "until_no_win", "effective_capacity_definition": "visible_cells",
            "step_multiplier_rule": "同一深度可随机出现多个倍率状态",
            "same_depth_multiplier_randomness": True,
            "dependency_evidence": "sealed-dependence.json",
        },
    }
    linked_multiplier = clone(multiplier_nodes[0])
    linked_multiplier["semantic_event_set_ids"] = ["cascade-multiplier"]
    linked_multiplier["attributes"].update({
        "progression_driver": "cascade_depth",
        "cascade_node_id": "cascade",
        "same_depth_multiplier_randomness": True,
        "progression_rule": "按Cascade深度选择倍率状态",
        "reset_rule": "每个付费入口结束后重置",
        "cap_rule": "受value_domain上限约束",
        "state_to_effective_multiplier_rule": "由深度和该深度随机结果共同确定最终倍率",
        "dependency_evidence": "sealed-dependence.json",
    })
    assert "interaction.cascade-multiplier" in required_package_ids([cascade, linked_multiplier], catalog)
    assert validate_profile_links([cascade, linked_multiplier]) == []

    mismatched_cascade_multiplier = clone(linked_multiplier)
    mismatched_cascade_multiplier["attributes"]["same_depth_multiplier_randomness"] = False
    assert any(
        "同深度倍率随机性声明不一致" in error
        for error in validate_profile_links([cascade, mismatched_cascade_multiplier])
    )
    missing_dependency_cascade = clone(cascade)
    missing_dependency_cascade["attributes"].pop("dependency_evidence")
    missing_dependency_multiplier = clone(linked_multiplier)
    missing_dependency_multiplier["attributes"].pop("dependency_evidence")
    assert any(
        "同深度倍率仍随机时缺少Cascade倍率依赖证据" in error
        for error in validate_profile_links([missing_dependency_cascade, missing_dependency_multiplier])
    )

    deterministic_cascade = clone(cascade)
    deterministic_cascade["attributes"].update({
        "step_multiplier_rule": "深度到倍率出现、应用和最终值唯一映射",
        "same_depth_multiplier_randomness": False,
    })
    deterministic_multiplier = clone(linked_multiplier)
    deterministic_multiplier["attributes"].update({
        "same_depth_multiplier_randomness": False,
        "state_to_effective_multiplier_rule": "每个Cascade深度唯一确定倍率出现、应用与最终值",
    })
    assert validate_profile_links([deterministic_cascade, deterministic_multiplier]) == []
    for metric_id, source_ids in (
        ("multiplier.occurrence_rate", [deterministic_multiplier["node_id"]]),
        ("multiplier.application_rate_given_occurrence", [deterministic_multiplier["node_id"]]),
        ("multiplier.effective_value_distribution", [deterministic_multiplier["node_id"]]),
        ("cascade_multiplier.dependence_by_depth", ["cascade", deterministic_multiplier["node_id"]]),
    ):
        derived_item = {
            "metric_id": metric_id,
            "status": "不适用",
            "inapplicability_reason_code": "deterministically_derived_from_primary",
            "source_node_ids": source_ids,
        }
        assert validate_cascade_multiplier_ownership(
            derived_item, [deterministic_cascade, deterministic_multiplier]
        ) == []
        duplicate_owner_item = clone(derived_item)
        duplicate_owner_item.update({"status": "适用"})
        duplicate_owner_item.pop("inapplicability_reason_code")
        assert any(
            "必须由深度分布派生且不重复计分" in error
            for error in validate_cascade_multiplier_ownership(
                duplicate_owner_item, [deterministic_cascade, deterministic_multiplier]
            )
        )
    random_residual_derived = {
        "metric_id": "cascade_multiplier.dependence_by_depth",
        "status": "不适用",
        "inapplicability_reason_code": "deterministically_derived_from_primary",
        "source_node_ids": ["cascade", linked_multiplier["node_id"]],
    }
    assert any(
        "仍有倍率随机性时不得把依赖残差声明为深度确定性派生" in error
        for error in validate_cascade_multiplier_ownership(random_residual_derived, [cascade, linked_multiplier])
    )

    payline = {
        "node_id": "line", "mechanic_id": "settlement.payline", "name_zh": "固定线结算", "scope": "settlement:line",
        "status": "必需", "semantic_event_set_ids": ["line-event"],
        "attributes": {
            "line_count": 1, "line_definitions": [{"line_id": "L1", "coordinates": [[0, 0], [0, 0], [2, 0]]}],
            "direction": "left_to_right", "min_reels": 3, "aggregation_unit": "per_line", "winning_scale_dimension": "matched_reel_count",
        },
        "evidence": ["profile.json"],
    }
    payline_errors, _, _ = validate_profile({"mechanics": [payline], "required_node_count": 1, "gaps": [], "semantic_gap_count": 0}, catalog)
    assert any("每轴至多一个合法reel/row坐标" in error for error in payline_errors)
    duplicate_payline = clone(payline)
    duplicate_payline["attributes"].update({
        "line_count": 2,
        "line_definitions": [
            {"line_id": "L1", "coordinates": [[0, 0], [1, 1], [2, 0]]},
            {"line_id": "L2", "coordinates": [[2, 0], [1, 1], [0, 0]]},
        ],
    })
    duplicate_payline_errors, _, _ = validate_profile(
        {"mechanics": [duplicate_payline], "required_node_count": 1, "gaps": [], "semantic_gap_count": 0}, catalog
    )
    assert any("重复规范几何路径" in error for error in duplicate_payline_errors)
    progressing_multiplier = clone(multiplier_nodes[0])
    progressing_multiplier["attributes"]["progression_driver"] = "persistent_state"
    progression_errors, _, _ = validate_profile({"mechanics": [progressing_multiplier], "required_node_count": 1, "gaps": [], "semantic_gap_count": 0}, catalog)
    assert any("倍率递进缺少条件必需属性" in error for error in progression_errors)
    assert any("持久状态驱动倍率缺少progression_state_id" in error for error in progression_errors)

    ordered_metric = clone(catalog["metrics"]["multiplier.effective_value_distribution"])
    ordered_metric.update({"target": {"2x": 0.5, "3x": 0.5}})
    ordered_metric["score_profile"]["bin_positions"] = [2, 2]
    assert any("唯一且严格递增" in error for error in validate_metric_target(ordered_metric))
    ordered_metric["score_profile"]["bin_positions"] = [3, 2]
    assert any("唯一且严格递增" in error for error in validate_metric_target(ordered_metric))
    grouped_metric = clone(catalog["metrics"]["feature_cycle.return_distribution_by_stage_path"])
    grouped_metric.update({"target": {"路径A::0x": 0.5, "路径A::正回报": 0.5}})
    grouped_metric["score_profile"].update({"group_weights": {"路径A": 1.0}, "bin_positions_by_group": {"路径A": {"0x": 0}}})
    assert any("目标标签与位置键必须完全一致" in error for error in validate_metric_target(grouped_metric))
    invalid_audit = clone(catalog["metrics"]["core.max_win.audit"])
    invalid_audit["target"] = {"theoretical_max": 5000, "cap": 5000, "overflow_rule_status": "大概符合"}
    assert any("无效审计状态字段" in error for error in validate_metric_target(invalid_audit))
    blocking_audit = clone(catalog["metrics"]["jackpot.rule_consistency.audit"])
    audit_fields = blocking_audit["display"]["object_labels"]
    blocking_audit["target"] = {field: "符合" for field in audit_fields}
    blocking_audit["target"]["trigger_rule_status"] = "不符合"
    blocking_errors = validate_metric_target(blocking_audit)
    assert blocking_errors and any("不符合" in error or "阻塞审计" in error for error in blocking_errors)

    stage = {
        "metric_id": "feature_cycle.stage_path_distribution", "status": "适用", "source_node_ids": ["free-spin-main"],
        "instance_dimensions": {"entry_source": "natural"}, "target": {"标准路径": 0.7, "重触发路径": 0.3},
        "sealed_event_set_id": "feature-natural", "sealed_event_set_path": "evidence/events/feature-natural.json",
        "sealed_event_set_sha256": "b" * 64, "sealed_event_count": 2,
    }
    path_return = {
        "metric_id": "feature_cycle.return_distribution_by_stage_path", "status": "适用", "source_node_ids": ["free-spin-main"],
        "instance_dimensions": {"entry_source": "natural"}, "return_denominator": "triggering_paid_bet",
        "target": {"标准路径::0x": 0.2, "标准路径::1-10x": 0.8, "重触发路径::0x": 0.1, "重触发路径::1-10x": 0.9},
        "score_profile": {
            "group_separator": "::", "normalization_tolerance": 1e-6,
            "group_weights": {"标准路径": 0.7, "重触发路径": 0.3},
            "bin_positions_by_group": {"标准路径": {"0x": 0, "1-10x": 5}, "重触发路径": {"0x": 0, "1-10x": 5}},
            "bin_boundaries_by_group": {
                "标准路径": {"0x": {"lower": 0, "upper": 0}, "1-10x": {"lower": 0.000001, "upper": 10}},
                "重触发路径": {"0x": {"lower": 0, "upper": 0}, "1-10x": {"lower": 0.000001, "upper": 10}},
            },
        },
        "sealed_event_set_id": "feature-natural", "sealed_event_set_path": "evidence/events/feature-natural.json",
        "sealed_event_set_sha256": "b" * 64, "sealed_event_count": 2,
    }
    feature_marginal = {
        "metric_id": "feature_cycle.return_distribution", "status": "适用", "source_node_ids": ["free-spin-main"],
        "instance_dimensions": {"entry_source": "natural"},
        "target": {"0x": 0.7 * 0.2 + 0.3 * 0.1, "1-10x": 0.7 * 0.8 + 0.3 * 0.9},
    }
    feature_zero = {
        "metric_id": "feature_cycle.zero_return_rate", "status": "适用", "source_node_ids": ["free-spin-main"],
        "instance_dimensions": {"entry_source": "natural"}, "target": 0.17,
    }
    feature_median = {
        "metric_id": "feature_cycle.median_return", "status": "适用", "source_node_ids": ["free-spin-main"],
        "instance_dimensions": {"entry_source": "natural"}, "target": "1-10x",
    }
    path_items = [stage, path_return, feature_marginal, feature_zero, feature_median]
    path_map = {(item["metric_id"], ("free-spin-main",), (("entry_source", "natural"),)): item for item in path_items}
    assert validate_feature_return_zero_bucket(path_return) == []
    path_errors = {item["metric_id"]: validate_feature_path_contract(item, path_map) for item in path_items[1:]}
    assert all(not errors for errors in path_errors.values()), path_errors
    missing_zero = clone(path_return)
    missing_zero["target"].pop("标准路径::0x")
    missing_zero["score_profile"]["bin_positions_by_group"]["标准路径"].pop("0x")
    missing_zero["score_profile"]["bin_boundaries_by_group"]["标准路径"].pop("0x")
    assert any("缺少独立精确0x桶" in error for error in validate_feature_return_zero_bucket(missing_zero))
    wrong_path = clone(stage)
    wrong_path["target"] = {"其他路径": 1.0}
    wrong_path_map = dict(path_map)
    wrong_path_map[(stage["metric_id"], ("free-spin-main",), (("entry_source", "natural"),))] = wrong_path
    assert any("支持集完全一致" in error for error in validate_feature_path_contract(path_return, wrong_path_map))
    wrong_weight = clone(path_return)
    wrong_weight["score_profile"]["group_weights"] = {"标准路径": 0.5, "重触发路径": 0.5}
    wrong_weight_map = dict(path_map)
    wrong_weight_map[(path_return["metric_id"], ("free-spin-main",), (("entry_source", "natural"),))] = wrong_weight
    assert any("逐项等于" in error for error in validate_feature_path_contract(wrong_weight, wrong_weight_map))
    wrong_path_binding = clone(path_return)
    wrong_path_binding["sealed_event_set_path"] = "evidence/events/other-feature.json"
    wrong_binding_map = dict(path_map)
    wrong_binding_map[(path_return["metric_id"], ("free-spin-main",), (("entry_source", "natural"),))] = wrong_path_binding
    assert any("必须绑定同一密封事件集" in error for error in validate_feature_path_contract(wrong_path_binding, wrong_binding_map))
    wrong_zero = clone(feature_zero)
    wrong_zero["target"] = 0.18
    assert any("零回报率目标" in error for error in validate_feature_path_contract(wrong_zero, path_map))

    buy_event_path = base / "feature-buy-events.json"
    buy_events = {"events": [
        {"event_id": "buy-1", "stage_path_id": "标准路径", "feature_total_win": 0, "actual_purchase_cost": 100, "normal_base_bet": 1, "entry_source": "feature_buy"},
        {"event_id": "buy-2", "stage_path_id": "重触发路径", "feature_total_win": 10, "actual_purchase_cost": 100, "normal_base_bet": 1, "entry_source": "feature_buy"},
    ]}
    dump(buy_event_path, buy_events)
    buy_hash = semantic_sha(buy_event_path)
    buy_node = clone(free_spin)
    buy_node["attributes"]["entry_sources"] = ["feature_buy"]
    buy_primary = clone(path_return)
    buy_primary.update({
        "instance_dimensions": {"entry_source": "feature_buy"}, "return_denominator": "actual_purchase_cost",
        "target": {"标准路径::0x": 1.0, "标准路径::1-10x": 0.0, "重触发路径::0x": 0.0, "重触发路径::1-10x": 1.0},
        "sealed_event_set_id": "fs-buy", "sealed_event_set_path": buy_event_path.name,
        "sealed_event_set_sha256": buy_hash, "sealed_event_count": 2,
    })
    buy_primary["score_profile"]["group_weights"] = {"标准路径": 0.5, "重触发路径": 0.5}
    buy_stage = clone(stage)
    buy_stage.update({
        "instance_dimensions": {"entry_source": "feature_buy"}, "target": {"标准路径": 0.5, "重触发路径": 0.5},
        "sealed_event_set_id": "fs-buy", "sealed_event_set_path": buy_event_path.name,
        "sealed_event_set_sha256": buy_hash, "sealed_event_count": 2,
    })
    buy_item = {
        "metric_id": "feature_cycle.base_bet_equivalent_return_distribution", "status": "适用",
        "source_node_ids": ["free-spin-main"], "instance_dimensions": {"entry_source": "feature_buy"},
        "target": {"0x": 0.5, "1-20x": 0.5},
        "event_recomputation_contract": {
            "sealed_event_set_id": "fs-buy", "sealed_event_set_path": buy_event_path.name,
            "sealed_event_set_sha256": buy_hash, "event_count": 2,
            "event_id_field": "event_id", "feature_total_win_field": "feature_total_win",
            "actual_purchase_cost_field": "actual_purchase_cost", "normal_base_bet_field": "normal_base_bet",
            "entry_source_field": "entry_source", "entry_source_value": "feature_buy",
            "base_bet_equivalent_bins": {"0x": {"lower": 0, "upper": 0}, "1-20x": {"lower": 0.000001, "upper": 20}},
        },
    }
    buy_map = {
        ("feature_cycle.return_distribution_by_stage_path", ("free-spin-main",), (("entry_source", "feature_buy"),)): buy_primary,
        ("feature_cycle.stage_path_distribution", ("free-spin-main",), (("entry_source", "feature_buy"),)): buy_stage,
    }
    buy_errors = validate_feature_buy_contract(buy_item, [buy_node], buy_map, base.resolve())
    assert buy_errors == [], buy_errors
    bad_buy_binding = clone(buy_item)
    bad_buy_binding["event_recomputation_contract"]["sealed_event_set_id"] = "other"
    assert any("未绑定同一事件ID、路径、hash和事件数" in error for error in validate_feature_buy_contract(bad_buy_binding, [buy_node], buy_map, base.resolve()))
    missing_buy_field = clone(buy_events)
    missing_buy_field["events"][0].pop("normal_base_bet")
    dump(buy_event_path, missing_buy_field)
    assert any("逐事件重算失败" in error for error in validate_feature_buy_contract(buy_item, [buy_node], buy_map, base.resolve()))
    dump(buy_event_path, buy_events)
    wrong_entry_source = clone(buy_events)
    wrong_entry_source["events"][0]["entry_source"] = "natural"
    dump(buy_event_path, wrong_entry_source)
    assert any("entry_source不是feature_buy" in error for error in validate_feature_buy_contract(buy_item, [buy_node], buy_map, base.resolve()))
    dump(buy_event_path, buy_events)

    jackpot_evidence_path = base / "jackpot-fixed-evidence.json"
    jackpot_claim = {"deterministic_per_tier": True, "value_model": "fixed_by_tier"}
    dump(jackpot_evidence_path, {"claims": {"fixed": jackpot_claim}})
    jackpot_hash = semantic_sha(jackpot_evidence_path)
    jackpot_node = {
        "node_id": "jackpot", "mechanic_id": "award.jackpot", "semantic_event_set_ids": ["jackpot-event"],
        "attributes": {"tier_domain": ["MINI"], "trigger_rule": "fixed", "value_model": "fixed_by_tier", "payout_scope": "feature", "reset_rule": "none"},
    }
    jackpot_item = clone(catalog["metrics"]["jackpot.award_value_distribution_by_tier"])
    jackpot_item.update({
        "scope": "award:jackpot|mode=base", "source_node_ids": ["jackpot"], "instance_dimensions": {"mode": "base"},
        "status": "不适用", "target": {"MINI": 100}, "inapplicability_reason_code": "deterministic_rule_result",
        "inapplicability_evidence": [{
            "evidence_path": jackpot_evidence_path.name, "evidence_sha256": jackpot_hash,
            "json_pointer": "/claims/fixed", "expected_value": jackpot_claim,
        }],
    })
    jackpot_manifest = {"hashes": {jackpot_evidence_path.name: jackpot_hash}}
    assert validate_inapplicability(jackpot_item, [jackpot_node], {}, catalog, base.resolve(), jackpot_manifest) == []
    bad_pointer = clone(jackpot_item)
    bad_pointer["inapplicability_evidence"][0]["expected_value"] = {"deterministic_per_tier": False, "value_model": "fixed_by_tier"}
    assert any("JSON Pointer值不一致" in error for error in validate_inapplicability(bad_pointer, [jackpot_node], {}, catalog, base.resolve(), jackpot_manifest))


def tolerance_policy_case(base):
    contract = {
        "schema_version": "1.0", "task_id": "policy-test", "input_hashes": {}, "group_weights": {"experience": 1},
        "metrics": [
            {"metric_id": "core.rtp.total", "name_zh": "总RTP", "owner": "core.general", "kind": "hard", "scope": "base", "target": 0.96, "hard_gate_profile": {"method": "absolute_error", "tolerance": 0.002}},
            {"metric_id": "core.return_distribution.lt200", "name_zh": "200x以下付费入口回报分布", "owner": "core.general", "kind": "hard", "scope": "base", "target": [1.0, 0.0], "hard_gate_profile": {"method": "total_variation", "tolerance": 0.01}},
            {"metric_id": "demo.a", "name_zh": "体验A", "owner": "demo", "kind": "score", "scope": "base", "target": 0.10, "score_group": "experience", "weight": 1.0, "score_profile": {"method": "absolute_error", "anchors": [[0,100],[0.01,85],[0.10,0]]}}
        ]
    }
    measurements = {"measurements": [
        {"metric_id": "core.rtp.total", "scope": "base", "status": "有效", "value": 0.959},
        {"metric_id": "core.return_distribution.lt200", "scope": "base", "status": "有效", "value": [0.964, 0.036]},
        {"metric_id": "demo.a", "scope": "base", "status": "有效", "value": 0.10}
    ]}
    dump(base / "base-contract.json", contract)
    dump(base / "measurements.json", measurements)
    run(ROOT / "apply_hard_gate_tolerance_policy.py", "--contract", base / "base-contract.json", "--policy", SKILL_ROOT / "assets/policies/hard_gate_tolerance_policy.v2.json", "--output", base / "contract.json")
    run(ROOT / "score_alignment.py", "--contract", base / "contract.json", "--measurements", base / "measurements.json", "--output", base / "scorecard.json")
    scorecard = json.loads((base / "scorecard.json").read_text(encoding="utf-8"))
    tampered = json.loads((base / "contract.json").read_text(encoding="utf-8"))
    tv = next(item for item in tampered["metrics"] if item["metric_id"] == "core.return_distribution.lt200")
    tv["hard_gate_profile"]["tolerance"] = 0.041
    dump(base / "tampered-contract.json", tampered)
    invalid = run_result(ROOT / "score_alignment.py", "--contract", base / "tampered-contract.json", "--measurements", base / "measurements.json", "--output", base / "tampered-scorecard.json")
    assert invalid.returncode == 2
    return scorecard


def component_rtp_target_case(base):
    source = {
        "authoritative_total_rtp_target": {"min": 0.95, "max": 0.96},
        "components": [
            {"scope": "base", "original_component_share": 0.25, "source_evidence": "original.json#base"},
            {"scope": "feature:free-spin", "original_component_share": 0.75, "source_evidence": "original.json#feature"}
        ]
    }
    dump(base / "shares.json", source)
    run(ROOT / "derive_component_rtp_targets.py", "--input", base / "shares.json", "--output", base / "targets.json")
    result = json.loads((base / "targets.json").read_text(encoding="utf-8"))
    assert result["original_absolute_rtp_as_target"] is False
    assert abs(result["components"][0]["target"]["min"] - 0.2375) < 1e-12
    assert abs(result["components"][0]["target"]["max"] - 0.24) < 1e-12
    assert abs(result["components"][1]["target"]["min"] - 0.7125) < 1e-12
    assert abs(result["components"][1]["target"]["max"] - 0.72) < 1e-12
    contract = {
        "scope": {"target_rtp": {"min": 0.95, "max": 0.96}},
        "component_rtp_target_policy": {
            "method": "original_component_share_mapped_to_authoritative_total_rtp",
            "original_absolute_rtp_as_target": False,
            "authoritative_total_rtp_required": True,
            "share_sum_target": 1.0,
            "legacy_contracts_unchanged": True
        },
        "metrics": [dict(item, kind="hard", status="适用") for item in result["components"]]
    }
    assert validate_component_rtp_targets(contract) == []
    contract["metrics"][0]["target"] = {"min": 0.24, "max": 0.25}
    assert "组件RTP目标未按贡献占比映射: base" in validate_component_rtp_targets(contract)
    legacy = {"schema_version": "1.0", "scope": contract["scope"], "metrics": contract["metrics"]}
    assert validate_component_rtp_targets(legacy) == []
    invalid = dict(source)
    invalid["components"] = [dict(source["components"][0]), dict(source["components"][1])]
    invalid["components"][1]["original_component_share"] = 0.70
    dump(base / "invalid-shares.json", invalid)
    failed = run_result(ROOT / "derive_component_rtp_targets.py", "--input", base / "invalid-shares.json", "--output", base / "invalid-targets.json")
    assert failed.returncode == 2
    return result


def main():
    assert detail_rows({"min": 0.95, "max": 0.96, "distribution": [0.8, 0.2]}, "目标") == [
        ["目标.distribution[1]", 0.8],
        ["目标.distribution[2]", 0.2],
        ["目标.max", 0.96],
        ["目标.min", 0.95],
    ]
    for invalid_manifest in ({}, {"report_contract_version": ""}):
        try:
            delivery_report_contract_version(invalid_manifest)
            raise AssertionError("缺失报告合同版本未阻塞交付")
        except ValueError as exc:
            assert "缺少显式report_contract_version" in str(exc)
    assert delivery_report_contract_version({"report_contract_version": "slot-alignment.reports.v2.6"}) == "slot-alignment.reports.v2.6"
    assert delivery_report_contract_version({"report_contract_version": "slot-alignment.reports.v2.7"}) == "slot-alignment.reports.v2.7"
    assert delivery_report_contract_version({"report_contract_version": "slot-alignment.reports.v2.8"}) == "slot-alignment.reports.v2.8"
    assert delivery_report_contract_version({"report_contract_version": "slot-alignment.reports.v2.9"}) == "slot-alignment.reports.v2.9"
    assert abs(distance("mean_absolute_error", [0.2, 0.8], [0.3, 0.7]) - 0.1) < 1e-12
    assert abs(distance("max_absolute_error", {"a": 0.2, "b": 0.8}, {"a": 0.25, "b": 0.7}) - 0.1) < 1e-12
    for zero_floor in (0, -1, float("nan"), float("inf")):
        try:
            distance("relative_error", 0, 1, zero_floor=zero_floor)
            raise AssertionError("非法relative_error.zero_floor未阻塞")
        except ValueError:
            pass
    assert_distance_error("range_error", {"min": 2, "max": 1}, 1.5, {}, "min不能大于max")
    for profile, expected in (
        ({"anchors": [[0, 100], [float("nan"), 0]]}, "有限数值"),
        ({"anchors": [[0, 100], [1, float("inf")]]}, "有限数值"),
        ({"anchors": [[0, 100], [0, 0]]}, "严格递增"),
        ({"anchors": [[0, 100], [1, 100]]}, "严格递减"),
        ({"anchors": [[0, 100], [1, -1]]}, "0至100"),
        ({"anchors": [[0.1, 100], [1, 0]]}, "首点"),
    ):
        assert_anchor_error(profile, expected)
    active_distribution = {
        "target": [1.0],
        "score_profile": {"method": "total_variation", "reachable_support_source": "task_contract", "reachable_support_status": "active"},
    }
    try:
        validate_reachable_support(active_distribution)
        raise AssertionError("单项有效支持未阻塞")
    except ValueError as exc:
        assert "至少需要2项" in str(exc)
    grouped_active = {
        "target": {"A::唯一": 1.0, "B::低": 0.5, "B::高": 0.5},
        "score_profile": {"method": "grouped_total_variation", "reachable_support_source": "task_contract", "reachable_support_status": "active", "group_separator": "::", "group_weight_source": "task_contract", "normalization_tolerance": 1e-6, "group_weights": {"A": 0.5, "B": 0.5}},
    }
    try:
        validate_reachable_support(grouped_active)
        raise AssertionError("退化条件组未阻塞")
    except ValueError as exc:
        assert "活动组" in str(exc) and "A" in str(exc)
    grouped_active["target"] = {"B::低": 0.5, "B::高": 0.5}
    grouped_active["score_profile"]["group_weights"] = {"B": 1.0}
    validate_reachable_support(grouped_active)
    assert abs(distance("wasserstein_1d", [1, 0, 0], [0, 1, 0], profile={"bin_positions": [0, 1, 2]}) - 0.5) < 1e-12
    grouped_wasserstein_profile = {
        "bin_positions_source": "task_contract",
        "distance_normalization": "sealed_support_span",
        "group_separator": "::",
        "group_weight_source": "task_contract",
        "normalization_tolerance": 1e-6,
        "bin_positions_by_group": {
            "A": {"低": 0, "中": 1, "高": 2},
            "B": {"低": 0, "高": 2},
        },
        "group_weights": {"A": 0.75, "B": 0.25},
    }
    grouped_wasserstein_target = {"A::低": 1, "A::中": 0, "A::高": 0, "B::低": 1, "B::高": 0}
    grouped_wasserstein_value = {"A::低": 0, "A::中": 1, "A::高": 0, "B::低": 0, "B::高": 1}
    assert abs(distance("grouped_wasserstein_1d", grouped_wasserstein_target, grouped_wasserstein_value, profile=grouped_wasserstein_profile) - 0.625) < 1e-12
    ordered_group_profile = {
        "bin_positions_source": "task_contract",
        "distance_normalization": "sealed_support_span",
        "group_separator": "::",
        "group_weight_source": "task_contract",
        "normalization_tolerance": 1e-6,
        "bin_positions_by_group": {"G": {"低": 0, "中": 1, "高": 3}},
        "group_weights": {"G": 1},
    }
    ordered_group_target = {"G::低": 1, "G::中": 0, "G::高": 0}
    adjacent_distance = distance(
        "grouped_wasserstein_1d",
        ordered_group_target,
        {"G::低": 0, "G::中": 1, "G::高": 0},
        profile=ordered_group_profile,
    )
    distant_distance = distance(
        "grouped_wasserstein_1d",
        ordered_group_target,
        {"G::低": 0, "G::中": 0, "G::高": 1},
        profile=ordered_group_profile,
    )
    assert abs(adjacent_distance - 1 / 3) < 1e-12 and abs(distant_distance - 1) < 1e-12
    assert distant_distance > adjacent_distance
    assert_distance_error(
        "grouped_wasserstein_1d",
        ordered_group_target,
        {"G::低": 0, "G::中": 1, "G::高": 0},
        dict(ordered_group_profile, bin_positions_by_group={"G": {"低": 0, "中": 0, "高": 3}}),
        "严格递增",
    )
    assert_distance_error(
        "grouped_wasserstein_1d",
        ordered_group_target,
        {"G::低": 0, "G::中": 1, "G::高": 0},
        dict(ordered_group_profile, bin_positions_by_group={"G": {"低": 0, "中": 1}}),
        "完全一致",
    )
    assert_distance_error(
        "grouped_wasserstein_1d",
        ordered_group_target,
        {"G::低": 0, "G::中": 1, "G::高": 0},
        dict(ordered_group_profile, bin_positions_by_group={"G": {"低": 0, "中": "非法", "高": 3}}),
        "有限数值",
    )
    assert_distance_error(
        "grouped_wasserstein_1d",
        {"G::低": 0.8, "G::中": 0.1, "G::高": 0},
        {"G::低": 0, "G::中": 1, "G::高": 0},
        ordered_group_profile,
        "未归一化",
    )
    assert_distance_error(
        "grouped_wasserstein_1d",
        ordered_group_target,
        {"G::低": -0.1, "G::中": 1.1, "G::高": 0},
        ordered_group_profile,
        "负数",
    )
    for invalid_weights, expected in (
        ({}, "完全一致"),
        ({"G": -1}, "有限正数"),
        ({"G": 0}, "有限正数"),
        ({"G": float("nan")}, "有限数值"),
        ({"G": 0.9}, "未归一化"),
    ):
        assert_distance_error(
            "grouped_wasserstein_1d",
            ordered_group_target,
            {"G::低": 0, "G::中": 1, "G::高": 0},
            dict(ordered_group_profile, group_weights=invalid_weights),
            expected,
        )
    for method, target, candidate, profile in (
        ("total_variation", [0, 0], [0, 0], {}),
        ("wasserstein_1d", [0, 0], [0, 0], {"bin_positions": [0, 1]}),
        ("grouped_total_variation", {"A::低": 0, "A::高": 0}, {"A::低": 0, "A::高": 0}, {"group_separator": "::", "group_weight_source": "task_contract", "normalization_tolerance": 1e-6, "group_weights": {"A": 1}}),
    ):
        try:
            distance(method, target, candidate, profile=profile)
            raise AssertionError(f"{method}全零分布未阻塞")
        except ValueError as exc:
            assert "大于0" in str(exc)
    try:
        distance("wasserstein_1d", [1, 0, 0], [0, 1, 0], profile={"bin_positions": [0, 1, 2], "distance_normalization": "非法值"})
        raise AssertionError("无效Wasserstein归一声明未阻塞")
    except ValueError as exc:
        assert "不支持的距离归一化" in str(exc)
    catalog_profile_errors = []
    validate_score_profile(
        "demo.grouped",
        {
            "method": "grouped_wasserstein_1d",
            "anchors": [[0, 100], [1, 0]],
            "bin_positions_source": "task_contract",
            "distance_normalization": "sealed_support_span",
            "group_separator": "::",
            "normalization_tolerance": 1e-6,
        },
        catalog_profile_errors,
    )
    assert any("密封组权重" in error for error in catalog_profile_errors)
    assert condition_implies(
        {"mechanic_id_all": ["board.variable-grid", "settlement.ways"]},
        {"mechanic_id": "board.variable-grid"},
    )
    assert not condition_implies(
        {"mechanic_id_any": ["board.variable-grid", "settlement.ways"]},
        {"mechanic_id": "board.variable-grid"},
    )
    semantic_errors = []
    validate_relationships(
        {
            "demo.primary-a": {
                "kind": "score",
                "owner": "demo.a",
                "semantic_variable_id": "demo.same-variable",
                "semantic_role": "primary",
                "relationships": {"derived_from": [], "cross_checks_with": []},
            },
            "demo.primary-b": {
                "kind": "score",
                "owner": "demo.a",
                "semantic_variable_id": "demo.same-variable",
                "semantic_role": "primary",
                "relationships": {"derived_from": [], "cross_checks_with": []},
            },
            "demo.derived": {
                "kind": "audit",
                "owner": "demo.a",
                "semantic_variable_id": "demo.derived-variable",
                "semantic_role": "derived_diagnostic",
                "relationships": {"derived_from": [], "cross_checks_with": []},
            },
        },
        semantic_errors,
    )
    assert any("多个primary指标" in error for error in semantic_errors)
    assert any("derived_diagnostic缺少" in error for error in semantic_errors)
    grouped_target = {"H1::0个": 0.4, "H1::1个以上": 0.6, "H2::0个": 0.7, "H2::1个以上": 0.3}
    grouped_value = {"H1::0个": 0.5, "H1::1个以上": 0.5, "H2::0个": 0.6, "H2::1个以上": 0.4}
    assert abs(distance("grouped_total_variation", grouped_target, grouped_value, profile={"group_separator": "::", "group_weight_source": "task_contract", "normalization_tolerance": 1e-6, "group_weights": {"H1": 0.5, "H2": 0.5}}) - 0.1) < 1e-12
    grouped_metric = {
        "metric_id": "board.symbol_count_per_board_distribution",
        "kind": "score",
        "unit": "probability",
        "target": grouped_target,
        "display": {
            "display_unit": "%（条件盘面占比）",
            "object_labels": {name: name.replace("::", "：") for name in grouped_target},
        },
    }
    grouped_table = metric_stage2_table(grouped_metric)
    assert "H1：0个" in grouped_table and "40" in grouped_table and "{" not in grouped_table
    joint_contract = apply_metric_display_metadata({"metrics": [{"metric_id": "cascade_multiplier.joint_distribution", "scope": "feature", "kind": "score", "unit": "distribution", "target": [0.6, 0.4]}]}, {"metrics": [{"metric_id": "cascade_multiplier.joint_distribution", "scope": "feature", "item_labels": ["Cascade深度1 × 实际倍率1x", "Cascade深度1 × 实际倍率2x"]}]})
    assert metric_item_labels(joint_contract["metrics"][0], 2) == ["Cascade深度1 × 实际倍率1x", "Cascade深度1 × 实际倍率2x"]
    joint_table = metric_stage2_table(joint_contract["metrics"][0])
    assert "联合桶" not in joint_table and "60" in joint_table and "%（样本占比）" in joint_table
    assert validate_templates(SKILL_ROOT) == []
    stage1_template = (SKILL_ROOT / TEMPLATE_PATHS[1]).read_text(encoding="utf-8")
    missing_example = stage1_template.replace("- 展示实例：", "- 实例已删除：", 1)
    assert any("缺少展示契约标记 展示实例" in error for error in validate_template_text(missing_example, 1))
    mainstream_chain_metric_case()
    position_semantic_contract_case()
    transform_target_coherence_case()
    conditional_group_weight_binding_case()
    hold_spin_capacity_contract_case()
    derivation_projection_case()
    mode_and_owner_semantic_contract_case()
    catalog_semantic_contract_case()
    root = Path(tempfile.mkdtemp(prefix="slot-alignment-self-test-"))
    contract_io_case(root / "contract-io")
    preflight_input_confirmation_case(root / "preflight-input-confirmation")
    step_return_owner_partition_case(root / "step-return-owner-partition")
    sample_capability_case(root / "sample-capability")
    semantic_contract_gate_case(root / "semantic-contract-gate")
    instance_compiler_case(root / "semantic-contract-gate")
    full_catalog_matrix_case(root / "full-catalog-matrix")
    degenerate_support_case(root / "degenerate-support")
    audit_gate_case(root / "audit-gate")
    catalog_summary_case(root / "catalog-copy")
    normal = score_case(root / "normal")
    budgeted = score_budget_case(root / "budgeted")
    mismatched_process, mismatched_budget = rerun_budget_case(
        root / "budget-mismatched-group",
        lambda contract: (
            contract.update({"group_weights": {"feature_experience": 0.5, "modifier": 0.5}}),
            contract["metrics"][1].update({"score_group": "modifier"}),
        ),
    )
    nan_process, nan_weight = rerun_budget_case(
        root / "nan-weight",
        lambda contract: contract["metrics"][0].update({"weight": float("nan")}),
    )
    inf_scope_process, inf_scope_weight = rerun_budget_case(
        root / "inf-scope-weight",
        lambda contract: contract["metrics"][0].update({"scope_weight": float("inf")}),
    )
    inf_group_process, inf_group_weight = rerun_budget_case(
        root / "inf-group-weight",
        lambda contract: contract.update({"group_weights": {"feature_experience": float("-inf")}}),
    )
    missing_weight_process, missing_weight = rerun_budget_case(
        root / "missing-weight",
        lambda contract: contract["metrics"][0].pop("weight"),
    )
    missing_scope_process, missing_scope = rerun_budget_case(
        root / "missing-scope-weight",
        lambda contract: contract["metrics"][0].pop("scope_weight"),
    )
    missing_group_process, missing_group = rerun_budget_case(
        root / "missing-group-weights",
        lambda contract: contract.pop("group_weights"),
    )
    bad_group_sum_process, bad_group_sum = rerun_budget_case(
        root / "bad-group-weight-sum",
        lambda contract: contract.update({"group_weights": {"feature_experience": 0.9}}),
    )
    waived = score_case(root / "waived", waiver=True)
    failed = score_case(root / "failed", hard_fail=True)
    policy = tolerance_policy_case(root / "policy")
    component_targets = component_rtp_target_case(root / "component-targets")
    assert normal["alignment_status"] == "通过"
    assert len(budgeted["budget_scores"]) == 2
    assert {item["score_budget_key"]: item["scope_count"] for item in budgeted["budget_scores"]} == {"demo.a": 2, "demo.b": 1}
    assert abs(budgeted["groups"][0]["score"] - 92.5) < 1e-12
    assert budgeted["groups"][0]["budget_count"] == 2
    assert mismatched_process.returncode == 2
    assert mismatched_budget["status"] == "阻塞" and mismatched_budget["alignment_status"] == "无法判定"
    assert any("评分组、聚合方式或权重不一致" in item["reason"] for item in mismatched_budget["blocking_reasons"])
    for process, result in ((nan_process, nan_weight), (inf_scope_process, inf_scope_weight), (inf_group_process, inf_group_weight)):
        assert process.returncode == 2
        assert result["status"] == "阻塞" and result["alignment_status"] == "无法判定"
        assert result["overall_score"] is None or math.isfinite(result["overall_score"])
    for process, result, reason in (
        (missing_weight_process, missing_weight, "缺少已密封weight"),
        (missing_scope_process, missing_scope, "缺少已密封scope_weight"),
        (missing_group_process, missing_group, "group_weights必须与政策活动评分组完全一致"),
        (bad_group_sum_process, bad_group_sum, "权重不符合版本化政策"),
    ):
        assert process.returncode == 2
        assert result["status"] == "阻塞" and result["alignment_status"] == "无法判定"
        assert any(reason in item["reason"] for item in result["blocking_reasons"])
    assert waived["alignment_status"] == "豁免后通过"
    assert failed["alignment_status"] == "不通过"
    policy_gates = {item["metric_id"]: item for item in policy["hard_gates"]}
    assert policy_gates["core.rtp.total"]["tolerance_factor"] == 1.0
    assert policy_gates["core.return_distribution.lt200"]["base_tolerance"] == 0.01
    assert policy_gates["core.return_distribution.lt200"]["tolerance_factor"] == 4.0
    assert policy_gates["core.return_distribution.lt200"]["tolerance"] == 0.04
    assert policy_gates["core.return_distribution.lt200"]["status"] == "通过"
    artifacts = root / "artifacts"
    reports = root / "交付物/报告文档/rv0001"
    formal_runtime = root / "work/formal/fv0001/runtime"
    for rel in ("01-input-profile", "02-metric-matching", "03-scoring", "04-alignment"):
        (artifacts / rel).mkdir(parents=True, exist_ok=True)
    reports.mkdir(parents=True, exist_ok=True)
    formal_runtime.mkdir(parents=True, exist_ok=True)
    certification_sha = "a" * 64
    script_sha = "b" * 64
    dump(artifacts / "01-input-profile/input_manifest.json", {"schema_version": "1.1", "report_contract_version": "slot-alignment.reports.v2.6", "task_id": "self-test", "status": "已完成", "scope": {"game_code": "demo", "mode": "base", "rtp_group": 1, "target_rtp": 0.96}, "paths": {"simulation_script": "/tmp/demo_simulator.py"}, "hashes": {"simulation_script": script_sha}, "script_qualification": {"status": "通过", "certified_execution_path": "python", "certification_method": "user_direct", "user_certification": {"status": "通过", "certified_by": "user", "approved_at": "2026-01-01T00:00:00Z", "evidence_path": "user-approval.json", "evidence_sha256": certification_sha, "certified_script_sha256": script_sha, "certified_scope": ["RTP与派奖账本", "玩法状态与统计输出"]}, "evidence": []}})
    valid_input_manifest = json.loads((artifacts / "01-input-profile/input_manifest.json").read_text(encoding="utf-8"))
    assert validate_execution_qualification(valid_input_manifest) == []
    invalid_python_path = json.loads(json.dumps(valid_input_manifest))
    invalid_python_path["script_qualification"]["certified_execution_path"] = "kotlin"
    assert "用户认证的执行路径必须是Python" in validate_execution_qualification(invalid_python_path)
    missing_user_certification = json.loads(json.dumps(valid_input_manifest))
    missing_user_certification["script_qualification"]["user_certification"]["status"] = "未开始"
    assert "缺少有效的用户直接认证" in validate_execution_qualification(missing_user_certification)
    legacy_scope = {"game_code": "demo", "mode": "base", "rtp_group": 1, "target_rtp": 0.96}
    dump(artifacts / "01-input-profile/game_profile.json", {
        "schema_version": "1.1", "report_contract_version": "slot-alignment.reports.v2.6",
        "task_id": "self-test", "status": "已完成", "scope": legacy_scope,
        "mechanics_catalog": {"version": "2.0.0", "sha256": "b" * 64},
        "mechanics": [{"mechanic_id": "feature.free-spin", "name_zh": "免费旋转", "status": "必需", "scope": "base", "attributes": {"initial_spins": 10, "retrigger": True}, "evidence": ["demo", {"protocol": "spin"}]}],
        "required_node_count": 1, "semantic_gap_count": 0,
    })
    dump(artifacts / "01-input-profile/parameter_authority.json", {
        "schema_version": "1.1", "report_contract_version": "slot-alignment.reports.v2.6",
        "task_id": "self-test", "status": "已完成", "scope": legacy_scope,
        "parameters": [{"path": "demo.weight", "type": "weight", "current": 1, "authorization_status": "已授权", "affected_metrics": ["demo.a", "demo.b"], "control_cluster": "demo", "constraints": {"min": 1, "max": 10}, "evidence": ["authority.json"]}],
    })
    run(ROOT / "render_input_profile_report.py", "--artifacts", artifacts, "--output", reports / "阶段1-资料确认与玩法画像.md")
    contract = json.loads((root / "normal/contract.json").read_text(encoding="utf-8"))
    contract.update({
        "schema_version": "1.2", "report_contract_version": "slot-alignment.reports.v2.6",
        "status": "已完成", "sealed_at": "2026-01-01T00:00:00Z", "scope": legacy_scope,
        "catalogs": {
            "mechanics_version": "2.0.0", "metrics_version": "2.0.0",
            "hashes": {"mechanics": "b" * 64, "metrics": "c" * 64},
        },
        "coverage": {
            "mechanic_required": 1, "mechanic_owned": 1, "mechanic_coverage": 1,
            "metric_required": len(contract["metrics"]), "metric_measurable": len(contract["metrics"]), "metric_measurability": 1,
        },
        "coupling_clusters": [], "waivers": [], "gaps": [], "owner_conflicts": [],
        "component_rtp_target_policy": {"method": "original_component_share_mapped_to_authoritative_total_rtp", "original_absolute_rtp_as_target": False, "authoritative_total_rtp_required": True, "share_sum_target": 1.0, "legacy_contracts_unchanged": True},
    })
    for metric in contract["metrics"]:
        metric.setdefault("status", "适用")
        metric.setdefault("unit", "ratio")
        metric.setdefault("measurement", f"legacy measurement for {metric['metric_id']}")
        display = metric.setdefault("display", {})
        display.setdefault("description_zh", f"衡量{metric.get('name_zh', metric['metric_id'])}。")
        display.setdefault("usage_scene_zh", "用于当前自测合同的对齐验证。")
        display.setdefault("target_meaning_zh", "目标值来自自测密封样本。")
        display.setdefault("display_unit", "%")
        if isinstance(metric.get("target"), list):
            display.setdefault("item_labels", [f"实际档位{i}" for i in range(1, len(metric["target"]) + 1)])
        if metric.get("kind") == "score":
            metric["score_group"] = "feature_experience"
            metric.setdefault("score_budget_key", metric["metric_id"])
            metric.setdefault("scope_aggregation", "weighted_mean")
            metric.setdefault("scope_weight", 1.0)
    contract["input_hashes"] = {
        "input_manifest": semantic_sha(artifacts / "01-input-profile/input_manifest.json"),
        "game_profile": semantic_sha(artifacts / "01-input-profile/game_profile.json"),
        "parameter_authority": semantic_sha(artifacts / "01-input-profile/parameter_authority.json"),
    }
    contract["package_matches"] = [{"mechanic_id": "feature.free-spin", "scope": "base", "package_id": "atomic.free-spin", "owner": "feature", "metric_ids": ["demo.a", "demo.b"], "evidence": {"method": "mechanic_id精确匹配", "catalog": "references/指标目录/index.json"}, "status": "已匹配"}]
    contract["coupling_clusters"] = [{"cluster_id": "demo", "parameters": ["demo.weight"], "metrics": ["demo.a", "demo.b"], "direction_evidence": {"demo.a": "正向", "demo.b": "负向"}, "sensitivity_evidence": ["sensitivity.json"], "control_type": "耦合", "attainability_status": "可达", "budget_expansion_allowed": True}]
    max_win_target = {"observed_max": 1100, "theoretical_max": 5000, "cap": 5000, "cap_hit_count": 0, "overflow_event_count": 0, "overflow_rule_status": "符合"}
    contract["metrics"].append({
        "metric_id": "core.max_win.audit", "name_zh": "最大中奖与封顶审计", "owner": "core.general", "kind": "audit", "scope": "paid-entry",
        "status": "适用", "unit": "status_object", "measurement": "legacy max-win rule audit", "target": max_win_target,
        "score_weight": 0, "audit_profile": {"method": "field_consistency_gate", "blocking_on_missing": True, "blocking_on_mismatch": True, "required_result_status": "符合", "exact_match_fields": ["theoretical_max", "cap"]},
        "display": {
            "description_zh": "核对最大中奖与封顶治理。", "usage_scene_zh": "用于验证高倍和超限处理。", "target_meaning_zh": "逐字段记录最大中奖与封顶规则。", "display_unit": "复合审计（金额为倍投注额x、次数为次、规则为状态）",
            "object_labels": {"observed_max": "样本观测最大中奖", "theoretical_max": "规则理论最大中奖", "cap": "生效封顶值", "cap_hit_count": "触发封顶次数", "overflow_event_count": "实际超限事件次数", "overflow_rule_status": "超限处理规则核对状态"},
            "object_units": {"observed_max": "倍投注额（x）", "theoretical_max": "倍投注额（x）", "cap": "倍投注额（x）", "cap_hit_count": "次", "overflow_event_count": "次", "overflow_rule_status": "状态（符合/不符合/无法证明）"},
        },
    })
    contract["coverage"].update({
        "metric_required": len(contract["metrics"]),
        "metric_measurable": len(contract["metrics"]),
    })
    contract_path = artifacts / "02-metric-matching/metric_contract.json"
    dump(contract_path, contract)
    seal_modern_policies(contract_path)
    run(ROOT / "render_metric_matching_report.py", "--contract", contract_path, "--output", reports / "阶段2-指标匹配报告.md")
    baseline_measurements = root / "baseline-measurements.json"
    baseline_measurement_data = json.loads((root / "normal/measurements.json").read_text(encoding="utf-8"))
    baseline_measurement_data["measurements"].append({"metric_id": "core.max_win.audit", "scope": "paid-entry", "status": "符合", "value": max_win_target})
    dump(baseline_measurements, baseline_measurement_data)
    scorecard_path = artifacts / "03-scoring/scorecard.json"
    report_path = reports / "阶段3-评分报告.md"
    gate_path = artifacts / "03-scoring/stage3_gate.json"
    run(ROOT / "score_alignment.py", "--contract", contract_path, "--measurements", baseline_measurements, "--output", scorecard_path)
    missing_report = run_result(ROOT / "validate_stage_transition.py", "--historical-replay", "--artifacts", artifacts, "--reports", reports, "--output", gate_path)
    assert missing_report.returncode == 1
    run(ROOT / "render_scoring_report.py", "--contract", contract_path, "--scorecard", scorecard_path, "--output", report_path)
    scoring_text = report_path.read_text(encoding="utf-8")
    bad_header = scoring_text.replace("| 目标值 | 单位 | 基线值 | 差距 | 评分/门禁 |", "| 目标 | 单位 | 基线值 | 差距 | 评分/门禁 |", 1)
    field_errors = validate_report_against_template(bad_header, (SKILL_ROOT / TEMPLATE_PATHS[3]).read_text(encoding="utf-8"), 3)
    assert any("不允许的表头" in error for error in field_errors)
    stage1_report = reports / "阶段1-资料确认与玩法画像.md"
    stage1_original = stage1_report.read_text(encoding="utf-8")
    stage1_report.write_text("# 阶段1-资料确认与玩法画像\n\n已完成。\n", encoding="utf-8")
    incomplete_stage1 = run_result(ROOT / "validate_stage_transition.py", "--historical-replay", "--artifacts", artifacts, "--reports", reports, "--output", gate_path)
    assert incomplete_stage1.returncode == 1
    stage1_report.write_text(stage1_original, encoding="utf-8")
    stage2_report = reports / "阶段2-指标匹配报告.md"
    stage2_original = stage2_report.read_text(encoding="utf-8")
    stage2_report.write_text(stage2_original.replace("## 二、上游画像与目录版本绑定", "## 临时错误章节"), encoding="utf-8")
    reordered_stage2 = run_result(ROOT / "validate_stage_transition.py", "--historical-replay", "--artifacts", artifacts, "--reports", reports, "--output", gate_path)
    assert reordered_stage2.returncode == 1
    stage2_report.write_text(stage2_original, encoding="utf-8")
    run(ROOT / "validate_stage_transition.py", "--historical-replay", "--artifacts", artifacts, "--reports", reports, "--output", gate_path)
    report_path.write_text(report_path.read_text(encoding="utf-8") + "\n篡改", encoding="utf-8")
    tampered_report = run_result(ROOT / "validate_stage_transition.py", "--historical-replay", "--artifacts", artifacts, "--reports", reports, "--output", gate_path)
    assert tampered_report.returncode == 1
    run(ROOT / "render_scoring_report.py", "--contract", contract_path, "--scorecard", scorecard_path, "--output", report_path)
    run(ROOT / "validate_stage_transition.py", "--historical-replay", "--artifacts", artifacts, "--reports", reports, "--output", gate_path)
    original_contract = json.loads(contract_path.read_text(encoding="utf-8"))
    tampered_contract = json.loads(contract_path.read_text(encoding="utf-8"))
    tampered_contract["group_weights"] = {"experience": 2}
    dump(contract_path, tampered_contract)
    stale_contract = run_result(ROOT / "validate_stage_transition.py", "--historical-replay", "--artifacts", artifacts, "--reports", reports, "--output", gate_path)
    assert stale_contract.returncode == 1
    dump(contract_path, original_contract)
    run(ROOT / "validate_stage_transition.py", "--historical-replay", "--artifacts", artifacts, "--reports", reports, "--output", gate_path)
    failed_baseline = json.loads(baseline_measurements.read_text(encoding="utf-8"))
    failed_baseline["measurements"][0]["value"] = 0.90
    dump(baseline_measurements, failed_baseline)
    run(ROOT / "score_alignment.py", "--contract", contract_path, "--measurements", baseline_measurements, "--output", scorecard_path)
    assert json.loads(scorecard_path.read_text(encoding="utf-8"))["alignment_status"] == "不通过"
    run(ROOT / "render_scoring_report.py", "--contract", contract_path, "--scorecard", scorecard_path, "--output", report_path)
    run(ROOT / "validate_stage_transition.py", "--historical-replay", "--artifacts", artifacts, "--reports", reports, "--output", gate_path)
    dump(baseline_measurements, baseline_measurement_data)
    run(ROOT / "score_alignment.py", "--contract", contract_path, "--measurements", baseline_measurements, "--output", scorecard_path)
    run(ROOT / "render_scoring_report.py", "--contract", contract_path, "--scorecard", scorecard_path, "--output", report_path)
    run(ROOT / "validate_stage_transition.py", "--historical-replay", "--artifacts", artifacts, "--reports", reports, "--output", gate_path)
    gate_hash = sha(gate_path)
    dump(artifacts / "04-alignment/alignment_manifest.json", {"schema_version": "1.4", "report_contract_version": "slot-alignment.reports.v2.6", "task_id": "self-test", "status": "已完成", "input_hashes": {}, "execution_policy": {"calibration_execution_path": "python", "formal_execution_path": "python", "certification_method": "user_direct"}, "stage3_gate": {"path": "03-scoring/stage3_gate.json", "sha256": gate_hash, "stage4_allowed": True}, "budget_policy": {"auto_expand": True, "attainability_ceiling": {"enabled": True, "stop_status": "结构不可达", "prohibit_budget_only_expansion": True}}})
    dump(artifacts / "04-alignment/candidate_archive.json", {"schema_version": "1.3", "task_id": "self-test", "stage3_gate_sha256": gate_hash, "candidates": [{"candidate_id": "baseline", "parent_id": "—", "parameter_summary": {"demo.weight": 2}, "hard_gate_status": "通过", "overall_score": 90, "sample_count": 1000, "risk": "低", "decision_reason": "基线通过", "status": "冻结"}], "stop_reason": "基线通过", "budget": {"calibration_samples": 1000, "formal_samples": 1000}, "attainability": {"status": "可达", "evidence_path": "", "evidence_sha256": "", "budget_expansion_allowed": True}})
    dump(artifacts / "04-alignment/aligned_parameters.json", {"schema_version": "1.0", "task_id": "self-test", "candidate_id": "baseline", "status": "已完成", "parameters": [{"path": "demo.weight", "before": 1, "after": 2, "delta": 1, "authorization_status": "已授权", "control_cluster": "demo", "affected_metrics": ["demo.a", "demo.b"], "risk": "低"}]})
    formal_scorecard = json.loads(scorecard_path.read_text(encoding="utf-8"))
    dump(artifacts / "04-alignment/formal_result.json", {"schema_version": "1.1", "report_contract_version": "slot-alignment.reports.v2.6", "task_id": "self-test", "candidate_id": "baseline", "plan_id": "formal-1", "status": "通过", "execution_valid": True, "independent_from_calibration": True, "execution_path": "python", "user_script_certification_sha256": certification_sha, "input_hashes": {"metric_contract": "e" * 64, "candidate": "f" * 64}, "sample": {"paid_entry_count": 1000}, "scorecard": formal_scorecard, "attempt": 1, "audits": {"long_tail": [], "max_win": {"status": "已审计", "observed_max": 1200, "theoretical_max": 5000, "cap": 5000, "cap_hit_count": 0, "overflow_event_count": 0, "overflow_rule_status": "符合"}}})
    run(ROOT / "render_alignment_report.py", "--artifacts", artifacts, "--output", reports / "阶段4-数值对齐报告.md")
    alignment_report = reports / "阶段4-数值对齐报告.md"
    alignment_text = alignment_report.read_text(encoding="utf-8")
    assert "评分预算键" in alignment_text and "作用域聚合" in alignment_text and "预算得分" in alignment_text
    assert "有效评分预算数" in alignment_text and "demo.a" in alignment_text
    assert all(label in alignment_text for label in ("样本观测最大中奖", "规则理论最大中奖", "生效封顶值", "触发封顶次数", "实际超限事件次数", "超限处理规则核对状态"))
    stage_metric_headings = [
        [heading for heading, _ in metric_blocks(path.read_text(encoding="utf-8"))]
        for path in (reports / "阶段2-指标匹配报告.md", report_path, alignment_report)
    ]
    assert stage_metric_headings[0] == stage_metric_headings[1] == stage_metric_headings[2]
    alignment_original = alignment_report.read_text(encoding="utf-8")
    alignment_report.write_text(alignment_original + "\n手工篡改", encoding="utf-8")
    tampered_alignment = run_result(ROOT / "validate_artifacts.py", "--historical-replay", "--artifacts", artifacts, "--reports", reports, "--pre-delivery")
    assert tampered_alignment.returncode == 1
    alignment_report.write_text(alignment_original, encoding="utf-8")
    original_measurements = json.loads(baseline_measurements.read_text(encoding="utf-8"))
    tampered_measurements = json.loads(baseline_measurements.read_text(encoding="utf-8"))
    tampered_measurements["measurements"][0]["value"] = 0.91
    dump(baseline_measurements, tampered_measurements)
    stale_measurements = run_result(ROOT / "validate_artifacts.py", "--historical-replay", "--artifacts", artifacts, "--reports", reports, "--pre-delivery")
    assert stale_measurements.returncode == 1
    dump(baseline_measurements, original_measurements)
    run(ROOT / "validate_artifacts.py", "--historical-replay", "--artifacts", artifacts, "--reports", reports, "--pre-delivery")
    archive_path = artifacts / "04-alignment/candidate_archive.json"
    archive = json.loads(archive_path.read_text(encoding="utf-8"))
    archive["attainability"] = {"status": "结构不可达", "evidence_path": "blocked.json", "evidence_sha256": "a" * 64, "budget_expansion_allowed": True}
    dump(archive_path, archive)
    assert "结构不可达后仍允许预算扩张" in validate_attainability_ceiling(artifacts)
    archive["attainability"]["budget_expansion_allowed"] = False
    dump(archive_path, archive)
    assert validate_attainability_ceiling(artifacts) == []
    archive["attainability"] = {"status": "可达", "evidence_path": "", "evidence_sha256": "", "budget_expansion_allowed": True}
    dump(archive_path, archive)
    dump(formal_runtime / "game_core.json", {"meta": {"game_code": "demo", "version": "self-test"}, "runtime_flags": {"rtp_routing": {"default_group": 1, "groups": [1]}}})
    for name in ("payout_config.json", "reel_config.json", "symbol_catalog.json"):
        dump(formal_runtime / name, {})
    run(ROOT / "seal_delivery.py", "--historical-replay", "--artifacts", artifacts, "--reports", reports, "--formal-runtime", formal_runtime)
    run(ROOT / "validate_artifacts.py", "--historical-replay", "--artifacts", artifacts, "--reports", reports)
    for report_path in sorted(reports.glob("*.md")):
        assert_report_display(report_path)
    delivery_report = reports / "阶段5-交付清单.md"
    delivery_original = delivery_report.read_text(encoding="utf-8")
    delivery_report.write_text(delivery_original.replace("## 七、回退与复算方法", "## 错误章节"), encoding="utf-8")
    tampered_delivery = run_result(ROOT / "validate_artifacts.py", "--historical-replay", "--artifacts", artifacts, "--reports", reports)
    assert tampered_delivery.returncode == 1
    delivery_report.write_text(delivery_original, encoding="utf-8")
    run(ROOT / "validate_artifacts.py", "--historical-replay", "--artifacts", artifacts, "--reports", reports)

    skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    example_text = (SKILL_ROOT / "references/97-最小完整示例.md").read_text(encoding="utf-8")
    storage_text = (SKILL_ROOT / "references/98-通用合同架构升级.md").read_text(encoding="utf-8")
    assert "基础TV容差" not in example_text
    assert "一维Wasserstein基础有序距离容差" in example_text
    assert "slot-alignment.reports.v3.2" not in storage_text
    assert all(link in skill_text for link in (
        "(references/02A-可达性与豁免.md)",
        "(references/96-确定性工具与验证.md)",
        "(references/98-通用合同架构升级.md)",
    ))
    for name in ("01-资料确认与玩法画像.md", "02-指标匹配.md", "90-跨阶段一致性.md", "98-通用合同架构升级.md"):
        assert "v2.5～v2.9及v3.2" in (SKILL_ROOT / "references" / name).read_text(encoding="utf-8")
    assert "v2.5至v2.9及v3.2" in skill_text
    print(json.dumps({"status": "通过", "scenarios": ["104指标与24玩法包全量矩阵", "metric_contract 1.4紧凑往返与缓存", "五阶段模板展示契约", "逐章Markdown展示实例", "模板缺展示实例阻塞", "必需字段存在性", "表头名称与顺序", "指标通俗解释", "业务单位转换", "真实分布标签", "开工前样本数确认", "全量重算必须覆盖全部已发现源", "Python脚本名称绝对路径与Hash确认", "阶段1确定性完整报告", "阶段2确定性完整报告", "阶段1缺章节阻塞", "阶段2章节错误阻塞", "v3.3动态语义合同", "多节点、多入口与多盘面阶段实例", "事件集与目标证据完整性", "Feature路径与0x一致性", "Feature Buy逐事件重算", "固定Jackpot确定性不适用", "Wild倍率依赖、倍率递进、固定线、Wasserstein与阻塞审计反例", "正向", "硬指标失败", "豁免后通过", "未来任务容差系数", "组件RTP占比映射", "Python脚本用户直接认证", "非Python认证路径阻塞", "缺少用户认证阻塞", "阶段3报告缺失阻塞", "阶段3报告篡改阻塞", "阶段3合同hash失效阻塞", "阶段3测量hash失效阻塞", "基线不通过仍允许进入阶段4", "阶段3到阶段4门禁", "阶段4报告篡改阻塞", "预算可达性上限", "阶段5报告篡改阻塞", "交付封存", "旧任务报告契约版本保持", "v3.2历史复算兼容", "Skill导航与版本文档一致性"], "component_target_method": component_targets["method"], "fixture": str(root)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
