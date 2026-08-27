#!/usr/bin/env python3
"""metric_contract 的严格读取、兼容展开与内容身份工具。"""

from __future__ import annotations

import copy
import hashlib
import json
from collections import OrderedDict
from pathlib import Path, PurePosixPath


PASSTHROUGH_VERSIONS = {"1.0", "1.1", "1.2", "1.3"}
COMPACT_VERSION = "1.4"
DATA_SCHEMA_VERSION = "slot-alignment.contract-data.v1"
INSTANCE_ID_ALGORITHM = "metric-instance-id-v1"
PROTECTED_CATALOG_FIELDS = {"metric_id", "owner"}
PROFILE_PATCH_FIELDS = {
    "audit_profile_patch": "audit_profile",
    "hard_gate_profile_patch": "hard_gate_profile",
    "score_profile_patch": "score_profile",
}
LOADER_VERSION = "contract-io.v1"
MAX_MEMORY_CACHE_ENTRIES = 4
_EXPANDED_CACHE = OrderedDict()
_CACHE_STATS = {"hits": 0, "misses": 0}


class ContractIOError(ValueError):
    """合同结构、引用或 Hash 无法证明有效。"""


def _reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ContractIOError(f"JSON存在重复键: {key}")
        result[key] = value
    return result


def _reject_constant(value):
    raise ContractIOError(f"JSON包含非有限数值: {value}")


def load_json_strict(path):
    path = Path(path)
    try:
        with path.open("r", encoding="utf-8") as stream:
            return json.load(
                stream,
                object_pairs_hook=_reject_duplicate_keys,
                parse_constant=_reject_constant,
            )
    except ContractIOError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ContractIOError(f"无法严格读取JSON: {path}: {exc}") from exc


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical_json_bytes(value):
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ContractIOError(f"对象无法规范化为JSON: {exc}") from exc


def metric_instance_digest(metric_id, source_node_ids, instance_dimensions):
    if not isinstance(metric_id, str) or not metric_id.strip():
        raise ContractIOError("metric_id必须是非空字符串")
    if not isinstance(source_node_ids, list) or any(
        not isinstance(value, str) or not value.strip() for value in source_node_ids
    ):
        raise ContractIOError("source_node_ids必须是非空字符串数组")
    if not isinstance(instance_dimensions, dict):
        raise ContractIOError("instance_dimensions必须是对象")
    identity = {
        "instance_dimensions": instance_dimensions,
        "metric_id": metric_id,
        "source_node_ids": sorted(set(source_node_ids)),
    }
    return hashlib.sha256(canonical_json_bytes(identity)).hexdigest()


def metric_instance_id(metric_id, source_node_ids, instance_dimensions):
    return f"mi_{metric_instance_digest(metric_id, source_node_ids, instance_dimensions)[:24]}"


def _safe_relative_file(contract_path, relative):
    if not isinstance(relative, str) or not relative:
        raise ContractIOError("外部数据path必须是非空相对路径")
    pure = PurePosixPath(relative)
    if pure.is_absolute() or ".." in pure.parts or "." in pure.parts:
        raise ContractIOError(f"外部数据path不安全: {relative}")
    root = Path(contract_path).resolve().parent
    candidate = (root / Path(*pure.parts)).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ContractIOError(f"外部数据path越出合同目录: {relative}") from exc
    if not candidate.is_file():
        raise ContractIOError(f"外部数据文件不存在: {relative}")
    return candidate


