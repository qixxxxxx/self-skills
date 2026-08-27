#!/usr/bin/env python3
"""把展开的 metric_contract 1.3 转为可确定性展开的 1.4 紧凑合同。"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path

from contract_io import (
    COMPACT_VERSION,
    DATA_SCHEMA_VERSION,
    INSTANCE_ID_ALGORITHM,
    ContractIOError,
    _metric_catalog,
    canonical_json_bytes,
    load_json_strict,
    metric_instance_id,
    sha256_file,
)


INHERITED_FIELDS = {
    "applicability_rule",
    "audit_profile",
    "capability_ids",
    "category",
    "condition_on",
    "conditional_derivation_requirements",
    "default_weight",
    "display",
    "display_order",
    "hard_gate_profile",
    "inapplicability_reason_codes",
    "kind",
    "measurement",
    "missing_policy",
    "name_zh",
    "normalization",
    "owner",
    "profile_match",
    "relationships",
    "return_denominator",
    "sample_unit",
    "scope_aggregation",
    "scope_template",
    "score_budget_key",
    "score_group",
    "score_profile",
    "semantic_group",
    "semantic_role",
    "semantic_variable_id",
    "unit",
}
PROFILE_PATCH_FIELDS = {
    "audit_profile": "audit_profile_patch",
    "hard_gate_profile": "hard_gate_profile_patch",
    "score_profile": "score_profile_patch",
}
EXTERNALIZABLE_PATHS = {
    ("target",),
    ("display", "item_labels"),
    ("display", "object_labels"),
    ("display", "object_units"),
    ("hard_gate_profile_patch", "bin_positions"),
    ("hard_gate_profile_patch", "bin_positions_by_group"),
    ("hard_gate_profile_patch", "group_weights"),
    ("score_profile_patch", "bin_boundaries_by_group"),
    ("score_profile_patch", "bin_positions"),
    ("score_profile_patch", "bin_positions_by_group"),
    ("score_profile_patch", "group_weights"),
    ("score_profile_patch", "residual_baselines_by_group"),
    ("sample_capability",),
}


def _dict_patch(base, value):
    if not isinstance(base, dict) or not isinstance(value, dict):
        return copy.deepcopy(value) if base != value else None
    patch = {}
    for key, item in value.items():
        if key not in base:
            patch[key] = copy.deepcopy(item)
            continue
        difference = _dict_patch(base[key], item)
        if difference is not None:
            patch[key] = difference
    return patch or None


def _compact_metric(metric, catalog_metric):
    compact = copy.deepcopy(metric)
    for field in sorted(INHERITED_FIELDS):
        if field not in compact or field not in catalog_metric:
            continue
        difference = _dict_patch(catalog_metric[field], compact[field])
        compact.pop(field)
        if difference is None:
            continue
        compact[PROFILE_PATCH_FIELDS.get(field, field)] = difference
    source_node_ids = compact.get("source_node_ids", [])
    instance_dimensions = compact.get("instance_dimensions", {})
    compact["instance_id"] = metric_instance_id(compact.get("metric_id"), source_node_ids, instance_dimensions)
    return compact


def _externalize(value, path, instance_id, records, threshold):
    if path in EXTERNALIZABLE_PATHS and isinstance(value, (dict, list)) and len(canonical_json_bytes(value)) >= threshold:
        ref_id = f"metric:{instance_id}:{'.'.join(path)}"
        records.append({"ref_id": ref_id, "instance_id": instance_id, "value": copy.deepcopy(value)})
        return {"$data_ref": ref_id}
    if isinstance(value, dict):
        return {key: _externalize(item, (*path, key), instance_id, records, threshold) for key, item in value.items()}
    if isinstance(value, list):
        return [_externalize(item, path, instance_id, records, threshold) for item in value]
    return value


def _encode_shared_object_keys(records):
    uses = {}
    for record in records:
        value = record["value"]
        if isinstance(value, dict) and len(value) >= 32:
            keys = tuple(sorted(value))
            uses.setdefault(keys, []).append(record)
    keysets = []
    for keys, matching in uses.items():
        if len(matching) < 2:
            continue
        digest = hashlib.sha256(canonical_json_bytes(keys)).hexdigest()[:24]
        keyset_id = f"ks_{digest}"
        keysets.append({"keyset_id": keyset_id, "keys": list(keys)})
        for record in matching:
            value = record["value"]
            record["value"] = {
                "$encoding": "object_values.v1",
                "keyset_id": keyset_id,
                "values": [value[key] for key in keys],
            }
    return sorted(keysets, key=lambda item: item["keyset_id"])


def compact_contract_data(contract, skill_root, external_path="metric_contract_data/metric-data.json", threshold=2048):
    if not isinstance(contract, dict) or contract.get("schema_version") != "1.3":
        raise ContractIOError("紧凑化输入必须是metric_contract 1.3对象")
    if not isinstance(threshold, int) or isinstance(threshold, bool) or threshold < 1:
        raise ContractIOError("externalize threshold必须是正整数")
    catalog = _metric_catalog(skill_root, contract)
    metrics = contract.get("metrics")
    if not isinstance(metrics, list):
        raise ContractIOError("metric_contract.metrics必须是数组")
    compact_metrics, records, seen = [], [], set()
    for metric in metrics:
        if not isinstance(metric, dict) or metric.get("metric_id") not in catalog:
            raise ContractIOError(f"指标未命中目录: {metric.get('metric_id') if isinstance(metric, dict) else metric}")
        compact = _compact_metric(metric, catalog[metric["metric_id"]])
        instance_id = compact["instance_id"]
        if instance_id in seen:
            raise ContractIOError(f"指标实例ID重复: {instance_id}")
        seen.add(instance_id)
        compact_metrics.append(_externalize(compact, (), instance_id, records, threshold))
    result = copy.deepcopy(contract)
    result["schema_version"] = COMPACT_VERSION
    result["report_contract_version"] = "slot-alignment.reports.v3.3"
    result["contract_storage"] = {
        "layout": "compact_metric_instances_v1",
        "catalog_inheritance_version": "1",
        "instance_id_algorithm": INSTANCE_ID_ALGORITHM,
        "external_data_schema_version": DATA_SCHEMA_VERSION,
        "canonical_json": "utf8-sort_keys-compact-v1",
    }
    result["metrics"] = compact_metrics
    external = {
        "schema_version": DATA_SCHEMA_VERSION,
        "keysets": _encode_shared_object_keys(records),
        "records": records,
    }
    if records:
        result["external_data"] = [{
            "data_id": "metric-data",
            "path": external_path,
            "schema_version": DATA_SCHEMA_VERSION,
            "sha256": None,
            "record_count": len(records),
            "instance_count": len({record["instance_id"] for record in records}),
        }]
    else:
        result["external_data"] = []
    return result, external


def write_compact_contract(contract, output, skill_root, external_path="metric_contract_data/metric-data.json", threshold=2048):
    output = Path(output)
    compact, external = compact_contract_data(contract, skill_root, external_path, threshold)
    external_file = output.parent / Path(external_path)
    if external["records"]:
        external_file.parent.mkdir(parents=True, exist_ok=True)
        external_file.write_bytes(canonical_json_bytes(external) + b"\n")
        compact["external_data"][0]["sha256"] = sha256_file(external_file)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(canonical_json_bytes(compact) + b"\n")
    return compact


def main():
    parser = argparse.ArgumentParser(description="把metric_contract 1.3紧凑化为1.4")
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--skill-root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--external-path", default="metric_contract_data/metric-data.json")
    parser.add_argument("--threshold", type=int, default=2048)
    args = parser.parse_args()
    write_compact_contract(load_json_strict(args.contract), args.output, args.skill_root, args.external_path, args.threshold)
    print(json.dumps({"status": "通过", "output": str(args.output), "sha256": sha256_file(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
