#!/usr/bin/env python3
import argparse
import hashlib
import json
import sys
from pathlib import Path


REQUIRED_STAGE14 = [
    "01-input-profile/input_manifest.json", "01-input-profile/game_profile.json", "01-input-profile/parameter_authority.json", "01-input-profile/阶段1-资料确认与玩法画像.md",
    "02-metric-matching/metric_contract.json", "02-metric-matching/阶段2-指标匹配报告.md",
    "03-scoring/scorecard.json", "03-scoring/阶段3-评分报告.md",
    "04-alignment/alignment_manifest.json", "04-alignment/candidate_archive.json", "04-alignment/aligned_parameters.json", "04-alignment/formal_result.json", "04-alignment/阶段4-数值对齐报告.md"
]
REQUIRED_STAGE5 = ["05-delivery/delivery_manifest.json", "05-delivery/delivery_checklist.json", "05-delivery/阶段5-交付清单.md"]


def load(path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(root, require_delivery=True):
    errors, task_ids = [], set()
    required = REQUIRED_STAGE14 + (REQUIRED_STAGE5 if require_delivery else [])
    for rel in required:
        path = root / rel
        if not path.is_file():
            errors.append(f"缺少必需文件: {rel}")
            continue
        if path.suffix == ".json":
            try:
                data = load(path)
                if data.get("task_id"):
                    task_ids.add(data["task_id"])
            except (OSError, json.JSONDecodeError) as exc:
                errors.append(f"JSON无效 {rel}: {exc}")
        elif "{{" in path.read_text(encoding="utf-8"):
            errors.append(f"Markdown仍含模板占位符: {rel}")
    if len(task_ids) > 1:
        errors.append(f"task_id不一致: {sorted(task_ids)}")
    score_path = root / "03-scoring/scorecard.json"
    report_path = root / "04-alignment/阶段4-数值对齐报告.md"
    formal_path = root / "04-alignment/formal_result.json"
    if score_path.is_file() and report_path.is_file() and formal_path.is_file():
        score, formal, report = load(score_path), load(formal_path), report_path.read_text(encoding="utf-8")
        expected = formal.get("scorecard", {}).get("alignment_status") or score.get("alignment_status")
        if expected not in report:
            errors.append("阶段4报告未展示最终对齐状态")
    if formal_path.is_file():
        formal = load(formal_path)
        if formal.get("execution_valid") and not formal.get("independent_from_calibration"):
            errors.append("有效FORMAL缺少CALIBRATION独立性")
    manifest_path = root / "05-delivery/delivery_manifest.json"
    if require_delivery and manifest_path.is_file():
        for item in load(manifest_path).get("files", []):
            path = root / item.get("path", "")
            if not path.is_file() or sha(path) != item.get("sha256"):
                errors.append(f"交付Hash无效: {item.get('path')}")
    return errors


def main():
    parser = argparse.ArgumentParser(description="验证固定 artifacts 结构与一致性")
    parser.add_argument("--artifacts", required=True, type=Path)
    parser.add_argument("--pre-delivery", action="store_true")
    args = parser.parse_args()
    errors = validate(args.artifacts, not args.pre_delivery)
    print(json.dumps({"status": "通过" if not errors else "失败", "errors": errors}, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
