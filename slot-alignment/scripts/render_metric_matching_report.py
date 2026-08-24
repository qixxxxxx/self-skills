#!/usr/bin/env python3
import argparse
import hashlib
import json
import sys
from pathlib import Path

from report_common import table


def load(path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def render(contract, contract_hash):
    scope = contract.get("scope", {})
    coverage = contract.get("coverage", {})
    metrics = contract.get("metrics", [])
    hard = [x for x in metrics if x.get("kind") == "hard" and x.get("status") != "不适用"]
    scores = [x for x in metrics if x.get("kind") == "score" and x.get("status") != "不适用"]
    audits = [x for x in metrics if x.get("kind") == "audit" and x.get("status") != "不适用"]
    gaps = contract.get("gaps", contract.get("extensions", []))
    waivers = contract.get("waivers", [])
    conflicts = contract.get("owner_conflicts", [])
    clusters = contract.get("coupling_clusters", [])
    policy = contract.get("hard_gate_tolerance_policy", {})
    component_policy = contract.get("component_rtp_target_policy", {})
    component_metrics = [x for x in hard if x.get("metric_id") == "core.rtp.component_contribution"]
    all_measurable = coverage.get("metric_measurability") in {1, 1.0}
    all_covered = coverage.get("mechanic_coverage") in {1, 1.0}
    ready = contract.get("status") == "已完成" and all_measurable and all_covered and not gaps and not conflicts

    def metric_rows(items):
        return [[x.get("metric_id"), x.get("name_zh"), x.get("owner"), x.get("scope"), x.get("target"), x.get("unit"), x.get("data_source"), x.get("sample_qualification"), x.get("control_cluster"), x.get("status")] for x in items]

    lines = [
        "# 阶段2-指标匹配报告", "",
        "> 本报告必须由`render_metric_matching_report.py`根据当前`metric_contract.json`确定性生成；合同或报告变化后必须重新生成并重新通过阶段门禁。", "",
        "## 一、首页结论与阶段准入", "", table(["项目", "结果", "通过标准"], [
            ["任务ID", contract.get("task_id"), "与阶段1一致"], ["游戏 / 模式 / RTP组", f"{scope.get('game_code', '')} / {scope.get('mode', '')} / {scope.get('rtp_group', '')}", "作用域唯一"],
            ["合同状态", contract.get("status"), "已完成"], ["玩法覆盖率", coverage.get("mechanic_coverage"), "100%"], ["指标可测率", coverage.get("metric_measurability"), "100%"],
            ["硬指标 / 评分指标 / 审计指标", f"{len(hard)} / {len(scores)} / {len(audits)}", "全部适用项已实例化"], ["必需缺口", len(gaps), "0"], ["多Owner冲突", len(conflicts), "0"],
            ["豁免", len(waivers), "必须有用户批准和绑定hash"], ["阶段3准入", "允许" if ready else "禁止", "合同完整且无阻塞"],
        ]), "",
        "## 二、上游画像与目录版本绑定", "", table(["对象", "版本/值", "SHA-256", "用途"], [
            ["玩法语义目录", contract.get("catalogs", {}).get("mechanics_version"), contract.get("catalogs", {}).get("hashes", {}).get("mechanics"), "确定mechanic_id语义"],
            ["指标目录", contract.get("catalogs", {}).get("metrics_version"), contract.get("catalogs", {}).get("hashes", {}).get("metrics"), "确定指标包与评价合同"],
            ["阶段1输入绑定", contract.get("input_hashes"), contract.get("input_hashes"), "防止画像变更后沿用旧合同"],
            ["权威总RTP", scope.get("target_rtp"), contract.get("target_rtp_source"), "总RTP硬门禁及组件映射"],
        ]), "",
        "## 三、玩法节点到指标包映射", "", table(["mechanic_id", "作用域", "指标包", "Owner", "实例指标", "匹配依据", "状态"], [[x.get("mechanic_id"), x.get("scope"), x.get("package_id"), x.get("owner"), x.get("metric_ids"), x.get("evidence"), x.get("status")] for x in contract.get("package_matches", contract.get("mechanic_metric_matches", []))]), "",
        "## 四、指标合同总表", "", table(["指标ID", "中文名", "类型", "Owner", "作用域", "目标", "测量方法", "评价方法", "权重", "控制簇", "状态"], [[x.get("metric_id"), x.get("name_zh"), x.get("kind"), x.get("owner"), x.get("scope"), x.get("target"), x.get("measurement", x.get("measurement_method")), (x.get("hard_gate_profile") or x.get("score_profile") or x.get("audit_profile", {})).get("method"), x.get("weight"), x.get("control_cluster"), x.get("status")] for x in metrics]), "",
        "### 4.1 Core硬指标", "", table(["指标ID", "中文名", "Owner", "作用域", "目标", "单位", "数据源", "样本资格", "控制簇", "状态"], metric_rows(hard)), "",
        "### 4.2 100分评分指标", "", table(["指标ID", "中文名", "Owner", "作用域", "目标", "单位", "数据源", "样本资格", "控制簇", "状态"], metric_rows(scores)), "",
        "### 4.3 审计指标", "", table(["指标ID", "中文名", "Owner", "作用域", "目标/审计范围", "单位", "数据源", "样本资格", "控制簇", "状态"], metric_rows(audits)), "",
        "## 五、组件RTP贡献占比映射", "", table(["组件作用域", "原版贡献占比", "权威总RTP", "映射目标", "原版绝对RTP用途", "来源证据", "合计校验"], [[x.get("scope"), x.get("target_derivation", {}).get("original_component_share"), scope.get("target_rtp"), x.get("target"), "仅诊断", x.get("target_derivation", {}).get("source_evidence"), "参与占比及目标合计校验"] for x in component_metrics]), "",
        table(["政策项", "值", "要求"], [["映射方法", component_policy.get("method"), "original_component_share_mapped_to_authoritative_total_rtp"], ["允许原版绝对RTP作目标", component_policy.get("original_absolute_rtp_as_target"), "必须为false"], ["占比合计目标", component_policy.get("share_sum_target"), "1.0"]]), "",
        "## 六、硬指标容差政策", "", table(["指标ID", "基础容差", "系数", "生效容差", "方法", "锁定状态", "政策ID"], [[x.get("metric_id"), x.get("hard_gate_profile", {}).get("base_tolerance"), x.get("hard_gate_profile", {}).get("tolerance_factor"), x.get("hard_gate_profile", {}).get("tolerance"), x.get("hard_gate_profile", {}).get("method"), "锁定" if x.get("metric_id") in policy.get("locked_metrics", []) else "可按政策", x.get("hard_gate_profile", {}).get("tolerance_policy_id")] for x in hard]), "",
        table(["政策", "版本", "源文件", "SHA-256", "默认系数", "已有任务策略"], [[policy.get("policy_id"), policy.get("version"), policy.get("source_path"), policy.get("source_sha256"), policy.get("default_factor"), "不回溯套用"]]), "",
        "## 七、测量、评价与样本资格合同", "", table(["指标ID", "作用域", "数据源", "样本资格", "测量方法", "评价方法", "评分组", "权重", "缺失处理"], [[x.get("metric_id"), x.get("scope"), x.get("data_source"), x.get("sample_qualification"), x.get("measurement", x.get("measurement_method")), x.get("hard_gate_profile") or x.get("score_profile") or x.get("audit_profile"), x.get("score_group"), x.get("weight"), x.get("missing_policy", "阻塞") ] for x in metrics]), "",
        "## 八、控制关系与结构可达性", "", table(["控制簇", "授权参数", "受影响指标", "方向证据", "敏感性证据", "独立性/耦合", "可达性状态", "预算扩张"], [[x.get("cluster_id"), x.get("parameters"), x.get("metrics"), x.get("direction_evidence"), x.get("sensitivity_evidence"), x.get("control_type"), x.get("attainability_status", x.get("status")), x.get("budget_expansion_allowed")] for x in clusters]), "",
        "## 九、指标缺口与扩展提案", "", table(["缺口ID", "玩法节点", "缺失能力", "影响指标", "提案路径", "批准状态", "停止原因"], [[x.get("gap_id"), x.get("mechanic_id"), x.get("missing_capability"), x.get("affected_metrics"), x.get("proposal_path"), x.get("approval_status"), x.get("reason")] for x in gaps]), "",
        "## 十、豁免与多Owner审查", "", table(["指标/节点", "类型", "原因", "Owner", "批准状态", "批准人/证据", "绑定Hash", "审计保留"], [[x.get("metric_id", x.get("mechanic_id")), "豁免", x.get("reason"), x.get("owner"), x.get("status", x.get("approval", {}).get("status")), x.get("approval"), x.get("bound_hashes"), x.get("audit_retained", True)] for x in waivers] + [[x.get("metric_id", x.get("mechanic_id")), "Owner冲突", x.get("reason"), x.get("owners"), x.get("status"), x.get("resolution"), x.get("bound_hashes"), True] for x in conflicts]), "",
        "## 十一、合同密封、Hash与复算", "", table(["对象", "Schema/版本", "SHA-256", "密封时间/状态"], [
            ["metric_contract.json", contract.get("schema_version"), contract_hash, contract.get("sealed_at")], ["容差政策", policy.get("version"), policy.get("source_sha256"), policy.get("policy_id")],
            ["玩法目录", contract.get("catalogs", {}).get("mechanics_version"), contract.get("catalogs", {}).get("hashes", {}).get("mechanics"), "已绑定"], ["指标目录", contract.get("catalogs", {}).get("metrics_version"), contract.get("catalogs", {}).get("hashes", {}).get("metrics"), "已绑定"],
        ]), "", "```bash", "<python_bin> <skill_root>/scripts/render_metric_matching_report.py --contract <artifacts/02-metric-matching/metric_contract.json> --output <artifacts/02-metric-matching/阶段2-指标匹配报告.md>", "```", "",
        "## 十二、阶段3准入结论", "", table(["条件", "当前值", "通过标准", "结论"], [
            ["玩法覆盖率", coverage.get("mechanic_coverage"), "100%", "通过" if all_covered else "阻塞"], ["指标可测率", coverage.get("metric_measurability"), "100%", "通过" if all_measurable else "阻塞"],
            ["必需缺口", len(gaps), "0或用户批准扩展后归零", "通过" if not gaps else "阻塞"], ["Owner冲突", len(conflicts), "0", "通过" if not conflicts else "阻塞"], ["最终准入", "允许" if ready else "禁止", "全部条件通过", "不得以候选结果倒推修改合同"],
        ]), ""
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="确定性生成阶段2中文报告")
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        contract = load(args.contract)
        text = render(contract, sha(args.contract))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
        print(json.dumps({"status": "通过", "output": str(args.output)}, ensure_ascii=False))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "失败", "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
