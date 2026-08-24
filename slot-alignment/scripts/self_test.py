#!/usr/bin/env python3
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from validate_artifacts import validate_attainability_ceiling, validate_component_rtp_targets
from report_common import TEMPLATE_PATHS, validate_report_against_template, validate_template_text, validate_templates


ROOT = Path(__file__).resolve().parent
SKILL_ROOT = ROOT.parent


def dump(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(*args):
    return subprocess.run([sys.executable, *map(str, args)], check=True, capture_output=True, text=True)


def run_result(*args):
    return subprocess.run([sys.executable, *map(str, args)], check=False, capture_output=True, text=True)


def score_case(base, waiver=False, hard_fail=False):
    contract = {
        "schema_version": "1.0", "task_id": "self-test", "input_hashes": {}, "group_weights": {"experience": 1},
        "metrics": [
            {"metric_id": "core.rtp.total", "name_zh": "总RTP", "owner": "core.general", "kind": "hard", "scope": "base", "target": 0.96, "hard_gate_profile": {"method": "absolute_error", "tolerance": 0.002}},
            {"metric_id": "demo.a", "name_zh": "体验A", "owner": "demo", "kind": "score", "scope": "base", "target": 0.10, "score_group": "experience", "weight": 0.5, "score_profile": {"method": "absolute_error", "anchors": [[0,100],[0.01,85],[0.10,0]]}},
            {"metric_id": "demo.b", "name_zh": "体验B", "owner": "demo", "kind": "score", "scope": "base", "target": 0.20, "score_group": "experience", "weight": 0.5, "score_profile": {"method": "absolute_error", "anchors": [[0,100],[0.01,85],[0.10,0]]}, "waiver": {"status": "已批准" if waiver else "无"}}
        ]
    }
    measurements = {"measurements": [
        {"metric_id": "core.rtp.total", "scope": "base", "status": "有效", "value": 0.95 if hard_fail else 0.959},
        {"metric_id": "demo.a", "scope": "base", "status": "有效", "value": 0.103},
        {"metric_id": "demo.b", "scope": "base", "status": "有效", "value": 0.204}
    ]}
    dump(base / "contract.json", contract)
    dump(base / "measurements.json", measurements)
    run(ROOT / "score_alignment.py", "--contract", base / "contract.json", "--measurements", base / "measurements.json", "--output", base / "scorecard.json")
    return json.loads((base / "scorecard.json").read_text(encoding="utf-8"))


def tolerance_policy_case(base):
    contract = {
        "schema_version": "1.0", "task_id": "policy-test", "input_hashes": {}, "group_weights": {"experience": 1},
        "metrics": [
            {"metric_id": "core.rtp.total", "name_zh": "总RTP", "owner": "core.general", "kind": "hard", "scope": "base", "target": 0.96, "hard_gate_profile": {"method": "absolute_error", "tolerance": 0.002}},
            {"metric_id": "core.multiplier_distribution.lt200", "name_zh": "200x以下倍率分布", "owner": "core.general", "kind": "hard", "scope": "base", "target": [1.0, 0.0], "hard_gate_profile": {"method": "total_variation", "tolerance": 0.01}},
            {"metric_id": "demo.a", "name_zh": "体验A", "owner": "demo", "kind": "score", "scope": "base", "target": 0.10, "score_group": "experience", "weight": 1.0, "score_profile": {"method": "absolute_error", "anchors": [[0,100],[0.01,85],[0.10,0]]}}
        ]
    }
    measurements = {"measurements": [
        {"metric_id": "core.rtp.total", "scope": "base", "status": "有效", "value": 0.959},
        {"metric_id": "core.multiplier_distribution.lt200", "scope": "base", "status": "有效", "value": [0.964, 0.036]},
        {"metric_id": "demo.a", "scope": "base", "status": "有效", "value": 0.10}
    ]}
    dump(base / "base-contract.json", contract)
    dump(base / "measurements.json", measurements)
    run(ROOT / "apply_hard_gate_tolerance_policy.py", "--contract", base / "base-contract.json", "--policy", SKILL_ROOT / "assets/policies/hard_gate_tolerance_policy.v1.json", "--output", base / "contract.json")
    run(ROOT / "score_alignment.py", "--contract", base / "contract.json", "--measurements", base / "measurements.json", "--output", base / "scorecard.json")
    scorecard = json.loads((base / "scorecard.json").read_text(encoding="utf-8"))
    tampered = json.loads((base / "contract.json").read_text(encoding="utf-8"))
    tv = next(item for item in tampered["metrics"] if item["metric_id"] == "core.multiplier_distribution.lt200")
    tv["hard_gate_profile"]["tolerance"] = 0.041
    dump(base / "tampered-contract.json", tampered)
    invalid = run_result(ROOT / "score_alignment.py", "--contract", base / "tampered-contract.json", "--measurements", base / "measurements.json", "--output", base / "tampered-scorecard.json")
    assert invalid.returncode == 2
    return scorecard


def component_rtp_target_case(base):
    source = {
        "authoritative_total_rtp_target": {"min": 0.95, "max": 0.96},
        "components": [
            {"scope": "base", "original_component_share": 0.25, "source_evidence": "original.json#base"},
            {"scope": "feature:free-spin", "original_component_share": 0.75, "source_evidence": "original.json#feature"}
        ]
    }
    dump(base / "shares.json", source)
    run(ROOT / "derive_component_rtp_targets.py", "--input", base / "shares.json", "--output", base / "targets.json")
    result = json.loads((base / "targets.json").read_text(encoding="utf-8"))
    assert result["original_absolute_rtp_as_target"] is False
    assert abs(result["components"][0]["target"]["min"] - 0.2375) < 1e-12
    assert abs(result["components"][0]["target"]["max"] - 0.24) < 1e-12
    assert abs(result["components"][1]["target"]["min"] - 0.7125) < 1e-12
    assert abs(result["components"][1]["target"]["max"] - 0.72) < 1e-12
    contract = {
        "scope": {"target_rtp": {"min": 0.95, "max": 0.96}},
        "component_rtp_target_policy": {
            "method": "original_component_share_mapped_to_authoritative_total_rtp",
            "original_absolute_rtp_as_target": False,
            "authoritative_total_rtp_required": True,
            "share_sum_target": 1.0,
            "legacy_contracts_unchanged": True
        },
        "metrics": [dict(item, kind="hard", status="适用") for item in result["components"]]
    }
    assert validate_component_rtp_targets(contract) == []
    contract["metrics"][0]["target"] = {"min": 0.24, "max": 0.25}
    assert "组件RTP目标未按贡献占比映射: base" in validate_component_rtp_targets(contract)
    legacy = {"schema_version": "1.0", "scope": contract["scope"], "metrics": contract["metrics"]}
    assert validate_component_rtp_targets(legacy) == []
    invalid = dict(source)
    invalid["components"] = [dict(source["components"][0]), dict(source["components"][1])]
    invalid["components"][1]["original_component_share"] = 0.70
    dump(base / "invalid-shares.json", invalid)
    failed = run_result(ROOT / "derive_component_rtp_targets.py", "--input", base / "invalid-shares.json", "--output", base / "invalid-targets.json")
    assert failed.returncode == 2
    return result


def main():
    assert validate_templates(SKILL_ROOT) == []
    stage1_template = (SKILL_ROOT / TEMPLATE_PATHS[1]).read_text(encoding="utf-8")
    missing_example = stage1_template.replace("- 展示实例：", "- 实例已删除：", 1)
    assert any("缺少展示契约标记 展示实例" in error for error in validate_template_text(missing_example, 1))
    root = Path(tempfile.mkdtemp(prefix="slot-alignment-self-test-"))
    normal = score_case(root / "normal")
    waived = score_case(root / "waived", waiver=True)
    failed = score_case(root / "failed", hard_fail=True)
    policy = tolerance_policy_case(root / "policy")
    component_targets = component_rtp_target_case(root / "component-targets")
    assert normal["alignment_status"] == "通过"
    assert waived["alignment_status"] == "豁免后通过"
    assert failed["alignment_status"] == "不通过"
    policy_gates = {item["metric_id"]: item for item in policy["hard_gates"]}
    assert policy_gates["core.rtp.total"]["tolerance_factor"] == 1.0
    assert policy_gates["core.multiplier_distribution.lt200"]["base_tolerance"] == 0.01
    assert policy_gates["core.multiplier_distribution.lt200"]["tolerance_factor"] == 4.0
    assert policy_gates["core.multiplier_distribution.lt200"]["tolerance"] == 0.04
    assert policy_gates["core.multiplier_distribution.lt200"]["status"] == "通过"
    artifacts = root / "artifacts"
    for rel in ("01-input-profile", "02-metric-matching", "03-scoring", "04-alignment"):
        (artifacts / rel).mkdir(parents=True, exist_ok=True)
    dump(artifacts / "01-input-profile/input_manifest.json", {"schema_version": "1.0", "task_id": "self-test", "status": "已完成", "scope": {"game_code": "demo", "mode": "base", "rtp_group": "96", "target_rtp": 0.96}, "paths": {}, "hashes": {}})
    dump(artifacts / "01-input-profile/game_profile.json", {"schema_version": "1.0", "task_id": "self-test", "status": "已完成", "scope": {}, "mechanics": [{"mechanic_id": "feature.free-spin", "name_zh": "免费旋转", "status": "必需", "scope": "base", "evidence": ["demo"]}], "required_node_count": 1, "semantic_gap_count": 0})
    dump(artifacts / "01-input-profile/parameter_authority.json", {"schema_version": "1.0", "task_id": "self-test", "status": "已完成", "parameters": []})
    run(ROOT / "render_input_profile_report.py", "--artifacts", artifacts, "--output", artifacts / "01-input-profile/阶段1-资料确认与玩法画像.md")
    contract = json.loads((root / "normal/contract.json").read_text(encoding="utf-8"))
    contract.update({"status": "已完成", "scope": {"game_code": "demo", "mode": "base", "rtp_group": "96", "target_rtp": 0.96}, "catalogs": {"hashes": {}}, "coverage": {"mechanic_coverage": 1, "metric_measurability": 1}, "coupling_clusters": [], "waivers": [], "component_rtp_target_policy": {"method": "original_component_share_mapped_to_authoritative_total_rtp", "original_absolute_rtp_as_target": False, "authoritative_total_rtp_required": True, "share_sum_target": 1.0, "legacy_contracts_unchanged": True}})
    contract_path = artifacts / "02-metric-matching/metric_contract.json"
    dump(contract_path, contract)
    run(ROOT / "render_metric_matching_report.py", "--contract", contract_path, "--output", artifacts / "02-metric-matching/阶段2-指标匹配报告.md")
    baseline_measurements = root / "baseline-measurements.json"
    dump(baseline_measurements, json.loads((root / "normal/measurements.json").read_text(encoding="utf-8")))
    scorecard_path = artifacts / "03-scoring/scorecard.json"
    report_path = artifacts / "03-scoring/阶段3-评分报告.md"
    gate_path = artifacts / "03-scoring/stage3_gate.json"
    run(ROOT / "score_alignment.py", "--contract", contract_path, "--measurements", baseline_measurements, "--output", scorecard_path)
    missing_report = run_result(ROOT / "validate_stage_transition.py", "--artifacts", artifacts, "--output", gate_path)
    assert missing_report.returncode == 1
    run(ROOT / "render_scoring_report.py", "--contract", contract_path, "--scorecard", scorecard_path, "--output", report_path)
    scoring_text = report_path.read_text(encoding="utf-8")
    bad_header = scoring_text.replace("| 指标 | 作用域 | 目标 | 基线 | 差距 | 方法 |", "| 指标名称 | 作用域 | 目标 | 基线 | 差距 | 方法 |", 1)
    field_errors = validate_report_against_template(bad_header, (SKILL_ROOT / TEMPLATE_PATHS[3]).read_text(encoding="utf-8"), 3)
    assert any("表头名称或顺序" in error for error in field_errors)
    stage1_report = artifacts / "01-input-profile/阶段1-资料确认与玩法画像.md"
    stage1_original = stage1_report.read_text(encoding="utf-8")
    stage1_report.write_text("# 阶段1-资料确认与玩法画像\n\n已完成。\n", encoding="utf-8")
    incomplete_stage1 = run_result(ROOT / "validate_stage_transition.py", "--artifacts", artifacts, "--output", gate_path)
    assert incomplete_stage1.returncode == 1
    stage1_report.write_text(stage1_original, encoding="utf-8")
    stage2_report = artifacts / "02-metric-matching/阶段2-指标匹配报告.md"
    stage2_original = stage2_report.read_text(encoding="utf-8")
    stage2_report.write_text(stage2_original.replace("## 二、上游画像与目录版本绑定", "## 临时错误章节"), encoding="utf-8")
    reordered_stage2 = run_result(ROOT / "validate_stage_transition.py", "--artifacts", artifacts, "--output", gate_path)
    assert reordered_stage2.returncode == 1
    stage2_report.write_text(stage2_original, encoding="utf-8")
    run(ROOT / "validate_stage_transition.py", "--artifacts", artifacts, "--output", gate_path)
    report_path.write_text(report_path.read_text(encoding="utf-8") + "\n篡改", encoding="utf-8")
    tampered_report = run_result(ROOT / "validate_stage_transition.py", "--artifacts", artifacts, "--output", gate_path)
    assert tampered_report.returncode == 1
    run(ROOT / "render_scoring_report.py", "--contract", contract_path, "--scorecard", scorecard_path, "--output", report_path)
    run(ROOT / "validate_stage_transition.py", "--artifacts", artifacts, "--output", gate_path)
    original_contract = json.loads(contract_path.read_text(encoding="utf-8"))
    tampered_contract = json.loads(contract_path.read_text(encoding="utf-8"))
    tampered_contract["group_weights"] = {"experience": 2}
    dump(contract_path, tampered_contract)
    stale_contract = run_result(ROOT / "validate_stage_transition.py", "--artifacts", artifacts, "--output", gate_path)
    assert stale_contract.returncode == 1
    dump(contract_path, original_contract)
    run(ROOT / "validate_stage_transition.py", "--artifacts", artifacts, "--output", gate_path)
    failed_baseline = json.loads(baseline_measurements.read_text(encoding="utf-8"))
    failed_baseline["measurements"][0]["value"] = 0.90
    dump(baseline_measurements, failed_baseline)
    run(ROOT / "score_alignment.py", "--contract", contract_path, "--measurements", baseline_measurements, "--output", scorecard_path)
    assert json.loads(scorecard_path.read_text(encoding="utf-8"))["alignment_status"] == "不通过"
    run(ROOT / "render_scoring_report.py", "--contract", contract_path, "--scorecard", scorecard_path, "--output", report_path)
    run(ROOT / "validate_stage_transition.py", "--artifacts", artifacts, "--output", gate_path)
    dump(baseline_measurements, json.loads((root / "normal/measurements.json").read_text(encoding="utf-8")))
    run(ROOT / "score_alignment.py", "--contract", contract_path, "--measurements", baseline_measurements, "--output", scorecard_path)
    run(ROOT / "render_scoring_report.py", "--contract", contract_path, "--scorecard", scorecard_path, "--output", report_path)
    run(ROOT / "validate_stage_transition.py", "--artifacts", artifacts, "--output", gate_path)
    gate_hash = sha(gate_path)
    dump(artifacts / "04-alignment/alignment_manifest.json", {"schema_version": "1.2", "task_id": "self-test", "status": "已完成", "input_hashes": {}, "stage3_gate": {"path": "03-scoring/stage3_gate.json", "sha256": gate_hash, "stage4_allowed": True}, "budget_policy": {"auto_expand": True, "attainability_ceiling": {"enabled": True, "stop_status": "结构不可达", "prohibit_budget_only_expansion": True}}})
    dump(artifacts / "04-alignment/candidate_archive.json", {"schema_version": "1.2", "task_id": "self-test", "stage3_gate_sha256": gate_hash, "candidates": [], "stop_reason": "基线通过", "budget": {}, "attainability": {"status": "可达", "evidence_path": "", "evidence_sha256": "", "budget_expansion_allowed": True}})
    dump(artifacts / "04-alignment/aligned_parameters.json", {"schema_version": "1.0", "task_id": "self-test", "candidate_id": "baseline", "status": "已完成", "parameters": []})
    dump(artifacts / "04-alignment/formal_result.json", {"schema_version": "1.0", "task_id": "self-test", "candidate_id": "baseline", "plan_id": "formal-1", "status": "通过", "execution_valid": True, "independent_from_calibration": True, "sample": {"paid_entry_count": 1000}, "scorecard": {"alignment_status": "通过"}, "attempt": 1, "audits": {"long_tail": [], "max_win": "已审计"}})
    run(ROOT / "render_alignment_report.py", "--artifacts", artifacts, "--output", artifacts / "04-alignment/阶段4-数值对齐报告.md")
    alignment_report = artifacts / "04-alignment/阶段4-数值对齐报告.md"
    alignment_original = alignment_report.read_text(encoding="utf-8")
    alignment_report.write_text(alignment_original + "\n手工篡改", encoding="utf-8")
    tampered_alignment = run_result(ROOT / "validate_artifacts.py", "--artifacts", artifacts, "--pre-delivery")
    assert tampered_alignment.returncode == 1
    alignment_report.write_text(alignment_original, encoding="utf-8")
    original_measurements = json.loads(baseline_measurements.read_text(encoding="utf-8"))
    tampered_measurements = json.loads(baseline_measurements.read_text(encoding="utf-8"))
    tampered_measurements["measurements"][0]["value"] = 0.91
    dump(baseline_measurements, tampered_measurements)
    stale_measurements = run_result(ROOT / "validate_artifacts.py", "--artifacts", artifacts, "--pre-delivery")
    assert stale_measurements.returncode == 1
    dump(baseline_measurements, original_measurements)
    run(ROOT / "validate_artifacts.py", "--artifacts", artifacts, "--pre-delivery")
    archive_path = artifacts / "04-alignment/candidate_archive.json"
    archive = json.loads(archive_path.read_text(encoding="utf-8"))
    archive["attainability"] = {"status": "结构不可达", "evidence_path": "blocked.json", "evidence_sha256": "a" * 64, "budget_expansion_allowed": True}
    dump(archive_path, archive)
    assert "结构不可达后仍允许预算扩张" in validate_attainability_ceiling(artifacts)
    archive["attainability"]["budget_expansion_allowed"] = False
    dump(archive_path, archive)
    assert validate_attainability_ceiling(artifacts) == []
    archive["attainability"] = {"status": "可达", "evidence_path": "", "evidence_sha256": "", "budget_expansion_allowed": True}
    dump(archive_path, archive)
    run(ROOT / "seal_delivery.py", "--artifacts", artifacts)
    run(ROOT / "validate_artifacts.py", "--artifacts", artifacts)
    delivery_report = artifacts / "05-delivery/阶段5-交付清单.md"
    delivery_original = delivery_report.read_text(encoding="utf-8")
    delivery_report.write_text(delivery_original.replace("## 七、回退与复算方法", "## 错误章节"), encoding="utf-8")
    tampered_delivery = run_result(ROOT / "validate_artifacts.py", "--artifacts", artifacts)
    assert tampered_delivery.returncode == 1
    delivery_report.write_text(delivery_original, encoding="utf-8")
    run(ROOT / "validate_artifacts.py", "--artifacts", artifacts)
    print(json.dumps({"status": "通过", "scenarios": ["五阶段模板展示契约", "逐章Markdown展示实例", "模板缺展示实例阻塞", "必需字段存在性", "表头名称与顺序", "阶段1确定性完整报告", "阶段2确定性完整报告", "阶段1缺章节阻塞", "阶段2章节错误阻塞", "正向", "硬指标失败", "豁免后通过", "未来任务容差系数", "组件RTP占比映射", "阶段3报告缺失阻塞", "阶段3报告篡改阻塞", "阶段3合同hash失效阻塞", "阶段3测量hash失效阻塞", "基线不通过仍允许进入阶段4", "阶段3到阶段4门禁", "阶段4报告篡改阻塞", "预算可达性上限", "阶段5报告篡改阻塞", "交付封存"], "component_target_method": component_targets["method"], "fixture": str(root)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
