#!/usr/bin/env python3
import argparse
import hashlib
import json
import sys
from pathlib import Path

from report_common import fmt, table


def load(path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def render(contract, scorecard, contract_hash, scorecard_hash):
    hard = scorecard.get("hard_gates", [])
    scores = scorecard.get("scores", [])
    groups = scorecard.get("groups", [])
    hard_required = [item for item in hard if item.get("status") != "硬指标已豁免"]
    hard_passed = sum(item.get("status") == "通过" for item in hard_required)
    low = [item for item in scores if item.get("score") is not None and item.get("score") < 85]
    blockers = scorecard.get("blocking_reasons", [])
    waivers = [item for item in hard + scores if item.get("waiver", {}).get("status") == "已批准"]
    scope = contract.get("scope", {})
    source_hashes = scorecard.get("source_hashes", {})
    source_paths = scorecard.get("source_paths", {})
    metric_contract = {(x.get("metric_id"), x.get("scope")): x for x in contract.get("metrics", [])}
    coverage = contract.get("coverage", {})

    def source(item):
        return metric_contract.get((item.get("metric_id"), item.get("scope")), {})

    lines = [
        "# 阶段3-评分报告", "",
        "> 本报告冻结候选搜索前的评价标准，并用当前基线验证全部指标可计算。基线不通过可以进入阶段4调参；评分无法判定不得进入阶段4。", "",
        "## 一、首页结论与阶段职责", "",
        table(["项目", "结果", "判定/说明"], [
            ["任务ID", scorecard.get("task_id")],
            ["游戏 / 模式 / RTP组", f"{scope.get('game_code', '')} / {scope.get('mode', '')} / {scope.get('rtp_group', '')}"],
            ["基线评分状态", scorecard.get("alignment_status")],
            ["阶段3机器状态", scorecard.get("status")],
            ["未豁免硬指标", f"{hard_passed} / {len(hard_required)}"],
            ["综合分", scorecard.get("overall_score")],
            ["综合档位", scorecard.get("overall_band")],
            ["低于85分项", len(low)],
            ["豁免项", len(waivers)],
            ["阶段4资格", "待阶段转换门禁校验" if not blockers else "阻塞"]
        ][0:0] + [
            ["任务ID", scorecard.get("task_id"), "与阶段1、2一致"],
            ["游戏 / 模式 / RTP组", f"{scope.get('game_code', '')} / {scope.get('mode', '')} / {scope.get('rtp_group', '')}", "固定评价作用域"],
            ["基线评分状态", scorecard.get("alignment_status"), "通过/豁免后通过/不通过均可判定"],
            ["阶段3机器状态", scorecard.get("status"), "必须已完成"],
            ["未豁免硬指标", f"{hard_passed} / {len(hard_required)}", "阶段3展示基线差距，不以基线不通过阻断调参"],
            ["综合分 / 档位", f"{scorecard.get('overall_score')} / {scorecard.get('overall_band')}", "非硬指标汇总"],
            ["低于85分项", len(low), "逐项列入第六章"], ["豁免项", len(waivers), "必须有批准证据"],
            ["阶段职责", "冻结标准并验证基线可测", "不得在本阶段计算新候选"],
            ["阶段4资格", "待阶段转换门禁校验" if not blockers else "阻塞", "以stage3_gate.json为准"],
        ]), "",
        "## 二、评分输入与冻结合同", "", table(["对象", "路径", "SHA-256", "资格/用途"], [
            ["指标合同", source_paths.get("metric_contract"), source_hashes.get("metric_contract", contract_hash), "候选结果出现前密封"],
            ["基线测量", source_paths.get("measurements"), source_hashes.get("measurements"), "当前Runtime、合格完整入口"],
            ["阶段3机器评分", "artifacts/03-scoring/scorecard.json", scorecard_hash, "本报告唯一评分来源"],
            ["容差政策", contract.get("hard_gate_tolerance_policy", {}).get("source_path"), contract.get("hard_gate_tolerance_policy", {}).get("source_sha256"), "基础容差×系数=生效容差"],
        ]), "",
        "## 三、硬指标门禁", "",
        table(["指标", "作用域", "目标", "基线", "差距", "方法", "基础容差", "系数", "生效容差", "样本资格", "状态"], [
            [item.get("name_zh", item.get("metric_id")), item.get("scope"), item.get("target"), item.get("candidate"), item.get("distance"), source(item).get("hard_gate_profile", {}).get("method"), item.get("base_tolerance"), item.get("tolerance_factor"), item.get("tolerance"), source(item).get("sample_qualification"), item.get("status")]
            for item in hard
        ]), "",
        "> 硬指标只作红线门禁，不进入综合分；基线不通过表示需要阶段4调参，不表示阶段3流程失败。", "",
        "## 四、综合评分组", "",
        table(["评分组", "得分", "档位", "组权重", "有效指标数", "汇总方法"], [[item.get("group"), item.get("score"), item.get("band"), item.get("weight"), item.get("metric_count"), item.get("method", "组内加权后参与综合分")] for item in groups]), "",
        "## 五、逐项100分评分", "",
        table(["指标", "作用域", "目标", "基线", "差距", "评价方法/锚点", "评分组", "权重", "得分", "档位", "状态"], [
            [item.get("name_zh", item.get("metric_id")), item.get("scope"), item.get("target"), item.get("candidate"), item.get("distance"), source(item).get("score_profile"), source(item).get("score_group"), item.get("weight", source(item).get("weight")), item.get("score"), item.get("band"), item.get("status")]
            for item in scores
        ]), "",
        "## 六、低于85分项与差距说明", "", table(["指标", "作用域", "得分", "档位", "目标", "基线", "差距", "主要影响控制簇", "阶段4优先级"], [[item.get("name_zh", item.get("metric_id")), item.get("scope"), item.get("score"), item.get("band"), item.get("target"), item.get("candidate"), item.get("distance"), source(item).get("control_cluster"), source(item).get("priority", "按分数和硬门禁联合排序")] for item in low]), "",
        "## 七、阻塞、豁免与不可判定项", "", table(["对象", "作用域", "类型", "原因", "批准/恢复状态", "证据"], [[item.get("metric_id"), item.get("scope"), "阻塞", item.get("reason"), item.get("status"), item.get("evidence")] for item in blockers] + [[item.get("metric_id"), item.get("scope"), "豁免", item.get("waiver", {}).get("reason"), item.get("waiver", {}).get("status"), item.get("waiver", {}).get("evidence")] for item in waivers]), "",
        "## 八、覆盖率与可测性复核", "", table(["检查项", "当前值", "通过标准", "结论"], [
            ["必需玩法节点", coverage.get("mechanic_required"), "全部有Owner", "通过" if coverage.get("mechanic_coverage") in {1, 1.0} else "阻塞"],
            ["玩法覆盖率", coverage.get("mechanic_coverage"), "100%", "通过" if coverage.get("mechanic_coverage") in {1, 1.0} else "阻塞"],
            ["必需指标", coverage.get("metric_required"), "全部实例化", "信息"], ["指标可测率", coverage.get("metric_measurability"), "100%", "通过" if coverage.get("metric_measurability") in {1, 1.0} else "阻塞"],
            ["硬指标结果数量", len(hard), len([x for x in contract.get("metrics", []) if x.get("kind") == "hard" and x.get("status") != "不适用"]), "必须一致"],
            ["评分指标结果数量", len(scores), len([x for x in contract.get("metrics", []) if x.get("kind") == "score" and x.get("status") != "不适用"]), "必须一致"],
        ]), "",
        "## 九、版本、Hash与复算", "", table(["对象", "路径", "SHA-256"], [
            ["指标合同", source_paths.get("metric_contract"), source_hashes.get("metric_contract", contract_hash)], ["基线测量", source_paths.get("measurements"), source_hashes.get("measurements")],
            ["阶段3评分", "artifacts/03-scoring/scorecard.json", scorecard_hash], ["生成器", "render_scoring_report.py", "由Skill版本绑定"]
        ]), "", "```bash", "<python_bin> <skill_root>/scripts/render_scoring_report.py --contract <metric_contract.json> --scorecard <scorecard.json> --output <阶段3-评分报告.md>", "```", "",
        "## 十、阶段3到阶段4门禁", "", table(["门禁项", "要求", "当前状态/动作"], [
            ["固定scorecard", "来自当前合同和基线测量", scorecard.get("status")], ["报告确定性", "与当前JSON重新渲染完全一致", "由validate_stage_transition.py校验"],
            ["评分可判定", "alignment_status不得为无法判定", scorecard.get("alignment_status")], ["阶段4启动", "stage3_gate.json通过且stage4_allowed=true", "未通过前禁止敏感性、CALIBRATION和候选计算"],
        ]), "", "阶段3只冻结评价标准并完成基线验算；不得把候选内部scorecard替代本阶段固定产物。", ""
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="确定性生成阶段3中文评分报告")
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--scorecard", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        contract, scorecard = load(args.contract), load(args.scorecard)
        if contract.get("task_id") != scorecard.get("task_id"):
            raise ValueError("指标合同与评分task_id不一致")
        text = render(contract, scorecard, sha(args.contract), sha(args.scorecard))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
        print(json.dumps({"status": "通过", "output": str(args.output), "alignment_status": scorecard.get("alignment_status")}, ensure_ascii=False))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "失败", "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
