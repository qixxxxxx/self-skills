#!/usr/bin/env python3
import argparse
import hashlib
import json
import re
from pathlib import Path


SUMMARY_RELATIVE_PATH = Path("references/指标目录/指标汇总.md")
SUMMARY_CONTRACT_VERSION = "slot-alignment.metric-summary.v8"
CATALOG_DIRECTORY_NAMES = {
    "mechanics": "玩法画像",
    "metrics": "指标目录",
}

KIND_NAMES = {"hard": "硬指标", "score": "评分指标", "audit": "审计指标"}
ROLE_NAMES = {
    "primary": "主指标",
    "guard_cross_check": "守卫/交叉核对",
    "derived_diagnostic": "派生诊断",
    "audit": "审计",
}
METHOD_NAMES = {
    "absolute_error": "绝对差",
    "relative_error": "相对误差",
    "range_error": "目标区间判定",
    "total_variation": "总变差距离",
    "mean_absolute_error": "平均绝对差",
    "grouped_mean_absolute_error": "分组平均绝对差",
    "max_absolute_error": "最大绝对差",
    "grouped_total_variation": "分组总变差距离",
    "wasserstein_1d": "一维Wasserstein距离",
    "grouped_wasserstein_1d": "分组一维Wasserstein距离",
    "report_only": "仅报告审计",
    "deterministic_derivation": "确定性派生核对",
    "sealed_event_recomputation": "同一密封事件集逐事件重算",
    "field_consistency_gate": "逐字段一致性门禁",
}
METHOD_DESCRIPTIONS = {
    "absolute_error": "比较实际值与目标值的绝对差。",
    "relative_error": "比较差值占目标值的比例。",
    "range_error": "判断实际值是否落在密封目标区间内。",
    "total_variation": "比较无序类别概率差；0表示完全一致。",
    "mean_absolute_error": "对各字段绝对差取平均。",
    "grouped_mean_absolute_error": "先在每个条件组内平均字段绝对差，再按候选出现前密封的组权重汇总。",
    "max_absolute_error": "取各字段中最差的绝对差。",
    "grouped_total_variation": "先逐条件组比较无序分布，再按候选出现前密封的组权重汇总。",
    "wasserstein_1d": "按实际有序桶之间的距离比较分布；自然计数保持线性，长尾价值按目录固定变换。",
    "grouped_wasserstein_1d": "先按目录密封的位置语义逐条件组比较有序分布，再按候选出现前密封的组权重汇总。",
    "report_only": "只展示统计结果，不进入评分。",
    "deterministic_derivation": "由已登记主指标按固定规则推出，并核对结果一致性。",
    "sealed_event_recomputation": "从同一批密封原始事件逐条重算，避免换样本或换口径。",
    "field_consistency_gate": "逐字段核对规则、封顶、重置或绑定关系；关键字段不一致时按目录规则阻塞。",
}
OPERATOR_NAMES = {
    "exists": "存在",
    "not_exists": "不存在",
    "equals": "等于",
    "not_equals": "不等于",
    "in": "属于",
    "not_in": "不属于",
    "contains": "包含",
    "gt": "大于",
    "gte": "大于等于",
    "lt": "小于",
    "lte": "小于等于",
    "truthy": "为真",
    "falsy": "为假",
}
AGGREGATION_NAMES = {
    "weighted_mean": "按作用域权重加权平均",
    "minimum": "取最差作用域",
}
PROFILE_ATTRIBUTE_NAMES_ZH = {
    "adjacency_rule": "邻接规则",
    "aggregation_rule": "奖励聚合规则",
    "application_scope": "应用范围",
    "application_timing": "应用时点",
    "assignment_timing": "赋值时点",
    "assistance_resolution_rule": "Wild辅助判定规则",
    "actual_capacity_domain": "实际容量取值域",
    "available_ways_formula": "可用Ways计算公式",
    "board_capacity": "盘面容量",
    "cap_rule": "上限规则",
    "capacity_domain": "容量取值域",
    "capacity_owner_bindings": "容量主Owner绑定",
    "capacity_observation_points": "容量观测时点集合",
    "capacity_observation_point": "容量观测时点",
    "capacity_scope": "容量作用范围",
    "capacity_transition_contract": "容量推进合同",
    "changed_position_coordinate_domain": "变形位置坐标域",
    "changed_position_pattern_representation": "变形位置模式表示",
    "collection_scope": "收集范围",
    "combine_rule": "组合计算规则",
    "continuation_condition": "连续演化继续条件",
    "count_scope": "计数范围",
    "draw_count_rule": "抽取次数规则",
    "draw_dependency_rule": "多次抽取依赖规则",
    "draw_state_definition": "抽取状态定义",
    "effect_owner_node_id": "效果Owner节点ID",
    "effective_capacity_axis_semantics": "实际有效容量轴语义",
    "effective_capacity_definition": "实际有效容量定义",
    "effective_capacity_formula": "实际有效容量公式",
    "effective_capacity_source": "实际有效容量来源",
    "effective_capacity_unit_zh": "实际有效容量业务单位",
    "eligibility_scope": "合格机会范围",
    "eligible_symbol_domain": "可结算符号域",
    "entry_source_semantics": "入口来源语义定义",
    "entry_sources": "入口来源集合",
    "evaluation_timing": "判定时点",
    "event_target_assignment_rule": "同事件目标分配规则",
    "exit_condition": "退出条件",
    "expansion_geometry": "扩展几何规则",
    "extension_rule": "延长或续命规则",
    "generator_partitions": "生成单元分区",
    "geometry_layout_binding": "几何布局观测绑定",
    "geometry_layout_domain": "几何布局取值域",
    "guarantee_rule": "保底规则",
    "height_domain_by_reel": "各轴高度取值域",
    "fixed_height_by_reel": "固定不规则盘面各轴高度",
    "fixed_valid_cell_layout_id": "固定有效格布局ID",
    "held_position_rule": "保留位置规则",
    "incremental_payout_rule": "增量派奖规则",
    "jackpot_material_owner_bindings": "物质性Jackpot主Owner绑定",
    "jackpot_tier_exposure": "Jackpot逐层原版暴露",
    "initial_locked_items_rule": "初始锁定对象规则",
    "initial_respin_rule": "初始重转次数规则",
    "initial_spin_grant_rule": "初始免费旋转赠送规则",
    "line_count": "赔付线数量",
    "line_definitions": "赔付线坐标定义",
    "linked_multiplier_id": "关联倍率节点ID",
    "linked_symbol_domain": "关联符号域",
    "lock_condition": "锁定条件",
    "matched_position_transition_bindings": "稳定对象位置配对绑定",
    "max_steps_policy": "最大抽取步数策略",
    "minimum_cluster_size": "最小中奖连片大小",
    "near_miss_structure_relevant": "是否关注未中奖近门槛连片",
    "observation_points": "观测时点集合",
    "ordered_axis_semantics": "有序状态轴语义",
    "outcome_pool": "奖励结果池",
    "outcome_return_equivalence": "奖励结果与路径回报等价证明",
    "output_axis_semantics_by_output": "各输出的有序轴语义",
    "output_category_domains_by_output": "各输出的类别取值域",
    "path_signature_definition": "Feature阶段路径签名定义",
    "payout_scope": "派奖范围",
    "position_domain": "位置域",
    "position_domain_by_actual_capacity": "各实际容量对应位置域",
    "position_pattern_coordinate_domain": "位置模式坐标域",
    "position_pattern_representation": "位置模式表示",
    "position_transition_bindings": "位置集合转移绑定",
    "progression_driver": "递进驱动因素",
    "progression_rule": "递进规则",
    "random_source": "随机来源",
    "realization_condition": "奖值兑现条件",
    "reel_height_variation": "轴高是否变化",
    "reels": "轴数量",
    "refill_rule": "补充符号规则",
    "refill_partition_rule": "补入格稳定分区规则",
    "replacement_rule": "Wild替代规则",
    "rerolled_scope": "重转覆盖范围",
    "reset_rule": "重置规则",
    "resolved_cell_rule": "实际结算格判定规则",
    "retrigger_rule": "重触发规则",
    "return_binding_rule": "回报绑定规则",
    "return_dependency_evidence": "回报额外依赖证据",
    "same_depth_multiplier_randomness": "同一Cascade深度是否仍有倍率随机性",
    "selection_rule": "选择规则",
    "source_domain": "来源符号域",
    "source_wild_domain": "来源Wild域",
    "spatial_partitions": "空间分区",
    "stack_axis": "连续堆叠方向",
    "stage_graph": "Feature阶段图",
    "state_id": "状态ID",
    "state_shape": "状态形态",
    "state_to_effective_multiplier_rule": "状态到生效倍率规则",
    "step_index_semantics": "步骤序号语义",
    "symbol_role_map": "符号角色映射",
    "target_assignment_scope": "目标分配粒度",
    "target_domain": "目标符号域",
    "target_kind": "目标类型",
    "target_node_id": "目标节点ID",
    "terminal_award_binding_rule": "终局奖项绑定规则",
    "terminal_award_rule": "终局派奖规则",
    "terminal_state_domain": "终局状态域",
    "threshold_rule": "阈值规则",
    "tier_domain": "Jackpot等级域",
    "tier_resolution_rule": "Jackpot逐机会唯一层级解析规则",
    "transform_return_binding_rule": "变形结果与回报绑定规则",
    "transition_rule": "状态转移规则",
    "trigger_rule": "触发规则",
    "valid_cell_definition": "有效格定义",
    "valid_cell_layout_domain": "有效格布局域",
    "valid_cell_layout_representation": "有效格布局表示",
    "value_domain": "数值域",
    "value_model": "奖值模型",
    "value_order": "数值顺序",
    "value_source": "奖值来源",
    "value_upgrade_state_binding": "价值符号升级状态绑定",
    "wild_effect_id": "Wild效果ID",
    "wild_effect_scope": "Wild效果作用范围",
    "assisting_cell_identity_rule": "实际参与Wild格身份规则",
    "wild_multiplier_dependency_evidence": "Wild与倍率额外依赖证据",
    "winning_scale_axis_semantics": "中奖规模轴语义",
    "winning_scale_dimension": "中奖规模维度",
    "ways_capacity_mode": "Ways容量组成模式",
    "feature_cycle_owner_node_id": "完整Feature周期Owner节点ID",
    "sequence_boundary_rule": "复合Feature周期边界规则",
    "stage_action_bindings": "阶段类型化动作绑定",
    "transition_resolution_rule": "阶段分支解析规则",
    "return_aggregation_rule": "阶段派奖汇总规则",
    "primary_action_count_rule": "主要动作计数规则",
    "stage_action_count_projection": "路径到主要动作次数投影",
    "player_input_role": "玩家输入角色",
}
PROFILE_VALUE_NAMES_ZH = {
    "none": "无",
    "categorical": "无序类别",
    "ordered_scalar": "有序标量",
    "position_set": "位置集合",
}
PLACEHOLDER_LABEL_PATTERN = re.compile(
    r"(?:联合桶|回报桶|取值桶|时长桶|分布项|类别|奖项)\s*0*\d+(?:$|[^0-9])"
    r"|^(?:item|bucket|category|award)[_-]?0*\d+$",
    re.IGNORECASE,
)

def reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"JSON对象存在重复键: {key}")
        result[key] = value
    return result


def load(path):
    with path.open(encoding="utf-8") as file:
        return json.load(file, object_pairs_hook=reject_duplicate_keys)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def indexed_catalogs(skill_root, kind):
    base = skill_root / "references" / CATALOG_DIRECTORY_NAMES[kind]
    index_path = base / "index.json"
    index = load(index_path)
    catalogs = []
    for entry in index.get("packages", []):
        path = base / entry["path"]
        catalogs.append({"entry": entry, "path": path, "data": load(path)})
    return index, catalogs


def source_fingerprint(skill_root, index_path, catalogs, extra_paths=()):
    paths = [index_path, *(item["path"] for item in catalogs), *extra_paths]
    entries = [(path.relative_to(skill_root).as_posix(), sha256(path)) for path in sorted(paths)]
    payload = "".join(f"{path}\t{digest}\n" for path, digest in entries).encode("utf-8")
    return hashlib.sha256(payload).hexdigest(), entries


def summary_categories(metrics_index):
    categories = []
    for item in sorted(metrics_index.get("categories", []), key=lambda value: value.get("display_order", 999999)):
        categories.append({
            "category_id": item.get("category_id"),
            "name_zh": item.get("name_zh"),
            "description_zh": item.get("description_zh"),
            "source_categories": tuple(item.get("source_categories", [])),
        })
    return categories


