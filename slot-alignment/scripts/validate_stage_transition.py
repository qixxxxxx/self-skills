#!/usr/bin/env python3
import argparse
import hashlib
import json
import sys
from pathlib import Path

from render_scoring_report import render
from render_input_profile_report import render as render_stage1
from render_metric_matching_report import render as render_stage2
from report_common import TEMPLATE_PATHS, validate_report_against_template, validate_server_flow_policy, validate_templates
from workspace_paths import REPORT_FILES, latest_report_dir, report_path as workspace_report_path, task_root


REQUIRED = [
    "01-input-profile/input_manifest.json",
    "01-input-profile/game_profile.json",
    "01-input-profile/parameter_authority.json",
    "02-metric-matching/metric_contract.json",
    "03-scoring/scorecard.json",
]


def load(path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def validate(root, reports=None):
    skill_root = Path(__file__).resolve().parent.parent
    errors = validate_templates(skill_root)
    reports = Path(reports) if reports else latest_report_dir(root)
    paths = {rel: root / rel for rel in REQUIRED}
    for rel, path in paths.items():
        if not path.is_file():
            errors.append(f"缺少阶段转换必需文件: {rel}")
    report_paths = {stage: workspace_report_path(reports, stage) for stage in (1, 2, 3)}
    for stage, path in report_paths.items():
        if not path.is_file():
            errors.append(f"缺少阶段转换必需报告: {REPORT_FILES[stage]}")
        elif "{{" in path.read_text(encoding="utf-8"):
            errors.append(f"阶段报告仍含模板占位符: {path}")
    if errors:
        return errors, {}
    input_manifest = load(paths["01-input-profile/input_manifest.json"])
    game_profile = load(paths["01-input-profile/game_profile.json"])
    authority = load(paths["01-input-profile/parameter_authority.json"])
    contract = load(paths["02-metric-matching/metric_contract.json"])
    scorecard = load(paths["03-scoring/scorecard.json"])
    task_ids = {item.get("task_id") for item in (input_manifest, game_profile, authority, contract, scorecard) if item.get("task_id")}
    if len(task_ids) != 1:
        errors.append(f"阶段1至3 task_id不一致: {sorted(task_ids)}")
    for name, item in (("input_manifest", input_manifest), ("game_profile", game_profile), ("parameter_authority", authority), ("metric_contract", contract)):
        if item.get("status") != "已完成":
            errors.append(f"上游阶段状态未完成: {name}={item.get('status')}")
    errors += validate_server_flow_policy(input_manifest)
    if scorecard.get("status") != "已完成" or scorecard.get("blocking_reasons"):
        errors.append("阶段3评分未完成或仍有阻塞")
    if scorecard.get("alignment_status") == "无法判定":
        errors.append("阶段3基线评分无法判定")
    expected_stage1 = render_stage1(input_manifest, game_profile, authority, {
        "input_manifest": sha(paths["01-input-profile/input_manifest.json"]),
        "game_profile": sha(paths["01-input-profile/game_profile.json"]),
        "parameter_authority": sha(paths["01-input-profile/parameter_authority.json"]),
    })
    stage1_report = report_paths[1].read_text(encoding="utf-8")
    errors += validate_report_against_template(stage1_report, (skill_root / TEMPLATE_PATHS[1]).read_text(encoding="utf-8"), 1)
    if stage1_report != expected_stage1:
        errors.append("阶段1中文报告不是当前三份机器JSON的确定性完整输出")
    expected_stage2 = render_stage2(contract, sha(paths["02-metric-matching/metric_contract.json"]))
    stage2_report = report_paths[2].read_text(encoding="utf-8")
    errors += validate_report_against_template(stage2_report, (skill_root / TEMPLATE_PATHS[2]).read_text(encoding="utf-8"), 2)
    if stage2_report != expected_stage2:
        errors.append("阶段2中文报告不是当前指标合同的确定性完整输出")
    applicable_hard = [item for item in contract.get("metrics", []) if item.get("kind") == "hard" and item.get("status") != "不适用"]
    applicable_scores = [item for item in contract.get("metrics", []) if item.get("kind") == "score" and item.get("status") != "不适用"]
    if len(scorecard.get("hard_gates", [])) != len(applicable_hard):
        errors.append("阶段3硬指标结果数量与合同不一致")
    if len(scorecard.get("scores", [])) != len(applicable_scores):
        errors.append("阶段3评分指标结果数量与合同不一致")
    source_hashes = scorecard.get("source_hashes", {})
    source_paths = scorecard.get("source_paths", {})
    if source_hashes.get("metric_contract") != sha(paths["02-metric-matching/metric_contract.json"]):
        errors.append("阶段3评分未绑定当前指标合同hash")
    measurement_path = Path(source_paths.get("measurements", ""))
    if not measurement_path.is_file():
        errors.append("阶段3基线测量源不存在")
    elif source_hashes.get("measurements") != sha(measurement_path):
        errors.append("阶段3基线测量hash失效")
    report_path = report_paths[3]
    expected_report = render(contract, scorecard, sha(paths["02-metric-matching/metric_contract.json"]), sha(paths["03-scoring/scorecard.json"]))
    errors += validate_report_against_template(report_path.read_text(encoding="utf-8"), (skill_root / TEMPLATE_PATHS[3]).read_text(encoding="utf-8"), 3)
    if report_path.read_text(encoding="utf-8") != expected_report:
        errors.append("阶段3中文报告不是当前机器结果的确定性输出")
    root_dir = task_root(root)
    hashes = {str(path.relative_to(root_dir)): sha(path) for path in [*paths.values(), *report_paths.values()] if path.is_file()}
    return errors, hashes


def main():
    parser = argparse.ArgumentParser(description="校验阶段3到阶段4的强制转换门禁")
    parser.add_argument("--artifacts", required=True, type=Path)
    parser.add_argument("--reports", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        errors, hashes = validate(args.artifacts, args.reports)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors, hashes = [str(exc)], {}
    task_id = ""
    manifest_path = args.artifacts / "01-input-profile/input_manifest.json"
    if manifest_path.is_file():
        try:
            task_id = load(manifest_path).get("task_id", "")
        except (OSError, json.JSONDecodeError):
            pass
    result = {
        "schema_version": "slot-alignment.stage3-gate.v1",
        "task_id": task_id,
        "status": "通过" if not errors else "阻塞",
        "transition": "03-scoring->04-alignment",
        "stage4_allowed": not errors,
        "errors": errors,
        "source_hashes": hashes
    }
    dump(args.output, result)
    print(json.dumps({"status": result["status"], "stage4_allowed": result["stage4_allowed"], "errors": errors, "output": str(args.output)}, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