def _external_records(contract, contract_path):
    declarations = contract.get("external_data", [])
    if not isinstance(declarations, list):
        raise ContractIOError("external_data必须是数组")
    refs, manifests, seen_ids, seen_paths = {}, [], set(), {}
    for declaration in declarations:
        if not isinstance(declaration, dict):
            raise ContractIOError("external_data条目必须是对象")
        data_id = declaration.get("data_id")
        if not isinstance(data_id, str) or not data_id or data_id in seen_ids:
            raise ContractIOError(f"external_data.data_id无效或重复: {data_id}")
        seen_ids.add(data_id)
        path = _safe_relative_file(contract_path, declaration.get("path"))
        digest = sha256_file(path)
        if declaration.get("sha256") != digest:
            raise ContractIOError(f"外部数据SHA-256失效: {data_id}")
        prior = seen_paths.setdefault(path, digest)
        if prior != digest:
            raise ContractIOError(f"同一路径绑定了不同SHA-256: {path}")
        payload = load_json_strict(path)
        if not isinstance(payload, dict) or payload.get("schema_version") != DATA_SCHEMA_VERSION:
            raise ContractIOError(f"外部数据Schema无效: {data_id}")
        if declaration.get("schema_version") != payload.get("schema_version"):
            raise ContractIOError(f"外部数据声明Schema不一致: {data_id}")
        records = payload.get("records")
        if not isinstance(records, list) or declaration.get("record_count") != len(records):
            raise ContractIOError(f"外部数据record_count不一致: {data_id}")
        keysets = {}
        for keyset in payload.get("keysets", []):
            if not isinstance(keyset, dict):
                raise ContractIOError(f"外部数据keysets条目必须是对象: {data_id}")
            keyset_id, keys = keyset.get("keyset_id"), keyset.get("keys")
            if (
                not isinstance(keyset_id, str)
                or not keyset_id
                or keyset_id in keysets
                or not isinstance(keys, list)
                or any(not isinstance(key, str) for key in keys)
                or len(keys) != len(set(keys))
            ):
                raise ContractIOError(f"外部数据keyset无效或重复: {keyset_id}")
            keysets[keyset_id] = keys
        instance_ids = set()
        for record in records:
            if not isinstance(record, dict):
                raise ContractIOError(f"外部数据records条目必须是对象: {data_id}")
            ref_id = record.get("ref_id")
            instance_id = record.get("instance_id")
            if not isinstance(ref_id, str) or not ref_id or ref_id in refs:
                raise ContractIOError(f"外部数据ref_id无效或重复: {ref_id}")
            if not isinstance(instance_id, str) or not instance_id:
                raise ContractIOError(f"外部数据instance_id无效: {ref_id}")
            if "value" not in record:
                raise ContractIOError(f"外部数据记录缺少value: {ref_id}")
            instance_ids.add(instance_id)
            value = record["value"]
            if isinstance(value, dict) and value.get("$encoding") == "object_values.v1":
                keyset_id, values = value.get("keyset_id"), value.get("values")
                keys = keysets.get(keyset_id)
                if keys is None or not isinstance(values, list) or len(values) != len(keys):
                    raise ContractIOError(f"外部数据共享键编码无效: {ref_id}")
                value = dict(zip(keys, values))
            refs[ref_id] = copy.deepcopy(value)
        if declaration.get("instance_count") != len(instance_ids):
            raise ContractIOError(f"外部数据instance_count不一致: {data_id}")
        manifests.append({
            "data_id": data_id,
            "schema_version": declaration["schema_version"],
            "sha256": digest,
            "record_count": len(records),
            "instance_count": len(instance_ids),
        })
    return refs, manifests


def _resolve_data_refs(value, refs, used_refs):
    if isinstance(value, dict):
        if set(value) == {"$data_ref"}:
            ref_id = value["$data_ref"]
            if not isinstance(ref_id, str) or ref_id not in refs:
                raise ContractIOError(f"合同引用了未声明外部数据: {ref_id}")
            used_refs.add(ref_id)
            return copy.deepcopy(refs[ref_id])
        return {key: _resolve_data_refs(item, refs, used_refs) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve_data_refs(item, refs, used_refs) for item in value]
    return value


