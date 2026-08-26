#!/usr/bin/env python3
import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from validate_artifacts import INPUT_VALIDATION_EXCEPTIONS, required_stage14, validate
from render_delivery_report import render
from workspace_paths import REPORT_FILES, RUNTIME_FILES, latest_report_dir, report_path, task_root


def load(path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def next_version(versions):
    nums = [int(p.name[2:]) for p in versions.iterdir() if p.is_dir() and p.name.startswith("dv") and p.name[2:].isdigit()] if versions.exists() else []
    return f"dv{(max(nums, default=0) + 1):04d}"


def delivery_report_contract_version(input_manifest):
    version = input_manifest.get("report_contract_version")
    if not isinstance(version, str) or not version.strip():
        raise ValueError("input_manifest缺少显式report_contract_version")
    return version


def main():
    parser = argparse.ArgumentParser(description="原子生成阶段5交付清单")
    parser.add_argument("--artifacts", required=True, type=Path)
    parser.add_argument("--reports", type=Path)
    parser.add_argument("--formal-runtime", required=True, type=Path)
    parser.add_argument("--historical-replay", action="store_true", help="仅用于显式复算受支持的旧版密封任务")
    args = parser.parse_args()
    reports = args.reports or latest_report_dir(args.artifacts)
    try:
        errors = validate(
            args.artifacts,
            require_delivery=False,
            reports=reports,
            validation_mode="historical_replay" if args.historical_replay else "stage_transition",
        )
    except INPUT_VALIDATION_EXCEPTIONS as exc:
        errors = [f"校验输入结构无效（{type(exc).__name__}）: {exc}"]
    for name in RUNTIME_FILES:
        if not (args.formal_runtime / name).is_file():
            errors.append(f"FORMAL Runtime缺少文件: {name}")
    manifest_path = args.artifacts / "01-input-profile/input_manifest.json"
    if (args.formal_runtime / "game_core.json").is_file() and manifest_path.is_file():
        runtime_core = load(args.formal_runtime / "game_core.json")
        input_manifest = load(manifest_path)
        if runtime_core.get("meta", {}).get("version") != input_manifest.get("task_id"):
            errors.append("FORMAL Runtime meta.version必须等于task_id")
        routing = runtime_core.get("runtime_flags", {}).get("rtp_routing", {})
        if routing.get("default_group") != 1 or routing.get("groups") != [1]:
            errors.append("FORMAL Runtime只允许RTP Group 1")
    if errors:
        print(json.dumps({"status": "失败", "errors": errors}, ensure_ascii=False, indent=2))
        return 1
    delivery = args.artifacts / "05-delivery"
    versions = delivery / "versions"
    versions.mkdir(parents=True, exist_ok=True)
    version = next_version(versions)
    version_dir = versions / version
    version_dir.mkdir()
    formal = load(args.artifacts / "04-alignment/formal_result.json")
    formal_score = formal.get("scorecard", {})
    input_manifest = load(args.artifacts / "01-input-profile/input_manifest.json")
    report_contract_version = delivery_report_contract_version(input_manifest)
    root = task_root(args.artifacts)
    delivery_runtime = root / "交付物/runtime"
    delivery_runtime.mkdir(parents=True, exist_ok=True)
    for name in RUNTIME_FILES:
        shutil.copyfile(args.formal_runtime / name, delivery_runtime / name)
    files = []
    for rel in required_stage14(args.artifacts):
        path = args.artifacts / rel
        files.append({"path": f"artifacts/{rel}", "required": True, "role": "机器结果", "sha256": sha(path), "valid": True})
    for stage in range(1, 5):
        path = report_path(reports, stage)
        files.append({"path": str(path.relative_to(root)), "required": True, "role": "中文报告", "sha256": sha(path), "valid": True})
    for name in RUNTIME_FILES:
        path = delivery_runtime / name
        files.append({"path": str(path.relative_to(root)), "required": True, "role": "FORMAL Runtime", "sha256": sha(path), "valid": True})
    now = datetime.now(timezone.utc).isoformat()
    manifest = {"schema_version": "1.1", "report_contract_version": report_contract_version, "task_id": input_manifest.get("task_id", ""), "delivery_version": version, "alignment_status": formal_score.get("alignment_status", "无法判定"), "delivery_status": "通过", "files": files, "generated_at": now}
    checks = [
        {"check_id": "structure", "name_zh": "固定目录与必需文件", "status": "通过"},
        {"check_id": "scope", "name_zh": "作用域与task_id一致", "status": "通过"},
        {"check_id": "authorization", "name_zh": "参数权限产物存在", "status": "通过"},
        {"check_id": "formal", "name_zh": "FORMAL结果、Runtime四件套与中文报告存在", "status": "通过"},
        {"check_id": "hash", "name_zh": "阶段1至4、Runtime和报告SHA-256有效", "status": "通过"}
    ]
    checklist = {"schema_version": "1.1", "report_contract_version": report_contract_version, "task_id": input_manifest.get("task_id", ""), "delivery_version": version, "status": "通过", "checks": checks}
    md = render(manifest, checklist)
    dump(version_dir / "delivery_manifest.json", manifest)
    dump(version_dir / "delivery_checklist.json", checklist)
    dump(delivery / "delivery_manifest.json", manifest)
    dump(delivery / "delivery_checklist.json", checklist)
    stage5_report = report_path(reports, 5)
    stage5_report.parent.mkdir(parents=True, exist_ok=True)
    stage5_report.write_text(md, encoding="utf-8")
    print(json.dumps({"status": "通过", "delivery_version": version, "path": str(version_dir)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
