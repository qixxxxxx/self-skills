#!/usr/bin/env python3
import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from validate_artifacts import required_stage14, validate
from render_delivery_report import render


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


def main():
    parser = argparse.ArgumentParser(description="原子生成阶段5交付清单")
    parser.add_argument("--artifacts", required=True, type=Path)
    args = parser.parse_args()
    errors = validate(args.artifacts, require_delivery=False)
    if errors:
        print(json.dumps({"status": "失败", "errors": errors}, ensure_ascii=False, indent=2))
        return 1
    delivery = args.artifacts / "05-delivery"
    versions = delivery / "versions"
    versions.mkdir(parents=True, exist_ok=True)
    version = next_version(versions)
    version_dir = versions / version
    version_dir.mkdir()
    score = load(args.artifacts / "03-scoring/scorecard.json")
    input_manifest = load(args.artifacts / "01-input-profile/input_manifest.json")
    files = []
    for rel in required_stage14(args.artifacts):
        path = args.artifacts / rel
        files.append({"path": rel, "required": True, "role": "机器结果" if path.suffix == ".json" else "中文报告", "sha256": sha(path), "valid": True})
    now = datetime.now(timezone.utc).isoformat()
    manifest = {"schema_version": "1.1", "report_contract_version": "slot-alignment.reports.v2.5", "task_id": input_manifest.get("task_id", ""), "delivery_version": version, "alignment_status": score.get("alignment_status", "无法判定"), "delivery_status": "通过", "files": files, "generated_at": now}
    checks = [
        {"check_id": "structure", "name_zh": "固定目录与必需文件", "status": "通过"},
        {"check_id": "scope", "name_zh": "作用域与task_id一致", "status": "通过"},
        {"check_id": "authorization", "name_zh": "参数权限产物存在", "status": "通过"},
        {"check_id": "formal", "name_zh": "FORMAL结果与中文报告存在", "status": "通过"},
        {"check_id": "hash", "name_zh": "阶段1至4 SHA-256有效", "status": "通过"}
    ]
    checklist = {"schema_version": "1.1", "report_contract_version": "slot-alignment.reports.v2.5", "task_id": input_manifest.get("task_id", ""), "delivery_version": version, "status": "通过", "checks": checks}
    md = render(manifest, checklist)
    dump(version_dir / "delivery_manifest.json", manifest)
    dump(version_dir / "delivery_checklist.json", checklist)
    (version_dir / "阶段5-交付清单.md").write_text(md, encoding="utf-8")
    dump(delivery / "delivery_manifest.json", manifest)
    dump(delivery / "delivery_checklist.json", checklist)
    shutil.copyfile(version_dir / "阶段5-交付清单.md", delivery / "阶段5-交付清单.md")
    print(json.dumps({"status": "通过", "delivery_version": version, "path": str(version_dir)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