def _deep_merge(base, override):
    if not isinstance(base, dict) or not isinstance(override, dict):
        return copy.deepcopy(override)
    result = copy.deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _metric_catalog(skill_root, contract):
    base = Path(skill_root) / "references" / "指标目录"
    index_path = base / "index.json"
    index = load_json_strict(index_path)
    catalogs = contract.get("catalogs") if isinstance(contract.get("catalogs"), dict) else {}
    hashes = catalogs.get("hashes") if isinstance(catalogs.get("hashes"), dict) else {}
    if catalogs.get("metrics_version") != index.get("version") or hashes.get("metrics") != sha256_file(index_path):
        raise ContractIOError("metric_contract未绑定当前指标目录版本与SHA-256")
    metrics = {}
    for package in index.get("packages", []):
        if not isinstance(package, dict):
            raise ContractIOError("指标目录packages条目必须是对象")
        path = base / package.get("path", "")
        if package.get("sha256") != sha256_file(path):
            raise ContractIOError(f"指标目录包SHA-256失效: {package.get('package_id')}")
        data = load_json_strict(path)
        for metric in data.get("metrics", []):
            metric_id = metric.get("metric_id") if isinstance(metric, dict) else None
            if not isinstance(metric_id, str) or metric_id in metrics:
                raise ContractIOError(f"指标目录metric_id无效或重复: {metric_id}")
            metrics[metric_id] = metric
    return metrics


def _expand_v14(contract, contract_path, skill_root, catalog=None):
    storage = contract.get("contract_storage")
    if not isinstance(storage, dict) or storage.get("layout") != "compact_metric_instances_v1":
        raise ContractIOError("metric_contract 1.4缺少有效contract_storage")
    if storage.get("instance_id_algorithm") != INSTANCE_ID_ALGORITHM:
        raise ContractIOError("metric_contract 1.4实例ID算法无效")
    catalog = catalog or _metric_catalog(skill_root, contract)
    refs, _ = _external_records(contract, contract_path)
    used_refs, expanded_metrics, seen_instances = set(), [], set()
    compact_metrics = contract.get("metrics")
    if not isinstance(compact_metrics, list):
        raise ContractIOError("metric_contract.metrics必须是数组")
    for compact in compact_metrics:
        if not isinstance(compact, dict):
            raise ContractIOError("metric_contract.metrics条目必须是对象")
        metric_id = compact.get("metric_id")
        if metric_id not in catalog:
            raise ContractIOError(f"metric_id未命中目录: {metric_id}")
        expected_id = metric_instance_id(
            metric_id,
            compact.get("source_node_ids", []),
            compact.get("instance_dimensions", {}),
        )
        instance_id = compact.get("instance_id")
        if instance_id != expected_id or instance_id in seen_instances:
            raise ContractIOError(f"指标实例ID失效或重复: {instance_id}")
        seen_instances.add(instance_id)
        resolved = _resolve_data_refs(compact, refs, used_refs)
        for field in PROTECTED_CATALOG_FIELDS:
            if field in resolved and resolved[field] != catalog[metric_id].get(field):
                raise ContractIOError(f"指标实例覆盖受保护目录字段: {instance_id}.{field}")
        remove_fields = resolved.pop("remove_fields", [])
        if not isinstance(remove_fields, list) or any(not isinstance(field, str) for field in remove_fields):
            raise ContractIOError(f"remove_fields无效: {instance_id}")
        patches = {target: resolved.pop(source) for source, target in PROFILE_PATCH_FIELDS.items() if source in resolved}
        resolved.pop("metric_id", None)
        metric = _deep_merge(catalog[metric_id], resolved)
        metric["metric_id"] = metric_id
        for target, patch in patches.items():
            if not isinstance(patch, dict):
                raise ContractIOError(f"评价合同patch必须是对象: {instance_id}.{target}")
            metric[target] = _deep_merge(metric.get(target, {}), patch)
        for field in remove_fields:
            if field in PROTECTED_CATALOG_FIELDS:
                raise ContractIOError(f"不得删除受保护目录字段: {instance_id}.{field}")
            metric.pop(field, None)
        expanded_metrics.append(metric)
    unused = sorted(set(refs) - used_refs)
    if unused:
        raise ContractIOError(f"外部数据存在未引用记录: {','.join(unused)}")
    expanded = copy.deepcopy(contract)
    expanded["metrics"] = expanded_metrics
    return expanded