def inline(value):
    if value is None or value == "":
        return "—"
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, list):
        return "、".join(inline(item) for item in value) if value else "无"
    if isinstance(value, dict):
        return "；".join(f"{inline(key)}：{inline(value[key])}" for key in sorted(value)) if value else "无"
    return str(value).replace("\n", "<br>")


def markdown(value):
    return inline(value).replace("\\", "\\\\").replace("|", "\\|")


def table(headers, rows):
    if not rows:
        rows = [["无", *("—" for _ in headers[1:])]]
    result = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    result.extend("| " + " | ".join(markdown(value) for value in row) + " |" for row in rows)
    return "\n".join(result)


def mechanic_label(mechanic_id, mechanic_map):
    mechanic = mechanic_map.get(mechanic_id, {})
    name = mechanic.get("name_zh")
    return f"{mechanic_id}（{name}）" if name else mechanic_id


def attribute_label(attribute):
    return f"{PROFILE_ATTRIBUTE_NAMES_ZH[attribute]}（{attribute}）"


def profile_value(value):
    if isinstance(value, str) and value in PROFILE_VALUE_NAMES_ZH:
        return f"{PROFILE_VALUE_NAMES_ZH[value]}（{value}）"
    return inline(value)


def is_placeholder_label(value):
    return isinstance(value, str) and bool(PLACEHOLDER_LABEL_PATTERN.search(value.strip()))


def condition_text(condition, mechanic_map):
    if not isinstance(condition, dict) or not condition:
        return "未配置"
    parts = []
    if condition.get("always") is True:
        parts.append("全部游戏")
    if condition.get("mechanic_id"):
        parts.append(f"命中{mechanic_label(condition['mechanic_id'], mechanic_map)}")
    if condition.get("mechanic_id_any"):
        labels = "、".join(mechanic_label(item, mechanic_map) for item in condition["mechanic_id_any"])
        parts.append(f"命中任一玩法：{labels}")
    if condition.get("mechanic_id_all"):
        labels = "、".join(mechanic_label(item, mechanic_map) for item in condition["mechanic_id_all"])
        parts.append(f"同时命中玩法：{labels}")
    if condition.get("required_attributes"):
        parts.append("需要画像属性：" + "、".join(attribute_label(item) for item in condition["required_attributes"]))
    for item in condition.get("attribute_conditions", []):
        label = mechanic_label(item.get("mechanic_id", ""), mechanic_map)
        operator = OPERATOR_NAMES.get(item.get("operator"), item.get("operator", ""))
        value = "" if item.get("operator") in {"exists", "not_exists", "truthy", "falsy"} else f" {profile_value(item.get('value'))}"
        parts.append(f"{label}的{attribute_label(item.get('attribute'))} {operator}{value}")
    return "；".join(parts) if parts else "未配置"


def anchors_text(profile):
    anchors = []
    for item in profile.get("anchors", []):
        if isinstance(item, dict):
            distance, score = item.get("distance"), item.get("score")
        else:
            distance, score = item[0], item[1]
        anchors.append(f"距离{distance}→{score}分")
    return "；".join(anchors) if anchors else "无"


def relation_targets(relationships):
    keys = (
        "derived_from",
        "conditional_derivation_sources",
        "marginal_of",
        "conditional_on_metric",
        "cross_checks_with",
        "fallback_for",
        "exclusive_with",
    )
    return {key: relationships.get(key, []) for key in keys}


def metric_anchor(metric_id):
    return "metric-" + "".join(char if char.isalnum() else "-" for char in metric_id).strip("-")


def relationship_text(relationships):
    labels = {
        "derived_from": "派生自",
        "conditional_derivation_sources": "满足严格绑定时可派生自",
        "marginal_of": "边际来源",
        "conditional_on_metric": "以前置指标为条件",
        "cross_checks_with": "交叉核对",
        "fallback_for": "后备替代",
        "exclusive_with": "互斥",
    }
    parts = [f"{labels[key]}：{inline(values)}" for key, values in relation_targets(relationships).items() if values]
    parts.append(f"重叠说明：{inline(relationships.get('overlap_reason_zh'))}")
    return "；".join(parts)


def metric_sort_key(item, category_rank):
    metric = item["metric"]
    entry = item["entry"]
    return (
        category_rank.get(metric.get("category"), 999),
        entry.get("display_order", 999999),
        entry.get("package_id", ""),
        metric.get("display_order", 999999),
        metric.get("metric_id", ""),
    )


def collect(skill_root):
    mechanics_index, mechanic_catalogs = indexed_catalogs(skill_root, "mechanics")
    metrics_index, metric_catalogs = indexed_catalogs(skill_root, "metrics")
    mechanics, mechanic_map = [], {}
    for catalog in mechanic_catalogs:
        category = catalog["data"].get("category")
        for mechanic in catalog["data"].get("mechanics", []):
            item = dict(mechanic)
            item["category"] = category
            item["package_id"] = catalog["data"].get("package_id")
            mechanics.append(item)
            mechanic_map[item.get("mechanic_id")] = item
    metrics = []
    for catalog in metric_catalogs:
        for metric in catalog["data"].get("metrics", []):
            metrics.append({"metric": metric, "package": catalog["data"], "entry": catalog["entry"]})
    return mechanics_index, mechanic_catalogs, metrics_index, metric_catalogs, mechanics, mechanic_map, metrics


