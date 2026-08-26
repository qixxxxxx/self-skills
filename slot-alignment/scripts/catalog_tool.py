#!/usr/bin/env python3
import argparse
import hashlib
import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path

from generate_metric_summary import SUMMARY_RELATIVE_PATH, generate_summary, is_placeholder_label

try:
    from jsonschema import Draft202012Validator
except ModuleNotFoundError:
    Draft202012Validator = None


SUPPORTED_SCORE_METHODS = {
    "absolute_error",
    "relative_error",
    "range_error",
    "total_variation",
    "mean_absolute_error",
    "max_absolute_error",
    "grouped_mean_absolute_error",
    "grouped_total_variation",
    "wasserstein_1d",
    "grouped_wasserstein_1d",
}
ORDERED_METHODS = {"wasserstein_1d", "grouped_wasserstein_1d"}
GROUPED_DISTRIBUTION_METHODS = {"grouped_total_variation", "grouped_wasserstein_1d"}
MECHANIC_CATEGORIES = {"settlement", "board", "evolution", "feature", "trigger", "modifier", "award", "state"}
METRIC_CATEGORIES = MECHANIC_CATEGORIES | {"core", "interaction"}
CATALOG_DIRECTORY_NAMES = {
    "mechanics": "玩法画像",
    "metrics": "指标目录",
}
SEMANTIC_ROLES = {"primary", "guard_cross_check", "derived_diagnostic", "audit"}
SCOPE_AGGREGATIONS = {"weighted_mean", "minimum"}
CONDITION_KEYS = {"always", "mechanic_id", "mechanic_id_any", "mechanic_id_all", "required_attributes", "attribute_conditions"}
ATTRIBUTE_OPERATORS = {"exists", "not_exists", "equals", "not_equals", "in", "not_in", "contains", "gt", "gte", "lt", "lte", "truthy", "falsy"}
VALUE_OPERATORS = {"equals", "not_equals", "in", "not_in", "contains", "gt", "gte", "lt", "lte"}
RELATION_KEYS = {
    "derived_from",
    "conditional_derivation_sources",
    "marginal_of",
    "conditional_on_metric",
    "cross_checks_with",
    "fallback_for",
    "exclusive_with",
}
ABSOLUTE_PATH_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_.-])/(?:Users|home|var|private|tmp|Volumes|opt|root|mnt|srv|etc|usr|workspace|workspaces|data|app)(?:/|\b)"
    r"|[A-Za-z]:[\\/]"
    r"|\\{2,}[^\\\s]+\\{1,}[^\\\s]+"
)
METRIC_REQUIRED_FIELDS = {
    "metric_id",
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
    "capability_ids",
    "profile_match",
    "semantic_variable_id",
    "semantic_group",
    "semantic_role",
    "relationships",
    "display",
}
DISPLAY_FIELDS = {"description_zh", "usage_scene_zh", "target_meaning_zh", "display_unit"}
SCORE_FIELDS = {"score_group", "score_budget_key", "scope_aggregation", "default_weight", "score_profile"}
TEXT_METRIC_FIELDS = {
    "metric_id",
    "name_zh",
    "owner",
    "category",
    "unit",
    "scope_template",
    "measurement",
    "sample_unit",
    "applicability_rule",
    "missing_policy",
    "semantic_variable_id",
    "semantic_group",
    "semantic_role",
}


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


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def non_empty_text(value):
    return isinstance(value, str) and bool(value.strip())


def finite_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def safe_entry_path(base, value, errors, label):
    if not non_empty_text(value):
        errors.append(f"{label}路径缺失")
        return None
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        errors.append(f"{label}路径不是安全相对路径: {value}")
        return None
    path = (base / relative).resolve()
    try:
        path.relative_to(base.resolve())
    except ValueError:
        errors.append(f"{label}路径越出目录: {value}")
        return None
    return path


def read_json(path, errors, label):
    try:
        return load(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"{label}无法读取: {path} / {exc}")
        return None


def validate_with_schema(data, schema, label, errors):
    if Draft202012Validator is None:
        errors.append("缺少jsonschema依赖，无法执行Draft 2020-12目录校验")
        return
    try:
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
    except Exception as exc:
        errors.append(f"{label}Schema无效: {exc}")
        return
    for error in sorted(validator.iter_errors(data), key=lambda item: tuple(str(part) for part in item.absolute_path)):
        path = ".".join(str(part) for part in error.absolute_path) or "$"
        errors.append(f"{label}不符合Schema: {path} / {error.message}")


def indexed_records(root, kind, errors):
    directory_name = CATALOG_DIRECTORY_NAMES[kind]
    base = root / "references" / directory_name
    index_path, index_md = base / "index.json", base / "index.md"
    files = [index_path, index_md]
    if not index_path.is_file():
        errors.append(f"缺少目录索引: {index_path}")
        return {}, [], files
    if not index_md.is_file():
        errors.append(f"缺少中文目录索引: {index_md}")
    index = read_json(index_path, errors, f"{kind}索引") or {}
    packages = index.get("packages")
    if not isinstance(packages, list):
        errors.append(f"{kind}索引packages不是数组")
        packages = []
    actual_paths = {path.relative_to(base).as_posix() for path in base.rglob("catalog.json")}
    indexed_paths, package_ids, records = set(), set(), []
    for position, entry in enumerate(packages, 1):
        label = f"{kind}索引第{position}项"
        if not isinstance(entry, dict):
            errors.append(f"{label}不是对象")
            continue
        package_id = entry.get("package_id")
        if not non_empty_text(package_id):
            errors.append(f"{label}缺少package_id")
        elif package_id in package_ids:
            errors.append(f"package_id重复: {package_id}")
        package_ids.add(package_id)
        path = safe_entry_path(base, entry.get("path"), errors, label)
        if path is None:
            continue
        relative = path.relative_to(base.resolve()).as_posix()
        if relative in indexed_paths:
            errors.append(f"目录路径重复: {relative}")
        indexed_paths.add(relative)
        md = path.with_name("catalog.md")
        files.extend([path, md])
        if not path.is_file() or not md.is_file():
            errors.append(f"缺少目录文件: {relative} 或 {md.relative_to(root) if md.is_absolute() else md}")
            continue
        data = read_json(path, errors, f"目录包{package_id}")
        if data is None:
            continue
        records.append({"entry": entry, "path": path, "md": md, "data": data})
    for relative in sorted(actual_paths - indexed_paths):
        errors.append(f"存在未写入索引的目录包: references/{directory_name}/{relative}")
    for relative in sorted(indexed_paths - actual_paths):
        errors.append(f"索引引用了不存在的目录包: references/{directory_name}/{relative}")
    return index, records, files


def validate_record_identity(record, kind, errors):
    entry, data, path, md = record["entry"], record["data"], record["path"], record["md"]
    expected_catalog_type = "mechanic_package" if kind == "mechanics" else "metric_package"
    if data.get("catalog_type") != expected_catalog_type:
        errors.append(f"catalog_type错误: {path}")
    for field in ("package_id", "version", "category"):
        if entry.get(field) != data.get(field):
            errors.append(f"{field}与索引不一致: {path}")
    if kind == "metrics":
        for field in ("type", "applies_when"):
            if entry.get(field) != data.get(field):
                errors.append(f"{field}与索引不一致: {path}")
    if entry.get("sha256") != digest(path):
        errors.append(f"目录hash与索引不一致: {path}")
    if kind == "metrics":
        match = re.search(r"^版本：([^\s]+)\s*$", md.read_text(encoding="utf-8"), re.MULTILINE)
        if match is None:
            errors.append(f"指标中文目录缺少版本号: {md}")
        elif match.group(1) != data.get("version"):
            errors.append(f"指标中文目录版本与JSON不一致: {md}")


