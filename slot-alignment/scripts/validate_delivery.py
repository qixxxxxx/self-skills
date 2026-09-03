#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

from alignment import sha256_file


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_FILES = ["game_core.json", "payout_config.json", "reel_config.json", "symbol_catalog.json"]


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validate_delivery(task_root, formal_path, alignment_manifest_path, aligned_parameters_path, runtime_dir, manifest_path):
    task_root, formal_path = Path(task_root).resolve(), Path(formal_path).resolve()
    alignment_manifest_path, aligned_parameters_path = Path(alignment_manifest_path).resolve(), Path(aligned_parameters_path).resolve()
    runtime_dir, manifest_path = Path(runtime_dir).resolve(), Path(manifest_path).resolve()
    formal, manifest = load(formal_path), load(manifest_path)
    alignment_manifest, aligned_parameters = load(alignment_manifest_path), load(aligned_parameters_path)
    errors = []
    expected_paths = {
        formal_path: task_root / "artifacts/04-alignment/formal_result.json",
        alignment_manifest_path: task_root / "artifacts/04-alignment/alignment_manifest.json",
        aligned_parameters_path: task_root / "artifacts/04-alignment/aligned_parameters.json",
        runtime_dir: task_root / "交付物/runtime",
        manifest_path: task_root / "artifacts/05-delivery/delivery_manifest.json",
    }
    for actual, expected in expected_paths.items():
        if actual != expected.resolve():
            errors.append(f"交付校验路径必须使用任务标准位置: {actual} != {expected}")
    schema = load(ROOT / "assets/schemas/delivery-manifest.schema.json")
    for error in Draft202012Validator(schema).iter_errors(manifest):
        location = ".".join(map(str, error.absolute_path)) or "$"
        errors.append(f"delivery_manifest:{location}: {error.message}")
    task_id = formal.get("task_id")
    if not isinstance(task_id, str) or not task_id:
        errors.append("FORMAL结果缺少task_id")
    if manifest.get("task_id") != task_id:
        errors.append("delivery_manifest.task_id必须与FORMAL task_id一致")
    if manifest.get("runtime_version") != task_id:
        errors.append("delivery_manifest.runtime_version必须等于task_id")
    if manifest.get("formal_result_sha256") != sha256_file(formal_path):
        errors.append("delivery_manifest绑定的formal_result_sha256不一致")
    if manifest.get("alignment_manifest_sha256") != sha256_file(alignment_manifest_path):
        errors.append("delivery_manifest绑定的alignment_manifest_sha256不一致")
    if manifest.get("aligned_parameters_sha256") != sha256_file(aligned_parameters_path):
        errors.append("delivery_manifest绑定的aligned_parameters_sha256不一致")
    source_formal = manifest.get("source_formal_result", {})
    source_formal_path = task_root / source_formal.get("path", "")
    if not source_formal_path.is_file():
        errors.append("delivery_manifest绑定的FORMAL来源结果不存在")
    else:
        source_hash = sha256_file(source_formal_path)
        if source_formal.get("sha256") != source_hash or source_hash != sha256_file(formal_path):
            errors.append("FORMAL工作区结果与晋级formal_result.json不一致")
    promoted = [item for item in alignment_manifest.get("formal_batches", []) if item.get("promoted_to_artifact") is True]
    if len(promoted) != 1:
        errors.append("alignment_manifest必须且只能标记一个FORMAL晋级批次")
        formal_binding = {}
    else:
        formal_binding = promoted[0]
    if {"batch_id": formal_binding.get("batch_id"), **(formal_binding.get("result") or {})} != source_formal:
        errors.append("alignment_manifest与delivery_manifest绑定的FORMAL来源不一致")
    if aligned_parameters.get("task_id") != task_id or alignment_manifest.get("task_id") != task_id:
        errors.append("对齐manifest或最终参数与FORMAL task_id不一致")
    selected = [item for item in alignment_manifest.get("candidate_freezes", []) if item.get("selected_for_formal") is True]
    if len(selected) != 1:
        errors.append("alignment_manifest必须且只能标记一个FORMAL候选")
        selected_freeze = {}
    else:
        selected_freeze = selected[0]
    candidate_id = formal_binding.get("candidate_id")
    if not candidate_id or candidate_id != selected_freeze.get("candidate_id") or candidate_id != aligned_parameters.get("candidate_id"):
        errors.append("FORMAL批次、冻结候选与最终参数的candidate_id不一致")
    freeze_path = task_root / selected_freeze.get("path", "")
    if not freeze_path.is_file():
        errors.append("入选候选的freeze_manifest不存在")
        freeze = {}
    else:
        freeze = load(freeze_path)
        if selected_freeze.get("sha256") != sha256_file(freeze_path) or aligned_parameters.get("freeze_manifest_sha256") != sha256_file(freeze_path):
            errors.append("入选候选的freeze_manifest SHA-256绑定不一致")
    parameter_binding = aligned_parameters.get("parameter_record") or {}
    parameter_path = task_root / parameter_binding.get("path", "")
    if not parameter_path.is_file():
        errors.append("最终参数绑定的parameter_record不存在")
    else:
        parameter_record = load(parameter_path)
        if parameter_binding.get("sha256") != sha256_file(parameter_path):
            errors.append("最终参数绑定的parameter_record SHA-256不一致")
        if aligned_parameters.get("parameters") != parameter_record.get("complete_parameters"):
            errors.append("aligned_parameters.parameters必须等于parameter_record.complete_parameters")
    if freeze and aligned_parameters.get("runtime_bundle_sha256") != freeze.get("runtime_bundle_sha256"):
        errors.append("最终参数与冻结候选的Runtime bundle SHA-256不一致")
    entries = manifest.get("runtime_files", [])
    names = [item.get("name") for item in entries if isinstance(item, dict)]
    if names != RUNTIME_FILES:
        errors.append(f"Runtime文件清单或顺序必须为{RUNTIME_FILES}")
    by_name = {item.get("name"): item for item in entries if isinstance(item, dict)}
    for name in RUNTIME_FILES:
        path = runtime_dir / name
        entry = by_name.get(name, {})
        if entry.get("path") != f"交付物/runtime/{name}":
            errors.append(f"{name}的manifest路径不正确")
        expected_source = f"work/formal/{source_formal.get('batch_id')}/runtime/{name}"
        if entry.get("source_path") != expected_source:
            errors.append(f"{name}的FORMAL来源路径不正确")
        source_path = task_root / entry.get("source_path", "")
        if not source_path.is_file():
            errors.append(f"FORMAL来源Runtime缺少文件: {name}")
        if not path.is_file():
            errors.append(f"交付Runtime缺少文件: {name}")
        elif source_path.is_file():
            source_hash, delivery_hash = sha256_file(source_path), sha256_file(path)
            if entry.get("sha256") != source_hash or source_hash != delivery_hash:
                errors.append(f"FORMAL与交付Runtime文件hash不一致: {name}")
    core_path = runtime_dir / "game_core.json"
    if core_path.is_file():
        core = load(core_path)
        meta = core.get("meta") if isinstance(core, dict) else None
        if not isinstance(meta, dict) or meta.get("version") != task_id:
            errors.append("game_core.json.meta.version必须等于task_id")
    return errors


def main():
    parser = argparse.ArgumentParser(description="校验slot-alignment 6.0交付Runtime版本与manifest")
    parser.add_argument("--task-root", required=True)
    parser.add_argument("--formal-result", required=True)
    parser.add_argument("--alignment-manifest", required=True)
    parser.add_argument("--aligned-parameters", required=True)
    parser.add_argument("--runtime-dir", required=True)
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args()
    errors = validate_delivery(args.task_root, args.formal_result, args.alignment_manifest, args.aligned_parameters, args.runtime_dir, args.manifest)
    if errors:
        print("\n".join(f"ERROR: {item}" for item in errors), file=sys.stderr)
        raise SystemExit(1)
    print(f"OK: 交付Runtime版本={load(args.formal_result).get('task_id')}，四件套与manifest一致")


if __name__ == "__main__":
    main()