def validate_sources(mechanics_index, mechanic_catalogs, metrics_index, metric_catalogs, mechanics, metrics):
    errors = []
    for kind, catalogs in (("玩法", mechanic_catalogs), ("指标", metric_catalogs)):
        for item in catalogs:
            entry, data, path = item["entry"], item["data"], item["path"]
            if entry.get("sha256") != sha256(path):
                errors.append(f"{kind}目录索引hash失效：{entry.get('package_id')}")
            if entry.get("package_id") != data.get("package_id"):
                errors.append(f"{kind}目录包ID不一致：{entry.get('package_id')}")
            if entry.get("version") != data.get("version"):
                errors.append(f"{kind}目录包版本不一致：{entry.get('package_id')}")
    mechanic_ids = [item.get("mechanic_id") for item in mechanics]
    if len(mechanic_ids) != len(set(mechanic_ids)):
        errors.append("玩法目录存在重复mechanic_id")
    metric_ids = [item["metric"].get("metric_id") for item in metrics]
    if len(metric_ids) != len(set(metric_ids)):
        errors.append("指标目录存在重复metric_id")
    categories = summary_categories(metrics_index)
    category_membership = {
        source: category["category_id"]
        for category in categories
        for source in category["source_categories"]
    }
    if len(category_membership) != sum(len(category["source_categories"]) for category in categories):
        errors.append("七类阅读映射存在重复source category")
    metric_map = {item["metric"].get("metric_id"): item["metric"] for item in metrics}
    required_display = ("description_zh", "usage_scene_zh", "target_meaning_zh", "display_unit")
    profile_attributes = set()
    for item in metrics:
        metric = item["metric"]
        metric_id = metric.get("metric_id")
        if metric.get("category") not in category_membership:
            errors.append(f"指标未归入七类阅读目录：{metric_id}")
        missing = [field for field in required_display if not str(metric.get("display", {}).get(field, "")).strip()]
        if missing:
            errors.append(f"指标中文阅读字段缺失：{metric_id}/{','.join(missing)}")
        match = metric.get("profile_match", {})
        profile_attributes.update(match.get("required_attributes", []))
        profile_attributes.update(
            condition.get("attribute")
            for condition in match.get("attribute_conditions", [])
            if isinstance(condition, dict) and isinstance(condition.get("attribute"), str)
        )
        display = metric.get("display", {})
        item_labels = display.get("item_labels")
        if item_labels is not None and (
            not isinstance(item_labels, list)
            or not item_labels
            or len(item_labels) != len(set(item_labels))
            or any(not isinstance(label, str) or not label.strip() or is_placeholder_label(label) for label in item_labels)
        ):
            errors.append(f"指标分布项业务标签无效：{metric_id}")
        object_labels = display.get("object_labels")
        object_units = display.get("object_units")
        if object_labels is not None or object_units is not None:
            if (
                not isinstance(object_labels, dict)
                or not isinstance(object_units, dict)
                or not object_labels
                or set(object_labels) != set(object_units)
                or any(not str(value).strip() or is_placeholder_label(value) for value in object_labels.values())
                or any(not str(value).strip() for value in object_units.values())
            ):
                errors.append(f"指标对象字段业务标签或单位不完整：{metric_id}")
        for relation, targets in relation_targets(metric.get("relationships", {})).items():
            for target in targets:
                if target not in metric_map:
                    errors.append(f"指标关系引用不存在：{metric_id}/{relation}/{target}")
    untranslated = sorted(profile_attributes - set(PROFILE_ATTRIBUTE_NAMES_ZH))
    if untranslated:
        errors.append("画像属性缺少中文名称：" + ",".join(untranslated))
    if errors:
        raise ValueError("；".join(errors))


def coverage_rows(mechanics, metric_catalogs, mechanic_map, category_rank):
    package_metrics = {
        item["data"].get("package_id"): item["data"].get("metrics", [])
        for item in metric_catalogs
    }

    def matched_metrics(package_ids, mechanic_id):
        result = {}
        for package_id in package_ids:
            for metric in package_metrics.get(package_id, []):
                if mechanic_id in metric.get("capability_ids", []) or metric.get("profile_match", {}).get("always") is True:
                    result[metric.get("metric_id")] = metric
        return list(result.values())

    def role_count(metrics, roles):
        return sum(metric.get("semantic_role") in roles for metric in metrics)

    rows = []
    for mechanic in sorted(mechanics, key=lambda item: (category_rank.get(item.get("category"), 999), item.get("display_order", 999999), item.get("mechanic_id", ""))):
        requirements = mechanic.get("metric_requirements", {})
        required = requirements.get("required_packages", [])
        conditional = requirements.get("conditional_packages", [])
        conditional_ids = [item.get("package_id") for item in conditional]
        package_ids = [*required, *conditional_ids]
        required_metrics = matched_metrics(required, mechanic.get("mechanic_id"))
        conditional_metrics = matched_metrics(conditional_ids, mechanic.get("mechanic_id"))
        conditional_text = [f"{item.get('package_id')}（{item.get('when')}）" for item in conditional]
        missing = [package_id for package_id in package_ids if package_id not in package_metrics]
        rows.append([
            mechanic.get("category"),
            mechanic_label(mechanic.get("mechanic_id"), mechanic_map),
            required,
            conditional_text,
            f"固定{role_count(required_metrics, {'primary', 'guard_cross_check'})}；条件候选{role_count(conditional_metrics, {'primary', 'guard_cross_check'})}",
            f"固定{role_count(required_metrics, {'audit', 'derived_diagnostic'})}；条件候选{role_count(conditional_metrics, {'audit', 'derived_diagnostic'})}",
            "包ID有效；属性命中由任务合同重算" if not missing else f"缺失：{'、'.join(missing)}",
        ])
    return rows


def canonical_score_profile(profile):
    result = dict(profile)
    if result.get("normalization_tolerance", 1e-6) == 1e-6:
        result.pop("normalization_tolerance", None)
    if result.get("axis_semantics") == "natural_linear":
        result.pop("axis_semantics")
    if result.get("position_transform") == "identity":
        result.pop("position_transform")
    return result