def _cache_key(contract, contract_path, skill_root):
    external = []
    for declaration in contract.get("external_data", []):
        if not isinstance(declaration, dict):
            raise ContractIOError("external_data条目必须是对象")
        path = _safe_relative_file(contract_path, declaration.get("path"))
        digest = sha256_file(path)
        if declaration.get("sha256") != digest:
            raise ContractIOError(f"外部数据SHA-256失效: {declaration.get('data_id')}")
        external.append({
            "data_id": declaration.get("data_id"),
            "schema_version": declaration.get("schema_version"),
            "sha256": digest,
            "record_count": declaration.get("record_count"),
            "instance_count": declaration.get("instance_count"),
        })
    storage = contract.get("contract_storage", {})
    payload = {
        "loader_version": LOADER_VERSION,
        "main_contract_sha256": sha256_file(contract_path),
        "metric_catalog_sha256": contract.get("catalogs", {}).get("hashes", {}).get("metrics"),
        "catalog_inheritance_version": storage.get("catalog_inheritance_version"),
        "external_data_schema_version": storage.get("external_data_schema_version"),
        "external_data": sorted(external, key=lambda item: str(item["data_id"])),
        "skill_root": str(Path(skill_root).resolve()),
    }
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def clear_contract_cache():
    _EXPANDED_CACHE.clear()
    _CACHE_STATS.update({"hits": 0, "misses": 0})


def contract_cache_stats():
    return {**_CACHE_STATS, "entries": len(_EXPANDED_CACHE), "max_entries": MAX_MEMORY_CACHE_ENTRIES}


def contract_content_identity(contract_path, contract=None):
    contract_path = Path(contract_path)
    contract = load_json_strict(contract_path) if contract is None else contract
    _, manifests = _external_records(contract, contract_path)
    payload = {
        "main_contract_sha256": sha256_file(contract_path),
        "external_data": sorted(manifests, key=lambda item: item["data_id"]),
    }
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def load_contract(contract_path, skill_root=None):
    """读取合同；1.0～1.3原样返回，1.4返回目录继承后的展开视图。"""
    contract_path = Path(contract_path)
    try:
        with contract_path.open("r", encoding="utf-8") as stream:
            contract = json.load(stream)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ContractIOError(f"无法读取metric_contract: {contract_path}: {exc}") from exc
    if not isinstance(contract, dict):
        raise ContractIOError("metric_contract顶层必须是对象")
    version = contract.get("schema_version")
    if version in PASSTHROUGH_VERSIONS:
        return contract
    if version != COMPACT_VERSION:
        raise ContractIOError(f"不支持的metric_contract.schema_version: {version}")
    contract = load_json_strict(contract_path)
    skill_root = Path(skill_root or Path(__file__).resolve().parent.parent)
    catalog = _metric_catalog(skill_root, contract)
    cache_key = _cache_key(contract, contract_path, skill_root)
    if cache_key in _EXPANDED_CACHE:
        _CACHE_STATS["hits"] += 1
        _EXPANDED_CACHE.move_to_end(cache_key)
        return copy.deepcopy(_EXPANDED_CACHE[cache_key])
    _CACHE_STATS["misses"] += 1
    expanded = _expand_v14(contract, contract_path, skill_root, catalog)
    _EXPANDED_CACHE[cache_key] = copy.deepcopy(expanded)
    _EXPANDED_CACHE.move_to_end(cache_key)
    while len(_EXPANDED_CACHE) > MAX_MEMORY_CACHE_ENTRIES:
        _EXPANDED_CACHE.popitem(last=False)
    return expanded


def write_contract(contract, output, skill_root=None):
    """按合同版本写回；1.4重新紧凑化，旧版本保持原有展开JSON格式。"""
    output = Path(output)
    if contract.get("schema_version") == COMPACT_VERSION:
        from compact_metric_contract import write_compact_contract

        expanded = copy.deepcopy(contract)
        expanded["schema_version"] = "1.3"
        expanded["report_contract_version"] = "slot-alignment.reports.v3.3"
        expanded.pop("contract_storage", None)
        expanded.pop("external_data", None)
        return write_compact_contract(
            expanded,
            output,
            skill_root or Path(__file__).resolve().parent.parent,
            external_path=f"{output.stem}_data/metric-data.json",
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return contract
