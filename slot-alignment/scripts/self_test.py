#!/usr/bin/env python3
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def dump(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(*args):
    return subprocess.run([sys.executable, *map(str, args)], check=True, capture_output=True, text=True)


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


def main():
    root = Path(tempfile.mkdtemp(prefix="slot-alignment-self-test-"))
    normal = score_case(root / "normal")
    waived = score_case(root / "waived", waiver=True)
    failed = score_case(root / "failed", hard_fail=True)
    assert normal["alignment_status"] == "通过"
    assert waived["alignment_status"] == "豁免后通过"
    assert failed["alignment_status"] == "不通过"
    artifacts = root / "artifacts"
    for rel in ("01-input-profile", "02-metric-matching", "03-scoring", "04-alignment"):
        (artifacts / rel).mkdir(parents=True, exist_ok=True)
    dump(artifacts / "01-input-profile/input_manifest.json", {"schema_version": "1.0", "task_id": "self-test", "status": "已完成", "scope": {"game_code": "demo", "mode": "base", "rtp_group": "96", "target_rtp": 0.96}, "paths": {}, "hashes": {}})
    dump(artifacts / "01-input-profile/game_profile.json", {"schema_version": "1.0", "task_id": "self-test", "status": "已完成", "scope": {}, "mechanics": [{"mechanic_id": "feature.free-spin", "name_zh": "免费旋转", "status": "必需", "scope": "base", "evidence": ["demo"]}], "required_node_count": 1, "semantic_gap_count": 0})
    dump(artifacts / "01-input-profile/parameter_authority.json", {"schema_version": "1.0", "task_id": "self-test", "status": "已完成", "parameters": []})
    (artifacts / "01-input-profile/阶段1-资料确认与玩法画像.md").write_text("# 阶段1-资料确认与玩法画像\n\n已完成。\n", encoding="utf-8")
    contract = json.loads((root / "normal/contract.json").read_text(encoding="utf-8"))
    contract.update({"status": "已完成", "scope": {"game_code": "demo", "mode": "base", "rtp_group": "96", "target_rtp": 0.96}, "catalogs": {"hashes": {}}, "coverage": {"mechanic_coverage": 1, "metric_measurability": 1}, "coupling_clusters": [], "waivers": []})
    dump(artifacts / "02-metric-matching/metric_contract.json", contract)
    (artifacts / "02-metric-matching/阶段2-指标匹配报告.md").write_text("# 阶段2-指标匹配报告\n\n已完成。\n", encoding="utf-8")
    dump(artifacts / "03-scoring/scorecard.json", normal)
    (artifacts / "03-scoring/阶段3-评分报告.md").write_text("# 阶段3-评分报告\n\n通过。\n", encoding="utf-8")
    dump(artifacts / "04-alignment/alignment_manifest.json", {"schema_version": "1.0", "task_id": "self-test", "status": "已完成", "input_hashes": {}})
    dump(artifacts / "04-alignment/candidate_archive.json", {"schema_version": "1.0", "task_id": "self-test", "candidates": [], "stop_reason": "基线通过", "budget": {}})
    dump(artifacts / "04-alignment/aligned_parameters.json", {"schema_version": "1.0", "task_id": "self-test", "candidate_id": "baseline", "status": "已完成", "parameters": []})
    dump(artifacts / "04-alignment/formal_result.json", {"schema_version": "1.0", "task_id": "self-test", "candidate_id": "baseline", "plan_id": "formal-1", "status": "通过", "execution_valid": True, "independent_from_calibration": True, "sample": {"paid_entry_count": 1000}, "scorecard": {"alignment_status": "通过"}, "attempt": 1, "audits": {"long_tail": [], "max_win": "已审计"}})
    run(ROOT / "render_alignment_report.py", "--artifacts", artifacts, "--output", artifacts / "04-alignment/阶段4-数值对齐报告.md")
    run(ROOT / "validate_artifacts.py", "--artifacts", artifacts, "--pre-delivery")
    run(ROOT / "seal_delivery.py", "--artifacts", artifacts)
    run(ROOT / "validate_artifacts.py", "--artifacts", artifacts)
    print(json.dumps({"status": "通过", "scenarios": ["正向", "硬指标失败", "豁免后通过", "报告生成", "交付封存"], "fixture": str(root)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
