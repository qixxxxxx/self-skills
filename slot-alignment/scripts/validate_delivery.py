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


def main():
    parser = argparse.ArgumentParser(description="校验slot-alignment v5交付Runtime版本与manifest")
    parser.add_argument("--formal-result", required=True)
    parser.add_argument("--runtime-dir", required=True)
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args()
    formal_path, runtime_dir, manifest_path = Path(args.formal_result), Path(args.runtime_dir), Path(args.manifest)
    formal, manifest = load(formal_path), load(manifest_path)
    errors = []
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
        if not path.is_file():
            errors.append(f"交付Runtime缺少文件: {name}")
        elif entry.get("sha256") != sha256_file(path):
            errors.append(f"交付Runtime文件hash不一致: {name}")
    core_path = runtime_dir / "game_core.json"
    if core_path.is_file():
        core = load(core_path)
        meta = core.get("meta") if isinstance(core, dict) else None
        if not isinstance(meta, dict) or meta.get("version") != task_id:
            errors.append("game_core.json.meta.version必须等于task_id")
    if errors:
        print("\n".join(f"ERROR: {item}" for item in errors), file=sys.stderr)
        raise SystemExit(1)
    print(f"OK: 交付Runtime版本={task_id}，四件套与manifest一致")


if __name__ == "__main__":
    main()