def validate_mechanics(records, errors):
    mechanic_map, seen = {}, set()
    for record in records:
        data, md = record["data"], record["md"]
        if data.get("category") not in MECHANIC_CATEGORIES:
            errors.append(f"玩法包category无效: {data.get('package_id')} / {data.get('category')}")
        mechanics = data.get("mechanics")
        if not isinstance(mechanics, list) or not mechanics:
            errors.append(f"玩法包mechanics为空: {data.get('package_id')}")
            continue
        text = md.read_text(encoding="utf-8")
        for mechanic in mechanics:
            mechanic_id = mechanic.get("mechanic_id") if isinstance(mechanic, dict) else None
            if not non_empty_text(mechanic_id) or mechanic_id in seen:
                errors.append(f"mechanic_id缺失或重复: {mechanic_id}")
                continue
            seen.add(mechanic_id)
            mechanic_map[mechanic_id] = mechanic
            if mechanic_id not in text:
                errors.append(f"中文目录未说明 {mechanic_id}: {md}")
            required = {"mechanic_id", "name_zh", "display_order", "definition", "required_attributes", "optional_attributes", "evidence_signatures", "exclusions", "metric_requirements"}
            missing = sorted(required - set(mechanic))
            if missing:
                errors.append(f"玩法字段缺失: {mechanic_id} / {','.join(missing)}")
            for field in ("mechanic_id", "name_zh", "definition"):
                if not non_empty_text(mechanic.get(field)):
                    errors.append(f"玩法字段为空: {mechanic_id} / {field}")
            order = mechanic.get("display_order")
            if not isinstance(order, int) or isinstance(order, bool) or order < 0:
                errors.append(f"玩法display_order无效: {mechanic_id}")
            attributes = set()
            for field in ("required_attributes", "optional_attributes", "evidence_signatures", "exclusions"):
                values = mechanic.get(field)
                if not isinstance(values, list) or any(not non_empty_text(item) for item in values):
                    errors.append(f"玩法数组字段无效: {mechanic_id} / {field}")
                    continue
                if len(values) != len(set(values)):
                    errors.append(f"玩法数组字段存在重复项: {mechanic_id} / {field}")
                if field in {"required_attributes", "optional_attributes"}:
                    overlap = attributes.intersection(values)
                    if overlap:
                        errors.append(f"玩法属性同时为必需和可选: {mechanic_id} / {','.join(sorted(overlap))}")
                    attributes.update(values)
            requirements = mechanic.get("metric_requirements")
            if not isinstance(requirements, dict):
                errors.append(f"玩法metric_requirements无效: {mechanic_id}")
                continue
            required_packages = requirements.get("required_packages")
            conditional_packages = requirements.get("conditional_packages")
            if not isinstance(required_packages, list) or any(not non_empty_text(item) for item in required_packages):
                errors.append(f"玩法required_packages无效: {mechanic_id}")
                required_packages = []
            if len(required_packages) != len(set(required_packages)):
                errors.append(f"玩法required_packages存在重复项: {mechanic_id}")
            if not isinstance(conditional_packages, list):
                errors.append(f"玩法conditional_packages无效: {mechanic_id}")
                conditional_packages = []
            conditional_ids = []
            for item in conditional_packages:
                if not isinstance(item, dict) or not non_empty_text(item.get("package_id")) or not non_empty_text(item.get("when")):
                    errors.append(f"玩法条件指标包无效: {mechanic_id}")
                    continue
                conditional_ids.append(item["package_id"])
            if len(conditional_ids) != len(set(conditional_ids)):
                errors.append(f"玩法conditional_packages存在重复项: {mechanic_id}")
            overlap = set(required_packages).intersection(conditional_ids)
            if overlap:
                errors.append(f"玩法指标包同时为必需和条件项: {mechanic_id} / {','.join(sorted(overlap))}")
    return mechanic_map


def condition_ids(condition):
    if not isinstance(condition, dict):
        return set()
    result = set()
    if condition.get("mechanic_id"):
        result.add(condition["mechanic_id"])
    for field in ("mechanic_id_any", "mechanic_id_all"):
        values = condition.get(field)
        if isinstance(values, list):
            result.update(values)
    for item in condition.get("attribute_conditions", []) if isinstance(condition.get("attribute_conditions", []), list) else []:
        if isinstance(item, dict) and item.get("mechanic_id"):
            result.add(item["mechanic_id"])
    return result


def mechanic_attributes(mechanic):
    if not isinstance(mechanic, dict):
        return set()
    return set(mechanic.get("required_attributes", [])) | set(mechanic.get("optional_attributes", []))


def validate_condition(condition, label, mechanic_map, errors):
    if not isinstance(condition, dict) or not condition:
        errors.append(f"画像匹配条件为空: {label}")
        return set()
    unknown = sorted(set(condition) - CONDITION_KEYS)
    if unknown:
        errors.append(f"画像匹配条件存在未知字段: {label} / {','.join(unknown)}")
    selectors = [key for key in ("always", "mechanic_id", "mechanic_id_any", "mechanic_id_all", "attribute_conditions") if key in condition]
    if not selectors:
        errors.append(f"画像匹配条件缺少玩法选择器: {label}")
    if "always" in condition and condition.get("always") is not True:
        errors.append(f"画像匹配always必须为true: {label}")
    if condition.get("always") is True and any(key in condition for key in ("mechanic_id", "mechanic_id_any", "mechanic_id_all", "attribute_conditions")):
        errors.append(f"画像匹配always不能与其他选择器并用: {label}")
    mechanic_selectors = [key for key in ("mechanic_id", "mechanic_id_any", "mechanic_id_all") if key in condition]
    if len(mechanic_selectors) > 1:
        errors.append(f"画像匹配玩法选择器只能使用一个: {label} / {','.join(mechanic_selectors)}")
    mechanic_id = condition.get("mechanic_id")
    if mechanic_id is not None and not non_empty_text(mechanic_id):
        errors.append(f"mechanic_id无效: {label}")
    for field in ("mechanic_id_any", "mechanic_id_all"):
        values = condition.get(field)
        if values is not None and (not isinstance(values, list) or not values or any(not non_empty_text(item) for item in values)):
            errors.append(f"{field}无效: {label}")
        elif isinstance(values, list) and len(values) != len(set(values)):
            errors.append(f"{field}存在重复项: {label}")
    ids = condition_ids(condition)
    for value in sorted(ids):
        if value not in mechanic_map:
            errors.append(f"画像引用未知mechanic_id: {label} / {value}")
    required_attributes = condition.get("required_attributes")
    if required_attributes is not None:
        if not isinstance(required_attributes, list) or not required_attributes or any(not non_empty_text(item) for item in required_attributes):
            errors.append(f"required_attributes无效: {label}")
        else:
            available = set().union(*(mechanic_attributes(mechanic_map.get(value)) for value in ids)) if ids else set()
            for attribute in required_attributes:
                if attribute not in available:
                    errors.append(f"画像引用未知属性: {label} / {attribute}")
    attribute_conditions = condition.get("attribute_conditions")
    if attribute_conditions is not None:
        if not isinstance(attribute_conditions, list) or not attribute_conditions:
            errors.append(f"attribute_conditions无效: {label}")
        else:
            for position, item in enumerate(attribute_conditions, 1):
                item_label = f"{label}.attribute_conditions[{position}]"
                if not isinstance(item, dict):
                    errors.append(f"属性条件不是对象: {item_label}")
                    continue
                ref = item.get("mechanic_id")
                attribute = item.get("attribute")
                operator = item.get("operator")
                if ref not in mechanic_map:
                    errors.append(f"属性条件引用未知mechanic_id: {item_label} / {ref}")
                elif attribute not in mechanic_attributes(mechanic_map[ref]):
                    errors.append(f"属性条件引用未知属性: {item_label} / {attribute}")
                if operator not in ATTRIBUTE_OPERATORS:
                    errors.append(f"属性条件操作符无效: {item_label} / {operator}")
                if operator in VALUE_OPERATORS and "value" not in item:
                    errors.append(f"属性条件缺少value: {item_label}")
    return ids


