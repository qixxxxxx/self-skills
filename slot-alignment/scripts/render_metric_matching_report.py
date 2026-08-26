#!/usr/bin/env python3
import argparse
import hashlib
import json
import sys
from pathlib import Path

from report_common import apply_metric_display_metadata, detail_rows, labeled_detail_rows, metric_groups, metric_meta_lines, metric_sample_capability_lines, metric_stage2_table, sample_capability_policy_table, table


def load(path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ratio_with_machine_value(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{value * 100:g}%（机器值{value:g}）"
    return value


def percentage_points_with_machine_value(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{value * 100:g}个百分点（机器值{value:g}）"
    return value


def jackpot_policy_detail_table(policy):
    classifications = policy.get("classifications")
    classification_rule = {
        "material_when_hit_rate_gte_hit_rate_threshold_or_original_rtp_contribution_gte_component_rtp_tolerance": "命中率达到阈值，或原版组件RTP贡献达到阈值，即为物质性层级",
    }.get(policy.get("classification_rule"), policy.get("classification_rule"))
    return table(["Jackpot物质性政策项", "当前值", "中文语义"], [
        ["policy_id", policy.get("policy_id"), "政策唯一身份"],
        ["version", policy.get("version"), "候选结果出现前固定"],
        ["命中率分辨率/物质性阈值", ratio_with_machine_value(policy.get("hit_rate_threshold")), "沿用jackpot.material_hit_rate的95分最小正距离锚点，表示当前评价体系能稳定分辨的最小命中率差异"],
        ["组件RTP物质性阈值", percentage_points_with_machine_value(policy.get("component_rtp_tolerance_threshold")), "来自全部活动core.rtp.component_contribution实例生效容差的最小值"],
        ["组件RTP生效容差来源", "core.rtp.component_contribution.hard_gate_profile.tolerance最小值", "沿用当前合同已经生效的硬指标容差，不新增经验阈值"],
        ["分类规则", classification_rule, "两个条件满足任意一个即可；不是同时满足"],
        ["分类冻结规则", "候选前按原版层级暴露冻结；候选不得重新分类", "分类只由已密封原版命中率和组件RTP贡献决定"],
        ["分类SHA-256", policy.get("classifications_sha256"), "确认逐机会集、逐层级分类结果未变化"],
        ["冻结机会集数", len(classifications) if isinstance(classifications, list) else "无法判定", "完整分类结果保存在机器合同，不在中文报告展开JSON"],
        ["source_path", policy.get("source_path"), "政策源文件"],
        ["source_sha256", policy.get("source_sha256"), "确认政策源文件未变化"],
    ])


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
    jackpot_policy = contract.get("jackpot_materiality_policy", {})
    score_group_policy = contract.get("score_group_weight_policy", {})
    ordered_distance_policy = contract.get("ordered_distance_policy", {})
    sample_capability_policy = contract.get("sample_capability_policy", {})
    component_policy = contract.get("component_rtp_target_policy", {})
    component_metrics = [x for x in hard if x.get("metric_id") == "core.rtp.component_contribution"]
    all_measurable = coverage.get("metric_measurability") in {1, 1.0}
    all_covered = coverage.get("mechanic_coverage") in {1, 1.0}
    ready = contract.get("status") == "已完成" and all_measurable and all_covered and not gaps and not conflicts

    package_summary_rows, package_metric_rows, package_evidence_rows = [], [], []
    for item in contract.get("package_matches", contract.get("mechanic_metric_matches", [])):
        mechanic_id = item.get("mechanic_id")
        metric_ids = item.get("metric_ids", [])
        package_summary_rows.append([mechanic_id, item.get("scope"), item.get("package_id"), item.get("owner"), len(metric_ids) if isinstance(metric_ids, list) else 1, item.get("status")])
        package_metric_rows.extend([[mechanic_id, field, value] for field, value in detail_rows(metric_ids, "指标")])
        package_evidence_rows.extend([[mechanic_id, field, value] for field, value in detail_rows(item.get("evidence"), "匹配依据")])
    grouped_metrics = metric_groups(metrics)
    metric_overview_rows = [[number, item.get("name_zh", item.get("metric_id")), title, item.get("scope"), item.get("status")] for _, title, items in grouped_metrics for number, item in items]

    def metric_sections(kind):
        items = next((items for group_kind, _, items in grouped_metrics if group_kind == kind), [])
        if not items:
            return "无适用指标。"
        blocks = []
        for number, item in items:
            blocks.extend([
                f"#### {number} {item.get('name_zh', item.get('metric_id'))}", "",
                *metric_meta_lines(number, item), "",
                metric_stage2_table(item), "",
                *metric_sample_capability_lines(item, 2), "",
                f"合同结论：{item.get('status', '必需')}；缺失处理：{item.get('missing_policy', '阻塞')}。", "",
            ])
        return "\n".join(blocks).rstrip()
    cluster_summary_rows, cluster_parameter_rows, cluster_metric_rows, cluster_evidence_rows = [], [], [], []
    for item in clusters:
        cluster_id = item.get("cluster_id")
        cluster_summary_rows.append([cluster_id, item.get("control_type"), item.get("attainability_status", item.get("status")), item.get("budget_expansion_allowed")])
        cluster_parameter_rows.extend([[cluster_id, field, value] for field, value in detail_rows(item.get("parameters"), "参数")])
        cluster_metric_rows.extend([[cluster_id, field, value] for field, value in detail_rows(item.get("metrics"), "指标")])
        cluster_evidence_rows.extend(labeled_detail_rows(cluster_id, {"方向证据": item.get("direction_evidence"), "敏感性证据": item.get("sensitivity_evidence")}))
    gap_summary_rows, gap_metric_rows, gap_path_rows = [], [], []
    for item in gaps:
        gap_id = item.get("gap_id")
        gap_summary_rows.append([gap_id, item.get("mechanic_id"), item.get("missing_capability"), item.get("approval_status"), item.get("reason")])
        gap_metric_rows.extend([[gap_id, field, value] for field, value in detail_rows(item.get("affected_metrics"), "影响指标")])
        gap_path_rows.append([gap_id, item.get("proposal_path")])
    review_summary_rows, approval_rows, bound_hash_rows = [], [], []
    for item, review_type in [(x, "豁免") for x in waivers] + [(x, "Owner冲突") for x in conflicts]:
        object_id = item.get("metric_id", item.get("mechanic_id"))
        approval = item.get("approval", item.get("resolution"))
        review_summary_rows.append([object_id, review_type, item.get("reason"), item.get("owner", item.get("owners")), item.get("status", approval.get("status") if isinstance(approval, dict) else approval), item.get("audit_retained", True)])
        approval_rows.extend([[object_id, field, value] for field, value in detail_rows(approval, "批准/处理")])
        bound_hash_rows.extend([[object_id, field, value] for field, value in detail_rows(item.get("bound_hashes"), "绑定Hash")])
    input_hash_rows = [[name, value] for name, value in sorted(contract.get("input_hashes", {}).items())]
    component_evidence_rows = [[x.get("scope"), x.get("target_derivation", {}).get("source_evidence")] for x in component_metrics]
    policy_identity_rows = [
        ["硬指标容差政策", policy.get("policy_id"), policy.get("version"), "基础容差乘固定系数得到生效容差；锁定指标不得放宽"],
        ["Jackpot物质性政策", jackpot_policy.get("policy_id"), jackpot_policy.get("version"), "沿用既有命中率分辨率和组件RTP生效容差冻结物质性层级"],
        ["有序距离政策", ordered_distance_policy.get("policy_id"), ordered_distance_policy.get("version"), "自然次数按线性距离；回报、奖值和倍率按固定长尾尺度"],
        ["评分组权重政策", score_group_policy.get("policy_id"), score_group_policy.get("version"), "按活动体验语义组的基础预算归一化"],
        ["样本能力政策", sample_capability_policy.get("policy_id"), sample_capability_policy.get("version"), "原版与FORMAL逐指标、逐条件组达到统一置信要求"],
    ]
    policy_source_rows = [
        ["硬指标容差政策", policy.get("source_path"), policy.get("source_sha256")],
        ["Jackpot物质性政策", jackpot_policy.get("source_path"), jackpot_policy.get("source_sha256")],
        ["有序距离政策", ordered_distance_policy.get("source_path"), ordered_distance_policy.get("source_sha256")],
        ["评分组权重政策", score_group_policy.get("source_path"), score_group_policy.get("source_sha256")],
        ["样本能力政策", sample_capability_policy.get("source_path"), sample_capability_policy.get("source_sha256")],
    ]
    lines = [
        "# 阶段2-指标匹配报告", "",
        "> 本报告必须由`render_metric_matching_report.py`根据当前`metric_contract.json`确定性生成；合同或报告变化后必须重新生成并重新通过阶段门禁。", "",
        "## 一、首页结论与阶段准入", "", table(["项目", "结果", "通过标准"], [
            ["任务ID", contract.get("task_id"), "与阶段1一致"], ["游戏 / 模式 / RTP组", f"{scope.get('game_code', '')} / {scope.get('mode', '')} / {scope.get('rtp_group', '')}", "作用域唯一"],
            ["合同状态", contract.get("status"), "已完成"], ["玩法覆盖率", coverage.get("mechanic_coverage"), "100%"], ["指标可测率", coverage.get("metric_measurability"), "100%"],
            ["硬指标 / 评分指标 / 审计指标", f"{len(hard)} / {len(scores)} / {len(audits)}", "全部适用项已实例化"], ["必需缺口", len(gaps), "0"], ["多Owner冲突", len(conflicts), "0"],
            ["豁免", len(waivers), "必须有用户批准和绑定hash"], ["阶段3准入", "允许" if ready else "禁止", "合同完整且无阻塞"],
        ]), "",
        "## 二、上游画像与目录版本绑定", "", table(["对象", "版本/值", "用途"], [
            ["玩法语义目录", contract.get("catalogs", {}).get("mechanics_version"), "确定mechanic_id语义"],
            ["指标目录", contract.get("catalogs", {}).get("metrics_version"), "确定指标包与评价合同"],
            ["阶段1输入绑定", f"{len(input_hash_rows)}项", "防止画像变更后沿用旧合同"],
            ["权威总RTP", "见目标明细", "总RTP硬门禁及组件映射"],
        ]), "", table(["政策", "policy_id", "版本", "核心语义"], policy_identity_rows), "", table(["目标项", "值"], detail_rows(scope.get("target_rtp"), "权威总RTP")), "", table(["绑定对象", "SHA-256"], input_hash_rows + [["玩法语义目录", contract.get("catalogs", {}).get("hashes", {}).get("mechanics")], ["指标目录", contract.get("catalogs", {}).get("hashes", {}).get("metrics")]]), "", table(["来源对象", "路径/标识"], [["权威总RTP", contract.get("target_rtp_source")]]), "", table(["政策", "source_path", "source_sha256"], policy_source_rows), "", jackpot_policy_detail_table(jackpot_policy), "", sample_capability_policy_table(sample_capability_policy), "",
        "## 三、玩法节点到指标包映射", "", table(["mechanic_id", "作用域", "指标包", "Owner", "指标数", "状态"], package_summary_rows), "", table(["mechanic_id", "指标项", "指标ID"], package_metric_rows), "", table(["mechanic_id", "依据项", "匹配依据"], package_evidence_rows), "",
        "## 四、指标清单与详细目标", "", table(["编号", "指标", "分类", "作用域", "状态"], metric_overview_rows), "", "指标详情按固定分类展示；三个阶段沿用相同编号、顺序和标题。", "",
        "### 4.1 硬指标", "", metric_sections("hard"), "",
        "### 4.2 评分指标", "", metric_sections("score"), "",
        "### 4.3 审计指标", "", metric_sections("audit"), "",
        "## 五、组件RTP贡献占比映射", "", table(["组件作用域", "原版贡献占比", "原版绝对RTP用途", "合计校验"], [[x.get("scope"), x.get("target_derivation", {}).get("original_component_share"), "仅诊断", "参与占比及目标合计校验"] for x in component_metrics]), "", table(["组件作用域", "来源证据"], component_evidence_rows), "",
        table(["政策项", "值", "要求"], [["映射方法", component_policy.get("method"), "original_component_share_mapped_to_authoritative_total_rtp"], ["允许原版绝对RTP作目标", component_policy.get("original_absolute_rtp_as_target"), "必须为false"], ["占比合计目标", component_policy.get("share_sum_target"), "1.0"]]), "",
        "## 六、控制关系与结构可达性", "", table(["控制簇", "独立性/耦合", "可达性状态", "预算扩张"], cluster_summary_rows), "", table(["控制簇", "参数项", "授权参数"], cluster_parameter_rows), "", table(["控制簇", "指标项", "受影响指标"], cluster_metric_rows), "", table(["控制簇", "证据项", "证据"], cluster_evidence_rows), "",
        "## 七、指标缺口与扩展提案", "", table(["缺口ID", "玩法节点", "缺失能力", "批准状态", "停止原因"], gap_summary_rows), "", table(["缺口ID", "指标项", "影响指标"], gap_metric_rows), "", table(["缺口ID", "提案路径"], gap_path_rows), "",
        "## 八、豁免与多Owner审查", "", table(["指标/节点", "类型", "原因", "Owner", "批准状态", "审计保留"], review_summary_rows), "", table(["指标/节点", "批准/处理项", "内容"], approval_rows), "", table(["指标/节点", "绑定对象", "SHA-256"], bound_hash_rows), "",
        "## 九、合同密封、Hash与复算", "", table(["对象", "Schema/版本", "SHA-256", "密封时间/状态"], [
            ["metric_contract.json", contract.get("schema_version"), contract_hash, contract.get("sealed_at")], ["硬指标容差政策", policy.get("version"), policy.get("source_sha256"), policy.get("policy_id")], ["Jackpot物质性政策", jackpot_policy.get("version"), jackpot_policy.get("source_sha256"), jackpot_policy.get("policy_id")], ["有序距离政策", ordered_distance_policy.get("version"), ordered_distance_policy.get("source_sha256"), ordered_distance_policy.get("policy_id")], ["评分组权重政策", score_group_policy.get("version"), score_group_policy.get("source_sha256"), score_group_policy.get("policy_id")], ["样本能力政策", sample_capability_policy.get("version"), sample_capability_policy.get("source_sha256"), sample_capability_policy.get("policy_id")],
            ["玩法目录", contract.get("catalogs", {}).get("mechanics_version"), contract.get("catalogs", {}).get("hashes", {}).get("mechanics"), "已绑定"], ["指标目录", contract.get("catalogs", {}).get("metrics_version"), contract.get("catalogs", {}).get("hashes", {}).get("metrics"), "已绑定"],
        ]), "", table(["Jackpot封存项", "值"], [["命中率物质性阈值", ratio_with_machine_value(jackpot_policy.get("hit_rate_threshold"))], ["组件RTP物质性阈值", percentage_points_with_machine_value(jackpot_policy.get("component_rtp_tolerance_threshold"))], ["分类冻结规则", "候选前按原版暴露冻结；候选不得重新分类"], ["分类SHA-256", jackpot_policy.get("classifications_sha256")], ["source_path", jackpot_policy.get("source_path")], ["source_sha256", jackpot_policy.get("source_sha256")]]), "", "```bash", "<python_bin> <skill_root>/scripts/render_metric_matching_report.py --contract <artifacts/02-metric-matching/metric_contract.json> --output <report_dir>/阶段2-指标匹配报告.md", "```", "",
        "## 十、阶段3准入结论", "", table(["条件", "当前值", "通过标准", "结论"], [
            ["玩法覆盖率", coverage.get("mechanic_coverage"), "100%", "通过" if all_covered else "阻塞"], ["指标可测率", coverage.get("metric_measurability"), "100%", "通过" if all_measurable else "阻塞"],
            ["必需缺口", len(gaps), "0或用户批准扩展后归零", "通过" if not gaps else "阻塞"], ["Owner冲突", len(conflicts), "0", "通过" if not conflicts else "阻塞"], ["最终准入", "允许" if ready else "禁止", "全部条件通过", "不得以候选结果倒推修改合同"],
        ]), ""
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="确定性生成阶段2中文报告")
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--display-metadata", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        contract = apply_metric_display_metadata(load(args.contract), load(args.display_metadata) if args.display_metadata else None)
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
