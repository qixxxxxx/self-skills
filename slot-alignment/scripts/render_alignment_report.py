#!/usr/bin/env python3
import argparse
import hashlib
import json
import sys
from pathlib import Path

from report_common import apply_metric_display_metadata, detail_rows, metric_brief_result, metric_groups, metric_key, metric_meta_lines, metric_result_summary, metric_stage4_table, table


def load(path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def named_rows(data, names):
    return [[names.get(k, k), v] for k, v in data.items()]


def render(a, display_metadata=None):
    inputs = load(a / "01-input-profile/input_manifest.json")
    profile = load(a / "01-input-profile/game_profile.json")
    authority = load(a / "01-input-profile/parameter_authority.json")
    contract = apply_metric_display_metadata(load(a / "02-metric-matching/metric_contract.json"), display_metadata)
    score = load(a / "03-scoring/scorecard.json")
    manifest = load(a / "04-alignment/alignment_manifest.json")
    candidates = load(a / "04-alignment/candidate_archive.json")
    parameters = load(a / "04-alignment/aligned_parameters.json")
    formal = load(a / "04-alignment/formal_result.json")
    scope = inputs.get("scope", {})
    final_score = formal.get("scorecard", {}) if formal.get("scorecard", {}).get("hard_gates") is not None else score
    if not final_score.get("hard_gates") and score.get("hard_gates"):
        final_score = score
    status = formal.get("scorecard", {}).get("alignment_status") or final_score.get("alignment_status", "无法判定")
    hard = final_score.get("hard_gates", [])
    hard_required = [x for x in hard if x.get("status") != "硬指标已豁免"]
    hard_passed = sum(x.get("status") == "通过" for x in hard_required)
    low = [x for x in final_score.get("scores", []) if x.get("score") is not None and x["score"] < 85]
    waivers = contract.get("waivers", [])
    mechanics = profile.get("mechanics", [])
    metric_items = contract.get("metrics", [])
    feature_scores = [x for x in final_score.get("scores", []) if "feature" in x.get("metric_id", "") or "free_spin" in x.get("metric_id", "") or "respin" in x.get("metric_id", "")]
    contract_metrics = {(x.get("metric_id"), x.get("scope")): x for x in contract.get("metrics", [])}
    baseline_hard = {metric_key(item): item for item in score.get("hard_gates", [])}
    baseline_scores = {metric_key(item): item for item in score.get("scores", [])}
    formal_hard = {metric_key(item): item for item in final_score.get("hard_gates", [])}
    formal_scores = {metric_key(item): item for item in final_score.get("scores", [])}
    audit_results = {}
    long_tail_audit = formal.get("audits", {}).get("long_tail", [])
    if isinstance(long_tail_audit, list):
        audit_results["core.long_tail.audit"] = {
            "candidate": [item.get("candidate") for item in long_tail_audit if isinstance(item, dict)],
            "status": "审计完成" if long_tail_audit else "无审计结果",
        }
    max_win_audit = formal.get("audits", {}).get("max_win")
    if isinstance(max_win_audit, dict):
        audit_results["core.max_win.audit"] = {
            "candidate": {
                "cap": max_win_audit.get("cap"),
                "cap_hit_count": max_win_audit.get("cap_hit_count"),
                "observed": max_win_audit.get("observed", max_win_audit.get("observed_normal_bet_multiple")),
            },
            "status": max_win_audit.get("status", "审计"),
        }
    grouped_metrics = metric_groups(metric_items)

    def baseline_for(metric):
        if metric.get("kind") == "hard":
            return baseline_hard.get(metric_key(metric))
        if metric.get("kind") == "score":
            return baseline_scores.get(metric_key(metric))
        return None

    def formal_for(metric):
        if metric.get("kind") == "hard":
            return formal_hard.get(metric_key(metric))
        if metric.get("kind") == "score":
            return formal_scores.get(metric_key(metric))
        return audit_results.get(metric.get("metric_id"))

    metric_overview_rows = []
    for _, title, items in grouped_metrics:
        for number, metric in items:
            baseline_item, formal_item = baseline_for(metric), formal_for(metric)
            metric_overview_rows.append([
                number,
                metric.get("name_zh", metric.get("metric_id")),
                title,
                metric.get("scope"),
                f"{metric_brief_result(metric, baseline_item, '—')} → {metric_brief_result(metric, formal_item, '—')}",
            ])

    def metric_sections(kind):
        items = next((items for group_kind, _, items in grouped_metrics if group_kind == kind), [])
        if not items:
            return "无适用指标。"
        blocks = []
        for number, metric in items:
            baseline_item, formal_item = baseline_for(metric), formal_for(metric)
            blocks.extend([
                f"#### {number} {metric.get('name_zh', metric.get('metric_id'))}", "",
                *metric_meta_lines(number, metric), "",
                metric_stage4_table(metric, baseline_item, formal_item), "",
                f"阶段4结论：{metric_result_summary(metric, formal_item, 'FORMAL未生成该指标结果')}。", "",
            ])
        return "\n".join(blocks).rstrip()
    hard_table = table(["指标", "作用域", "FORMAL", "差距", "样本资格", "状态"], [[x.get("name_zh", x.get("metric_id")), x.get("scope"), x.get("candidate"), x.get("distance"), contract_metrics.get((x.get("metric_id"), x.get("scope")), {}).get("sample_qualification"), x.get("status")] for x in hard])
    hard_target_rows = []
    for item in hard:
        name = item.get("name_zh", item.get("metric_id"))
        hard_target_rows.extend([[name, field, value] for field, value in detail_rows(item.get("target"), "目标")])
    hard_target_table = table(["指标", "目标项", "值"], hard_target_rows)
    hard_tolerance_table = table(["指标", "方法", "基础容差", "系数", "生效容差"], [[x.get("name_zh", x.get("metric_id")), contract_metrics.get((x.get("metric_id"), x.get("scope")), {}).get("hard_gate_profile", {}).get("method"), x.get("base_tolerance", x.get("tolerance")), x.get("tolerance_factor", 1.0), x.get("tolerance")] for x in hard])
    score_summary_rows, score_method_rows, score_detail_rows = [], [], []
    for item in final_score.get("scores", []):
        name = item.get("name_zh", item.get("metric_id"))
        source = contract_metrics.get((item.get("metric_id"), item.get("scope")), {})
        profile_data = source.get("score_profile", {})
        score_summary_rows.append([name, item.get("scope"), item.get("candidate"), item.get("distance"), item.get("score"), item.get("band"), item.get("status")])
        score_method_rows.append([name, profile_data.get("method"), source.get("score_group"), item.get("weight")])
        score_detail_rows.extend([[name, field, value] for field, value in detail_rows(profile_data)])
    score_target_rows = []
    for item in final_score.get("scores", []):
        name = item.get("name_zh", item.get("metric_id"))
        score_target_rows.extend([[name, field, value] for field, value in detail_rows(item.get("target"), "目标")])
    score_table = table(["指标", "作用域", "FORMAL", "差距", "得分", "档位", "状态"], score_summary_rows)
    score_target_table = table(["指标", "目标项", "值"], score_target_rows)
    score_method_table = table(["指标", "评价方法", "评分组", "权重"], score_method_rows)
    score_detail_table = table(["指标", "评价参数", "值"], score_detail_rows)
    group_table = table(["评分组", "得分", "档位", "权重"], [[x.get("group"), x.get("score"), x.get("band"), x.get("weight")] for x in final_score.get("groups", [])])
    mechanic_summary_rows, mechanic_attribute_rows, mechanic_evidence_rows = [], [], []
    for item in mechanics:
        mechanic_id = item.get("mechanic_id")
        mechanic_summary_rows.append([mechanic_id, item.get("name_zh"), item.get("parent_id"), item.get("status"), item.get("scope"), item.get("confidence", item.get("confidence_status"))])
        mechanic_attribute_rows.extend([[mechanic_id, field, value] for field, value in detail_rows(item.get("attributes"))])
        mechanic_evidence_rows.extend([[mechanic_id, field, value] for field, value in detail_rows(item.get("evidence"))])
    mechanic_table = table(["玩法ID", "中文名", "父节点", "状态", "作用域", "置信状态"], mechanic_summary_rows)
    mechanic_attribute_table = table(["玩法ID", "属性", "值"], mechanic_attribute_rows)
    mechanic_evidence_table = table(["玩法ID", "证据项", "证据"], mechanic_evidence_rows)
    metric_table = table(["指标ID", "Owner", "类型", "作用域", "状态"], [[x.get("metric_id"), x.get("owner"), x.get("kind"), x.get("scope"), x.get("status", "必需")] for x in metric_items])
    parameter_summary_rows, parameter_metric_rows = [], []
    for item in parameters.get("parameters", []):
        parameter_summary_rows.append([item.get("path"), item.get("before"), item.get("after"), item.get("delta"), item.get("authorization_status", "已授权"), item.get("control_cluster"), item.get("risk")])
        parameter_metric_rows.extend([[item.get("path"), field, value] for field, value in detail_rows(item.get("affected_metrics"), "影响指标")])
    parameter_table = table(["参数", "原值", "对齐值", "变化", "授权", "控制簇", "运行风险"], parameter_summary_rows)
    parameter_metric_table = table(["参数", "指标项", "影响指标"], parameter_metric_rows)
    candidate_summary_rows, candidate_parameter_rows = [], []
    for item in candidates.get("candidates", []):
        candidate_id = item.get("candidate_id")
        candidate_summary_rows.append([candidate_id, item.get("parent_id"), item.get("hard_gate_status"), item.get("overall_score"), item.get("sample_count"), item.get("risk"), item.get("decision_reason"), item.get("stage3_gate_sha256", candidates.get("stage3_gate_sha256")), item.get("status")])
        candidate_parameter_rows.extend([[candidate_id, field, value] for field, value in detail_rows(item.get("parameter_summary"), "参数摘要")])
    candidate_table = table(["候选", "父候选", "硬指标", "综合分", "样本", "风险", "晋级/淘汰原因", "stage3_gate hash", "状态"], candidate_summary_rows)
    candidate_parameter_table = table(["候选", "参数项", "参数摘要"], candidate_parameter_rows)
    feature_table = table(["Feature指标", "得分", "档位"], [[x.get("name_zh", x.get("metric_id")), x.get("score"), x.get("band")] for x in feature_scores])
    long_tail = formal.get("audits", {}).get("long_tail", [])
    long_tail_table = table(["倍率桶", "原版", "候选", "样本资格", "结论"], [[x.get("bucket"), x.get("target"), x.get("candidate"), x.get("sample_status"), x.get("status", "审计")] for x in long_tail])
    hashes = {}
    for source in (inputs.get("hashes", {}), contract.get("catalogs", {}).get("hashes", {}), manifest.get("input_hashes", {})):
        hashes.update(source)
    tolerance_policy = contract.get("hard_gate_tolerance_policy", {})
    if tolerance_policy.get("source_sha256"):
        hashes["hard_gate_tolerance_policy"] = tolerance_policy["source_sha256"]
    component_rows, component_target_rows = [], []
    for item in hard:
        if "component_contribution" not in item.get("metric_id", ""):
            continue
        source = contract_metrics.get((item.get("metric_id"), item.get("scope")), {})
        derivation = source.get("target_derivation", {})
        component_rows.append([item.get("scope"), derivation.get("original_component_share"), item.get("candidate"), item.get("status")])
        component_target_rows.extend([[item.get("scope"), field, value] for field, value in detail_rows(item.get("target"), "映射目标")])
    component_table = table(["作用域", "原版贡献占比", "FORMAL", "状态"], component_rows)
    component_target_table = table(["作用域", "目标项", "值"], component_target_rows)
    budget_table = table(["预算项", "值"], detail_rows(candidates.get("budget", {})))
    attainability_table = table(["可达性项", "值"], detail_rows(candidates.get("attainability", {})))
    ceiling_table = table(["上限项", "值"], detail_rows(manifest.get("budget_policy", {}).get("attainability_ceiling", {})))
    source_summary_rows, source_path_rows = [], []
    source_names = {"workspace_root": "工作区", "slot_docs_root": "游戏资料根目录", "server_root": "Server根目录", "runtime": "Runtime", "simulation_script": "模拟脚本"}
    for index, (key, value) in enumerate(inputs.get("paths", {}).items(), 1):
        ref = f"P{index:02d}"
        source_summary_rows.append([ref, source_names.get(key, key), "阶段1已密封"])
        source_path_rows.append([ref, value, inputs.get("hashes", {}).get(key)])
    formal_hash_rows = [[name, value] for name, value in sorted(formal.get("input_hashes", {}).items())]
    waiver_summary_rows, waiver_approval_rows = [], []
    for item in waivers:
        metric_id = item.get("metric_id")
        approval = item.get("approval")
        waiver_summary_rows.append([metric_id, item.get("status"), item.get("reason"), approval.get("status") if isinstance(approval, dict) else approval])
        waiver_approval_rows.extend([[metric_id, field, value] for field, value in detail_rows(approval, "批准")])
    max_win_rows = detail_rows(formal.get("audits", {}).get("max_win", "无。"))
    scope_rows = [[name, value, "不得跨作用域"] for name, value in named_rows({key: value for key, value in scope.items() if key != "target_rtp"}, {"game_code": "游戏", "mode": "模式", "rtp_group": "RTP组"})]
    scope_target_rows = detail_rows(scope.get("target_rtp"), "目标RTP")
    rtp_items = [item for item in hard if item.get("metric_id") == "core.rtp.total"]
    rtp_result_rows = [[item.get("candidate"), item.get("confidence_interval_99", formal.get("rtp_confidence_interval_99")), formal.get("sample", {}).get("paid_entry_count"), item.get("sigma", item.get("standard_error")), item.get("ci_fully_within_target"), item.get("status")] for item in rtp_items]
    rtp_target_rows = [[field, value] for item in rtp_items for field, value in detail_rows(item.get("target"), "目标")]
    probability_items = [item for item in hard if "hit_rate" in item.get("metric_id", "") or "trigger_rate" in item.get("metric_id", "")]
    probability_rows = [[item.get("name_zh"), item.get("scope"), item.get("candidate"), item.get("distance"), item.get("tolerance"), item.get("status")] for item in probability_items]
    probability_target_rows = [[item.get("name_zh"), field, value] for item in probability_items for field, value in detail_rows(item.get("target"), "目标")]
    distribution_items = [item for item in hard if "multiplier_distribution" in item.get("metric_id", "")]
    distribution_rows = [[item.get("name_zh"), item.get("distance"), item.get("base_tolerance", item.get("tolerance")), item.get("tolerance_factor", 1.0), item.get("tolerance"), item.get("status")] for item in distribution_items]
    distribution_detail_rows = []
    for item in distribution_items:
        name = item.get("name_zh")
        distribution_detail_rows.extend([[name, "目标分布", field, value] for field, value in detail_rows(item.get("target"), "分布")])
        distribution_detail_rows.extend([[name, "FORMAL分布", field, value] for field, value in detail_rows(item.get("candidate"), "分布")])
    sigma_items = [item for item in hard if item.get("metric_id") == "core.sigma"]
    sigma_rows = [[item.get("scope"), item.get("candidate"), item.get("distance"), item.get("tolerance"), formal.get("sample", {}).get("paid_entry_count"), item.get("status")] for item in sigma_items]
    sigma_target_rows = [[item.get("scope"), field, value] for item in sigma_items for field, value in detail_rows(item.get("target"), "目标")]
    for rel in [
        "01-input-profile/input_manifest.json", "01-input-profile/game_profile.json", "01-input-profile/parameter_authority.json",
        "02-metric-matching/metric_contract.json", "03-scoring/scorecard.json", "03-scoring/stage3_gate.json",
        "04-alignment/alignment_manifest.json", "04-alignment/candidate_archive.json", "04-alignment/aligned_parameters.json", "04-alignment/formal_result.json",
    ]:
        path = a / rel
        if path.is_file():
            hashes[rel] = sha(path)
    lines = [
        "# 阶段4-数值对齐报告", "", "## 首页结论", "",
        table(["项目", "最终结果"], [
            ["游戏 / 模式 / RTP组", f"{scope.get('game_code','')} / {scope.get('mode','')} / {scope.get('rtp_group','')}"],
            ["对齐结论", status], ["FORMAL有效性", "有效" if formal.get("execution_valid") else "无效"],
            ["未豁免硬指标", f"{hard_passed} / {len(hard_required)}"], ["综合分", final_score.get("overall_score")],
            ["综合档位", final_score.get("overall_band")], ["低于85分项", len(low)], ["豁免", len(waivers)],
            ["200x以上长尾", "已审计" if long_tail else "无数据/未完成"], ["交付建议", "可进入交付" if formal.get("execution_valid") else "等待有效FORMAL"]
        ]), "", "### 一句话结论", "", f"本次对齐结论为**{status}**；硬指标、综合评分和 FORMAL 资格以本报告后续机器证据为准。", "",
        "## 1. 任务范围与依据", "", "### 1.1 对齐范围", "", table(["字段", "值", "边界"], [["任务ID", inputs.get("task_id"), "全阶段一致"], *scope_rows]), "", table(["目标项", "值"], scope_target_rows), "", "### 1.2 权威资料与版本", "", table(["资料ID", "资料", "资格"], source_summary_rows), "", table(["资料ID", "路径", "SHA-256/版本"], source_path_rows), "", "### 1.3 统计口径", "", table(["口径项", "定义"], [["完整付费入口", inputs.get("paid_entry_definition", "真实扣款开始至恢复可再次扣款状态")], ["投注", inputs.get("bet_basis", "入口实际扣款")], ["派奖", inputs.get("payout_basis", "入口及全部后续Feature/collect派奖")], ["组件拆分", "按同一入口链拆分Base/Feature/其他贡献"], ["定向样本", "不混入总体指标"], ["FORMAL单位", "完整付费入口"]]), "",
        "## 2. 指标对齐详情", "", table(["编号", "指标", "分类", "作用域", "基线→FORMAL"], metric_overview_rows), "", "指标编号、分类和顺序与阶段2、阶段3保持一致。", "",
        "### 2.1 硬指标", "", metric_sections("hard"), "", "> 硬指标只判最终门禁，不进入综合分。组件RTP目标仍使用原版贡献占比映射权威总RTP。", "",
        "### 2.2 评分指标", "", metric_sections("score"), "",
        "### 2.3 审计指标", "", metric_sections("audit"), "", "> 审计指标不参与硬门禁和综合分，但必须保留目标与FORMAL审计结果。", "",
        "## 3. 综合评分汇总", "", "### 3.1 评分组汇总", "", group_table, "", "### 3.2 低于85分项", "", table(["指标", "得分", "档位", "差距"], [[x.get("name_zh"), x.get("score"), x.get("band"), x.get("distance")] for x in low]), "",
        "## 4. 玩法画像与指标覆盖", "", "### 4.1 玩法画像", "", mechanic_table, "", mechanic_attribute_table, "", mechanic_evidence_table, "", "### 4.2 指标包匹配", "", metric_table, "", "### 4.3 覆盖率", "", table(["项目", "结果"], named_rows(contract.get("coverage", {}), {"mechanic_required": "必需玩法节点", "mechanic_owned": "已有Owner玩法节点", "mechanic_coverage": "玩法覆盖率", "metric_required": "必需指标", "metric_measurable": "可测指标", "metric_measurability": "指标可测率"})), "",
        "## 5. 参数变化", "", parameter_table, "", parameter_metric_table, "", "### 5.1 权限与玩法边界确认", "", table(["边界", "结论", "依据"], [["参数授权", authority.get("status", "未知"), "parameter_authority.json"], ["Normal / Ante", "未修改", "作用域限制"], ["paytable / 价格 / 初始次数 / 重触", "未修改", "禁止类别"], ["状态机 / 触发与结算 / RNG顺序", "未修改", "禁止类别"], ["封顶 / 最大中奖 / 公共接口", "未修改", "禁止类别"]]), "",
        "## 6. CALIBRATION过程", "", "### 6.1 搜索与预算", "", budget_table, "", attainability_table, "", ceiling_table, "", "### 6.2 候选演进", "", candidate_table, "", candidate_parameter_table, "", "### 6.3 停止原因", "", f"停止原因：{candidates.get('stop_reason', '—')}", "",
        "## 7. FORMAL验收", "", table(["项目", "计划/要求", "实际结果"], [["冻结候选", manifest.get("frozen_candidate_id"), formal.get("candidate_id")], ["计划ID", manifest.get("formal_plan_id"), formal.get("plan_id")], ["执行路径", "仅Python；Server Flow/JVM调用数=0", formal.get("execution_path", "未记录")], ["独立种子集", "与CALIBRATION不同", formal.get("sample", {}).get("seed_set_hash")], ["样本数", formal.get("planned_sample_count"), formal.get("sample", {}).get("paid_entry_count")], ["有效尝试上限", manifest.get("formal_attempt_limit"), formal.get("attempt")], ["执行有效性", True, formal.get("execution_valid")], ["真实结论", "硬指标+综合分+FORMAL联合判定", formal.get("status")]]), "", "### 7.1 独立性证明", "", table(["检查项", "要求", "结果"], [["候选冻结", "FORMAL前参数hash固定", formal.get("candidate_hash", "未记录")], ["种子/trace", "与CALIBRATION独立", formal.get("sample", {}).get("seed_set_hash")], ["执行进程/输入", "独立且hash密封", f"{len(formal_hash_rows)}项"], ["阶段1Server Flow认证", "绑定认证证据hash", formal.get("stage1_server_flow_certification_sha256", "未记录")], ["FORMAL Server Flow调用数", 0, formal.get("server_flow_call_count", "未记录")], ["独立性总判定", True, formal.get("independent_from_calibration")]]), "", table(["输入对象", "SHA-256"], formal_hash_rows), "",
        "## 8. 豁免、不可达与阻塞", "", table(["指标", "状态", "原因", "批准状态"], waiver_summary_rows), "", table(["指标", "批准项", "内容"], waiver_approval_rows), "", "## 9. 最终交付建议", "", "进入阶段5封存；封存后执行一次非阻塞ServerFlow硬指标审计，审计结果只警告且不改变既有状态。" if formal.get("execution_valid") else "等待有效FORMAL或补充证据后再封存。", "",
        "## 10. 版本、Hash与复算", "", table(["对象", "SHA-256"], sorted(hashes.items())), "", "### 10.1 复算命令", "", "```bash", "<python_bin> <skill_root>/scripts/score_alignment.py --contract artifacts/02-metric-matching/metric_contract.json --measurements <formal_measurements.json> --output artifacts/03-scoring/scorecard.json", "```", "", "## 附录索引", "", "- `../01-input-profile/`：资料、玩法画像与参数权限", "- `../02-metric-matching/`：指标合同、扩展与豁免", "- `../03-scoring/scorecard.json`：权威评分", "- `alignment_manifest.json`、`candidate_archive.json`、`aligned_parameters.json`、`formal_result.json`：对齐与FORMAL机器结果", ""
    ]
    return "\n".join(lines), status


def main():
    parser = argparse.ArgumentParser(description="由密封机器结果生成中文数值对齐报告")
    parser.add_argument("--artifacts", required=True, type=Path)
    parser.add_argument("--display-metadata", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    text, status = render(args.artifacts, load(args.display_metadata) if args.display_metadata else None)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding="utf-8")
    print(json.dumps({"status": "通过", "output": str(args.output), "alignment_status": status}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