def condition_mechanic_alternatives(condition):
    """把画像条件转换成“满足条件时必然存在的玩法集合”析取项。"""
    if not isinstance(condition, dict):
        return []
    if condition.get("always") is True:
        alternatives = [set()]
    elif non_empty_text(condition.get("mechanic_id")):
        alternatives = [{condition["mechanic_id"]}]
    elif isinstance(condition.get("mechanic_id_all"), list):
        alternatives = [set(condition["mechanic_id_all"])]
    elif isinstance(condition.get("mechanic_id_any"), list):
        alternatives = [{item} for item in condition["mechanic_id_any"]]
    else:
        alternatives = [set()]
    attribute_mechanics = {
        item.get("mechanic_id")
        for item in condition.get("attribute_conditions", [])
        if isinstance(item, dict) and non_empty_text(item.get("mechanic_id"))
    }
    return [alternative | attribute_mechanics for alternative in alternatives]


def guaranteed_attributes(condition):
    result = set(condition.get("required_attributes", [])) if isinstance(condition, dict) else set()
    for item in condition.get("attribute_conditions", []) if isinstance(condition, dict) else []:
        if isinstance(item, dict) and item.get("operator") != "not_exists" and non_empty_text(item.get("attribute")):
            result.add(item["attribute"])
    return result


