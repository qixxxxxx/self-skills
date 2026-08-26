#!/usr/bin/env python3
import argparse
import hashlib
import itertools
import json
import math
import re
import sys
from pathlib import Path

from apply_ordered_distance_policy import validate_policy_source_binding as validate_ordered_distance_policy_binding
from apply_score_group_weight_policy import validate_policy_source_binding as validate_score_group_weight_policy_binding
from apply_jackpot_materiality_policy import validate_policy_source_binding as validate_jackpot_materiality_policy_binding
from catalog_tool import CATALOG_DIRECTORY_NAMES, validate_catalogs
from workspace_paths import task_root

try:
    from jsonschema import Draft202012Validator
except ModuleNotFoundError:
    Draft202012Validator = None


ACTIVE_MECHANIC_STATUSES = {"必需", "适用"}
INACTIVE_METRIC_STATUS = "不适用"
COMPLETE_STATUS = "已完成"
FEATURE_MECHANIC_IDS = {
    "feature.free-spin",
    "feature.respin",
    "feature.hold-and-spin",
    "feature.award-draw",
    "feature.bonus-sequence",
}
BONUS_SEQUENCE_MECHANIC_ID = "feature.bonus-sequence"
CORE_ALWAYS_ACTIVE = {
    "core.rtp.total",
    "core.hit_rate.paid_entry",
    "core.return_distribution.lt200",
    "core.sigma",
    "core.rtp.component_contribution",
    "core.feature.natural_trigger_rate",
    "core.long_tail.audit",
    "core.max_win.audit",
}
CORE_NODE_SCOPED = {
    "core.feature.natural_trigger_rate",
    "core.sigma",
    "core.rtp.component_contribution",
}
INAPPLICABILITY_REASON_CODES = {
    "degenerate_reachable_support",
    "deterministically_derived_from_primary",
    "semantic_owner_exclusive",
    "feature_buy_unavailable",
    "deterministic_rule_result",
    "below_materiality_resolution",
}
PROFILE_INAPPLICABILITY_REASON_CODES = {"source_evidence_proves_absence"}
EXCLUSIVE_METRIC_PAIRS = set()
STEP_RETURN_OWNER_PRIORITY = (
    "cascade.step_return_distribution_by_depth",
    "variable_grid.return_distribution_by_capacity",
    "effective_ways.return_distribution_by_capacity",
    "settlement.step_return_distribution",
)
STEP_RETURN_SETTLEMENT_MECHANICS = {
    "settlement.payline",
    "settlement.ways",
    "settlement.count-pay",
    "settlement.cluster-pay",
}
WILD_ECONOMIC_METRIC_IDS = {
    "wild.assistance_rate_given_opportunity",
    "wild.incremental_return_given_assistance_distribution",
    "wild.rtp_contribution.audit",
}
AWARD_CHAIN_PROOF = {
    "draw_state_definition_minimal_sufficient": True,
    "transition_rule_deterministic": True,
    "stop_rule_deterministic": True,
    "award_aggregation_deterministic": True,
    "terminal_return_projection_deterministic": True,
    "extra_random_reward_outside_draw_chain": False,
    "unmodeled_player_decision_affects_return": False,
}
FEATURE_PATH_INCLUDED_FIELDS = {"control_stage_id", "branch_id"}
FEATURE_PATH_REQUIRED_EXCLUDED_FIELDS = {"award_outcome", "state_value", "duration", "return_bucket"}
FALSE_MARKERS = {"", "none", "null", "false", "no", "n/a", "not_applicable", "无", "不适用", "不存在"}
MISSING = object()
INSTANCE_DIMENSION_KEYS = {
    "mode",
    "rtp_group",
    "stage",
    "component",
    "state",
    "state_id",
    "observation_point",
    "transition_event",
    "board_phase",
    "settlement_type",
    "entry_source",
    "entry_source_domain",
    "actual_capacity",
    "current_actual_capacity",
    "next_actual_capacity",
    "capacity_observation_point",
    "capacity_scope",
    "geometry_layout",
    "assignment_context",
    "generator_partition",
    "cascade_step_bucket",
    "settlement_scope",
    "output_semantic",
    "output_unit",
    "jackpot_opportunity_set",
}
ENTRY_SOURCE_VALUES = {
    "natural",
    "feature_buy",
    "feature_award",
    "state_threshold",
    "direct_award",
    "forced_test",
    "test_injection",
    "operator_override",
}
ENDOGENOUS_ENTRY_SOURCE_KINDS = {
    "symbol_rule",
    "random_event",
    "state_threshold",
    "feature_award",
    "direct_game_award",
    "other_game_rule",
}
EXOGENOUS_ENTRY_SOURCE_KINDS = {
    "feature_buy",
    "forced_test",
    "test_injection",
    "operator_override",
    "other_external",
}
ORDERED_AXIS_SEMANTICS = {"natural_linear", "nonnegative_multiplicative"}
SETTLEMENT_SCALE_AXIS = {
    "settlement.payline": "natural_linear",
    "settlement.ways": "nonnegative_multiplicative",
    "settlement.count-pay": "natural_linear",
    "settlement.cluster-pay": "natural_linear",
}
COLLECT_OUTPUT_AXIS = {
    "direct_payout": "nonnegative_multiplicative",
    "multiplier": "nonnegative_multiplicative",
    "state_increment": "natural_linear",
    "level": "natural_linear",
    "natural_count": "natural_linear",
    "progress_step": "natural_linear",
}
DYNAMIC_ORDERED_METRICS = {
    "cascade.effective_capacity_distribution_by_depth",
    "collect.output_value_given_input_count_distribution",
    "settlement.scale_given_symbol_distribution",
    "persistent_state.ordered_value_distribution",
    "persistent_state.ordered_transition_distribution",
}
DERIVATION_PROJECTORS = {
    "board.symbol_partition_count_vector_given_total_distribution": {
        "projector_id": "actual_position_pattern_to_partition_vector_v1",
        "source_sets": ({"trigger.position_pattern_given_count_distribution"},),
        "normalization": "condition_on_retained_mass_by_target_group",
    },
    "board.max_symbol_stack_length_given_count_distribution": {
        "projector_id": "actual_position_pattern_to_max_stack_length_v1",
        "source_sets": ({"trigger.position_pattern_given_count_distribution"},),
        "normalization": "condition_on_retained_mass_by_target_group",
    },
    "trigger.symbol_count_distribution": {
        "projector_id": "exact_board_count_to_trigger_count_v1",
        "source_sets": ({"board.symbol_count_per_board_distribution"},),
        "normalization": "condition_on_retained_mass",
    },
    "settlement.winning_symbol_distribution": {
        "projector_id": "exact_board_count_to_count_pay_winning_symbol_v1",
        "source_sets": ({"board.symbol_count_per_board_distribution"},),
        "normalization": "condition_on_retained_mass",
    },
    "settlement.scale_given_symbol_distribution": {
        "projector_id": "exact_board_count_to_count_pay_scale_v1",
        "source_sets": ({"board.symbol_count_per_board_distribution"},),
        "normalization": "condition_on_retained_mass_by_target_group",
    },
    "feature_cycle.duration_distribution": {
        "projector_id": "initial_resource_or_draw_chain_to_duration_v1",
        "source_sets": (
            {"free_spin.initial_grant_distribution"},
            {"respin.initial_grant_distribution"},
            {"award_draw.outcome_distribution_given_draw_state"},
            {"feature_cycle.stage_path_distribution"},
        ),
        "normalization": "none",
    },
}
FEATURE_RESOURCE_METRICS = {
    "free_spin.initial_grant_distribution": "deterministic_success_subset",
    "free_spin.retrigger_grant_distribution": "same_event_pushforward",
    "respin.initial_grant_distribution": "deterministic_success_subset",
    "respin.extension_grant_distribution": "same_event_pushforward",
    "hold_spin.initial_occupancy_distribution": "deterministic_success_subset",
}
FEATURE_RESOURCE_SOURCE_METRICS = {
    "board.symbol_count_per_board_distribution",
    "trigger.symbol_count_distribution",
}
VALIDATION_MODES = {"stage_transition", "historical_replay"}
LEGACY_REPORT_VERSIONS = {f"slot-alignment.reports.v2.{minor}" for minor in range(5, 10)}
CURRENT_REPORT_VERSION = "slot-alignment.reports.v3.2"
AUDIT_TARGET_STATUSES = {"符合", "不符合", "无法证明", "有证据不适用", "置信不足"}
CATALOG_IMMUTABLE_FIELDS = (
    "name_zh",
    "owner",
    "category",
    "display_order",
    "kind",
    "unit",
    "scope_template",
    "measurement",
    "sample_unit",
    "condition_on",
    "normalization",
    "applicability_rule",
    "missing_policy",
    "inapplicability_reason_codes",
    "capability_ids",
    "profile_match",
    "semantic_variable_id",
    "semantic_group",
    "semantic_role",
    "relationships",
    "conditional_derivation_requirements",
    "score_group",
    "score_budget_key",
    "scope_aggregation",
    "score_profile",
    "hard_gate_profile",
    "audit_profile",
    "display",
)


def load(path):
    with Path(path).open(encoding="utf-8") as file:
        return json.load(file)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def task_evidence_root(task_root_path):
    return Path(task_root_path).resolve()


def safe_evidence_path(root, relative):
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        return None
    path = (root / relative).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        return None
    return path


def sealed_event_count(path, sample_unit=None, dimensions=None):
    data = load(path)
    if isinstance(data, list):
        events = data
    elif isinstance(data, dict) and isinstance(data.get("events"), list):
        events = data["events"]
    else:
        raise ValueError("密封事件集必须为JSON数组或包含events数组的对象")
    if not events or not all(
        isinstance(event, dict)
        and isinstance(event.get("event_id"), str)
        and bool(event["event_id"].strip())
        for event in events
    ):
        raise ValueError("密封事件必须为含event_id的非空对象数组")
    if len({event["event_id"] for event in events}) != len(events):
        raise ValueError("密封事件event_id必须唯一")
    if sample_unit is not None and any(event.get("sample_unit") != sample_unit for event in events):
        raise ValueError("密封事件sample_unit与scope_instance不一致")
    dimensions = dimensions or {}
    if any(
        not isinstance(event.get("dimensions"), dict)
        or any(event["dimensions"].get(name) != value for name, value in dimensions.items())
        for event in events
    ):
        raise ValueError("密封事件dimensions与scope_instance不一致")
    return len(events)


def canonical_sha256(value):
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def measurement_contract_sha256(metric):
    return canonical_sha256({
        field: metric.get(field)
        for field in ("measurement", "sample_unit", "condition_on", "normalization", "unit")
    })


def historical_contract_errors(
    profile,
    contract,
    input_manifest,
    profile_path,
    input_manifest_path,
    parameter_authority_path=None,
):
    errors = []
    input_manifest = input_manifest or {}
    if input_manifest_path is None or not Path(input_manifest_path).is_file():
        errors.append("historical_replay缺少input_manifest")
    versions = [
        contract.get("report_contract_version"),
        profile.get("report_contract_version"),
        input_manifest.get("report_contract_version"),
    ]
    if input_manifest.get("schema_version") != "1.1" or profile.get("schema_version") != "1.1" or contract.get("schema_version") != "1.2":
        errors.append("historical_replay只允许已发布的input_manifest/game_profile 1.1与metric_contract 1.2")
    if not all(isinstance(value, str) and value for value in versions) or len(set(versions)) != 1 or versions[0] not in LEGACY_REPORT_VERSIONS:
        errors.append("historical_replay三份报告版本必须一致且属于v2.5至v2.9")
    documents = {
        "game_profile": profile,
        "metric_contract": contract,
        "input_manifest": input_manifest,
    }
    authority = None
    if parameter_authority_path is not None and Path(parameter_authority_path).is_file():
        authority = load(parameter_authority_path)
        if not isinstance(authority, dict):
            errors.append("historical_replay parameter_authority顶层必须为对象")
            authority = {}
        documents["parameter_authority"] = authority
        if authority.get("schema_version") != "1.1":
            errors.append("historical_replay只允许parameter_authority 1.1")
        authority_version = authority.get("report_contract_version")
        if authority_version != versions[0]:
            errors.append("historical_replay parameter_authority报告版本不一致")
        parameters = authority.get("parameters")
        if not isinstance(parameters, list) or not all(isinstance(item, dict) for item in parameters):
            errors.append("historical_replay parameter_authority.parameters必须为对象数组")
    else:
        errors.append("historical_replay缺少parameter_authority")
    task_ids = {name: value.get("task_id") for name, value in documents.items()}
    if any(not non_empty(value) for value in task_ids.values()) or len(set(task_ids.values())) != 1:
        errors.append("historical_replay任务身份缺失或task_id不一致")
    for name, value in documents.items():
        if value.get("status") != COMPLETE_STATUS:
            errors.append(f"historical_replay完成态无效: {name}={value.get('status')}")
    profile_scope = profile.get("scope") if isinstance(profile.get("scope"), dict) else {}
    contract_scope = contract.get("scope") if isinstance(contract.get("scope"), dict) else {}
    manifest_scope = input_manifest.get("scope") if isinstance(input_manifest.get("scope"), dict) else {}
    for field in ("game_code", "mode", "rtp_group"):
        declared = [scope[field] for scope in (contract_scope, manifest_scope) if non_empty(scope.get(field))]
        if len(declared) != 2 or declared[0] != declared[1]:
            errors.append(f"historical_replay合同与清单作用域不一致或缺少{field}")
        if non_empty(profile_scope.get(field)) and declared and profile_scope[field] != declared[0]:
            errors.append(f"historical_replay玩法画像作用域{field}与合同不一致")
    if "target_rtp" not in contract_scope or contract_scope.get("target_rtp") != manifest_scope.get("target_rtp"):
        errors.append("historical_replay合同与清单target_rtp缺失或不一致")
    mechanics = profile.get("mechanics")
    if not isinstance(mechanics, list) or not mechanics or not all(isinstance(item, dict) and non_empty(item.get("mechanic_id")) for item in mechanics):
        errors.append("historical_replay玩法画像必须包含至少一个完整玩法节点")
    required_node_count = profile.get("required_node_count")
    if not isinstance(required_node_count, int) or isinstance(required_node_count, bool) or required_node_count < 1 or not isinstance(mechanics, list) or required_node_count > len(mechanics):
        errors.append("historical_replay required_node_count必须为不超过玩法数的正整数")
    if profile.get("semantic_gap_count") != 0:
        errors.append("historical_replay玩法画像仍有语义缺口")
    mechanic_catalog = profile.get("mechanics_catalog") if isinstance(profile.get("mechanics_catalog"), dict) else {}
    if not non_empty(mechanic_catalog.get("version")) or not is_sha256(mechanic_catalog.get("sha256")):
        errors.append("historical_replay玩法画像缺少有效目录版本与hash")
    metrics = contract.get("metrics")
    if not isinstance(metrics, list) or not metrics or not all(
        isinstance(item, dict)
        and non_empty(item.get("metric_id"))
        and non_empty(item.get("kind"))
        and non_empty(item.get("scope"))
        and non_empty(item.get("unit"))
        and non_empty(item.get("measurement"))
        and "target" in item
        for item in metrics
    ):
        errors.append("historical_replay指标合同必须包含至少一个可识别指标")
    if not isinstance(metrics, list) or not any(
        isinstance(item, dict)
        and item.get("metric_id") == "core.rtp.total"
        and item.get("status") != INACTIVE_METRIC_STATUS
        for item in metrics
    ):
        errors.append("historical_replay指标合同缺少活动core.rtp.total")
    coverage = contract.get("coverage")
    coverage_fields = {
        "mechanic_required", "mechanic_owned", "mechanic_coverage",
        "metric_required", "metric_measurable", "metric_measurability",
    }
    if not isinstance(coverage, dict) or not coverage_fields.issubset(coverage):
        errors.append("historical_replay缺少有效覆盖率")
    else:
        if (
            not isinstance(coverage["mechanic_required"], int)
            or isinstance(coverage["mechanic_required"], bool)
            or coverage["mechanic_required"] < 1
            or coverage["mechanic_required"] != required_node_count
            or coverage["mechanic_owned"] != coverage["mechanic_required"]
            or coverage["mechanic_coverage"] != 1
            or not isinstance(coverage["metric_required"], int)
            or isinstance(coverage["metric_required"], bool)
            or coverage["metric_required"] < 1
            or coverage["metric_measurable"] != coverage["metric_required"]
            or coverage["metric_measurability"] != 1
        ):
            errors.append("historical_replay覆盖率必须证明全部玩法与必需指标已覆盖")
    catalogs = contract.get("catalogs") if isinstance(contract.get("catalogs"), dict) else {}
    catalog_hashes = catalogs.get("hashes") if isinstance(catalogs.get("hashes"), dict) else {}
    if (
        not non_empty(catalogs.get("mechanics_version"))
        or not non_empty(catalogs.get("metrics_version"))
        or not is_sha256(catalog_hashes.get("mechanics"))
        or not is_sha256(catalog_hashes.get("metrics"))
        or catalogs.get("mechanics_version") != mechanic_catalog.get("version")
        or catalog_hashes.get("mechanics") != mechanic_catalog.get("sha256")
    ):
        errors.append("historical_replay玩法与指标目录绑定不完整或内部不一致")
    for field in ("coupling_clusters", "waivers", "gaps", "owner_conflicts"):
        if not isinstance(contract.get(field), list):
            errors.append(f"historical_replay指标合同缺少数组字段{field}")
    if contract.get("gaps") or contract.get("owner_conflicts"):
        errors.append("historical_replay完成态仍有指标缺口或Owner冲突")
    if not non_empty(contract.get("sealed_at")):
        errors.append("historical_replay指标合同缺少sealed_at")
    if "input_hashes" in contract:
        input_hashes = contract.get("input_hashes")
        if not isinstance(input_hashes, dict) or not input_hashes:
            errors.append("historical_replay已声明input_hashes但内容为空或无效")
        else:
            expected_hashes = {"game_profile": sha(profile_path)}
            if input_manifest_path is not None and Path(input_manifest_path).is_file():
                expected_hashes["input_manifest"] = sha(input_manifest_path)
            if parameter_authority_path is not None and Path(parameter_authority_path).is_file():
                expected_hashes["parameter_authority"] = sha(parameter_authority_path)
            declared_known = set(input_hashes) & set(expected_hashes)
            if not declared_known:
                errors.append("historical_replay input_hashes未绑定任何阶段1输入")
            for field in declared_known:
                if input_hashes.get(field) != expected_hashes[field]:
                    errors.append(f"historical_replay输入hash失效: {field}")
    return errors


def non_empty(value):
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return True


def semantic_truthy(value):
    if isinstance(value, str):
        return value.strip().lower() not in FALSE_MARKERS
    if isinstance(value, (list, tuple, set)):
        return any(semantic_truthy(item) for item in value)
    if isinstance(value, dict):
        return bool(value)
    return bool(value)


def source_evidence_proves_absence(value):
    if value is None or value is False or value == 0:
        return True
    if isinstance(value, str):
        return value.strip().lower() in FALSE_MARKERS | {
            "absent", "missing", "not_present", "not-present", "不存在", "未发现",
        }
    if not isinstance(value, dict):
        return False
    for field in ("present", "exists", "enabled", "active", "available"):
        if field in value:
            return value[field] is False
    status = value.get("status")
    return isinstance(status, str) and status.strip().lower() in {
        "absent", "missing", "not_present", "not-present", "不存在", "未发现",
    }


def collect_output_axis_map(value):
    errors, result = [], {}
    if value is None:
        return errors, result
    if not isinstance(value, list) or not value:
        return ["Collect有序输出轴语义必须为非空对象数组"], result
    required = {"output_semantic", "output_unit", "axis_semantics"}
    for index, item in enumerate(value, 1):
        if not isinstance(item, dict) or set(item) != required:
            errors.append(f"Collect输出轴语义第{index}项必须只含output_semantic、output_unit、axis_semantics")
            continue
        semantic = item.get("output_semantic")
        unit = item.get("output_unit")
        axis = item.get("axis_semantics")
        expected = COLLECT_OUTPUT_AXIS.get(semantic)
        if expected is None:
            errors.append(f"Collect输出语义不受支持或属于无序奖项: {semantic}")
        if not non_empty(unit):
            errors.append(f"Collect输出单位不能为空: {semantic}")
        if axis not in ORDERED_AXIS_SEMANTICS or expected is not None and axis != expected:
            errors.append(f"Collect输出轴语义与输出含义不一致: {semantic} / {axis}")
        if semantic == "direct_payout" and unit != "bet_multiple":
            errors.append("Collect直接派奖必须先换算为bet_multiple")
        if semantic == "multiplier" and unit != "multiplier":
            errors.append("Collect倍率结果的output_unit必须为multiplier")
        key = (semantic, unit)
        if key in result:
            errors.append(f"Collect输出语义与单位重复: {semantic} / {unit}")
        elif expected is not None and non_empty(unit) and axis in ORDERED_AXIS_SEMANTICS:
            result[key] = axis
    return errors, result


def collect_output_category_map(value):
    errors, result = [], {}
    if value is None:
        return errors, result
    if not isinstance(value, list) or not value:
        return ["Collect无序输出类别域必须为非空对象数组"], result
    required = {"output_semantic", "output_unit", "categories"}
    for index, item in enumerate(value, 1):
        if not isinstance(item, dict) or set(item) != required:
            errors.append(f"Collect无序输出第{index}项必须只含output_semantic、output_unit、categories")
            continue
        semantic = item.get("output_semantic")
        unit = item.get("output_unit")
        categories = item.get("categories")
        if not non_empty(semantic):
            errors.append(f"Collect无序输出语义不能为空: 第{index}项")
        if not non_empty(unit):
            errors.append(f"Collect无序输出单位不能为空: {semantic}")
        if (
            not isinstance(categories, list)
            or len(categories) < 2
            or any(not non_empty(category) for category in categories)
            or len(categories) != len(set(categories))
        ):
            errors.append(f"Collect无序输出类别域必须包含至少两个非空唯一真实类别: {semantic}")
        key = (semantic, unit)
        if key in result:
            errors.append(f"Collect无序输出语义与单位重复: {semantic} / {unit}")
        elif non_empty(semantic) and non_empty(unit) and isinstance(categories, list) and len(categories) >= 2:
            result[key] = categories
    return errors, result


def validate_collect_output_maps(attributes):
    axis_errors, ordered = collect_output_axis_map(attributes.get("output_axis_semantics_by_output"))
    category_errors, categorical = collect_output_category_map(attributes.get("output_category_domains_by_output"))
    errors = axis_errors + category_errors
    if not ordered and not categorical:
        errors.append("Collect必须至少声明一种有序数值输出或无序类别输出")
    ordered_semantics = {semantic for semantic, _ in ordered}
    categorical_semantics = {semantic for semantic, _ in categorical}
    if len(ordered_semantics) != len(ordered):
        errors.append("同一Collect有序输出语义只能登记一次且必须使用唯一业务单位")
    if len(categorical_semantics) != len(categorical):
        errors.append("同一Collect无序输出语义只能登记一次且必须使用唯一业务单位")
    overlap = sorted(ordered_semantics & categorical_semantics)
    if overlap:
        errors.append(f"同一Collect输出语义不得同时登记为有序和无序: {','.join(overlap)}")
    domain = attributes.get("output_semantic_domain")
    if (
        not isinstance(domain, list)
        or not domain
        or any(not non_empty(semantic) for semantic in domain)
        or len(domain) != len(set(domain))
    ):
        errors.append("Collect output_semantic_domain必须为非空唯一真实语义列表")
    elif set(domain) != ordered_semantics | categorical_semantics:
        errors.append("Collect每个output_semantic必须且只能由有序数值或无序类别映射承接一次")
    return errors, ordered, categorical


def is_sha256(value):
    return isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def validate_position_count_owner_bindings(node):
    bindings = node.get("attributes", {}).get("position_count_owner_bindings")
    if bindings is None:
        return []
    if not isinstance(bindings, list) or not bindings:
        return [f"位置数量Owner绑定必须为非空对象数组: {node.get('node_id')}"]
    required = {
        "consumer_metric_id",
        "consumer_instance_dimensions",
        "primary_owner_metric_instance",
        "shared_semantic_event_set_id",
        "relation",
        "rule_evidence_sha256",
    }
    allowed = {
        "persistent_state.position_share_given_occupied_count_distribution": {
            "same_observation_count_marginal": {
                "hold_spin.initial_occupancy_distribution",
                "hold_spin.terminal_occupied_cell_count_distribution",
            },
        },
        "persistent_state.position_role_dependence_residual_given_count_transition": {
            "monotone_count_transition": {"hold_spin.occupancy_transition_distribution"},
        },
    }
    errors, identities = [], set()
    for index, binding in enumerate(bindings, 1):
        label = f"{node.get('node_id')}第{index}条位置数量Owner绑定"
        if not isinstance(binding, dict) or set(binding) != required:
            errors.append(f"{label}必须完整使用六个固定字段")
            continue
        metric_id = binding.get("consumer_metric_id")
        relation = binding.get("relation")
        source = binding.get("primary_owner_metric_instance")
        dimensions = binding.get("consumer_instance_dimensions")
        if metric_id not in allowed or relation not in allowed.get(metric_id, {}):
            errors.append(f"{label}的consumer_metric_id或relation不受支持")
        expected_dimension_keys = {
            "persistent_state.position_share_given_occupied_count_distribution": {"state_id", "observation_point"},
            "persistent_state.position_role_dependence_residual_given_count_transition": {"state_id", "transition_event"},
        }.get(metric_id, set())
        if not isinstance(dimensions, dict) or set(dimensions) != expected_dimension_keys or any(not non_empty(value) for value in dimensions.values()):
            errors.append(f"{label}的consumer_instance_dimensions无效")
            dimensions = {}
        identity = metric_id, dimensions_key(dimensions)
        if identity in identities:
            errors.append(f"{label}重复绑定同一空间指标实例")
        identities.add(identity)
        source_fields = {"metric_id", "source_node_ids", "instance_dimensions"}
        if not isinstance(source, dict) or set(source) != source_fields:
            errors.append(f"{label}的primary_owner_metric_instance必须完整使用三个固定字段")
            source = {}
        if source.get("metric_id") not in allowed.get(metric_id, {}).get(relation, set()):
            errors.append(f"{label}的数量Owner与relation不一致")
        source_ids = source.get("source_node_ids")
        if not isinstance(source_ids, list) or not source_ids or len(source_ids) != len(set(source_ids)) or any(not non_empty(value) for value in source_ids):
            errors.append(f"{label}的来源节点ID无效")
        source_dimensions = source.get("instance_dimensions")
        if not isinstance(source_dimensions, dict) or not source_dimensions or any(not non_empty(name) or not non_empty(value) for name, value in source_dimensions.items()):
            errors.append(f"{label}的来源实例维度无效")
        shared_event = binding.get("shared_semantic_event_set_id")
        if not non_empty(shared_event) or shared_event not in node.get("semantic_event_set_ids", []):
            errors.append(f"{label}未绑定持久状态节点声明的共享语义事件集")
        if not is_sha256(binding.get("rule_evidence_sha256")):
            errors.append(f"{label}缺少有效规则证据SHA-256")
    return errors


def validate_matched_position_transition_bindings(node):
    bindings = node.get("attributes", {}).get("matched_position_transition_bindings")
    if bindings is None:
        return []
    if not isinstance(bindings, list) or not bindings:
        return [f"一一配对位置移动绑定必须为非空对象数组: {node.get('node_id')}"]
    required = {
        "transition_event",
        "from_observation_point",
        "to_observation_point",
        "semantic_event_set_id",
        "object_identity_rule",
        "pairing_rule",
        "complete_bijective_matching",
        "birth_or_death_possible",
        "reachable_position_pairs",
        "all_reachable_pairs_covered",
        "rule_evidence_sha256",
    }
    observations = node.get("attributes", {}).get("observation_points", [])
    position_domain = node.get("attributes", {}).get("position_domain", [])
    position_domain = position_domain if isinstance(position_domain, list) else []
    transition_bindings = node.get("attributes", {}).get("position_transition_bindings", [])
    transition_map = {
        binding.get("transition_event"): binding
        for binding in transition_bindings
        if isinstance(binding, dict) and non_empty(binding.get("transition_event"))
    } if isinstance(transition_bindings, list) else {}
    errors, events = [], set()
    for index, binding in enumerate(bindings, 1):
        label = f"{node.get('node_id')}第{index}条一一配对位置移动绑定"
        if not isinstance(binding, dict) or set(binding) != required:
            errors.append(f"{label}必须完整使用十一个固定字段")
            continue
        event = binding.get("transition_event")
        if not all(non_empty(binding.get(field)) for field in (
            "transition_event", "from_observation_point", "to_observation_point",
            "semantic_event_set_id", "object_identity_rule", "pairing_rule",
        )):
            errors.append(f"{label}包含空字段")
        if event in events:
            errors.append(f"一一配对位置移动绑定重复transition_event: {event}")
        events.add(event)
        if binding.get("from_observation_point") == binding.get("to_observation_point"):
            errors.append(f"{label}的前后观察点必须不同")
        if any(binding.get(field) not in observations for field in ("from_observation_point", "to_observation_point")):
            errors.append(f"{label}的前后观察点未写入observation_points")
        if binding.get("semantic_event_set_id") not in node.get("semantic_event_set_ids", []):
            errors.append(f"{label}的事件集未由持久状态节点声明")
        if binding.get("complete_bijective_matching") is not True or binding.get("birth_or_death_possible") is not False:
            errors.append(f"{label}必须证明完整一一配对且不存在对象出生或消失")
        pairs = binding.get("reachable_position_pairs")
        if not isinstance(pairs, list) or not pairs:
            errors.append(f"{label}缺少非空reachable_position_pairs")
        else:
            pair_keys, pair_ids = [], []
            for pair_index, pair in enumerate(pairs, 1):
                pair_label = f"{label}第{pair_index}个可达位置对"
                if not isinstance(pair, dict) or set(pair) != {"pair_id", "origin_position_id", "destination_position_id"}:
                    errors.append(f"{pair_label}必须完整使用pair_id、origin_position_id和destination_position_id")
                    continue
                pair_id = pair.get("pair_id")
                origin = pair.get("origin_position_id")
                destination = pair.get("destination_position_id")
                if not non_empty(pair_id) or "::" in pair_id or "|" in pair_id:
                    errors.append(f"{pair_label}的pair_id必须为非空且不得包含::或|")
                if origin not in position_domain or destination not in position_domain:
                    errors.append(f"{pair_label}使用了position_domain之外的位置")
                if origin == destination:
                    errors.append(f"{pair_label}不得把未移动对象写入移动位置对")
                pair_keys.append((origin, destination))
                pair_ids.append(pair_id)
            if len(pair_keys) != len(set(pair_keys)) or len(pair_ids) != len(set(pair_ids)):
                errors.append(f"{label}的reachable_position_pairs存在重复pair_id或位置对")
        if binding.get("all_reachable_pairs_covered") is not True:
            errors.append(f"{label}必须证明reachable_position_pairs覆盖全部结构可达移动")
        if not is_sha256(binding.get("rule_evidence_sha256")):
            errors.append(f"{label}缺少有效规则证据SHA-256")
        transition = transition_map.get(event)
        if transition is None or any(
            transition.get(field) != binding.get(field)
            for field in ("from_observation_point", "to_observation_point", "semantic_event_set_id")
        ):
            errors.append(f"{label}未与同一position_transition_bindings事件逐字段一致")
    return errors


def validate_resource_count_derivation_bindings(node):
    attributes = node.get("attributes", {})
    bindings = attributes.get("resource_count_derivation_bindings")
    if bindings is None:
        return []
    if not isinstance(bindings, list) or not bindings:
        return [f"Feature资源数量派生绑定必须为非空对象数组: {node.get('node_id')}"]
    allowed_by_mechanic = {
        "feature.free-spin": {
            "free_spin.initial_grant_distribution",
            "free_spin.retrigger_grant_distribution",
        },
        "feature.respin": {
            "respin.initial_grant_distribution",
            "respin.extension_grant_distribution",
        },
        "feature.hold-and-spin": {"hold_spin.initial_occupancy_distribution"},
    }
    required = {
        "derived_metric_id",
        "derived_instance_dimensions",
        "primary_owner_metric_instance",
        "shared_semantic_event_set_id",
        "relation",
        "source_count_to_resource_count",
        "mapping_total_and_deterministic",
        "source_count_sufficient",
        "extra_random_or_state_dependency",
        "rule_evidence_sha256",
    }
    errors, identities = [], set()
    for index, binding in enumerate(bindings, 1):
        label = f"{node.get('node_id')}第{index}条Feature资源派生绑定"
        if not isinstance(binding, dict) or set(binding) != required:
            errors.append(f"{label}必须完整使用固定字段")
            continue
        metric_id = binding.get("derived_metric_id")
        if metric_id not in allowed_by_mechanic.get(node.get("mechanic_id"), set()):
            errors.append(f"{label}的derived_metric_id与Feature玩法不一致: {metric_id}")
        dimensions = binding.get("derived_instance_dimensions")
        if not isinstance(dimensions, dict) or any(
            not non_empty(name) or not isinstance(value, (str, int, float, bool)) or not non_empty(value)
            for name, value in dimensions.items()
        ):
            errors.append(f"{label}的derived_instance_dimensions无效")
            dimensions = {}
        identity = metric_id, dimensions_key(dimensions)
        if identity in identities:
            errors.append(f"{label}重复绑定同一派生指标实例")
        identities.add(identity)
        source = binding.get("primary_owner_metric_instance")
        source_fields = {"metric_id", "source_node_ids", "instance_dimensions", "target_group_id"}
        if not isinstance(source, dict) or set(source) != source_fields:
            errors.append(f"{label}的primary_owner_metric_instance必须完整使用固定字段")
            source = {}
        if source.get("metric_id") not in FEATURE_RESOURCE_SOURCE_METRICS:
            errors.append(f"{label}只能引用Board或Trigger数量主Owner")
        source_ids = source.get("source_node_ids")
        if not isinstance(source_ids, list) or not source_ids or any(not non_empty(value) for value in source_ids) or len(source_ids) != len(set(source_ids)):
            errors.append(f"{label}的来源节点ID无效")
        source_dimensions = source.get("instance_dimensions")
        if not isinstance(source_dimensions, dict) or any(
            not non_empty(name) or not isinstance(value, (str, int, float, bool)) or not non_empty(value)
            for name, value in source_dimensions.items()
        ):
            errors.append(f"{label}的来源实例维度无效")
        target_group_id = source.get("target_group_id")
        if source.get("metric_id") == "board.symbol_count_per_board_distribution" and not non_empty(target_group_id):
            errors.append(f"{label}引用盘面数量Owner时必须指定真实symbol_id目标组")
        if source.get("metric_id") == "trigger.symbol_count_distribution" and target_group_id is not None:
            errors.append(f"{label}引用Trigger数量Owner时target_group_id必须为null")
        relation = binding.get("relation")
        if relation != FEATURE_RESOURCE_METRICS.get(metric_id):
            errors.append(f"{label}的事件投影关系与指标语义不一致")
        shared_event = binding.get("shared_semantic_event_set_id")
        if not non_empty(shared_event) or shared_event not in node.get("semantic_event_set_ids", []):
            errors.append(f"{label}未绑定Feature节点声明的共享语义事件集")
        mapping = binding.get("source_count_to_resource_count")
        valid_mapping = isinstance(mapping, dict) and bool(mapping)
        if valid_mapping:
            for source_count, resource_count in mapping.items():
                try:
                    parsed = float(source_count)
                except (TypeError, ValueError):
                    valid_mapping = False
                    break
                if parsed < 0 or not parsed.is_integer():
                    valid_mapping = False
                    break
                if resource_count is not None and (
                    not isinstance(resource_count, int) or isinstance(resource_count, bool) or resource_count < 0
                ):
                    valid_mapping = False
                    break
        if not valid_mapping:
            errors.append(f"{label}的计数到资源映射必须使用非负整数计数和非负整数或null结果")
        elif relation == "same_event_pushforward" and any(value is None for value in mapping.values()):
            errors.append(f"{label}的同事件推送映射不得使用null，未追加必须映射为0")
        if binding.get("mapping_total_and_deterministic") is not True or binding.get("source_count_sufficient") is not True:
            errors.append(f"{label}必须证明映射完整确定且来源计数充分")
        if binding.get("extra_random_or_state_dependency") is not False:
            errors.append(f"{label}存在额外随机、位置、状态或玩家选择依赖时不得派生")
        if not is_sha256(binding.get("rule_evidence_sha256")):
            errors.append(f"{label}缺少有效规则证据SHA-256")
    return errors


def metric_instance_key(item):
    source_ids = item.get("source_node_ids", [])
    if not isinstance(source_ids, list) or not all(isinstance(value, str) for value in source_ids):
        source_ids = []
    dimensions = item.get("instance_dimensions", {})
    if not isinstance(dimensions, dict):
        dimensions = {}
    return item.get("metric_id"), tuple(sorted(source_ids)), dimensions_key(dimensions)


def format_instance(key):
    metric_id, source_ids, dimensions = key
    suffix = ",".join(f"{name}={value}" for name, value in dimensions)
    return f"{metric_id}[{','.join(source_ids) or 'core'}{';' + suffix if suffix else ''}]"


def dimensions_key(dimensions):
    if not isinstance(dimensions, dict):
        return ()
    values = [
        (str(name), value if isinstance(value, (str, int, float, bool)) else json.dumps(value, ensure_ascii=False, sort_keys=True))
        for name, value in dimensions.items()
    ]
    return tuple(sorted(values, key=lambda item: item[0]))


def dimension_mapping_sort_key(item):
    dimensions, _ = item
    return json.dumps(dict(dimensions), ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def instance_sort_key(key):
    return format_instance(key)


def metric_dimension_names(metric):
    template = metric.get("scope_template", "")
    tokens = {token.strip() for token in re.split(r"[×|]", template) if token.strip()}
    return tokens & INSTANCE_DIMENSION_KEYS


def declared_dimension_domains(metric, source_ids, active_node_map, names=None):
    names = metric_dimension_names(metric) if names is None else set(names)
    domains = {}
    nodes = [active_node_map[node_id] for node_id in source_ids if node_id in active_node_map]
    if "entry_source" in names:
        values = sorted(set().union(*(alignment_entry_sources(node) for node in nodes))) if nodes else []
        if values:
            domains["entry_source"] = values
    if "entry_source_domain" in names:
        domains["entry_source_domain"] = ["endogenous"]
    if "board_phase" in names:
        values = []
        for node in nodes:
            domain = node.get("attributes", {}).get("board_phase_domain")
            values.extend(domain if isinstance(domain, list) else [domain] if non_empty(domain) else [])
        if values:
            domains["board_phase"] = sorted(set(values), key=str)
    if "actual_capacity" in names:
        values = []
        for node in nodes:
            attributes = node.get("attributes", {})
            domain = attributes.get("actual_capacity_domain", attributes.get("board_capacity"))
            values.extend(domain if isinstance(domain, list) else [domain] if non_empty(domain) else [])
            capacity_map = attributes.get("position_domain_by_actual_capacity")
            if isinstance(capacity_map, dict):
                values.extend(integer_token(value) for value in capacity_map)
        values = [value for value in values if value is not None]
        if values:
            domains["actual_capacity"] = sorted(set(values), key=str)
    if {"current_actual_capacity", "next_actual_capacity"} & names:
        values = []
        for node in nodes:
            attributes = node.get("attributes", {})
            capacity_map = attributes.get("position_domain_by_actual_capacity")
            if isinstance(capacity_map, dict):
                values.extend(integer_token(value) for value in capacity_map)
            domain = attributes.get("actual_capacity_domain")
            values.extend(domain if isinstance(domain, list) else [])
        values = [value for value in values if value is not None]
        if values:
            values = sorted(set(values))
            if "current_actual_capacity" in names:
                domains["current_actual_capacity"] = values
            if "next_actual_capacity" in names:
                domains["next_actual_capacity"] = values
    if "capacity_observation_point" in names:
        values = []
        for node in nodes:
            domain = node.get("attributes", {}).get("capacity_observation_points")
            values.extend(domain if isinstance(domain, list) else [domain] if non_empty(domain) else [])
        if values:
            domains["capacity_observation_point"] = list(dict.fromkeys(values))
    if "state_id" in names:
        values = [node.get("attributes", {}).get("state_id") for node in nodes]
        values = [value for value in values if non_empty(value)]
        if values:
            domains["state_id"] = sorted(set(values), key=str)
    if "observation_point" in names:
        values = []
        for node in nodes:
            domain = node.get("attributes", {}).get("observation_points")
            values.extend(domain if isinstance(domain, list) else [domain] if non_empty(domain) else [])
        if values:
            domains["observation_point"] = sorted(set(values), key=str)
    if "transition_event" in names:
        values = []
        for node in nodes:
            domain = node.get("attributes", {}).get("transition_event_domain")
            values.extend(domain if isinstance(domain, list) else [domain] if non_empty(domain) else [])
        if values:
            domains["transition_event"] = sorted(set(values), key=str)
    if "capacity_scope" in names:
        values = [node.get("attributes", {}).get("capacity_scope") for node in nodes]
        values = [value for value in values if non_empty(value)]
        if values:
            domains["capacity_scope"] = sorted(set(values), key=str)
    if "geometry_layout" in names:
        values = []
        for node in nodes:
            domain = node.get("attributes", {}).get("geometry_layout_domain")
            values.extend(domain if isinstance(domain, list) else [domain] if non_empty(domain) else [])
        if values:
            domains["geometry_layout"] = sorted(set(values), key=str)
    if "jackpot_opportunity_set" in names:
        values = []
        for node in nodes:
            exposure = node.get("attributes", {}).get("jackpot_tier_exposure")
            if isinstance(exposure, list):
                values.extend(
                    row.get("opportunity_set_id")
                    for row in exposure
                    if isinstance(row, dict) and non_empty(row.get("opportunity_set_id"))
                )
        if values:
            domains["jackpot_opportunity_set"] = sorted(set(values), key=str)
    return domains


def metric_dimensions(metric, source_ids, scope_instances, active_node_map, errors):
    names = metric_dimension_names(metric)
    template = metric.get("scope_template", "")
    nodes = [active_node_map[node_id] for node_id in source_ids if node_id in active_node_map]
    variable_position_capacity = any(
        isinstance(node.get("attributes", {}).get("position_domain_by_actual_capacity"), dict)
        and node.get("attributes", {}).get("position_domain_by_actual_capacity")
        for node in nodes
    )
    if variable_position_capacity and "actual_capacity_if_variable" in template:
        names.add("actual_capacity")
    if variable_position_capacity and "current_actual_capacity_if_variable" in template:
        names.add("current_actual_capacity")
    if variable_position_capacity and "next_actual_capacity_if_variable" in template:
        names.add("next_actual_capacity")
    candidates = [
        scope for scope in scope_instances
        if set(source_ids).issubset(scope.get("source_node_ids", []))
        and scope.get("sample_unit") == metric.get("sample_unit")
        and (scope.get("scope_role") == "core") == (not source_ids)
    ]
    collect_pairs = None
    if metric.get("metric_id") in {
        "collect.output_value_given_input_count_distribution",
        "collect.output_category_given_input_count_distribution",
    }:
        collect_nodes = [
            active_node_map[node_id] for node_id in source_ids
            if node_id in active_node_map and active_node_map[node_id].get("mechanic_id") == "modifier.collect"
        ]
        if len(collect_nodes) == 1:
            _, ordered, categorical = validate_collect_output_maps(collect_nodes[0].get("attributes", {}))
            collect_pairs = set(ordered if metric.get("metric_id") == "collect.output_value_given_input_count_distribution" else categorical)
            candidates = [
                scope for scope in candidates
                if (
                    scope.get("dimensions", {}).get("output_semantic"),
                    scope.get("dimensions", {}).get("output_unit"),
                ) in collect_pairs
            ]
    if metric.get("owner") == "core.general" and not source_ids:
        candidates = [
            scope for scope in candidates
            if scope.get("dimensions", {}).get("component") in {None, "overall"}
        ]
    if "entry_source:feature_buy" in metric.get("scope_template", ""):
        if nodes and not has_feature_buy(nodes):
            scope_prefix = "&".join(sorted({node.get("scope", "feature") for node in nodes}))
            virtual_scope = {
                "scope_instance_id": f"virtual-na:{metric.get('metric_id')}:{','.join(sorted(source_ids))}",
                "scope": f"{scope_prefix}|entry_source=feature_buy",
                "scope_role": "mechanic",
                "source_node_ids": sorted(source_ids),
                "sample_unit": metric.get("sample_unit"),
                "dimensions": {"entry_source": "feature_buy"},
                "virtual_na": True,
            }
            return [({"entry_source": "feature_buy"}, virtual_scope)]
        matched = [scope for scope in candidates if scope.get("dimensions", {}).get("entry_source") == "feature_buy"]
        if len(matched) != 1:
            errors.append(f"Feature Buy指标必须唯一绑定feature_buy scope_instance: {metric.get('metric_id')}")
        return [({"entry_source": "feature_buy"}, matched[0] if len(matched) == 1 else None)]
    if not names:
        if len(candidates) > 1:
            event_sets = {scope.get("semantic_event_set_id") for scope in candidates}
            if len(event_sets) > 1:
                errors.append(f"指标作用域实例缺少区分维度: {metric.get('metric_id')} / {','.join(sorted(source_ids))}")
        return [({}, candidates[0] if candidates else None)]
    domains = declared_dimension_domains(metric, source_ids, active_node_map, names)
    result = {}
    for scope in candidates:
        dimensions = scope.get("dimensions", {})
        selected = {name: dimensions[name] for name in sorted(names) if name in dimensions}
        if set(selected) != names:
            continue
        if any(name in domains and value not in domains[name] for name, value in selected.items()):
            continue
        key = dimensions_key(selected)
        if key in result:
            errors.append(f"相同指标维度重复绑定scope_instance: {metric.get('metric_id')} / {dict(key)}")
            continue
        result[key] = scope
    if domains:
        domain_names = sorted(domains)
        for values in itertools.product(*(domains[name] for name in domain_names)):
            required = dict(zip(domain_names, values))
            if not any(all(dict(key).get(name) == value for name, value in required.items()) for key in result):
                errors.append(f"画像声明维度缺少scope_instance: {metric.get('metric_id')} / {required}")
    if collect_pairs is not None:
        actual_pairs = {
            (dict(key).get("output_semantic"), dict(key).get("output_unit"))
            for key in result
        }
        missing_pairs = sorted(collect_pairs - actual_pairs)
        if missing_pairs:
            errors.append(f"Collect画像输出映射缺少scope_instance: {metric.get('metric_id')} / {missing_pairs}")
    if not result:
        errors.append(f"画像scope_instances无法实例化指标维度: {metric.get('metric_id')} / {','.join(sorted(names))}")
    return [(dict(key), scope) for key, scope in sorted(result.items(), key=dimension_mapping_sort_key)]


def validate_schema(data, schema_path, label):
    if Draft202012Validator is None:
        return ["缺少jsonschema依赖，无法执行任务语义Schema校验"]
    schema = load(schema_path)
    errors = []
    for error in sorted(Draft202012Validator(schema).iter_errors(data), key=lambda item: tuple(map(str, item.absolute_path))):
        path = ".".join(map(str, error.absolute_path)) or "$"
        errors.append(f"{label}不符合Schema: {path} / {error.message}")
    return errors


def indexed_catalogs(skill_root, kind):
    base = Path(skill_root) / "references" / CATALOG_DIRECTORY_NAMES[kind]
    index_path = base / "index.json"
    index = load(index_path)
    catalogs, errors = {}, []
    for entry in index.get("packages", []):
        path = base / entry.get("path", "")
        if not path.is_file():
            errors.append(
                f"目录索引引用不存在文件: references/{CATALOG_DIRECTORY_NAMES[kind]}/{entry.get('path')}"
            )
            continue
        if entry.get("sha256") != sha(path):
            errors.append(f"目录包hash失效: {entry.get('package_id')}")
        data = load(path)
        if data.get("package_id") != entry.get("package_id"):
            errors.append(f"目录包ID与索引不一致: {entry.get('package_id')}")
        catalogs[entry.get("package_id")] = data
    return index_path, index, catalogs, errors


def catalog_maps(skill_root):
    mechanic_index_path, mechanic_index, mechanic_packages, errors = indexed_catalogs(skill_root, "mechanics")
    metric_index_path, metric_index, metric_packages, metric_errors = indexed_catalogs(skill_root, "metrics")
    errors += metric_errors
    mechanics, metrics = {}, {}
    for package in mechanic_packages.values():
        for mechanic in package.get("mechanics", []):
            mechanic_id = mechanic.get("mechanic_id")
            if mechanic_id in mechanics:
                errors.append(f"目录mechanic_id重复: {mechanic_id}")
            mechanics[mechanic_id] = mechanic
    for package_id, package in metric_packages.items():
        for metric in package.get("metrics", []):
            metric_id = metric.get("metric_id")
            if metric_id in metrics:
                errors.append(f"目录metric_id重复: {metric_id}")
            metrics[metric_id] = metric
            if metric.get("owner") != package_id:
                errors.append(f"目录指标Owner不一致: {metric_id}")
    return {
        "mechanics_index_path": mechanic_index_path,
        "mechanics_index": mechanic_index,
        "metrics_index_path": metric_index_path,
        "metrics_index": metric_index,
        "mechanics": mechanics,
        "metric_packages": metric_packages,
        "metrics": metrics,
        "errors": errors,
    }


def node_key(node, position):
    return node.get("node_id") or f"{node.get('mechanic_id')}@{node.get('scope')}#{position}"


def compare(operator, actual, expected=None):
    if actual is MISSING:
        return operator == "not_exists"
    if operator == "exists":
        return non_empty(actual)
    if operator == "not_exists":
        return not non_empty(actual)
    if operator == "truthy":
        return semantic_truthy(actual)
    if operator == "falsy":
        return not semantic_truthy(actual)
    if operator == "equals":
        return actual == expected
    if operator == "not_equals":
        return actual != expected
    if operator == "in":
        return isinstance(expected, (list, tuple, set)) and actual in expected
    if operator == "not_in":
        return isinstance(expected, (list, tuple, set)) and actual not in expected
    if operator == "contains":
        try:
            return expected in actual
        except TypeError:
            return False
    try:
        if operator == "gt":
            return actual > expected
        if operator == "gte":
            return actual >= expected
        if operator == "lt":
            return actual < expected
        if operator == "lte":
            return actual <= expected
    except TypeError:
        return False
    return False


def condition_matches(condition, nodes):
    if condition.get("always") is True:
        return [set()]
    if len([key for key in ("mechanic_id", "mechanic_id_any", "mechanic_id_all") if key in condition]) > 1:
        return []
    indexed_nodes = list(enumerate(nodes))
    matches = []
    if condition.get("mechanic_id"):
        alternatives = [[item] for item in indexed_nodes if item[1].get("mechanic_id") == condition["mechanic_id"]]
    elif condition.get("mechanic_id_any"):
        allowed = set(condition["mechanic_id_any"])
        alternatives = [[item] for item in indexed_nodes if item[1].get("mechanic_id") in allowed]
    elif condition.get("mechanic_id_all"):
        groups = [
            [item for item in indexed_nodes if item[1].get("mechanic_id") == mechanic_id]
            for mechanic_id in condition["mechanic_id_all"]
        ]
        alternatives = [list(items) for items in itertools.product(*groups)] if all(groups) else []
    else:
        alternatives = [[]]
    for selected in alternatives:
        selected_by_id = {}
        for item in selected:
            selected_by_id.setdefault(item[1].get("mechanic_id"), []).append(item)
        candidate_groups, valid = [], True
        for mechanic_id, grouped_conditions in itertools.groupby(
            sorted(condition.get("attribute_conditions", []), key=lambda item: item.get("mechanic_id", "")),
            key=lambda item: item.get("mechanic_id"),
        ):
            conditions = list(grouped_conditions)
            candidates = selected_by_id.get(mechanic_id) or [item for item in indexed_nodes if item[1].get("mechanic_id") == mechanic_id]
            candidates = [item for item in candidates if all(
                compare(
                    rule.get("operator"),
                    item[1].get("attributes", {}).get(rule.get("attribute"), MISSING),
                    rule.get("value"),
                )
                for rule in conditions
            )]
            if not candidates:
                valid = False
                break
            candidate_groups.append(candidates)
        if not valid:
            continue
        expansions = itertools.product(*candidate_groups) if candidate_groups else [()]
        for additions in expansions:
            expanded_map = {position: (position, node) for position, node in [*selected, *additions]}
            expanded = list(expanded_map.values())
            required = condition.get("required_attributes", [])
            attribute_union = {
                key
                for _, node in expanded
                for key, value in node.get("attributes", {}).items()
                if semantic_truthy(value)
            }
            if not set(required).issubset(attribute_union):
                continue
            matches.append({node_key(node, position) for position, node in expanded})
    unique = {tuple(sorted(item)) for item in matches}
    return [set(item) for item in sorted(unique)]


def deep_subset(expected, actual, path=""):
    errors = []
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return [f"{path or '$'}类型不一致"]
        for key, value in expected.items():
            child = f"{path}.{key}" if path else key
            if key not in actual:
                errors.append(f"{child}缺失")
            else:
                errors += deep_subset(value, actual[key], child)
        return errors
    if expected != actual:
        errors.append(f"{path or '$'}与目录不一致")
    return errors


def validate_feature_control_contract(attributes, mechanic_id):
    errors = []
    graph = attributes.get("stage_graph")
    required_graph_fields = {"entry_stage", "stages", "transitions", "terminal_stages"}
    if not isinstance(graph, dict) or not required_graph_fields.issubset(graph):
        errors.append(f"Feature阶段图必须包含entry_stage、stages、transitions和terminal_stages: {mechanic_id}")
    else:
        stages = graph.get("stages")
        entry = graph.get("entry_stage")
        terminals = graph.get("terminal_stages")
        transitions = graph.get("transitions")
        valid_stages = (
            isinstance(stages, list)
            and bool(stages)
            and all(isinstance(stage, str) and stage.strip() for stage in stages)
            and len(stages) == len(set(stages))
        )
        if not valid_stages:
            errors.append(f"Feature阶段图stages必须为非空唯一字符串列表: {mechanic_id}")
            stages = []
        stage_set = set(stages)
        if not non_empty(entry) or entry not in stage_set:
            errors.append(f"Feature阶段图entry_stage必须属于stages: {mechanic_id}")
        if (
            not isinstance(terminals, list)
            or not terminals
            or not all(isinstance(stage, str) and stage.strip() for stage in terminals)
            or len(terminals) != len(set(terminals))
            or not set(terminals).issubset(stage_set)
        ):
            errors.append(f"Feature阶段图terminal_stages必须为stages中的非空唯一子集: {mechanic_id}")
            terminals = []
        if not isinstance(transitions, list):
            errors.append(f"Feature阶段图transitions必须为数组: {mechanic_id}")
            transitions = []
        edges, branch_keys = [], set()
        for index, transition in enumerate(transitions, 1):
            if not isinstance(transition, dict) or set(transition) != {"from_stage", "to_stage", "branch_id"}:
                errors.append(f"Feature阶段图转移必须只含from_stage、to_stage和branch_id: {mechanic_id} / {index}")
                continue
            source, target, branch = transition["from_stage"], transition["to_stage"], transition["branch_id"]
            if source not in stage_set or target not in stage_set or not non_empty(branch):
                errors.append(f"Feature阶段图转移引用未知阶段或空branch_id: {mechanic_id} / {index}")
                continue
            branch_key = (source, branch)
            if branch_key in branch_keys:
                errors.append(f"Feature阶段图同一来源阶段branch_id重复: {mechanic_id} / {source} / {branch}")
            branch_keys.add(branch_key)
            edges.append((source, target))
        if stage_set and non_empty(entry) and entry in stage_set:
            reachable = {entry}
            changed = True
            while changed:
                changed = False
                for source, target in edges:
                    if source in reachable and target not in reachable:
                        reachable.add(target)
                        changed = True
            if reachable != stage_set:
                errors.append(f"Feature阶段图存在从entry_stage不可达阶段: {mechanic_id} / {','.join(sorted(stage_set - reachable))}")
        terminal_set = set(terminals)
        if any(source in terminal_set for source, _ in edges):
            errors.append(f"Feature阶段图终止阶段不得继续转移: {mechanic_id}")
        if stage_set and terminal_set:
            can_finish = set(terminal_set)
            changed = True
            while changed:
                changed = False
                for source, target in edges:
                    if target in can_finish and source not in can_finish:
                        can_finish.add(source)
                        changed = True
            if can_finish != stage_set:
                errors.append(f"Feature阶段图存在无法到达终止阶段的节点: {mechanic_id} / {','.join(sorted(stage_set - can_finish))}")

    signature = attributes.get("path_signature_definition")
    required_signature_fields = {"path_id_domain", "included_fields", "excluded_fields", "canonicalization_rule"}
    if not isinstance(signature, dict) or not required_signature_fields.issubset(signature):
        errors.append(f"Feature路径签名必须包含path_id_domain、included_fields、excluded_fields和canonicalization_rule: {mechanic_id}")
        return errors
    path_ids = signature.get("path_id_domain")
    if (
        not isinstance(path_ids, list)
        or not path_ids
        or not all(non_empty(path_id) for path_id in path_ids)
        or len(path_ids) != len(set(path_ids))
    ):
        errors.append(f"Feature路径签名path_id_domain必须为非空唯一字符串列表: {mechanic_id}")
    included = signature.get("included_fields")
    valid_included = isinstance(included, list) and all(isinstance(field, str) for field in included)
    if not valid_included or len(included) != len(set(included)) or set(included) != FEATURE_PATH_INCLUDED_FIELDS:
        errors.append(f"Feature路径签名included_fields必须且只能包含control_stage_id和branch_id: {mechanic_id}")
    excluded = signature.get("excluded_fields")
    valid_excluded = isinstance(excluded, list) and all(isinstance(field, str) for field in excluded)
    if (
        not valid_excluded
        or len(excluded) != len(set(excluded))
        or not FEATURE_PATH_REQUIRED_EXCLUDED_FIELDS.issubset(set(excluded))
        or FEATURE_PATH_INCLUDED_FIELDS.intersection(excluded)
    ):
        errors.append(f"Feature路径签名必须排除奖励结果、状态值、时长和回报桶且不得排除控制流字段: {mechanic_id}")
    if not non_empty(signature.get("canonicalization_rule")):
        errors.append(f"Feature路径签名缺少规范化规则: {mechanic_id}")
    return errors


def bonus_sequence_cyclic_transition_keys(graph):
    stages = graph.get("stages", []) if isinstance(graph, dict) else []
    transitions = graph.get("transitions", []) if isinstance(graph, dict) else []
    adjacency = {stage: set() for stage in stages if isinstance(stage, str)}
    for transition in transitions:
        if isinstance(transition, dict):
            adjacency.setdefault(transition.get("from_stage"), set()).add(transition.get("to_stage"))

    def reachable(start, target):
        pending, seen = [start], set()
        while pending:
            current = pending.pop()
            if current == target:
                return True
            if current in seen:
                continue
            seen.add(current)
            pending.extend(adjacency.get(current, ()))
        return False

    return {
        (transition.get("from_stage"), transition.get("branch_id"), transition.get("to_stage"))
        for transition in transitions
        if isinstance(transition, dict)
        and reachable(transition.get("to_stage"), transition.get("from_stage"))
    }


def enumerate_bonus_sequence_paths(attributes):
    graph = attributes.get("stage_graph", {})
    transitions = graph.get("transitions", []) if isinstance(graph, dict) else []
    outgoing = {}
    for transition in transitions:
        if isinstance(transition, dict):
            outgoing.setdefault(transition.get("from_stage"), []).append(transition)
    loop = attributes.get("stage_loop_contract")
    limits = {}
    if isinstance(loop, dict):
        for row in loop.get("cyclic_transitions", []):
            if isinstance(row, dict):
                key = (row.get("from_stage"), row.get("branch_id"), row.get("to_stage"))
                limits[key] = row.get("max_transition_count")
    terminals = set(graph.get("terminal_stages", [])) if isinstance(graph, dict) else set()
    entry = graph.get("entry_stage") if isinstance(graph, dict) else None
    paths, errors = [], []

    def visit(stage, path, counts):
        if len(paths) > 10000:
            return
        if stage in terminals:
            paths.append(tuple(path))
            return
        options = outgoing.get(stage, [])
        if not options:
            return
        for transition in options:
            key = (transition.get("from_stage"), transition.get("branch_id"), transition.get("to_stage"))
            limit = limits.get(key)
            used = counts.get(key, 0)
            if limit is not None and used >= limit:
                continue
            next_counts = dict(counts)
            if limit is not None:
                next_counts[key] = used + 1
            visit(transition.get("to_stage"), [*path, key], next_counts)

    visit(entry, [], {})
    if len(paths) > 10000:
        errors.append("Bonus Sequence有限路径枚举超过10000条")
    if len(paths) != len(set(paths)):
        errors.append("Bonus Sequence有限路径枚举存在重复规范路径")
    return paths[:10001], errors


def validate_bonus_sequence_structure(node):
    attributes = node.get("attributes", {})
    node_id = node.get("node_id")
    errors = []
    if attributes.get("feature_cycle_owner_node_id") != node_id:
        errors.append(f"Bonus Sequence完整周期Owner必须等于当前节点: {node_id}")
    boundary = attributes.get("sequence_boundary_rule")
    boundary_fields = {
        "cycle_id_field", "start_event_id", "terminal_event_id", "complete_cycle_semantic_event_set_id",
        "start_event_occurs_once", "terminal_event_occurs_once", "no_additional_wager_inside_cycle",
    }
    if not isinstance(boundary, dict) or set(boundary) != boundary_fields:
        errors.append(f"Bonus Sequence周期边界必须完整使用七个固定字段: {node_id}")
    elif (
        not all(non_empty(boundary.get(field)) for field in (
            "cycle_id_field", "start_event_id", "terminal_event_id", "complete_cycle_semantic_event_set_id",
        ))
        or any(boundary.get(field) is not True for field in (
            "start_event_occurs_once", "terminal_event_occurs_once", "no_additional_wager_inside_cycle",
        ))
        or boundary.get("complete_cycle_semantic_event_set_id") not in node.get("semantic_event_set_ids", [])
    ):
        errors.append(f"Bonus Sequence周期必须有稳定身份、唯一开始/结束、完整事件集且周期内无追加投注: {node_id}")

    graph = attributes.get("stage_graph", {})
    stages = graph.get("stages", []) if isinstance(graph, dict) else []
    terminals = set(graph.get("terminal_stages", [])) if isinstance(graph, dict) else set()
    bindings = attributes.get("stage_action_bindings")
    if not isinstance(bindings, list) or len(bindings) != len(stages):
        errors.append(f"Bonus Sequence stage_action_bindings必须恰好覆盖全部阶段: {node_id}")
        bindings = []
    by_stage, action_mechanics = {}, set()
    binding_fields = {
        "stage_id", "stage_role", "action_node_id", "action_mechanic_id", "semantic_event_set_id",
        "completion_event_id", "random_owner_node_ids", "payout_owner_node_ids",
    }
    for binding in bindings:
        if not isinstance(binding, dict) or set(binding) != binding_fields:
            errors.append(f"Bonus Sequence阶段动作绑定字段不完整: {node_id}")
            continue
        stage_id, role = binding.get("stage_id"), binding.get("stage_role")
        if stage_id in by_stage:
            errors.append(f"Bonus Sequence阶段动作绑定重复: {node_id}/{stage_id}")
        by_stage[stage_id] = binding
        owners_valid = all(
            isinstance(binding.get(field), list)
            and len(binding[field]) == len(set(binding[field]))
            and all(non_empty(value) for value in binding[field])
            for field in ("random_owner_node_ids", "payout_owner_node_ids")
        )
        if not owners_valid:
            errors.append(f"Bonus Sequence随机与派奖Owner必须为唯一节点ID列表: {node_id}/{stage_id}")
        if role == "typed_action":
            if not all(non_empty(binding.get(field)) for field in (
                "action_node_id", "action_mechanic_id", "semantic_event_set_id", "completion_event_id",
            )):
                errors.append(f"Bonus Sequence动作阶段缺少类型化玩法、事件集或完成事件: {node_id}/{stage_id}")
            action_mechanics.add(binding.get("action_mechanic_id"))
        elif role in {"control", "terminal"}:
            if any(binding.get(field) is not None for field in (
                "action_node_id", "action_mechanic_id", "semantic_event_set_id", "completion_event_id",
            )) or binding.get("random_owner_node_ids") or binding.get("payout_owner_node_ids"):
                errors.append(f"Bonus Sequence控制或终止阶段不得拥有动作、随机或派奖: {node_id}/{stage_id}")
        else:
            errors.append(f"Bonus Sequence stage_role无效: {node_id}/{stage_id}")
        if role == "terminal" and stage_id not in terminals or role != "terminal" and stage_id in terminals:
            errors.append(f"Bonus Sequence终止阶段角色与terminal_stages不一致: {node_id}/{stage_id}")
    if set(by_stage) != set(stages):
        errors.append(f"Bonus Sequence阶段动作绑定阶段集合不完整: {node_id}")
    if len(action_mechanics) < 2:
        errors.append(f"Bonus Sequence至少需要两种不同的非Feature动作玩法: {node_id}")

    transitions = graph.get("transitions", []) if isinstance(graph, dict) else []
    transition_keys = {
        (row.get("from_stage"), row.get("branch_id"), row.get("to_stage"))
        for row in transitions if isinstance(row, dict)
    }
    resolution = attributes.get("transition_resolution_rule")
    resolutions = resolution.get("branch_resolutions") if isinstance(resolution, dict) else None
    resolution_fields = {"from_stage", "branch_id", "to_stage", "resolution_type", "owner_node_id", "outcome_id"}
    if not isinstance(resolution, dict) or set(resolution) != {"anonymous_random_routing", "branch_resolutions"} or resolution.get("anonymous_random_routing") is not False:
        errors.append(f"Bonus Sequence分支解析必须禁止匿名随机路由: {node_id}")
        resolutions = []
    resolved_keys = []
    for row in resolutions if isinstance(resolutions, list) else []:
        if not isinstance(row, dict) or set(row) != resolution_fields:
            errors.append(f"Bonus Sequence分支解析字段不完整: {node_id}")
            continue
        key = (row.get("from_stage"), row.get("branch_id"), row.get("to_stage"))
        resolved_keys.append(key)
        if row.get("resolution_type") == "deterministic_control":
            if row.get("owner_node_id") is not None or row.get("outcome_id") is not None:
                errors.append(f"确定性Bonus分支不得声明随机Owner或结果: {node_id}/{key}")
        elif row.get("resolution_type") == "owned_mechanic_outcome":
            if not non_empty(row.get("owner_node_id")) or not non_empty(row.get("outcome_id")):
                errors.append(f"玩法结果Bonus分支缺少Owner或结果ID: {node_id}/{key}")
        else:
            errors.append(f"Bonus Sequence分支解析类型无效: {node_id}/{key}")
    if set(resolved_keys) != transition_keys or len(resolved_keys) != len(set(resolved_keys)):
        errors.append(f"Bonus Sequence分支解析必须逐条且仅覆盖阶段图全部转移: {node_id}")

    cyclic_keys = bonus_sequence_cyclic_transition_keys(graph)
    loop = attributes.get("stage_loop_contract")
    loop_rows = loop.get("cyclic_transitions") if isinstance(loop, dict) else None
    declared_cyclic = []
    if cyclic_keys:
        if not isinstance(loop, dict) or set(loop) != {"termination_measure", "cyclic_transitions"} or not non_empty(loop.get("termination_measure")):
            errors.append(f"Bonus Sequence存在环时必须密封逐循环边有限上限: {node_id}")
            loop_rows = []
        for row in loop_rows if isinstance(loop_rows, list) else []:
            if not isinstance(row, dict) or set(row) != {"from_stage", "branch_id", "to_stage", "max_transition_count"}:
                errors.append(f"Bonus Sequence循环边上限字段不完整: {node_id}")
                continue
            key = (row.get("from_stage"), row.get("branch_id"), row.get("to_stage"))
            declared_cyclic.append(key)
            limit = row.get("max_transition_count")
            if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 1000:
                errors.append(f"Bonus Sequence循环边max_transition_count必须为1至1000: {node_id}/{key}")
        if set(declared_cyclic) != cyclic_keys or len(declared_cyclic) != len(set(declared_cyclic)):
            errors.append(f"Bonus Sequence stage_loop_contract必须恰好覆盖全部循环边: {node_id}")
    elif loop is not None:
        errors.append(f"无环Bonus Sequence不得声明stage_loop_contract: {node_id}")

    paths, path_errors = enumerate_bonus_sequence_paths(attributes)
    errors += path_errors
    if not paths:
        errors.append(f"Bonus Sequence阶段图没有有限终止路径: {node_id}")
    signature = attributes.get("path_signature_definition", {})
    signatures = signature.get("path_signatures") if isinstance(signature, dict) else None
    path_ids = signature.get("path_id_domain") if isinstance(signature, dict) else None
    declared_paths, declared_ids = {}, []
    for row in signatures if isinstance(signatures, list) else []:
        if not isinstance(row, dict) or set(row) != {"path_id", "transitions"}:
            errors.append(f"Bonus Sequence路径签名字段不完整: {node_id}")
            continue
        path_id = row.get("path_id")
        values = row.get("transitions")
        if not non_empty(path_id) or not isinstance(values, list):
            errors.append(f"Bonus Sequence路径签名缺少path_id或转移序列: {node_id}")
            continue
        key = tuple(
            (value.get("from_stage"), value.get("branch_id"), value.get("to_stage"))
            for value in values if isinstance(value, dict) and set(value) == {"from_stage", "branch_id", "to_stage"}
        )
        if len(key) != len(values) or path_id in declared_paths:
            errors.append(f"Bonus Sequence路径签名转移格式无效或path_id重复: {node_id}/{path_id}")
        declared_paths[path_id] = key
        declared_ids.append(path_id)
    if path_ids != declared_ids or set(declared_paths.values()) != set(paths) or len(declared_paths) != len(paths):
        errors.append(f"Bonus Sequence路径签名必须与完整有限路径集合精确相等: {node_id}")
    if signature.get("canonicalization_rule") != "ordered_control_stage_and_branch_sequence_v1":
        errors.append(f"Bonus Sequence路径规范化规则无效: {node_id}")

    projection = attributes.get("stage_action_count_projection")
    rows = projection.get("path_action_counts") if isinstance(projection, dict) else None
    if not isinstance(projection, dict) or set(projection) != {"projector_id", "path_action_counts"} or projection.get("projector_id") != "stage_path_to_primary_action_count_v1":
        errors.append(f"Bonus Sequence动作次数投影合同无效: {node_id}")
        rows = []
    projected = {}
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or set(row) != {"path_id", "typed_action_stage_ids", "primary_action_count"}:
            errors.append(f"Bonus Sequence路径动作次数项字段不完整: {node_id}")
            continue
        path_id = row.get("path_id")
        if path_id in projected:
            errors.append(f"Bonus Sequence路径动作次数投影重复path_id: {node_id}/{path_id}")
        projected[path_id] = row
    for path_id, transitions_path in declared_paths.items():
        visited = [graph.get("entry_stage"), *(value[2] for value in transitions_path)]
        expected_stages = [stage for stage in visited if by_stage.get(stage, {}).get("stage_role") == "typed_action"]
        row = projected.get(path_id)
        if not isinstance(row, dict) or row.get("typed_action_stage_ids") != expected_stages or row.get("primary_action_count") != len(expected_stages):
            errors.append(f"Bonus Sequence主要动作次数未按路径逐阶段复算一致: {node_id}/{path_id}")
    if set(projected) != set(declared_paths):
        errors.append(f"Bonus Sequence动作次数投影必须覆盖全部且仅覆盖路径域: {node_id}")

    primary_rule = attributes.get("primary_action_count_rule")
    expected_primary = {
        "counted_stage_role": "typed_action",
        "count_unit": "completed_typed_stage_action",
        "control_stage_count": 0,
        "terminal_stage_count": 0,
    }
    if primary_rule != expected_primary:
        errors.append(f"Bonus Sequence主要动作计数规则必须固定为已完成类型化阶段动作: {node_id}")
    exit_condition = attributes.get("exit_condition")
    if not isinstance(exit_condition, dict) or set(exit_condition) != {"terminal_stage_ids", "all_paths_terminate"} or set(exit_condition.get("terminal_stage_ids", [])) != terminals or exit_condition.get("all_paths_terminate") is not True:
        errors.append(f"Bonus Sequence退出条件必须精确覆盖全部终止阶段并证明全部路径终止: {node_id}")
    if attributes.get("player_input_role") not in {"none", "reveal_only"}:
        errors.append(f"Bonus Sequence不得包含改变数学结果的玩家决策: {node_id}")
    return errors


def validate_bonus_sequence_links(node, active_nodes):
    attributes = node.get("attributes", {})
    node_id = node.get("node_id")
    node_map = {value.get("node_id"): value for value in active_nodes if non_empty(value.get("node_id"))}
    errors = []
    bindings = {
        row.get("stage_id"): row
        for row in attributes.get("stage_action_bindings", [])
        if isinstance(row, dict) and non_empty(row.get("stage_id"))
    }
    for stage_id, binding in bindings.items():
        if binding.get("stage_role") != "typed_action":
            continue
        action = node_map.get(binding.get("action_node_id"))
        if (
            not isinstance(action, dict)
            or action.get("mechanic_id") != binding.get("action_mechanic_id")
            or action.get("mechanic_id", "").startswith("feature.")
        ):
            errors.append(f"Bonus Sequence动作阶段必须引用活动非Feature玩法节点: {node_id}/{stage_id}")
            continue
        event_set = binding.get("semantic_event_set_id")
        if event_set not in node.get("semantic_event_set_ids", []) or event_set not in action.get("semantic_event_set_ids", []):
            errors.append(f"Bonus Sequence动作阶段未绑定父子双方共享事件集: {node_id}/{stage_id}")
        for owner_id in [*binding.get("random_owner_node_ids", []), *binding.get("payout_owner_node_ids", [])]:
            owner = node_map.get(owner_id)
            if not isinstance(owner, dict) or owner.get("mechanic_id", "").startswith("feature."):
                errors.append(f"Bonus Sequence随机或派奖Owner必须为活动非Feature节点: {node_id}/{stage_id}/{owner_id}")
            elif event_set not in owner.get("semantic_event_set_ids", []):
                errors.append(f"Bonus Sequence随机或派奖Owner未共享阶段事件集: {node_id}/{stage_id}/{owner_id}")

    resolution = attributes.get("transition_resolution_rule", {})
    for row in resolution.get("branch_resolutions", []) if isinstance(resolution, dict) else []:
        if not isinstance(row, dict) or row.get("resolution_type") != "owned_mechanic_outcome":
            continue
        stage_binding = bindings.get(row.get("from_stage"), {})
        if row.get("owner_node_id") not in stage_binding.get("random_owner_node_ids", []):
            errors.append(f"Bonus Sequence玩法结果分支必须引用来源阶段登记的随机Owner: {node_id}/{row.get('from_stage')}/{row.get('branch_id')}")

    aggregation = attributes.get("return_aggregation_rule")
    aggregation_fields = {
        "anonymous_payout", "feature_cycle_owner_pays", "stage_payout_owner_bindings",
        "entry_source_denominators", "all_payouts_covered_exactly_once", "terminal_return_equals_sum_of_stage_payouts",
    }
    if not isinstance(aggregation, dict) or set(aggregation) != aggregation_fields:
        return errors + [f"Bonus Sequence回报聚合合同必须完整使用六个固定字段: {node_id}"]
    if (
        aggregation.get("anonymous_payout") is not False
        or aggregation.get("feature_cycle_owner_pays") is not False
        or aggregation.get("all_payouts_covered_exactly_once") is not True
        or aggregation.get("terminal_return_equals_sum_of_stage_payouts") is not True
    ):
        errors.append(f"Bonus Sequence必须禁止匿名/父Owner派奖并保证阶段派奖恰好一次汇总: {node_id}")
    expected_payouts = {
        (stage_id, owner_id, binding.get("semantic_event_set_id"))
        for stage_id, binding in bindings.items()
        for owner_id in binding.get("payout_owner_node_ids", [])
    }
    rows = aggregation.get("stage_payout_owner_bindings")
    actual_payouts = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or set(row) != {"stage_id", "owner_node_id", "semantic_event_set_id"}:
            errors.append(f"Bonus Sequence阶段派奖Owner聚合字段不完整: {node_id}")
            continue
        actual_payouts.append((row.get("stage_id"), row.get("owner_node_id"), row.get("semantic_event_set_id")))
    if set(actual_payouts) != expected_payouts or len(actual_payouts) != len(set(actual_payouts)):
        errors.append(f"Bonus Sequence阶段派奖Owner集合必须完整、互斥且恰好一次: {node_id}")
    denominators = aggregation.get("entry_source_denominators")
    expected_denominators = {}
    for source_id, semantics in entry_source_semantics(node).items():
        if semantics.get("origin") == "endogenous":
            expected_denominators[source_id] = "triggering_paid_bet"
        elif semantics.get("source_kind") == "feature_buy":
            expected_denominators[source_id] = "actual_purchase_cost"
        else:
            expected_denominators[source_id] = "not_applicable_external_control"
    if denominators != expected_denominators:
        errors.append(f"Bonus Sequence逐入口回报分母与入口来源语义不一致: {node_id}")

    complete_event_set = attributes.get("sequence_boundary_rule", {}).get("complete_cycle_semantic_event_set_id")
    for other in active_nodes:
        if other.get("node_id") == node_id:
            continue
        if other.get("mechanic_id", "").startswith("feature.") and complete_event_set in other.get("semantic_event_set_ids", []):
            errors.append(f"其他Feature不得共享Bonus Sequence完整周期事件集: {node_id}/{other.get('node_id')}")
    current = node
    visited = set()
    while current.get("parent_id") in node_map and current.get("parent_id") not in visited:
        visited.add(current.get("parent_id"))
        current = node_map[current["parent_id"]]
        if current.get("mechanic_id", "").startswith("feature."):
            errors.append(f"Bonus Sequence不得存在Feature祖先: {node_id}/{current.get('node_id')}")
            break
    if any(
        other.get("parent_id") == node_id and other.get("mechanic_id", "").startswith("feature.")
        for other in active_nodes
    ):
        errors.append(f"Bonus Sequence不得包含Feature子节点: {node_id}")
    return errors


def validate_profile_inapplicability(node, evidence_root, input_manifest):
    mechanic_id = node.get("mechanic_id")
    reason = node.get("inapplicability_reason_code")
    if reason not in PROFILE_INAPPLICABILITY_REASON_CODES:
        return [f"不适用玩法节点原因码不受支持: {mechanic_id} / {reason}"]
    records = node.get("inapplicability_evidence")
    if not isinstance(records, list) or not records or not all(isinstance(record, dict) for record in records):
        return [f"不适用玩法节点证据必须为非空对象数组: {mechanic_id}"]
    if evidence_root is None:
        return [f"不适用玩法节点证据缺少可信task_root: {mechanic_id}"]
    manifest_hashes = input_manifest.get("hashes", {}) if isinstance(input_manifest.get("hashes"), dict) else {}
    errors = []
    for record in records:
        path = record.get("evidence_path")
        expected_sha = record.get("evidence_sha256")
        if not non_empty(path) or not is_sha256(expected_sha):
            errors.append(f"不适用玩法节点证据路径或SHA-256无效: {mechanic_id}")
            continue
        resolved = safe_evidence_path(evidence_root, path)
        if resolved is None or not resolved.is_file() or sha(resolved) != expected_sha:
            errors.append(f"不适用玩法节点证据文件不存在或hash失效: {mechanic_id} / {path}")
            continue
        if manifest_hashes.get(path) != expected_sha:
            errors.append(f"不适用玩法节点证据未写入input_manifest.hashes: {mechanic_id} / {path}")
        try:
            actual = json_pointer_value(load(resolved), record.get("json_pointer"))
            if actual != record.get("expected_value"):
                errors.append(f"不适用玩法节点证据JSON Pointer值不一致: {mechanic_id}")
            elif not source_evidence_proves_absence(actual):
                errors.append(f"source_evidence_proves_absence不得绑定存在、启用或正向证据: {mechanic_id}")
        except (OSError, ValueError, KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            errors.append(f"不适用玩法节点证据无法核验: {mechanic_id} / {exc}")
    return errors


def validate_position_capacity_domains(node):
    attributes = node.get("attributes", {})
    if attributes.get("state_shape") != "position_set":
        return []
    capacity_map = attributes.get("position_domain_by_actual_capacity")
    if capacity_map is None:
        return []
    node_id = node.get("node_id")
    domain = attributes.get("position_domain")
    if not isinstance(domain, list) or not domain:
        return [f"可变容量位置状态缺少全局position_domain: {node_id}"]
    parsed = parsed_integer_key_mapping(capacity_map)
    if parsed is None:
        return [f"position_domain_by_actual_capacity容量键必须为不冲突的正整数字符串: {node_id}"]
    errors = []
    global_positions = set(domain)
    for capacity, positions in parsed.items():
        if capacity <= 0:
            errors.append(f"position_domain_by_actual_capacity容量必须为正整数: {node_id}/{capacity}")
            continue
        if (
            not isinstance(positions, list)
            or len(positions) != capacity
            or len(positions) != len(set(positions))
            or any(not non_empty(position) or position not in global_positions for position in positions)
        ):
            errors.append(f"position_domain_by_actual_capacity每个容量必须给出等容量、唯一且属于全局域的位置: {node_id}/{capacity}")
    if parsed and set().union(*(set(value) for value in parsed.values())) != global_positions:
        errors.append(f"position_domain_by_actual_capacity全部容量位置并集必须等于全局position_domain: {node_id}")
    return errors


def validate_profile_attribute_types(node):
    mechanic_id = node.get("mechanic_id")
    attributes = node.get("attributes", {})
    errors = []
    if mechanic_id in {"board.fixed-grid", "board.variable-grid"}:
        partitions = attributes.get("generator_partitions")
        valid_partitions = partitions == "none" or (
            isinstance(partitions, list)
            and bool(partitions)
            and len(partitions) == len(set(partitions))
            and all(non_empty(value) for value in partitions)
        )
        if not valid_partitions:
            errors.append(f"generator_partitions必须为受控值none或非空唯一生成分区列表: {node.get('node_id')}")
        stack_axis = attributes.get("stack_axis")
        if not isinstance(stack_axis, str) or not stack_axis.strip():
            errors.append(f"stack_axis必须为受控值none或明确实际方向: {node.get('node_id')}")
    if mechanic_id == "board.variable-grid":
        mode = attributes.get("ways_capacity_mode")
        if mode not in {"none", "layout_only", "layout_plus_non_layout"}:
            errors.append(f"ways_capacity_mode必须为none、layout_only或layout_plus_non_layout: {node.get('node_id')}")
        formula = attributes.get("available_ways_formula")
        bindings = attributes.get("layout_capacity_projection_bindings")
        if mode == "none" and (formula is not None or bindings is not None):
            errors.append(f"ways_capacity_mode=none时不得声明容量公式或布局容量投影: {node.get('node_id')}")
        if mode in {"layout_only", "layout_plus_non_layout"} and not non_empty(formula):
            errors.append(f"存在Ways容量语义时必须声明available_ways_formula: {node.get('node_id')}")
    if mechanic_id == "settlement.ways":
        if not isinstance(attributes.get("variable_ways"), bool):
            errors.append(f"settlement.ways.variable_ways必须为布尔值: {node.get('node_id')}")
        if not isinstance(attributes.get("available_ways_formula"), (str, dict)) or not non_empty(attributes.get("available_ways_formula")):
            errors.append(f"settlement.ways.available_ways_formula必须为非空公式或结构化规则: {node.get('node_id')}")
    if mechanic_id == "settlement.cluster-pay" and not isinstance(attributes.get("near_miss_structure_relevant"), bool):
        errors.append(f"near_miss_structure_relevant必须为显式布尔值: {node.get('node_id')}")
    if mechanic_id in {"feature.free-spin", "feature.respin"}:
        retrigger = attributes.get("retrigger_rule")
        if mechanic_id == "feature.free-spin" and (not isinstance(retrigger, (str, dict)) or not non_empty(retrigger)):
            errors.append(f"retrigger_rule必须为非空规则或受控值none: {node.get('node_id')}")
    if mechanic_id == "settlement.effective-ways-capacity":
        geometry_domain = attributes.get("geometry_layout_domain")
        if (
            not isinstance(geometry_domain, list)
            or not geometry_domain
            or len(geometry_domain) != len(set(geometry_domain))
            or any(not non_empty(value) for value in geometry_domain)
        ):
            errors.append(f"geometry_layout_domain必须为非空唯一真实布局列表: {node.get('node_id')}")
        binding = attributes.get("geometry_layout_binding")
        required = {
            "board_node_id", "shared_semantic_event_set_id", "layout_identity_field",
            "all_observations_bound", "rule_evidence_sha256",
        }
        if not isinstance(binding, dict) or set(binding) != required:
            errors.append(f"geometry_layout_binding必须完整使用五个固定字段: {node.get('node_id')}")
        elif (
            not all(non_empty(binding.get(field)) for field in ("board_node_id", "shared_semantic_event_set_id", "layout_identity_field"))
            or binding.get("all_observations_bound") is not True
            or not is_sha256(binding.get("rule_evidence_sha256"))
        ):
            errors.append(f"geometry_layout_binding缺少布局身份、共享事件集、完整覆盖或规则证据: {node.get('node_id')}")
    if mechanic_id == "award.jackpot":
        rule = attributes.get("tier_resolution_rule")
        required = {
            "opportunity_id_field", "resolved_tier_field", "no_hit_value",
            "all_opportunities_resolved", "at_most_one_tier_per_opportunity", "rule_evidence_sha256",
        }
        if not isinstance(rule, dict) or set(rule) != required:
            errors.append(f"tier_resolution_rule必须完整使用六个固定字段: {node.get('node_id')}")
        elif (
            not all(non_empty(rule.get(field)) for field in ("opportunity_id_field", "resolved_tier_field", "no_hit_value"))
            or rule.get("all_opportunities_resolved") is not True
            or rule.get("at_most_one_tier_per_opportunity") is not True
            or not is_sha256(rule.get("rule_evidence_sha256"))
        ):
            errors.append(f"tier_resolution_rule必须证明每个机会完整解析且至多命中一个层级: {node.get('node_id')}")
    return errors


def validate_profile(profile, catalog, evidence_root=None, input_manifest=None):
    errors, active, required_nodes = [], [], []
    input_manifest = input_manifest or {}
    mechanics = profile.get("mechanics")
    if not isinstance(mechanics, list) or not mechanics:
        return ["新任务玩法画像不能为空"], [], []
    seen_node_ids = set()
    for position, node in enumerate(mechanics, 1):
        if not isinstance(node, dict):
            errors.append(f"玩法节点{position}不是对象")
            continue
        mechanic_id, scope = node.get("mechanic_id"), node.get("scope")
        node_id = node.get("node_id")
        definition = catalog["mechanics"].get(mechanic_id)
        if definition is None:
            errors.append(f"玩法画像引用未知mechanic_id: {mechanic_id}")
            continue
        if not non_empty(node_id):
            errors.append(f"玩法节点缺少node_id: {mechanic_id}")
        elif node_id in seen_node_ids:
            errors.append(f"玩法画像node_id重复: {node_id}")
        seen_node_ids.add(node_id)
        if not non_empty(scope):
            errors.append(f"玩法节点缺少作用域: {mechanic_id}")
        event_set_ids = node.get("semantic_event_set_ids")
        if (
            not isinstance(event_set_ids, list)
            or not event_set_ids
            or not all(isinstance(value, str) and value.strip() for value in event_set_ids)
            or len(event_set_ids) != len(set(event_set_ids))
        ):
            errors.append(f"玩法节点semantic_event_set_ids无效: {mechanic_id}")
        if node.get("name_zh") != definition.get("name_zh"):
            errors.append(f"玩法中文名与目录不一致: {mechanic_id}")
        attributes = node.get("attributes")
        if not isinstance(attributes, dict):
            errors.append(f"玩法属性必须为对象: {mechanic_id}")
            continue
        allowed = set(definition.get("required_attributes", [])) | set(definition.get("optional_attributes", []))
        unknown = sorted(set(attributes) - allowed)
        if unknown:
            errors.append(f"玩法画像包含未知属性: {mechanic_id} / {','.join(unknown)}")
        status = node.get("status")
        if status in ACTIVE_MECHANIC_STATUSES:
            missing = sorted(name for name in definition.get("required_attributes", []) if not non_empty(attributes.get(name)))
            if missing:
                errors.append(f"玩法画像缺少必需属性: {mechanic_id} / {','.join(missing)}")
            errors += validate_profile_attribute_types(node)
            errors += validate_position_capacity_domains(node)
            if mechanic_id in SETTLEMENT_SCALE_AXIS:
                expected_axis = SETTLEMENT_SCALE_AXIS[mechanic_id]
                if attributes.get("winning_scale_axis_semantics") != expected_axis:
                    errors.append(f"中奖规模轴语义与结算玩法不一致: {mechanic_id} / 必须为{expected_axis}")
            if mechanic_id == "modifier.collect":
                collect_errors, _, _ = validate_collect_output_maps(attributes)
                errors += collect_errors
            if mechanic_id in FEATURE_MECHANIC_IDS:
                errors += validate_resource_count_derivation_bindings(node)
            if mechanic_id == "state.persistent-state" and attributes.get("state_shape") == "ordered_scalar":
                axis = attributes.get("ordered_axis_semantics")
                if axis not in ORDERED_AXIS_SEMANTICS:
                    errors.append("ordered_scalar持久状态必须密封有效ordered_axis_semantics")
                transition_events = attributes.get("transition_event_domain")
                if transition_events is not None and (
                    not isinstance(transition_events, list)
                    or not transition_events
                    or len(transition_events) != len(set(transition_events))
                    or any(not non_empty(value) for value in transition_events)
                ):
                    errors.append("ordered_scalar持久状态的transition_event_domain必须为非空唯一事件ID列表")
                if axis == "nonnegative_multiplicative":
                    domain = attributes.get("value_domain")
                    if not isinstance(domain, list) or not domain or any(not finite_number(value) or value < 0 for value in domain):
                        errors.append("乘法尺度持久状态的value_domain必须为非空有限非负数值列表")
            if mechanic_id == "state.persistent-state" and attributes.get("state_shape") == "position_set":
                errors += validate_position_count_owner_bindings(node)
                errors += validate_matched_position_transition_bindings(node)
                position_domain = attributes.get("position_domain")
                if (
                    not isinstance(position_domain, list)
                    or not position_domain
                    or any(not non_empty(position) for position in position_domain)
                    or len(position_domain) != len(set(position_domain))
                ):
                    errors.append("position_set持久状态必须密封非空唯一真实position_domain")
                bindings = attributes.get("position_transition_bindings")
                required_binding_fields = {
                    "transition_event",
                    "from_observation_point",
                    "to_observation_point",
                    "semantic_event_set_id",
                }
                observation_points = attributes.get("observation_points")
                transition_required = (
                    isinstance(observation_points, list)
                    and len(observation_points) >= 2
                    and semantic_truthy(attributes.get("transition_rule"))
                )
                if bindings is None:
                    if transition_required:
                        errors.append("存在跨观测点位置转移时必须密封非空position_transition_bindings")
                elif not isinstance(bindings, list) or not bindings:
                    errors.append("已声明position_transition_bindings时必须为非空数组")
                else:
                    transition_events = set()
                    for index, binding in enumerate(bindings, 1):
                        if not isinstance(binding, dict) or set(binding) != required_binding_fields:
                            errors.append(f"position_transition_bindings第{index}项必须完整使用四个固定字段")
                            continue
                        if any(not non_empty(binding.get(field)) for field in required_binding_fields):
                            errors.append(f"position_transition_bindings第{index}项包含空字段")
                        event = binding.get("transition_event")
                        if event in transition_events:
                            errors.append(f"position_transition_bindings重复transition_event: {event}")
                        transition_events.add(event)
                        for field in ("from_observation_point", "to_observation_point"):
                            if not isinstance(observation_points, list) or binding.get(field) not in observation_points:
                                errors.append(f"position_transition_bindings观测点未写入observation_points: {binding.get(field)}")
                        if binding.get("semantic_event_set_id") not in node.get("semantic_event_set_ids", []):
                            errors.append(f"position_transition_bindings事件集未由持久状态节点声明: {event}")
            if mechanic_id == "settlement.payline":
                pair = (attributes.get("aggregation_unit"), attributes.get("winning_scale_dimension"))
                legal = {
                    ("per_line", "matched_reel_count"),
                    ("per_step_symbol", "winning_line_count"),
                }
                if pair not in legal:
                    errors.append("固定线只允许per_line+matched_reel_count或per_step_symbol+winning_line_count")
                line_count = attributes.get("line_count")
                min_reels = attributes.get("min_reels")
                definitions = attributes.get("line_definitions")
                def valid_coordinate(value):
                    if isinstance(value, dict):
                        reel, row = value.get("reel"), value.get("row")
                    elif isinstance(value, list) and len(value) == 2:
                        reel, row = value
                    else:
                        return False
                    return all(isinstance(item, int) and not isinstance(item, bool) and item >= 0 for item in (reel, row))
                valid_definitions = (
                    isinstance(line_count, int)
                    and not isinstance(line_count, bool)
                    and line_count > 0
                    and isinstance(min_reels, int)
                    and not isinstance(min_reels, bool)
                    and min_reels > 0
                    and isinstance(definitions, list)
                    and len(definitions) == line_count
                    and all(
                        isinstance(definition, dict)
                        and non_empty(definition.get("line_id"))
                        and isinstance(definition.get("coordinates"), list)
                        and len(definition["coordinates"]) >= min_reels
                        and all(valid_coordinate(value) for value in definition["coordinates"])
                        and len({json.dumps(value, sort_keys=True) for value in definition["coordinates"]}) == len(definition["coordinates"])
                        and len({value.get("reel") if isinstance(value, dict) else value[0] for value in definition["coordinates"]}) == len(definition["coordinates"])
                        for definition in definitions
                    )
                    and len({definition["line_id"] for definition in definitions}) == line_count
                )
                if not valid_definitions:
                    errors.append("固定线line_count与min_reels必须为正整数，line_definitions必须逐线提供唯一line_id及每轴至多一个合法reel/row坐标")
                else:
                    canonical_geometries = []
                    for definition in definitions:
                        coordinates = [
                            (value.get("reel"), value.get("row")) if isinstance(value, dict) else (value[0], value[1])
                            for value in definition["coordinates"]
                        ]
                        canonical_geometries.append(tuple(sorted(coordinates, key=lambda value: value[0])))
                    if len(canonical_geometries) != len(set(canonical_geometries)):
                        errors.append("固定线同一作用域存在重复规范几何路径，禁止不同line_id映射到同一坐标线路后静默合并")
            if mechanic_id in FEATURE_MECHANIC_IDS:
                errors += validate_feature_control_contract(attributes, mechanic_id)
                if mechanic_id == BONUS_SEQUENCE_MECHANIC_ID:
                    errors += validate_bonus_sequence_structure(node)
                entry_sources = attributes.get("entry_sources")
                if not isinstance(entry_sources, list) or not entry_sources or not all(non_empty(source) for source in entry_sources):
                    errors.append(f"Feature入口来源必须为非空列表: {mechanic_id}")
                elif len(entry_sources) != len(set(entry_sources)):
                    errors.append(f"Feature入口来源不得重复: {mechanic_id}")
                elif any(
                    not isinstance(source, str)
                    or source not in ENTRY_SOURCE_VALUES and not source.startswith("other:")
                    for source in entry_sources
                ):
                    errors.append(f"Feature入口来源必须使用规范枚举: {mechanic_id}")
                semantics = attributes.get("entry_source_semantics")
                if not isinstance(semantics, dict) or not isinstance(entry_sources, list) or set(semantics) != set(entry_sources):
                    errors.append(f"Feature入口来源语义必须逐项覆盖entry_sources: {mechanic_id}")
                else:
                    reserved = {
                        "feature_buy": ("exogenous", "feature_buy"),
                        "forced_test": ("exogenous", "forced_test"),
                        "test_injection": ("exogenous", "test_injection"),
                        "operator_override": ("exogenous", "operator_override"),
                    }
                    for source_id, definition in semantics.items():
                        if not isinstance(definition, dict) or set(definition) != {"origin", "source_kind"}:
                            errors.append(f"Feature入口来源语义必须只含origin和source_kind: {mechanic_id} / {source_id}")
                            continue
                        origin, source_kind = definition.get("origin"), definition.get("source_kind")
                        allowed_kinds = ENDOGENOUS_ENTRY_SOURCE_KINDS if origin == "endogenous" else EXOGENOUS_ENTRY_SOURCE_KINDS if origin == "exogenous" else set()
                        if source_kind not in allowed_kinds:
                            errors.append(f"Feature入口来源origin与source_kind不一致: {mechanic_id} / {source_id}")
                        if source_id in {"natural", "feature_award", "state_threshold", "direct_award"} and origin != "endogenous":
                            errors.append(f"游戏规则入口不得标记为外生来源: {mechanic_id} / {source_id}")
                        expected = reserved.get(source_id)
                        if expected is not None and (origin, source_kind) != expected:
                            errors.append(f"保留外生入口分类无效: {mechanic_id} / {source_id}")
            if mechanic_id == "feature.award-draw":
                equivalence = attributes.get("outcome_return_equivalence")
                entry_sources = attributes.get("entry_sources")
                proof_fields = set(AWARD_CHAIN_PROOF)
                if not isinstance(equivalence, dict) or not isinstance(entry_sources, list) or set(equivalence) != set(entry_sources):
                    errors.append("抽取型奖励outcome_return_equivalence必须逐入口来源完整声明")
                else:
                    for source_id, proof in equivalence.items():
                        if (
                            not isinstance(proof, dict)
                            or set(proof) != proof_fields
                            or any(not isinstance(proof[field], bool) for field in proof_fields)
                        ):
                            errors.append(f"抽取型奖励完整随机链证明必须完整使用七个布尔字段: {source_id}")
                            continue
                        if proof.get("terminal_return_projection_deterministic") and not award_return_is_deterministic_chain(node, source_id):
                            errors.append(f"抽取完整随机链可复算声明与状态、转移、停止、聚合或链外随机证明冲突: {source_id}")
            if mechanic_id in {"feature.free-spin", "feature.respin"} and "duration_determinism" in attributes:
                duration_contract = attributes.get("duration_determinism")
                required_duration_fields = {
                    "one_to_one_with_initial_grant",
                    "early_termination_possible",
                    "variable_consumption_possible",
                    "counter_reset_possible",
                    "cross_step_dependency_possible",
                }
                if (
                    not isinstance(duration_contract, dict)
                    or set(duration_contract) != required_duration_fields
                    or any(not isinstance(duration_contract[field], bool) for field in required_duration_fields)
                ):
                    errors.append(f"Feature时长确定性声明必须完整使用五个布尔字段: {mechanic_id}")
            if mechanic_id == "feature.hold-and-spin":
                terminal_states = attributes.get("terminal_state_domain")
                if not isinstance(terminal_states, list) or not terminal_states or len(terminal_states) != len(set(map(str, terminal_states))):
                    errors.append("Hold & Spin terminal_state_domain必须为非空唯一值列表")
                board_capacity = attributes.get("board_capacity")
                if not isinstance(board_capacity, int) or isinstance(board_capacity, bool) or board_capacity <= 0:
                    errors.append("Hold & Spin board_capacity必须为正整数")
                variable_capacity = semantic_truthy(attributes.get("variable_capacity_rule")) or semantic_truthy(attributes.get("unlock_or_upgrade_rule"))
                capacity_domain = attributes.get("actual_capacity_domain")
                capacity_points = attributes.get("capacity_observation_points")
                capacity_bindings = attributes.get("capacity_owner_bindings")
                capacity_transition = attributes.get("capacity_transition_contract")
                if variable_capacity:
                    if (
                        not isinstance(capacity_domain, list)
                        or len(capacity_domain) < 2
                        or len(capacity_domain) != len(set(capacity_domain))
                        or any(not isinstance(value, int) or isinstance(value, bool) or value <= 0 for value in capacity_domain)
                    ):
                        errors.append("可变容量Hold & Spin必须密封至少两个唯一正整数actual_capacity_domain")
                    elif isinstance(board_capacity, int) and board_capacity != max(capacity_domain):
                        errors.append("可变容量Hold & Spin的board_capacity必须等于actual_capacity_domain最大容量")
                    if capacity_points != ["entry", "step_start", "terminal"]:
                        errors.append("可变容量Hold & Spin的capacity_observation_points必须按entry、step_start、terminal固定顺序完整声明")
                    required_transition_fields = {
                        "current_observation_point", "next_observation_point", "group_separator",
                        "current_capacity_occupancy_to_next_capacity_domain",
                        "all_reachable_groups_covered", "rule_evidence_sha256",
                    }
                    if not isinstance(capacity_transition, dict) or set(capacity_transition) != required_transition_fields:
                        errors.append("可变容量Hold & Spin必须完整密封capacity_transition_contract六个固定字段")
                    else:
                        if (
                            capacity_transition.get("current_observation_point") != "step_start_before_generation"
                            or capacity_transition.get("next_observation_point") != "after_resolution_as_next_step_start_or_terminal"
                            or capacity_transition.get("group_separator") != "|"
                            or capacity_transition.get("all_reachable_groups_covered") is not True
                            or not is_sha256(capacity_transition.get("rule_evidence_sha256"))
                        ):
                            errors.append("Hold & Spin容量转移合同的观察边界、分隔符、完整覆盖或证据hash无效")
                        transition_map = capacity_transition.get("current_capacity_occupancy_to_next_capacity_domain")
                        if not isinstance(transition_map, dict) or not transition_map:
                            errors.append("Hold & Spin容量转移合同必须包含非空C|O到C'域映射")
                        else:
                            for group, next_domain in transition_map.items():
                                parts = group.split("|") if isinstance(group, str) else []
                                current_capacity = integer_token(parts[0]) if len(parts) == 2 else None
                                current_occupancy = integer_token(parts[1]) if len(parts) == 2 else None
                                if (
                                    current_capacity not in (capacity_domain if isinstance(capacity_domain, list) else [])
                                    or current_occupancy is None or current_occupancy < 0 or current_occupancy > current_capacity
                                ):
                                    errors.append(f"Hold & Spin容量转移条件组不是合法current_capacity|current_occupancy: {group}")
                                if (
                                    not isinstance(next_domain, list) or not next_domain
                                    or len(next_domain) != len(set(next_domain))
                                    or any(value not in (capacity_domain if isinstance(capacity_domain, list) else []) for value in next_domain)
                                ):
                                    errors.append(f"Hold & Spin容量转移下一容量域无效: {group}")
                    if capacity_bindings is not None:
                        required_capacity_binding_fields = {
                            "derived_metric_id", "derived_instance_dimensions", "primary_owner_metric_instance",
                            "shared_semantic_event_set_id", "source_value_to_actual_capacity",
                            "mapping_total_and_deterministic", "same_observation_event_universe",
                            "extra_random_or_state_dependency", "rule_evidence_sha256",
                        }
                        if not isinstance(capacity_bindings, list) or not capacity_bindings:
                            errors.append("Hold & Spin capacity_owner_bindings必须为非空对象数组")
                        else:
                            seen_instances = set()
                            allowed_source_metrics = {
                                "variable_grid.reel_height_layout_distribution",
                                "variable_grid.valid_cell_layout_distribution",
                                "persistent_state.ordered_value_distribution",
                                "effective_ways.capacity_distribution",
                            }
                            for index, binding in enumerate(capacity_bindings, 1):
                                label = f"Hold & Spin第{index}条容量Owner绑定"
                                if not isinstance(binding, dict) or set(binding) != required_capacity_binding_fields:
                                    errors.append(f"{label}必须完整使用九个固定字段")
                                    continue
                                if binding.get("derived_metric_id") != "hold_spin.actual_capacity_distribution_by_observation":
                                    errors.append(f"{label}的derived_metric_id无效")
                                dimensions = binding.get("derived_instance_dimensions")
                                point = dimensions.get("capacity_observation_point") if isinstance(dimensions, dict) else None
                                entry_source = dimensions.get("entry_source") if isinstance(dimensions, dict) else None
                                if (
                                    not isinstance(dimensions, dict)
                                    or set(dimensions) != {"entry_source", "capacity_observation_point"}
                                    or point not in {"entry", "step_start", "terminal"}
                                    or entry_source not in entry_source_tokens(node)
                                ):
                                    errors.append(f"{label}的入口来源或容量观察点实例无效")
                                elif (entry_source, point) in seen_instances:
                                    errors.append(f"Hold & Spin容量Owner重复绑定入口来源与观察点: {entry_source}/{point}")
                                seen_instances.add((entry_source, point))
                                source = binding.get("primary_owner_metric_instance")
                                if not isinstance(source, dict) or set(source) != {"metric_id", "source_node_ids", "instance_dimensions"}:
                                    errors.append(f"{label}的Primary来源实例必须完整使用三个固定字段")
                                    source = {}
                                if source.get("metric_id") not in allowed_source_metrics:
                                    errors.append(f"{label}引用了不支持的容量Primary来源")
                                source_ids = source.get("source_node_ids")
                                if not isinstance(source_ids, list) or len(source_ids) != 1 or not non_empty(source_ids[0]):
                                    errors.append(f"{label}必须且只能引用一个来源玩法节点")
                                if not isinstance(source.get("instance_dimensions"), dict):
                                    errors.append(f"{label}的来源实例维度必须为对象")
                                mapping = binding.get("source_value_to_actual_capacity")
                                if (
                                    not isinstance(mapping, dict)
                                    or not mapping
                                    or any(not non_empty(key) for key in mapping)
                                    or any(value not in (capacity_domain if isinstance(capacity_domain, list) else []) for value in mapping.values())
                                ):
                                    errors.append(f"{label}的来源值到实际容量映射无效")
                                if (
                                    binding.get("mapping_total_and_deterministic") is not True
                                    or binding.get("same_observation_event_universe") is not True
                                    or binding.get("extra_random_or_state_dependency") is not False
                                    or not is_sha256(binding.get("rule_evidence_sha256"))
                                ):
                                    errors.append(f"{label}必须证明完整确定映射、同观察事件全集、无额外随机并绑定规则证据hash")
                elif any(value is not None for value in (capacity_domain, capacity_points, capacity_bindings, capacity_transition)):
                    errors.append("固定容量Hold & Spin不得声明可变容量域、观察点、容量Owner绑定或容量转移合同")
            if mechanic_id == "modifier.symbol-transform":
                target_scope = attributes.get("target_assignment_scope")
                if target_scope not in {
                    "deterministic_mapping",
                    "per_event_shared",
                    "per_source_group_shared",
                    "per_cell_independent",
                    "mixed_or_state_dependent",
                }:
                    errors.append("符号变形target_assignment_scope必须为确定映射、整事件共享、来源组共享、逐格独立或混合状态规则")
                if not non_empty(attributes.get("event_target_assignment_rule")):
                    errors.append("符号变形缺少同事件目标分配规则")
            if mechanic_id == "modifier.win-multiplier":
                if not isinstance(attributes.get("application_may_be_skipped"), bool):
                    errors.append("倍率application_may_be_skipped必须为布尔值")
                driver = attributes.get("progression_driver")
                if not isinstance(driver, str) or driver not in {"none", "persistent_state", "cascade_depth"} and not driver.startswith("other:"):
                    errors.append("倍率progression_driver必须为none、persistent_state、cascade_depth或other:说明")
                elif driver != "none":
                    required_progression = ["progression_rule", "reset_rule", "cap_rule", "state_to_effective_multiplier_rule"]
                    missing_progression = [field for field in required_progression if not non_empty(attributes.get(field))]
                    if missing_progression:
                        errors.append(f"倍率递进缺少条件必需属性: {','.join(missing_progression)}")
                    if driver == "persistent_state" and not non_empty(attributes.get("progression_state_id")):
                        errors.append("持久状态驱动倍率缺少progression_state_id")
                    if driver == "cascade_depth" and not non_empty(attributes.get("cascade_node_id")):
                        errors.append("Cascade驱动倍率缺少cascade_node_id")
                    if driver == "cascade_depth" and not isinstance(attributes.get("same_depth_multiplier_randomness"), bool):
                        errors.append("Cascade驱动倍率必须密封same_depth_multiplier_randomness布尔值")
                return_evidence = attributes.get("return_dependency_evidence")
                if return_evidence is not None:
                    required_return_fields = {
                        "shared_semantic_event_set_id",
                        "controlled_driver_node_ids",
                        "control_stratum_fields",
                        "joint_observation_rule",
                        "residual_dependence_after_control",
                    }
                    if not isinstance(return_evidence, dict):
                        errors.append("倍率回报依赖证据必须为结构化对象")
                    else:
                        missing_return_fields = sorted(required_return_fields - set(return_evidence))
                        if missing_return_fields:
                            errors.append(f"倍率回报依赖证据字段缺失: {','.join(missing_return_fields)}")
                        driver_ids = return_evidence.get("controlled_driver_node_ids")
                        if (
                            not isinstance(driver_ids, list)
                            or len(driver_ids) != len(set(driver_ids))
                            or any(not non_empty(value) for value in driver_ids)
                        ):
                            errors.append("倍率回报依赖证据controlled_driver_node_ids必须为唯一节点ID列表")
                        strata = return_evidence.get("control_stratum_fields")
                        if (
                            not isinstance(strata, list)
                            or not strata
                            or len(strata) != len(set(strata))
                            or any(not non_empty(value) for value in strata)
                        ):
                            errors.append("倍率回报依赖证据control_stratum_fields必须为非空唯一字段列表")
                        if not non_empty(return_evidence.get("joint_observation_rule")):
                            errors.append("倍率回报依赖证据缺少联合观测规则")
                        if return_evidence.get("residual_dependence_after_control") is not True:
                            errors.append("倍率回报Interaction只允许在控制全部直接驱动后仍有剩余依赖时加载")
            if mechanic_id == "feature.respin":
                if attributes.get("step_index_semantics") != "executed_respin_action_index_1_based":
                    errors.append("普通Respin step_index_semantics必须固定为executed_respin_action_index_1_based")
                position_domain = attributes.get("position_domain")
                if (
                    not isinstance(position_domain, list)
                    or not position_domain
                    or any(not non_empty(position) for position in position_domain)
                    or len(position_domain) != len(set(position_domain))
                ):
                    errors.append("普通Respin必须密封非空唯一真实position_domain")
                retained_binding = attributes.get("retained_position_state_binding")
                if retained_binding is not None:
                    retained_fields = {
                        "state_node_id",
                        "state_id",
                        "observation_point",
                        "semantic_event_set_id",
                    }
                    if not isinstance(retained_binding, dict) or set(retained_binding) != retained_fields:
                        errors.append("Respin retained_position_state_binding必须完整使用四个固定字段")
                    elif any(not non_empty(retained_binding.get(field)) for field in retained_fields):
                        errors.append("Respin retained_position_state_binding包含空字段")
            if mechanic_id == "evolution.cascade" and semantic_truthy(attributes.get("step_multiplier_rule")):
                if not isinstance(attributes.get("same_depth_multiplier_randomness"), bool):
                    errors.append("存在Cascade逐层倍率规则时必须密封same_depth_multiplier_randomness布尔值")
            if mechanic_id == "evolution.cascade":
                if attributes.get("effective_capacity_axis_semantics") not in ORDERED_AXIS_SEMANTICS:
                    errors.append("Cascade有效容量必须密封natural_linear或nonnegative_multiplicative轴语义")
                if not non_empty(attributes.get("effective_capacity_unit_zh")):
                    errors.append("Cascade有效容量必须密封中文业务单位")
                if not non_empty(attributes.get("effective_capacity_source")):
                    errors.append("Cascade有效容量必须密封可复算的数据来源或规则来源")
            active.append(node)
            if node.get("status") == "必需":
                required_nodes.append(node)
        elif status == "可选":
            errors.append(f"已完成的新任务不得保留可选玩法节点: {mechanic_id} / {node_id}")
        elif status == "缺口":
            errors.append(f"已完成的新任务不得保留缺口玩法节点: {mechanic_id} / {node_id}")
        elif status == "不适用":
            errors += validate_profile_inapplicability(node, evidence_root, input_manifest)
        else:
            errors.append(f"玩法节点状态无效: {mechanic_id} / {status}")
    if profile.get("required_node_count") != len(required_nodes):
        errors.append(f"required_node_count自报不一致: 期望{len(required_nodes)},实际{profile.get('required_node_count')}")
    gaps = profile.get("gaps", [])
    if not isinstance(gaps, list):
        errors.append("game_profile.gaps必须为数组")
        gaps = []
    if profile.get("semantic_gap_count") != len(gaps):
        errors.append(f"semantic_gap_count自报不一致: 期望{len(gaps)},实际{profile.get('semantic_gap_count')}")
    if gaps:
        errors.append("已完成的新任务玩法画像不得保留语义缺口")
    if not active:
        errors.append("新任务没有活动玩法节点")
    return errors, active, required_nodes


def validate_scope_instances(profile, active_nodes, task_root_path, input_manifest):
    errors, result = [], []
    scopes = profile.get("scope_instances")
    if not isinstance(scopes, list) or not scopes:
        return ["新任务scope_instances不能为空"], []
    if task_root_path is None:
        return ["新任务语义门禁必须由调用方提供可信task_root"], []
    node_map = {
        node.get("node_id"): node
        for node in active_nodes
        if isinstance(node, dict) and isinstance(node.get("node_id"), str) and node.get("node_id")
    }
    seen_ids = set()
    manifest_hashes = input_manifest.get("hashes", {}) if isinstance(input_manifest.get("hashes"), dict) else {}
    evidence_root = task_evidence_root(task_root_path)
    event_bindings = {}
    reverse_event_bindings = {}
    covered_nodes = set()
    covered_event_sets = {node_id: set() for node_id in node_map}
    for position, scope in enumerate(scopes, 1):
        if not isinstance(scope, dict):
            errors.append(f"scope_instances第{position}项不是对象")
            continue
        scope_id = scope.get("scope_instance_id")
        if not non_empty(scope_id) or scope_id in seen_ids:
            errors.append(f"scope_instance_id缺失或重复: {scope_id}")
        seen_ids.add(scope_id)
        scope_role = scope.get("scope_role")
        if scope_role not in {"core", "mechanic"}:
            errors.append(f"scope_instance缺少有效scope_role: {scope_id}")
        source_ids = scope.get("source_node_ids")
        if (
            not isinstance(source_ids, list)
            or not all(isinstance(node_id, str) and node_id for node_id in source_ids)
            or len(source_ids) != len(set(source_ids))
            or scope_role == "mechanic" and not source_ids
        ):
            errors.append(f"scope_instance来源节点无效: {scope_id}")
            continue
        unknown = sorted(set(source_ids) - set(node_map))
        if unknown:
            errors.append(f"scope_instance引用未知来源节点: {scope_id} / {','.join(unknown)}")
            continue
        if scope_role == "mechanic":
            covered_nodes.update(source_ids)
        event_set_id = scope.get("semantic_event_set_id")
        if not isinstance(event_set_id, str) or not event_set_id:
            errors.append(f"scope_instance缺少有效semantic_event_set_id: {scope_id}")
            continue
        if source_ids and any(event_set_id not in node_map[node_id].get("semantic_event_set_ids", []) for node_id in source_ids):
            errors.append(f"scope_instance事件集未绑定全部来源节点: {scope_id}")
        else:
            for node_id in source_ids:
                covered_event_sets[node_id].add(event_set_id)
        if not non_empty(scope.get("sample_unit")):
            errors.append(f"scope_instance缺少sample_unit: {scope_id}")
        dimensions = scope.get("dimensions")
        if not isinstance(dimensions, dict) or not dimensions or any(
            not non_empty(name)
            or not isinstance(value, (str, int, float, bool))
            or isinstance(value, float) and not math.isfinite(value)
            or not non_empty(value)
            for name, value in dimensions.items()
        ):
            errors.append(f"scope_instance维度无效: {scope_id}")
            dimensions = {}
        entry_source = dimensions.get("entry_source")
        for node_id in source_ids:
            node = node_map[node_id]
            if node.get("mechanic_id") in FEATURE_MECHANIC_IDS and non_empty(entry_source) and entry_source not in entry_source_tokens(node):
                errors.append(f"scope_instance入口来源未在Feature画像声明: {scope_id} / {node_id} / {entry_source}")
        event_path = scope.get("event_set_path")
        resolved = safe_evidence_path(evidence_root, event_path)
        if resolved is None or not resolved.is_file():
            errors.append(f"scope_instance事件集文件不存在: {scope_id}")
        elif not is_sha256(scope.get("event_set_sha256")) or sha(resolved) != scope.get("event_set_sha256"):
            errors.append(f"scope_instance事件集hash失效: {scope_id}")
        else:
            try:
                actual_count = sealed_event_count(resolved, scope.get("sample_unit"), dimensions)
                if actual_count != scope.get("event_count"):
                    errors.append(f"scope_instance事件数与密封文件不一致: {scope_id}")
            except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
                errors.append(f"scope_instance事件集格式无效: {scope_id} / {exc}")
        if manifest_hashes.get(event_path) != scope.get("event_set_sha256"):
            errors.append(f"scope_instance事件集未写入input_manifest.hashes: {scope_id}")
        if not isinstance(scope.get("event_count"), int) or isinstance(scope.get("event_count"), bool) or scope.get("event_count") < 1:
            errors.append(f"scope_instance事件数无效: {scope_id}")
        binding = (event_path, scope.get("event_set_sha256"), scope.get("event_count"))
        if event_set_id in event_bindings and event_bindings[event_set_id] != binding:
            errors.append(f"同一semantic_event_set_id绑定了不同文件、hash或事件数: {event_set_id}")
        event_bindings[event_set_id] = binding
        if binding in reverse_event_bindings and reverse_event_bindings[binding] != event_set_id:
            errors.append(f"同一密封事件集绑定了多个semantic_event_set_id: {reverse_event_bindings[binding]},{event_set_id}")
        reverse_event_bindings[binding] = event_set_id
        result.append(scope)
    missing_nodes = sorted(set(node_map) - covered_nodes)
    if missing_nodes:
        errors.append(f"活动玩法节点未绑定任何scope_instance: {','.join(missing_nodes)}")
    for node_id, node in node_map.items():
        declared = set(node.get("semantic_event_set_ids", []))
        missing = sorted(declared - covered_event_sets[node_id])
        if missing:
            errors.append(f"活动玩法节点存在未绑定scope_instance的语义事件集: {node_id} / {','.join(missing)}")
    return errors, result


def list_value(value):
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def validate_value_symbol_upgrade_profile_link(node, state_by_id):
    attributes = node.get("attributes", {})
    binding = attributes.get("value_upgrade_state_binding")
    if not semantic_truthy(attributes.get("value_upgrade_rule")):
        return [f"Value Symbol未声明升级规则时不得提供value_upgrade_state_binding: {node.get('node_id')}"] if binding is not None else []
    if not isinstance(binding, dict):
        return [f"Value Symbol存在升级规则但缺少value_upgrade_state_binding: {node.get('node_id')}"]
    required = {
        "persistent_state_id", "initial_assignment_semantic_event_set_id", "shared_semantic_event_set_id", "value_symbol_instance_id_field",
        "persistent_state_instance_id_field", "upgrade_check_event_id_field",
        "state_observation_point", "state_transition_event",
        "same_instance_bijective", "initial_assignment_maps_to_state_initial_value",
        "each_eligible_upgrade_check_maps_to_one_transition_opportunity",
        "no_upgrade_outcome_maps_to_self_transition", "initial_assignment_excluded_from_upgrade_observation",
        "value_domain_equal", "rule_evidence_sha256",
    }
    errors = []
    if set(binding) != required:
        errors.append(f"Value Symbol升级状态绑定必须完整使用十五个固定字段: {node.get('node_id')}")
    state_id = binding.get("persistent_state_id")
    state = state_by_id.get(state_id)
    if not isinstance(state, dict):
        errors.append(f"Value Symbol升级状态绑定引用未知持久状态: {node.get('node_id')} / {state_id}")
        return errors
    state_attributes = state.get("attributes", {})
    if state_attributes.get("state_shape") != "ordered_scalar":
        errors.append(f"Value Symbol升级状态必须为ordered_scalar: {node.get('node_id')} / {state_id}")
    if state_attributes.get("ordered_axis_semantics") != "nonnegative_multiplicative":
        errors.append(f"Value Symbol升级状态必须使用非负奖值乘法尺度: {node.get('node_id')} / {state_id}")
    if attributes.get("value_domain") != state_attributes.get("value_domain"):
        errors.append(f"Value Symbol升级状态值域必须与奖值域完全一致: {node.get('node_id')} / {state_id}")
    if binding.get("state_observation_point") not in state_attributes.get("observation_points", []):
        errors.append(f"Value Symbol升级状态观察点未由持久状态声明: {node.get('node_id')} / {state_id}")
    if binding.get("state_transition_event") not in state_attributes.get("transition_event_domain", []):
        errors.append(f"Value Symbol升级事件未由持久状态transition_event_domain声明: {node.get('node_id')} / {state_id}")
    shared_event = binding.get("shared_semantic_event_set_id")
    if shared_event not in node.get("semantic_event_set_ids", []) or shared_event not in state.get("semantic_event_set_ids", []):
        errors.append(f"Value Symbol升级状态未共享绑定事件集: {node.get('node_id')} / {state_id}")
    initial_event = binding.get("initial_assignment_semantic_event_set_id")
    if initial_event not in node.get("semantic_event_set_ids", []):
        errors.append(f"Value Symbol初始赋值事件集未由动态奖值节点声明: {node.get('node_id')}")
    if initial_event == shared_event:
        errors.append(f"Value Symbol初始赋值事件集不得混入升级检查观察事件集: {node.get('node_id')}")
    if binding.get("state_observation_point") != "before_each_eligible_upgrade_check":
        errors.append(f"Value Symbol升级状态必须在每次合格升级检查前观察: {node.get('node_id')}")
    if any(binding.get(field) is not True for field in (
        "same_instance_bijective", "initial_assignment_maps_to_state_initial_value",
        "each_eligible_upgrade_check_maps_to_one_transition_opportunity",
        "no_upgrade_outcome_maps_to_self_transition", "initial_assignment_excluded_from_upgrade_observation",
        "value_domain_equal",
    )):
        errors.append(f"Value Symbol升级状态绑定必须证明同实例、初值、检查前观察、每次合格检查和未升级自环完整映射: {node.get('node_id')}")
    if not all(non_empty(binding.get(field)) for field in (
        "value_symbol_instance_id_field", "persistent_state_instance_id_field",
        "upgrade_check_event_id_field", "state_observation_point", "state_transition_event",
    )) or not is_sha256(binding.get("rule_evidence_sha256")):
        errors.append(f"Value Symbol升级状态绑定缺少实例字段、升级检查事件字段、状态事件字段或规则证据hash: {node.get('node_id')}")
    return errors


def validate_profile_links(active_nodes):
    errors = []
    node_map = {
        node.get("node_id"): node
        for node in active_nodes
        if isinstance(node, dict) and isinstance(node.get("node_id"), str) and node.get("node_id")
    }
    state_by_id = {}
    for node in active_nodes:
        if node.get("mechanic_id") == "state.persistent-state":
            state_id = node.get("attributes", {}).get("state_id")
            if not isinstance(state_id, str) or not state_id:
                errors.append(f"持久状态state_id无效: {node.get('node_id')}")
                continue
            if state_id in state_by_id:
                errors.append(f"持久状态state_id重复: {state_id}")
            state_by_id[state_id] = node
    wild_effects = {}
    for node in active_nodes:
        if node.get("mechanic_id") not in {"modifier.wild-substitute", "modifier.expanding-wild"}:
            continue
        attributes = node.get("attributes", {})
        effect_id = attributes.get("wild_effect_id")
        owner_id = attributes.get("effect_owner_node_id")
        if not non_empty(effect_id) or not non_empty(owner_id):
            errors.append(f"Wild节点缺少wild_effect_id或effect_owner_node_id: {node.get('node_id')}")
            continue
        wild_effects.setdefault(effect_id, []).append(node)
    for effect_id, nodes in wild_effects.items():
        owner_ids = {node.get("attributes", {}).get("effect_owner_node_id") for node in nodes}
        if len(owner_ids) != 1:
            errors.append(f"同一wild_effect_id声明了多个经济效果Owner: {effect_id}")
            continue
        owner_id = next(iter(owner_ids))
        owner = node_map.get(owner_id)
        if owner not in nodes:
            errors.append(f"Wild经济效果Owner不属于同一wild_effect_id: {effect_id} / {owner_id}")
            continue
        owner_events = set(owner.get("semantic_event_set_ids", []))
        linked_multiplier_ids = {
            node.get("attributes", {}).get("linked_multiplier_id")
            for node in nodes
            if semantic_truthy(node.get("attributes", {}).get("linked_multiplier_id"))
        }
        if len(linked_multiplier_ids) > 1:
            errors.append(f"同一Wild经济效果绑定了多个倍率节点: {effect_id}")
        for node in nodes:
            if not owner_events.intersection(node.get("semantic_event_set_ids", [])):
                errors.append(f"同一Wild经济效果节点未与Owner共享语义事件集: {effect_id} / {node.get('node_id')}")
    for node in active_nodes:
        node_id = node.get("node_id")
        if node_id not in node_map:
            continue
        parent_id = node.get("parent_id")
        if parent_id is not None and (parent_id == node_id or parent_id not in node_map):
            errors.append(f"玩法节点parent_id无效: {node_id} / {parent_id}")
        mechanic_id = node.get("mechanic_id")
        attributes = node.get("attributes", {})
        if mechanic_id == BONUS_SEQUENCE_MECHANIC_ID:
            errors += validate_bonus_sequence_links(node, active_nodes)
        if mechanic_id == "award.value-symbol":
            errors += validate_value_symbol_upgrade_profile_link(node, state_by_id)
        if mechanic_id.startswith("trigger."):
            target_id = attributes.get("target_node_id")
            target_kind = attributes.get("target_kind")
            target = node_map.get(target_id) if isinstance(target_id, str) else None
            expected = (
                target_kind == "feature" and isinstance(target, dict) and target.get("mechanic_id") in FEATURE_MECHANIC_IDS
                or target_kind == "reward_state" and isinstance(target, dict) and target.get("mechanic_id") == "state.persistent-state"
            )
            if not expected:
                errors.append(f"触发节点target_node_id与target_kind未引用匹配的活动目标节点: {node_id}")
            elif target_kind == "feature" and target.get("parent_id") != node_id:
                errors.append(f"触发节点与目标Feature缺少明确parent_id依赖边: {node_id} / {target_id}")
            elif target_kind == "reward_state" and not set(node.get("semantic_event_set_ids", [])).intersection(target.get("semantic_event_set_ids", [])):
                errors.append(f"触发节点与目标奖励状态未共享语义事件集: {node_id} / {target_id}")
        if mechanic_id == "trigger.state-threshold":
            state_node_id = attributes.get("state_node_id")
            state_node = node_map.get(state_node_id) if isinstance(state_node_id, str) else None
            if not isinstance(state_node, dict) or state_node.get("mechanic_id") != "state.persistent-state":
                errors.append(f"状态阈值触发引用未知持久状态节点: {node_id}")
            elif not set(node.get("semantic_event_set_ids", [])).intersection(state_node.get("semantic_event_set_ids", [])):
                errors.append(f"状态阈值触发与持久状态节点未共享语义事件集: {node_id} / {state_node_id}")
            elif attributes.get("state_id") != state_node.get("attributes", {}).get("state_id"):
                errors.append(f"状态阈值触发state_id与引用的持久状态节点不一致: {node_id} / {state_node_id}")
        state_refs = []
        for field in ("persistent_state_ids", "persistent_state_id", "persistence_state_id", "output_state_id", "progression_state_id"):
            state_refs.extend(list_value(attributes.get(field)))
        for state_id in state_refs:
            if not isinstance(state_id, str):
                errors.append(f"玩法节点持久状态引用必须为字符串: {node_id}")
            elif semantic_truthy(state_id) and state_id not in state_by_id:
                errors.append(f"玩法节点引用未知持久状态: {node_id} / {state_id}")
            elif semantic_truthy(state_id) and not set(node.get("semantic_event_set_ids", [])).intersection(state_by_id[state_id].get("semantic_event_set_ids", [])):
                errors.append(f"玩法节点与持久状态引用未共享语义事件集: {node_id} / {state_id}")
        for binding in attributes.get("resource_count_derivation_bindings", []) if isinstance(attributes.get("resource_count_derivation_bindings"), list) else []:
            if not isinstance(binding, dict):
                continue
            source = binding.get("primary_owner_metric_instance")
            if not isinstance(source, dict):
                continue
            source_ids = source.get("source_node_ids")
            if not isinstance(source_ids, list) or len(source_ids) != 1:
                errors.append(f"Feature资源派生必须只引用一个来源指标实例: {node_id}")
                continue
            source_node = node_map.get(source_ids[0])
            source_metric_id = source.get("metric_id")
            valid_source = (
                source_metric_id == "board.symbol_count_per_board_distribution"
                and isinstance(source_node, dict)
                and source_node.get("mechanic_id") in {"board.fixed-grid", "board.variable-grid"}
                or source_metric_id == "trigger.symbol_count_distribution"
                and isinstance(source_node, dict)
                and source_node.get("mechanic_id", "").startswith("trigger.")
            )
            if not valid_source:
                errors.append(f"Feature资源派生来源节点与来源指标不一致: {node_id}")
                continue
            shared_event = binding.get("shared_semantic_event_set_id")
            if shared_event not in source_node.get("semantic_event_set_ids", []):
                errors.append(f"Feature资源派生来源与Feature未共享密封事件集: {node_id} / {source_ids[0]}")
            if source_metric_id == "trigger.symbol_count_distribution":
                target_id = source_node.get("attributes", {}).get("target_node_id")
                if target_id != node_id:
                    errors.append(f"Feature资源派生Trigger未指向当前Feature节点: {node_id} / {source_ids[0]}")
                entry_source = binding.get("derived_instance_dimensions", {}).get("entry_source")
                semantics = entry_source_semantics(node).get(entry_source)
                if entry_source is not None and (not isinstance(semantics, dict) or semantics.get("origin") != "endogenous"):
                    errors.append(f"外生Feature入口不得引用游戏内生Trigger数量Owner: {node_id} / {entry_source}")
        for binding in attributes.get("position_count_owner_bindings", []) if isinstance(attributes.get("position_count_owner_bindings"), list) else []:
            if not isinstance(binding, dict):
                continue
            source = binding.get("primary_owner_metric_instance")
            source_ids = source.get("source_node_ids") if isinstance(source, dict) else None
            if not isinstance(source_ids, list) or len(source_ids) != 1:
                errors.append(f"位置数量Owner绑定必须只引用一个专用玩法节点: {node_id}")
                continue
            owner_node = node_map.get(source_ids[0])
            owner_metric_id = source.get("metric_id")
            if not isinstance(owner_node, dict) or owner_node.get("mechanic_id") != "feature.hold-and-spin":
                errors.append(f"位置数量Owner绑定引用未知Hold & Spin节点: {node_id} / {source_ids[0]}")
                continue
            shared_event = binding.get("shared_semantic_event_set_id")
            if shared_event not in owner_node.get("semantic_event_set_ids", []):
                errors.append(f"位置数量Owner与持久状态未共享同一语义事件集: {node_id} / {source_ids[0]}")
            if owner_metric_id in {
                "hold_spin.initial_occupancy_distribution",
                "hold_spin.current_occupancy_distribution",
                "hold_spin.terminal_occupied_cell_count_distribution",
            }:
                capacity = integer_token(source.get("instance_dimensions", {}).get("actual_capacity"))
                capacity_map = parsed_integer_key_mapping(attributes.get("position_domain_by_actual_capacity"))
                expected_domain = capacity_map.get(capacity) if isinstance(capacity_map, dict) else attributes.get("position_domain", [])
                consumer_capacity = integer_token(binding.get("consumer_instance_dimensions", {}).get("actual_capacity"))
                if capacity is None or capacity != consumer_capacity or not isinstance(expected_domain, list) or len(expected_domain) != capacity:
                    errors.append(f"位置数量Owner与空间实例actual_capacity或对应position_domain不一致: {node_id}")
            elif owner_metric_id == "hold_spin.occupancy_transition_distribution":
                capacity_map = parsed_integer_key_mapping(attributes.get("position_domain_by_actual_capacity"))
                consumer_dimensions = binding.get("consumer_instance_dimensions", {})
                current_capacity = integer_token(consumer_dimensions.get("current_actual_capacity"))
                next_capacity = integer_token(consumer_dimensions.get("next_actual_capacity"))
                if not isinstance(capacity_map, dict) or current_capacity not in capacity_map or next_capacity not in capacity_map:
                    errors.append(f"位置角色残差Owner绑定缺少有效前后actual_capacity位置域: {node_id}")
        if mechanic_id == "feature.respin" and isinstance(attributes.get("retained_position_state_binding"), dict):
            binding = attributes["retained_position_state_binding"]
            state_node = node_map.get(binding.get("state_node_id"))
            if not isinstance(state_node, dict) or state_node.get("mechanic_id") != "state.persistent-state":
                errors.append(f"Respin保留位置绑定引用未知持久状态节点: {node_id}")
            else:
                state_attributes = state_node.get("attributes", {})
                if state_attributes.get("state_shape") != "position_set":
                    errors.append(f"Respin保留位置绑定的持久状态不是position_set: {node_id}")
                if binding.get("state_id") != state_attributes.get("state_id"):
                    errors.append(f"Respin保留位置绑定state_id不一致: {node_id}")
                if attributes.get("position_domain") != state_attributes.get("position_domain"):
                    errors.append(f"Respin与持久状态position_domain不一致: {node_id}")
                if binding.get("observation_point") not in state_attributes.get("observation_points", []):
                    errors.append(f"Respin保留位置绑定观测点未由持久状态声明: {node_id}")
                shared_event = binding.get("semantic_event_set_id")
                if (
                    shared_event not in node.get("semantic_event_set_ids", [])
                    or shared_event not in state_node.get("semantic_event_set_ids", [])
                ):
                    errors.append(f"Respin与持久状态保留位置绑定未共享同一语义事件集: {node_id}")
        for field in ("linked_multiplier_id", "multiplier_node_id"):
            linked = attributes.get(field)
            if semantic_truthy(linked) and (not isinstance(linked, str) or linked not in node_map or node_map[linked].get("mechanic_id") != "modifier.win-multiplier"):
                errors.append(f"玩法节点引用未知倍率节点: {node_id} / {linked}")
            elif semantic_truthy(linked) and not set(node.get("semantic_event_set_ids", [])).intersection(node_map[linked].get("semantic_event_set_ids", [])):
                errors.append(f"玩法节点与倍率引用未共享语义事件集: {node_id} / {linked}")
        if mechanic_id in {"modifier.wild-substitute", "modifier.expanding-wild"} and semantic_truthy(attributes.get("wild_multiplier_dependency_evidence")):
            evidence = attributes.get("wild_multiplier_dependency_evidence")
            linked = attributes.get("linked_multiplier_id")
            required_fields = {
                "linked_multiplier_node_id",
                "shared_semantic_event_set_id",
                "wild_assistance_state_domain",
                "multiplier_state_domain",
                "joint_observation_rule",
            }
            if not isinstance(evidence, dict):
                errors.append(f"Wild倍率专属依赖证据必须为对象: {node_id}")
            else:
                missing = sorted(required_fields - set(evidence))
                if missing:
                    errors.append(f"Wild倍率专属依赖证据字段缺失: {node_id} / {','.join(missing)}")
                if evidence.get("linked_multiplier_node_id") != linked:
                    errors.append(f"Wild倍率专属依赖证据引用与linked_multiplier_id不一致: {node_id}")
                multiplier = node_map.get(linked) if isinstance(linked, str) else None
                shared_event_set_id = evidence.get("shared_semantic_event_set_id")
                shared_event_sets = (
                    set(node.get("semantic_event_set_ids", [])).intersection(multiplier.get("semantic_event_set_ids", []))
                    if isinstance(multiplier, dict)
                    else set()
                )
                if not isinstance(shared_event_set_id, str) or shared_event_set_id not in shared_event_sets:
                    errors.append(f"Wild倍率专属依赖证据未绑定双方共享语义事件集: {node_id}")
                wild_states = evidence.get("wild_assistance_state_domain")
                if (
                    not isinstance(wild_states, list)
                    or len(wild_states) < 2
                    or not all(isinstance(value, str) and value for value in wild_states)
                    or len(wild_states) != len(set(map(str, wild_states)))
                    or "none" not in wild_states
                ):
                    errors.append(f"Wild倍率专属依赖证据的Wild状态域必须唯一且包含none及至少一个实际辅助状态: {node_id}")
                multiplier_states = evidence.get("multiplier_state_domain")
                required_multiplier_states = {"not_occurred", "not_applied", "1x"}
                if (
                    not isinstance(multiplier_states, list)
                    or not all(isinstance(value, str) and value for value in multiplier_states)
                    or len(multiplier_states) != len(set(map(str, multiplier_states)))
                    or not required_multiplier_states.issubset(set(multiplier_states))
                ):
                    errors.append(f"Wild倍率专属依赖证据的倍率状态域必须唯一且包含not_occurred、not_applied、1x: {node_id}")
                if not non_empty(evidence.get("joint_observation_rule")):
                    errors.append(f"Wild倍率专属依赖证据缺少联合观测规则: {node_id}")
        if mechanic_id == "modifier.win-multiplier" and attributes.get("progression_driver") == "cascade_depth":
            cascade_id = attributes.get("cascade_node_id")
            if not isinstance(cascade_id, str) or cascade_id not in node_map or node_map[cascade_id].get("mechanic_id") != "evolution.cascade":
                errors.append(f"Cascade驱动倍率引用未知Cascade节点: {node_id} / {cascade_id}")
            elif not set(node.get("semantic_event_set_ids", [])).intersection(node_map[cascade_id].get("semantic_event_set_ids", [])):
                errors.append(f"Cascade驱动倍率与Cascade节点未共享语义事件集: {node_id} / {cascade_id}")
            else:
                cascade_attributes = node_map[cascade_id].get("attributes", {})
                randomness = attributes.get("same_depth_multiplier_randomness")
                if cascade_attributes.get("same_depth_multiplier_randomness") is not randomness:
                    errors.append(f"倍率节点与Cascade节点的同深度倍率随机性声明不一致: {node_id} / {cascade_id}")
                if randomness is True and not (
                    semantic_truthy(attributes.get("dependency_evidence"))
                    or semantic_truthy(cascade_attributes.get("dependency_evidence"))
                ):
                    errors.append(f"同深度倍率仍随机时缺少Cascade倍率依赖证据: {node_id} / {cascade_id}")
        if mechanic_id == "modifier.win-multiplier" and isinstance(attributes.get("return_dependency_evidence"), dict):
            evidence = attributes["return_dependency_evidence"]
            shared_event = evidence.get("shared_semantic_event_set_id")
            if not non_empty(shared_event) or shared_event not in node.get("semantic_event_set_ids", []):
                errors.append(f"倍率回报依赖证据未绑定倍率节点共享语义事件集: {node_id}")
            controlled_ids = evidence.get("controlled_driver_node_ids")
            controlled_ids = controlled_ids if isinstance(controlled_ids, list) else []
            for controlled_id in controlled_ids:
                controlled = node_map.get(controlled_id)
                if not isinstance(controlled, dict) or controlled_id == node_id:
                    errors.append(f"倍率回报依赖证据引用未知或自身驱动节点: {node_id} / {controlled_id}")
                elif shared_event not in controlled.get("semantic_event_set_ids", []):
                    errors.append(f"倍率回报依赖受控驱动未共享同一语义事件集: {node_id} / {controlled_id}")
            expected_driver_ids, required_strata = set(), set()
            if attributes.get("progression_driver") == "cascade_depth" and non_empty(attributes.get("cascade_node_id")):
                expected_driver_ids.add(attributes["cascade_node_id"])
                required_strata.add("cascade_depth")
            persistent_ids = {
                value for value in (
                    attributes.get("persistent_state_id"),
                    attributes.get("progression_state_id"),
                )
                if non_empty(value)
            }
            for state_id in persistent_ids:
                state_node = state_by_id.get(state_id)
                if isinstance(state_node, dict):
                    expected_driver_ids.add(state_node.get("node_id"))
                    required_strata.add("persistent_multiplier_state")
            linked_wild_owners = {
                candidate.get("attributes", {}).get("effect_owner_node_id", candidate.get("node_id"))
                for candidate in active_nodes
                if candidate.get("mechanic_id") in {"modifier.wild-substitute", "modifier.expanding-wild"}
                and candidate.get("attributes", {}).get("linked_multiplier_id") == node_id
            }
            if linked_wild_owners:
                expected_driver_ids.update(linked_wild_owners)
                required_strata.add("wild_assistance_state")
            missing_drivers = sorted(expected_driver_ids - set(controlled_ids))
            if missing_drivers:
                errors.append(f"倍率回报依赖证据漏控已登记直接驱动节点: {node_id} / {','.join(missing_drivers)}")
            strata = evidence.get("control_stratum_fields")
            if isinstance(strata, list):
                missing_strata = sorted(required_strata - set(strata))
                if missing_strata:
                    errors.append(f"倍率回报依赖证据缺少直接驱动控制字段: {node_id} / {','.join(missing_strata)}")
        if mechanic_id == "award.jackpot":
            tier_domain = attributes.get("tier_domain")
            tier_domain = tier_domain if isinstance(tier_domain, list) else []
            exposures = attributes.get("jackpot_tier_exposure")
            if (
                not tier_domain
                or not all(isinstance(value, str) and value for value in tier_domain)
                or len(tier_domain) != len(set(tier_domain))
                or not isinstance(exposures, list)
                or not exposures
            ):
                errors.append(f"Jackpot层级域或逐层暴露无效: {node_id}")
                exposures = []
            exposure_tiers, opportunity_sets = [], {}
            for exposure in exposures:
                if not isinstance(exposure, dict):
                    errors.append(f"Jackpot逐层暴露存在非对象项: {node_id}")
                    continue
                tier_id = exposure.get("tier_id")
                opportunity_set_id = exposure.get("opportunity_set_id")
                opportunity_count = exposure.get("original_opportunity_count")
                hit_count = exposure.get("original_hit_count")
                rtp = exposure.get("original_rtp_contribution")
                exposure_tiers.append(tier_id)
                if (
                    tier_id not in tier_domain
                    or not non_empty(opportunity_set_id)
                    or not isinstance(opportunity_count, int) or isinstance(opportunity_count, bool) or opportunity_count < 1
                    or not isinstance(hit_count, int) or isinstance(hit_count, bool) or hit_count < 0 or hit_count > opportunity_count
                    or not finite_number(rtp) or rtp < 0
                    or not non_empty(exposure.get("evidence_path"))
                    or not is_sha256(exposure.get("evidence_sha256"))
                    or not isinstance(exposure.get("json_pointer"), str) or not exposure.get("json_pointer", "").startswith("/")
                ):
                    errors.append(f"Jackpot逐层暴露字段无效: {node_id} / {tier_id}")
                    continue
                evidence_path = safe_evidence_path(evidence_root, exposure.get("evidence_path")) if evidence_root is not None else None
                if evidence_path is None or not evidence_path.is_file() or sha(evidence_path) != exposure.get("evidence_sha256"):
                    errors.append(f"Jackpot逐层暴露证据文件不存在或hash失效: {node_id} / {tier_id}")
                else:
                    manifest_hashes = input_manifest.get("hashes", {}) if isinstance(input_manifest, dict) and isinstance(input_manifest.get("hashes"), dict) else {}
                    if manifest_hashes.get(exposure.get("evidence_path")) != exposure.get("evidence_sha256"):
                        errors.append(f"Jackpot逐层暴露证据未写入input_manifest.hashes: {node_id} / {tier_id}")
                    expected_claim = {
                        "tier_id": tier_id,
                        "opportunity_set_id": opportunity_set_id,
                        "original_opportunity_count": opportunity_count,
                        "original_hit_count": hit_count,
                        "original_rtp_contribution": rtp,
                        "tier_resolution_rule_sha256": canonical_sha256(attributes.get("tier_resolution_rule")),
                    }
                    try:
                        actual_claim = json_pointer_value(load(evidence_path), exposure.get("json_pointer"))
                        if actual_claim != expected_claim:
                            errors.append(f"Jackpot逐层暴露未由密封机会与派奖账本精确复算: {node_id} / {tier_id}")
                    except (OSError, ValueError, KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
                        errors.append(f"Jackpot逐层暴露证据格式无效: {node_id} / {tier_id} / {exc}")
                opportunity_sets.setdefault(opportunity_set_id, {"denominators": set(), "tiers": set(), "hit_count": 0})
                opportunity_sets[opportunity_set_id]["denominators"].add(opportunity_count)
                opportunity_sets[opportunity_set_id]["tiers"].add(tier_id)
                opportunity_sets[opportunity_set_id]["hit_count"] += hit_count
            if set(exposure_tiers) != set(tier_domain) or len(exposure_tiers) != len(set(exposure_tiers)):
                errors.append(f"Jackpot逐层暴露必须恰好覆盖tier_domain且每层唯一: {node_id}")
            for opportunity_set_id, values in opportunity_sets.items():
                if len(values["denominators"]) != 1:
                    errors.append(f"同一Jackpot机会集各层级必须使用相同原版机会分母: {node_id} / {opportunity_set_id}")
                elif values["hit_count"] > next(iter(values["denominators"])):
                    errors.append(f"同一Jackpot机会集逐层命中数合计不得超过机会分母: {node_id} / {opportunity_set_id}")
            owner_bindings = attributes.get("jackpot_material_owner_bindings", [])
            if owner_bindings is not None and not isinstance(owner_bindings, list):
                errors.append(f"Jackpot物质性Owner绑定必须为数组: {node_id}")
                owner_bindings = []
            seen_opportunities = set()
            for binding in owner_bindings:
                if not isinstance(binding, dict):
                    errors.append(f"Jackpot物质性Owner绑定存在非对象项: {node_id}")
                    continue
                opportunity_set_id = binding.get("opportunity_set_id")
                if opportunity_set_id in seen_opportunities:
                    errors.append(f"同一Jackpot机会集不得声明多个上游Owner: {node_id} / {opportunity_set_id}")
                seen_opportunities.add(opportunity_set_id)
                covered = binding.get("covered_tier_ids")
                covered = set(covered) if isinstance(covered, list) else set()
                expected_tiers = opportunity_sets.get(opportunity_set_id, {}).get("tiers", set())
                mapping = binding.get("source_outcome_to_jackpot_tier")
                mapped_tiers = {value for value in mapping.values() if value is not None} if isinstance(mapping, dict) else set()
                if not covered or not covered.issubset(expected_tiers) or mapped_tiers != covered:
                    errors.append(f"Jackpot物质性Owner覆盖层级或结果映射无效: {node_id} / {opportunity_set_id}")
                source_ref = binding.get("primary_owner_metric_instance")
                source_ids = source_ref.get("source_node_ids") if isinstance(source_ref, dict) else None
                source_metric_id = source_ref.get("metric_id") if isinstance(source_ref, dict) else None
                if not non_empty(source_metric_id):
                    errors.append(f"Jackpot物质性Owner来源指标ID无效: {node_id} / {opportunity_set_id}")
                if not isinstance(source_ids, list) or not source_ids:
                    errors.append(f"Jackpot物质性Owner来源节点为空: {node_id} / {opportunity_set_id}")
                    source_ids = []
                shared_event = binding.get("shared_semantic_event_set_id")
                if shared_event not in node.get("semantic_event_set_ids", []):
                    errors.append(f"Jackpot物质性Owner未绑定Jackpot节点共享事件集: {node_id} / {opportunity_set_id}")
                for source_id in source_ids:
                    source_node = node_map.get(source_id)
                    if not isinstance(source_node, dict) or shared_event not in source_node.get("semantic_event_set_ids", []):
                        errors.append(f"Jackpot物质性Owner来源节点未知或未共享事件集: {node_id} / {source_id}")
        if mechanic_id == "feature.hold-and-spin":
            jackpot_refs = list_value(attributes.get("jackpot_node_ids"))
            value_refs = list_value(attributes.get("value_symbol_node_ids"))
            collect_refs = list_value(attributes.get("collect_node_ids"))
            capacity_source_mechanics = {
                "variable_grid.reel_height_layout_distribution": "board.variable-grid",
                "variable_grid.valid_cell_layout_distribution": "board.variable-grid",
                "persistent_state.ordered_value_distribution": "state.persistent-state",
                "effective_ways.capacity_distribution": "settlement.effective-ways-capacity",
            }
            for binding in attributes.get("capacity_owner_bindings", []) if isinstance(attributes.get("capacity_owner_bindings"), list) else []:
                if not isinstance(binding, dict):
                    continue
                source = binding.get("primary_owner_metric_instance")
                source_ids = source.get("source_node_ids") if isinstance(source, dict) else None
                source_metric_id = source.get("metric_id") if isinstance(source, dict) else None
                if not isinstance(source_ids, list) or len(source_ids) != 1:
                    continue
                source_node = node_map.get(source_ids[0])
                expected_mechanic = capacity_source_mechanics.get(source_metric_id)
                if not isinstance(source_node, dict) or source_node.get("mechanic_id") != expected_mechanic:
                    errors.append(f"Hold & Spin容量Owner来源节点与来源指标不一致: {node_id} / {source_ids[0]}")
                    continue
                shared_event = binding.get("shared_semantic_event_set_id")
                if shared_event not in node.get("semantic_event_set_ids", []) or shared_event not in source_node.get("semantic_event_set_ids", []):
                    errors.append(f"Hold & Spin容量Owner来源未共享观察事件集: {node_id} / {source_ids[0]}")
                if source_metric_id == "persistent_state.ordered_value_distribution":
                    source_attributes = source_node.get("attributes", {})
                    if source_attributes.get("state_shape") != "ordered_scalar":
                        errors.append(f"Hold & Spin容量Owner引用的持久状态必须为ordered_scalar: {node_id} / {source_ids[0]}")
            if semantic_truthy(attributes.get("jackpot_rule")) and not jackpot_refs:
                errors.append(f"Hold & Spin存在Jackpot规则但未绑定jackpot_node_ids: {node_id}")
            if semantic_truthy(attributes.get("collector_rule")) and not collect_refs:
                errors.append(f"Hold & Spin存在Collect规则但未绑定collect_node_ids: {node_id}")
            for ref in jackpot_refs:
                if not isinstance(ref, str) or ref not in node_map or node_map[ref].get("mechanic_id") != "award.jackpot":
                    errors.append(f"Hold & Spin引用未知Jackpot节点: {node_id} / {ref}")
                elif not set(node.get("semantic_event_set_ids", [])).intersection(node_map[ref].get("semantic_event_set_ids", [])):
                    errors.append(f"Hold & Spin与Jackpot节点未共享语义事件集: {node_id} / {ref}")
            for ref in value_refs:
                if not isinstance(ref, str) or ref not in node_map or node_map[ref].get("mechanic_id") != "award.value-symbol":
                    errors.append(f"Hold & Spin引用未知动态奖值节点: {node_id} / {ref}")
                elif not set(node.get("semantic_event_set_ids", [])).intersection(node_map[ref].get("semantic_event_set_ids", [])):
                    errors.append(f"Hold & Spin与动态奖值节点未共享语义事件集: {node_id} / {ref}")
            for ref in collect_refs:
                if not isinstance(ref, str) or ref not in node_map or node_map[ref].get("mechanic_id") != "modifier.collect":
                    errors.append(f"Hold & Spin引用未知Collect节点: {node_id} / {ref}")
                elif not set(node.get("semantic_event_set_ids", [])).intersection(node_map[ref].get("semantic_event_set_ids", [])):
                    errors.append(f"Hold & Spin与Collect节点未共享语义事件集: {node_id} / {ref}")
        if mechanic_id == "modifier.symbol-transform":
            for ref in list_value(attributes.get("value_symbol_node_ids")):
                if not isinstance(ref, str) or ref not in node_map or node_map[ref].get("mechanic_id") != "award.value-symbol":
                    errors.append(f"符号变形引用未知动态奖值节点: {node_id} / {ref}")
                elif not set(node.get("semantic_event_set_ids", [])).intersection(node_map[ref].get("semantic_event_set_ids", [])):
                    errors.append(f"符号变形与动态奖值节点未共享语义事件集: {node_id} / {ref}")
        if mechanic_id == "board.variable-grid":
            node_events = set(node.get("semantic_event_set_ids", []))
            capacity_mode = attributes.get("ways_capacity_mode")
            capacity_relevant = any(
                candidate.get("mechanic_id") == "settlement.ways"
                and node_events.intersection(candidate.get("semantic_event_set_ids", []))
                for candidate in active_nodes
            )
            if capacity_relevant and capacity_mode == "none":
                errors.append(f"与Ways共享结算事件的可变网格不得把ways_capacity_mode设为none: {node_id}")
            if not capacity_relevant and capacity_mode != "none":
                errors.append(f"未关联Ways结算的可变网格必须把ways_capacity_mode设为none: {node_id}")
            bindings = attributes.get("layout_capacity_projection_bindings")
            if capacity_mode in {"layout_only", "layout_plus_non_layout"}:
                if not isinstance(bindings, list) or not bindings:
                    errors.append(f"可变网格容量公式缺少layout_capacity_projection_bindings: {node_id}")
                else:
                    source_ids = []
                    required_fields = {
                        "source_metric_id", "source_layout_to_capacity",
                        "mapping_total_and_deterministic", "rule_evidence_sha256",
                    }
                    for index, binding in enumerate(bindings, 1):
                        if not isinstance(binding, dict) or set(binding) != required_fields:
                            errors.append(f"可变网格第{index}条容量投影绑定必须完整使用四个固定字段: {node_id}")
                            continue
                        source_metric_id = binding.get("source_metric_id")
                        source_ids.append(source_metric_id)
                        if source_metric_id not in {
                            "variable_grid.reel_height_layout_distribution",
                            "variable_grid.valid_cell_layout_distribution",
                        }:
                            errors.append(f"可变网格容量投影来源指标无效: {node_id}")
                        mapping = binding.get("source_layout_to_capacity")
                        if (
                            not isinstance(mapping, dict)
                            or not mapping
                            or any(not non_empty(label) for label in mapping)
                            or any(not finite_number(value) or value <= 0 for value in mapping.values())
                        ):
                            errors.append(f"可变网格容量投影映射必须使用非空布局标签和正容量: {node_id}")
                        if binding.get("mapping_total_and_deterministic") is not True or not is_sha256(binding.get("rule_evidence_sha256")):
                            errors.append(f"可变网格容量投影必须证明完整确定映射并绑定规则证据hash: {node_id}")
                    if len(source_ids) != len(set(source_ids)):
                        errors.append(f"可变网格容量投影不得重复来源指标: {node_id}")
            elif bindings is not None:
                errors.append(f"可变网格没有容量公式时不得声明layout_capacity_projection_bindings: {node_id}")
            effective_nodes = [
                candidate for candidate in active_nodes
                if candidate.get("mechanic_id") == "settlement.effective-ways-capacity"
                and node_events.intersection(candidate.get("semantic_event_set_ids", []))
            ]
            if capacity_mode == "layout_plus_non_layout" and len(effective_nodes) != 1:
                errors.append(f"layout_plus_non_layout必须唯一绑定共享事件集的动态实际Ways容量节点: {node_id}")
            if capacity_mode == "layout_only" and effective_nodes:
                errors.append(f"layout_only不得在同一事件集重复绑定动态实际Ways容量Owner: {node_id}")
        if mechanic_id == "settlement.effective-ways-capacity":
            binding = attributes.get("geometry_layout_binding")
            board_id = binding.get("board_node_id") if isinstance(binding, dict) else None
            board = node_map.get(board_id)
            if not isinstance(board, dict) or board.get("mechanic_id") not in {"board.fixed-grid", "board.variable-grid"}:
                errors.append(f"动态实际Ways容量引用未知网格节点: {node_id} / {board_id}")
                continue
            shared_event = binding.get("shared_semantic_event_set_id")
            if shared_event not in node.get("semantic_event_set_ids", []) or shared_event not in board.get("semantic_event_set_ids", []):
                errors.append(f"动态实际Ways容量与网格节点未共享geometry_layout事件集: {node_id} / {board_id}")
            geometry_domain = attributes.get("geometry_layout_domain")
            board_attributes = board.get("attributes", {})
            if board.get("mechanic_id") == "board.fixed-grid":
                if not isinstance(geometry_domain, list) or len(geometry_domain) != 1:
                    errors.append(f"固定网格动态Ways容量必须使用唯一geometry_layout_domain: {node_id}")
            else:
                if board_attributes.get("ways_capacity_mode") != "layout_plus_non_layout":
                    errors.append(f"可变网格与动态实际Ways容量绑定时ways_capacity_mode必须为layout_plus_non_layout: {board_id}")
                mappings = [
                    value.get("source_layout_to_capacity")
                    for value in board_attributes.get("layout_capacity_projection_bindings", [])
                    if isinstance(value, dict) and isinstance(value.get("source_layout_to_capacity"), dict)
                ]
                layout_labels = set().union(*(set(value) for value in mappings)) if mappings else set()
                if not isinstance(geometry_domain, list) or set(geometry_domain) != layout_labels:
                    errors.append(f"动态实际Ways容量geometry_layout_domain必须与可变网格活动布局标签完全一致: {node_id}")
        if mechanic_id == "settlement.ways":
            node_events = set(node.get("semantic_event_set_ids", []))
            variable_boards = [
                candidate for candidate in active_nodes
                if candidate.get("mechanic_id") == "board.variable-grid"
                and candidate.get("attributes", {}).get("ways_capacity_mode") in {"layout_only", "layout_plus_non_layout"}
                and node_events.intersection(candidate.get("semantic_event_set_ids", []))
            ]
            effective_nodes = [
                candidate for candidate in active_nodes
                if candidate.get("mechanic_id") == "settlement.effective-ways-capacity"
                and node_events.intersection(candidate.get("semantic_event_set_ids", []))
            ]
            expected_variable = bool(variable_boards or effective_nodes)
            if attributes.get("variable_ways") is not expected_variable:
                errors.append(f"settlement.ways.variable_ways与布局或非几何容量画像不一致: {node_id}")
    for node in active_nodes:
        if node.get("mechanic_id") in FEATURE_MECHANIC_IDS and "natural" in entry_source_tokens(node):
            if not any(
                candidate.get("mechanic_id", "").startswith("trigger.")
                and candidate.get("attributes", {}).get("target_node_id") == node["node_id"]
                and candidate.get("attributes", {}).get("target_kind") == "feature"
                and node.get("parent_id") == candidate.get("node_id")
                for candidate in active_nodes
            ):
                errors.append(f"自然入口Feature缺少指向自身的活动触发节点: {node.get('node_id')}")
    for node in active_nodes:
        visited, current = set(), node
        while current.get("parent_id") is not None and current.get("parent_id") in node_map:
            current_id = current.get("node_id")
            if current_id in visited:
                errors.append(f"玩法节点parent_id形成环: {node.get('node_id')}")
                break
            visited.add(current_id)
            current = node_map[current["parent_id"]]
    return errors


def validate_mode_contract(profile, contract, active_nodes):
    profile_scope = profile.get("scope") if isinstance(profile.get("scope"), dict) else {}
    contract_scope = contract.get("scope") if isinstance(contract.get("scope"), dict) else {}
    profile_mode = profile_scope.get("mode_contract")
    contract_mode = contract_scope.get("mode_contract")
    errors = []
    if not isinstance(profile_mode, dict):
        return ["新任务game_profile.scope缺少mode_contract"]
    if not isinstance(contract_mode, dict):
        return ["新任务metric_contract.scope缺少mode_contract"]
    if profile_mode != contract_mode:
        errors.append("metric_contract.scope.mode_contract与阶段1画像不一致")
    if profile_mode.get("mode_id") != profile_scope.get("mode") or contract_mode.get("mode_id") != contract_scope.get("mode"):
        errors.append("mode_contract.mode_id必须分别等于game_profile与metric_contract的scope.mode")
    if profile_mode.get("mixed_sample_forbidden") is not True:
        errors.append("mode_contract.mixed_sample_forbidden必须为true")
    paid = profile_mode.get("paid_configuration")
    if not isinstance(paid, dict) or paid.get("fixed_for_task") is not True or not is_sha256(paid.get("evidence_sha256")):
        errors.append("mode_contract.paid_configuration必须固定本任务付费配置并绑定规则证据")
    selections = profile_mode.get("feature_mode_selections")
    if not isinstance(selections, list):
        selections = []
        errors.append("mode_contract.feature_mode_selections必须为数组")
    records = {}
    for record in selections:
        node_id = record.get("feature_node_id") if isinstance(record, dict) else None
        if not non_empty(node_id) or node_id in records:
            errors.append("mode_contract.feature_mode_selections存在空或重复feature_node_id")
            continue
        records[node_id] = record
    expected_choice_nodes = set()
    for node in active_nodes:
        if node.get("mechanic_id") != "feature.free-spin":
            continue
        node_id = node.get("node_id")
        attributes = node.get("attributes", {})
        domain = attributes.get("feature_mode_domain")
        selected = attributes.get("selected_feature_mode_id")
        rule = attributes.get("mode_selection_rule")
        role = attributes.get("player_input_role")
        if not isinstance(domain, list) or not domain or len(domain) != len(set(domain)) or selected not in domain:
            errors.append(f"Free Spin模式域或固定选择无效: {node_id}")
            continue
        if not isinstance(rule, dict):
            errors.append(f"Free Spin缺少结构化mode_selection_rule: {node_id}")
            continue
        selection_type = rule.get("selection_type")
        if selection_type == "player_choice_before_feature":
            expected_choice_nodes.add(node_id)
            record = records.get(node_id)
            if not isinstance(record, dict):
                errors.append(f"玩家可选Free Spin节点未写入mode_contract: {node_id}")
                continue
            expected = {
                "feature_node_id": node_id,
                "mode_domain": domain,
                "selected_mode_id": selected,
                "selection_rule": rule.get("selection_timing"),
                "player_input_role": role,
                "fixed_for_task": True,
                "evidence_sha256": rule.get("evidence_sha256"),
            }
            if record != expected:
                errors.append(f"mode_contract中的Free Spin固定模式未与画像逐字段一致: {node_id}")
        elif node_id in records:
            errors.append(f"非玩家可选Free Spin节点不得写入feature_mode_selections: {node_id}")
    extra = set(records) - expected_choice_nodes
    if extra:
        errors.append(f"mode_contract引用了非活动或非玩家可选Feature节点: {','.join(sorted(extra))}")
    return errors


def numeric_domain(values):
    if not isinstance(values, list) or not values:
        return None
    result = []
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(number) or number < 0 or number in result:
            return None
        result.append(number)
    return result


def value_symbol_multiplier_bindings(active_nodes):
    return [
        (node, node.get("attributes", {}).get("value_symbol_effective_multiplier_binding"))
        for node in active_nodes
        if node.get("mechanic_id") == "modifier.win-multiplier"
        and isinstance(node.get("attributes", {}).get("value_symbol_effective_multiplier_binding"), dict)
    ]


def validate_value_symbol_multiplier_profile_bindings(active_nodes):
    node_map = {node.get("node_id"): node for node in active_nodes if non_empty(node.get("node_id"))}
    errors, pairs = [], set()
    required_fields = {
        "value_symbol_node_id",
        "multiplier_node_id",
        "shared_semantic_event_set_id",
        "value_symbol_instance_id_field",
        "multiplier_application_event_id_field",
        "event_pairing_bijective",
        "all_assignments_realized_exactly_once",
        "same_event_universe",
        "no_additional_multiplier_source",
        "value_to_effective_multiplier_mapping",
        "mapping_total_and_bijective",
        "primary_owner_metric_id",
        "rule_evidence_sha256",
    }
    for multiplier, binding in value_symbol_multiplier_bindings(active_nodes):
        label = f"倍率节点{multiplier.get('node_id')}的Value Symbol Owner绑定"
        if set(binding) != required_fields:
            errors.append(f"{label}必须完整使用十三个固定字段")
            continue
        value_node = node_map.get(binding.get("value_symbol_node_id"))
        if binding.get("multiplier_node_id") != multiplier.get("node_id"):
            errors.append(f"{label}的multiplier_node_id未指向当前节点")
        if value_node is None or value_node.get("mechanic_id") != "award.value-symbol":
            errors.append(f"{label}未指向有效award.value-symbol节点")
            continue
        pair = (value_node.get("node_id"), multiplier.get("node_id"))
        if pair in pairs:
            errors.append(f"Value Symbol与倍率节点重复Owner绑定: {pair[0]} / {pair[1]}")
        pairs.add(pair)
        linked = value_node.get("attributes", {}).get("linked_multiplier_node_ids")
        if not isinstance(linked, list) or linked != [multiplier.get("node_id")]:
            errors.append(f"{label}要求Value Symbol只链接当前唯一倍率节点")
        event_set = binding.get("shared_semantic_event_set_id")
        if event_set not in value_node.get("semantic_event_set_ids", []) or event_set not in multiplier.get("semantic_event_set_ids", []):
            errors.append(f"{label}未绑定双方共享语义事件集")
        if any(binding.get(field) is not True for field in (
            "event_pairing_bijective",
            "all_assignments_realized_exactly_once",
            "same_event_universe",
            "no_additional_multiplier_source",
            "mapping_total_and_bijective",
        )):
            errors.append(f"{label}缺少完整一一兑现、同域、无额外来源或双向映射证明")
        if not is_sha256(binding.get("rule_evidence_sha256")):
            errors.append(f"{label}缺少有效规则证据SHA-256")
        value_domain = numeric_domain(value_node.get("attributes", {}).get("value_domain"))
        multiplier_domain = numeric_domain(multiplier.get("attributes", {}).get("value_domain"))
        mapping = binding.get("value_to_effective_multiplier_mapping")
        numeric_mapping = parsed_numeric_mapping(mapping)
        if (
            value_domain is None
            or multiplier_domain is None
            or numeric_mapping is None
            or set(numeric_mapping) != set(value_domain)
            or set(numeric_mapping.values()) != set(multiplier_domain)
            or len(numeric_mapping.values()) != len(set(numeric_mapping.values()))
        ):
            errors.append(f"{label}的值映射必须完整双射覆盖双方实际value_domain")
    return errors


def validate_cascade_multiplier_profile_bindings(active_nodes):
    node_map = {node.get("node_id"): node for node in active_nodes if non_empty(node.get("node_id"))}
    required = {
        "cascade_node_id",
        "multiplier_node_id",
        "shared_semantic_event_set_id",
        "terminal_depth_semantics",
        "settlement_step_index_semantics",
        "terminal_depth_to_step_states",
        "all_reachable_depths_covered",
        "mapping_total_and_deterministic",
        "extra_random_or_state_dependency",
        "rule_evidence_sha256",
    }
    state_fields = {
        "settlement_step_index",
        "multiplier_state_id",
        "multiplier_occurred",
        "multiplier_applied",
        "effective_multiplier",
    }
    errors = []
    for multiplier in active_nodes:
        attributes = multiplier.get("attributes", {})
        if multiplier.get("mechanic_id") != "modifier.win-multiplier" or attributes.get("progression_driver") != "cascade_depth":
            continue
        randomness = attributes.get("same_depth_multiplier_randomness")
        binding = attributes.get("cascade_depth_multiplier_binding")
        if randomness is True:
            if binding is not None:
                errors.append(f"同一深度仍有倍率随机性时不得声明确定Cascade映射: {multiplier.get('node_id')}")
            continue
        if randomness is not False or not isinstance(binding, dict):
            errors.append(f"同深度倍率确定时必须提供cascade_depth_multiplier_binding: {multiplier.get('node_id')}")
            continue
        label = f"倍率节点{multiplier.get('node_id')}的Cascade确定映射"
        if set(binding) != required:
            errors.append(f"{label}必须完整使用十个固定字段")
            continue
        cascade = node_map.get(binding.get("cascade_node_id"))
        if cascade is None or cascade.get("mechanic_id") != "evolution.cascade":
            errors.append(f"{label}未指向有效Cascade节点")
            continue
        if binding.get("multiplier_node_id") != multiplier.get("node_id") or attributes.get("cascade_node_id") != cascade.get("node_id"):
            errors.append(f"{label}的双方节点引用不闭合")
        event_set = binding.get("shared_semantic_event_set_id")
        if event_set not in multiplier.get("semantic_event_set_ids", []) or event_set not in cascade.get("semantic_event_set_ids", []):
            errors.append(f"{label}未绑定双方共享语义事件集")
        if binding.get("terminal_depth_semantics") != "completed_cascade_settlement_count_0_based":
            errors.append(f"{label}的终局深度语义无效")
        if binding.get("settlement_step_index_semantics") != "initial_settlement_0_then_cascade_step_1_based":
            errors.append(f"{label}的结算步骤语义无效")
        if (
            binding.get("all_reachable_depths_covered") is not True
            or binding.get("mapping_total_and_deterministic") is not True
            or binding.get("extra_random_or_state_dependency") is not False
        ):
            errors.append(f"{label}必须证明完整确定覆盖且不存在额外依赖")
        if not is_sha256(binding.get("rule_evidence_sha256")):
            errors.append(f"{label}缺少有效规则证据SHA-256")
        mapping = binding.get("terminal_depth_to_step_states")
        if not isinstance(mapping, dict) or not mapping:
            errors.append(f"{label}缺少终局深度到逐步倍率状态映射")
            continue
        multiplier_domain = numeric_domain(attributes.get("value_domain"))
        parsed_depths = {}
        for depth_label, states in mapping.items():
            depth = integer_token(depth_label)
            if depth is None or depth < 0 or depth in parsed_depths:
                errors.append(f"{label}包含无效或重复终局深度: {depth_label}")
                continue
            parsed_depths[depth] = states
            if not isinstance(states, list) or len(states) != depth + 1:
                errors.append(f"{label}的每个终局深度必须覆盖步骤0至depth: {depth_label}")
                continue
            indexes = []
            for state in states:
                if not isinstance(state, dict) or set(state) != state_fields:
                    errors.append(f"{label}的逐步倍率状态必须完整使用五个固定字段: {depth_label}")
                    continue
                step = state.get("settlement_step_index")
                indexes.append(step)
                if not non_empty(state.get("multiplier_state_id")):
                    errors.append(f"{label}的逐步倍率状态缺少multiplier_state_id: {depth_label}/{step}")
                occurred, applied = state.get("multiplier_occurred"), state.get("multiplier_applied")
                effective = state.get("effective_multiplier")
                if not isinstance(occurred, bool) or not isinstance(applied, bool) or applied and not occurred:
                    errors.append(f"{label}的出现与应用状态逻辑无效: {depth_label}/{step}")
                if applied:
                    if not finite_number(effective) or multiplier_domain is None or float(effective) not in multiplier_domain:
                        errors.append(f"{label}的生效倍率不在value_domain: {depth_label}/{step}")
                elif effective is not None:
                    errors.append(f"{label}未应用步骤的effective_multiplier必须为null: {depth_label}/{step}")
            if indexes != list(range(depth + 1)):
                errors.append(f"{label}的结算步骤必须按0至depth连续排列: {depth_label}")
        if parsed_depths and set(parsed_depths) != set(range(max(parsed_depths) + 1)):
            errors.append(f"{label}的终局深度映射必须从0连续覆盖")
        step_states = {}
        for depth, states in parsed_depths.items():
            if not isinstance(states, list):
                continue
            for state in states:
                if not isinstance(state, dict) or set(state) != state_fields:
                    continue
                step = state.get("settlement_step_index")
                signature = tuple((field, state.get(field)) for field in sorted(state_fields - {"settlement_step_index"}))
                if step in step_states and step_states[step] != signature:
                    errors.append(f"{label}同一实际结算步骤在不同终局深度下出现不一致倍率状态: {step}")
                step_states[step] = signature
    return errors


def required_package_ids(active_nodes, catalog):
    result = {"core.general"}
    for node in active_nodes:
        mechanic = catalog["mechanics"][node["mechanic_id"]]
        result.update(mechanic.get("metric_requirements", {}).get("required_packages", []))
    if any(
        node.get("mechanic_id") in FEATURE_MECHANIC_IDS and endogenous_entry_sources(node)
        for node in active_nodes
    ):
        result.add("atomic.trigger")
    for package_id, package in catalog["metric_packages"].items():
        if package_id == "atomic.trigger" and not (
            any(node.get("mechanic_id", "").startswith("trigger.") for node in active_nodes)
            or any(
                node.get("mechanic_id") in FEATURE_MECHANIC_IDS and endogenous_entry_sources(node)
                for node in active_nodes
            )
        ):
            continue
        if condition_matches(package.get("applies_when", {}), active_nodes):
            result.add(package_id)
    return result


def required_core_component_ids(active_nodes):
    node_map = {
        node.get("node_id"): node
        for node in active_nodes
        if isinstance(node, dict) and non_empty(node.get("node_id"))
    }
    components = {"base"}
    for node_id, node in node_map.items():
        if node.get("mechanic_id") not in FEATURE_MECHANIC_IDS:
            continue
        current = node
        nested = False
        visited = set()
        while isinstance(current.get("parent_id"), str) and current["parent_id"] in node_map:
            parent_id = current["parent_id"]
            if parent_id in visited:
                break
            visited.add(parent_id)
            current = node_map[parent_id]
            if current.get("mechanic_id") in FEATURE_MECHANIC_IDS:
                nested = True
                break
        if not nested:
            components.add(f"feature:{node_id}")
    return components


def expected_metrics(active_nodes, scope_instances, package_ids, catalog, errors):
    expected, package_metrics, expected_bindings = set(), {}, {}
    active_node_map = {node["node_id"]: node for node in active_nodes}

    def wild_effect_source_sets():
        grouped = {}
        for node in active_nodes:
            if node.get("mechanic_id") not in {"modifier.wild-substitute", "modifier.expanding-wild"}:
                continue
            effect_id = node.get("attributes", {}).get("wild_effect_id")
            if non_empty(effect_id):
                grouped.setdefault(effect_id, set()).add(node["node_id"])
        return [nodes for _, nodes in sorted(grouped.items())]

    def wild_multiplier_source_sets():
        result = []
        for wild_ids in wild_effect_source_sets():
            wild_nodes = [active_node_map[node_id] for node_id in wild_ids]
            linked_ids = {
                node.get("attributes", {}).get("linked_multiplier_id")
                for node in wild_nodes
                if semantic_truthy(node.get("attributes", {}).get("linked_multiplier_id"))
            }
            if len(linked_ids) != 1:
                continue
            multiplier_id = next(iter(linked_ids))
            multiplier = active_node_map.get(multiplier_id)
            if not isinstance(multiplier, dict) or multiplier.get("mechanic_id") != "modifier.win-multiplier":
                continue
            if not semantic_truthy(multiplier.get("attributes", {}).get("linked_symbol_domain")):
                continue
            valid_evidence = any(
                isinstance(node.get("attributes", {}).get("wild_multiplier_dependency_evidence"), dict)
                and node["attributes"]["wild_multiplier_dependency_evidence"].get("linked_multiplier_node_id") == multiplier_id
                for node in wild_nodes
            )
            if valid_evidence:
                result.append(set(wild_ids) | {multiplier_id})
        return result

    def add_instance(package_id, metric, source_ids, dimensions, binding=None):
        source_key = tuple(sorted(source_ids))
        dimension_key = dimensions_key(dimensions)
        key = (metric["metric_id"], source_key, dimension_key)
        expected.add(key)
        package_metrics.setdefault((package_id, source_key, dimension_key), set()).add(metric["metric_id"])
        if binding is not None:
            previous = expected_bindings.get(key)
            if previous is not None and previous.get("scope_instance_id") != binding.get("scope_instance_id"):
                errors.append(f"指标实例绑定多个scope_instance: {format_instance(key)}")
            expected_bindings[key] = binding
        return key

    for package_id in sorted(package_ids):
        package = catalog["metric_packages"].get(package_id)
        if package is None:
            errors.append(f"玩法要求引用未知指标包: {package_id}")
            continue
        matched = []
        for metric in package.get("metrics", []):
            if package_id == "core.general":
                metric_id = metric["metric_id"]
                feature_nodes = [
                    node for node in active_nodes
                    if node.get("mechanic_id") in FEATURE_MECHANIC_IDS
                ]
                if metric_id == "core.feature.natural_trigger_rate":
                    for node in feature_nodes:
                        if not endogenous_entry_sources(node):
                            continue
                        matched_scopes = [
                            scope for scope in scope_instances
                            if node["node_id"] in scope.get("source_node_ids", [])
                            and scope.get("sample_unit") == metric.get("sample_unit")
                            and scope.get("dimensions", {}).get("entry_source_domain") == "endogenous"
                        ]
                        if len(matched_scopes) != 1:
                            errors.append(f"自然Feature必须唯一绑定entry_source_domain=endogenous scope_instance: {node['node_id']}")
                            continue
                        matched.append(add_instance(package_id, metric, {node["node_id"]}, {"entry_source_domain": "endogenous"}, matched_scopes[0]))
                    continue
                elif metric_id in {"core.sigma", "core.rtp.component_contribution"}:
                    core_scopes = [
                        scope for scope in scope_instances
                        if scope.get("scope_role") == "core"
                        and scope.get("sample_unit") == metric.get("sample_unit")
                    ]
                    if metric_id == "core.sigma":
                        overall = [scope for scope in core_scopes if scope.get("dimensions", {}).get("component") == "overall"]
                        if len(overall) != 1:
                            errors.append("core.sigma必须唯一绑定overall核心scope_instance")
                        else:
                            matched.append(add_instance(package_id, metric, set(), {}, overall[0]))
                    group_names = ("component", "state") if metric_id == "core.sigma" else ("component",)
                    groups = {}
                    for scope in core_scopes:
                        dimensions = scope.get("dimensions", {})
                        if dimensions.get("component") == "overall":
                            continue
                        if not non_empty(dimensions.get("component")):
                            errors.append(f"Core组件scope_instance缺少component维度: {scope.get('scope_instance_id')}")
                            continue
                        selected = {name: dimensions[name] for name in group_names if name in dimensions}
                        if metric_id == "core.sigma" and "state" in metric_dimension_names(metric) and "state" not in selected:
                            errors.append(f"core.sigma组件scope_instance缺少state维度: {scope.get('scope_instance_id')}")
                            continue
                        key = dimensions_key(selected)
                        if key in groups:
                            errors.append(f"Core指标相同维度绑定多个scope_instance: {metric_id} / {dict(key)}")
                            continue
                        groups[key] = scope
                    for dimension_key, scope in sorted(groups.items(), key=dimension_mapping_sort_key):
                        matched.append(add_instance(package_id, metric, set(scope.get("source_node_ids", [])), dict(dimension_key), scope))
                    components = {dict(key).get("component") for key in groups}
                    if not groups:
                        errors.append(f"{metric_id}缺少任何组件scope_instance")
                    required_components = required_core_component_ids(active_nodes)
                    missing_components = sorted(required_components - components)
                    unknown_feature_components = sorted(
                        component for component in components
                        if isinstance(component, str)
                        and component.startswith("feature:")
                        and component not in required_components
                    )
                    if missing_components:
                        errors.append(f"{metric_id}缺少画像推导的组件scope_instance: {','.join(missing_components)}")
                    if unknown_feature_components:
                        errors.append(f"{metric_id}包含未知或嵌套Feature组件scope_instance: {','.join(unknown_feature_components)}")
                    continue
                else:
                    source_sets = [set()]
            else:
                if metric.get("metric_id") == "trigger.entry_source_distribution":
                    source_sets = [
                        {node["node_id"]}
                        for node in active_nodes
                        if node.get("mechanic_id") in FEATURE_MECHANIC_IDS
                        and endogenous_entry_sources(node)
                    ]
                elif metric.get("metric_id") in WILD_ECONOMIC_METRIC_IDS:
                    source_sets = wild_effect_source_sets()
                elif metric.get("metric_id") == "wild_multiplier.dependence_residual":
                    source_sets = wild_multiplier_source_sets()
                else:
                    source_sets = condition_matches(metric.get("profile_match", {}), active_nodes)
            for source_ids in source_sets:
                for dimensions, binding in metric_dimensions(metric, source_ids, scope_instances, active_node_map, errors):
                    matched.append(add_instance(package_id, metric, source_ids, dimensions, binding))
        effective = [
            catalog["metrics"][metric_id]
            for metric_id, _, _ in matched
            if catalog["metrics"][metric_id].get("semantic_role") in {"primary", "guard_cross_check"}
            or catalog["metrics"][metric_id].get("audit_profile", {}).get("blocking_on_missing") is True
        ]
        if package_id != "core.general" and not effective:
            errors.append(f"必需指标包没有命中有效承接指标: {package_id}")
    return expected, package_metrics, expected_bindings


def validate_package_matches(contract, package_metrics, expected_bindings, active_nodes):
    errors, declared = [], {}
    nodes = {node["node_id"]: node for node in active_nodes}
    for item in contract.get("package_matches", []):
        if not isinstance(item, dict):
            errors.append("package_matches存在非对象项")
            continue
        package_id = item.get("package_id")
        source_ids = item.get("source_node_ids", [])
        if (
            not isinstance(source_ids, list)
            or not source_ids
            or not all(isinstance(node_id, str) and node_id for node_id in source_ids)
            or len(source_ids) != len(set(source_ids))
        ):
            errors.append(f"package_matches.source_node_ids无效: {package_id}")
            continue
        dimensions = item.get("instance_dimensions", {})
        if not isinstance(dimensions, dict) or any(not isinstance(value, (str, int, float, bool)) for value in dimensions.values()):
            errors.append(f"package_matches.instance_dimensions无效: {package_id}")
            continue
        key = (package_id, tuple(sorted(source_ids)), dimensions_key(dimensions))
        if key not in package_metrics or package_id == "core.general":
            errors.append(f"package_matches声明未命中指标包实例: {package_id} / {','.join(source_ids) if isinstance(source_ids, list) else source_ids}")
            continue
        if any(node_id not in nodes for node_id in source_ids):
            errors.append(f"package_matches引用未知source_node_ids: {package_id}")
            continue
        binding_scopes = {
            expected_bindings[(metric_id, key[1], key[2])].get("scope")
            for metric_id in package_metrics.get(key, set())
            if (metric_id, key[1], key[2]) in expected_bindings
        }
        if binding_scopes and (len(binding_scopes) != 1 or item.get("scope") not in binding_scopes):
            errors.append(f"package_matches作用域与scope_instance不一致: {package_id}")
        if any(str(value) not in item.get("scope", "") for value in dimensions.values()):
            errors.append(f"package_matches作用域未体现实例维度: {package_id}")
        source_mechanics = {nodes[node_id].get("mechanic_id") for node_id in source_ids}
        if item.get("mechanic_id") not in source_mechanics:
            errors.append(f"package_matches.mechanic_id不属于来源节点: {package_id}")
        if item.get("owner") != package_id or item.get("status") != "已匹配" or not non_empty(item.get("evidence")):
            errors.append(f"package_matches的Owner、状态或证据无效: {package_id}")
        metric_ids = item.get("metric_ids", [])
        if not isinstance(metric_ids, list):
            errors.append(f"package_matches.metric_ids不是数组: {package_id}")
            continue
        if key in declared:
            errors.append(f"package_matches重复声明指标包实例: {package_id} / {','.join(source_ids)}")
            continue
        declared[key] = set(metric_ids)
    for key, metric_ids in sorted(
        package_metrics.items(),
        key=lambda item: f"{item[0][0]}|{','.join(item[0][1])}|{json.dumps(dict(item[0][2]), ensure_ascii=False, sort_keys=True, default=str)}",
    ):
        package_id, source_ids, dimensions = key
        if package_id == "core.general":
            continue
        expected = set(metric_ids)
        actual = declared.get(key, set())
        if actual != expected:
            errors.append(f"package_matches指标集合不一致: {package_id} / {','.join(source_ids)} / {dict(dimensions)} / 缺失={','.join(sorted(expected - actual)) or '无'} / 额外={','.join(sorted(actual - expected)) or '无'}")
    extra = sorted(set(declared) - set(package_metrics))
    for package_id, source_ids, dimensions in extra:
        errors.append(f"package_matches包含额外指标包实例: {package_id} / {','.join(source_ids)} / {dict(dimensions)}")
    return errors


def json_pointer_value(data, pointer):
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise ValueError("JSON Pointer必须以/开头")
    current = data
    for token in pointer[1:].split("/"):
        if re.search(r"~(?![01])", token):
            raise ValueError("JSON Pointer包含非法转义")
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list):
            if not re.fullmatch(r"0|[1-9][0-9]*", token):
                raise ValueError(f"JSON Pointer数组索引无效: {token}")
            current = current[int(token)]
        elif isinstance(current, dict):
            current = current[token]
        else:
            raise KeyError(token)
    return current


def evidence_records(item, evidence_root, input_manifest):
    evidence = item.get("inapplicability_evidence")
    if not isinstance(evidence, list) or not evidence or not all(isinstance(record, dict) for record in evidence):
        return [], [f"不适用证据必须为非空对象数组: {item.get('metric_id')}"]
    errors = []
    if evidence_root is None:
        return evidence, [f"不适用证据缺少可信task_root: {item.get('metric_id')}"]
    manifest_hashes = input_manifest.get("hashes", {}) if isinstance(input_manifest.get("hashes"), dict) else {}
    for record in evidence:
        if not non_empty(record.get("evidence_path")) or not is_sha256(record.get("evidence_sha256")):
            errors.append(f"不适用证据缺少路径或有效SHA-256: {item.get('metric_id')}")
            continue
        resolved = safe_evidence_path(evidence_root, record["evidence_path"])
        if resolved is None or not resolved.is_file() or sha(resolved) != record["evidence_sha256"]:
            errors.append(f"不适用证据文件不存在或hash失效: {item.get('metric_id')} / {record['evidence_path']}")
            continue
        if manifest_hashes.get(record["evidence_path"]) != record["evidence_sha256"]:
            errors.append(f"不适用证据未写入input_manifest.hashes: {item.get('metric_id')} / {record['evidence_path']}")
        try:
            data = load(resolved)
            actual = json_pointer_value(data, record.get("json_pointer"))
            if actual != record.get("expected_value"):
                errors.append(f"不适用证据JSON Pointer值不一致: {item.get('metric_id')} / {record.get('json_pointer')}")
            record["_claim"] = actual
        except (OSError, ValueError, KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            errors.append(f"不适用证据不是可核验JSON: {item.get('metric_id')} / {exc}")
    return evidence, errors


def validate_target_evidence(item, catalog_metric, expected_binding, evidence_root, input_manifest):
    if item.get("status") == INACTIVE_METRIC_STATUS:
        return []
    metric_id = item.get("metric_id")
    if evidence_root is None:
        return [f"活动指标target_evidence缺少可信task_root: {metric_id}"]
    record = item.get("target_evidence")
    if not isinstance(record, dict):
        return [f"活动指标缺少target_evidence: {metric_id}"]
    path = record.get("evidence_path")
    expected_sha = record.get("evidence_sha256")
    pointer = record.get("json_pointer")
    binding_pointer = record.get("binding_json_pointer")
    if (
        not non_empty(path)
        or not is_sha256(expected_sha)
        or not isinstance(pointer, str)
        or not pointer.startswith("/")
        or not isinstance(binding_pointer, str)
        or not binding_pointer.startswith("/")
    ):
        return [f"target_evidence路径、SHA-256或目标/绑定JSON Pointer无效: {metric_id}"]
    resolved = safe_evidence_path(evidence_root, path)
    if resolved is None or not resolved.is_file():
        return [f"target_evidence文件不存在: {metric_id} / {path}"]
    errors = []
    if sha(resolved) != expected_sha:
        errors.append(f"target_evidence文件hash失效: {metric_id}")
    manifest_hashes = input_manifest.get("hashes", {}) if isinstance(input_manifest.get("hashes"), dict) else {}
    if manifest_hashes.get(path) != expected_sha:
        errors.append(f"target_evidence未写入input_manifest.hashes: {metric_id} / {path}")
    if not isinstance(expected_binding, dict) or expected_binding.get("virtual_na") is True:
        errors.append(f"活动指标缺少真实父scope_instance绑定: {metric_id}")
        return errors
    try:
        evidence_data = load(resolved)
        actual = json_pointer_value(evidence_data, pointer)
        if actual != item.get("target"):
            errors.append(f"target_evidence指针值与目标不一致: {metric_id}")
        actual_binding = json_pointer_value(evidence_data, binding_pointer)
        expected_claim = {
            "metric_instance": {
                "metric_id": metric_id,
                "source_node_ids": sorted(item.get("source_node_ids", [])),
                "instance_dimensions": item.get("instance_dimensions", {}),
            },
            "measurement_contract_sha256": measurement_contract_sha256(catalog_metric),
            "parent_event_set": {
                "scope_instance_id": expected_binding.get("scope_instance_id"),
                "semantic_event_set_id": expected_binding.get("semantic_event_set_id"),
                "event_set_path": expected_binding.get("event_set_path"),
                "event_set_sha256": expected_binding.get("event_set_sha256"),
                "event_count": expected_binding.get("event_count"),
            },
        }
        if actual_binding != expected_claim:
            errors.append(f"target_evidence未绑定当前指标实例、目录测量口径与父事件集: {metric_id}")
    except (OSError, ValueError, KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        errors.append(f"target_evidence无法核验: {metric_id} / {exc}")
    return errors


def evaluation_profile(item):
    if item.get("kind") == "hard":
        return item.get("hard_gate_profile")
    if item.get("kind") == "score":
        return item.get("score_profile")
    return item.get("audit_profile")


def target_groups(item):
    target = item.get("target")
    profile = evaluation_profile(item)
    separator = profile.get("group_separator", "::") if isinstance(profile, dict) else "::"
    if not isinstance(target, dict) or not non_empty(separator):
        return {}
    groups = {}
    for key in target:
        if not isinstance(key, str) or separator not in key:
            return {}
        group, label = key.split(separator, 1)
        groups.setdefault(group, set()).add(label)
    return groups


def target_group_labels_in_order(item):
    target = item.get("target")
    profile = evaluation_profile(item)
    separator = profile.get("group_separator", "::") if isinstance(profile, dict) else "::"
    result = {}
    if not isinstance(target, dict) or not non_empty(separator):
        return result
    for key in target:
        if not isinstance(key, str) or separator not in key:
            return {}
        group, label = key.split(separator, 1)
        result.setdefault(group, []).append(label)
    return result


def distribution_positions(item, group=None):
    target = item.get("target")
    profile = evaluation_profile(item)
    if not isinstance(profile, dict):
        return None
    if group is None:
        values = probability_values(target)
        positions = profile.get("bin_positions")
        if not isinstance(positions, list) or len(positions) != len(values):
            return None
        return {position: probability for position, probability in zip(positions, values)}
    labels = target_group_labels_in_order(item).get(group)
    positions_by_group = profile.get("bin_positions_by_group")
    if not isinstance(labels, list) or not isinstance(positions_by_group, dict):
        return None
    positions = positions_by_group.get(group)
    separator = profile.get("group_separator", "::")
    if not isinstance(positions, dict) or set(positions) != set(labels):
        return None
    return {
        positions[label]: target[f"{group}{separator}{label}"]
        for label in labels
    }


def close_probability(left, right, tolerance=1e-8):
    return finite_number(left) and finite_number(right) and abs(left - right) <= tolerance


def finite_number(value):
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    return isinstance(value, float) and math.isfinite(value)


def probability_values(value):
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return list(value.values())
    return []


def validate_probability_distribution(value, label, tolerance=1e-6):
    values = probability_values(value)
    if not values or any(not finite_number(item) or item < 0 for item in values):
        return [f"{label}必须为非空有限非负概率分布"]
    if abs(sum(values) - 1.0) > tolerance:
        return [f"{label}概率和必须为1"]
    return []


def validate_metric_target(item):
    if item.get("status") == INACTIVE_METRIC_STATUS and item.get("inapplicability_reason_code") != "degenerate_reachable_support":
        return []
    target = item.get("target")
    kind = item.get("kind")
    score_profile = item.get("score_profile")
    hard_gate_profile = item.get("hard_gate_profile")
    audit_profile = item.get("audit_profile")
    if kind == "score" and not isinstance(score_profile, dict):
        return [f"指标目标{item.get('metric_id')}缺少有效score_profile"]
    if kind == "hard" and not isinstance(hard_gate_profile, dict):
        return [f"指标目标{item.get('metric_id')}缺少有效hard_gate_profile"]
    if kind == "audit" and not isinstance(audit_profile, dict):
        return [f"指标目标{item.get('metric_id')}缺少有效audit_profile"]
    profile = evaluation_profile(item)
    method = profile.get("method") if kind in {"hard", "score"} else None
    label = f"指标目标{item.get('metric_id')}"
    if method in {"absolute_error", "relative_error"}:
        return [] if finite_number(target) else [f"{label}必须为有限数值"]
    if method == "range_error":
        valid = isinstance(target, dict) and finite_number(target.get("min")) and finite_number(target.get("max")) and target["min"] <= target["max"]
        return [] if valid else [f"{label}必须为min<=max的有限区间"]
    if method in {"total_variation", "wasserstein_1d"}:
        errors = validate_probability_distribution(target, label)
        if method == "wasserstein_1d" and not errors:
            positions = profile.get("bin_positions")
            if not isinstance(positions, list) or len(positions) != len(probability_values(target)) or any(not finite_number(value) for value in positions):
                errors.append(f"{label}与bin_positions数量或类型不一致")
            elif len(set(positions)) != len(positions) or any(right <= left for left, right in zip(positions, positions[1:])):
                errors.append(f"{label}的bin_positions必须唯一且严格递增")
            elif profile.get("position_transform") == "log10_1p" and any(value < 0 for value in positions):
                errors.append(f"{label}的log10_1p原始位置必须全部非负")
        return errors
    if method in {"grouped_total_variation", "grouped_wasserstein_1d"}:
        groups = target_groups(item)
        if not groups:
            return [f"{label}必须使用group::item键"]
        separator = profile.get("group_separator", "::")
        errors = []
        for group in groups:
            values = {
                key: value for key, value in target.items()
                if isinstance(key, str) and key.startswith(group + separator)
            }
            errors += validate_probability_distribution(values, f"{label}组{group}")
        weights = profile.get("group_weights")
        if not isinstance(weights, dict) or set(weights) != set(groups) or any(not finite_number(value) or value <= 0 for value in weights.values()) or abs(sum(weights.values()) - 1.0) > 1e-6:
            errors.append(f"{label}的group_weights必须覆盖全部组并归一化")
        if method == "grouped_wasserstein_1d":
            positions = profile.get("bin_positions_by_group")
            if not isinstance(positions, dict) or set(positions) != set(groups):
                errors.append(f"{label}缺少完整bin_positions_by_group")
            else:
                labels_by_group = target_group_labels_in_order(item)
                for group, labels in labels_by_group.items():
                    group_positions = positions.get(group)
                    if not isinstance(group_positions, dict) or set(group_positions) != set(labels):
                        errors.append(f"{label}组{group}的目标标签与位置键必须完全一致")
                        continue
                    values = [group_positions[item_label] for item_label in labels]
                    if any(not finite_number(value) for value in values):
                        errors.append(f"{label}组{group}的位置必须为有限数值")
                    elif len(set(values)) != len(values) or any(right <= left for left, right in zip(values, values[1:])):
                        errors.append(f"{label}组{group}的位置必须唯一且按目标标签严格递增")
                    elif profile.get("position_transform") == "log10_1p" and any(value < 0 for value in values):
                        errors.append(f"{label}组{group}的log10_1p原始位置必须全部非负")
        return errors
    if method == "grouped_mean_absolute_error":
        groups = target_groups(item)
        if not groups or any(not non_empty(group) or any(not non_empty(field) for field in fields) for group, fields in groups.items()):
            return [f"{label}必须使用非空group::field键"]
        values = probability_values(target)
        errors = [] if values and all(finite_number(value) for value in values) else [f"{label}必须为非空有限数值对象"]
        weights = profile.get("group_weights")
        tolerance = profile.get("normalization_tolerance")
        tolerance_valid = finite_number(tolerance) and 0 <= tolerance < 1
        if profile.get("group_weight_source") != "task_contract":
            errors.append(f"{label}的组权重必须来自task_contract")
        if not tolerance_valid:
            errors.append(f"{label}的normalization_tolerance必须在[0,1)内")
        weights_valid = (
            isinstance(weights, dict)
            and set(weights) == set(groups)
            and all(finite_number(value) and value > 0 for value in weights.values())
        )
        if not weights_valid:
            errors.append(f"{label}的group_weights必须以有限正数覆盖全部组")
        elif tolerance_valid and abs(sum(weights.values()) - 1.0) > tolerance:
            errors.append(f"{label}的group_weights未归一化")
        return errors
    if method in {"mean_absolute_error", "max_absolute_error"}:
        values = probability_values(target)
        return [] if values and all(finite_number(value) for value in values) else [f"{label}必须为非空有限数值向量"]
    if kind in {"hard", "score"}:
        return [f"{label}使用不支持的评价方法: {method}"]
    exact_fields = audit_profile.get("exact_match_fields", [])
    if exact_fields and (not isinstance(target, dict) or not set(exact_fields).issubset(target)):
        return [f"{label}缺少阻塞审计精确字段"]
    if audit_profile.get("method") == "field_consistency_gate" and isinstance(target, dict):
        display_labels = item.get("display", {}).get("object_labels", {}) if isinstance(item.get("display"), dict) else {}
        declared_status_fields = {
            field for field in display_labels
            if isinstance(field, str) and field.endswith("_status")
        }
        target_status_fields = {
            field for field in target
            if isinstance(field, str) and field.endswith("_status")
        }
        required_status_fields = declared_status_fields or target_status_fields
        missing_status_fields = sorted(required_status_fields - set(target))
        if missing_status_fields:
            return [f"{label}缺少规则核对状态字段: {','.join(missing_status_fields)}"]
        invalid = [
            field for field, value in target.items()
            if field.endswith("_status") and value not in AUDIT_TARGET_STATUSES
        ]
        if invalid:
            return [f"{label}包含无效审计状态字段: {','.join(sorted(invalid))}"]
        required_status = audit_profile.get("required_result_status")
        if audit_profile.get("blocking_on_mismatch") is True:
            if not non_empty(required_status) or not required_status_fields:
                return [f"{label}阻塞型一致性审计缺少required_result_status或状态字段"]
            mismatched = sorted(field for field in required_status_fields if target.get(field) != required_status)
            if mismatched:
                return [f"{label}阻塞型审计结果不符合: {','.join(mismatched)}"]
    return [] if non_empty(target) else [f"{label}不能为空"]


def source_nodes(item, active_node_map):
    source_ids = item.get("source_node_ids", [])
    if not isinstance(source_ids, list) or not all(isinstance(node_id, str) for node_id in source_ids):
        return []
    return [active_node_map[node_id] for node_id in source_ids if node_id in active_node_map]


def validate_dynamic_ordered_axis(item, active_node_map):
    metric_id = item.get("metric_id")
    if metric_id not in DYNAMIC_ORDERED_METRICS or item.get("status") == INACTIVE_METRIC_STATUS:
        return []
    profile = item.get("score_profile")
    if not isinstance(profile, dict):
        return [f"动态有序指标缺少score_profile: {metric_id}"]
    nodes = source_nodes(item, active_node_map)
    dimensions = item.get("instance_dimensions") if isinstance(item.get("instance_dimensions"), dict) else {}
    expected = None
    errors = []
    if metric_id == "cascade.effective_capacity_distribution_by_depth":
        cascade_nodes = [node for node in nodes if node.get("mechanic_id") == "evolution.cascade"]
        if len(cascade_nodes) != 1:
            return ["Cascade容量指标必须唯一绑定evolution.cascade画像节点"]
        expected = cascade_nodes[0].get("attributes", {}).get("effective_capacity_axis_semantics")
    elif metric_id == "collect.output_value_given_input_count_distribution":
        collect_nodes = [node for node in nodes if node.get("mechanic_id") == "modifier.collect"]
        if len(collect_nodes) != 1:
            return ["Collect输出价值指标必须唯一绑定modifier.collect画像节点"]
        mapping_errors, mapping, _ = validate_collect_output_maps(collect_nodes[0].get("attributes", {}))
        errors += mapping_errors
        semantic, unit = dimensions.get("output_semantic"), dimensions.get("output_unit")
        expected = mapping.get((semantic, unit))
        if expected is None:
            errors.append(f"Collect输出指标作用域未命中画像轴语义: {semantic} / {unit}")
    elif metric_id == "settlement.scale_given_symbol_distribution":
        settlement_nodes = [node for node in nodes if node.get("mechanic_id") in SETTLEMENT_SCALE_AXIS]
        if len(settlement_nodes) != 1:
            return ["中奖规模指标必须唯一绑定一种标准结算画像节点"]
        node = settlement_nodes[0]
        expected = node.get("attributes", {}).get("winning_scale_axis_semantics")
        if expected != SETTLEMENT_SCALE_AXIS[node.get("mechanic_id")]:
            errors.append("中奖规模指标绑定了无效画像轴语义")
    else:
        state_nodes = [node for node in nodes if node.get("mechanic_id") == "state.persistent-state"]
        if len(state_nodes) != 1:
            return [f"持久状态有序指标必须唯一绑定state.persistent-state画像节点: {metric_id}"]
        expected = state_nodes[0].get("attributes", {}).get("ordered_axis_semantics")
    if expected not in ORDERED_AXIS_SEMANTICS:
        errors.append(f"动态有序指标无法从画像解析轴语义: {metric_id}")
    elif profile.get("axis_semantics") != expected:
        errors.append(f"动态有序指标轴语义与画像不一致: {metric_id} / 期望{expected}")
    return errors


def validate_collect_category_contract(item, active_node_map):
    metric_id = item.get("metric_id")
    if metric_id != "collect.output_category_given_input_count_distribution" or item.get("status") == INACTIVE_METRIC_STATUS:
        return []
    nodes = source_nodes(item, active_node_map)
    collect_nodes = [node for node in nodes if node.get("mechanic_id") == "modifier.collect"]
    if len(collect_nodes) != 1:
        return ["Collect输出类别指标必须唯一绑定modifier.collect画像节点"]
    errors, ordered, categorical = validate_collect_output_maps(collect_nodes[0].get("attributes", {}))
    dimensions = item.get("instance_dimensions") if isinstance(item.get("instance_dimensions"), dict) else {}
    key = (dimensions.get("output_semantic"), dimensions.get("output_unit"))
    categories = categorical.get(key)
    if categories is None:
        errors.append(f"Collect输出类别指标作用域未命中画像类别域: {key[0]} / {key[1]}")
        return errors
    if key in ordered:
        errors.append(f"Collect输出类别指标误用了有序输出作用域: {key[0]} / {key[1]}")
    groups = target_groups(item)
    if not groups:
        errors.append("Collect输出类别目标必须使用input_count::output_category真实标签")
    else:
        expected = set(categories)
        for group, labels in groups.items():
            if set(labels) != expected:
                errors.append(f"Collect输出类别目标未完整使用画像类别域: {group}")
    return errors


def validate_multiplier_return_contract(item, active_node_map):
    if item.get("metric_id") != "multiplier.return_dependence_residual" or item.get("status") == INACTIVE_METRIC_STATUS:
        return []
    nodes = source_nodes(item, active_node_map)
    multiplier_nodes = [node for node in nodes if node.get("mechanic_id") == "modifier.win-multiplier"]
    if len(multiplier_nodes) != 1:
        return ["倍率回报依赖残差必须唯一绑定modifier.win-multiplier画像节点"]
    evidence = multiplier_nodes[0].get("attributes", {}).get("return_dependency_evidence")
    if not isinstance(evidence, dict) or evidence.get("residual_dependence_after_control") is not True:
        return ["倍率回报依赖残差缺少控制后仍有剩余依赖的结构化证据"]
    groups = target_group_labels_in_order(item)
    if not groups:
        return ["倍率回报依赖残差必须使用control_stratum|pre_return_bucket::multiplier_state字段"]
    errors, state_domain, strata_groups = [], None, {}
    separator = item.get("score_profile", {}).get("group_separator", "::")
    for group, labels in groups.items():
        if "|" not in group:
            errors.append(f"倍率回报依赖残差组缺少控制层或倍率前回报档: {group}")
            continue
        control_stratum, return_bucket = group.rsplit("|", 1)
        if not non_empty(control_stratum) or not non_empty(return_bucket):
            errors.append(f"倍率回报依赖残差组标签无效: {group}")
        strata_groups.setdefault(control_stratum, set()).add(return_bucket)
        if state_domain is None:
            state_domain = set(labels)
        elif set(labels) != state_domain:
            errors.append(f"倍率回报依赖残差各组倍率状态域不一致: {group}")
        values = [item.get("target", {}).get(f"{group}{separator}{label}") for label in labels]
        if all(finite_number(value) for value in values) and abs(sum(values)) > 1e-6:
            errors.append(f"倍率回报依赖残差组内概率差之和必须为0: {group}")
    for control_stratum, return_buckets in strata_groups.items():
        if len(return_buckets) < 2:
            errors.append(f"同一控制层只有一个倍率前回报档时不得评分依赖残差: {control_stratum}")
    return errors


def validate_transform_target_coherence_contract(item, active_node_map):
    if (
        item.get("metric_id") != "transform.target_coherence_residual_given_count"
        or item.get("status") == INACTIVE_METRIC_STATUS
    ):
        return []
    transform_nodes = [
        node for node in source_nodes(item, active_node_map)
        if node.get("mechanic_id") == "modifier.symbol-transform"
    ]
    if len(transform_nodes) != 1:
        return ["目标一致性残差必须唯一绑定modifier.symbol-transform画像节点"]
    source_domain = transform_nodes[0].get("attributes", {}).get("source_domain")
    if (
        not isinstance(source_domain, list)
        or not source_domain
        or len(source_domain) != len(set(source_domain))
        or any(not non_empty(source) for source in source_domain)
    ):
        return ["目标一致性残差的source_domain必须为非空、无重复的真实来源ID数组"]
    reserved = ("|", "+", "::")
    if any(any(token in source for token in reserved) for source in source_domain):
        return ["目标一致性残差的source_domain来源ID不得包含保留分隔符|、+或::"]
    source_order = {str(source): index for index, source in enumerate(source_domain)}
    groups = target_group_labels_in_order(item)
    if not groups:
        return ["目标一致性残差必须使用changed_count|source_a+source_b::same_target_residual字段"]
    errors = []
    for group, fields in groups.items():
        if fields != ["same_target_residual"]:
            errors.append(f"目标一致性残差每组必须且只能包含same_target_residual字段: {group}")
        if not isinstance(group, str) or "|" not in group:
            errors.append(f"目标一致性残差组缺少变换格数或无序来源对: {group}")
            continue
        count_label, pair_label = group.split("|", 1)
        count = integer_token(count_label)
        pair = pair_label.split("+") if isinstance(pair_label, str) else []
        if count is None or count < 2:
            errors.append(f"目标一致性残差只允许实际变换格数至少为2的组: {group}")
        if len(pair) != 2 or any(source not in source_order for source in pair):
            errors.append(f"目标一致性残差来源对必须由source_domain中的两个真实来源组成: {group}")
        elif source_order[pair[0]] > source_order[pair[1]]:
            errors.append(f"目标一致性残差无序来源对必须按source_domain顺序规范化: {group}")
        value = item.get("target", {}).get(f"{group}::same_target_residual")
        if not finite_number(value) or value < -1 or value > 1:
            errors.append(f"目标一致性残差必须落在[-1,1]: {group}")
    return errors


def metric_instances_overlap(left, right, active_node_map):
    left_dimensions = left.get("instance_dimensions") if isinstance(left.get("instance_dimensions"), dict) else {}
    right_dimensions = right.get("instance_dimensions") if isinstance(right.get("instance_dimensions"), dict) else {}
    if any(left_dimensions[name] != right_dimensions[name] for name in set(left_dimensions) & set(right_dimensions)):
        return False
    left_nodes = source_nodes(left, active_node_map)
    right_nodes = source_nodes(right, active_node_map)
    left_node_ids = {node.get("node_id") for node in left_nodes}
    right_node_ids = {node.get("node_id") for node in right_nodes}
    if left_node_ids & right_node_ids:
        return True
    left_events = {
        event_id for node in left_nodes for event_id in node.get("semantic_event_set_ids", [])
        if isinstance(event_id, str) and event_id
    }
    right_events = {
        event_id for node in right_nodes for event_id in node.get("semantic_event_set_ids", [])
        if isinstance(event_id, str) and event_id
    }
    if left_events & right_events:
        return True
    for field in ("sealed_event_set_id", "sealed_event_set_path", "sealed_event_set_sha256"):
        if non_empty(left.get(field)) and left.get(field) == right.get(field):
            return True
    return non_empty(left.get("scope")) and left.get("scope") == right.get("scope")


def entry_source_tokens(node):
    values = node.get("attributes", {}).get("entry_sources", [])
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        return set()
    return {str(value).strip().lower() for value in values}


def entry_source_semantics(node):
    value = node.get("attributes", {}).get("entry_source_semantics", {})
    return value if isinstance(value, dict) else {}


def endogenous_entry_sources(node):
    return {
        source_id
        for source_id, definition in entry_source_semantics(node).items()
        if isinstance(definition, dict) and definition.get("origin") == "endogenous"
    }


def alignment_entry_sources(node):
    return {
        source_id
        for source_id, definition in entry_source_semantics(node).items()
        if isinstance(definition, dict)
        and (
            definition.get("origin") == "endogenous"
            or definition.get("source_kind") == "feature_buy"
        )
    }


def award_return_equivalence_proof(node, entry_source):
    value = node.get("attributes", {}).get("outcome_return_equivalence", {})
    if not isinstance(value, dict):
        return None
    proof = value.get(entry_source)
    return proof if isinstance(proof, dict) else None


def award_return_is_deterministic_chain(node, entry_source):
    return award_return_equivalence_proof(node, entry_source) == AWARD_CHAIN_PROOF


def has_feature_buy(nodes):
    return any("feature_buy" in entry_source_tokens(node) for node in nodes)


def has_natural_feature(nodes):
    return any(node.get("mechanic_id") in FEATURE_MECHANIC_IDS and endogenous_entry_sources(node) for node in nodes)


def referenced_source_instances(records):
    refs, errors = [], []
    for record in records:
        claim = record.get("_claim", {})
        values = claim.get("source_metric_instances") if isinstance(claim, dict) else None
        if not isinstance(values, list) or not values:
            errors.append("派生或互斥证据缺少source_metric_instances")
            continue
        for value in values:
            if not isinstance(value, dict):
                errors.append("source_metric_instances存在非对象项")
                continue
            refs.append(metric_instance_key(value))
    return sorted(set(refs), key=instance_sort_key), errors


def validate_inapplicability(item, active_nodes, active_items_by_key, catalog, evidence_root, input_manifest):
    metric_id = item.get("metric_id")
    reason = item.get("inapplicability_reason_code")
    records, errors = evidence_records(item, evidence_root, input_manifest)
    if reason not in INAPPLICABILITY_REASON_CODES:
        errors.append(f"不适用原因码不受支持: {metric_id} / {reason}")
        return errors
    if reason not in catalog["metrics"].get(metric_id, {}).get("inapplicability_reason_codes", []):
        errors.append(f"指标目录未允许该不适用原因: {metric_id} / {reason}")
        return errors
    if metric_id in CORE_ALWAYS_ACTIVE:
        errors.append(f"Core通用指标不得标记不适用: {metric_id}")
        return errors
    node_map = {node["node_id"]: node for node in active_nodes}
    metric_nodes = source_nodes(item, node_map)
    if reason == "degenerate_reachable_support":
        profile = item.get("score_profile") if isinstance(item.get("score_profile"), dict) else {}
        if item.get("kind") != "score" or profile.get("reachable_support_status") != "all_degenerate" or profile.get("reachable_support_source") != "task_contract":
            errors.append(f"退化支持不适用缺少all_degenerate评分合同: {metric_id}")
        valid_support = False
        for record in records:
            claim = record.get("_claim", {})
            support = claim.get("reachable_support") if isinstance(claim, dict) else None
            grouped = claim.get("reachable_support_by_group") if isinstance(claim, dict) else None
            if isinstance(support, list) and len(support) == 1:
                valid_support = True
            if isinstance(grouped, dict) and grouped and all(isinstance(values, list) and len(values) == 1 for values in grouped.values()):
                expected_groups = set(target_groups(item))
                valid_support = not expected_groups or set(grouped) == expected_groups
        if not valid_support:
            errors.append(f"退化支持证据必须密封唯一可达值或每组唯一可达值: {metric_id}")
    elif reason == "feature_buy_unavailable":
        if metric_id != "feature_cycle.base_bet_equivalent_return_distribution" or has_feature_buy(metric_nodes):
            errors.append(f"Feature Buy不存在原因与画像不一致: {metric_id}")
        actual_sources = sorted(set().union(*(entry_source_tokens(node) for node in metric_nodes))) if metric_nodes else []
        if not any(record.get("_claim") == {"entry_sources": actual_sources} for record in records):
            errors.append(f"Feature Buy不存在证据未精确绑定画像入口来源: {metric_id}")
    elif reason == "deterministic_rule_result":
        if metric_id == "multiplier.application_rate_given_occurrence":
            valid = metric_nodes and all(
                node.get("mechanic_id") == "modifier.win-multiplier"
                and node.get("attributes", {}).get("application_may_be_skipped") is False
                for node in metric_nodes
            )
            expected_claim = {"application_may_be_skipped": False}
            if not valid or not any(record.get("_claim") == expected_claim for record in records):
                errors.append(f"确定性规则结果证据内容无效: {metric_id}")
        elif metric_id == "respin.rerolled_position_count_distribution_given_retained_count":
            respin_nodes = [node for node in metric_nodes if node.get("mechanic_id") == "feature.respin"]
            valid_claim = any(
                isinstance(record.get("_claim"), dict)
                and record["_claim"].get("rerolled_set_rule") == "position_domain_minus_retained_set"
                and record["_claim"].get("rerolled_count_rule") == "position_domain_size_minus_retained_count"
                and record["_claim"].get("all_eligible_steps_deterministic") is True
                and len(respin_nodes) == 1
                and record["_claim"].get("position_domain") == respin_nodes[0].get("attributes", {}).get("position_domain")
                for record in records
            )
            valid_profile = len(respin_nodes) == 1 and respin_nodes[0].get("attributes", {}).get("rerolled_position_binding") == "position_domain_minus_retained_set"
            if not valid_profile or not valid_claim:
                errors.append(f"Respin重转数量确定规则未绑定同一position_domain、补集关系和逐步确定性: {metric_id}")
        elif metric_id == "jackpot.award_value_distribution_by_tier":
            jackpot_nodes = [node for node in metric_nodes if node.get("mechanic_id") == "award.jackpot"]
            valid_claim = any(
                isinstance(record.get("_claim"), dict)
                and record["_claim"].get("deterministic_per_tier") is True
                and any(record["_claim"].get("value_model") == node.get("attributes", {}).get("value_model") for node in jackpot_nodes)
                for record in records
            )
            if not jackpot_nodes or not valid_claim:
                errors.append(f"固定Jackpot奖值证据未精确绑定value_model: {metric_id}")
        elif metric_id == "hold_spin.capacity_transition_distribution":
            hold_nodes = [node for node in metric_nodes if node.get("mechanic_id") == "feature.hold-and-spin"]
            transition = hold_nodes[0].get("attributes", {}).get("capacity_transition_contract") if len(hold_nodes) == 1 else None
            transition_map = transition.get("current_capacity_occupancy_to_next_capacity_domain") if isinstance(transition, dict) else None
            if (
                not isinstance(transition_map, dict) or not transition_map
                or any(not isinstance(values, list) or len(values) != 1 for values in transition_map.values())
            ):
                errors.append("Hold & Spin容量转移只有全部可达C|O组都唯一确定C'时才可按确定规则不计分")
            else:
                groups = target_groups(item)
                if set(groups) != set(transition_map):
                    errors.append("Hold & Spin确定容量转移目标组必须完整覆盖capacity_transition_contract")
                for group, values in transition_map.items():
                    distribution = distribution_positions(item, group)
                    expected_capacity = float(values[0])
                    if not isinstance(distribution, dict) or set(distribution) != {expected_capacity} or not close_probability(distribution[expected_capacity], 1.0):
                        errors.append(f"Hold & Spin确定容量转移目标未由规则精确推出: {group}")
                expected_hash = canonical_sha256(transition)
                if not any(
                    isinstance(record.get("_claim"), dict)
                    and record["_claim"].get("capacity_transition_contract_sha256") == expected_hash
                    for record in records
                ):
                    errors.append("Hold & Spin确定容量转移证据未绑定capacity_transition_contract哈希")
        else:
            errors.append(f"确定性规则结果原因与指标语义不一致: {metric_id}")
    elif reason in {"deterministically_derived_from_primary", "semantic_owner_exclusive"}:
        source_keys, source_errors = referenced_source_instances(records)
        errors += source_errors
        for record in records:
            claim = record.get("_claim", {})
            if not isinstance(claim, dict) or not non_empty(claim.get("derivation_rule")):
                errors.append(f"派生或互斥证据缺少确定性规则: {metric_id}")
        source_items = [active_items_by_key[key] for key in source_keys if key in active_items_by_key]
        if not source_keys or len(source_items) != len(source_keys):
            errors.append(f"派生或互斥证据未绑定活动来源指标: {metric_id}")
        incompatible = [
            format_instance(metric_instance_key(source))
            for source in source_items
            if not metric_instances_overlap(item, source, node_map)
        ]
        if incompatible:
            errors.append(f"派生或互斥证据引用了不同节点、维度或事件集实例: {metric_id} / {','.join(incompatible)}")
        source_evidence = {
            format_instance(metric_instance_key(source)): (
                source.get("target_evidence", {}).get("evidence_sha256")
                if isinstance(source.get("target_evidence"), dict)
                else None
            )
            for source in source_items
        }
        if source_items and not any(
            isinstance(record.get("_claim"), dict)
            and record["_claim"].get("source_target_evidence_sha256") == source_evidence
            for record in records
        ):
            errors.append(f"派生或互斥证据未绑定来源目标证据hash: {metric_id}")
        source_metric_ids = {key[0] for key in source_keys}
        if reason == "deterministically_derived_from_primary":
            relationships = catalog["metrics"].get(metric_id, {}).get("relationships", {})
            allowed = set(relationships.get("derived_from", []))
            allowed.update(relationships.get("conditional_derivation_sources", []))
            if not source_metric_ids or not source_metric_ids.issubset(allowed):
                errors.append(f"确定性派生来源不在登记关系内: {metric_id}")
            errors += validate_declared_derivation_projection(item, source_items, records)
            errors += validate_respin_persistent_derivation(item, source_items, active_nodes)
            errors += validate_value_symbol_multiplier_derivation(item, source_items, active_nodes)
            errors += validate_cascade_multiplier_derivation(item, source_items, active_nodes)
        else:
            exclusive = set(catalog["metrics"].get(metric_id, {}).get("relationships", {}).get("exclusive_with", []))
            exclusive.update(
                next(iter(pair - {metric_id}))
                for pair in EXCLUSIVE_METRIC_PAIRS
                if metric_id in pair
            )
            if not source_metric_ids.issubset(exclusive):
                errors.append(f"互斥Owner来源不在登记关系内: {metric_id}")
    return errors


def resolve_derived_facts(items, active_nodes, active_items_by_key, catalog, evidence_root, input_manifest):
    facts = dict(active_items_by_key)
    pending = {
        metric_instance_key(item): item
        for item in items
        if isinstance(item, dict)
        and item.get("status") == INACTIVE_METRIC_STATUS
        and item.get("inapplicability_reason_code") == "deterministically_derived_from_primary"
    }
    results = {}
    while pending:
        progressed = False
        for key, item in list(pending.items()):
            source_keys = declared_source_keys(item)
            if source_keys and any(source_key not in facts for source_key in source_keys):
                continue
            item_errors = validate_inapplicability(item, active_nodes, facts, catalog, evidence_root, input_manifest)
            results[key] = item_errors
            if not item_errors:
                facts[key] = item
            pending.pop(key)
            progressed = True
        if not progressed:
            break
    for key, item in pending.items():
        results[key] = validate_inapplicability(item, active_nodes, facts, catalog, evidence_root, input_manifest)
    return facts, results


def validate_feature_resource_ownership(item, active_nodes, active_items_by_key):
    metric_id = item.get("metric_id")
    if metric_id not in FEATURE_RESOURCE_METRICS:
        return []
    node_map = {node.get("node_id"): node for node in active_nodes}
    feature_nodes = [
        node for node in source_nodes(item, node_map)
        if node.get("mechanic_id") in FEATURE_MECHANIC_IDS
    ]
    if len(feature_nodes) != 1:
        return [f"Feature资源指标必须唯一绑定一个Feature画像节点: {metric_id}"]
    dimensions = item.get("instance_dimensions") if isinstance(item.get("instance_dimensions"), dict) else {}
    bindings = feature_nodes[0].get("attributes", {}).get("resource_count_derivation_bindings", [])
    matches = [
        binding for binding in bindings
        if isinstance(binding, dict)
        and binding.get("derived_metric_id") == metric_id
        and binding.get("derived_instance_dimensions") == dimensions
    ] if isinstance(bindings, list) else []
    derived = item.get("status") == INACTIVE_METRIC_STATUS and item.get("inapplicability_reason_code") == "deterministically_derived_from_primary"
    errors = []
    if len(matches) > 1:
        return [f"Feature资源指标实例命中多个派生绑定: {format_instance(metric_instance_key(item))}"]
    if matches and not derived:
        errors.append(f"已声明完整Feature资源派生绑定的实例不得重复评分: {format_instance(metric_instance_key(item))}")
        return errors
    if derived and not matches:
        errors.append(f"Feature资源确定性派生缺少画像实例绑定: {format_instance(metric_instance_key(item))}")
        return errors
    if not matches:
        return errors
    binding = matches[0]
    source_ref = binding["primary_owner_metric_instance"]
    source_key = (
        source_ref["metric_id"],
        tuple(sorted(source_ref["source_node_ids"])),
        dimensions_key(source_ref["instance_dimensions"]),
    )
    source = active_items_by_key.get(source_key)
    if source is None:
        return errors + [f"Feature资源派生未绑定唯一活动数量Owner: {format_instance(source_key)}"]
    group = source_ref.get("target_group_id")
    source_distribution = distribution_positions(source, group) if group is not None else distribution_positions(source)
    derived_distribution = distribution_positions(item)
    if not isinstance(source_distribution, dict) or not isinstance(derived_distribution, dict):
        return errors + [f"Feature资源派生来源或目标缺少实际计数位置: {metric_id}"]
    mapping = {}
    try:
        mapping = parsed_numeric_mapping(
            binding["source_count_to_resource_count"],
            value_parser=float,
            key_parser=float,
            allow_none=True,
        )
    except (TypeError, ValueError):
        return errors + [f"Feature资源派生计数映射无法解析: {metric_id}"]
    if mapping is None:
        return errors + [f"Feature资源派生计数映射包含非数值、非有限值或数值键冲突: {metric_id}"]
    if set(mapping) != set(source_distribution):
        errors.append(f"Feature资源派生映射未完整覆盖来源目标支持集: {metric_id}")
        return errors
    projected = {}
    retained_probability = 0.0
    for source_count, probability in source_distribution.items():
        resource_count = mapping[source_count]
        if resource_count is None:
            continue
        retained_probability += probability
        projected[float(resource_count)] = projected.get(float(resource_count), 0.0) + probability
    if binding.get("relation") == "deterministic_success_subset":
        if retained_probability <= 0:
            errors.append(f"Feature资源成功子集映射没有任何可进入Feature的来源计数: {metric_id}")
            return errors
        projected = {value: probability / retained_probability for value, probability in projected.items()}
    elif not close_probability(retained_probability, 1.0):
        errors.append(f"Feature资源同事件推送映射必须覆盖全部来源概率质量: {metric_id}")
        return errors
    positive_outcomes = {value for value, probability in projected.items() if probability > 1e-12}
    if len(positive_outcomes) <= 1:
        errors.append(f"Feature资源固定单值必须使用degenerate_reachable_support而不是计数派生: {metric_id}")
    if set(projected) != set(derived_distribution) or any(
        not close_probability(projected[value], derived_distribution[value])
        for value in set(projected) & set(derived_distribution)
    ):
        errors.append(f"Feature资源派生目标未由来源计数目标与密封映射精确复算: {metric_id}")
    return errors


def validate_hold_spin_capacity_ownership(item, active_nodes, active_items_by_key, expected_binding=None):
    metric_id = item.get("metric_id")
    if metric_id != "hold_spin.actual_capacity_distribution_by_observation":
        return []
    node_map = {node.get("node_id"): node for node in active_nodes}
    hold_spin_nodes = [
        node for node in source_nodes(item, node_map)
        if node.get("mechanic_id") == "feature.hold-and-spin"
    ]
    if len(hold_spin_nodes) != 1:
        return ["Hold & Spin容量指标必须唯一绑定一个Hold & Spin玩法节点"]
    dimensions = item.get("instance_dimensions") if isinstance(item.get("instance_dimensions"), dict) else {}
    bindings = hold_spin_nodes[0].get("attributes", {}).get("capacity_owner_bindings", [])
    matches = [
        binding for binding in bindings
        if isinstance(binding, dict)
        and binding.get("derived_metric_id") == metric_id
        and binding.get("derived_instance_dimensions") == dimensions
    ] if isinstance(bindings, list) else []
    derived = item.get("status") == INACTIVE_METRIC_STATUS and item.get("inapplicability_reason_code") == "deterministically_derived_from_primary"
    errors = []
    if len(matches) > 1:
        return [f"Hold & Spin容量指标实例命中多个Owner绑定: {format_instance(metric_instance_key(item))}"]
    if matches and not derived:
        return [f"已声明容量Primary推送绑定的Hold & Spin容量实例不得重复评分: {format_instance(metric_instance_key(item))}"]
    if derived and not matches:
        return [f"Hold & Spin容量确定性派生缺少画像实例绑定: {format_instance(metric_instance_key(item))}"]
    if not matches:
        return errors
    binding = matches[0]
    source_ref = binding.get("primary_owner_metric_instance", {})
    source_key = (
        source_ref.get("metric_id"),
        tuple(sorted(source_ref.get("source_node_ids", []))),
        dimensions_key(source_ref.get("instance_dimensions", {})),
    )
    source = active_items_by_key.get(source_key)
    if source is None:
        return [f"Hold & Spin容量派生未绑定唯一活动Primary实例: {format_instance(source_key)}"]
    shared_event = binding.get("shared_semantic_event_set_id")
    if source.get("sealed_event_set_id") != shared_event:
        errors.append("Hold & Spin容量派生来源Primary未密封到画像共享观察事件集")
    if not isinstance(expected_binding, dict) or expected_binding.get("semantic_event_set_id") != shared_event:
        errors.append("Hold & Spin容量派生目标实例未绑定画像共享观察事件集")
    source_target = source.get("target")
    mapping = binding.get("source_value_to_actual_capacity")
    if target_groups(source):
        if source_ref.get("metric_id") != "effective_ways.capacity_distribution":
            return [f"Hold & Spin容量派生仅允许effective_ways容量Owner使用分组来源: {source_ref.get('metric_id')}"]
        source_distribution = weighted_source_distribution_fields(source)
    elif isinstance(source_target, dict):
        source_distribution = source_target
    elif isinstance(source_target, list):
        labels = source.get("display", {}).get("item_labels") if isinstance(source.get("display"), dict) else None
        source_distribution = dict(zip(labels, source_target)) if isinstance(labels, list) and len(labels) == len(source_target) else None
    else:
        source_distribution = None
    if not isinstance(source_distribution, dict) or not source_distribution:
        return [f"Hold & Spin容量派生来源缺少完整业务标签分布: {source_ref.get('metric_id')}"]
    if not isinstance(mapping, dict) or set(mapping) != set(source_distribution):
        return ["Hold & Spin容量派生映射未完整且仅覆盖来源目标支持集"]
    if any(not finite_number(probability) or probability < 0 for probability in source_distribution.values()) or not close_probability(sum(source_distribution.values()), 1.0):
        return ["Hold & Spin容量派生来源目标不是合法概率分布"]
    projected = {}
    for label, probability in source_distribution.items():
        capacity = mapping[label]
        projected[float(capacity)] = projected.get(float(capacity), 0.0) + probability
    target_distribution = distribution_positions(item)
    if not isinstance(target_distribution, dict):
        return ["Hold & Spin容量派生目标缺少实际容量bin_positions"]
    if set(projected) != set(target_distribution) or any(
        not close_probability(projected[value], target_distribution[value])
        for value in set(projected) & set(target_distribution)
    ):
        errors.append("Hold & Spin容量目标未由来源Primary和完整值映射精确复算")
    binding_hash = canonical_sha256(binding)
    claims = [
        record.get("_claim") for record in item.get("inapplicability_evidence", [])
        if isinstance(record, dict) and isinstance(record.get("_claim"), dict)
    ]
    if not any(claim.get("capacity_owner_binding_sha256") == binding_hash for claim in claims):
        errors.append("Hold & Spin容量派生证据未绑定画像capacity_owner_binding哈希")
    return errors


def validate_hold_spin_transition_contract(item, active_nodes):
    metric_id = item.get("metric_id")
    if metric_id not in {
        "hold_spin.capacity_transition_distribution",
        "hold_spin.occupancy_transition_distribution",
    }:
        return []
    node_map = {node.get("node_id"): node for node in active_nodes}
    nodes = [
        node for node in source_nodes(item, node_map)
        if node.get("mechanic_id") == "feature.hold-and-spin"
    ]
    if len(nodes) != 1:
        return [f"Hold & Spin推进指标必须唯一绑定一个玩法节点: {metric_id}"]
    attributes = nodes[0].get("attributes", {})
    variable = semantic_truthy(attributes.get("variable_capacity_rule")) or semantic_truthy(attributes.get("unlock_or_upgrade_rule"))
    if not variable:
        if metric_id == "hold_spin.capacity_transition_distribution":
            return ["固定容量Hold & Spin不得实例化容量推进指标"]
        return []
    transition = attributes.get("capacity_transition_contract")
    transition_map = transition.get("current_capacity_occupancy_to_next_capacity_domain") if isinstance(transition, dict) else None
    if not isinstance(transition_map, dict) or not transition_map:
        return [f"可变容量Hold & Spin推进指标缺少结构化容量转移合同: {metric_id}"]
    errors = []
    if metric_id == "hold_spin.capacity_transition_distribution":
        deterministic = all(isinstance(values, list) and len(values) == 1 for values in transition_map.values())
        if deterministic:
            if item.get("status") != INACTIVE_METRIC_STATUS or item.get("inapplicability_reason_code") != "deterministic_rule_result":
                errors.append("全部C|O组唯一确定C'时容量推进必须按确定规则派生且不评分")
            return errors
        if item.get("status") == INACTIVE_METRIC_STATUS:
            errors.append("存在至少一个多结果C|O组时容量推进不得整项标记不适用")
            return errors
        active_groups = {group: values for group, values in transition_map.items() if len(values) > 1}
        groups = target_groups(item)
        if set(groups) != set(active_groups):
            errors.append("容量推进活动组必须恰好等于规则中存在多个可达C'的C|O组")
        for group, values in active_groups.items():
            actual = distribution_positions(item, group)
            expected = {float(value) for value in values}
            if not isinstance(actual, dict) or set(actual) != expected:
                errors.append(f"容量推进目标支持未完整覆盖规则可达next_capacity: {group}")
        return errors

    if item.get("status") == INACTIVE_METRIC_STATUS:
        return errors
    allowed_groups = {
        f"{group}|{next_capacity}"
        for group, next_domain in transition_map.items()
        for next_capacity in next_domain
    }
    actual_groups = set(target_groups(item))
    invalid = sorted(actual_groups - allowed_groups)
    if invalid:
        errors.append(f"占用推进包含容量规则不可达的C|O|C'条件组: {','.join(invalid)}")
    return errors


def jackpot_classification(contract, node_id, opportunity_set_id):
    policy = contract.get("jackpot_materiality_policy")
    rows = policy.get("classifications") if isinstance(policy, dict) else None
    matches = [
        row for row in rows or []
        if isinstance(row, dict)
        and row.get("jackpot_node_id") == node_id
        and row.get("opportunity_set_id") == opportunity_set_id
    ]
    return matches[0] if len(matches) == 1 else None


def weighted_source_distribution_fields(item):
    fields = exact_target_fields(item)
    if not isinstance(fields, dict):
        return None
    groups = target_groups(item)
    if not groups:
        return fields
    profile = evaluation_profile(item) or {}
    weights = profile.get("group_weights")
    separator = profile.get("group_separator", "::")
    if not isinstance(weights, dict) or set(weights) != set(groups):
        return None
    result = {}
    for key, probability in fields.items():
        if separator not in key:
            return None
        group = key.split(separator, 1)[0]
        result[key] = probability * weights[group]
    return result


def validate_jackpot_material_metric(item, active_nodes, active_items_by_key, catalog, contract):
    metric_id = item.get("metric_id")
    if metric_id not in {"jackpot.material_hit_rate", "jackpot.material_tier_distribution_given_hit"}:
        return []
    node_map = {node.get("node_id"): node for node in active_nodes}
    jackpot_nodes = [
        node for node in source_nodes(item, node_map)
        if node.get("mechanic_id") == "award.jackpot"
    ]
    if len(jackpot_nodes) != 1:
        return [f"物质性Jackpot指标必须唯一绑定一个Jackpot节点: {metric_id}"]
    node = jackpot_nodes[0]
    dimensions = item.get("instance_dimensions") if isinstance(item.get("instance_dimensions"), dict) else {}
    opportunity_set_id = dimensions.get("jackpot_opportunity_set")
    classification = jackpot_classification(contract, node.get("node_id"), opportunity_set_id)
    if not isinstance(classification, dict):
        return [f"物质性Jackpot指标未命中唯一政策分类: {metric_id} / {opportunity_set_id}"]
    material_tiers = classification.get("material_tier_ids")
    if not isinstance(material_tiers, list) or len(material_tiers) != len(set(material_tiers)):
        return [f"物质性Jackpot政策层级集合无效: {metric_id} / {opportunity_set_id}"]
    reason = item.get("inapplicability_reason_code")
    errors = []
    if not material_tiers:
        if item.get("status") != INACTIVE_METRIC_STATUS or reason != "below_materiality_resolution":
            errors.append(f"没有物质性层级的Jackpot机会集必须按政策分辨率标记不适用: {metric_id} / {opportunity_set_id}")
        claims = [
            record.get("_claim") for record in item.get("inapplicability_evidence", [])
            if isinstance(record, dict) and isinstance(record.get("_claim"), dict)
        ]
        expected_hash = canonical_sha256(classification)
        if not any(claim.get("jackpot_materiality_classification_sha256") == expected_hash for claim in claims):
            errors.append(f"Jackpot低于物质性分辨率的证据未绑定当前分类hash: {metric_id} / {opportunity_set_id}")
        return errors

    tier_rows = classification.get("tier_exposure")
    tier_hits = {
        row.get("tier_id"): row.get("original_hit_count")
        for row in tier_rows or []
        if isinstance(row, dict) and row.get("tier_id") in material_tiers
    }
    opportunity_count = classification.get("original_opportunity_count")
    if (
        not isinstance(opportunity_count, int)
        or isinstance(opportunity_count, bool)
        or opportunity_count < 1
        or set(tier_hits) != set(material_tiers)
        or any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in tier_hits.values())
    ):
        return [f"Jackpot物质性原版暴露无法复算: {metric_id} / {opportunity_set_id}"]
    material_hit_count = sum(tier_hits.values())
    if material_hit_count > opportunity_count:
        errors.append(f"同一Jackpot机会集物质性层级命中数合计超过机会数: {opportunity_set_id}")
    expected_hit_rate = material_hit_count / opportunity_count
    expected_tiers = {
        tier_id: count / material_hit_count
        for tier_id, count in tier_hits.items()
    } if material_hit_count else None
    if metric_id == "jackpot.material_tier_distribution_given_hit" and len(material_tiers) == 1:
        if item.get("status") != INACTIVE_METRIC_STATUS or reason != "degenerate_reachable_support":
            errors.append(f"单一物质性层级的Jackpot构成必须按退化支持不计分: {opportunity_set_id}")
        return errors

    profile_bindings = node.get("attributes", {}).get("jackpot_material_owner_bindings", [])
    matches = [
        binding for binding in profile_bindings
        if isinstance(binding, dict) and binding.get("opportunity_set_id") == opportunity_set_id
    ] if isinstance(profile_bindings, list) else []
    if len(matches) > 1:
        return errors + [f"同一Jackpot机会集命中多个Primary投影绑定: {opportunity_set_id}"]
    if not matches:
        if item.get("status") == INACTIVE_METRIC_STATUS:
            errors.append(f"物质性Jackpot不存在Primary投影时必须直接评分: {metric_id} / {opportunity_set_id}")
        elif metric_id == "jackpot.material_hit_rate":
            if not finite_number(item.get("target")) or not close_probability(item.get("target"), expected_hit_rate):
                errors.append(f"物质性Jackpot总体命中率未由逐层原版暴露精确复算: {opportunity_set_id}")
        else:
            target = exact_target_fields(item)
            if expected_tiers is None:
                errors.append(f"物质性Jackpot原版没有命中样本，无法形成层级条件目标: {opportunity_set_id}")
            elif not isinstance(target, dict) or set(target) != set(expected_tiers) or any(
                not close_probability(target[tier_id], probability) for tier_id, probability in expected_tiers.items()
            ):
                errors.append(f"物质性Jackpot层级构成未由逐层原版命中数精确复算: {opportunity_set_id}")
        return errors

    binding = matches[0]
    if set(binding.get("covered_tier_ids", [])) != set(material_tiers):
        errors.append(f"Jackpot Primary投影必须恰好覆盖当前物质性层级: {opportunity_set_id}")
    if item.get("status") != INACTIVE_METRIC_STATUS or reason != "deterministically_derived_from_primary":
        errors.append(f"存在完整Jackpot Primary投影时不得重复评分: {metric_id} / {opportunity_set_id}")
        return errors
    if item.get("jackpot_material_owner_binding") != binding:
        errors.append(f"Jackpot指标合同未逐字段复制画像Primary投影绑定: {metric_id} / {opportunity_set_id}")
    source_ref = binding.get("primary_owner_metric_instance")
    source_key = metric_instance_key(source_ref) if isinstance(source_ref, dict) else (None, (), ())
    source = active_items_by_key.get(source_key)
    if source is None:
        return errors + [f"Jackpot投影未绑定唯一活动Primary实例: {format_instance(source_key)}"]
    source_catalog = catalog["metrics"].get(source.get("metric_id"), {})
    if (
        source_catalog.get("semantic_role") != "primary"
        or source.get("kind") not in {"hard", "score"}
        or source.get("metric_id") in {"core.rtp.component_contribution", "jackpot.material_hit_rate", "jackpot.material_tier_distribution_given_hit"}
    ):
        errors.append(f"Jackpot投影来源不是允许的活动Primary: {source.get('metric_id')}")
    if source.get("sealed_event_set_id") != binding.get("shared_semantic_event_set_id"):
        errors.append(f"Jackpot投影来源未使用画像绑定的共享机会事件集: {source.get('metric_id')}")
    source_fields = weighted_source_distribution_fields(source)
    mapping = binding.get("source_outcome_to_jackpot_tier")
    if not isinstance(source_fields, dict) or not isinstance(mapping, dict) or set(mapping) != set(source_fields):
        return errors + [f"Jackpot投影映射必须完整且仅覆盖来源Primary支持: {opportunity_set_id}"]
    projected_tiers = {tier_id: 0.0 for tier_id in material_tiers}
    for source_field, probability in source_fields.items():
        tier_id = mapping[source_field]
        if tier_id is not None:
            if tier_id not in projected_tiers:
                errors.append(f"Jackpot投影映射到了非物质性或未知层级: {source_field} / {tier_id}")
                continue
            projected_tiers[tier_id] += probability
    projected_hit_rate = sum(projected_tiers.values())
    if not close_probability(projected_hit_rate, expected_hit_rate):
        errors.append(f"Jackpot Primary投影总体命中率与逐层原版暴露不一致: {opportunity_set_id}")
    if expected_tiers is not None and projected_hit_rate > 0:
        projected_given_hit = {tier_id: probability / projected_hit_rate for tier_id, probability in projected_tiers.items()}
        if any(not close_probability(projected_given_hit[tier_id], expected_tiers[tier_id]) for tier_id in expected_tiers):
            errors.append(f"Jackpot Primary投影层级构成与逐层原版暴露不一致: {opportunity_set_id}")
    if metric_id == "jackpot.material_hit_rate":
        if not finite_number(item.get("target")) or not close_probability(item.get("target"), projected_hit_rate):
            errors.append(f"物质性Jackpot总体命中率未由活动Primary精确投影: {opportunity_set_id}")
    else:
        target = exact_target_fields(item)
        if projected_hit_rate <= 0:
            errors.append(f"Jackpot Primary投影没有物质性命中概率质量: {opportunity_set_id}")
        else:
            projected = {tier_id: probability / projected_hit_rate for tier_id, probability in projected_tiers.items()}
            if not isinstance(target, dict) or set(target) != set(projected) or any(
                not close_probability(target[tier_id], probability) for tier_id, probability in projected.items()
            ):
                errors.append(f"物质性Jackpot层级构成未由活动Primary精确投影: {opportunity_set_id}")
    return errors


def validate_feature_return_zero_bucket(item, active_nodes=None):
    if item.get("metric_id") != "feature_cycle.return_distribution_by_stage_path" or item.get("status") == INACTIVE_METRIC_STATUS:
        return []
    dimensions = item.get("instance_dimensions")
    entry_source = dimensions.get("entry_source") if isinstance(dimensions, dict) else None
    if active_nodes is None:
        expected_denominator = {"natural": "triggering_paid_bet", "feature_buy": "actual_purchase_cost"}.get(entry_source)
    else:
        node_map = {
            node.get("node_id"): node
            for node in active_nodes
            if isinstance(node, dict) and isinstance(node.get("node_id"), str) and node.get("node_id")
        }
        nodes = source_nodes(item, node_map)
        definitions = [entry_source_semantics(node).get(entry_source) for node in nodes]
        definitions = [definition for definition in definitions if isinstance(definition, dict)]
        if len(definitions) != 1:
            expected_denominator = None
        elif definitions[0].get("origin") == "endogenous":
            expected_denominator = "triggering_paid_bet"
        elif definitions[0].get("source_kind") == "feature_buy":
            expected_denominator = "actual_purchase_cost"
        else:
            expected_denominator = None
    if expected_denominator is None:
        denominator_errors = [f"Feature入口来源缺少已登记的主回报分母语义: {entry_source}"]
    elif item.get("return_denominator") != expected_denominator:
        denominator_errors = [f"Feature路径回报分母与入口来源不一致: {entry_source}"]
    else:
        denominator_errors = []
    groups = target_groups(item)
    profile = item.get("score_profile")
    if not isinstance(profile, dict):
        return denominator_errors + ["Feature路径回报缺少有效score_profile"]
    positions = profile.get("bin_positions_by_group")
    boundaries = profile.get("bin_boundaries_by_group")
    if not groups or not isinstance(positions, dict) or set(positions) != set(groups):
        return denominator_errors + ["Feature路径回报必须按真实路径组密封目标与bin_positions_by_group"]
    if not isinstance(boundaries, dict) or set(boundaries) != set(groups):
        return denominator_errors + ["Feature路径回报必须按真实路径组密封bin_boundaries_by_group"]
    errors = list(denominator_errors)
    for group, labels in groups.items():
        if "0x" not in labels:
            errors.append(f"Feature路径缺少独立精确0x桶: {group}")
        if not isinstance(positions.get(group), dict) or positions[group].get("0x") != 0:
            errors.append(f"Feature路径0x桶位置必须精确为0: {group}")
        if set(positions[group]) != labels:
            errors.append(f"Feature路径目标桶与位置映射不一致: {group}")
        group_boundaries = boundaries.get(group)
        if not isinstance(group_boundaries, dict) or set(group_boundaries) != labels:
            errors.append(f"Feature路径目标桶与边界映射不一致: {group}")
            group_boundaries = {}
        values = {
            key.split(item.get("score_profile", {}).get("group_separator", "::"), 1)[1]: value
            for key, value in item.get("target", {}).items()
            if key.startswith(group + item.get("score_profile", {}).get("group_separator", "::"))
        }
        if any(not finite_number(value) or value < 0 for value in values.values()):
            errors.append(f"Feature路径目标概率包含非法值: {group}")
        elif abs(sum(values.values()) - 1.0) > item.get("score_profile", {}).get("normalization_tolerance", 1e-6):
            errors.append(f"Feature路径目标概率未按组归一化: {group}")
        position_values = positions.get(group, {}).values()
        if (
            any(not finite_number(value) or value < 0 for value in position_values)
            or any(label != "0x" and value <= 0 for label, value in positions.get(group, {}).items())
            or len(set(position_values)) != len(positions.get(group, {}))
        ):
            errors.append(f"Feature路径回报桶位置必须唯一、非负且正回报桶大于0: {group}")
        ordered = sorted(positions.get(group, {}), key=positions.get(group, {}).get)
        previous_upper = None
        for index, bucket in enumerate(ordered):
            boundary = group_boundaries.get(bucket)
            if not isinstance(boundary, dict) or not finite_number(boundary.get("lower")) or (
                boundary.get("upper") is not None and not finite_number(boundary.get("upper"))
            ):
                errors.append(f"Feature路径回报桶边界无效: {group} / {bucket}")
                continue
            lower, upper = boundary["lower"], boundary.get("upper")
            position = positions[group][bucket]
            if bucket == "0x":
                if lower != 0 or upper != 0 or position != 0:
                    errors.append(f"Feature路径0x桶必须精确绑定[0,0]: {group}")
            elif lower <= 0 or upper is not None and upper <= lower:
                errors.append(f"Feature路径正回报桶下界必须大于0且上界必须大于下界: {group} / {bucket}")
            if (upper is not None and not lower <= position <= upper) or (upper is None and position < lower):
                errors.append(f"Feature路径回报桶代表位置必须落在边界内: {group} / {bucket}")
            if previous_upper is not None and lower < previous_upper:
                errors.append(f"Feature路径回报桶边界发生重叠: {group} / {bucket}")
            if upper is None and index != len(ordered) - 1:
                errors.append(f"Feature路径无上界桶只能位于最后: {group} / {bucket}")
            previous_upper = upper
    return errors


def same_metric_instance_key(item, metric_id):
    source_ids = item.get("source_node_ids")
    if not isinstance(source_ids, list) or not all(isinstance(value, str) for value in source_ids):
        source_ids = []
    return metric_id, tuple(sorted(source_ids)), dimensions_key(item.get("instance_dimensions", {}))


def single_numeric_token(value):
    if finite_number(value):
        return float(value)
    if not isinstance(value, str):
        return None
    matches = re.findall(r"-?(?:\d+(?:\.\d*)?|\.\d+)", value)
    return float(matches[0]) if len(matches) == 1 else None


def integer_token(value):
    number = single_numeric_token(value)
    return int(number) if number is not None and number.is_integer() else None


def parsed_numeric_mapping(value, value_parser=float, key_parser=float, allow_none=False):
    if not isinstance(value, dict) or not value:
        return None
    result = {}
    try:
        for raw_key, raw_value in value.items():
            key = key_parser(raw_key)
            if key in result:
                return None
            parsed_value = None if allow_none and raw_value is None else value_parser(raw_value)
            if not finite_number(key) or parsed_value is not None and not finite_number(parsed_value):
                return None
            result[key] = parsed_value
    except (TypeError, ValueError):
        return None
    return result


def parsed_integer_key_mapping(value):
    if not isinstance(value, dict) or not value:
        return None
    result = {}
    for raw_key, raw_value in value.items():
        key = integer_token(raw_key)
        if key is None or key in result:
            return None
        result[key] = raw_value
    return result


def group_target_values(item, group):
    profile = evaluation_profile(item)
    separator = profile.get("group_separator", "::") if isinstance(profile, dict) else "::"
    return {
        key.split(separator, 1)[1]: value
        for key, value in item.get("target", {}).items()
        if isinstance(key, str) and key.startswith(group + separator)
    } if isinstance(item.get("target"), dict) else {}


def integer_distribution(item, group=None):
    values = distribution_positions(item, group)
    if not isinstance(values, dict):
        return None
    result = {}
    for position, probability in values.items():
        if not finite_number(position) or not float(position).is_integer():
            return None
        position = int(position)
        if position in result:
            return None
        result[position] = probability
    return result


def labeled_distribution(item):
    target = item.get("target")
    if isinstance(target, dict) and not target_groups(item):
        return target
    if isinstance(target, list):
        display = item.get("display") if isinstance(item.get("display"), dict) else {}
        labels = display.get("item_labels")
        if isinstance(labels, list) and len(labels) == len(target) and len(labels) == len(set(labels)):
            return dict(zip(labels, target))
    return None


def exact_target_fields(item):
    target = item.get("target")
    if isinstance(target, dict) and target:
        return {str(key): value for key, value in target.items()}
    if isinstance(target, list) and target:
        display = item.get("display") if isinstance(item.get("display"), dict) else {}
        labels = display.get("item_labels")
        if isinstance(labels, list) and len(labels) == len(target) and len(labels) == len(set(map(str, labels))):
            return {str(label): value for label, value in zip(labels, target)}
    return None


def declared_source_keys(item):
    keys = []
    for record in item.get("inapplicability_evidence", []):
        claim = record.get("expected_value") if isinstance(record, dict) else None
        sources = claim.get("source_metric_instances") if isinstance(claim, dict) else None
        if not isinstance(sources, list):
            continue
        for source in sources:
            if isinstance(source, dict):
                keys.append(metric_instance_key(source))
    return sorted(set(keys), key=instance_sort_key)


def validate_declared_derivation_projection(item, source_items, records):
    metric_id = item.get("metric_id")
    spec = DERIVATION_PROJECTORS.get(metric_id)
    if spec is None:
        return []
    source_ids = {source.get("metric_id") for source in source_items}
    if source_ids not in spec["source_sets"] or len(source_items) != 1:
        allowed = " 或 ".join("+".join(sorted(values)) for values in spec["source_sets"])
        return [f"条件派生必须精确绑定唯一登记来源集合: {metric_id} / 允许={allowed}"]
    claims = [record.get("_claim") for record in records if isinstance(record.get("_claim"), dict)]
    projections = [claim.get("projection") for claim in claims if isinstance(claim.get("projection"), dict)]
    if len(projections) != 1:
        return [f"条件派生必须且只能密封一个可执行projection: {metric_id}"]
    projection = projections[0]
    required = {"projector_id", "source_field_to_target_field", "normalization"}
    if set(projection) != required:
        return [f"条件派生projection必须完整使用三个固定字段: {metric_id}"]
    expected_projector = (
        "stage_path_to_primary_action_count_v1"
        if metric_id == "feature_cycle.duration_distribution"
        and source_ids == {"feature_cycle.stage_path_distribution"}
        else spec["projector_id"]
    )
    if projection.get("projector_id") != expected_projector:
        return [f"条件派生projector_id与登记语义不一致: {metric_id}"]
    if projection.get("normalization") != spec["normalization"]:
        return [f"条件派生归一化规则与登记语义不一致: {metric_id}"]
    source = source_items[0]
    source_fields = exact_target_fields(source)
    target_fields = exact_target_fields(item)
    mapping = projection.get("source_field_to_target_field")
    if not isinstance(source_fields, dict) or not isinstance(target_fields, dict):
        return [f"条件派生来源或目标缺少完整业务标签分布: {metric_id}"]
    if not isinstance(mapping, dict) or set(mapping) != set(source_fields):
        return [f"条件派生映射必须完整且仅覆盖来源目标字段: {metric_id}"]
    if any(value is not None and (not isinstance(value, str) or not value) for value in mapping.values()):
        return [f"条件派生映射目标必须为非空字段名或null: {metric_id}"]
    retained = {
        source_key: target_key
        for source_key, target_key in mapping.items()
        if target_key is not None
    }
    if not retained or set(retained.values()) != set(target_fields):
        return [f"条件派生映射必须覆盖全部且仅覆盖目标字段: {metric_id}"]
    if any(not finite_number(value) or value < 0 for value in source_fields.values()):
        return [f"条件派生来源目标包含非法概率: {metric_id}"]
    projected = {key: 0.0 for key in target_fields}
    for source_key, target_key in retained.items():
        projected[target_key] += source_fields[source_key]
    normalization = projection["normalization"]
    if normalization == "condition_on_retained_mass":
        total = sum(projected.values())
        if total <= 0:
            return [f"条件派生保留概率质量为0: {metric_id}"]
        projected = {key: value / total for key, value in projected.items()}
    elif normalization == "condition_on_retained_mass_by_target_group":
        profile = evaluation_profile(item) or {}
        separator = profile.get("group_separator", "::")
        groups = {}
        for key in projected:
            if not isinstance(key, str) or separator not in key:
                return [f"条件派生分组目标字段缺少group_separator: {metric_id} / {key}"]
            group = key.split(separator, 1)[0]
            groups.setdefault(group, []).append(key)
        for group, keys in groups.items():
            total = sum(projected[key] for key in keys)
            if total <= 0:
                return [f"条件派生目标组保留概率质量为0: {metric_id} / {group}"]
            for key in keys:
                projected[key] /= total
    elif normalization != "none":
        return [f"条件派生使用未知归一化规则: {metric_id} / {normalization}"]
    if any(not close_probability(target_fields[key], projected[key]) for key in projected):
        return [f"条件派生目标未由来源目标和密封映射逐值精确复算: {metric_id}"]
    return []


def validate_derived_diagnostic_projection(item, items_by_key, active_nodes):
    metric_id = item.get("metric_id")
    controlled = {
        "board.symbol_presence_distribution",
        "board.symbol_cell_share_distribution",
        "cascade.continuation_rate_by_step",
        "free_spin.retrigger_rate",
        "respin.extension_rate",
        "variable_grid.capacity_distribution",
    }
    if metric_id not in controlled or item.get("status") == INACTIVE_METRIC_STATUS:
        return []
    errors = []

    if metric_id in {"board.symbol_presence_distribution", "board.symbol_cell_share_distribution"}:
        source = items_by_key.get(same_metric_instance_key(item, "board.symbol_count_per_board_distribution"))
        if not isinstance(source, dict):
            return [f"盘面派生诊断缺少同实例单盘符号数量Owner: {metric_id}"]
        groups = target_groups(source)
        if not groups:
            return [f"单盘符号数量Owner缺少按真实symbol_id分组目标: {metric_id}"]
        count_distributions = {group: integer_distribution(source, group) for group in groups}
        if any(not isinstance(values, dict) or 0 not in values for values in count_distributions.values()):
            return [f"单盘符号数量Owner必须逐symbol_id保留含0的完整精确整数支持: {metric_id}"]
        actual = labeled_distribution(item)
        if not isinstance(actual, dict) or set(actual) != set(groups):
            return [f"盘面派生诊断目标必须逐项覆盖来源symbol_id: {metric_id}"]
        if metric_id == "board.symbol_presence_distribution":
            expected = {group: 1.0 - values[0] for group, values in count_distributions.items()}
        else:
            expected_counts = {
                group: sum(count * probability for count, probability in values.items())
                for group, values in count_distributions.items()
            }
            total = sum(expected_counts.values())
            if total <= 0:
                return ["符号格占比无法从全0数量目标派生"]
            expected = {group: value / total for group, value in expected_counts.items()}
        if any(not close_probability(actual[group], expected[group]) for group in expected):
            errors.append(f"盘面派生诊断目标未由单盘符号数量Owner精确复算: {metric_id}")
        return errors

    if metric_id == "cascade.continuation_rate_by_step":
        source = items_by_key.get(same_metric_instance_key(item, "cascade.depth_distribution"))
        depth = integer_distribution(source) if isinstance(source, dict) else None
        target = labeled_distribution(item)
        if not isinstance(depth, dict) or not isinstance(target, dict):
            return ["Cascade继续率缺少同实例深度Owner或逐层目标"]
        for label, actual in target.items():
            step = integer_token(label)
            if step is None or step < 0:
                errors.append(f"Cascade继续率层级标签不是非负整数: {label}")
                continue
            reached = sum(probability for terminal_depth, probability in depth.items() if terminal_depth >= step)
            continued = sum(probability for terminal_depth, probability in depth.items() if terminal_depth >= step + 1)
            if reached <= 0 or not close_probability(actual, continued / reached):
                errors.append(f"Cascade继续率未由深度生存概率精确复算: {label}")
        return errors

    if metric_id in {"free_spin.retrigger_rate", "respin.extension_rate"}:
        source_id = {
            "free_spin.retrigger_rate": "free_spin.retrigger_grant_distribution",
            "respin.extension_rate": "respin.extension_grant_distribution",
        }[metric_id]
        source = items_by_key.get(same_metric_instance_key(item, source_id))
        distribution = integer_distribution(source) if isinstance(source, dict) else None
        if not isinstance(distribution, dict) or 0 not in distribution or not finite_number(item.get("target")):
            return [f"续命发生率缺少同实例完整赠送次数Owner或0次桶: {metric_id}"]
        expected = 1.0 - distribution[0]
        return [] if close_probability(item.get("target"), expected) else [f"续命发生率未由0次赠送补集精确复算: {metric_id}"]

    node_map = {node.get("node_id"): node for node in active_nodes}
    nodes = [
        node for node in source_nodes(item, node_map)
        if node.get("mechanic_id") == "board.variable-grid"
    ]
    if len(nodes) != 1:
        return ["可变网格容量派生必须唯一绑定一个可变网格节点"]
    bindings = nodes[0].get("attributes", {}).get("layout_capacity_projection_bindings", [])
    candidates = []
    for binding in bindings if isinstance(bindings, list) else []:
        source_id = binding.get("source_metric_id") if isinstance(binding, dict) else None
        source = items_by_key.get(same_metric_instance_key(item, source_id)) if source_id else None
        if isinstance(source, dict) and source.get("status") != INACTIVE_METRIC_STATUS:
            candidates.append((binding, source))
    if len(candidates) != 1:
        return ["可变网格容量派生必须命中唯一活动几何Owner及其投影绑定"]
    binding, source = candidates[0]
    source_distribution = labeled_distribution(source)
    mapping = binding.get("source_layout_to_capacity")
    if not isinstance(source_distribution, dict) or not isinstance(mapping, dict) or set(mapping) != set(source_distribution):
        return ["可变网格容量投影映射未完整且仅覆盖活动布局Owner支持"]
    projected = {}
    for label, probability in source_distribution.items():
        capacity = float(mapping[label])
        projected[capacity] = projected.get(capacity, 0.0) + probability
    actual = distribution_positions(item)
    if not isinstance(actual, dict) or set(actual) != set(projected) or any(
        not close_probability(actual[capacity], projected[capacity]) for capacity in projected
    ):
        errors.append("可变网格容量目标未由完整布局Owner和密封容量映射精确复算")
    return errors


def normalized_weights(raw):
    total = sum(raw.values()) if raw and all(finite_number(value) and value > 0 for value in raw.values()) else 0
    return {key: value / total for key, value in raw.items()} if total > 0 else {}


def weights_match(actual, expected):
    return (
        isinstance(actual, dict)
        and set(actual) == set(expected)
        and all(close_probability(actual[key], value) for key, value in expected.items())
    )


def validate_conditional_group_weight_binding(item, items_by_key, active_node_map, evidence_root, input_manifest):
    profile = evaluation_profile(item)
    grouped_methods = {
        "grouped_mean_absolute_error",
        "grouped_total_variation",
        "grouped_wasserstein_1d",
    }
    if (
        item.get("status") == INACTIVE_METRIC_STATUS
        or item.get("kind") not in {"hard", "score"}
        or not isinstance(profile, dict)
        or profile.get("method") not in grouped_methods
    ):
        return []
    metric_id = item.get("metric_id")
    weights = profile.get("group_weights")
    if not isinstance(weights, dict) or not weights:
        return [f"活动分组指标缺少group_weights: {metric_id}"]
    binding = item.get("conditional_group_weight_binding")
    if not isinstance(binding, dict):
        return [f"活动分组指标缺少conditional_group_weight_binding: {metric_id}"]
    method = binding.get("method")
    normalization = binding.get("normalization")
    errors = []
    if normalization != "normalize_positive_active_groups":
        errors.append(f"条件组权重必须固定按正暴露活动组归一化: {metric_id}")

    if method == "sealed_original_exposure":
        required = {
            "method",
            "source_event_set_id",
            "source_evidence_path",
            "source_evidence_sha256",
            "source_event_count",
            "group_exposure_counts",
            "token_multipliers",
            "normalization",
        }
        if set(binding) != required:
            return errors + [f"原版暴露组权重绑定必须完整使用八个固定字段: {metric_id}"]
        path_value = binding.get("source_evidence_path")
        path = safe_evidence_path(Path(evidence_root).resolve(), path_value) if evidence_root is not None else None
        digest = binding.get("source_evidence_sha256")
        if not non_empty(binding.get("source_event_set_id")):
            errors.append(f"原版暴露组权重缺少source_event_set_id: {metric_id}")
        if path is None or not path.is_file():
            errors.append(f"原版暴露组权重证据文件不存在: {metric_id}")
            events = []
        elif not is_sha256(digest) or sha(path) != digest:
            errors.append(f"原版暴露组权重证据hash无效: {metric_id}")
            events = []
        else:
            manifest_hashes = input_manifest.get("hashes", {}) if isinstance(input_manifest.get("hashes"), dict) else {}
            if manifest_hashes.get(path_value) != digest:
                errors.append(f"原版暴露组权重证据未写入input_manifest.hashes: {metric_id}")
            try:
                payload = load(path)
                events = payload if isinstance(payload, list) else payload.get("events") if isinstance(payload, dict) else None
                if not isinstance(events, list) or not events:
                    raise ValueError("证据必须为非空事件数组")
                if any(
                    not isinstance(event, dict)
                    or not non_empty(event.get("event_id"))
                    or not non_empty(event.get("conditional_group_id"))
                    for event in events
                ):
                    raise ValueError("每条事件必须包含event_id与conditional_group_id")
            except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
                errors.append(f"原版暴露组权重证据格式无效: {metric_id} / {exc}")
                events = []
        declared_count = binding.get("source_event_count")
        if not isinstance(declared_count, int) or isinstance(declared_count, bool) or declared_count < 1:
            errors.append(f"原版暴露组权重source_event_count无效: {metric_id}")
        elif events and len(events) != declared_count:
            errors.append(f"原版暴露组权重事件数与证据不一致: {metric_id}")
        declared_counts = binding.get("group_exposure_counts")
        multipliers = binding.get("token_multipliers")
        if (
            not isinstance(declared_counts, dict)
            or set(declared_counts) != set(weights)
            or any(not isinstance(value, int) or isinstance(value, bool) or value < 1 for value in declared_counts.values())
        ):
            errors.append(f"原版暴露组权重必须以正整数完整覆盖活动组: {metric_id}")
            declared_counts = {}
        if (
            not isinstance(multipliers, dict)
            or set(multipliers) != set(weights)
            or any(not finite_number(value) or value <= 0 for value in multipliers.values())
        ):
            errors.append(f"原版暴露组权重token_multipliers必须以有限正数完整覆盖活动组: {metric_id}")
            multipliers = {}
        if events:
            actual_counts = {}
            for event in events:
                group = event["conditional_group_id"]
                actual_counts[group] = actual_counts.get(group, 0) + 1
            if actual_counts != declared_counts:
                errors.append(f"原版暴露组计数未由证据逐事件复算一致: {metric_id}")
        if declared_counts and multipliers:
            expected = normalized_weights({group: declared_counts[group] * multipliers[group] for group in weights})
            if not weights_match(weights, expected):
                errors.append(f"group_weights未由原版组暴露计数与token倍率确定性生成: {metric_id}")
        return errors

    if method != "source_metric_factors":
        return errors + [f"未知conditional_group_weight_binding.method: {metric_id} / {method}"]
    required = {
        "method",
        "source_metric_instances",
        "group_factor_rules",
        "normalization",
    }
    if set(binding) != required:
        return errors + [f"来源指标因子组权重绑定必须完整使用四个固定字段: {metric_id}"]
    references = binding.get("source_metric_instances")
    rules = binding.get("group_factor_rules")
    if not isinstance(references, dict) or not references:
        return errors + [f"条件组权重缺少来源指标实例: {metric_id}"]
    sources = {}
    for alias, reference in references.items():
        label = f"{metric_id}条件组权重来源{alias}"
        fields = {"metric_id", "source_node_ids", "instance_dimensions", "target_evidence_sha256"}
        if not non_empty(alias) or not isinstance(reference, dict) or set(reference) != fields:
            errors.append(f"{label}必须完整使用四个固定字段")
            continue
        key = (
            reference.get("metric_id"),
            tuple(sorted(reference.get("source_node_ids", []))) if isinstance(reference.get("source_node_ids"), list) else (),
            dimensions_key(reference.get("instance_dimensions")),
        )
        source = items_by_key.get(key)
        if source is None:
            errors.append(f"{label}未绑定唯一已验证指标事实: {format_instance(key)}")
            continue
        evidence = source.get("target_evidence") if isinstance(source.get("target_evidence"), dict) else {}
        if not is_sha256(reference.get("target_evidence_sha256")) or reference.get("target_evidence_sha256") != evidence.get("evidence_sha256"):
            errors.append(f"{label}未绑定当前来源目标证据hash")
        if not metric_instances_overlap(item, source, active_node_map):
            errors.append(f"{label}与消费指标不共享节点、作用域或语义事件集")
        sources[alias] = source
    if not isinstance(rules, dict) or set(rules) != set(weights):
        return errors + [f"条件组权重group_factor_rules必须完整覆盖活动组: {metric_id}"]
    raw_weights = {}
    for group, factors in rules.items():
        if not isinstance(factors, list) or not factors:
            errors.append(f"条件组权重因子列表不能为空: {metric_id} / {group}")
            continue
        product = 1.0
        for factor in factors:
            if not isinstance(factor, dict):
                errors.append(f"条件组权重因子必须为对象: {metric_id} / {group}")
                product = 0
                continue
            if set(factor) == {"constant"}:
                value = factor.get("constant")
                if not finite_number(value) or value <= 0:
                    errors.append(f"条件组权重常数因子必须为有限正数: {metric_id} / {group}")
                    product = 0
                else:
                    product *= value
                continue
            fields = {"source_alias", "source_field", "source_keys", "aggregation"}
            if set(factor) != fields or factor.get("source_field") not in {"target", "group_weights"} or factor.get("aggregation") != "sum":
                errors.append(f"条件组权重来源因子字段或聚合方式无效: {metric_id} / {group}")
                product = 0
                continue
            source = sources.get(factor.get("source_alias"))
            keys = factor.get("source_keys")
            if source is None or not isinstance(keys, list) or not keys or len(keys) != len(set(map(str, keys))):
                errors.append(f"条件组权重来源别名或键列表无效: {metric_id} / {group}")
                product = 0
                continue
            container = source.get("target") if factor.get("source_field") == "target" else (evaluation_profile(source) or {}).get("group_weights")
            if not isinstance(container, dict) or any(key not in container or not finite_number(container[key]) or container[key] < 0 for key in keys):
                errors.append(f"条件组权重来源键无法从密封来源复算: {metric_id} / {group}")
                product = 0
                continue
            product *= sum(container[key] for key in keys)
        if product <= 0 or not math.isfinite(product):
            errors.append(f"条件组权重活动组复算结果必须为有限正数: {metric_id} / {group}")
        else:
            raw_weights[group] = product
    if set(raw_weights) == set(weights) and not weights_match(weights, normalized_weights(raw_weights)):
        errors.append(f"group_weights未由来源指标目标与密封因子确定性生成: {metric_id}")
    return errors


def validate_position_residual_baselines(item, current_domain, next_domain=None):
    if item.get("metric_id") != "persistent_state.position_role_dependence_residual_given_count_transition":
        return []
    next_domain = current_domain if next_domain is None else next_domain
    profile = item.get("score_profile") if isinstance(item.get("score_profile"), dict) else {}
    groups = target_groups(item)
    baselines = profile.get("residual_baselines_by_group")
    if not isinstance(baselines, dict) or set(baselines) != set(groups):
        return ["位置角色残差必须为每个活动组密封residual_baselines_by_group"]
    separator = profile.get("group_separator", "::")
    errors = []
    for group, labels in groups.items():
        parts = group.split("|") if isinstance(group, str) else []
        current, removed, added = (integer_token(part) for part in parts[:3]) if len(parts) == 4 else (None, None, None)
        role = parts[3] if len(parts) == 4 else None
        domain = current_domain if role == "removed" else next_domain
        available = current if role == "removed" else len(next_domain) - current if role == "added" and current is not None else None
        selected = removed if role == "removed" else added if role == "added" else None
        if available is not None and selected is not None and not 0 < selected < available:
            errors.append(f"位置角色没有选择自由度时不得保留残差活动组: {group}")
        baseline = baselines.get(group)
        if (
            not isinstance(baseline, dict)
            or set(baseline) != set(domain)
            or any(not finite_number(value) or value < 0 or value > 1 for value in baseline.values())
        ):
            errors.append(f"位置角色残差基线必须以[0,1]概率完整覆盖position_domain: {group}")
            continue
        if not close_probability(sum(baseline.values()), 1.0):
            errors.append(f"位置角色残差基线组内必须合计为1: {group}")
        for position in labels:
            residual = item.get("target", {}).get(f"{group}{separator}{position}")
            if not finite_number(residual):
                errors.append(f"位置角色残差目标不是有限数: {group}::{position}")
                continue
            actual = baseline[position] + residual
            if actual < -1e-9 or actual > 1 + 1e-9:
                errors.append(f"位置角色残差baseline+residual超出[0,1]: {group}::{position}")
    return errors


def validate_respin_persistent_derivation(item, source_items, active_nodes):
    metric_id = item.get("metric_id")
    if metric_id not in {
        "persistent_state.occupied_position_count_distribution",
        "persistent_state.position_share_given_occupied_count_distribution",
    }:
        return []
    state = state_position_node(item, active_nodes)
    if state is None:
        return [f"Respin到持久位置派生必须唯一绑定position_set状态节点: {metric_id}"]
    dimensions = item.get("instance_dimensions") if isinstance(item.get("instance_dimensions"), dict) else {}
    binding_matches = []
    for node in active_nodes:
        if node.get("mechanic_id") != "feature.respin":
            continue
        binding = node.get("attributes", {}).get("retained_position_state_binding")
        if not isinstance(binding, dict):
            continue
        if (
            binding.get("state_node_id") == state.get("node_id")
            and binding.get("state_id") == dimensions.get("state_id")
            and binding.get("observation_point") == dimensions.get("observation_point")
            and binding.get("semantic_event_set_id") in set(state.get("semantic_event_set_ids", []))
        ):
            binding_matches.append((node, binding))
    if len(binding_matches) != 1:
        return [f"Respin到持久位置派生缺少唯一retained_position_state_binding: {metric_id}"]
    respin, binding = binding_matches[0]
    domain = state.get("attributes", {}).get("position_domain", [])
    respin_domain = respin.get("attributes", {}).get("position_domain", [])
    errors = []
    if not domain or domain != respin_domain:
        errors.append(f"Respin到持久位置派生的position_domain不一致: {metric_id}")
        return errors
    if binding.get("semantic_event_set_id") not in respin.get("semantic_event_set_ids", []):
        errors.append(f"Respin到持久位置派生未绑定双方共享语义事件集: {metric_id}")
    expected_source_id = respin.get("node_id")
    retained_items = [
        source for source in source_items
        if source.get("metric_id") == "respin.retained_position_count_distribution_by_step"
        and source.get("source_node_ids") == [expected_source_id]
    ]
    if len(retained_items) != 1:
        return errors + [f"Respin到持久位置派生缺少唯一按步骤保留数量Owner: {metric_id}"]
    retained = retained_items[0]
    step_groups = target_groups(retained)
    step_weights = (evaluation_profile(retained) or {}).get("group_weights")
    if not isinstance(step_weights, dict) or set(step_weights) != set(step_groups):
        return errors + [f"Respin按步骤保留数量缺少原版步骤暴露权重: {metric_id}"]
    retained_by_step = {}
    for group in step_groups:
        step = integer_token(group)
        distribution = integer_distribution(retained, group)
        if step is None or distribution is None or set(distribution) != set(range(len(domain) + 1)):
            errors.append(f"Respin按步骤保留数量目标无法边际化: {group}")
            continue
        retained_by_step[step] = (group, distribution)
    if len(retained_by_step) != len(step_groups):
        return errors

    count_mass = {count: 0.0 for count in range(len(domain) + 1)}
    for group, distribution in retained_by_step.values():
        for count, probability in distribution.items():
            count_mass[count] += step_weights[group] * probability
    if metric_id == "persistent_state.occupied_position_count_distribution":
        actual = integer_distribution(item)
        if actual is None or set(actual) != set(count_mass) or any(
            not close_probability(actual[count], probability)
            for count, probability in count_mass.items()
        ):
            errors.append("持久位置占用数量目标未由Respin步骤暴露与按步骤保留数量精确边际化")
        return errors

    share_items = [
        source for source in source_items
        if source.get("metric_id") == "respin.rerolled_position_share_given_counts_distribution"
        and source.get("source_node_ids") == [expected_source_id]
    ]
    if len(share_items) != 1:
        return errors + ["持久位置份额派生缺少唯一Respin重转位置份额Owner"]
    if respin.get("attributes", {}).get("rerolled_position_binding") != "position_domain_minus_retained_set":
        return errors + ["只有完整补集Respin才能派生持久位置份额"]
    rerolled_share = share_items[0]
    rerolled_groups = target_groups(rerolled_share)
    parsed_share = {}
    for group in rerolled_groups:
        parts = group.split("|") if isinstance(group, str) else []
        key = tuple(integer_token(part) for part in parts) if len(parts) == 3 else (None, None, None)
        if None in key or key in parsed_share:
            errors.append(f"Respin重转位置份额组无法用于补集派生: {group}")
        parsed_share[key] = group
    expected_by_count = {}
    expected_count_weights = {}
    size = len(domain)
    for count in range(1, size):
        denominator = count_mass[count]
        if denominator <= 1e-12:
            continue
        accumulated = {position: 0.0 for position in domain}
        for step, (step_group, distribution) in retained_by_step.items():
            joint_weight = step_weights[step_group] * distribution[count]
            if joint_weight <= 1e-12:
                continue
            rerolled_count = size - count
            share_group = parsed_share.get((step, count, rerolled_count))
            if share_group is None:
                errors.append(f"完整补集派生缺少step|retained|rerolled活动组: {step}|{count}|{rerolled_count}")
                continue
            rerolled_values = group_target_values(rerolled_share, share_group)
            if set(rerolled_values) != set(domain):
                errors.append(f"Respin重转位置份额未完整覆盖position_domain: {share_group}")
                continue
            for position in domain:
                occupied_share = (1.0 - rerolled_count * rerolled_values[position]) / count
                if occupied_share < -1e-9 or occupied_share > 1 + 1e-9:
                    errors.append(f"Respin补集反推的占用位置份额超出[0,1]: {share_group}::{position}")
                accumulated[position] += joint_weight * occupied_share
        expected_by_count[count] = {position: value / denominator for position, value in accumulated.items()}
        expected_count_weights[count] = denominator
    target_groups_by_name = target_groups(item)
    parsed_target = {group: integer_token(group) for group in target_groups_by_name}
    if set(parsed_target.values()) != set(expected_by_count) or len(set(parsed_target.values())) != len(parsed_target):
        errors.append("持久位置份额派生目标组未完整覆盖Respin正概率非退化保留数量")
    for group, count in parsed_target.items():
        if count not in expected_by_count:
            continue
        actual_values = group_target_values(item, group)
        expected_values = expected_by_count[count]
        if set(actual_values) != set(domain) or any(
            not close_probability(actual_values[position], expected_values[position])
            for position in set(actual_values) & set(expected_values)
        ):
            errors.append(f"持久位置份额目标未由Respin完整补集逐步骤复算并聚合: {group}")
    actual_weights = (evaluation_profile(item) or {}).get("group_weights")
    if isinstance(actual_weights, dict):
        expected_weights = normalized_weights({
            group: expected_count_weights.get(count, 0)
            for group, count in parsed_target.items()
        })
        if not weights_match(actual_weights, expected_weights):
            errors.append("持久位置份额group_weights未由Respin原版步骤与保留数量联合暴露生成")
    return errors


def state_position_node(item, active_nodes):
    source_ids = set(item.get("source_node_ids", []))
    matches = [
        node for node in active_nodes
        if node.get("node_id") in source_ids
        and node.get("mechanic_id") == "state.persistent-state"
        and node.get("attributes", {}).get("state_shape") == "position_set"
    ]
    return matches[0] if len(matches) == 1 else None


def position_domains_for_item(state, item):
    attributes = state.get("attributes", {})
    global_domain = attributes.get("position_domain")
    if not isinstance(global_domain, list) or not global_domain:
        return None, None, ["持久位置状态缺少非空position_domain"]
    raw_map = attributes.get("position_domain_by_actual_capacity")
    if raw_map is None:
        return global_domain, global_domain, []
    capacity_map = parsed_integer_key_mapping(raw_map)
    if capacity_map is None:
        return None, None, ["position_domain_by_actual_capacity容量键无效或数值归一后冲突"]
    dimensions = item.get("instance_dimensions") if isinstance(item.get("instance_dimensions"), dict) else {}
    metric_id = item.get("metric_id")
    if metric_id == "persistent_state.position_share_given_occupied_count_distribution":
        capacity = integer_token(dimensions.get("actual_capacity"))
        domain = capacity_map.get(capacity)
        if domain is None:
            return None, None, ["可变容量位置份额实例必须绑定有效actual_capacity"]
        return domain, domain, []
    if metric_id == "persistent_state.position_role_dependence_residual_given_count_transition":
        current_capacity = integer_token(dimensions.get("current_actual_capacity"))
        next_capacity = integer_token(dimensions.get("next_actual_capacity"))
        current_domain = capacity_map.get(current_capacity)
        next_domain = capacity_map.get(next_capacity)
        if current_domain is None or next_domain is None:
            return None, None, ["可变容量位置角色残差实例必须绑定有效current_actual_capacity与next_actual_capacity"]
        return current_domain, next_domain, []
    capacity = integer_token(dimensions.get("actual_capacity"))
    if capacity is None:
        return global_domain, global_domain, []
    domain = capacity_map.get(capacity)
    if domain is None:
        return None, None, ["可变容量位置指标实例actual_capacity不在画像容量域"]
    return domain, domain, []


def respin_node(item, active_nodes):
    source_ids = set(item.get("source_node_ids", []))
    matches = [
        node for node in active_nodes
        if node.get("node_id") in source_ids and node.get("mechanic_id") == "feature.respin"
    ]
    return matches[0] if len(matches) == 1 else None


def persistent_occupancy_for_transition(item, state_node, items_by_key):
    dimensions = item.get("instance_dimensions", {}) if isinstance(item.get("instance_dimensions"), dict) else {}
    event = dimensions.get("transition_event")
    bindings = state_node.get("attributes", {}).get("position_transition_bindings", [])
    matches = [binding for binding in bindings if isinstance(binding, dict) and binding.get("transition_event") == event]
    if len(matches) != 1:
        return None
    expected_dimensions = {
        "state_id": dimensions.get("state_id"),
        "observation_point": matches[0].get("from_observation_point"),
    }
    candidates = [
        candidate for candidate in items_by_key.values()
        if candidate.get("metric_id") == "persistent_state.occupied_position_count_distribution"
        and candidate.get("status") != INACTIVE_METRIC_STATUS
        and set(candidate.get("source_node_ids", [])) == set(item.get("source_node_ids", []))
        and candidate.get("instance_dimensions") == expected_dimensions
    ]
    return candidates[0] if len(candidates) == 1 else None


def position_count_owner_binding(item, state_node):
    bindings = state_node.get("attributes", {}).get("position_count_owner_bindings", [])
    dimensions = item.get("instance_dimensions", {}) if isinstance(item.get("instance_dimensions"), dict) else {}
    matches = [
        binding for binding in bindings
        if isinstance(binding, dict)
        and binding.get("consumer_metric_id") == item.get("metric_id")
        and binding.get("consumer_instance_dimensions") == dimensions
    ] if isinstance(bindings, list) else []
    return matches[0] if len(matches) == 1 else None


def bound_owner_item(binding, items_by_key):
    source = binding.get("primary_owner_metric_instance") if isinstance(binding, dict) else None
    if not isinstance(source, dict):
        return None
    key = (
        source.get("metric_id"),
        tuple(sorted(source.get("source_node_ids", []))),
        dimensions_key(source.get("instance_dimensions", {})),
    )
    return items_by_key.get(key)


def validate_external_position_count_owner(item, binding, owner, current_domain, next_domain=None):
    next_domain = current_domain if next_domain is None else next_domain
    metric_id, size, errors = item.get("metric_id"), len(current_domain), []
    errors += validate_position_residual_baselines(item, current_domain, next_domain)
    if owner is None:
        return errors + [f"空间指标绑定的专用数量Owner实例不存在: {metric_id}"]
    owner_dimensions = owner.get("instance_dimensions") if isinstance(owner.get("instance_dimensions"), dict) else {}
    owner_capacity = integer_token(owner_dimensions.get("actual_capacity"))
    if binding.get("relation") == "same_observation_count_marginal" and owner_capacity != size:
        errors.append(f"空间指标绑定的Hold & Spin实际容量必须等于当前position_domain大小: {metric_id}")
    if binding.get("relation") == "same_observation_count_marginal":
        distribution = integer_distribution(owner)
        if distribution is None or set(distribution) != set(range(size + 1)):
            return [f"空间位置份额绑定的专用数量Owner未完整覆盖0到N: {metric_id}"]
        groups = target_groups(item)
        parsed = {group: integer_token(group) for group in groups}
        expected_counts = {count for count, probability in distribution.items() if 0 < count < size and probability > 1e-12}
        if any(value is None or value <= 0 or value >= size for value in parsed.values()) or set(parsed.values()) != expected_counts:
            errors.append("空间位置份额组未完整且仅覆盖专用数量Owner的正概率非退化占用数量")
        for group, labels in groups.items():
            if set(labels) != set(current_domain):
                errors.append(f"空间位置份额组必须完整使用position_domain: {group}")
        expected = normalized_weights({group: distribution.get(count, 0) for group, count in parsed.items()})
        if not weights_match(item.get("score_profile", {}).get("group_weights"), expected):
            errors.append("空间位置份额group_weights未由专用数量Owner目标确定性生成")
        return errors

    owner_groups = target_groups(owner)
    owner_weights = owner.get("score_profile", {}).get("group_weights", {})
    expected_raw = {}
    for group in owner_groups:
        parts = group.split("|") if isinstance(group, str) else []
        current_capacity = integer_token(parts[0]) if len(parts) == 3 else None
        current = integer_token(parts[1]) if len(parts) == 3 else None
        next_capacity = integer_token(parts[2]) if len(parts) == 3 else None
        dimensions = item.get("instance_dimensions") if isinstance(item.get("instance_dimensions"), dict) else {}
        if (
            current_capacity != integer_token(dimensions.get("current_actual_capacity"))
            or next_capacity != integer_token(dimensions.get("next_actual_capacity"))
        ):
            continue
        if current is None or not 0 <= current <= size:
            errors.append(f"Hold & Spin数量转移组缺少真实当前占用数量: {group}")
            continue
        distribution = integer_distribution(owner, group)
        if distribution is None:
            errors.append(f"Hold & Spin数量转移组缺少实际下一占用数位置: {group}")
            continue
        for next_count, probability in distribution.items():
            if probability <= 1e-12:
                continue
            next_size = len(next_domain)
            if not current <= next_count <= next_size:
                errors.append(f"monotone_count_transition只允许current≤next≤下一实际容量: {group}")
                continue
            added = next_count - current
            if 0 < added < next_size - current:
                expected_raw[(current, 0, added, "added")] = (
                    expected_raw.get((current, 0, added, "added"), 0)
                    + owner_weights.get(group, 0) * probability * added
                )
    groups = target_groups(item)
    parsed = {}
    for group, labels in groups.items():
        parts = group.split("|") if isinstance(group, str) else []
        current, removed, added = (integer_token(part) for part in parts[:3]) if len(parts) == 4 else (None, None, None)
        role = parts[3] if len(parts) == 4 else None
        key = (current, removed, added, role)
        if role != "added" or removed != 0 or None in {current, added}:
            errors.append(f"H&S单调空间残差只允许current|removed0|addedN|added: {group}")
        parsed[group] = key
        expected_domain = next_domain if role == "added" else current_domain
        if set(labels) != set(expected_domain):
            errors.append(f"H&S空间残差组必须完整使用对应实际容量的position_domain: {group}")
        values = group_target_values(item, group).values()
        if values and all(finite_number(value) for value in values) and abs(sum(values)) > 1e-6:
            errors.append(f"H&S空间残差组内残差和必须为0: {group}")
    if set(parsed.values()) != set(expected_raw):
        errors.append("H&S空间残差组未完整且仅覆盖专用数量转移的正概率非退化新增角色")
    expected = normalized_weights({group: expected_raw.get(key, 0) for group, key in parsed.items()})
    if not weights_match(item.get("score_profile", {}).get("group_weights"), expected):
        errors.append("H&S空间残差group_weights未由专用数量转移目标与新增token数量确定性生成")
    return errors


def validate_persistent_position_contract(item, active_nodes, items_by_key):
    metric_id = item.get("metric_id")
    position_metrics = {
        "persistent_state.occupied_position_count_distribution",
        "persistent_state.position_share_given_occupied_count_distribution",
        "persistent_state.position_count_transition_distribution",
        "persistent_state.position_role_dependence_residual_given_count_transition",
    }
    if metric_id not in position_metrics or item.get("status") == INACTIVE_METRIC_STATUS:
        return []
    state = state_position_node(item, active_nodes)
    if state is None:
        return [f"持久位置指标必须唯一绑定position_set状态节点: {metric_id}"]
    current_domain, next_domain, domain_errors = position_domains_for_item(state, item)
    if domain_errors:
        return [f"{message}: {metric_id}" for message in domain_errors]
    domain = current_domain
    size, errors = len(domain), []
    errors += validate_position_residual_baselines(item, current_domain, next_domain)

    if metric_id == "persistent_state.occupied_position_count_distribution":
        distribution = integer_distribution(item)
        if distribution is None or set(distribution) != set(range(size + 1)):
            errors.append("持久位置占用数量目标必须完整覆盖0到position_domain大小的精确整数")
        return errors

    external_binding = position_count_owner_binding(item, state)
    if external_binding is not None:
        return validate_external_position_count_owner(
            item,
            external_binding,
            bound_owner_item(external_binding, items_by_key),
            current_domain,
            next_domain,
        )

    if metric_id == "persistent_state.position_share_given_occupied_count_distribution":
        occupancy = items_by_key.get(same_metric_instance_key(item, "persistent_state.occupied_position_count_distribution"))
    else:
        occupancy = persistent_occupancy_for_transition(item, state, items_by_key)
    if occupancy is None:
        return [f"持久位置指标缺少同状态同观测点占用数量Owner: {metric_id}"]
    occupancy_target = integer_distribution(occupancy)
    if occupancy_target is None:
        return [f"持久位置占用数量目标无法复算: {metric_id}"]

    if metric_id == "persistent_state.position_share_given_occupied_count_distribution":
        groups = target_groups(item)
        parsed = {group: integer_token(group) for group in groups}
        if any(value is None or value <= 0 or value >= size for value in parsed.values()) or len(set(parsed.values())) != len(parsed):
            errors.append("持久位置份额组必须使用1到N-1的唯一真实占用数量")
        expected_counts = {count for count, probability in occupancy_target.items() if 0 < count < size and probability > 1e-12}
        if set(parsed.values()) != expected_counts:
            errors.append("持久位置份额组未完整且仅覆盖正概率非退化占用数量")
        for group, labels in groups.items():
            if set(labels) != set(domain):
                errors.append(f"持久位置份额组必须完整使用position_domain: {group}")
        expected_weights = normalized_weights({group: occupancy_target.get(count, 0) for group, count in parsed.items()})
        if not weights_match(item.get("score_profile", {}).get("group_weights"), expected_weights):
            errors.append("持久位置份额group_weights未由原版占用数量边际确定性生成")
        return errors

    transition = item if metric_id == "persistent_state.position_count_transition_distribution" else items_by_key.get(
        same_metric_instance_key(item, "persistent_state.position_count_transition_distribution")
    )
    if transition is None or transition.get("status") == INACTIVE_METRIC_STATUS:
        return [f"持久位置角色残差缺少同转移实例数量转移Owner: {metric_id}"]
    transition_groups = target_groups(transition)
    current_by_group = {group: integer_token(group) for group in transition_groups}
    if any(value is None or value < 0 or value > size for value in current_by_group.values()) or len(set(current_by_group.values())) != len(current_by_group):
        errors.append("持久位置数量转移组必须使用0到N的唯一当前占用数量")
    expected_current = {count for count, probability in occupancy_target.items() if probability > 1e-12}
    if set(current_by_group.values()) != expected_current:
        errors.append("持久位置数量转移组未完整覆盖原版正概率当前占用数量")
    transition_pairs = {}
    for group, labels in transition_groups.items():
        current = current_by_group.get(group)
        parsed_pairs = {}
        for label in labels:
            parts = label.split("|") if isinstance(label, str) else []
            removed, added = (integer_token(part) for part in parts) if len(parts) == 2 else (None, None)
            if current is None or removed is None or added is None or not (0 <= removed <= current and 0 <= added <= size - current):
                errors.append(f"持久位置数量转移值违反removed≤current或added≤N-current: {group}::{label}")
                continue
            if (removed, added) in parsed_pairs.values():
                errors.append(f"持久位置数量转移组存在重复实际计数组合: {group}")
            parsed_pairs[label] = (removed, added)
        transition_pairs[group] = parsed_pairs
    expected_transition_weights = normalized_weights({group: occupancy_target.get(count, 0) for group, count in current_by_group.items()})
    if not weights_match(transition.get("score_profile", {}).get("group_weights"), expected_transition_weights):
        errors.append("持久位置数量转移group_weights未由转移前占用数量边际确定性生成")
    if metric_id == "persistent_state.position_count_transition_distribution":
        return errors

    residual_groups = target_groups(item)
    parsed_residual = {}
    for group, labels in residual_groups.items():
        parts = group.split("|") if isinstance(group, str) else []
        current, removed, added = (integer_token(part) for part in parts[:3]) if len(parts) == 4 else (None, None, None)
        role = parts[3] if len(parts) == 4 else None
        key = (current, removed, added, role)
        if role not in {"removed", "added"} or None in {current, removed, added}:
            errors.append(f"持久位置角色残差组只允许current|removed|added|removed或added: {group}")
            continue
        expected_domain = current_domain if role == "removed" else next_domain
        if set(labels) != set(expected_domain):
            errors.append(f"持久位置角色残差组必须完整使用对应实际容量的position_domain: {group}")
        values = group_target_values(item, group).values()
        if values and all(finite_number(value) for value in values) and abs(sum(values)) > 1e-6:
            errors.append(f"持久位置角色残差组内残差和必须为0: {group}")
        if key in parsed_residual.values():
            errors.append(f"持久位置角色残差存在重复实际条件组: {group}")
        parsed_residual[group] = key

    expected_raw = {}
    transition_weights = transition.get("score_profile", {}).get("group_weights", {})
    for transition_group, pairs in transition_pairs.items():
        current = current_by_group.get(transition_group)
        for label, (removed, added) in pairs.items():
            probability = group_target_values(transition, transition_group).get(label, 0)
            if not finite_number(probability) or probability <= 1e-12:
                continue
            for role, count, available in (("removed", removed, current), ("added", added, len(next_domain) - current)):
                if 0 < count < available:
                    key = (current, removed, added, role)
                    expected_raw[key] = transition_weights.get(transition_group, 0) * probability * count
    actual_keys = set(parsed_residual.values())
    if actual_keys != set(expected_raw):
        errors.append("持久位置角色残差组未完整且仅覆盖正概率、非退化的removed/added角色")
    expected_residual_weights = normalized_weights({group: expected_raw.get(key, 0) for group, key in parsed_residual.items()})
    if not weights_match(item.get("score_profile", {}).get("group_weights"), expected_residual_weights):
        errors.append("持久位置角色残差group_weights未由数量转移目标与角色数量确定性生成")
    return errors


def validate_matched_position_transition_contract(item, active_nodes, items_by_key):
    metric_id = item.get("metric_id")
    if (
        metric_id != "persistent_state.matched_position_pairing_residual_given_count_transition"
        or item.get("status") == INACTIVE_METRIC_STATUS
    ):
        return []
    state = state_position_node(item, active_nodes)
    if state is None:
        return ["一一配对位置移动残差必须唯一绑定position_set状态节点"]
    dimensions = item.get("instance_dimensions") if isinstance(item.get("instance_dimensions"), dict) else {}
    event = dimensions.get("transition_event")
    bindings = state.get("attributes", {}).get("matched_position_transition_bindings", [])
    matches = [binding for binding in bindings if isinstance(binding, dict) and binding.get("transition_event") == event]
    if len(matches) != 1:
        return ["一一配对位置移动残差未命中唯一matched_position_transition_bindings"]
    binding = matches[0]
    pairs = binding.get("reachable_position_pairs", [])
    pair_ids = [pair.get("pair_id") for pair in pairs if isinstance(pair, dict)]
    pair_map = {
        pair.get("pair_id"): (pair.get("origin_position_id"), pair.get("destination_position_id"))
        for pair in pairs
        if isinstance(pair, dict)
    }
    target = item.get("target") if isinstance(item.get("target"), dict) else {}
    groups = target_group_labels_in_order(item)
    profile = item.get("score_profile") if isinstance(item.get("score_profile"), dict) else {}
    errors = []
    if profile.get("method") != "grouped_mean_absolute_error" or profile.get("group_weight_source") != "task_contract":
        errors.append("一一配对位置移动残差必须使用任务合同组权重的grouped_mean_absolute_error")
    if len(pair_ids) < 2 or len(pair_ids) != len(set(pair_ids)) or set(pair_ids) != set(pair_map):
        errors.append("活动的一一配对位置移动残差必须绑定至少两个唯一pair_id")
    if not groups:
        errors.append("一一配对位置移动残差必须使用current_count|removed_count|added_count::pair_id字段")
    transition = items_by_key.get(same_metric_instance_key(item, "persistent_state.position_count_transition_distribution"))
    if transition is None or transition.get("status") == INACTIVE_METRIC_STATUS:
        errors.append("一一配对位置移动缺少同转移实例的移除新增数量Owner")
        transition_positive = set()
    else:
        transition_positive = {
            (integer_token(group), integer_token(label.split("|")[0]), integer_token(label.split("|")[1]))
            for group, labels in target_groups(transition).items()
            for label in labels
            if isinstance(label, str)
            and len(label.split("|")) == 2
            and finite_number(group_target_values(transition, group).get(label))
            and group_target_values(transition, group).get(label) > 1e-12
        }
    parsed_groups = set()
    tolerance = profile.get("normalization_tolerance", 1e-6)
    separator = profile.get("group_separator", "::")
    for group, labels in groups.items():
        parts = group.split("|") if isinstance(group, str) else []
        key = tuple(integer_token(part) for part in parts) if len(parts) == 3 else (None, None, None)
        current, removed, added = key
        if None in key or current < 0 or removed < 0 or added < 0 or removed > current:
            errors.append(f"一一配对位置移动残差组必须使用合法current_count|removed_count|added_count: {group}")
            continue
        if key in parsed_groups:
            errors.append(f"一一配对位置移动残差存在重复数量转移组: {group}")
        parsed_groups.add(key)
        if transition is not None and key not in transition_positive:
            errors.append(f"一一配对位置移动残差组未命中数量转移Owner正概率支持: {group}")
        if labels != pair_ids:
            errors.append(f"一一配对位置移动残差每组必须按Binding顺序完整使用全部pair_id: {group}")
            continue
        values = {pair_id: target.get(f"{group}{separator}{pair_id}") for pair_id in pair_ids}
        if any(not finite_number(value) or value < -1 or value > 1 for value in values.values()):
            errors.append(f"一一配对位置移动残差必须为[-1,1]有限值: {group}")
            continue
        if abs(sum(values.values())) > tolerance:
            errors.append(f"一一配对位置移动残差组总和必须为0: {group}")
        row_sums, column_sums = {}, {}
        for pair_id, value in values.items():
            origin, destination = pair_map[pair_id]
            row_sums[origin] = row_sums.get(origin, 0) + value
            column_sums[destination] = column_sums.get(destination, 0) + value
        if any(abs(value) > tolerance for value in row_sums.values()):
            errors.append(f"一一配对位置移动残差每个起点行和必须为0: {group}")
        if any(abs(value) > tolerance for value in column_sums.values()):
            errors.append(f"一一配对位置移动残差每个终点列和必须为0: {group}")
    return errors


def validate_respin_position_contract(item, active_nodes, items_by_key):
    metric_id = item.get("metric_id")
    position_metrics = {
        "respin.retained_position_count_distribution_by_step",
        "respin.rerolled_position_count_distribution_given_retained_count",
        "respin.rerolled_position_share_given_counts_distribution",
    }
    if metric_id not in position_metrics or item.get("status") == INACTIVE_METRIC_STATUS:
        return []
    node = respin_node(item, active_nodes)
    if node is None:
        return [f"Respin位置指标必须唯一绑定feature.respin节点: {metric_id}"]
    domain = node.get("attributes", {}).get("position_domain", [])
    size, errors = len(domain), []
    if not domain:
        return [f"Respin位置指标缺少非空position_domain: {metric_id}"]
    retained = item if metric_id == "respin.retained_position_count_distribution_by_step" else items_by_key.get(
        same_metric_instance_key(item, "respin.retained_position_count_distribution_by_step")
    )
    if retained is None or retained.get("status") == INACTIVE_METRIC_STATUS:
        return [f"Respin位置指标缺少同实例按步骤保留数量Owner: {metric_id}"]
    retained_groups = target_groups(retained)
    step_by_group = {group: integer_token(group) for group in retained_groups}
    steps = set(step_by_group.values())
    if None in steps or not steps or min(steps) != 1 or steps != set(range(1, max(steps) + 1)) or len(steps) != len(step_by_group):
        errors.append("Respin步骤组必须使用从1开始连续且唯一的实际执行序号")
    retained_distributions = {}
    for group in retained_groups:
        distribution = integer_distribution(retained, group)
        if distribution is None or set(distribution) != set(range(size + 1)):
            errors.append(f"Respin保留数量组必须完整覆盖0到position_domain大小: {group}")
        else:
            retained_distributions[group] = distribution
    if metric_id == "respin.retained_position_count_distribution_by_step":
        return errors

    rerolled = item if metric_id == "respin.rerolled_position_count_distribution_given_retained_count" else items_by_key.get(
        same_metric_instance_key(item, "respin.rerolled_position_count_distribution_given_retained_count")
    )
    if rerolled is None or (
        rerolled.get("status") == INACTIVE_METRIC_STATUS
        and rerolled.get("inapplicability_reason_code") != "deterministic_rule_result"
    ):
        return errors + [f"Respin位置份额缺少同实例重转位置数量Owner: {metric_id}"]
    complement_rule = node.get("attributes", {}).get("rerolled_position_binding") == "position_domain_minus_retained_set"
    if complement_rule and rerolled.get("status") != INACTIVE_METRIC_STATUS:
        errors.append("完整补集Respin的重转位置数量必须按deterministic_rule_result标记不适用")
    rerolled_groups = target_groups(rerolled)
    parsed_rerolled = {}
    expected_rerolled = {}
    retained_weights = retained.get("score_profile", {}).get("group_weights", {})
    for step_group, distribution in retained_distributions.items():
        step = step_by_group[step_group]
        for retained_count, probability in distribution.items():
            if finite_number(probability) and probability > 1e-12:
                expected_rerolled[(step, retained_count)] = retained_weights.get(step_group, 0) * probability
    for group in rerolled_groups:
        parts = group.split("|") if isinstance(group, str) else []
        key = tuple(integer_token(part) for part in parts) if len(parts) == 2 else (None, None)
        if None in key or key in parsed_rerolled.values():
            errors.append(f"Respin重转数量组必须使用唯一step|retained_count实际标签: {group}")
        parsed_rerolled[group] = key
        distribution = integer_distribution(rerolled, group)
        if distribution is None or set(distribution) != set(range(size + 1)):
            errors.append(f"Respin重转数量组必须完整覆盖0到position_domain大小: {group}")
        elif key[1] is not None and any(
            probability > 1e-12 and rerolled_count > size - key[1]
            for rerolled_count, probability in distribution.items()
        ):
            errors.append(f"Respin重转数量不得超过未保留位置数: {group}")
    if set(parsed_rerolled.values()) != set(expected_rerolled):
        errors.append("Respin重转数量组未完整覆盖按步骤保留数量目标的正概率支持")
    expected_rerolled_weights = normalized_weights({group: expected_rerolled.get(key, 0) for group, key in parsed_rerolled.items()})
    if not weights_match(rerolled.get("score_profile", {}).get("group_weights"), expected_rerolled_weights):
        errors.append("Respin重转数量group_weights未由步骤暴露与保留数量目标确定性生成")
    if metric_id == "respin.rerolled_position_count_distribution_given_retained_count":
        return errors

    share_groups = target_groups(item)
    parsed_share, expected_share = {}, {}
    rerolled_weights = rerolled.get("score_profile", {}).get("group_weights", {})
    for rerolled_group, (step, retained_count) in parsed_rerolled.items():
        for rerolled_count, probability in (integer_distribution(rerolled, rerolled_group) or {}).items():
            if finite_number(probability) and probability > 1e-12 and 0 < rerolled_count < size:
                expected_share[(step, retained_count, rerolled_count)] = rerolled_weights.get(rerolled_group, 0) * probability * rerolled_count
    for group, labels in share_groups.items():
        parts = group.split("|") if isinstance(group, str) else []
        key = tuple(integer_token(part) for part in parts) if len(parts) == 3 else (None, None, None)
        if None in key or key in parsed_share.values():
            errors.append(f"Respin位置份额组必须使用唯一step|retained_count|rerolled_count实际标签: {group}")
        parsed_share[group] = key
        if set(labels) != set(domain):
            errors.append(f"Respin位置份额组必须完整使用position_domain: {group}")
    if set(parsed_share.values()) != set(expected_share):
        errors.append("Respin位置份额组未完整且仅覆盖正概率、非全盘确定的重转数量条件")
    expected_share_weights = normalized_weights({group: expected_share.get(key, 0) for group, key in parsed_share.items()})
    if not weights_match(item.get("score_profile", {}).get("group_weights"), expected_share_weights):
        errors.append("Respin位置份额group_weights未由上游两层目标与重转token数量确定性生成")
    return errors


def validate_cascade_capacity_contract(item, items_by_key):
    if item.get("metric_id") != "cascade.step_return_distribution_by_depth" or item.get("status") == INACTIVE_METRIC_STATUS:
        return []
    depth = items_by_key.get(same_metric_instance_key(item, "cascade.depth_distribution"))
    capacity = items_by_key.get(same_metric_instance_key(item, "cascade.effective_capacity_distribution_by_depth"))
    if depth is None or capacity is None:
        return ["Cascade层回报缺少同实例深度边际或各层容量条件Owner"]
    if capacity.get("status") == INACTIVE_METRIC_STATUS and capacity.get("inapplicability_reason_code") != "degenerate_reachable_support":
        return ["Cascade层回报引用了非退化原因停用的容量条件Owner"]
    depth_distribution = distribution_positions(depth)
    if not isinstance(depth_distribution, dict):
        return ["Cascade深度目标缺少可复算的实际层数位置"]
    if any(position < 0 or not float(position).is_integer() for position in depth_distribution):
        return ["Cascade深度目标位置必须是非负整数层数"]
    exposure = {
        int(layer): sum(probability for completed, probability in depth_distribution.items() if completed >= layer)
        for layer in range(1, int(max(depth_distribution, default=0)) + 1)
    }
    exposure = {layer: probability for layer, probability in exposure.items() if probability > 1e-12}
    if not exposure:
        return ["Cascade层回报没有任何正概率到达层"]

    errors = []
    capacity_groups = target_group_labels_in_order(capacity)
    capacity_depths = {}
    for group, labels in capacity_groups.items():
        layer = single_numeric_token(group)
        if layer is None or not layer.is_integer() or int(layer) not in exposure:
            errors.append(f"Cascade容量条件组未使用唯一真实到达层标签: {group}")
            continue
        layer = int(layer)
        if layer in capacity_depths:
            errors.append(f"Cascade容量同一层出现多个条件组: {layer}")
            continue
        if len(labels) < 2:
            errors.append(f"Cascade容量退化层不得留在活动分组评分中: {group}")
        distribution = distribution_positions(capacity, group)
        if distribution is None:
            errors.append(f"Cascade容量组缺少实际容量位置: {group}")
            continue
        capacity_depths[layer] = {
            str(label): capacity.get("target", {}).get(f"{group}{capacity.get('score_profile', {}).get('group_separator', '::')}{label}")
            for label in labels
        }
    capacity_weights = capacity.get("score_profile", {}).get("group_weights")
    if capacity_groups:
        active_exposure_total = sum(exposure[layer] for layer in capacity_depths)
        expected_capacity_weights = {
            group: exposure[int(single_numeric_token(group))] / active_exposure_total
            for group in capacity_groups
            if single_numeric_token(group) is not None and int(single_numeric_token(group)) in capacity_depths
        }
        if not isinstance(capacity_weights, dict) or set(capacity_weights) != set(expected_capacity_weights):
            errors.append("Cascade容量group_weights未覆盖全部且仅覆盖非退化深度组")
        elif any(not close_probability(capacity_weights[group], expected) for group, expected in expected_capacity_weights.items()):
            errors.append("Cascade容量group_weights未由原版深度暴露概率确定性生成")
    elif capacity.get("status") != INACTIVE_METRIC_STATUS:
        errors.append("Cascade容量没有活动条件组时必须按退化支持标记不适用")

    step_groups = target_group_labels_in_order(item)
    step_by_depth = {}
    for group in step_groups:
        if "|" not in group:
            errors.append(f"Cascade层回报条件组必须使用真实depth|effective_capacity标签: {group}")
            continue
        depth_label, capacity_label = group.split("|", 1)
        layer = single_numeric_token(depth_label)
        if layer is None or not layer.is_integer() or int(layer) not in exposure or not non_empty(capacity_label):
            errors.append(f"Cascade层回报条件组层级或容量标签无效: {group}")
            continue
        step_by_depth.setdefault(int(layer), set()).add(capacity_label)
    if set(step_by_depth) != set(exposure):
        errors.append("Cascade层回报条件组未完整覆盖全部正概率到达层")

    expected_step_weights = {}
    for layer, q_layer in exposure.items():
        labels = step_by_depth.get(layer, set())
        if layer in capacity_depths:
            expected_labels = set(capacity_depths[layer])
            if labels != expected_labels:
                errors.append(f"Cascade层回报容量支持集与容量Owner不一致: 第{layer}层")
                continue
            for label, probability in capacity_depths[layer].items():
                expected_step_weights[(layer, label)] = q_layer * probability
        else:
            if len(labels) != 1:
                errors.append(f"Cascade容量Owner缺少非退化层条件边际: 第{layer}层")
                continue
            expected_step_weights[(layer, next(iter(labels)))] = q_layer
    total_step_exposure = sum(expected_step_weights.values())
    if total_step_exposure <= 0:
        errors.append("Cascade层回报无法从深度与容量目标生成有效组权重")
        return errors
    expected_by_group = {
        group: expected_step_weights[(int(single_numeric_token(group.split("|", 1)[0])), group.split("|", 1)[1])] / total_step_exposure
        for group in step_groups
        if "|" in group
        and single_numeric_token(group.split("|", 1)[0]) is not None
        and (int(single_numeric_token(group.split("|", 1)[0])), group.split("|", 1)[1]) in expected_step_weights
    }
    actual_step_weights = item.get("score_profile", {}).get("group_weights")
    if not isinstance(actual_step_weights, dict) or set(actual_step_weights) != set(expected_by_group):
        errors.append("Cascade层回报group_weights未覆盖深度×容量完整支持集")
    elif any(not close_probability(actual_step_weights[group], expected) for group, expected in expected_by_group.items()):
        errors.append("Cascade层回报group_weights未由原版深度暴露与容量条件目标确定性生成")
    return errors


def validate_feature_path_contract(item, active_items_by_key):
    metric_id = item.get("metric_id")
    if metric_id not in {
        "feature_cycle.return_distribution_by_stage_path",
        "feature_cycle.return_distribution",
        "feature_cycle.zero_return_rate",
        "feature_cycle.median_return",
    } or item.get("status") == INACTIVE_METRIC_STATUS:
        return []
    stage = active_items_by_key.get(same_metric_instance_key(item, "feature_cycle.stage_path_distribution"))
    returns = active_items_by_key.get(same_metric_instance_key(item, "feature_cycle.return_distribution_by_stage_path"))
    errors = []
    if stage is None or returns is None:
        return [f"Feature派生或条件回报缺少同实例路径边际与路径回报主指标: {metric_id}"]
    stage_target = stage.get("target")
    if not isinstance(stage_target, dict) or not stage_target or validate_probability_distribution(stage_target, "Feature路径边际"):
        errors.append("Feature阶段路径目标必须为带真实路径ID的概率对象")
        return errors
    return_groups = target_groups(returns)
    if set(return_groups) != set(stage_target):
        errors.append("Feature路径回报组必须与阶段路径目标支持集完全一致")
    weights = returns.get("score_profile", {}).get("group_weights")
    if not isinstance(weights, dict) or set(weights) != set(stage_target) or any(
        not finite_number(weights.get(path)) or abs(weights[path] - probability) > 1e-9
        for path, probability in stage_target.items()
    ):
        errors.append("Feature路径回报group_weights必须逐项等于同实例阶段路径目标概率")
    binding_fields = ("sealed_event_set_id", "sealed_event_set_path", "sealed_event_set_sha256", "sealed_event_count")
    if stage.get("status") != INACTIVE_METRIC_STATUS and any(stage.get(field) != returns.get(field) for field in binding_fields):
        errors.append("Feature路径边际与路径条件回报必须绑定同一密封事件集")
    if metric_id == "feature_cycle.return_distribution_by_stage_path":
        return errors
    returns_profile = returns.get("score_profile")
    separator = returns_profile.get("group_separator", "::") if isinstance(returns_profile, dict) else "::"
    marginal = {}
    if isinstance(returns.get("target"), dict):
        for key, probability in returns["target"].items():
            if not isinstance(key, str) or separator not in key or not finite_number(probability):
                errors.append("Feature路径回报目标结构无效，无法确定性聚合")
                continue
            path, bucket = key.split(separator, 1)
            marginal[bucket] = marginal.get(bucket, 0.0) + stage_target.get(path, 0.0) * probability
    if metric_id == "feature_cycle.return_distribution":
        if item.get("target") != marginal:
            errors.append("完整Feature回报边际目标未由路径边际与条件回报确定性聚合")
    elif metric_id == "feature_cycle.zero_return_rate":
        if not finite_number(item.get("target")) or abs(item.get("target") - marginal.get("0x", 0.0)) > 1e-9:
            errors.append("Feature零回报率目标必须等于确定性聚合后的精确0x概率")
    elif metric_id == "feature_cycle.median_return":
        positions_by_group = returns_profile.get("bin_positions_by_group", {}) if isinstance(returns_profile, dict) else {}
        positions = {}
        for group_positions in positions_by_group.values() if isinstance(positions_by_group, dict) else []:
            if not isinstance(group_positions, dict):
                continue
            for bucket, position in group_positions.items():
                if bucket in positions and positions[bucket] != position:
                    errors.append(f"Feature不同路径对同一回报桶使用了不同位置: {bucket}")
                positions[bucket] = position
        if marginal and set(marginal).issubset(positions):
            cumulative, median = 0.0, None
            for bucket in sorted(marginal, key=positions.get):
                cumulative += marginal[bucket]
                if cumulative >= 0.5 - 1e-12:
                    median = bucket
                    break
            if item.get("target") != median:
                errors.append("Feature回报中位档位目标未由完整回报边际确定性推出")
        else:
            errors.append("Feature回报中位档位缺少完整且一致的回报桶位置")
    return errors


def event_field(event, field):
    if not isinstance(field, str) or not field:
        raise KeyError(field)
    if field.startswith("/"):
        return json_pointer_value(event, field)
    current = event
    for token in field.split("."):
        if not isinstance(current, dict) or token not in current:
            raise KeyError(field)
        current = current[token]
    return current


def load_events(path):
    data = load(path)
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("events"), list):
        return data["events"]
    raise ValueError("密封事件集必须为JSON数组或包含events数组的对象")


def validate_feature_buy_contract(item, active_nodes, items_by_key, evidence_root):
    if item.get("metric_id") != "feature_cycle.base_bet_equivalent_return_distribution":
        return []
    node_map = {
        node.get("node_id"): node
        for node in active_nodes
        if isinstance(node, dict) and isinstance(node.get("node_id"), str) and node.get("node_id")
    }
    present = has_feature_buy(source_nodes(item, node_map))
    if not present:
        return [] if item.get("status") == INACTIVE_METRIC_STATUS and item.get("inapplicability_reason_code") == "feature_buy_unavailable" else ["无Feature Buy时折算回报审计必须按标准原因标记不适用"]
    if item.get("status") == INACTIVE_METRIC_STATUS:
        return ["存在Feature Buy时基础投注折算回报审计不得标记不适用"]
    if evidence_root is None:
        return ["Feature Buy折算审计缺少可信task_root"]
    contract = item.get("event_recomputation_contract")
    required = {
        "sealed_event_set_id",
        "sealed_event_set_path",
        "sealed_event_set_sha256",
        "event_count",
        "event_id_field",
        "feature_total_win_field",
        "actual_purchase_cost_field",
        "normal_base_bet_field",
        "entry_source_field",
        "entry_source_value",
        "base_bet_equivalent_bins",
    }
    if not isinstance(contract, dict) or not required.issubset(contract):
        return ["Feature Buy折算审计缺少完整逐事件重算合同"]
    errors = []
    if not is_sha256(contract.get("sealed_event_set_sha256")):
        errors.append("Feature Buy折算审计事件集SHA-256无效")
    primary_key = (
        "feature_cycle.return_distribution_by_stage_path",
        tuple(sorted(item.get("source_node_ids", []))),
        dimensions_key(item.get("instance_dimensions", {})),
    )
    primary = items_by_key.get(primary_key)
    stage = items_by_key.get((
        "feature_cycle.stage_path_distribution",
        primary_key[1],
        primary_key[2],
    ))
    if primary is None:
        errors.append("Feature Buy折算审计未绑定同实例的主回报指标")
    else:
        binding = {
            "sealed_event_set_id": "sealed_event_set_id",
            "sealed_event_set_path": "sealed_event_set_path",
            "sealed_event_set_sha256": "sealed_event_set_sha256",
            "event_count": "sealed_event_count",
        }
        if any(contract.get(field) != primary.get(primary_field) for field, primary_field in binding.items()):
            errors.append("Feature Buy折算审计与主回报未绑定同一事件ID、路径、hash和事件数")
        if primary.get("return_denominator") != "actual_purchase_cost":
            errors.append("Feature Buy主回报必须使用actual_purchase_cost分母")
    if stage is None:
        errors.append("Feature Buy折算审计未绑定同实例的阶段路径指标")
    for field in required - {"sealed_event_set_sha256", "event_count", "base_bet_equivalent_bins"}:
        if not non_empty(contract.get(field)):
            errors.append(f"Feature Buy折算审计字段为空: {field}")
    if contract.get("entry_source_value") != "feature_buy":
        errors.append("Feature Buy折算审计entry_source_value必须为feature_buy")
    if not isinstance(contract.get("event_count"), int) or isinstance(contract.get("event_count"), bool) or contract.get("event_count") < 1:
        errors.append("Feature Buy折算审计event_count无效")
    bins = contract.get("base_bet_equivalent_bins")
    valid_bins = isinstance(bins, dict) and "0x" in bins and len(bins) >= 2
    if valid_bins:
        ordered_bins = []
        for label, boundary in bins.items():
            if not isinstance(boundary, dict) or not finite_number(boundary.get("lower")) or (
                boundary.get("upper") is not None and not finite_number(boundary.get("upper"))
            ):
                valid_bins = False
                break
            lower, upper = boundary["lower"], boundary.get("upper")
            if label == "0x":
                valid_bins = valid_bins and lower == 0 and upper == 0
            else:
                valid_bins = valid_bins and lower > 0 and (upper is None or upper > lower)
            ordered_bins.append((lower, upper, label))
        ordered_bins.sort(key=lambda value: value[0])
        for index, (lower, upper, label) in enumerate(ordered_bins):
            if upper is None and index != len(ordered_bins) - 1:
                valid_bins = False
            if index and ordered_bins[index - 1][1] is not None and lower < ordered_bins[index - 1][1]:
                valid_bins = False
    if not valid_bins:
        errors.append("Feature Buy折算审计必须密封含独立0x的实际有序倍率桶边界")
        return errors
    event_path = safe_evidence_path(evidence_root, contract.get("sealed_event_set_path"))
    if event_path is None or not event_path.is_file():
        errors.append("Feature Buy折算审计密封事件集文件不存在")
        return errors
    try:
        if sha(event_path) != contract.get("sealed_event_set_sha256"):
            errors.append("Feature Buy折算审计密封事件集hash失效")
        events = load_events(event_path)
        if not events:
            raise ValueError("密封事件集为空")
        counts = {label: 0 for label in bins}
        path_counts = {}
        primary_counts = {}
        primary_boundaries = primary.get("score_profile", {}).get("bin_boundaries_by_group", {}) if isinstance(primary, dict) and isinstance(primary.get("score_profile"), dict) else {}
        primary_groups = target_groups(primary) if isinstance(primary, dict) else {}
        seen_ids = set()
        for event in events:
            event_id = event_field(event, contract["event_id_field"])
            if not non_empty(event_id) or event_id in seen_ids:
                raise ValueError("event_id缺失或重复")
            seen_ids.add(event_id)
            win = event_field(event, contract["feature_total_win_field"])
            cost = event_field(event, contract["actual_purchase_cost_field"])
            base_bet = event_field(event, contract["normal_base_bet_field"])
            entry_source = event_field(event, contract["entry_source_field"])
            if not finite_number(win) or win < 0 or not finite_number(cost) or cost <= 0 or not finite_number(base_bet) or base_bet <= 0:
                raise ValueError("派奖、购买成本或基础投注字段无效")
            if entry_source != "feature_buy":
                raise ValueError("entry_source不是feature_buy")
            stage_path_id = event_field(event, "stage_path_id")
            if not isinstance(stage_path_id, str) or stage_path_id not in primary_groups:
                raise ValueError(f"stage_path_id未命中密封路径支持集: {stage_path_id}")
            path_counts[stage_path_id] = path_counts.get(stage_path_id, 0) + 1
            purchase_ratio = win / cost
            purchase_matches = []
            for label, boundary in primary_boundaries.get(stage_path_id, {}).items():
                lower, upper = boundary.get("lower"), boundary.get("upper")
                if label == "0x" and purchase_ratio == 0 or label != "0x" and purchase_ratio >= lower and (upper is None or purchase_ratio < upper):
                    purchase_matches.append(label)
            if len(purchase_matches) != 1:
                raise ValueError(f"购买成本回报{purchase_ratio}未唯一落入路径{stage_path_id}的密封桶")
            primary_counts.setdefault(stage_path_id, {label: 0 for label in primary_groups[stage_path_id]})[purchase_matches[0]] += 1
            ratio = win / base_bet
            matches = []
            for label, boundary in bins.items():
                lower, upper = boundary["lower"], boundary.get("upper")
                if label == "0x" and ratio == 0 or label != "0x" and ratio >= lower and (upper is None or ratio < upper):
                    matches.append(label)
            if len(matches) != 1:
                raise ValueError(f"折算回报{ratio}未唯一落入密封桶")
            counts[matches[0]] += 1
        if len(events) != contract.get("event_count"):
            errors.append("Feature Buy折算审计逐事件数与合同不一致")
        computed_stage = {path: path_counts.get(path, 0) / len(events) for path in primary_groups}
        if not isinstance(stage, dict) or stage.get("target") != computed_stage:
            errors.append("Feature Buy阶段路径目标未由同一事件集逐事件重算得到")
        separator = primary.get("score_profile", {}).get("group_separator", "::") if isinstance(primary, dict) and isinstance(primary.get("score_profile"), dict) else "::"
        computed_primary = {
            f"{path}{separator}{label}": count / path_counts[path]
            for path, bucket_counts in primary_counts.items()
            for label, count in bucket_counts.items()
            if path_counts.get(path)
        }
        primary_target = primary.get("target") if isinstance(primary, dict) else None
        if not isinstance(primary_target, dict) or set(primary_target) != set(computed_primary) or any(
            not finite_number(primary_target[key]) or abs(primary_target[key] - value) > 1e-12
            for key, value in computed_primary.items()
        ):
            errors.append("Feature Buy购买成本主回报目标未由同一事件集逐事件重算得到")
        computed = {label: count / len(events) for label, count in counts.items()} if events else {}
        target = item.get("target")
        if not isinstance(target, dict) or set(target) != set(computed) or any(
            not finite_number(target[label]) or abs(target[label] - computed[label]) > 1e-12 for label in computed
        ):
            errors.append("Feature Buy折算审计目标未由同一事件集逐事件重算得到")
    except (OSError, ValueError, KeyError, TypeError, ZeroDivisionError, json.JSONDecodeError) as exc:
        errors.append(f"Feature Buy折算审计逐事件重算失败: {exc}")
    return errors


def validate_trigger_entry_source_contract(item, active_nodes, evidence_root):
    if item.get("metric_id") != "trigger.entry_source_distribution":
        return []
    node_map = {
        node.get("node_id"): node
        for node in active_nodes
        if isinstance(node, dict) and isinstance(node.get("node_id"), str) and node.get("node_id")
    }
    nodes = source_nodes(item, node_map)
    if len(nodes) != 1 or nodes[0].get("mechanic_id") not in FEATURE_MECHANIC_IDS:
        return ["游戏内生入口来源指标必须唯一绑定一个活动Feature节点"]
    node = nodes[0]
    expected_sources = sorted(endogenous_entry_sources(node))
    errors = []
    if item.get("instance_dimensions") != {"entry_source_domain": "endogenous"}:
        errors.append("游戏内生入口来源指标必须使用entry_source_domain=endogenous专属作用域")
    if not expected_sources:
        return errors + ["没有游戏内生入口来源的Feature不得实例化入口来源评分"]
    if len(expected_sources) == 1:
        if item.get("status") != INACTIVE_METRIC_STATUS or item.get("inapplicability_reason_code") != "degenerate_reachable_support":
            errors.append("只有一个游戏内生入口来源时必须按退化支持标记不适用")
        return errors
    if item.get("status") == INACTIVE_METRIC_STATUS:
        return errors + ["存在两个及以上游戏内生入口来源时不得省略入口来源评分"]
    target = item.get("target")
    if not isinstance(target, dict) or set(target) != set(expected_sources):
        errors.append("游戏内生入口来源目标键必须与画像全部endogenous来源ID完全一致")
    if evidence_root is None:
        return errors + ["游戏内生入口来源指标缺少可信task_root"]
    event_path = safe_evidence_path(evidence_root, item.get("sealed_event_set_path"))
    if event_path is None or not event_path.is_file():
        return errors
    try:
        events = load_events(event_path)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return errors + [f"游戏内生入口来源事件集无法读取: {exc}"]
    counts = {source_id: 0 for source_id in expected_sources}
    for event in events:
        if not isinstance(event, dict):
            errors.append("游戏内生入口来源事件必须为对象")
            continue
        source_id = event.get("entry_source_id")
        if source_id not in counts:
            errors.append(f"游戏内生入口来源评分事件混入外生或未声明来源: {source_id}")
        else:
            counts[source_id] += 1
        if event.get("target_feature_node_id") != node.get("node_id"):
            errors.append(f"游戏内生入口来源事件未绑定目标Feature节点: {event.get('event_id')}")
    if events and isinstance(target, dict) and set(target) == set(counts):
        for source_id, count in counts.items():
            probability = count / len(events)
            if not finite_number(target.get(source_id)) or abs(target[source_id] - probability) > 1e-9:
                errors.append(f"游戏内生入口来源目标未由密封事件集逐事件复算: {source_id}")
    return errors


def award_chain_projection(award, claim):
    errors = []
    target = award.get("target")
    separator = award.get("score_profile", {}).get("group_separator", "::")
    groups = target_groups(award)
    if not isinstance(target, dict) or not groups or not non_empty(separator):
        return None, None, ["奖励结果目标不是有效的抽取状态条件分布"]
    probabilities = {
        group: {
            key.split(separator, 1)[1]: value
            for key, value in target.items()
            if isinstance(key, str) and key.startswith(group + separator)
        }
        for group in groups
    }
    initial_state = claim.get("initial_draw_state")
    max_steps = claim.get("max_draw_steps")
    transitions = claim.get("transition_by_state_outcome")
    if not isinstance(initial_state, str) or initial_state not in groups:
        errors.append("完整抽取链initial_draw_state未命中奖励结果状态组")
    if not isinstance(max_steps, int) or isinstance(max_steps, bool) or not 1 <= max_steps <= 10000:
        errors.append("完整抽取链max_draw_steps必须为1至10000的整数")
    if not isinstance(transitions, dict):
        errors.append("完整抽取链transition_by_state_outcome必须为对象")
        transitions = {}
    expected_transition_keys = {
        f"{state}{separator}{outcome}"
        for state, outcomes in probabilities.items()
        for outcome in outcomes
    }
    if set(transitions) != expected_transition_keys:
        errors.append("完整抽取链转移映射必须逐项覆盖全部抽取状态与结果")
    for key, transition in transitions.items():
        if not isinstance(transition, dict) or not isinstance(transition.get("terminal"), bool):
            errors.append(f"完整抽取链转移项缺少terminal布尔值: {key}")
            continue
        if transition["terminal"]:
            if set(transition) != {"terminal", "stage_path_id", "return_bucket"} or not non_empty(transition.get("stage_path_id")) or not non_empty(transition.get("return_bucket")):
                errors.append(f"完整抽取链终止项必须只含terminal、stage_path_id和return_bucket: {key}")
        elif set(transition) != {"terminal", "next_draw_state"} or transition.get("next_draw_state") not in groups:
            errors.append(f"完整抽取链非终止项必须只含terminal及有效next_draw_state: {key}")
    if errors:
        return None, None, errors

    frontier = {initial_state: 1.0}
    terminal_joint = {}
    for _ in range(max_steps):
        following = {}
        for state, state_probability in frontier.items():
            for outcome, conditional_probability in probabilities[state].items():
                if not finite_number(conditional_probability) or conditional_probability < 0:
                    errors.append(f"奖励结果条件概率无效: {state}{separator}{outcome}")
                    continue
                probability = state_probability * conditional_probability
                transition = transitions[f"{state}{separator}{outcome}"]
                if transition["terminal"]:
                    terminal_key = (transition["stage_path_id"], transition["return_bucket"])
                    terminal_joint[terminal_key] = terminal_joint.get(terminal_key, 0.0) + probability
                else:
                    next_state = transition["next_draw_state"]
                    following[next_state] = following.get(next_state, 0.0) + probability
        frontier = {state: probability for state, probability in following.items() if probability > 1e-15}
        if not frontier:
            break
    if frontier and sum(frontier.values()) > 1e-9:
        errors.append("完整抽取链在max_draw_steps后仍存在未终止概率质量")
    total_terminal = sum(terminal_joint.values())
    if abs(total_terminal - 1.0) > 1e-9:
        errors.append("完整抽取链终止概率合计不等于1")
    if errors:
        return None, None, errors
    stage_probabilities = {}
    for (stage_path, _), probability in terminal_joint.items():
        stage_probabilities[stage_path] = stage_probabilities.get(stage_path, 0.0) + probability
    return_probabilities = {}
    for (stage_path, bucket), probability in terminal_joint.items():
        stage_probability = stage_probabilities[stage_path]
        return_probabilities[(stage_path, bucket)] = probability / stage_probability if stage_probability > 0 else 0.0
    return stage_probabilities, return_probabilities, []


def validate_award_draw_return_ownership(item, active_nodes, items_by_key):
    metric_id = item.get("metric_id")
    if metric_id not in {"feature_cycle.stage_path_distribution", "feature_cycle.return_distribution_by_stage_path"}:
        return []
    node_map = {
        node.get("node_id"): node
        for node in active_nodes
        if isinstance(node, dict) and isinstance(node.get("node_id"), str) and node.get("node_id")
    }
    nodes = source_nodes(item, node_map)
    award_nodes = [node for node in nodes if node.get("mechanic_id") == "feature.award-draw"]
    derived = item.get("status") == INACTIVE_METRIC_STATUS and item.get("inapplicability_reason_code") == "deterministically_derived_from_primary"
    if not award_nodes:
        return ["非抽取型Feature路径指标不得声明由奖励抽取链确定性派生"] if derived else []
    if len(nodes) != 1 or len(award_nodes) != 1:
        return ["抽取型奖励路径Owner判定必须唯一绑定一个award-draw节点"]
    node = award_nodes[0]
    dimensions = item.get("instance_dimensions") if isinstance(item.get("instance_dimensions"), dict) else {}
    entry_source = dimensions.get("entry_source")
    deterministic = isinstance(entry_source, str) and award_return_is_deterministic_chain(node, entry_source)
    if deterministic and not derived:
        return ["完整奖励抽取随机链可复算路径与终局回报时，Feature路径指标必须标记为确定性派生"]
    if not deterministic:
        return ["抽取链外仍有随机奖励、非确定聚合或未承接玩家决策时必须保留Feature路径指标评分"] if derived else []

    award_candidates = [
        candidate
        for candidate in items_by_key.values()
        if isinstance(candidate, dict)
        and candidate.get("metric_id") == "award_draw.outcome_distribution_given_draw_state"
        and candidate.get("status") != INACTIVE_METRIC_STATUS
        and set(candidate.get("source_node_ids", [])) == {node.get("node_id")}
        and isinstance(candidate.get("instance_dimensions"), dict)
        and candidate["instance_dimensions"].get("entry_source") == entry_source
    ]
    if len(award_candidates) != 1:
        return ["抽取链派生Feature路径必须唯一绑定同入口来源的活动奖励结果指标"]
    proof = award_return_equivalence_proof(node, entry_source)
    valid_claims = [
        record.get("_claim")
        for record in item.get("inapplicability_evidence", [])
        if isinstance(record, dict)
        and isinstance(record.get("_claim"), dict)
        and record["_claim"].get("entry_source") == entry_source
        and record["_claim"].get("outcome_return_equivalence") == proof
    ]
    if len(valid_claims) != 1:
        return ["抽取链派生证据必须唯一绑定当前入口、七项证明、初始状态、完整转移和最大抽取步数"]
    stage_expected, return_expected, errors = award_chain_projection(award_candidates[0], valid_claims[0])
    if errors:
        return errors
    stage = items_by_key.get(same_metric_instance_key(item, "feature_cycle.stage_path_distribution"))
    stage_target = stage.get("target") if isinstance(stage, dict) else None
    if not isinstance(stage_target, dict):
        return ["抽取链派生缺少同实例Feature阶段路径目标"]
    if set(stage_target) != set(stage_expected):
        return ["Feature阶段路径目标支持集必须与完整奖励抽取链投影完全一致"]
    mismatched_paths = [
        path
        for path, probability in stage_target.items()
        if not finite_number(probability) or abs(probability - stage_expected[path]) > 1e-9
    ]
    if mismatched_paths:
        return [f"Feature阶段路径目标未由完整奖励抽取链确定性推出: {','.join(sorted(mismatched_paths))}"]
    if metric_id == "feature_cycle.stage_path_distribution":
        return []

    separator = item.get("score_profile", {}).get("group_separator", "::")
    return_target = item.get("target")
    if not isinstance(return_target, dict):
        return ["抽取链派生缺少Feature路径回报目标"]
    target_by_path = {}
    for key, probability in return_target.items():
        if not isinstance(key, str) or separator not in key:
            return ["Feature路径回报目标键缺少阶段路径与回报桶分隔"]
        path, bucket = key.split(separator, 1)
        target_by_path.setdefault(path, {})[bucket] = probability
    expected_by_path = {}
    for (path, bucket), probability in return_expected.items():
        expected_by_path.setdefault(path, {})[bucket] = probability
    if set(target_by_path) != set(expected_by_path) or any(
        set(target_by_path[path]) != set(expected_by_path[path])
        for path in set(target_by_path) & set(expected_by_path)
    ):
        return ["Feature路径回报目标支持集必须与完整奖励抽取链投影完全一致"]
    mismatched_returns = [
        path
        for path, buckets in target_by_path.items()
        if any(
            not finite_number(probability) or abs(probability - expected_by_path[path][bucket]) > 1e-9
            for bucket, probability in buckets.items()
        )
    ]
    return [f"Feature路径回报目标未由完整奖励抽取链确定性推出: {','.join(sorted(mismatched_returns))}"] if mismatched_returns else []


def validate_feature_duration_contract(item, active_nodes):
    if item.get("metric_id") != "feature_cycle.duration_distribution":
        return []
    node_map = {
        node.get("node_id"): node
        for node in active_nodes
        if isinstance(node, dict) and isinstance(node.get("node_id"), str) and node.get("node_id")
    }
    nodes = source_nodes(item, node_map)
    bonus_nodes = [node for node in nodes if node.get("mechanic_id") == BONUS_SEQUENCE_MECHANIC_ID]
    if bonus_nodes:
        if len(nodes) != 1 or len(bonus_nodes) != 1:
            return ["Bonus Sequence时长必须唯一绑定一个顶层编排节点"]
        errors = []
        if item.get("status") != INACTIVE_METRIC_STATUS or item.get("inapplicability_reason_code") != "deterministically_derived_from_primary":
            errors.append("Bonus Sequence完整时长必须由阶段路径与动作次数投影确定性派生")
        projection_rows = bonus_nodes[0].get("attributes", {}).get("stage_action_count_projection", {}).get("path_action_counts", [])
        expected = {
            row.get("path_id"): row.get("primary_action_count")
            for row in projection_rows
            if isinstance(row, dict) and non_empty(row.get("path_id"))
        }
        claims = [
            record.get("expected_value")
            for record in item.get("inapplicability_evidence", [])
            if isinstance(record, dict) and isinstance(record.get("expected_value"), dict)
        ]
        mappings = [
            claim.get("projection", {}).get("source_field_to_target_field")
            for claim in claims
            if claim.get("projection", {}).get("projector_id") == "stage_path_to_primary_action_count_v1"
        ]
        if len(mappings) != 1 or not isinstance(mappings[0], dict) or set(mappings[0]) != set(expected) or any(
            integer_token(target_field) != expected[path_id]
            for path_id, target_field in mappings[0].items()
        ):
            errors.append("Bonus Sequence时长派生映射必须与画像逐路径主要动作次数完全一致")
        return errors
    deterministic_proof = {
        "one_to_one_with_initial_grant": True,
        "early_termination_possible": False,
        "variable_consumption_possible": False,
        "counter_reset_possible": False,
        "cross_step_dependency_possible": False,
    }
    deterministic = bool(nodes) and all(
        (
            node.get("mechanic_id") == "feature.free-spin"
            and not semantic_truthy(node.get("attributes", {}).get("retrigger_rule"))
            and node.get("attributes", {}).get("duration_determinism") == deterministic_proof
        )
        or (
            node.get("mechanic_id") == "feature.respin"
            and not semantic_truthy(node.get("attributes", {}).get("extension_rule"))
            and node.get("attributes", {}).get("duration_determinism") == deterministic_proof
        )
        for node in nodes
    )
    if deterministic:
        if item.get("status") != INACTIVE_METRIC_STATUS or item.get("inapplicability_reason_code") != "deterministically_derived_from_primary":
            return ["已证明最终次数与初始赠送一一映射的Feature时长必须标记为确定性派生"]
    elif item.get("status") == INACTIVE_METRIC_STATUS and item.get("inapplicability_reason_code") == "deterministically_derived_from_primary":
        return ["存在非确定性续命、停止或跨步依赖时Feature时长不得伪造为确定性派生"]
    return []


def validate_feature_stage_path_domain(item, active_nodes):
    if item.get("metric_id") != "feature_cycle.stage_path_distribution":
        return []
    node_map = {
        node.get("node_id"): node
        for node in active_nodes
        if isinstance(node, dict) and isinstance(node.get("node_id"), str) and node.get("node_id")
    }
    nodes = source_nodes(item, node_map)
    feature_nodes = [node for node in nodes if node.get("mechanic_id") in FEATURE_MECHANIC_IDS]
    if len(nodes) != 1 or len(feature_nodes) != 1:
        return ["Feature阶段路径指标必须唯一绑定一个Feature节点"]
    path_ids = feature_nodes[0].get("attributes", {}).get("path_signature_definition", {}).get("path_id_domain")
    target = item.get("target")
    if not isinstance(path_ids, list) or not isinstance(target, dict) or set(target) != set(path_ids):
        return ["Feature阶段路径目标键必须与画像path_id_domain完全一致"]
    return []


def validate_cascade_multiplier_ownership(item, active_nodes):
    metric_id = item.get("metric_id")
    controlled_metrics = {
        "multiplier.occurrence_rate",
        "multiplier.application_rate_given_occurrence",
        "multiplier.effective_value_distribution",
        "cascade_multiplier.dependence_by_depth",
    }
    if metric_id not in controlled_metrics:
        return []
    node_map = {
        node.get("node_id"): node
        for node in active_nodes
        if isinstance(node, dict) and isinstance(node.get("node_id"), str) and node.get("node_id")
    }
    nodes = source_nodes(item, node_map)
    multipliers = [
        node for node in nodes
        if node.get("mechanic_id") == "modifier.win-multiplier"
        and node.get("attributes", {}).get("progression_driver") == "cascade_depth"
    ]
    if not multipliers:
        return []
    if len(multipliers) != 1:
        return [f"Cascade倍率Owner判定必须唯一绑定一个倍率节点: {metric_id}"]
    randomness = multipliers[0].get("attributes", {}).get("same_depth_multiplier_randomness")
    if randomness is False:
        if item.get("status") != INACTIVE_METRIC_STATUS or item.get("inapplicability_reason_code") != "deterministically_derived_from_primary":
            return [f"同一Cascade深度唯一确定完整倍率状态时必须由深度分布派生且不重复计分: {metric_id}"]
    elif randomness is True and metric_id == "cascade_multiplier.dependence_by_depth":
        if item.get("status") == INACTIVE_METRIC_STATUS and item.get("inapplicability_reason_code") == "deterministically_derived_from_primary":
            return ["同一Cascade深度仍有倍率随机性时不得把依赖残差声明为深度确定性派生"]
    return []


def validate_value_symbol_multiplier_ownership(item, active_nodes):
    pair = {
        "value_symbol.assignment_value_distribution",
        "multiplier.effective_value_distribution",
    }
    metric_id = item.get("metric_id")
    if metric_id not in pair:
        return []
    source_metric_ids = set()
    for record in item.get("inapplicability_evidence", []):
        claim = record.get("_claim") if isinstance(record, dict) else None
        sources = claim.get("source_metric_instances") if isinstance(claim, dict) else None
        if isinstance(sources, list):
            source_metric_ids.update(source.get("metric_id") for source in sources if isinstance(source, dict))
    counterpart = next(iter(pair - {metric_id}))
    source_node_ids = set(item.get("source_node_ids", []))
    bindings = [
        binding
        for _, binding in value_symbol_multiplier_bindings(active_nodes)
        if (
            metric_id == "value_symbol.assignment_value_distribution"
            and binding.get("value_symbol_node_id") in source_node_ids
            or metric_id == "multiplier.effective_value_distribution"
            and binding.get("multiplier_node_id") in source_node_ids
        )
    ]
    qualified = [
        binding for binding in bindings
        if binding.get("event_pairing_bijective") is True
        and binding.get("all_assignments_realized_exactly_once") is True
        and binding.get("same_event_universe") is True
        and binding.get("no_additional_multiplier_source") is True
        and binding.get("mapping_total_and_bijective") is True
        and binding.get("primary_owner_metric_id") in pair
    ]
    owners = {binding["primary_owner_metric_id"] for binding in qualified}
    if len(owners) > 1:
        return ["同一Value Symbol赋值与生效倍率实例声明了冲突的主Owner"]
    if counterpart in source_metric_ids and not qualified:
        return [f"Value Symbol赋值与生效倍率默认分别评分，缺少完整同域一一兑现绑定时不得互相派生: {metric_id}"]
    if owners and metric_id not in owners:
        if item.get("status") != INACTIVE_METRIC_STATUS or item.get("inapplicability_reason_code") != "deterministically_derived_from_primary":
            return [f"Value Symbol赋值与生效倍率绑定已指定唯一主Owner，非Owner项必须确定性派生: {metric_id}"]
    if owners == {metric_id} and counterpart in source_metric_ids:
        return [f"Value Symbol赋值与生效倍率绑定已指定当前指标为主Owner，不得反向由非Owner派生: {metric_id}"]
    return []


def validate_value_symbol_upgrade_metric_bindings(items, active_nodes):
    errors = []
    states_by_id = {
        node.get("attributes", {}).get("state_id"): node
        for node in active_nodes
        if node.get("mechanic_id") == "state.persistent-state"
        and non_empty(node.get("attributes", {}).get("state_id"))
    }
    for value_node in active_nodes:
        attributes = value_node.get("attributes", {})
        if value_node.get("mechanic_id") != "award.value-symbol" or not semantic_truthy(attributes.get("value_upgrade_rule")):
            continue
        binding = attributes.get("value_upgrade_state_binding")
        if not isinstance(binding, dict):
            continue
        value_node_id = value_node.get("node_id")
        assignment_items = [
            item for item in items
            if isinstance(item, dict)
            and item.get("metric_id") == "value_symbol.assignment_value_distribution"
            and value_node_id in item.get("source_node_ids", [])
        ]
        if not assignment_items:
            errors.append(f"Value Symbol升级节点缺少初始赋值指标实例: {value_node_id}")
        if any(
            item.get("status") == INACTIVE_METRIC_STATUS
            and item.get("inapplicability_reason_code") == "deterministically_derived_from_primary"
            for item in assignment_items
        ):
            errors.append(f"Value Symbol存在升级时初始赋值不得由最终倍率反向替代: {value_node_id}")
        initial_event = binding.get("initial_assignment_semantic_event_set_id")
        active_assignments = [item for item in assignment_items if item.get("status") != INACTIVE_METRIC_STATUS]
        if any(item.get("sealed_event_set_id") != initial_event for item in active_assignments):
            errors.append(f"Value Symbol初始赋值活动实例未密封到独立初始赋值事件集: {value_node_id}")

        state = states_by_id.get(binding.get("persistent_state_id"))
        if not isinstance(state, dict):
            continue
        state_node_id = state.get("node_id")
        shared_event = binding.get("shared_semantic_event_set_id")
        required = (
            (
                "persistent_state.ordered_value_distribution",
                {"state_id": binding.get("persistent_state_id"), "observation_point": binding.get("state_observation_point")},
                "升级检查前当前值",
            ),
            (
                "persistent_state.ordered_transition_distribution",
                {"state_id": binding.get("persistent_state_id"), "transition_event": binding.get("state_transition_event")},
                "逐次升级转移",
            ),
        )
        for metric_id, dimensions, label in required:
            matches = [
                item for item in items
                if isinstance(item, dict)
                and item.get("metric_id") == metric_id
                and item.get("source_node_ids") == [state_node_id]
                and item.get("instance_dimensions") == dimensions
            ]
            if len(matches) != 1:
                errors.append(f"Value Symbol升级绑定未命中唯一{label}指标实例: {value_node_id}")
                continue
            metric = matches[0]
            if metric.get("status") == INACTIVE_METRIC_STATUS:
                errors.append(f"Value Symbol升级绑定的{label}指标必须真实活动: {value_node_id}")
            elif metric.get("sealed_event_set_id") != shared_event:
                errors.append(f"Value Symbol升级绑定的{label}指标未使用共享升级检查事件集: {value_node_id}")
    return errors


def validate_value_symbol_multiplier_derivation(item, source_items, active_nodes):
    pair = {
        "value_symbol.assignment_value_distribution",
        "multiplier.effective_value_distribution",
    }
    metric_id = item.get("metric_id")
    if metric_id not in pair:
        return []
    counterpart = next(iter(pair - {metric_id}))
    matching_sources = [source for source in source_items if source.get("metric_id") == counterpart]
    if not matching_sources:
        return []
    if len(source_items) != 1 or len(matching_sources) != 1:
        return [f"Value Symbol与倍率单Owner派生必须只引用唯一对侧活动指标: {metric_id}"]
    source = matching_sources[0]
    requirements = item.get("conditional_derivation_requirements")
    requirement = next((value for value in requirements if value.get("source_metric_id") == counterpart), None) if isinstance(requirements, list) else None
    if not isinstance(requirement, dict):
        return [f"Value Symbol与倍率派生缺少目录conditional_derivation_requirements: {metric_id}"]
    bindings = [binding for _, binding in value_symbol_multiplier_bindings(active_nodes)]
    item_nodes = set(item.get("source_node_ids", []))
    source_nodes_ids = set(source.get("source_node_ids", []))
    qualified = [
        binding for binding in bindings
        if binding.get("value_symbol_node_id") in item_nodes | source_nodes_ids
        and binding.get("multiplier_node_id") in item_nodes | source_nodes_ids
        and binding.get("primary_owner_metric_id") == counterpart
    ]
    if len(qualified) != 1:
        return [f"Value Symbol与倍率派生未命中唯一画像Owner绑定: {metric_id}"]
    binding = qualified[0]
    errors = []
    if item.get("owner_derivation_binding") != binding:
        errors.append(f"指标合同owner_derivation_binding未与画像绑定逐字段一致: {metric_id}")
    if set(binding) != set(requirement.get("required_binding_fields", [])):
        errors.append(f"Owner绑定字段未满足指标目录要求: {metric_id}")
    if binding.get("primary_owner_metric_id") != requirement.get("required_primary_owner_metric_id"):
        errors.append(f"Owner绑定主指标方向与目录要求不一致: {metric_id}")
    mapping = parsed_numeric_mapping(binding.get("value_to_effective_multiplier_mapping", {}))
    if mapping is None:
        return errors + [f"Owner绑定值映射无法解析为非负有序值: {metric_id}"]
    source_distribution = distribution_positions(source)
    item_distribution = distribution_positions(item)
    if not isinstance(source_distribution, dict) or not isinstance(item_distribution, dict):
        return errors + [f"Value Symbol与倍率派生双方目标缺少实际值位置: {metric_id}"]
    projected = {}
    if metric_id == "multiplier.effective_value_distribution":
        for value, probability in source_distribution.items():
            destination = mapping.get(float(value))
            if destination is None:
                errors.append(f"Value Symbol赋值未被倍率映射完整覆盖: {value}")
                continue
            projected[destination] = projected.get(destination, 0) + probability
    else:
        inverse = {value: key for key, value in mapping.items()}
        for value, probability in source_distribution.items():
            destination = inverse.get(float(value))
            if destination is None:
                errors.append(f"倍率值未被Value Symbol反向映射完整覆盖: {value}")
                continue
            projected[destination] = projected.get(destination, 0) + probability
    if set(projected) != set(item_distribution) or any(
        not close_probability(projected[value], item_distribution[value])
        for value in set(projected) & set(item_distribution)
    ):
        errors.append(f"非Owner目标未由主Owner目标和完整值映射精确复算: {metric_id}")
    return errors


def validate_cascade_multiplier_derivation(item, source_items, active_nodes):
    controlled = {
        "multiplier.occurrence_rate",
        "multiplier.application_rate_given_occurrence",
        "multiplier.effective_value_distribution",
        "cascade_multiplier.dependence_by_depth",
    }
    metric_id = item.get("metric_id")
    if metric_id not in controlled:
        return []
    depth_sources = [source for source in source_items if source.get("metric_id") == "cascade.depth_distribution"]
    if not depth_sources:
        return []
    if len(source_items) != 1 or len(depth_sources) != 1:
        return [f"Cascade确定倍率派生必须只引用唯一深度Owner: {metric_id}"]
    source = depth_sources[0]
    source_ids = set(item.get("source_node_ids", [])) | set(source.get("source_node_ids", []))
    bindings = [
        node.get("attributes", {}).get("cascade_depth_multiplier_binding")
        for node in active_nodes
        if node.get("mechanic_id") == "modifier.win-multiplier"
        and node.get("node_id") in source_ids
        and isinstance(node.get("attributes", {}).get("cascade_depth_multiplier_binding"), dict)
    ]
    if len(bindings) != 1:
        return [f"Cascade确定倍率派生未命中唯一结构化映射: {metric_id}"]
    binding = bindings[0]
    errors = []
    if item.get("cascade_derivation_binding") != binding:
        errors.append(f"指标合同cascade_derivation_binding未与画像逐字段一致: {metric_id}")
    depth_distribution = integer_distribution(source)
    if depth_distribution is None:
        return errors + [f"Cascade深度Owner缺少实际非负整数位置: {metric_id}"]
    raw_mapping = binding.get("terminal_depth_to_step_states", {})
    mapping = parsed_integer_key_mapping(raw_mapping)
    if mapping is None or set(mapping) != set(depth_distribution):
        return errors + [f"Cascade确定倍率映射未完整覆盖深度Owner支持集: {metric_id}"]
    step_states, step_exposure = {}, {}
    for depth, probability in depth_distribution.items():
        states = mapping.get(depth, [])
        if len(states) != depth + 1:
            errors.append(f"Cascade确定倍率映射未覆盖终局深度全部结算步骤: {depth}")
            continue
        for state in states:
            step = state.get("settlement_step_index")
            step_exposure[step] = step_exposure.get(step, 0) + probability
            step_states[step] = state
    total_exposure = sum(step_exposure.values())
    if total_exposure <= 0:
        return errors + [f"Cascade确定倍率映射没有正结算步骤暴露: {metric_id}"]
    occurred_exposure = sum(
        exposure for step, exposure in step_exposure.items()
        if step_states[step].get("multiplier_occurred") is True
    )
    applied_exposure = sum(
        exposure for step, exposure in step_exposure.items()
        if step_states[step].get("multiplier_applied") is True
    )
    if metric_id == "multiplier.occurrence_rate":
        expected = occurred_exposure / total_exposure
        if not close_probability(item.get("target"), expected):
            errors.append("倍率出现率未由Cascade深度与逐步确定状态精确复算")
        return errors
    if metric_id == "multiplier.application_rate_given_occurrence":
        if occurred_exposure <= 0:
            errors.append("Cascade确定映射没有倍率出现事件，无法派生出现后应用率")
        elif not close_probability(item.get("target"), applied_exposure / occurred_exposure):
            errors.append("倍率出现后应用率未由Cascade逐步确定状态精确复算")
        return errors
    state_exposure = {}
    value_exposure = {}
    for step, exposure in step_exposure.items():
        state = step_states[step]
        state_id = state.get("multiplier_state_id")
        state_exposure[state_id] = state_exposure.get(state_id, 0) + exposure
        if state.get("multiplier_applied") is True:
            value = float(state.get("effective_multiplier"))
            value_exposure[value] = value_exposure.get(value, 0) + exposure
    if metric_id == "multiplier.effective_value_distribution":
        actual = distribution_positions(item)
        expected = {value: exposure / applied_exposure for value, exposure in value_exposure.items()} if applied_exposure > 0 else {}
        if not expected or not isinstance(actual, dict) or set(actual) != set(expected) or any(
            not close_probability(actual[value], probability) for value, probability in expected.items()
        ):
            errors.append("生效倍率值分布未由Cascade逐步确定状态精确复算")
        return errors

    groups = target_groups(item)
    parsed = {group: integer_token(group) for group in groups}
    if set(parsed.values()) != set(step_exposure) or len(set(parsed.values())) != len(parsed):
        errors.append("Cascade倍率依赖残差组未完整覆盖实际结算步骤")
        return errors
    unconditional = {state: exposure / total_exposure for state, exposure in state_exposure.items()}
    for group, step in parsed.items():
        values = group_target_values(item, group)
        if set(values) != set(unconditional):
            errors.append(f"Cascade倍率依赖残差组未完整覆盖实际倍率状态域: {group}")
            continue
        actual_state = step_states[step].get("multiplier_state_id")
        expected = {state: (1.0 if state == actual_state else 0.0) - probability for state, probability in unconditional.items()}
        if any(not close_probability(values[state], expected[state]) for state in expected):
            errors.append(f"Cascade倍率依赖残差未由深度边际与确定状态精确复算: {group}")
    actual_weights = (evaluation_profile(item) or {}).get("group_weights")
    expected_weights = {group: step_exposure[step] / total_exposure for group, step in parsed.items()}
    if not weights_match(actual_weights, expected_weights):
        errors.append("Cascade倍率依赖group_weights未由原版逐步暴露精确复算")
    return errors


def sealed_scope_events(scope, evidence_root, label, errors, identity_field="settlement_step_id"):
    path = safe_evidence_path(evidence_root, scope.get("event_set_path")) if isinstance(scope, dict) else None
    if path is None or not path.is_file():
        errors.append(f"{label}密封事件集文件不存在")
        return {}
    if not is_sha256(scope.get("event_set_sha256")) or sha(path) != scope.get("event_set_sha256"):
        errors.append(f"{label}密封事件集hash失效")
        return {}
    try:
        count = sealed_event_count(path, scope.get("sample_unit"), scope.get("dimensions"))
        if count != scope.get("event_count"):
            errors.append(f"{label}密封事件数与声明不一致")
            return {}
        events = load_events(path)
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        errors.append(f"{label}密封事件集格式无效: {exc}")
        return {}
    identities = [event.get(identity_field) for event in events]
    if any(not non_empty(value) for value in identities):
        errors.append(f"{label}存在缺失{identity_field}的结算步骤")
        return {}
    if len(identities) != len(set(identities)):
        errors.append(f"{label}的{identity_field}必须唯一")
        return {}
    return dict(zip(identities, events))


def step_return_owner_metric_id(event, active_node_map, label, errors):
    source_ids = event.get("source_node_ids") if isinstance(event, dict) else None
    if (
        not isinstance(source_ids, list)
        or not source_ids
        or not all(isinstance(node_id, str) and node_id for node_id in source_ids)
        or len(source_ids) != len(set(source_ids))
    ):
        errors.append(f"{label}缺少唯一非空source_node_ids")
        return None
    unknown = sorted(set(source_ids) - set(active_node_map))
    if unknown:
        errors.append(f"{label}引用未知source_node_ids: {','.join(unknown)}")
        return None
    mechanic_ids = {active_node_map[node_id].get("mechanic_id") for node_id in source_ids}
    if not mechanic_ids & STEP_RETURN_SETTLEMENT_MECHANICS:
        errors.append(f"{label}未关联任何完整步骤结算玩法节点")
        return None
    if "evolution.cascade" in mechanic_ids:
        return STEP_RETURN_OWNER_PRIORITY[0]
    if {"board.variable-grid", "settlement.ways"} <= mechanic_ids:
        return STEP_RETURN_OWNER_PRIORITY[1]
    if {"board.fixed-grid", "settlement.ways", "settlement.effective-ways-capacity"} <= mechanic_ids:
        return STEP_RETURN_OWNER_PRIORITY[2]
    return STEP_RETURN_OWNER_PRIORITY[3]


def validate_step_return_owner_partitions(
    profile,
    contract,
    active_items_by_key,
    scope_instances,
    active_nodes,
    task_root_path,
):
    if profile.get("schema_version") != "1.2" or contract.get("schema_version") != "1.3":
        return []
    errors = []
    profile_partitions = profile.get("step_return_partitions")
    contract_partitions = contract.get("step_return_owner_partitions")
    if not isinstance(profile_partitions, list) or not profile_partitions:
        errors.append("game_profile 1.2缺少step_return_partitions")
        profile_partitions = []
    if not isinstance(contract_partitions, list) or not contract_partitions:
        errors.append("metric_contract 1.3缺少step_return_owner_partitions")
        contract_partitions = []
    if task_root_path is None:
        errors.append("步骤回报Owner分区校验缺少可信task_root")
        return sorted(dict.fromkeys(errors))

    def partition_map(values, label):
        result = {}
        for position, item in enumerate(values, 1):
            if not isinstance(item, dict):
                errors.append(f"{label}第{position}项不是对象")
                continue
            partition_id = item.get("partition_id")
            if not non_empty(partition_id) or partition_id in result:
                errors.append(f"{label} partition_id缺失或重复: {partition_id}")
                continue
            result[partition_id] = item
        return result

    profile_by_id = partition_map(profile_partitions, "game_profile.step_return_partitions")
    contract_by_id = partition_map(contract_partitions, "metric_contract.step_return_owner_partitions")
    if set(profile_by_id) != set(contract_by_id):
        errors.append("步骤回报Owner分区ID集合不一致")

    scopes_by_id = {}
    for scope in scope_instances if isinstance(scope_instances, list) else []:
        if isinstance(scope, dict) and non_empty(scope.get("scope_instance_id")):
            scopes_by_id.setdefault(scope["scope_instance_id"], []).append(scope)
    active_node_map = {
        node.get("node_id"): node
        for node in active_nodes
        if isinstance(node, dict) and non_empty(node.get("node_id"))
    }
    active_owners = {
        metric_instance_key(item): item
        for item in active_items_by_key.values()
        if isinstance(item, dict)
        and item.get("status") != INACTIVE_METRIC_STATUS
        and item.get("metric_id") in STEP_RETURN_OWNER_PRIORITY
    }
    binding_counts = {key: 0 for key in active_owners}
    evidence_root = task_evidence_root(task_root_path)
    event_cache = {}
    priority = {metric_id: index for index, metric_id in enumerate(STEP_RETURN_OWNER_PRIORITY)}

    def exact_scope(scope_id, label):
        matches = scopes_by_id.get(scope_id, [])
        if len(matches) != 1:
            errors.append(f"{label}必须唯一引用scope_instance: {scope_id}")
            return None
        return matches[0]

    def scope_events(scope, label):
        scope_id = scope.get("scope_instance_id")
        if scope_id not in event_cache:
            event_cache[scope_id] = sealed_scope_events(scope, evidence_root, label, errors)
        return event_cache[scope_id]

    for partition_id in sorted(set(profile_by_id) & set(contract_by_id)):
        profile_partition = profile_by_id[partition_id]
        contract_partition = contract_by_id[partition_id]
        if (
            profile_partition.get("partition_rule_id") != "complete-step-return-owner-v1"
            or profile_partition.get("step_identity_field") != "settlement_step_id"
        ):
            errors.append(f"步骤回报Owner分区规则无效: {partition_id}")
        universe_scope = exact_scope(
            profile_partition.get("universe_scope_instance_id"),
            f"步骤回报父全集{partition_id}",
        )
        universe_events = scope_events(universe_scope, f"步骤回报父全集{partition_id}") if universe_scope else {}
        expected_owner_by_event = {
            step_id: step_return_owner_metric_id(
                event,
                active_node_map,
                f"步骤回报父事件{partition_id}/{step_id}",
                errors,
            )
            for step_id, event in universe_events.items()
        }
        owner_bindings = contract_partition.get("owner_bindings")
        if not isinstance(owner_bindings, list) or not owner_bindings:
            errors.append(f"步骤回报Owner分区缺少owner_bindings: {partition_id}")
            owner_bindings = []
        assigned = {}
        for position, binding in enumerate(owner_bindings, 1):
            if not isinstance(binding, dict):
                errors.append(f"步骤回报Owner绑定不是对象: {partition_id}/{position}")
                continue
            reference = binding.get("metric_instance")
            if not isinstance(reference, dict):
                errors.append(f"步骤回报Owner绑定缺少metric_instance: {partition_id}/{position}")
                continue
            key = metric_instance_key(reference)
            metric_id = key[0]
            if metric_id not in STEP_RETURN_OWNER_PRIORITY:
                errors.append(f"步骤回报Owner绑定引用非四类指标: {format_instance(key)}")
            active_item = active_owners.get(key)
            if active_item is None:
                errors.append(f"步骤回报Owner绑定未命中活动指标实例: {format_instance(key)}")
            else:
                binding_counts[key] += 1
            subset_scope = exact_scope(
                binding.get("subset_scope_instance_id"),
                f"步骤回报Owner子集{partition_id}/{format_instance(key)}",
            )
            if subset_scope is None:
                continue
            if active_item is not None and any(
                active_item.get(metric_field) != subset_scope.get(scope_field)
                for metric_field, scope_field in (
                    ("sealed_event_set_id", "semantic_event_set_id"),
                    ("sealed_event_set_path", "event_set_path"),
                    ("sealed_event_set_sha256", "event_set_sha256"),
                    ("sealed_event_count", "event_count"),
                )
            ):
                errors.append(f"步骤回报Owner指标实例与子集密封事件集不一致: {format_instance(key)}")
            subset_events = scope_events(
                subset_scope,
                f"步骤回报Owner子集{partition_id}/{format_instance(key)}",
            )
            outside = sorted(set(subset_events) - set(universe_events))
            if outside:
                errors.append(
                    f"步骤回报Owner子集超出父全集: {partition_id}/{format_instance(key)} / "
                    f"settlement_step_id={','.join(outside)}"
                )
            for step_id in sorted(set(subset_events) & set(universe_events)):
                if step_id in assigned:
                    pair = sorted(
                        (assigned[step_id], key),
                        key=lambda value: (priority.get(value[0], len(priority)), format_instance(value)),
                    )
                    errors.append(
                        f"步骤回报Owner子集不互斥: {partition_id}/settlement_step_id={step_id} / "
                        f"高优先级Owner={format_instance(pair[0])} / 低优先级Owner={format_instance(pair[1])}"
                    )
                else:
                    assigned[step_id] = key
                expected_owner = expected_owner_by_event.get(step_id)
                if expected_owner is not None and expected_owner != metric_id:
                    errors.append(
                        f"步骤回报Owner优先级复算不一致: {partition_id}/settlement_step_id={step_id} / "
                        f"期望{expected_owner} / 实际{metric_id}"
                    )
                event = universe_events[step_id]
                event_source_ids = set(event.get("source_node_ids", []))
                if not set(key[1]) <= event_source_ids:
                    errors.append(
                        f"步骤回报Owner实例来源节点与父事件不一致: {partition_id}/settlement_step_id={step_id} / "
                        f"{format_instance(key)}"
                    )
                event_dimensions = event.get("dimensions")
                if not isinstance(event_dimensions, dict) or any(
                    event_dimensions.get(name) != value for name, value in key[2]
                ):
                    errors.append(
                        f"步骤回报Owner实例维度与父事件不一致: {partition_id}/settlement_step_id={step_id} / "
                        f"{format_instance(key)}"
                    )
        missing = sorted(set(universe_events) - set(assigned))
        if missing:
            errors.append(
                f"步骤回报Owner子集并集不完整: {partition_id} / 缺少settlement_step_id={','.join(missing)}"
            )

    for key, count in sorted(binding_counts.items(), key=lambda item: instance_sort_key(item[0])):
        if count == 0:
            errors.append(f"活动步骤回报Owner指标实例未绑定: {format_instance(key)}")
        elif count > 1:
            errors.append(f"活动步骤回报Owner指标实例重复绑定: {format_instance(key)} / {count}次")
    return sorted(dict.fromkeys(errors))


def validate_active_owner_conflicts(items, catalog, active_nodes):
    errors = []
    active = [
        item for item in items
        if isinstance(item, dict) and item.get("kind") == "score" and item.get("status") != INACTIVE_METRIC_STATUS
    ]
    node_map = {
        node.get("node_id"): node
        for node in active_nodes
        if isinstance(node, dict) and isinstance(node.get("node_id"), str) and node.get("node_id")
    }

    def dimensions_compatible(left, right):
        left_dimensions = left.get("instance_dimensions") if isinstance(left.get("instance_dimensions"), dict) else {}
        right_dimensions = right.get("instance_dimensions") if isinstance(right.get("instance_dimensions"), dict) else {}
        return all(left_dimensions[name] == right_dimensions[name] for name in set(left_dimensions) & set(right_dimensions))

    def source_event_ids(item):
        return {
            event_id
            for node in source_nodes(item, node_map)
            for event_id in node.get("semantic_event_set_ids", [])
            if isinstance(event_id, str) and event_id
        }

    def persistent_state_ids(item):
        result = set()
        for node in source_nodes(item, node_map):
            attributes = node.get("attributes", {})
            if node.get("mechanic_id") == "state.persistent-state" and isinstance(attributes.get("state_id"), str):
                result.add(attributes["state_id"])
            for field in ("persistent_state_ids", "persistent_state_id", "progression_state_id"):
                result.update(value for value in list_value(attributes.get(field)) if isinstance(value, str) and value)
        return result

    def overlaps(left, right):
        if not dimensions_compatible(left, right):
            return False
        if non_empty(left.get("scope")) and left.get("scope") == right.get("scope"):
            return True
        for field in ("sealed_event_set_id", "sealed_event_set_path", "sealed_event_set_sha256"):
            if non_empty(left.get(field)) and left.get(field) == right.get(field):
                return True
        if source_event_ids(left) & source_event_ids(right):
            return True
        return bool(persistent_state_ids(left) & persistent_state_ids(right))

    for index, left in enumerate(active):
        left_id = left.get("metric_id")
        exclusive = set(catalog["metrics"].get(left_id, {}).get("relationships", {}).get("exclusive_with", []))
        exclusive.update(next(iter(pair - {left_id})) for pair in EXCLUSIVE_METRIC_PAIRS if left_id in pair)
        for right in active[index + 1:]:
            right_id = right.get("metric_id")
            if right_id in exclusive and overlaps(left, right):
                errors.append(f"同一语义作用域存在互斥评分Owner: {format_instance(metric_instance_key(left))},{format_instance(metric_instance_key(right))}")
    return errors


def validate_new_task_identity(profile, contract, input_manifest, authority):
    errors = []
    documents = {
        "game_profile": profile,
        "metric_contract": contract,
        "input_manifest": input_manifest,
        "parameter_authority": authority,
    }
    task_ids = {name: value.get("task_id") for name, value in documents.items() if isinstance(value, dict)}
    if len(task_ids) != len(documents) or any(not non_empty(value) for value in task_ids.values()) or len(set(task_ids.values())) != 1:
        errors.append("新任务四份阶段1/2文件task_id缺失或不一致")
    for name, value in documents.items():
        if not isinstance(value, dict) or value.get("status") != COMPLETE_STATUS:
            errors.append(f"新任务完成态无效: {name}={value.get('status') if isinstance(value, dict) else '非对象'}")
    scopes = {
        name: value.get("scope") if isinstance(value, dict) and isinstance(value.get("scope"), dict) else {}
        for name, value in documents.items()
        if name != "parameter_authority"
    }
    for field in ("game_code", "mode", "rtp_group"):
        values = {name: scope.get(field) for name, scope in scopes.items()}
        if any(not non_empty(value) for value in values.values()) or len(set(values.values())) != 1:
            errors.append(f"新任务game_profile、metric_contract与input_manifest作用域{field}缺失或不一致")
    rtp_group = scopes.get("metric_contract", {}).get("rtp_group")
    if not isinstance(rtp_group, int) or isinstance(rtp_group, bool) or rtp_group != 1:
        errors.append("新任务rtp_group必须为整数1")
    if input_manifest.get("schema_version") != "1.1":
        errors.append("新任务必须使用input_manifest.schema_version=1.1")
    if not isinstance(authority, dict) or authority.get("schema_version") != "1.1":
        errors.append("新任务必须使用parameter_authority.schema_version=1.1")
    if not isinstance(authority, dict) or authority.get("report_contract_version") != CURRENT_REPORT_VERSION:
        errors.append(f"新任务parameter_authority必须使用{CURRENT_REPORT_VERSION}")
    return errors


def validate_contract(
    profile_path,
    contract_path,
    skill_root,
    parameter_authority_path=None,
    input_manifest_path=None,
    validation_mode="stage_transition",
    task_root_path=None,
):
    if validation_mode not in VALIDATION_MODES:
        return [f"未知语义校验模式: {validation_mode}"]
    profile_path, contract_path, skill_root = map(Path, (profile_path, contract_path, skill_root))
    profile, contract = load(profile_path), load(contract_path)
    manifest_path = Path(input_manifest_path) if input_manifest_path is not None else None
    input_manifest = load(manifest_path) if manifest_path is not None and manifest_path.is_file() else {}
    authority_path = Path(parameter_authority_path) if parameter_authority_path is not None else None
    authority = load(authority_path) if authority_path is not None and authority_path.is_file() else {}
    if not all(isinstance(value, dict) for value in (profile, contract, input_manifest, authority)):
        return ["game_profile、metric_contract、input_manifest与parameter_authority顶层必须为JSON对象"]
    if validation_mode == "historical_replay":
        return sorted(dict.fromkeys(historical_contract_errors(
            profile,
            contract,
            input_manifest,
            profile_path,
            manifest_path,
            authority_path,
        )))
    catalog = catalog_maps(skill_root)
    errors = list(catalog["errors"])
    catalog_errors, _, _ = validate_catalogs(skill_root)
    errors += [f"目录校验失败: {error}" for error in catalog_errors]
    schema_pair = profile.get("schema_version"), contract.get("schema_version")
    if schema_pair != ("1.2", "1.3"):
        errors.append("新任务必须成对使用game_profile.schema_version=1.2与metric_contract.schema_version=1.3")
    report_versions = {
        "game_profile": profile.get("report_contract_version"),
        "metric_contract": contract.get("report_contract_version"),
        "input_manifest": input_manifest.get("report_contract_version"),
    }
    for label, version in report_versions.items():
        if version != CURRENT_REPORT_VERSION:
            errors.append(f"新任务{label}必须使用{CURRENT_REPORT_VERSION}")
    errors += validate_new_task_identity(profile, contract, input_manifest, authority)
    errors += validate_schema(profile, skill_root / "assets/schemas/game-profile.schema.json", "game_profile")
    errors += validate_schema(contract, skill_root / "assets/schemas/metric-contract.schema.json", "metric_contract")
    if contract.get("schema_version") == "1.3":
        errors += validate_jackpot_materiality_policy_binding(contract, profile, skill_root)
    errors += validate_score_group_weight_policy_binding(contract, skill_root)
    errors += validate_ordered_distance_policy_binding(contract, skill_root)
    evidence_root = task_evidence_root(task_root_path) if task_root_path is not None else None
    profile_errors, active_nodes, required_nodes = validate_profile(profile, catalog, evidence_root, input_manifest)
    errors += profile_errors
    errors += validate_profile_links(active_nodes)
    errors += validate_mode_contract(profile, contract, active_nodes)
    errors += validate_value_symbol_multiplier_profile_bindings(active_nodes)
    errors += validate_cascade_multiplier_profile_bindings(active_nodes)
    scope_errors, scope_instances = validate_scope_instances(profile, active_nodes, task_root_path, input_manifest)
    errors += scope_errors
    mechanic_hash, metric_hash = sha(catalog["mechanics_index_path"]), sha(catalog["metrics_index_path"])
    mechanic_binding = profile.get("mechanics_catalog") if isinstance(profile.get("mechanics_catalog"), dict) else {}
    if mechanic_binding.get("version") != catalog["mechanics_index"].get("version") or mechanic_binding.get("sha256") != mechanic_hash:
        errors.append("game_profile未绑定当前玩法目录版本与hash")
    contract_catalogs = contract.get("catalogs") if isinstance(contract.get("catalogs"), dict) else {}
    if contract_catalogs.get("mechanics_version") != catalog["mechanics_index"].get("version"):
        errors.append("metric_contract玩法目录版本失效")
    if contract_catalogs.get("metrics_version") != catalog["metrics_index"].get("version"):
        errors.append("metric_contract指标目录版本失效")
    hashes = contract_catalogs.get("hashes") if isinstance(contract_catalogs.get("hashes"), dict) else {}
    if hashes.get("mechanics") != mechanic_hash or hashes.get("metrics") != metric_hash:
        errors.append("metric_contract目录hash失效")
    input_hashes = contract.get("input_hashes") if isinstance(contract.get("input_hashes"), dict) else {}
    if input_manifest_path is None:
        errors.append("新任务语义门禁必须提供input_manifest")
    else:
        manifest_path = Path(input_manifest_path)
        if not manifest_path.is_file() or input_hashes.get("input_manifest") != sha(manifest_path):
            errors.append("metric_contract未绑定当前input_manifest hash")
    if input_hashes.get("game_profile") != sha(profile_path):
        errors.append("metric_contract未绑定当前game_profile hash")
    if parameter_authority_path is None:
        errors.append("新任务语义门禁必须提供parameter_authority")
    else:
        authority_path = Path(parameter_authority_path)
        if not authority_path.is_file() or input_hashes.get("parameter_authority") != sha(authority_path):
            errors.append("metric_contract未绑定当前parameter_authority hash")
    package_ids = required_package_ids(active_nodes, catalog)
    expected_instances, package_metrics, expected_bindings = expected_metrics(active_nodes, scope_instances, package_ids, catalog, errors)
    items = contract.get("metrics")
    if not isinstance(items, list):
        errors.append("metric_contract.metrics必须为数组")
        items = []
    actual_instances, resolved_instances, measurable_instances = set(), set(), set()
    active_node_map = {
        node.get("node_id"): node
        for node in active_nodes
        if isinstance(node, dict) and isinstance(node.get("node_id"), str) and node.get("node_id")
    }
    items_by_key = {}
    active_items_by_key = {}
    for item in items:
        if not isinstance(item, dict):
            errors.append("指标合同metrics存在非对象项")
            continue
        metric_id = item.get("metric_id")
        catalog_metric = catalog["metrics"].get(metric_id)
        if catalog_metric is None:
            errors.append(f"指标合同引用未知metric_id: {metric_id}")
            continue
        if item.get("status") not in {"适用", INACTIVE_METRIC_STATUS}:
            errors.append(f"新任务指标状态必须为适用或不适用: {metric_id} / {item.get('status')}")
        source_ids = item.get("source_node_ids")
        if (
            not isinstance(source_ids, list)
            or not all(isinstance(node_id, str) and node_id for node_id in source_ids)
            or len(source_ids) != len(set(source_ids))
        ):
            errors.append(f"指标合同source_node_ids无效: {metric_id}")
            source_ids = []
        unknown_source_ids = sorted(set(source_ids) - set(active_node_map))
        if unknown_source_ids:
            errors.append(f"指标合同引用未知source_node_ids: {metric_id} / {','.join(unknown_source_ids)}")
        dimensions = item.get("instance_dimensions")
        if not isinstance(dimensions, dict) or any(
            not non_empty(name)
            or not isinstance(value, (str, int, float, bool))
            or isinstance(value, float) and not math.isfinite(value)
            or not non_empty(value)
            for name, value in dimensions.items()
        ):
            errors.append(f"指标合同instance_dimensions无效: {metric_id}")
            dimensions = {}
        if catalog_metric.get("owner") == "core.general" and source_ids and metric_id not in CORE_NODE_SCOPED:
            errors.append(f"Core指标source_node_ids必须为空: {metric_id}")
        if catalog_metric.get("owner") != "core.general" and not source_ids:
            errors.append(f"非Core指标必须绑定source_node_ids: {metric_id}")
        key = (metric_id, tuple(sorted(source_ids)), dimensions_key(dimensions))
        if key in actual_instances:
            errors.append(f"指标合同实例重复: {format_instance(key)}")
        actual_instances.add(key)
        items_by_key[key] = item
        binding = expected_bindings.get(key)
        scope = item.get("scope")
        if binding is not None and scope != binding.get("scope"):
            errors.append(f"指标合同作用域与scope_instance不一致: {format_instance(key)}")
        if not isinstance(scope, str) or any(str(value) not in scope for value in dimensions.values()):
            errors.append(f"指标合同作用域未体现实例维度: {format_instance(key)}")
        for field in CATALOG_IMMUTABLE_FIELDS:
            if field not in catalog_metric:
                continue
            for mismatch in deep_subset(catalog_metric[field], item.get(field), field):
                errors.append(f"指标合同篡改目录语义: {metric_id} / {mismatch}")
        if item.get("kind") == "score" and item.get("status") != INACTIVE_METRIC_STATUS:
            if not finite_number(item.get("weight")) or not close_probability(item.get("weight"), catalog_metric.get("default_weight")):
                errors.append(f"评分指标weight必须等于目录default_weight: {metric_id}")
        if item.get("kind") == "score" and item.get("status") != INACTIVE_METRIC_STATUS:
            if not non_empty(item.get("sealed_event_set_id")):
                errors.append(f"评分指标缺少sealed_event_set_id: {format_instance(key)}")
            if source_ids and not unknown_source_ids and any(
                item.get("sealed_event_set_id") not in active_node_map[node_id].get("semantic_event_set_ids", [])
                for node_id in source_ids
            ):
                errors.append(f"评分指标事件集ID未绑定全部来源玩法节点: {format_instance(key)}")
            if binding is None and key in expected_instances:
                errors.append(f"评分指标实例没有唯一scope_instance绑定: {format_instance(key)}")
            elif binding is not None and (
                item.get("sealed_event_set_id") != binding.get("semantic_event_set_id")
                or item.get("sealed_event_set_path") != binding.get("event_set_path")
                or item.get("sealed_event_set_sha256") != binding.get("event_set_sha256")
                or item.get("sealed_event_count") != binding.get("event_count")
            ):
                errors.append(f"评分指标事件集绑定与scope_instance不一致: {format_instance(key)}")
            event_path = item.get("sealed_event_set_path")
            resolved_event_path = safe_evidence_path(evidence_root, event_path) if evidence_root is not None else None
            if resolved_event_path is None or not resolved_event_path.is_file():
                errors.append(f"评分指标密封事件集文件不存在: {format_instance(key)}")
            if not is_sha256(item.get("sealed_event_set_sha256")):
                errors.append(f"评分指标缺少有效sealed_event_set_sha256: {format_instance(key)}")
            elif resolved_event_path is not None and resolved_event_path.is_file() and sha(resolved_event_path) != item.get("sealed_event_set_sha256"):
                errors.append(f"评分指标密封事件集hash失效: {format_instance(key)}")
            elif resolved_event_path is not None and resolved_event_path.is_file():
                try:
                    sample_unit = binding.get("sample_unit") if binding is not None else item.get("sample_unit")
                    event_dimensions = binding.get("dimensions") if binding is not None else dimensions
                    if sealed_event_count(resolved_event_path, sample_unit, event_dimensions) != item.get("sealed_event_count"):
                        errors.append(f"评分指标密封事件数与文件不一致: {format_instance(key)}")
                except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
                    errors.append(f"评分指标密封事件集格式无效: {format_instance(key)} / {exc}")
            manifest_hashes = input_manifest.get("hashes", {}) if isinstance(input_manifest.get("hashes"), dict) else {}
            if not isinstance(event_path, str) or manifest_hashes.get(event_path) != item.get("sealed_event_set_sha256"):
                errors.append(f"评分指标密封事件集未写入input_manifest.hashes: {format_instance(key)}")
            if not isinstance(item.get("sealed_event_count"), int) or isinstance(item.get("sealed_event_count"), bool) or item.get("sealed_event_count") < 1:
                errors.append(f"评分指标缺少有效sealed_event_count: {format_instance(key)}")
        if item.get("status") != INACTIVE_METRIC_STATUS:
            active_items_by_key[key] = item
    score_budget_instances = {}
    for key, item in active_items_by_key.items():
        if item.get("kind") != "score" or item.get("scope_aggregation") != "weighted_mean":
            continue
        score_budget_instances.setdefault(item.get("score_budget_key"), []).append((key, item))
    for budget_key, budget_items in score_budget_instances.items():
        weights = [item.get("scope_weight") for _, item in budget_items]
        if any(not finite_number(value) or value <= 0 for value in weights):
            errors.append(f"score_budget_key作用域权重必须为有限正数: {budget_key}")
            continue
        if len(weights) == 1 and not close_probability(weights[0], 1.0):
            errors.append(f"单作用域score_budget_key的scope_weight必须为1: {budget_key}")
        elif len(weights) > 1 and not close_probability(sum(weights), 1.0):
            errors.append(f"同一score_budget_key全部scope_weight必须归一为1: {budget_key}")
    errors += validate_step_return_owner_partitions(
        profile,
        contract,
        active_items_by_key,
        scope_instances,
        active_nodes,
        task_root_path,
    )
    resolved_fact_items_by_key, derived_inapplicability_errors = resolve_derived_facts(
        items,
        active_nodes,
        active_items_by_key,
        catalog,
        evidence_root,
        input_manifest,
    )
    for item in items:
        if not isinstance(item, dict) or item.get("metric_id") not in catalog["metrics"]:
            continue
        key = metric_instance_key(item)
        item_errors = []
        if item.get("status") == INACTIVE_METRIC_STATUS:
            if item.get("inapplicability_reason_code") == "deterministically_derived_from_primary":
                item_errors += derived_inapplicability_errors.get(key, [f"确定性派生事实未完成解析: {format_instance(key)}"])
            else:
                item_errors += validate_inapplicability(item, active_nodes, resolved_fact_items_by_key, catalog, evidence_root, input_manifest)
            if not item_errors:
                resolved_instances.add(key)
        elif item.get("status") in {"缺口", "不可测", "缺失", "无效"} or not non_empty(item.get("target")):
            item_errors.append(f"适用指标缺少有效目标或可测状态: {format_instance(key)}")
        else:
            resolved_instances.add(key)
            measurable_instances.add(key)
        item_errors += validate_target_evidence(item, catalog["metrics"][item.get("metric_id")], expected_bindings.get(key), evidence_root, input_manifest)
        item_errors += validate_metric_target(item)
        item_errors += validate_derived_diagnostic_projection(item, resolved_fact_items_by_key, active_nodes)
        item_errors += validate_dynamic_ordered_axis(item, active_node_map)
        item_errors += validate_collect_category_contract(item, active_node_map)
        item_errors += validate_multiplier_return_contract(item, active_node_map)
        item_errors += validate_transform_target_coherence_contract(item, active_node_map)
        item_errors += validate_conditional_group_weight_binding(
            item,
            resolved_fact_items_by_key,
            active_node_map,
            evidence_root,
            input_manifest,
        )
        item_errors += validate_persistent_position_contract(item, active_nodes, items_by_key)
        item_errors += validate_matched_position_transition_contract(item, active_nodes, items_by_key)
        item_errors += validate_respin_position_contract(item, active_nodes, items_by_key)
        item_errors += validate_cascade_capacity_contract(item, items_by_key)
        item_errors += validate_feature_return_zero_bucket(item, active_nodes)
        item_errors += validate_feature_path_contract(item, items_by_key)
        item_errors += validate_feature_buy_contract(item, active_nodes, items_by_key, evidence_root)
        item_errors += validate_trigger_entry_source_contract(item, active_nodes, evidence_root)
        item_errors += validate_award_draw_return_ownership(item, active_nodes, items_by_key)
        item_errors += validate_feature_duration_contract(item, active_nodes)
        item_errors += validate_feature_stage_path_domain(item, active_nodes)
        item_errors += validate_feature_resource_ownership(item, active_nodes, resolved_fact_items_by_key)
        item_errors += validate_hold_spin_capacity_ownership(item, active_nodes, active_items_by_key, expected_bindings.get(key))
        item_errors += validate_hold_spin_transition_contract(item, active_nodes)
        item_errors += validate_jackpot_material_metric(item, active_nodes, active_items_by_key, catalog, contract)
        item_errors += validate_cascade_multiplier_ownership(item, active_nodes)
        item_errors += validate_value_symbol_multiplier_ownership(item, active_nodes)
        errors += item_errors
        if item_errors:
            resolved_instances.discard(key)
            measurable_instances.discard(key)
    missing_instances = expected_instances - actual_instances
    extra_instances = actual_instances - expected_instances
    if missing_instances:
        errors.append(f"指标合同缺少画像命中指标实例: {','.join(format_instance(key) for key in sorted(missing_instances, key=instance_sort_key))}")
    if extra_instances:
        errors.append(f"指标合同包含画像未命中指标实例: {','.join(format_instance(key) for key in sorted(extra_instances, key=instance_sort_key))}")
    errors += validate_package_matches(contract, package_metrics, expected_bindings, active_nodes)
    required_node_count = len(required_nodes)
    owned_nodes = 0
    for node in required_nodes:
        node_owned = True
        for package_id in catalog["mechanics"][node["mechanic_id"]].get("metric_requirements", {}).get("required_packages", []):
            instances = [
                (source_ids, dimensions, metric_ids)
                for (candidate_package_id, source_ids, dimensions), metric_ids in package_metrics.items()
                if candidate_package_id == package_id and node["node_id"] in source_ids
            ]
            if not instances or not all(
                all((metric_id, source_ids, dimensions) in resolved_instances for metric_id in metric_ids)
                for source_ids, dimensions, metric_ids in instances
            ):
                node_owned = False
                break
        owned_nodes += int(node_owned)
    required_metrics = len(expected_instances)
    measurable_metrics = len(expected_instances & measurable_instances)
    resolved_metrics = len(expected_instances & resolved_instances)
    expected_coverage = {
        "mechanic_required": required_node_count,
        "mechanic_owned": owned_nodes,
        "mechanic_coverage": owned_nodes / required_node_count if required_node_count else None,
        "metric_required": required_metrics,
        "metric_measurable": measurable_metrics,
        "metric_measurability": measurable_metrics / required_metrics if required_metrics else None,
        "metric_resolved": resolved_metrics,
        "metric_resolution": resolved_metrics / required_metrics if required_metrics else None,
    }
    if contract.get("coverage") != expected_coverage:
        errors.append(f"coverage自报不一致: 期望{json.dumps(expected_coverage, ensure_ascii=False, sort_keys=True)}")
    if contract.get("gaps"):
        errors.append("已完成的新任务合同不得保留未解决指标缺口")
    if contract.get("owner_conflicts"):
        errors.append("已完成的新任务合同不得保留多Owner冲突")
    errors += validate_value_symbol_upgrade_metric_bindings(items, active_nodes)
    errors += validate_active_owner_conflicts(items, catalog, active_nodes)
    return sorted(dict.fromkeys(errors))


def main():
    parser = argparse.ArgumentParser(description="校验玩法画像到指标合同的确定性语义覆盖")
    parser.add_argument("--game-profile", required=True, type=Path)
    parser.add_argument("--metric-contract", required=True, type=Path)
    parser.add_argument("--skill-root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--parameter-authority", type=Path)
    parser.add_argument("--input-manifest", type=Path)
    parser.add_argument("--task-root", type=Path)
    parser.add_argument("--historical-replay", action="store_true")
    args = parser.parse_args()
    try:
        trusted_root = args.task_root
        if trusted_root is None and args.input_manifest is not None:
            trusted_root = task_root(args.input_manifest.parent.parent)
        errors = validate_contract(
            args.game_profile,
            args.metric_contract,
            args.skill_root,
            args.parameter_authority,
            args.input_manifest,
            validation_mode="historical_replay" if args.historical_replay else "stage_transition",
            task_root_path=trusted_root,
        )
    except (OSError, ValueError, TypeError, AttributeError, KeyError, IndexError, OverflowError, RecursionError, json.JSONDecodeError) as exc:
        errors = [str(exc)]
    result = {"status": "通过" if not errors else "阻塞", "errors": errors}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
