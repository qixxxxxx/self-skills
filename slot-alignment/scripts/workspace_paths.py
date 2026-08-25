#!/usr/bin/env python3
import re
from pathlib import Path


REPORT_FILES = {
    1: "阶段1-资料确认与玩法画像.md",
    2: "阶段2-指标匹配报告.md",
    3: "阶段3-评分报告.md",
    4: "阶段4-数值对齐报告.md",
    5: "阶段5-交付清单.md",
}
RUNTIME_FILES = ("game_core.json", "payout_config.json", "reel_config.json", "symbol_catalog.json")
REPORT_VERSION_PATTERN = re.compile(r"^rv\d{4}$")


def task_root(artifacts):
    artifacts = Path(artifacts)
    return artifacts.parent if artifacts.name == "artifacts" else artifacts


def latest_report_dir(artifacts):
    root = task_root(artifacts)
    documents = root / "交付物/报告文档"
    versions = sorted(path for path in documents.iterdir() if path.is_dir() and REPORT_VERSION_PATTERN.match(path.name)) if documents.is_dir() else []
    if versions:
        return versions[-1]
    legacy = Path(artifacts)
    if any((legacy / rel).is_file() for rel in (
        "01-input-profile/阶段1-资料确认与玩法画像.md",
        "02-metric-matching/阶段2-指标匹配报告.md",
        "03-scoring/阶段3-评分报告.md",
        "04-alignment/阶段4-数值对齐报告.md",
    )):
        return legacy
    return documents / "rv0001"


def report_path(report_dir, stage):
    report_dir = Path(report_dir)
    if report_dir.name == "artifacts":
        legacy_stage_dirs = {1: "01-input-profile", 2: "02-metric-matching", 3: "03-scoring", 4: "04-alignment", 5: "05-delivery"}
        return report_dir / legacy_stage_dirs[stage] / REPORT_FILES[stage]
    return report_dir / REPORT_FILES[stage]


def resolve_manifest_path(artifacts, rel):
    rel_path = Path(rel)
    root = task_root(artifacts)
    if rel_path.parts and rel_path.parts[0] in {"artifacts", "交付物", "post-delivery-server-flow"}:
        return root / rel_path
    return Path(artifacts) / rel_path