def normalized_attribute_conditions(condition):
    result = set()
    for item in condition.get("attribute_conditions", []) if isinstance(condition, dict) else []:
        if isinstance(item, dict):
            result.add(json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return result


def condition_implies(metric_condition, package_condition):
    """判断更精确的指标条件是否必然满足所属包条件。"""
    if not isinstance(metric_condition, dict) or not isinstance(package_condition, dict):
        return False
    if package_condition.get("always") is True:
        return True
    if metric_condition.get("always") is True:
        return False
    metric_alternatives = condition_mechanic_alternatives(metric_condition)
    package_alternatives = condition_mechanic_alternatives(package_condition)
    if not metric_alternatives or not package_alternatives:
        return False
    mechanics_imply = all(
        any(package_required.issubset(metric_required) for package_required in package_alternatives)
        for metric_required in metric_alternatives
    )
    attributes_imply = guaranteed_attributes(package_condition).issubset(guaranteed_attributes(metric_condition))
    package_attribute_conditions = normalized_attribute_conditions(package_condition)
    conditions_imply = package_attribute_conditions.issubset(normalized_attribute_conditions(metric_condition))
    return mechanics_imply and attributes_imply and conditions_imply


def anchor_pair(item):
    if isinstance(item, dict):
        return item.get("distance"), item.get("score")
    if isinstance(item, list) and len(item) == 2:
        return item[0], item[1]
    return None, None


def validate_ordered_profile(metric_id, profile, errors):
    method = profile.get("method") if isinstance(profile, dict) else None
    if method not in ORDERED_METHODS:
        return
    if profile.get("bin_positions_source") != "task_contract":
        errors.append(f"{method}必须从task_contract密封bin_positions: {metric_id}")
    axis_source = profile.get("axis_semantics_source")
    if axis_source is not None:
        if not non_empty_text(axis_source):
            errors.append(f"{method}的axis_semantics_source无效: {metric_id}")
        forbidden = {
            "axis_semantics", "ordered_distance_policy_id", "position_transform",
            "distance_normalization", "distance_scale", "distance_scale_source", "distance_unit",
        } & set(profile)
        if forbidden:
            errors.append(f"动态有序指标公共目录不得提前写死距离轴字段: {metric_id} / {','.join(sorted(forbidden))}")
    else:
        transform = profile.get("position_transform", "identity")
        normalization = profile.get("distance_normalization")
        if transform == "identity" and normalization != "sealed_support_span":
            errors.append(f"{method}线性位置必须使用sealed_support_span归一化: {metric_id}")
        elif transform == "log10_1p" and normalization != "fixed_transform_unit":
            errors.append(f"{method}长尾位置必须使用fixed_transform_unit: {metric_id}")
        elif transform not in {"identity", "log10_1p"}:
            errors.append(f"{method}的position_transform无效: {metric_id} / {transform}")
        if transform == "log10_1p" and (
            profile.get("axis_semantics") != "nonnegative_multiplicative"
            or profile.get("distance_scale") != 1
            or profile.get("distance_unit") != "log10_decade"
        ):
            errors.append(f"{method}长尾轴必须密封乘法语义、单位尺度1和log10_decade: {metric_id}")
        if transform == "identity" and profile.get("axis_semantics") not in {None, "natural_linear"}:
            errors.append(f"{method}线性轴语义无效: {metric_id}")
    if method == "grouped_wasserstein_1d" and "bin_positions_by_group" in profile:
        errors.append(f"公共指标目录不得密封实际bin_positions_by_group: {metric_id}")


def validate_score_profile(metric_id, profile, errors):
    if not isinstance(profile, dict):
        errors.append(f"评分指标score_profile无效: {metric_id}")
        return
    method = profile.get("method")
    if method not in SUPPORTED_SCORE_METHODS:
        errors.append(f"评分指标距离方法不受支持: {metric_id} / {method}")
    tolerance = profile.get("normalization_tolerance")
    if tolerance is not None and (not finite_number(tolerance) or tolerance < 0 or tolerance >= 1):
        errors.append(f"评分指标normalization_tolerance必须在[0,1)内: {metric_id}")
    validate_ordered_profile(metric_id, profile, errors)
    if method in {"grouped_mean_absolute_error", "grouped_total_variation", "grouped_wasserstein_1d"}:
        if profile.get("group_weight_source") != "task_contract":
            errors.append(f"{method}必须从task_contract密封组权重: {metric_id}")
        if not non_empty_text(profile.get("group_separator")):
            errors.append(f"{method}缺少group_separator: {metric_id}")
        if tolerance is None:
            errors.append(f"{method}缺少normalization_tolerance: {metric_id}")
        if "group_weights" in profile:
            errors.append(f"公共指标目录不得密封实际group_weights: {metric_id}")
    anchors = profile.get("anchors")
    if not isinstance(anchors, list) or len(anchors) < 2:
        errors.append(f"评分指标锚点不足: {metric_id}")
        return
    points = [anchor_pair(item) for item in anchors]
    if any(not finite_number(distance) or not finite_number(score) for distance, score in points):
        errors.append(f"评分指标锚点不是有限数值: {metric_id}")
        return
    if any(distance < 0 for distance, _ in points):
        errors.append(f"评分指标锚点距离小于0: {metric_id}")
    if any(score < 0 or score > 100 for _, score in points):
        errors.append(f"评分指标锚点分数超出0至100: {metric_id}")
    if any(right[0] <= left[0] for left, right in zip(points, points[1:])):
        errors.append(f"评分指标锚点距离未严格递增: {metric_id}")
    if any(right[1] >= left[1] for left, right in zip(points, points[1:])):
        errors.append(f"评分指标锚点分数未严格递减: {metric_id}")
    if points[0] != (0, 100):
        errors.append(f"评分指标首锚点必须为距离0、得分100: {metric_id}")


def validate_metrics(records, mechanic_map, errors):
    metric_map, package_map, seen = {}, {}, set()
    for record in records:
        data, md = record["data"], record["md"]
        package_id = data.get("package_id")
        package_map[package_id] = data
        package_category = data.get("category")
        if package_category not in METRIC_CATEGORIES:
            errors.append(f"指标包category无效: {package_id} / {package_category}")
        package_condition = data.get("applies_when")
        package_ids = validate_condition(package_condition, f"指标包{package_id}.applies_when", mechanic_map, errors)
        metrics = data.get("metrics")
        if not isinstance(metrics, list) or not metrics:
            errors.append(f"指标包metrics为空: {package_id}")
            continue
        text = md.read_text(encoding="utf-8")
        for metric in metrics:
            metric_id = metric.get("metric_id") if isinstance(metric, dict) else None
            if not non_empty_text(metric_id) or metric_id in seen:
                errors.append(f"metric_id缺失或重复: {metric_id}")
                continue
            seen.add(metric_id)
            metric_map[metric_id] = metric
            if metric_id not in text:
                errors.append(f"中文目录未说明 {metric_id}: {md}")
            missing = sorted(METRIC_REQUIRED_FIELDS - set(metric))
            if missing:
                errors.append(f"指标字段缺失: {metric_id} / {','.join(missing)}")
            for field in TEXT_METRIC_FIELDS:
                if field in metric and not non_empty_text(metric.get(field)):
                    errors.append(f"指标字段为空: {metric_id} / {field}")
            if metric.get("owner") != package_id:
                errors.append(f"Owner不等于所属包: {metric_id}")
            if metric.get("category") not in METRIC_CATEGORIES:
                errors.append(f"指标category无效: {metric_id} / {metric.get('category')}")
            elif metric.get("category") != package_category:
                errors.append(f"指标category与所属包不一致: {metric_id} / {metric.get('category')} != {package_category}")
            order = metric.get("display_order")
            if not isinstance(order, int) or isinstance(order, bool) or order < 0:
                errors.append(f"指标display_order无效: {metric_id}")
            condition_on = metric.get("condition_on")
            if not (non_empty_text(condition_on) or isinstance(condition_on, list) and condition_on and all(non_empty_text(item) for item in condition_on)):
                errors.append(f"指标condition_on无效: {metric_id}")
            normalization = metric.get("normalization")
            if not (non_empty_text(normalization) or isinstance(normalization, dict) and normalization):
                errors.append(f"指标normalization无效: {metric_id}")
            display = metric.get("display")
            if not isinstance(display, dict):
                errors.append(f"指标display无效: {metric_id}")
            else:
                display_missing = sorted(DISPLAY_FIELDS - set(display))
                if display_missing:
                    errors.append(f"指标展示元数据缺失: {metric_id} / {','.join(display_missing)}")
                for field in DISPLAY_FIELDS:
                    if field in display and not non_empty_text(display.get(field)):
                        errors.append(f"指标展示元数据为空: {metric_id} / {field}")
                item_labels = display.get("item_labels")
                if item_labels is not None and (
                    not isinstance(item_labels, list)
                    or not item_labels
                    or len(item_labels) != len(set(item_labels))
                    or any(not non_empty_text(label) or is_placeholder_label(label) for label in item_labels)
                ):
                    errors.append(f"指标分布项业务标签无效或使用占位标签: {metric_id}")
                object_labels = display.get("object_labels")
                object_units = display.get("object_units")
                if object_labels is not None or object_units is not None:
                    if (
                        not isinstance(object_labels, dict)
                        or not isinstance(object_units, dict)
                        or not object_labels
                        or set(object_labels) != set(object_units)
                        or any(not non_empty_text(value) or is_placeholder_label(value) for value in object_labels.values())
                        or any(not non_empty_text(value) for value in object_units.values())
                    ):
                        errors.append(f"指标对象字段业务标签与单位必须完整一一对应: {metric_id}")
            capabilities = metric.get("capability_ids")
            if not isinstance(capabilities, list) or any(not non_empty_text(item) for item in capabilities):
                errors.append(f"指标capability_ids无效: {metric_id}")
                capabilities = []
            elif len(capabilities) != len(set(capabilities)):
                errors.append(f"指标capability_ids存在重复项: {metric_id}")
            for capability_id in capabilities:
                if capability_id not in mechanic_map:
                    errors.append(f"指标capability_ids引用未知mechanic_id: {metric_id} / {capability_id}")
            match_ids = validate_condition(metric.get("profile_match"), f"指标{metric_id}.profile_match", mechanic_map, errors)
            if metric.get("profile_match", {}).get("always") is not True:
                if not capabilities:
                    errors.append(f"非通用指标capability_ids不能为空: {metric_id}")
                if not match_ids.issubset(set(capabilities)):
                    errors.append(f"profile_match未被capability_ids完整覆盖: {metric_id}")
                if not condition_implies(metric.get("profile_match"), package_condition):
                    errors.append(f"指标profile_match超出所属包applies_when: {metric_id}")
            role = metric.get("semantic_role")
            if role not in SEMANTIC_ROLES:
                errors.append(f"指标semantic_role无效: {metric_id} / {role}")
            kind = metric.get("kind")
            if kind == "score" and role != "primary":
                errors.append(f"评分指标必须是primary语义角色: {metric_id} / {role}")
            if role == "derived_diagnostic" and kind != "audit":
                errors.append(f"derived_diagnostic必须是审计指标: {metric_id} / {kind}")
            if role == "audit" and kind != "audit":
                errors.append(f"audit语义角色必须是审计指标: {metric_id} / {kind}")
            relationships = metric.get("relationships")
            if not isinstance(relationships, dict) or not relationships:
                errors.append(f"指标relationships无效: {metric_id}")
            else:
                for field in ("derived_from", "cross_checks_with"):
                    if field not in relationships:
                        errors.append(f"指标relationships缺少字段: {metric_id} / {field}")
                if not non_empty_text(relationships.get("overlap_reason_zh")):
                    errors.append(f"指标overlap_reason_zh为空: {metric_id}")
                for field in RELATION_KEYS:
                    values = relationships.get(field, [])
                    if not isinstance(values, list) or any(not non_empty_text(item) for item in values):
                        errors.append(f"指标关系字段无效: {metric_id} / {field}")
                    elif len(values) != len(set(values)):
                        errors.append(f"指标关系字段存在重复项: {metric_id} / {field}")
            if kind == "score":
                missing_score = sorted(SCORE_FIELDS - set(metric))
                if missing_score:
                    errors.append(f"评分指标字段缺失: {metric_id} / {','.join(missing_score)}")
                for field in ("score_group", "score_budget_key", "scope_aggregation"):
                    if field in metric and not non_empty_text(metric.get(field)):
                        errors.append(f"评分指标字段为空: {metric_id} / {field}")
                if metric.get("scope_aggregation") not in SCOPE_AGGREGATIONS:
                    errors.append(f"评分指标scope_aggregation不受支持: {metric_id} / {metric.get('scope_aggregation')}")
                if not finite_number(metric.get("default_weight")) or metric.get("default_weight", 0) <= 0:
                    errors.append(f"评分指标default_weight无效: {metric_id}")
                validate_score_profile(metric_id, metric.get("score_profile"), errors)
            elif kind == "hard":
                profile = metric.get("hard_gate_profile")
                if not isinstance(profile, dict) or not profile:
                    errors.append(f"硬指标缺少hard_gate_profile: {metric_id}")
                else:
                    for field in ("method", "tolerance_source"):
                        if not non_empty_text(profile.get(field)):
                            errors.append(f"硬指标评价字段为空: {metric_id} / {field}")
                    if profile.get("method") not in SUPPORTED_SCORE_METHODS:
                        errors.append(f"硬指标距离方法不受支持: {metric_id} / {profile.get('method')}")
                    if not isinstance(profile.get("confidence_required"), bool):
                        errors.append(f"硬指标confidence_required无效: {metric_id}")
                    validate_ordered_profile(metric_id, profile, errors)
            elif kind == "audit":
                if metric.get("score_weight") != 0:
                    errors.append(f"审计指标score_weight必须为0: {metric_id}")
                profile = metric.get("audit_profile")
                if not isinstance(profile, dict) or not profile:
                    errors.append(f"审计指标缺少audit_profile: {metric_id}")
                else:
                    if not non_empty_text(profile.get("method")):
                        errors.append(f"审计指标audit_profile.method为空: {metric_id}")
                    if not isinstance(profile.get("blocking_on_missing"), bool):
                        errors.append(f"审计指标blocking_on_missing无效: {metric_id}")
                    if "blocking_on_mismatch" in profile and not isinstance(profile.get("blocking_on_mismatch"), bool):
                        errors.append(f"审计指标blocking_on_mismatch无效: {metric_id}")
                    if profile.get("blocking_on_mismatch") is True and not non_empty_text(profile.get("required_result_status")):
                        errors.append(f"阻塞型一致性审计缺少required_result_status: {metric_id}")
                    insufficient_fields = {"insufficient_sample_status", "insufficient_sample_blocks_formal"}
                    if insufficient_fields & set(profile):
                        if not non_empty_text(profile.get("insufficient_sample_status")):
                            errors.append(f"审计指标insufficient_sample_status无效: {metric_id}")
                        if not isinstance(profile.get("insufficient_sample_blocks_formal"), bool):
                            errors.append(f"审计指标insufficient_sample_blocks_formal无效: {metric_id}")
            else:
                errors.append(f"指标kind无效: {metric_id} / {kind}")
    return metric_map, package_map


def validate_relationships(metric_map, errors):
    graph = defaultdict(set)
    primary_score_owners = defaultdict(set)
    primary_metric_ids = defaultdict(list)
    for metric_id, metric in metric_map.items():
        relationships = metric.get("relationships", {}) if isinstance(metric.get("relationships"), dict) else {}
        derived_targets = []
        for field in RELATION_KEYS:
            values = relationships.get(field, [])
            if not isinstance(values, list):
                continue
            for target in values:
                if target == metric_id:
                    errors.append(f"指标关系不能引用自身: {metric_id} / {field}")
                elif target not in metric_map:
                    errors.append(f"指标关系引用未知目标: {metric_id} / {field} / {target}")
            if field in {"derived_from", "marginal_of"}:
                graph[metric_id].update(values)
                derived_targets.extend(values)
        if derived_targets:
            if metric.get("kind") == "score":
                errors.append(f"派生或边际指标不得参与评分: {metric_id}")
            if metric.get("semantic_role") != "derived_diagnostic":
                errors.append(f"派生或边际指标必须标记为derived_diagnostic: {metric_id}")
            if not non_empty_text(relationships.get("overlap_reason_zh")):
                errors.append(f"派生或边际指标缺少重叠说明: {metric_id}")
        if metric.get("semantic_role") == "derived_diagnostic" and not derived_targets:
            errors.append(f"derived_diagnostic缺少derived_from或marginal_of关系: {metric_id}")
        conditional_sources = relationships.get("conditional_derivation_sources", [])
        if conditional_sources:
            if metric.get("kind") != "score" or metric.get("semantic_role") != "primary":
                errors.append(f"条件派生来源只能登记在primary评分指标: {metric_id}")
            if "deterministically_derived_from_primary" not in metric.get("inapplicability_reason_codes", []):
                errors.append(f"条件派生指标未允许deterministically_derived_from_primary: {metric_id}")
            if set(conditional_sources) & set(derived_targets):
                errors.append(f"条件派生来源不得与无条件派生关系重复: {metric_id}")
        elif "deterministically_derived_from_primary" in metric.get("inapplicability_reason_codes", []):
            errors.append(f"允许确定性派生的评分指标缺少conditional_derivation_sources: {metric_id}")
        if metric.get("semantic_role") == "primary":
            primary_metric_ids[metric.get("semantic_variable_id")].append(metric_id)
        if metric.get("kind") == "score" and metric.get("semantic_role") == "primary":
            primary_score_owners[metric.get("semantic_variable_id")].add(metric.get("owner"))
    for semantic_variable_id, metric_ids in sorted(primary_metric_ids.items()):
        if len(metric_ids) > 1:
            errors.append(f"同一semantic_variable_id存在多个primary指标: {semantic_variable_id} / {','.join(sorted(metric_ids))}")
    for semantic_variable_id, owners in sorted(primary_score_owners.items()):
        if len(owners) > 1:
            errors.append(f"同一semantic_variable_id存在多个primary score Owner: {semantic_variable_id} / {','.join(sorted(owners))}")

    state = {}

    def visit(metric_id, stack):
        status = state.get(metric_id, 0)
        if status == 1:
            cycle = " -> ".join([*stack, metric_id])
            errors.append(f"指标派生关系存在环: {cycle}")
            return
        if status == 2:
            return
        state[metric_id] = 1
        for target in sorted(graph.get(metric_id, ())):
            if target in metric_map:
                visit(target, [*stack, metric_id])
        state[metric_id] = 2

    for metric_id in sorted(metric_map):
        visit(metric_id, [])


def validate_owner_direction_contracts(metric_map, errors):
    hold_spin_ids = {
        "hold_spin.initial_occupancy_distribution",
        "hold_spin.current_occupancy_distribution",
        "hold_spin.occupancy_transition_distribution",
        "hold_spin.terminal_occupied_cell_count_distribution",
    }
    for metric_id in hold_spin_ids:
        metric = metric_map.get(metric_id, {})
        if "semantic_owner_exclusive" in metric.get("inapplicability_reason_codes", []):
            errors.append(f"Hold & Spin专用数量Owner不得反向让位给通用持久状态指标: {metric_id}")
    transition = metric_map.get("hold_spin.occupancy_transition_distribution", {})
    transition_exclusive = set(transition.get("relationships", {}).get("exclusive_with", []))
    if "persistent_state.position_count_transition_distribution" not in transition_exclusive:
        errors.append("Hold & Spin占用推进未与通用位置数量转移建立双向互斥")
    persistent = metric_map.get("persistent_state.position_count_transition_distribution", {})
    persistent_exclusive = set(persistent.get("relationships", {}).get("exclusive_with", []))
    if "hold_spin.occupancy_transition_distribution" not in persistent_exclusive:
        errors.append("通用位置数量转移未向Hold & Spin专用推进Owner让位")
    current = metric_map.get("hold_spin.current_occupancy_distribution", {})
    transition_condition = transition.get("relationships", {}).get("conditional_on_metric", [])
    if not current:
        errors.append("Hold & Spin缺少全部实际执行步骤的当前占用边际Owner")
    elif transition_condition != [
        "hold_spin.actual_capacity_distribution_by_observation",
        "hold_spin.current_occupancy_distribution",
        "hold_spin.capacity_transition_distribution",
    ]:
        errors.append("Hold & Spin占用推进必须按P(C)×P(O|C)×P(C'|C,O)的完整前置链建立条件Owner")
    resource_audit = metric_map.get("hold_spin.respin_resource_rule_consistency.audit", {})
    audit_profile = resource_audit.get("audit_profile") if isinstance(resource_audit.get("audit_profile"), dict) else {}
    if (
        resource_audit.get("kind") != "audit"
        or resource_audit.get("score_weight") != 0
        or audit_profile.get("method") != "field_consistency_gate"
        or audit_profile.get("blocking_on_missing") is not True
        or audit_profile.get("blocking_on_mismatch") is not True
    ):
        errors.append("Hold & Spin缺少0权重阻塞型重转资源规则一致性审计")


def validate_matched_position_joint_contract(metric_map, errors):
    legacy_ids = {
        "persistent_state.matched_position_transition_given_origin_distribution",
        "persistent_state.matched_position_transition_distribution",
    }
    metric_id = "persistent_state.matched_position_pairing_residual_given_count_transition"
    for legacy_id in sorted(legacy_ids & set(metric_map)):
        errors.append(f"一一配对位置移动仍使用包含位置边际或漏掉数量分层的旧指标ID: {legacy_id}")
    metric = metric_map.get(metric_id)
    if not isinstance(metric, dict):
        errors.append(f"持久状态缺少一一配对位置移动纯配对残差Owner: {metric_id}")
        return
    profile = metric.get("score_profile") if isinstance(metric.get("score_profile"), dict) else {}
    relationships = metric.get("relationships") if isinstance(metric.get("relationships"), dict) else {}
    capabilities = set(metric.get("capability_ids", []))
    if profile.get("method") != "grouped_mean_absolute_error" or profile.get("group_weight_source") != "task_contract":
        errors.append("一一配对位置移动残差必须使用任务合同组权重的grouped_mean_absolute_error")
    if relationships.get("conditional_on_metric") != ["persistent_state.position_count_transition_distribution"]:
        errors.append("一一配对位置移动残差必须且只能以数量转移Owner为条件前置")
    if relationships.get("exclusive_with"):
        errors.append("纯配对残差不得停用位置份额或位置角色残差Owner")
    if not {"state.persistent-state", "modifier.wild-substitute"}.issubset(capabilities) or "modifier.expanding-wild" in capabilities:
        errors.append("一一配对位置移动残差的玩法画像必须使用持久位置状态与Wild替代语义")
    if (
        metric.get("unit") != "probability_difference"
        or metric.get("default_weight") != 0.5
        or metric.get("score_budget_key") != metric_id
        or metric.get("semantic_variable_id") != "persistent_state.matched_position_pairing_dependence_residual_given_count_transition"
    ):
        errors.append("一一配对位置移动残差的单位、权重、预算键或语义变量ID无效")


def validate_transform_target_coherence_contract(metric_map, errors):
    metric_id = "transform.target_coherence_residual_given_count"
    metric = metric_map.get(metric_id)
    if not isinstance(metric, dict):
        errors.append(f"多格符号变形缺少低维目标一致性残差Owner: {metric_id}")
        return
    profile = metric.get("score_profile") if isinstance(metric.get("score_profile"), dict) else {}
    relationships = metric.get("relationships") if isinstance(metric.get("relationships"), dict) else {}
    if metric.get("unit") != "probability_difference" or profile.get("method") != "grouped_mean_absolute_error":
        errors.append("目标一致性残差必须使用分组平均绝对差评价有符号概率残差")
    if profile.get("group_weight_source") != "task_contract" or metric.get("default_weight") != 0.5:
        errors.append("目标一致性残差必须使用任务合同原版组权重并限制为0.5默认权重")
    if set(relationships.get("conditional_on_metric", [])) != {
        "transform.changed_cell_count_distribution",
        "transform.target_symbol_given_source_distribution",
    }:
        errors.append("目标一致性残差必须且只能以变换格数和来源条件目标边际为前置Owner")
    if metric.get("score_budget_key") != metric_id:
        errors.append("目标一致性残差预算键无效")


def validate_grouped_distribution_degeneracy(metric_map, errors):
    required_tokens = ("移除", "重新归一", "全部", "不适用")
    for metric_id, metric in metric_map.items():
        profile = metric.get("score_profile") if isinstance(metric.get("score_profile"), dict) else {}
        if metric.get("kind") != "score" or profile.get("method") not in GROUPED_DISTRIBUTION_METHODS:
            continue
        if "degenerate_reachable_support" not in metric.get("inapplicability_reason_codes", []):
            errors.append(f"分组分布指标缺少退化支持原因码: {metric_id}")
        text = " ".join(str(metric.get(field, "")) for field in ("applicability_rule", "missing_policy", "normalization"))
        missing = [token for token in required_tokens if token not in text]
        if missing:
            errors.append(f"分组分布指标缺少局部移除、原版权重重归一或全部退化不适用规则: {metric_id} / {','.join(missing)}")


def validate_score_budgets(metric_map, errors):
    budgets = {}
    for metric_id, metric in metric_map.items():
        if metric.get("kind") != "score":
            continue
        budget_key = metric.get("score_budget_key")
        signature = (metric.get("score_group"), metric.get("scope_aggregation"), metric.get("default_weight"), metric.get("semantic_variable_id"))
        previous = budgets.get(budget_key)
        if previous is None:
            budgets[budget_key] = (metric_id, signature)
            continue
        previous_id, previous_signature = previous
        if previous_id != metric_id or previous_signature != signature:
            errors.append(f"score_budget_key被多个不同评分语义复用: {budget_key} / {previous_id},{metric_id}")


def validate_score_group_weight_policy(root, metric_map, errors, files):
    path = root / "assets/policies/score_group_weight_policy.v1.json"
    files.append(path)
    data = read_json(path, errors, "评分组权重政策") if path.is_file() else None
    if data is None:
        if not path.is_file():
            errors.append("缺少评分组权重政策: assets/policies/score_group_weight_policy.v1.json")
        return
    if data.get("method") != "normalize_active_base_weights" or data.get("legacy_contracts_unchanged") is not True:
        errors.append("评分组权重政策方法或历史合同边界无效")
    base = data.get("base_weights")
    if not isinstance(base, dict) or not base or any(not finite_number(value) or value <= 0 for value in base.values()):
        errors.append("评分组权重政策base_weights无效")
        return
    if len({round(float(value), 12) for value in base.values()}) != 1:
        errors.append("v1默认评分组权重政策必须对全部语义组使用相同基础权重")
    score_groups = {metric.get("score_group") for metric in metric_map.values() if metric.get("kind") == "score"}
    if set(base) != score_groups:
        errors.append(f"评分组权重政策未与目录评分组完全对应: 政策={','.join(sorted(base))}；目录={','.join(sorted(score_groups))}")
    names = data.get("group_names_zh")
    if not isinstance(names, dict) or set(names) != set(base) or any(not non_empty_text(value) for value in names.values()):
        errors.append("评分组权重政策中文组名未完整覆盖")


def validate_ordered_distance_policy(root, metric_map, errors, files):
    path = root / "assets/policies/ordered_distance_policy.v1.json"
    files.append(path)
    data = read_json(path, errors, "有序距离政策") if path.is_file() else None
    if data is None:
        if not path.is_file():
            errors.append("缺少有序距离政策: assets/policies/ordered_distance_policy.v1.json")
        return
    expected_fixed = {
        "cascade.step_return_distribution_by_depth",
        "core.return_distribution.lt200",
        "effective_ways.capacity_distribution",
        "effective_ways.return_distribution_by_capacity",
        "feature_cycle.return_distribution_by_stage_path",
        "multiplier.effective_value_distribution",
        "settlement.step_return_distribution",
        "value_symbol.assignment_value_distribution",
        "variable_grid.return_distribution_by_capacity",
        "wild.incremental_return_given_assistance_distribution",
    }
    expected_dynamic = {
        "cascade.effective_capacity_distribution_by_depth": "evolution.cascade.effective_capacity_axis_semantics",
        "collect.output_value_given_input_count_distribution": "modifier.collect.output_axis_semantics_by_output",
        "persistent_state.ordered_transition_distribution": "state.persistent-state.ordered_axis_semantics",
        "persistent_state.ordered_value_distribution": "state.persistent-state.ordered_axis_semantics",
        "settlement.scale_given_symbol_distribution": "settlement mechanic winning_scale_axis_semantics",
    }
    fixed = data.get("fixed_nonnegative_multiplicative_metrics")
    dynamic = data.get("dynamic_axis_metrics")
    if not isinstance(fixed, list) or len(fixed) != len(set(fixed)) or set(fixed) != expected_fixed:
        errors.append("有序距离政策固定长尾指标清单失效")
        fixed = []
    if not isinstance(dynamic, dict) or set(dynamic) != set(expected_dynamic):
        errors.append("有序距离政策动态轴指标清单失效")
        dynamic = {}
    else:
        for metric_id, source in expected_dynamic.items():
            rule = dynamic.get(metric_id)
            if (
                not isinstance(rule, dict)
                or rule.get("resolution_source") != source
                or set(rule.get("allowed_axis_semantics", [])) != {"natural_linear", "nonnegative_multiplicative"}
            ):
                errors.append(f"有序距离政策动态轴规则失效: {metric_id}")
    expected_profiles = {
        "natural_linear": {
            "position_transform": "identity",
            "distance_normalization": "sealed_support_span",
            "distance_scale_source": "sealed_support_span",
            "distance_unit": "normalized_linear_support",
        },
        "nonnegative_multiplicative": {
            "position_transform": "log10_1p",
            "distance_normalization": "fixed_transform_unit",
            "distance_scale": 1.0,
            "distance_unit": "log10_decade",
        },
    }
    if data.get("default_axis_semantics") != "natural_linear" or data.get("axis_profiles") != expected_profiles or data.get("legacy_contracts_unchanged") is not True:
        errors.append("有序距离政策轴配置或历史合同边界失效")
    ordered = {}
    for metric_id, metric in metric_map.items():
        profile = metric.get("hard_gate_profile") if metric.get("kind") == "hard" else metric.get("score_profile")
        if metric.get("kind") in {"hard", "score"} and isinstance(profile, dict) and profile.get("method") in ORDERED_METHODS:
            ordered[metric_id] = (metric, profile)
    missing = sorted((expected_fixed | set(expected_dynamic)) - set(ordered))
    if missing:
        errors.append(f"有序距离政策引用未知或非有序硬/评分指标: {','.join(missing)}")
    for metric_id, (_, profile) in ordered.items():
        if profile.get("distance_normalization") == "none":
            errors.append(f"有序指标仍使用含义模糊的none归一化: {metric_id}")
        if metric_id in expected_fixed:
            expected = expected_profiles["nonnegative_multiplicative"]
            fields = {**expected, "axis_semantics": "nonnegative_multiplicative"}
            if any(profile.get(field) != value for field, value in fields.items()) or "axis_semantics_source" in profile:
                errors.append(f"固定长尾指标目录未使用政策尺度: {metric_id}")
        elif metric_id in expected_dynamic:
            if profile.get("axis_semantics_source") != expected_dynamic[metric_id]:
                errors.append(f"动态有序指标目录轴来源失效: {metric_id}")
        else:
            if profile.get("axis_semantics_source") is not None:
                errors.append(f"自然线性指标不得声明动态轴来源: {metric_id}")
            if profile.get("position_transform", "identity") != "identity" or profile.get("distance_normalization") != "sealed_support_span":
                errors.append(f"自然线性有序指标距离尺度失效: {metric_id}")


def requirement_package_ids(mechanic):
    requirements = mechanic.get("metric_requirements", {}) if isinstance(mechanic.get("metric_requirements"), dict) else {}
    required = requirements.get("required_packages", []) if isinstance(requirements.get("required_packages", []), list) else []
    conditional = requirements.get("conditional_packages", []) if isinstance(requirements.get("conditional_packages", []), list) else []
    return set(required) | {item.get("package_id") for item in conditional if isinstance(item, dict) and item.get("package_id")}


def validate_capability_coverage(mechanic_map, package_map, errors):
    for mechanic_id, mechanic in mechanic_map.items():
        requirements = mechanic.get("metric_requirements", {}) if isinstance(mechanic.get("metric_requirements"), dict) else {}
        required_packages = requirements.get("required_packages", []) if isinstance(requirements.get("required_packages", []), list) else []
        conditional_packages = requirements.get("conditional_packages", []) if isinstance(requirements.get("conditional_packages", []), list) else []
        for package_id in sorted(required_packages):
            package = package_map.get(package_id)
            if package is None:
                errors.append(f"玩法指标要求引用未知指标包: {mechanic_id} / {package_id}")
                continue
            covered = any(
                mechanic_id in metric.get("capability_ids", [])
                or metric.get("profile_match", {}).get("always") is True
                for metric in package.get("metrics", [])
            )
            if not covered:
                errors.append(f"玩法指标要求没有capability承接: {mechanic_id} / {package_id}")
        for item in conditional_packages:
            if not isinstance(item, dict):
                continue
            package_id = item.get("package_id")
            if package_id not in package_map:
                errors.append(f"玩法条件指标要求引用未知指标包: {mechanic_id} / {package_id}")
    for package_id, package in package_map.items():
        for metric in package.get("metrics", []):
            metric_id = metric.get("metric_id")
            for mechanic_id in metric.get("capability_ids", []) if isinstance(metric.get("capability_ids", []), list) else []:
                mechanic = mechanic_map.get(mechanic_id)
                if mechanic is not None and package_id not in requirement_package_ids(mechanic):
                    errors.append(f"指标capability未被玩法metric_requirements声明: {metric_id} / {mechanic_id} / {package_id}")


def summary_metric_ids(text):
    pattern = re.compile(r"^##### `([^`]+)`｜", re.MULTILINE)
    return pattern.findall(text)


def validate_summary(root, metric_map, errors, files):
    summary_path = root / SUMMARY_RELATIVE_PATH
    files.append(summary_path)
    try:
        expected = generate_summary(root)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"无法确定性生成指标汇总: {exc}")
        return
    if str(root) in expected or ABSOLUTE_PATH_PATTERN.search(expected):
        errors.append("指标汇总包含机器绝对路径")
    if not summary_path.is_file():
        errors.append(f"缺少指标汇总文档: {SUMMARY_RELATIVE_PATH.as_posix()}")
        return
    actual = summary_path.read_text(encoding="utf-8")
    if actual != expected:
        errors.append("指标汇总文档已过期，必须由generate_metric_summary.py重新生成")
    ids = summary_metric_ids(actual)
    if len(ids) != len(set(ids)):
        errors.append("指标汇总文档存在重复metric_id章节")
    if set(ids) != set(metric_map):
        missing = sorted(set(metric_map) - set(ids))
        extra = sorted(set(ids) - set(metric_map))
        errors.append(f"指标汇总收录集合不一致: 缺失={','.join(missing) or '无'}；额外={','.join(extra) or '无'}")