def score_profile_registry(metrics):
    payloads = {
        json.dumps(item["metric"].get("score_profile", {}), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        for item in metrics
        if item["metric"].get("kind") == "score"
    }
    canonical_by_payload = {
        payload: json.dumps(canonical_score_profile(json.loads(payload)), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        for payload in payloads
    }
    canonical_identifiers = {
        payload: f"S{index:02d}"
        for index, payload in enumerate(sorted(set(canonical_by_payload.values())), 1)
    }
    identifiers = {payload: canonical_identifiers[canonical] for payload, canonical in canonical_by_payload.items()}
    rows = []
    for payload, identifier in canonical_identifiers.items():
        profile = json.loads(payload)
        method = profile.get("method")
        details = []
        if "bin_positions_source" in profile:
            details.append("有序桶位置由任务合同密封")
        if "axis_semantics_source" in profile:
            details.append(f"轴语义由玩法画像解析：{profile.get('axis_semantics_source')}")
        transform = profile.get("position_transform", "identity")
        if transform == "log10_1p":
            details.append("位置固定变换为log10(1+x)，不查看候选选择尺度")
        elif "bin_positions_source" in profile and "axis_semantics_source" not in profile:
            details.append("位置保持真实线性业务距离")
        if profile.get("distance_normalization") == "sealed_support_span":
            details.append("距离除以密封支持跨度")
        elif profile.get("distance_normalization") == "fixed_transform_unit":
            details.append("按固定变换单位计距，不再除以极端全跨度")
        if "group_weight_source" in profile:
            details.append("条件组权重由任务合同密封")
        if "support" in profile:
            details.append(f"目录支持值：{inline(profile.get('support'))}")
        if "zero_floor" in profile:
            details.append(f"零值下限：{profile.get('zero_floor')}")
        rows.append([
            identifier,
            METHOD_NAMES.get(method, method),
            METHOD_DESCRIPTIONS.get(method, "按目录合同执行。"),
            anchors_text(profile),
            "；".join(details) or "无额外参数",
        ])
    return identifiers, rows


def evaluation_text(metric, score_profiles):
    kind = metric.get("kind")
    if kind == "score":
        profile = metric.get("score_profile", {})
        payload = json.dumps(profile, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        method = profile.get("method")
        return "；".join([
            f"{KIND_NAMES[kind]}，{METHOD_NAMES.get(method, method)}（评分方案{score_profiles[payload]}）",
            f"评分组：{metric.get('score_group')}，预算键：{metric.get('score_budget_key')}",
            f"默认权重：{metric.get('default_weight')}，作用域汇总：{AGGREGATION_NAMES.get(metric.get('scope_aggregation'), metric.get('scope_aggregation'))}",
        ])
    if kind == "hard":
        profile = metric.get("hard_gate_profile", {})
        method = profile.get("method")
        parts = [
            f"{KIND_NAMES[kind]}，{METHOD_NAMES.get(method, method)}",
            f"容差来源：{profile.get('tolerance_source')}，要求置信资格：{markdown(profile.get('confidence_required'))}",
        ]
        if method in {"wasserstein_1d", "grouped_wasserstein_1d"}:
            axis = profile.get("axis_semantics") or f"画像解析：{profile.get('axis_semantics_source')}"
            scale = profile.get("distance_scale", profile.get("distance_scale_source"))
            parts.append(
                f"有序轴：{axis}，位置变换：{profile.get('position_transform')}，"
                f"距离归一化：{profile.get('distance_normalization')}，尺度：{scale}，距离单位：{profile.get('distance_unit')}"
            )
        return "；".join(parts)
    profile = metric.get("audit_profile", {})
    method = profile.get("method")
    parts = [
        f"{KIND_NAMES.get(kind, kind)}，{METHOD_NAMES.get(method, method)}，不计分",
        f"缺失是否阻塞：{inline(profile.get('blocking_on_missing'))}",
    ]
    if "blocking_on_mismatch" in profile:
        parts.append(f"结果不一致是否阻塞：{inline(profile.get('blocking_on_mismatch'))}")
    if "required_result_status" in profile:
        parts.append(f"要求规则核对状态：{inline(profile.get('required_result_status'))}")
    if "exact_match_fields" in profile:
        parts.append(f"精确比对字段：{inline(profile.get('exact_match_fields'))}")
    if "insufficient_sample_status" in profile:
        parts.append(f"样本不足状态：{inline(profile.get('insufficient_sample_status'))}")
    if "insufficient_sample_blocks_formal" in profile:
        parts.append(f"样本不足是否阻塞FORMAL：{inline(profile.get('insufficient_sample_blocks_formal'))}")
    return "；".join(parts)


def metric_section(item, mechanic_map, score_profiles):
    metric = item["metric"]
    display = metric.get("display", {})
    relationships = metric.get("relationships", {})
    inapplicable = metric.get("inapplicability_reason_codes", [])
    target_text = display.get("target_meaning_zh")
    if display.get("source_zh"):
        target_text = f"{target_text}<br>来源约束：{display.get('source_zh')}"
    lines = [
        f"<a id=\"{metric_anchor(metric.get('metric_id'))}\"></a>",
        f"##### `{metric.get('metric_id')}`｜{metric.get('name_zh')}",
        "",
        table(["阅读项", "内容"], [
            ["指标说明", display.get("description_zh")],
            ["使用场景", display.get("usage_scene_zh")],
            ["目标值统计", target_text],
            ["业务单位", f"{display.get('display_unit')}（机器单位：{metric.get('unit')}）"],
            ["匹配画像", [mechanic_label(value, mechanic_map) for value in metric.get("capability_ids", [])] or "全部游戏"],
            ["精确匹配条件", condition_text(metric.get("profile_match"), mechanic_map)],
            ["样本与作用域", f"样本单位：{metric.get('sample_unit')}<br>作用域：{metric.get('scope_template')}<br>条件：{inline(metric.get('condition_on'))}"],
            ["统计与归一化", f"{inline(metric.get('measurement'))}<br>{inline(metric.get('normalization'))}"],
            ["评价方式", evaluation_text(metric, score_profiles)],
            ["语义归属", f"Owner：{metric.get('owner')}<br>变量：{metric.get('semantic_variable_id')}<br>语义组：{metric.get('semantic_group')}；角色：{ROLE_NAMES.get(metric.get('semantic_role'), metric.get('semantic_role'))}"],
            ["派生与防重复", relationship_text(relationships)],
            ["适用与缺失边界", f"适用：{inline(metric.get('applicability_rule'))}<br>允许不适用原因：{inline(inapplicable) if inapplicable else '无'}<br>缺失处理：{inline(metric.get('missing_policy'))}"],
        ]),
        "",
    ]
    if display.get("item_labels"):
        lines.extend([
            "分布项标签：",
            "",
            table(["序号", "业务标签"], [[index, label] for index, label in enumerate(display["item_labels"], 1)]),
            "",
        ])
    object_labels = display.get("object_labels", {})
    object_units = display.get("object_units", {})
    if object_labels or object_units:
        object_fields = sorted(object_labels)
        lines.extend([
            "对象字段展示：",
            "",
            table(["机器字段", "业务标签", "业务单位"], [
                [field, object_labels[field], object_units[field]]
                for field in object_fields
            ]),
            "",
        ])
    return lines


def generate_summary(skill_root):
    skill_root = skill_root.resolve()
    mechanics_index, mechanic_catalogs, metrics_index, metric_catalogs, mechanics, mechanic_map, metrics = collect(skill_root)
    validate_sources(mechanics_index, mechanic_catalogs, metrics_index, metric_catalogs, mechanics, metrics)
    categories = summary_categories(metrics_index)
    category_rank = {
        category: rank
        for rank, item in enumerate(categories)
        for category in item["source_categories"]
    }
    metrics = sorted(metrics, key=lambda item: metric_sort_key(item, category_rank))
    score_profiles, score_profile_rows = score_profile_registry(metrics)
    generator_path = skill_root / "scripts/generate_metric_summary.py"
    mechanic_schema = skill_root / "assets/schemas/mechanic-catalog.schema.json"
    metric_schema = skill_root / "assets/schemas/metric-catalog.schema.json"
    hard_gate_policy_path = skill_root / "assets/policies/hard_gate_tolerance_policy.v2.json"
    jackpot_materiality_policy_path = skill_root / "assets/policies/jackpot_materiality_policy.v1.json"
    ordered_distance_policy_path = skill_root / "assets/policies/ordered_distance_policy.v1.json"
    score_group_policy_path = skill_root / "assets/policies/score_group_weight_policy.v1.json"
    sample_capability_policy_path = skill_root / "assets/policies/sample_capability_policy.v1.json"
    hard_gate_policy = load(hard_gate_policy_path)
    jackpot_materiality_policy = load(jackpot_materiality_policy_path)
    ordered_distance_policy = load(ordered_distance_policy_path)
    score_group_policy = load(score_group_policy_path)
    sample_capability_policy = load(sample_capability_policy_path)
    mechanic_fingerprint, _ = source_fingerprint(
        skill_root,
        skill_root / "references/玩法画像/index.json",
        mechanic_catalogs,
        (mechanic_schema,),
    )
    metric_fingerprint, _ = source_fingerprint(
        skill_root,
        skill_root / "references/指标目录/index.json",
        metric_catalogs,
        (
            metric_schema,
            hard_gate_policy_path,
            jackpot_materiality_policy_path,
            ordered_distance_policy_path,
            score_group_policy_path,
            sample_capability_policy_path,
        ),
    )

    overview_rows = []
    category_name_by_source = {}
    for category in categories:
        category_name_by_source.update({source: category["name_zh"] for source in category["source_categories"]})
        items = [item["metric"] for item in metrics if item["metric"].get("category") in category["source_categories"]]
        overview_rows.append([
            category["name_zh"],
            "、".join(category["source_categories"]),
            len(items),
            sum(item.get("kind") == "hard" for item in items),
            sum(item.get("kind") == "score" for item in items),
            sum(item.get("kind") == "audit" for item in items),
        ])

    hard_gate_rows = [
        [
            metric_id,
            factor,
            "是" if metric_id in hard_gate_policy.get("locked_metrics", []) else "否",
            "基础容差 × 系数；权威目标本身不得改写",
        ]
        for metric_id, factor in sorted(hard_gate_policy.get("metric_factors", {}).items())
    ]
    group_name_map = score_group_policy.get("group_names_zh", {})
    group_weight_rows = [
        [group, group_name_map.get(group, group), weight, "仅活动组按基础权重重新归一化"]
        for group, weight in sorted(score_group_policy.get("base_weights", {}).items())
    ]
    axis_profile_rows = []
    axis_names = {
        "natural_linear": "自然线性",
        "nonnegative_multiplicative": "非负乘法/长尾",
    }
    for semantics, profile in ordered_distance_policy.get("axis_profiles", {}).items():
        scale = profile.get("distance_scale", profile.get("distance_scale_source"))
        axis_profile_rows.append([
            semantics,
            axis_names.get(semantics, semantics),
            profile.get("position_transform"),
            profile.get("distance_normalization"),
            scale,
            profile.get("distance_unit"),
        ])
    dynamic_axis_rows = [
        [metric_id, rule.get("resolution_source"), " / ".join(rule.get("allowed_axis_semantics", []))]
        for metric_id, rule in sorted(ordered_distance_policy.get("dynamic_axis_metrics", {}).items())
    ]
    quick_index_rows = []
    for item in metrics:
        metric = item["metric"]
        quick_index_rows.append([
            f"[{metric.get('metric_id')}](#{metric_anchor(metric.get('metric_id'))})",
            metric.get("name_zh"),
            category_name_by_source.get(metric.get("category"), metric.get("category")),
            KIND_NAMES.get(metric.get("kind"), metric.get("kind")),
            metric.get("display", {}).get("display_unit"),
        ])

    lines = [
        "# Slot 对齐指标汇总",
        "",
        "> 本文档由`generate_metric_summary.py`从玩法与指标JSON目录确定性生成，禁止手工修改。玩法与指标JSON是唯一事实源。",
        "",
        "## 一、说明与目录指纹",
        "",
        table(["项目", "值"], [
            ["汇总合同", SUMMARY_CONTRACT_VERSION],
            ["玩法目录版本", mechanics_index.get("version")],
            ["玩法目录指纹", mechanic_fingerprint],
            ["指标目录版本", metrics_index.get("version")],
            ["指标目录指纹", metric_fingerprint],
            ["玩法目录Schema SHA-256", sha256(mechanic_schema)],
            ["指标目录Schema SHA-256", sha256(metric_schema)],
            ["硬指标容差政策", f"{hard_gate_policy.get('policy_id')} / {hard_gate_policy.get('version')}"],
            ["硬指标容差政策SHA-256", sha256(hard_gate_policy_path)],
            ["Jackpot物质性政策", f"{jackpot_materiality_policy.get('policy_id')} / {jackpot_materiality_policy.get('version')}"],
            ["Jackpot物质性政策SHA-256", sha256(jackpot_materiality_policy_path)],
            ["有序距离政策", f"{ordered_distance_policy.get('policy_id')} / {ordered_distance_policy.get('version')}"],
            ["有序距离政策SHA-256", sha256(ordered_distance_policy_path)],
            ["评分组权重政策", f"{score_group_policy.get('policy_id')} / {score_group_policy.get('version')}"],
            ["评分组权重政策SHA-256", sha256(score_group_policy_path)],
            ["样本能力政策", f"{sample_capability_policy.get('policy_id')} / {sample_capability_policy.get('version')}"],
            ["样本能力政策SHA-256", sha256(sample_capability_policy_path)],
            ["生成器", generator_path.relative_to(skill_root).as_posix()],
            ["生成器SHA-256", sha256(generator_path)],
            ["玩法数 / 指标数", f"{len(mechanics)} / {len(metrics)}"],
        ]),
        "",
        "阅读规则：先按玩法画像确定适用指标包，再按每项指标的精确画像条件实例化；硬指标负责红线门禁，评分指标进入100分评价，审计指标不计分但保留风险和派生核对。",
        "",
        "边界说明：公共指标目录只解释目标统计语义、目标结构和来源约束；单游戏实际标量、区间或分布目标保存在任务指标合同及阶段2/3/4报告中，不在公共目录预填。",
        "",
        "## 二、分类总览",
        "",
        table(["阅读分类", "目录category", "指标数", "硬指标", "评分指标", "审计指标"], overview_rows),
        "",
        "### 2.1 评价方法与评分方案",
        "",
        "同一评分方案只在本节展开一次；单项指标引用方案编号，避免重复展示相同锚点。距离越小表示越接近原版，具体通过线仍由阶段2任务合同密封。",
        "",
        table(["方案", "评价方法", "怎么理解", "评分锚点", "额外约束"], score_profile_rows),
        "",
        "### 2.2 硬指标容差政策",
        "",
        "硬指标先保留权威目标和基础容差，再按候选出现前密封的固定系数计算生效容差。系数只改变门禁宽度，不得改写目标、目标区间或统计口径。",
        "",
        table(["硬指标ID", "容差系数", "目标是否锁定", "计算规则"], hard_gate_rows),
        "",
        "### 2.3 Jackpot物质性分辨率",
        "",
        "Jackpot层级在候选出现前按统一政策分类：原版命中率达到`jackpot.material_hit_rate`的95分最小正距离锚点，或原版RTP贡献达到当前组件RTP硬门禁容差时，进入正式低维评分；其余极低频且低贡献层级保留逐层审计。",
        "",
        "### 2.4 有序分布距离政策",
        "",
        "次数、长度、格数等自然计数按真实线性位置比较；回报、奖值、倍率和组合容量等长尾量先做固定`log10(1+x)`变换。尺度由指标语义和玩法画像在候选出现前确定，不能看候选结果后切换。",
        "",
        table(["轴语义", "通俗含义", "位置变换", "距离归一化", "尺度", "距离单位"], axis_profile_rows),
        "",
        "以下指标必须由具体玩法画像解析轴语义；同一实例不得混合不同语义或单位：",
        "",
        table(["指标ID", "画像来源", "允许轴语义"], dynamic_axis_rows),
        "",
        "固定长尾指标：" + "、".join(f"`{metric_id}`" for metric_id in ordered_distance_policy.get("fixed_nonnegative_multiplicative_metrics", [])) + "。",
        "",
        "### 2.5 顶层评分组固定政策",
        "",
        "顶层组权重不按指标数量、作用域数量或候选频率分配。阶段2先确定适用且未获批准豁免的活动评分组，再按下表基础预算重新归一化；未知评分组或手工改权重直接阻塞。",
        "",
        table(["评分组", "中文含义", "基础权重", "任务内生成规则"], group_weight_rows),
        "",
        "### 2.6 样本能力门禁",
        "",
        f"采用分布或残差距离的活动硬指标与评分指标，原版和FORMAL两侧都必须达到统一样本能力要求。政策固定使用{sample_capability_policy.get('confidence_level', 0) * 100:g}%置信水平，并按活动条件组同时校正；纯计数不足按用户预授权政策精确豁免对应指标实例，定义、测量、实现或配置异常仍直接阻塞。",
        "",
        "### 2.7 全量指标快速索引",
        "",
        "本表只保留查找所需字段，避免与第四节详情重复；点击指标ID可跳到完整说明。",
        "",
        table(["指标ID", "中文名", "阅读分类", "类型", "业务单位"], quick_index_rows),
        "",
        "## 三、玩法画像目录承接",
        "",
        "本节只核对公共玩法画像能否在目录中找到应有的候选指标及其职责，不代表任何单游戏任务已经命中、实例化或可测。任务实际覆盖率与指标可测率只由阶段2任务指标合同判定。",
        "",
        "### 3.1 目录与任务责任边界",
        "",
        table(["事项", "公共目录负责", "阶段2任务指标合同负责"], [
            ["Primary / Guard", "登记主Owner、守卫关系、适用画像和候选指标包", "按本游戏画像实例化，并确认目标、样本、作用域和测量输出"],
            ["Audit / 派生", "登记不计分的风险审计、派生关系和重叠理由", "确认上游证据是否存在，并保留适用审计项及状态传播"],
            ["条件命中", "登记条件指标包及画像条件", "依据本游戏证据判定是否命中；未命中不能算已加载"],
            ["退化 / 不适用", "登记适用规则、缺失策略和退化处理语义", "密封实际可达支持，并给出不适用原因码和证据"],
            ["可测性与100%", "登记统计公式、样本单位、归一化和评价方法", "验证统计脚本确实产出所需字段；必需覆盖率和指标可测率达到100%或存在有效豁免"],
        ]),
        "",
        "### 3.2 目录承接矩阵",
        "",
        table(["机器分类", "玩法画像", "固定承接包", "条件候选包（仅命中后）", "候选主/守卫目录项", "候选审计/派生目录项", "目录引用状态"], coverage_rows(mechanics, metric_catalogs, mechanic_map, category_rank)),
        "",
        "审计/派生目录项数量不属于Primary/Guard正式数值覆盖。Jackpot命中率、动态奖值等低频数值项只有在规则一致性和资料门禁通过后才进入审计展示，仍不计分；规则资料缺失或不一致由阻塞型规则审计处理。",
        "",
        "## 四、七类指标逐项详情",
        "",
    ]

    for index, category in enumerate(categories, 1):
        category_items = [item for item in metrics if item["metric"].get("category") in category["source_categories"]]
        lines.extend([
            f"<a id=\"category-{category['category_id']}\"></a>",
            f"### 4.{index} {category['name_zh']}",
            "",
            category["description_zh"],
            "",
            table(["指标ID", "中文名", "类型", "指标包"], [
                [item["metric"].get("metric_id"), item["metric"].get("name_zh"), KIND_NAMES.get(item["metric"].get("kind"), item["metric"].get("kind")), item["package"].get("package_id")]
                for item in category_items
            ]),
            "",
        ])
        if not category_items:
            lines.extend(["无已登记指标。", ""])
        package_groups = []
        for item in category_items:
            package_id = item["package"].get("package_id")
            if not package_groups or package_groups[-1][0] != package_id:
                package_groups.append((package_id, []))
            package_groups[-1][1].append(item)
        for package_index, (package_id, package_items) in enumerate(package_groups, 1):
            package = package_items[0]["package"]
            lines.extend([
                f"#### 4.{index}.{package_index} `{package_id}`",
                "",
                table(["指标包字段", "内容"], [
                    ["包类型 / 机器分类", f"{package.get('type')} / {package.get('category')}"],
                    ["加载条件", condition_text(package.get("applies_when"), mechanic_map)],
                    ["版本 / 指标数", f"{package.get('version')} / {len(package_items)}"],
                ]),
                "",
            ])
            for item in package_items:
                lines.extend(metric_section(item, mechanic_map, score_profiles))

    relation_labels = {
        "derived_from": "派生自",
        "conditional_derivation_sources": "严格绑定后可派生自",
        "marginal_of": "属于其边际",
        "conditional_on_metric": "以前置指标为条件",
        "cross_checks_with": "交叉核对",
        "exclusive_with": "互斥Owner",
        "fallback_for": "后备承接",
    }
    relation_rows = []
    for item in metrics:
        metric = item["metric"]
        relationships = metric.get("relationships", {})
        targets = relation_targets(relationships)
        if any(targets.values()) or metric.get("semantic_role") != "primary":
            navigation = "<br>".join(
                f"{relation_labels[key]}：{'、'.join(values)}"
                for key, values in targets.items()
                if values
            ) or "无跨指标关系"
            relation_rows.append([
                metric.get("metric_id"),
                ROLE_NAMES.get(metric.get("semantic_role"), metric.get("semantic_role")),
                navigation,
                "不参与评分" if metric.get("kind") != "score" else "独立评分",
            ])
    lines.extend([
        "## 五、派生关系与防重复计分导航",
        "",
        "本节只提供关系跳转，不重复第四节已经逐项说明的Owner边界、重叠原因和使用条件。",
        "",
        table(["指标ID", "语义角色", "关系导航", "计分状态"], relation_rows),
        "",
        "## 六、主动忽略范围",
        "",
        "- 不声明覆盖未进入玩法语义目录的冷门机制；需要时先扩展玩法画像和指标Owner。",
        "- Gamble/Double-Up、现金退出、真实技巧选择等由玩家策略改变数学结果的玩法不纳入通用Slot指标包，遇到时必须单独建模决策策略。",
        "- 非Cascade/Respin的Reel Nudge、强同步Linked Reels、外部社区或网络累进事件不默认加载；只有目标游戏确实存在且能取得权威联合证据时才提出条件扩展。",
        "- 标准Walking Wild已由Wild替代、position_set持久状态及按数量转移分组的一一配对位置移动残差覆盖；该残差只评价扣除候选起点与终点边际后的配对耦合。对象会出生、消失、合并、拆分，或多个对象同时携带独立位置奖值、等级等高维身份时才提出任务级扩展，不用完整状态签名硬凑。",
        "- Hold & Spin不保存奖值×具体位置×完整终局盘面的高维联合签名；具体位置确实改变奖值规则且现有位置、奖值、Collect与终局账本Owner不足时，才提出任务级扩展。续命数量含独立RNG时同样单独扩展，不用默认剩余次数分布重复放大时长偏差。",
        "- 多格Mystery由低维目标一致性残差承接主流的整批共享与逐格独立差异，不保存完整目标向量或完整变形后盘面签名。",
        "- Wheel动画、扇区邻接近门槛、纯展示停点及reveal-only玩家选择频率不进入通用数学指标；玩家选择真实改变概率时按决策策略玩法单独建模。",
        "- 同容量Megaways布局的回报依赖、Cascade布局转移及补充符号高阶空间相关不默认加载；只有原版证据证明容量、布局、补充符号和现有回报Owner不足时才条件扩展。",
        "- 不把完整盘面签名分布作为通用硬门禁，避免高维稀疏与有限样本过拟合。",
        "- 极低频且样本不足的长尾组合只按目录定义审计，不伪造精确评分目标。",
        "- 无法由原版证据、规格或实现证明的维度不猜测，按对应指标的缺失策略处理。",
        "",
        "## 七、维护方法",
        "",
        "1. 在对应玩法或指标`catalog.json`中维护唯一事实，补齐画像、语义、测量、评价和关系字段。",
        "2. 更新相应`index.json`中的版本与目录SHA-256。",
        "3. 重新生成本汇总文档。",
        "4. 执行严格目录校验；汇总缺项、过期、画像引用失效、目录承接缺口或重复计分都会失败。",
        "5. 在每个单游戏任务的阶段2合同中另行验证实际命中、退化、不适用、必需覆盖率和指标可测率。",
        "",
        "```bash",
        "<python_bin> <skill_root>/scripts/generate_metric_summary.py --skill-root <skill_root>",
        "<python_bin> <skill_root>/scripts/catalog_tool.py validate --skill-root <skill_root>",
        "```",
        "",
    ])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="从玩法与指标JSON目录确定性生成全量中文指标汇总")
    parser.add_argument("--skill-root", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or args.skill_root / SUMMARY_RELATIVE_PATH
    try:
        text = generate_summary(args.skill_root)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"指标汇总生成失败：{exc}")
        return 1
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")
    try:
        display_path = output.resolve().relative_to(args.skill_root.resolve()).as_posix()
    except ValueError:
        display_path = output.name
    print(f"指标汇总已生成：{display_path}（SHA-256：{sha256(output)}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
