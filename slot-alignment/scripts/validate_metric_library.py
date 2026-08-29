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
    errors = []
    for path in root.rglob("*.json"):
        try:
            load(path)
        except Exception as exc:
            errors.append(f"{path.relative_to(root)}不是有效JSON: {exc}")
    errors += schema_errors(root / "assets/schemas/metric-library.schema.json", library_path)
    errors += schema_errors(root / "assets/schemas/alignment-evaluation-policy.schema.json", evaluation_path)
    errors += schema_errors(root / "assets/schemas/hard-gate-tolerance-policy.schema.json", hard_path)
    for schema_name in ["metric-contract.schema.json", "alignment-result.schema.json", "game-profile-metric-bindings.schema.json", "joint-self-comparison.schema.json", "stage3-gate.schema.json", "delivery-manifest.schema.json"]:
        Draft202012Validator.check_schema(load(root / "assets/schemas" / schema_name))
    library, evaluation, hard = load(library_path), load(evaluation_path), load(hard_path)
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
    calculation = hard["calculation"]
    if calculation.get("N1_interval_forbidden") is not True or calculation.get("N1_distance") != "abs(candidate-target)":
        errors.append("N1必须禁止区间目标并使用绝对RTP差")
    n4 = next(item for item in cards if item["card_id"] == "N4")["facets"][0]
    if n4.get("boundary") != "inclusive" or n4.get("feature_buy_cost_rule") != "use_actual_purchase_cost":
        errors.append("N4必须包含>=1x边界并按Feature Buy实际成本")
    p2 = next(item for item in cards if item["card_id"] == "P2")["facets"][0]
    if "not_occurred_or_not_effective" not in p2.get("required_states", []):
        errors.append("P2必须包含未发生或未生效状态")
    b1 = next(item for item in cards if item["card_id"] == "B1")["facets"][0]
    if b1.get("zero_bucket_required") is not True:
        errors.append("B1必须包含0桶")
    b2 = next(item for item in cards if item["card_id"] == "B2")["facets"][1]
    if b2.get("measurement") != "board_equalized_symbol_cell_density_conditioned_on_presence":
        errors.append("B2关键符号位置必须按出现盘面等权归一化")
    if b2.get("subitem_source") != "profile_selected_spatial_symbols_and_board_scopes" or "condition_on" in b2:
        errors.append("B2只能按画像选定关键空间符号逐作用域展开，不得按数量展开")
    structural = evaluation["distance_methods"]["structural_wasserstein"]
    if structural.get("symbol_position_occurrence_mass") != "1/count_on_board":
        errors.append("B2关键符号位置必须消除单盘符号数量影响")
    decision = evaluation["decision_model"]
    if any(decision[key] for key in ["score_scale_enabled", "weights_enabled", "composite_score_enabled", "metric_compensation_enabled", "formal_metric_waiver_enabled"]):
        errors.append("v5评价政策不得启用分数、权重、补偿或豁免")
    if evaluation["tolerance"]["joint_confidence_quantile"] != 0.99 or evaluation["tolerance"]["maximum_perceptual_cap"] is not None:
        errors.append("J/P/B必须使用无额外上限的联合99%自对照")
    required_files = [
        "SKILL.md",
        "references/01-指标框架.md",
        "references/02-评价合同.md",
        "references/03-执行与报告.md",
        "references/04-工作区目录结构.md",
        "assets/templates/reports/原版体验对齐报告.md",
        "assets/templates/reports/指标分类明细.md",
        "assets/templates/artifacts/05-delivery/delivery_manifest.json",
        "scripts/alignment.py",
        "scripts/compile_metric_contract.py",
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
    print(f"OK: v5指标库校验通过，4类13卡{sum(len(item['facets']) for item in cards)}个Facet")


if __name__ == "__main__":
    main()
