#!/usr/bin/env python3
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

from render_alignment_report import render as render_stage4
from render_delivery_report import render as render_stage5
from render_input_profile_report import render as render_stage1
from render_metric_matching_report import render as render_stage2
from render_scoring_report import render as render_stage3
from report_common import TEMPLATE_PATHS, validate_report_against_template, validate_server_flow_policy, validate_templates
from workspace_paths import REPORT_FILES, REPORT_VERSION_PATTERN, RUNTIME_FILES, latest_report_dir, report_path as workspace_report_path, resolve_manifest_path, task_root


REQUIRED_STAGE14 = [
    "01-input-profile/input_manifest.json", "01-input-profile/game_profile.json", "01-input-profile/parameter_authority.json",
    "02-metric-matching/metric_contract.json",
    "03-scoring/scorecard.json",
    "04-alignment/alignment_manifest.json", "04-alignment/candidate_archive.json", "04-alignment/aligned_parameters.json", "04-alignment/formal_result.json"
]
STAGE3_GATE_REL = "03-scoring/stage3_gate.json"
REQUIRED_STAGE5 = ["05-delivery/delivery_manifest.json", "05-delivery/delivery_checklist.json"]


def load(path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_tolerance_policy(contract):
    errors = []
    policy = contract.get("hard_gate_tolerance_policy")
    if not policy:
        return errors
    factors = policy.get("metric_factors", {})
    default_factor = policy.get("default_factor", 1.0)
    locked = set(policy.get("locked_metrics", []))
    for metric in contract.get("metrics", []):
        if metric.get("kind") != "hard" or metric.get("status") == "不适用":
            continue
        metric_id = metric.get("metric_id", "")
        profile = metric.get("hard_gate_profile", {})
        try:
            base = float(profile["base_tolerance"])
            factor = float(profile["tolerance_factor"])
            effective = float(profile["tolerance"])
            expected_factor = float(factors.get(metric_id, default_factor))
        except (KeyError, TypeError, ValueError):
            errors.append(f"硬指标容差字段无效: {metric_id}")
            continue
        if profile.get("tolerance_policy_id") != policy.get("policy_id"):
            errors.append(f"硬指标政策ID不一致: {metric_id}")
        if metric_id in locked and factor != 1.0:
            errors.append(f"锁定硬指标系数不是1.0: {metric_id}")
        if not math.isclose(factor, expected_factor, rel_tol=0.0, abs_tol=1e-12):
            errors.append(f"硬指标系数与政策不一致: {metric_id}")
        if not math.isclose(effective, base * factor, rel_tol=1e-12, abs_tol=1e-15):
            errors.append(f"硬指标生效容差计算错误: {metric_id}")
    return errors


def normalize_target(value):
    if isinstance(value, (int, float)):
        return float(value), float(value)
    if isinstance(value, list) and len(value) == 2:
        return float(value[0]), float(value[1])
    if isinstance(value, dict) and "min" in value and "max" in value:
        return float(value["min"]), float(value["max"])
    raise ValueError("目标必须是数值、[min,max]或{min,max}")


def schema_at_least(contract, major, minor):
    try:
        current_major, current_minor = map(int, str(contract.get("schema_version", "1.0")).split(".")[:2])
        return (current_major, current_minor) >= (major, minor)
    except ValueError:
        return False


def validate_component_rtp_targets(contract):
    errors = []
    policy = contract.get("component_rtp_target_policy")
    components = [
        metric for metric in contract.get("metrics", [])
        if metric.get("metric_id") == "core.rtp.component_contribution" and metric.get("status") != "不适用"
    ]
    if not policy and not components:
        return errors
    if not policy:
        return ["组件RTP指标缺少component_rtp_target_policy"] if schema_at_least(contract, 1, 1) else errors
    method = "original_component_share_mapped_to_authoritative_total_rtp"
    if policy.get("method") != method:
        errors.append("组件RTP目标映射方法无效")
    if policy.get("original_absolute_rtp_as_target") is not False:
        errors.append("组件RTP不得使用原版绝对RTP作为目标")
    if policy.get("authoritative_total_rtp_required") is not True:
        errors.append("组件RTP映射必须绑定权威总RTP")
    if not components:
        return errors
    try:
        total_low, total_high = normalize_target(contract.get("scope", {}).get("target_rtp"))
    except (TypeError, ValueError) as exc:
        errors.append(f"权威总RTP目标无效: {exc}")
        return errors
    shares, target_lows, target_highs = [], [], []
    for metric in components:
        scope = metric.get("scope", "")
        derivation = metric.get("target_derivation", {})
        if derivation.get("method") != method:
            errors.append(f"组件RTP目标推导方法无效: {scope}")
            continue
        if not derivation.get("source_evidence"):
            errors.append(f"组件RTP缺少原版占比证据: {scope}")
        try:
            share = float(derivation["original_component_share"])
            target_low, target_high = normalize_target(metric["target"])
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(f"组件RTP目标字段无效 {scope}: {exc}")
            continue
        shares.append(share)
        target_lows.append(target_low)
        target_highs.append(target_high)
        if not math.isclose(target_low, share * total_low, rel_tol=1e-12, abs_tol=1e-12) or not math.isclose(target_high, share * total_high, rel_tol=1e-12, abs_tol=1e-12):
            errors.append(f"组件RTP目标未按贡献占比映射: {scope}")
    if shares and not math.isclose(sum(shares), 1.0, rel_tol=0.0, abs_tol=1e-9):
        errors.append(f"组件RTP贡献占比合计不为1: {sum(shares)}")
    if target_lows and (not math.isclose(sum(target_lows), total_low, rel_tol=1e-12, abs_tol=1e-12) or not math.isclose(sum(target_highs), total_high, rel_tol=1e-12, abs_tol=1e-12)):
        errors.append("组件RTP目标合计未还原权威总RTP")
    return errors


def validate_attainability_ceiling(root):
    errors = []
    manifest_path = root / "04-alignment/alignment_manifest.json"
    archive_path = root / "04-alignment/candidate_archive.json"
    if not manifest_path.is_file() or not archive_path.is_file():
        return errors
    manifest, archive = load(manifest_path), load(archive_path)
    policy = manifest.get("budget_policy", {}).get("attainability_ceiling")
    if not policy:
        return errors
    if policy.get("enabled") is not True or policy.get("prohibit_budget_only_expansion") is not True:
        errors.append("预算可达性上限未启用或未禁止单纯追加预算")
    attainability = archive.get("attainability", {})
    if attainability.get("status") in {"结构不可达", "授权参数空间不可达"}:
        if attainability.get("budget_expansion_allowed") is not False:
            errors.append("结构不可达后仍允许预算扩张")
        if not attainability.get("evidence_path") or not attainability.get("evidence_sha256"):
            errors.append("结构不可达缺少密封证据路径或hash")
    return errors


def required_stage14(root):
    required = list(REQUIRED_STAGE14)
    manifest_path = root / "04-alignment/alignment_manifest.json"
    if manifest_path.is_file():
        try:
            if schema_at_least(load(manifest_path), 1, 2):
                required.append(STAGE3_GATE_REL)
        except (OSError, json.JSONDecodeError):
            pass
    return required


def validate_stage3_gate(root):
    errors = []
    manifest_path = root / "04-alignment/alignment_manifest.json"
    archive_path = root / "04-alignment/candidate_archive.json"
    if not manifest_path.is_file():
        return errors
    manifest = load(manifest_path)
    if not schema_at_least(manifest, 1, 2):
        return errors
    binding = manifest.get("stage3_gate", {})
    if binding.get("path") != STAGE3_GATE_REL:
        errors.append("阶段4未绑定固定stage3_gate路径")
        return errors
    gate_path = root / STAGE3_GATE_REL
    if not gate_path.is_file():
        return ["缺少阶段3到阶段4门禁文件"]
    gate_hash = sha(gate_path)
    if binding.get("sha256") != gate_hash or binding.get("stage4_allowed") is not True:
        errors.append("阶段4manifest中的stage3_gate绑定无效")
    gate = load(gate_path)
    if gate.get("status") != "通过" or gate.get("stage4_allowed") is not True or gate.get("errors"):
        errors.append("阶段3到阶段4门禁未通过")
    for rel, expected in gate.get("source_hashes", {}).items():
        path = resolve_manifest_path(root, rel)
        if not path.is_file() or sha(path) != expected:
            errors.append(f"阶段3门禁上游hash失效: {rel}")
    score_path = root / "03-scoring/scorecard.json"
    contract_path = root / "02-metric-matching/metric_contract.json"
    if score_path.is_file() and contract_path.is_file():
        score = load(score_path)
        source_hashes = score.get("source_hashes", {})
        source_paths = score.get("source_paths", {})
        if source_hashes.get("metric_contract") != sha(contract_path):
            errors.append("阶段3评分绑定的指标合同hash失效")
        measurement_path = Path(source_paths.get("measurements", ""))
        if not measurement_path.is_file() or source_hashes.get("measurements") != sha(measurement_path):
            errors.append("阶段3评分绑定的基线测量源失效")
    if archive_path.is_file():
        archive = load(archive_path)
        if archive.get("stage3_gate_sha256") != gate_hash:
            errors.append("候选档案未绑定当前stage3_gate hash")
    return errors


def validate(root, require_delivery=True, reports=None):
    skill_root = Path(__file__).resolve().parent.parent
    errors, task_ids = validate_templates(skill_root), set()
    reports = Path(reports) if reports else latest_report_dir(root)
    if reports.name != "artifacts" and not REPORT_VERSION_PATTERN.match(reports.name):
        errors.append("报告目录必须使用rv####命名")
    if reports.name != "artifacts":
        for markdown in root.rglob("*.md"):
            errors.append(f"artifacts只允许机器JSON，发现Markdown: {markdown.relative_to(root)}")
    required = required_stage14(root) + (REQUIRED_STAGE5 if require_delivery else [])
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
    if len(task_ids) > 1:
        errors.append(f"task_id不一致: {sorted(task_ids)}")
    required_reports = range(1, 6 if require_delivery else 5)
    for stage in required_reports:
        path = workspace_report_path(reports, stage)
        if not path.is_file():
            errors.append(f"缺少必需中文报告: {REPORT_FILES[stage]}")
        elif "{{" in path.read_text(encoding="utf-8"):
            errors.append(f"Markdown仍含模板占位符: {path}")
    stage1_paths = [root / "01-input-profile/input_manifest.json", root / "01-input-profile/game_profile.json", root / "01-input-profile/parameter_authority.json", workspace_report_path(reports, 1)]
    input_manifest = None
    if all(path.is_file() for path in stage1_paths):
        input_manifest, profile, authority = map(load, stage1_paths[:3])
        actual = stage1_paths[3].read_text(encoding="utf-8")
        expected = render_stage1(input_manifest, profile, authority, {"input_manifest": sha(stage1_paths[0]), "game_profile": sha(stage1_paths[1]), "parameter_authority": sha(stage1_paths[2])})
        errors += validate_report_against_template(actual, (skill_root / TEMPLATE_PATHS[1]).read_text(encoding="utf-8"), 1)
        if actual != expected:
            errors.append("阶段1报告不是当前机器JSON的确定性完整输出")
    contract_path = root / "02-metric-matching/metric_contract.json"
    if contract_path.is_file():
        contract = load(contract_path)
        errors += validate_tolerance_policy(contract)
        errors += validate_component_rtp_targets(contract)
        stage2_path = workspace_report_path(reports, 2)
        if stage2_path.is_file():
            actual = stage2_path.read_text(encoding="utf-8")
            errors += validate_report_against_template(actual, (skill_root / TEMPLATE_PATHS[2]).read_text(encoding="utf-8"), 2)
            if actual != render_stage2(contract, sha(contract_path)):
                errors.append("阶段2报告不是当前指标合同的确定性完整输出")
    errors += validate_attainability_ceiling(root)
    errors += validate_stage3_gate(root)
    score_path = root / "03-scoring/scorecard.json"
    stage3_report_path = workspace_report_path(reports, 3)
    if score_path.is_file() and contract_path.is_file() and stage3_report_path.is_file():
        score = load(score_path)
        actual = stage3_report_path.read_text(encoding="utf-8")
        errors += validate_report_against_template(actual, (skill_root / TEMPLATE_PATHS[3]).read_text(encoding="utf-8"), 3)
        if actual != render_stage3(load(contract_path), score, sha(contract_path), sha(score_path)):
            errors.append("阶段3报告不是当前合同与scorecard的确定性完整输出")
    report_path = workspace_report_path(reports, 4)
    formal_path = root / "04-alignment/formal_result.json"
    if score_path.is_file() and report_path.is_file() and formal_path.is_file():
        score, formal, report = load(score_path), load(formal_path), report_path.read_text(encoding="utf-8")
        expected = formal.get("scorecard", {}).get("alignment_status") or score.get("alignment_status")
        if expected not in report:
            errors.append("阶段4报告未展示最终对齐状态")
        try:
            expected_report, _ = render_stage4(root)
            errors += validate_report_against_template(report, (skill_root / TEMPLATE_PATHS[4]).read_text(encoding="utf-8"), 4)
            if report != expected_report:
                errors.append("阶段4报告不是当前阶段1至4机器结果的确定性完整输出")
        except (OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"阶段4报告复算失败: {exc}")
    if formal_path.is_file():
        formal = load(formal_path)
        if formal.get("execution_valid") and not formal.get("independent_from_calibration"):
            errors.append("有效FORMAL缺少CALIBRATION独立性")
        alignment_manifest_path = root / "04-alignment/alignment_manifest.json"
        candidate_archive_path = root / "04-alignment/candidate_archive.json"
        if input_manifest is not None and alignment_manifest_path.is_file() and candidate_archive_path.is_file():
            errors += validate_server_flow_policy(input_manifest, load(alignment_manifest_path), load(candidate_archive_path), formal)
        elif input_manifest is not None:
            errors += validate_server_flow_policy(input_manifest)
    manifest_path = root / "05-delivery/delivery_manifest.json"
    if require_delivery and manifest_path.is_file():
        delivery_manifest = load(manifest_path)
        for item in delivery_manifest.get("files", []):
            path = resolve_manifest_path(root, item.get("path", ""))
            if not path.is_file() or sha(path) != item.get("sha256"):
                errors.append(f"交付Hash无效: {item.get('path')}")
        delivery_runtime = task_root(root) / "交付物/runtime"
        for name in RUNTIME_FILES:
            path = delivery_runtime / name
            if not path.is_file():
                errors.append(f"交付物缺少FORMAL Runtime文件: {name}")
        game_core_path = delivery_runtime / "game_core.json"
        if game_core_path.is_file():
            try:
                game_core = load(game_core_path)
                task_id = delivery_manifest.get("task_id")
                if game_core.get("meta", {}).get("version") != task_id:
                    errors.append("交付Runtime meta.version必须等于task_id")
                routing = game_core.get("runtime_flags", {}).get("rtp_routing", {})
                if routing.get("default_group") != 1 or routing.get("groups") != [1]:
                    errors.append("交付Runtime只允许RTP Group 1")
            except (OSError, json.JSONDecodeError) as exc:
                errors.append(f"交付Runtime game_core.json无效: {exc}")
        checklist_path = root / "05-delivery/delivery_checklist.json"
        delivery_report_path = workspace_report_path(reports, 5)
        if checklist_path.is_file() and delivery_report_path.is_file():
            actual = delivery_report_path.read_text(encoding="utf-8")
            errors += validate_report_against_template(actual, (skill_root / TEMPLATE_PATHS[5]).read_text(encoding="utf-8"), 5)
            if actual != render_stage5(delivery_manifest, load(checklist_path)):
                errors.append("阶段5报告不是当前交付manifest与checklist的确定性完整输出")
    return errors


def main():
    parser = argparse.ArgumentParser(description="验证固定 artifacts 结构与一致性")
    parser.add_argument("--artifacts", required=True, type=Path)
    parser.add_argument("--reports", type=Path)
    parser.add_argument("--pre-delivery", action="store_true")
    args = parser.parse_args()
    errors = validate(args.artifacts, not args.pre_delivery, args.reports)
    print(json.dumps({"status": "通过" if not errors else "失败", "errors": errors}, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