def validate_summary_categories(metrics_index, metric_records, errors):
    # packages[].category是机器语义分类；七类阅读归并只能由source_categories决定。
    categories = metrics_index.get("categories")
    expected_ids = ["core", "board", "settlement", "trigger", "evolution", "feature", "modifier"]
    if not isinstance(categories, list) or not all(isinstance(item, dict) for item in categories):
        errors.append("指标索引categories无效")
        return
    if any(not isinstance(item.get("display_order"), int) for item in categories):
        errors.append("指标索引分类display_order必须为整数")
        return
    ordered = sorted(categories, key=lambda item: item["display_order"])
    if [item.get("category_id") for item in ordered] != expected_ids:
        errors.append("指标索引七类分类顺序或ID无效")
        return
    source_owner = {}
    summary_by_source = {}
    for item in ordered:
        category_id = item.get("category_id")
        if not non_empty_text(item.get("name_zh")) or not non_empty_text(item.get("description_zh")):
            errors.append(f"指标索引分类展示元数据无效: {category_id}")
        sources = item.get("source_categories")
        if not isinstance(sources, list) or not sources or any(value not in METRIC_CATEGORIES for value in sources) or len(sources) != len(set(sources)):
            errors.append(f"指标索引source_categories无效: {category_id}")
            continue
        for source in sources:
            if source in source_owner:
                errors.append(f"目录category被多个阅读分类承接: {source} / {source_owner[source]},{category_id}")
            source_owner[source] = category_id
            summary_by_source[source] = category_id
    missing = sorted(METRIC_CATEGORIES - set(source_owner))
    if missing:
        errors.append(f"七类阅读分类未覆盖目录category: {','.join(missing)}")
    for record in metric_records:
        data = record["data"]
        package_reading = summary_by_source.get(data.get("category"))
        metric_readings = {
            summary_by_source.get(metric.get("category"))
            for metric in data.get("metrics", [])
            if isinstance(metric, dict) and summary_by_source.get(metric.get("category"))
        }
        if len(metric_readings) > 1:
            errors.append(f"指标包跨越多个阅读分类: {data.get('package_id')} / {','.join(sorted(metric_readings))}")
        elif metric_readings and package_reading not in metric_readings:
            errors.append(f"指标包机器category与指标阅读归并不一致: {data.get('package_id')} / {data.get('category')}")


