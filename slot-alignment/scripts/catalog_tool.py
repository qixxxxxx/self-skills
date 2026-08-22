#!/usr/bin/env python3
import argparse
import hashlib
import json
import sys
from pathlib import Path


def load(path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_index(root, kind):
    base = root / "references" / kind
    index = load(base / "index.json")
    errors, ids, files = [], set(), [base / "index.json", base / "index.md"]
    expected_type = "mechanic_package" if kind == "mechanics" else "metric_package"
    item_key = "mechanics" if kind == "mechanics" else "metrics"
    id_key = "mechanic_id" if kind == "mechanics" else "metric_id"
    for entry in index.get("packages", []):
        path = base / entry["path"]
        md = path.with_name("catalog.md")
        files += [path, md]
        if not path.is_file() or not md.is_file():
            errors.append(f"缺少目录文件: {path} 或 {md}")
            continue
        data = load(path)
        if data.get("catalog_type") != expected_type:
            errors.append(f"catalog_type错误: {path}")
        if data.get("package_id") != entry.get("package_id"):
            errors.append(f"package_id与索引不一致: {path}")
        if entry.get("sha256") != digest(path):
            errors.append(f"目录hash与索引不一致: {path}")
        text = md.read_text(encoding="utf-8")
        for item in data.get(item_key, []):
            item_id = item.get(id_key, "")
            if not item_id or item_id in ids:
                errors.append(f"{id_key}缺失或重复: {item_id}")
            ids.add(item_id)
            if item_id not in text:
                errors.append(f"中文目录未说明 {item_id}: {md}")
            if kind == "metrics" and item.get("owner") != data.get("package_id"):
                errors.append(f"Owner不等于所属包: {item_id}")
            if kind == "metrics" and item.get("kind") == "hard" and "hard_gate_profile" not in item:
                errors.append(f"硬指标缺少hard_gate_profile: {item_id}")
            if kind == "metrics" and item.get("kind") == "score" and "score_profile" not in item:
                errors.append(f"评分指标缺少score_profile: {item_id}")
    return errors, files, len(ids)


def main():
    parser = argparse.ArgumentParser(description="验证或计算玩法/指标目录哈希")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("validate", "hash"):
        p = sub.add_parser(name)
        p.add_argument("--skill-root", required=True, type=Path)
    args = parser.parse_args()
    all_errors, all_files, counts = [], [], {}
    for kind in ("mechanics", "metrics"):
        errors, files, count = validate_index(args.skill_root, kind)
        all_errors += errors
        all_files += files
        counts[kind] = count
    if all_errors:
        print(json.dumps({"status": "失败", "errors": all_errors}, ensure_ascii=False, indent=2))
        return 1
    result = {"status": "通过", "counts": counts}
    if args.cmd == "hash":
        result["files"] = {str(p.relative_to(args.skill_root)): digest(p) for p in sorted(set(all_files))}
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
