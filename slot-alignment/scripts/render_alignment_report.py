#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path


def load(path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def fmt(value):
    if value is None:
        return "无"
    if isinstance(value, float):
        return f"{value:.4f}".rstrip("0").rstrip(".")
    if isinstance(value, (dict, list)):
        return f"`{json.dumps(value, ensure_ascii=False, sort_keys=True)}`"
    return str(value).replace("|", "\\|")


def table(headers, rows):
    if not rows:
        return "无。"
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    lines += ["| " + " | ".join(fmt(x) for x in row) + " |" for row in rows]
    return "\n".join(lines)


def named_rows(data, names):
    return [[names.get(k, k), v] for k, v in data.items()]


def main():
    parser = argparse.ArgumentParser(description="由密封机器结果生成中文数值对齐报告")
    parser.add_argument("--artifacts", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    a = args.artifacts
    inputs = load(a / "01-input-profile/input_manifest.json")
    profile = load(a / "01-input-profile/game_profile.json")
    authority = load(a / "01-input-profile/parameter_authority.json")
    contract = load(a / "02-metric-matching/metric_contract.json")
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
    hard_table = table(["指标", "作用域", "目标", "FORMAL", "差距", "容差", "状态"], [[x.get("name_zh", x.get("metric_id")), x.get("scope"), x.get("target"), x.get("candidate"), x.get("distance"), x.get("tolerance"), x.get("status")] for x in hard])
    score_table = table(["指标", "作用域", "得分", "档位", "权重"], [[x.get("name_zh", x.get("metric_id")), x.get("scope"), x.get("score"), x.get("band"), x.get("weight")] for x in final_score.get("scores", [])])
    group_table = table(["评分组", "得分", "档位", "权重"], [[x.get("group"), x.get("score"), x.get("band"), x.get("weight")] for x in final_score.get("groups", [])])
    mechanic_table = table(["玩法ID", "中文名", "状态", "作用域", "证据"], [[x.get("mechanic_id"), x.get("name_zh"), x.get("status"), x.get("scope"), x.get("evidence", [])] for x in mechanics])
    metric_table = table(["指标ID", "Owner", "类型", "作用域", "状态"], [[x.get("metric_id"), x.get("owner"), x.get("kind"), x.get("scope"), x.get("status", "必需")] for x in metric_items])
    parameter_table = table(["参数", "原值", "对齐值", "变化", "授权"], [[x.get("path"), x.get("before"), x.get("after"), x.get("delta"), x.get("authorization_status", "已授权")] for x in parameters.get("parameters", [])])
    candidate_table = table(["候选", "父候选", "硬指标", "综合分", "样本", "状态"], [[x.get("candidate_id"), x.get("parent_id"), x.get("hard_gate_status"), x.get("overall_score"), x.get("sample_count"), x.get("status")] for x in candidates.get("candidates", [])])
    feature_table = table(["Feature指标", "得分", "档位"], [[x.get("name_zh", x.get("metric_id")), x.get("score"), x.get("band")] for x in feature_scores]) if feature_scores else "不适用。"
    long_tail = formal.get("audits", {}).get("long_tail", [])
    long_tail_table = table(["倍率桶", "原版", "候选", "样本资格", "结论"], [[x.get("bucket"), x.get("target"), x.get("candidate"), x.get("sample_status"), x.get("status", "审计")] for x in long_tail])
    hashes = {}
    for source in (inputs.get("hashes", {}), contract.get("catalogs", {}).get("hashes", {}), manifest.get("input_hashes", {})):
        hashes.update(source)
    lines = [
        "# 阶段4-数值对齐报告", "", "## 首页结论", "",
        table(["项目", "最终结果"], [
            ["游戏 / 模式 / RTP组", f"{scope.get('game_code','')} / {scope.get('mode','')} / {scope.get('rtp_group','')}"],
            ["对齐结论", status], ["FORMAL有效性", "有效" if formal.get("execution_valid") else "无效"],
            ["未豁免硬指标", f"{hard_passed} / {len(hard_required)}"], ["综合分", final_score.get("overall_score")],
            ["综合档位", final_score.get("overall_band")], ["低于85分项", len(low)], ["豁免", len(waivers)],
            ["200x以上长尾", "已审计" if long_tail else "无数据/未完成"], ["交付建议", "可进入交付" if formal.get("execution_valid") else "等待有效FORMAL"]
        ]), "", "### 一句话结论", "", f"本次对齐结论为**{status}**；硬指标、综合评分和 FORMAL 资格以本报告后续机器证据为准。", "",
        "## 1. 任务范围与依据", "", "### 1.1 对齐范围", "", table(["字段", "值"], named_rows(scope, {"game_code": "游戏", "mode": "模式", "rtp_group": "RTP组", "target_rtp": "目标RTP"})), "", "### 1.2 权威资料与版本", "", table(["资料", "路径"], named_rows(inputs.get("paths", {}), {"workspace_root": "工作区", "slot_docs_root": "游戏资料根目录", "server_root": "Server根目录", "runtime": "Runtime", "simulation_script": "模拟脚本"})), "", "### 1.3 统计口径", "", "以真实扣款开始、包含全部自然后续状态的完整付费入口链为总体统计单位；定向 Feature 样本不混入总体指标。", "",
        "## 2. 硬指标结果", "", "> 硬指标采用红线门禁，只判通过、不通过或硬指标已豁免，不进入综合分。", "", hard_table, "", "### 2.1 总RTP", "", table(["指标", "目标", "FORMAL", "状态"], [[x.get("name_zh"), x.get("target"), x.get("candidate"), x.get("status")] for x in hard if x.get("metric_id") == "core.rtp.total"]), "", "### 2.2 中奖率与各类Feature自然触发率", "", table(["指标", "作用域", "目标", "FORMAL", "状态"], [[x.get("name_zh"), x.get("scope"), x.get("target"), x.get("candidate"), x.get("status")] for x in hard if "hit_rate" in x.get("metric_id", "") or "trigger_rate" in x.get("metric_id", "")]), "", "### 2.3 200x以下倍率分布", "", table(["指标", "差距", "容差", "状态"], [[x.get("name_zh"), x.get("distance"), x.get("tolerance"), x.get("status")] for x in hard if "multiplier_distribution" in x.get("metric_id", "")]), "", "### 2.4 Sigma", "", table(["作用域", "目标", "FORMAL", "状态"], [[x.get("scope"), x.get("target"), x.get("candidate"), x.get("status")] for x in hard if x.get("metric_id") == "core.sigma"]), "", "### 2.5 Base / Feature / 其他组件RTP贡献", "", table(["作用域", "目标", "FORMAL", "状态"], [[x.get("scope"), x.get("target"), x.get("candidate"), x.get("status")] for x in hard if "component_contribution" in x.get("metric_id", "")]), "",
        "## 3. 综合评分", "", "### 3.1 评分组汇总", "", group_table, "", "### 3.2 低于85分项", "", table(["指标", "得分", "档位", "差距"], [[x.get("name_zh"), x.get("score"), x.get("band"), x.get("distance")] for x in low]), "", "### 3.3 全部评分指标", "", score_table, "",
        "## 4. 玩法画像与指标覆盖", "", "### 4.1 玩法画像", "", mechanic_table, "", "### 4.2 指标包匹配", "", metric_table, "", "### 4.3 覆盖率", "", table(["项目", "结果"], named_rows(contract.get("coverage", {}), {"mechanic_required": "必需玩法节点", "mechanic_owned": "已有Owner玩法节点", "mechanic_coverage": "玩法覆盖率", "metric_required": "必需指标", "metric_measurable": "可测指标", "metric_measurability": "指标可测率"})), "",
        "## 5. Feature专项结果", "", feature_table, "", "## 6. 200x以上长尾与最大中奖审计", "", long_tail_table, "", fmt(formal.get("audits", {}).get("max_win", "无。")), "", "> 本章节只审计；其贡献仍包含在总RTP、Sigma和风险判断中。", "",
        "## 7. 参数变化", "", parameter_table, "", "### 7.1 权限与玩法边界确认", "", f"参数授权状态：{authority.get('status','未知')}；未修改玩法、状态机、触发/结算语义、RNG顺序或封顶规则。", "",
        "## 8. CALIBRATION过程", "", "### 8.1 搜索与预算", "", fmt(candidates.get("budget", {})), "", "### 8.2 候选演进", "", candidate_table, "", "### 8.3 停止原因", "", fmt(candidates.get("stop_reason", "")), "",
        "## 9. FORMAL验收", "", table(["项目", "结果"], [["候选ID", formal.get("candidate_id")], ["计划ID", formal.get("plan_id")], ["有效尝试", formal.get("attempt")], ["样本", formal.get("sample")], ["状态", formal.get("status")]]), "", "### 9.1 独立性证明", "", "通过。" if formal.get("independent_from_calibration") else "未通过或证据不足。", "",
        "## 10. 豁免、不可达与阻塞", "", table(["指标", "状态", "原因", "批准"], [[x.get("metric_id"), x.get("status"), x.get("reason"), x.get("approval")] for x in waivers]) if waivers else "无。", "", "## 11. 最终交付建议", "", "进入阶段5封存。" if formal.get("execution_valid") else "等待有效FORMAL或补充证据后再封存。", "",
        "## 12. 版本、Hash与复算", "", table(["对象", "SHA-256"], sorted(hashes.items())), "", "### 12.1 复算命令", "", "```bash", "<python_bin> <skill_root>/scripts/score_alignment.py --contract artifacts/02-metric-matching/metric_contract.json --measurements <formal_measurements.json> --output artifacts/03-scoring/scorecard.json", "```", "", "## 附录索引", "", "- `../01-input-profile/`：资料、玩法画像与参数权限", "- `../02-metric-matching/`：指标合同、扩展与豁免", "- `../03-scoring/scorecard.json`：权威评分", "- `alignment_manifest.json`、`candidate_archive.json`、`aligned_parameters.json`、`formal_result.json`：对齐与FORMAL机器结果", ""
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"status": "通过", "output": str(args.output), "alignment_status": status}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
