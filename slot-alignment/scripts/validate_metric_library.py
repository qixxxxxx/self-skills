#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def schema_errors(schema_path, data_path):
    schema, data = load(schema_path), load(data_path)
    Draft202012Validator.check_schema(schema)
    return [f"{data_path.relative_to(ROOT)}:{'.'.join(map(str, error.absolute_path)) or '$'}: {error.message}" for error in Draft202012Validator(schema).iter_errors(data)]


def walk_keys(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from walk_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk_keys(item)


def main():
    parser = argparse.ArgumentParser(description="校验slot-alignment v5指标库")
    parser.add_argument("--root", default=str(ROOT))
    args = parser.parse_args()
    root = Path(args.root).resolve()
    library_path = root / "references/指标目录/index.json"
    evaluation_path = root / "assets/policies/alignment_evaluation_policy.json"
    hard_path = root / "assets/policies/hard_gate_tolerance_policy.json"
    sample_path = root / "assets/policies/sample_execution_policy.json"
    capability_policy_path = root / "assets/policies/runtime_capability_policy.json"
    errors = []
    for path in root.rglob("*.json"):
        try:
            load(path)
        except Exception as exc:
            errors.append(f"{path.relative_to(root)}不是有效JSON: {exc}")
    errors += schema_errors(root / "assets/schemas/metric-library.schema.json", library_path)
    errors += schema_errors(root / "assets/schemas/alignment-evaluation-policy.schema.json", evaluation_path)
    errors += schema_errors(root / "assets/schemas/hard-gate-tolerance-policy.schema.json", hard_path)
    errors += schema_errors(root / "assets/schemas/sample-execution-policy.schema.json", sample_path)
    errors += schema_errors(root / "assets/schemas/runtime-capability-policy.schema.json", capability_policy_path)
    for schema_name in ["metric-contract.schema.json", "alignment-result.schema.json", "game-profile-metric-bindings.schema.json", "joint-self-comparison.schema.json", "sample-execution-plan.schema.json", "runtime-capability-matrix.schema.json", "stage3-gate.schema.json", "delivery-manifest.schema.json"]:
        Draft202012Validator.check_schema(load(root / "assets/schemas" / schema_name))
    library, evaluation, hard, sample, capability_policy = load(library_path), load(evaluation_path), load(hard_path), load(sample_path), load(capability_policy_path)
    if library.get("version") != "5.2.0" or evaluation.get("version") != "5.4.0" or evaluation.get("applies_to_metric_library") != "5.2.0":
        errors.append("指标库必须为5.2.0，评价政策必须为5.4.0且绑定指标库5.2.0")
    category_ids = [item["category_id"] for item in library["categories"]]
    if category_ids != ["N", "J", "P", "B"]:
        errors.append(f"顶层分类必须按N/J/P/B唯一排列，实际={category_ids}")
    expected_cards = ["N1", "N2", "N3", "N4", "N5", "N6", "J1", "J2", "J3", "P1", "P2", "B1", "B2"]
    cards = library["cards"]
    card_ids = [item["card_id"] for item in cards]
    if card_ids != expected_cards:
        errors.append(f"指标卡必须精确为{expected_cards}，实际={card_ids}")
    if len(card_ids) != len(set(card_ids)):
        errors.append("指标卡ID重复")
    for card in cards:
        if not card["card_id"].startswith(card["category_id"]):
            errors.append(f"{card['card_id']}分类与ID前缀不一致")
        expected_kind = "hard_gate" if card["category_id"] == "N" else "alignment"
        if card["kind"] != expected_kind:
            errors.append(f"{card['card_id']} kind必须为{expected_kind}")
        facet_ids = [item["facet_id"] for item in card["facets"]]
        if len(facet_ids) != len(set(facet_ids)):
            errors.append(f"{card['card_id']} facet_id重复")
        for facet in card["facets"]:
            if facet["distance_method"] not in evaluation["distance_methods"] and facet["distance_method"] not in {"range_error", "relative_error"}:
                errors.append(f"{card['card_id']}.{facet['facet_id']}距离方法未被评价政策覆盖")
    for audit in library["audits"]:
        unknown_cards = set(audit["source_cards"]) - set(card_ids)
        if unknown_cards:
            errors.append(f"{audit['audit_id']}引用未知指标卡: {sorted(unknown_cards)}")
    forbidden = {"weight", "weights", "score", "scores", "score_profile", "score_budget_key", "waiver", "waivers"}
    present = sorted(forbidden & set(walk_keys(library)))
    if present:
        errors.append(f"v5指标库出现禁止字段: {present}")
    if hard["metric_factors"].get("N4") != 1.5:
        errors.append("N4容差系数必须为1.5")
    n1 = next(item for item in cards if item["card_id"] == "N1")["facets"][0]
    if n1.get("target_source") != "user_confirmed_exact_rtp" or n1.get("distance_method") != "absolute_probability_error":
        errors.append("N1必须使用用户确认唯一RTP和绝对RTP差")
    n6 = next(item for item in cards if item["card_id"] == "N6")["facets"][0]
    if n6.get("target_source") != "original_component_share_mapped_to_user_confirmed_total_rtp" or n6.get("distance_method") != "absolute_probability_error":
        errors.append("N6必须由原版组件占比映射用户确认总RTP")
    expected_j_facets = {
        "J1": ["win_group_participation_rate"],
        "J2": ["primary_structure_size", "simultaneous_visible_win_count", "visible_step_reward_size"],
        "J3": ["total_depth", "chain_reward_size"],
    }
    for card_id, expected in expected_j_facets.items():
        actual = [item["facet_id"] for item in next(item for item in cards if item["card_id"] == card_id)["facets"]]
        if actual != expected:
            errors.append(f"{card_id}精简Facet必须为{expected}，实际={actual}")
    if any(card_id.startswith("J") for audit in library["audits"] for card_id in audit["source_cards"]):
        errors.append("v5.2不保留J类审计项")
    calculation = hard["calculation"]
    if calculation.get("N1_interval_forbidden") is not True or calculation.get("N1_distance") != "abs(candidate-target)":
        errors.append("N1必须禁止区间目标并使用绝对RTP差")
    n4 = next(item for item in cards if item["card_id"] == "N4")["facets"][0]
    if n4.get("boundary") != "inclusive" or n4.get("feature_buy_cost_rule") != "use_actual_purchase_cost":
        errors.append("N4必须包含>=1x边界并按Feature Buy实际成本")
    p2 = next(item for item in cards if item["card_id"] == "P2")["facets"][0]
    if "not_occurred_or_not_effective" not in p2.get("required_states", []):
        errors.append("P2必须包含未发生或未生效状态")
    b1_facets = {item["facet_id"]: item for item in next(item for item in cards if item["card_id"] == "B1")["facets"]}
    density = b1_facets.get("symbol_group_density_per_board", {})
    key_count = b1_facets.get("key_symbol_count_per_board", {})
    if density.get("measurement") != "count(group_symbols_on_board)/count(active_visible_cells)" or density.get("support_span") != 1.0 or density.get("visible_cell_normalized") is not True:
        errors.append("B1普通符号组必须按有效格密度评价并固定support_span=1")
    if key_count.get("zero_bucket_required") is not True:
        errors.append("B1关键符号数量必须包含0桶")
    b2 = next(item for item in cards if item["card_id"] == "B2")["facets"][1]
    if b2.get("measurement") != "board_equalized_symbol_cell_density_conditioned_on_presence":
        errors.append("B2关键符号位置必须按出现盘面等权归一化")
    if b2.get("subitem_source") != "profile_selected_spatial_symbols_and_formal_board_scopes" or "condition_on" in b2:
        errors.append("B2只能按画像选定关键空间符号逐作用域展开，不得按数量展开")
    structural = evaluation["distance_methods"]["structural_wasserstein"]
    if structural.get("symbol_position_occurrence_mass") != "1/count_on_board":
        errors.append("B2关键符号位置必须消除单盘符号数量影响")
    decision = evaluation["decision_model"]
    if any(decision[key] for key in ["score_scale_enabled", "weights_enabled", "composite_score_enabled", "metric_compensation_enabled", "formal_metric_waiver_enabled"]):
        errors.append("v5评价政策不得启用分数、权重、补偿或豁免")
    if evaluation["tolerance"]["joint_confidence_quantile"] != 0.99 or evaluation["tolerance"]["maximum_perceptual_cap"] is not None:
        errors.append("J/P/B必须使用无额外上限的联合99%自对照")
    if sample.get("version") != "1.1.0":
        errors.append("样本执行策略版本必须为1.1.0")
    if capability_policy.get("version") != "1.0.0" or capability_policy.get("rules", {}).get("implementation_must_not_narrow_authorized_cardinality") is not True:
        errors.append("Runtime能力策略必须为1.0.0并禁止实现层缩窄已授权能力")
    if sample["rng_protocol"]["calibration_default"] != "chunk_seeded" or sample["rng_protocol"]["formal_default"] != "chunk_seeded":
        errors.append("CALIBRATION与FORMAL默认RNG协议必须为chunk_seeded")
    if sample["rng_protocol"]["diagnostics_only"] != ["crn_v1"]:
        errors.append("crn_v1只能用于离线诊断")
    if [item["cumulative_paid_entries"] for item in sample["calibration"]["stages"]] != [100000, 500000, 2000000]:
        errors.append("CALIBRATION候选阶梯必须为10万、50万、200万累计局数")
    recheck = sample["calibration"]["independent_recheck"]
    if recheck != {"top_candidate_count": 2, "additional_paid_entries": 2000000, "independent_seed": True}:
        errors.append("CALIBRATION前2名必须另跑200万独立复核")
    formal = sample["formal"]
    if formal["paid_entry_tiers"] != [10000000, 20000000, 50000000] or formal["minimum_conditional_sample"] != 2000:
        errors.append("FORMAL必须使用1000万、2000万、5000万档位和2000个条件有效样本")
    if formal["state_frequency_must_not_drive_tier"] is not True or "whole_metric_instance_denominator" not in formal["conditional_probability_semantics"]:
        errors.append("FORMAL升档只能按指标实例整体条件分母，不得按分布内单个状态")
    if formal["maximum_paid_entries"] != 50000000 or formal["maximum_tier_insufficient_action"] != "run_max_tier_then_mark_affected_instances_sample_insufficient_U":
        errors.append("5000万不足时仍须执行并将受影响实例标为样本不足/U")
    if sample["execution"]["benchmark_is_blocking_gate"] is not False:
        errors.append("性能基准只能记录和优化，不得成为阻塞门禁")
    execution = sample["execution"]
    if execution.get("benchmark_profiles") != ["core_simulation", "formal_full_observation"]:
        errors.append("性能基准必须分别记录纯核心模拟和全部正式观测吞吐")
    if execution.get("shard_semantics") != "logical_checkpoint_and_rng_partition" or execution.get("internal_micro_batches_allowed") is not True or execution.get("internal_micro_batch_must_preserve_rng_stream") is not True:
        errors.append("25万分片必须是逻辑seed/checkpoint边界，并允许保持RNG流的内部micro-batch")
    if execution.get("worker_static_context_loads_once") is not True or execution.get("candidate_context_builds_once_per_worker") is not True:
        errors.append("Worker静态上下文和候选参数上下文必须分别只构建一次")
    if execution.get("core_loop_implementation") != "compiled_or_vectorized_batch_with_python_orchestration":
        errors.append("大样本核心循环必须使用编译或批量路径，Python只负责调度")
    if execution.get("accumulator_cardinality") != "bounded_by_frozen_metric_support":
        errors.append("正式累计器基数必须由冻结指标支持限定")
    if execution.get("parallelism_layer_count") != 1 or execution.get("nested_parallelism_forbidden") is not True:
        errors.append("单次执行只允许一层并行，禁止嵌套超配")
    required_hot_path_forbidden = {
        "per_entry_tdigest_update",
        "unbounded_exact_value_counts",
        "per_entry_string_key_construction",
        "per_entry_business_object_allocation",
    }
    if not required_hot_path_forbidden.issubset(set(execution.get("hot_path_forbidden", []))):
        errors.append("热路径必须禁止逐入口TDigest、无界精确值表、字符串key和业务对象分配")
    required_files = [
        "SKILL.md",
        "references/01-指标框架.md",
        "references/02-评价合同.md",
        "references/03-执行与报告.md",
        "references/04-工作区目录结构.md",
        "references/05-性能与执行预算.md",
        "assets/policies/sample_execution_policy.json",
        "assets/policies/runtime_capability_policy.json",
        "assets/schemas/sample-execution-policy.schema.json",
        "assets/schemas/sample-execution-plan.schema.json",
        "assets/schemas/runtime-capability-policy.schema.json",
        "assets/schemas/runtime-capability-matrix.schema.json",
        "assets/templates/artifacts/01-input-profile/runtime_capability_matrix.json",
        "assets/templates/artifacts/02-metric-matching/sample_execution_plan.json",
        "assets/templates/reports/原版体验对齐报告.md",
        "assets/templates/reports/指标分类明细.md",
        "assets/templates/artifacts/05-delivery/delivery_manifest.json",
        "scripts/alignment.py",
        "scripts/compile_metric_contract.py",
        "scripts/validate_sample_plan.py",
        "scripts/validate_runtime_capability_coverage.py",
        "scripts/evaluate_alignment.py",
        "scripts/validate_delivery.py",
    ]
    for relative in required_files:
        if not (root / relative).is_file():
            errors.append(f"缺少v5必需文件: {relative}")
    path_docs = "\n".join((root / relative).read_text(encoding="utf-8") for relative in ["SKILL.md", "references/04-工作区目录结构.md"])
    forbidden_path_aliases = ["workspace_root", "slot_docs_root", "config_runtime_root", "server_runtime_cache_root", "slot-dosc"]
    present_aliases = [item for item in forbidden_path_aliases if item in path_docs]
    if present_aliases:
        errors.append(f"项目路径必须使用标准目录ID，发现旧别名: {present_aliases}")
    required_directory_ids = {"config-test", "config-prod", "slot-docs", "slot-math-workbench", "pragmatic-workbench", "server-dev", "server-prod"}
    if not required_directory_ids.issubset(set(path_docs.replace("`", "").replace(":", " ").split())):
        errors.append("工作区规范未完整声明标准目录ID")
    delivery_docs = "\n".join((root / relative).read_text(encoding="utf-8") for relative in [
        "SKILL.md",
        "references/03-执行与报告.md",
        "references/04-工作区目录结构.md",
        "assets/templates/reports/原版体验对齐报告.md",
    ])
    for marker in ["game_core.json.meta.version", "delivery_manifest.runtime_version", "task_id"]:
        if marker not in delivery_docs:
            errors.append(f"交付Runtime版本规则缺少标记: {marker}")
    if "{{runtime_version}}" in delivery_docs:
        errors.append("报告不得使用独立runtime_version占位符，必须直接使用task_id")
    delivery_template = load(root / "assets/templates/artifacts/05-delivery/delivery_manifest.json")
    if delivery_template.get("runtime_version") != delivery_template.get("task_id"):
        errors.append("交付manifest模板的runtime_version必须与task_id使用同一占位值")
    authority_docs = "\n".join((root / relative).read_text(encoding="utf-8") for relative in ["SKILL.md", "references/03-执行与报告.md"])
    for marker in ["reel-strip", "默认", "重复次数与排列", "不得重复询问"]:
        if marker not in authority_docs:
            errors.append(f"默认reel-strip可调权重规则缺少标记: {marker}")
    old_major = "4"
    forbidden_markers = [
        f"v{old_major}.5",
        f"reports.v{old_major}",
        "histor" + "ical-replay",
        "histor" + "ical_library",
        "leg" + "acy_contracts_unchanged",
        "_v5" + ".py",
        "/" + "v5" + "/",
    ]
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".md", ".json", ".py", ".yaml", ".yml"}:
            continue
        text = path.read_text(encoding="utf-8")
        for marker in forbidden_markers:
            if marker in text or marker in path.as_posix():
                errors.append(f"纯5.0活动面出现历史或旁路标记: {path.relative_to(root)} -> {marker}")
    if (root / "README.md").exists():
        errors.append("纯5.0 Skill不保留README旁路入口")
    if errors:
        print("\n".join(f"ERROR: {item}" for item in errors), file=sys.stderr)
        raise SystemExit(1)
    print(f"OK: v5.2指标库校验通过，4类13卡{sum(len(item['facets']) for item in cards)}个Facet")


if __name__ == "__main__":
    main()