def validate_catalogs(root):
    root = root.resolve()
    errors, files = [], []
    mechanics_index, mechanic_records, mechanic_files = indexed_records(root, "mechanics", errors)
    metrics_index, metric_records, metric_files = indexed_records(root, "metrics", errors)
    files.extend([*mechanic_files, *metric_files])
    schema_paths = [root / "assets/schemas/mechanic-catalog.schema.json", root / "assets/schemas/metric-catalog.schema.json"]
    files.extend(schema_paths)
    schemas = []
    for path in schema_paths:
        if not path.is_file():
            errors.append(f"缺少目录Schema: {path.relative_to(root)}")
            schemas.append(None)
        else:
            schemas.append(read_json(path, errors, "目录Schema"))
    mechanic_schema, metric_schema = schemas
    if mechanic_schema:
        for record in mechanic_records:
            label = record["path"].relative_to(root).as_posix()
            validate_with_schema(record["data"], mechanic_schema, label, errors)
    if metric_schema:
        for record in metric_records:
            label = record["path"].relative_to(root).as_posix()
            validate_with_schema(record["data"], metric_schema, label, errors)
    mechanic_records = [record for record in mechanic_records if isinstance(record["data"], dict)]
    metric_records = [record for record in metric_records if isinstance(record["data"], dict)]
    for record in mechanic_records:
        validate_record_identity(record, "mechanics", errors)
    for record in metric_records:
        validate_record_identity(record, "metrics", errors)
    mechanic_map = validate_mechanics(mechanic_records, errors)
    metric_map, package_map = validate_metrics(metric_records, mechanic_map, errors)
    validate_relationships(metric_map, errors)
    validate_owner_direction_contracts(metric_map, errors)
    validate_matched_position_joint_contract(metric_map, errors)
    validate_transform_target_coherence_contract(metric_map, errors)
    validate_grouped_distribution_degeneracy(metric_map, errors)
    validate_score_budgets(metric_map, errors)
    validate_score_group_weight_policy(root, metric_map, errors, files)
    validate_ordered_distance_policy(root, metric_map, errors, files)
    validate_capability_coverage(mechanic_map, package_map, errors)
    # 索引本身也必须声明确定性版本和类型。
    for kind, index, expected in (("mechanics", mechanics_index, "mechanic_index"), ("metrics", metrics_index, "metric_index")):
        if index.get("catalog_type") != expected:
            errors.append(f"{kind}索引catalog_type错误")
        if not non_empty_text(index.get("version")):
            errors.append(f"{kind}索引version为空")
    if metrics_index.get("summary_path") != SUMMARY_RELATIVE_PATH.name:
        errors.append("指标索引summary_path必须指向指标汇总.md")
    validate_summary_categories(metrics_index, metric_records, errors)
    validate_summary(root, metric_map, errors, files)
    return sorted(dict.fromkeys(errors)), sorted({path for path in files if path.is_file()}), {"mechanics": len(mechanic_map), "metrics": len(metric_map)}


def main():
    parser = argparse.ArgumentParser(description="严格验证或计算玩法/指标目录哈希")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("validate", "hash"):
        command = sub.add_parser(name)
        command.add_argument("--skill-root", required=True, type=Path)
    args = parser.parse_args()
    errors, files, counts = validate_catalogs(args.skill_root)
    if errors:
        print(json.dumps({"status": "失败", "errors": errors}, ensure_ascii=False, indent=2))
        return 1
    result = {"status": "通过", "counts": counts}
    if args.cmd == "hash":
        result["files"] = {str(path.relative_to(args.skill_root.resolve())): digest(path) for path in files}
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
