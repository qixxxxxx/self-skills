#!/usr/bin/env python3
import argparse
from pathlib import Path

from alignment import load_json


def display(value):
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.8g}"
    return str(value)


def render(contract, result):
    by_card = {item["card_id"]: item for item in result["card_results"]}
    lines = [
        "# Slot Alignment v5.7指标判定报告",
        "",
        "## 1. 冻结输入与Hash",
        "",
        f"- 任务：`{result['task_id']}`",
        f"- 阶段：`{result['phase']}`",
        f"- 指标合同SHA-256：`{result['metric_contract_sha256']}`",
        "",
        "## 2. 玩法画像与适用指标卡",
        "",
        f"活动卡：{sum(item['status'] != '不适用' for item in result['card_results'])}；不适用卡：{sum(item['status'] == '不适用' for item in result['card_results'])}。",
        "",
    ]
    section_names = [("N", "3. N类数值门禁"), ("J", "4. J类中奖结算"), ("P", "5. P类玩法过程"), ("B", "6. B类盘面呈现")]
    for category, title in section_names:
        lines += [f"## {title}", "", "| 卡/实例 | 目标 | 候选 | C级容差 | 偏差倍数 | 单项/卡分 | 等级/状态 |", "|---|---:|---:|---:|---:|---:|---|"]
        for card in [item for item in contract["cards"] if item["category_id"] == category]:
            card_result = by_card[card["card_id"]]
            lines.append(f"| **{card['card_id']} {card['name_zh']}** | — | — | — | {display(card_result['maximum_deviation_ratio'])} | {display(card_result['score'])} | **{card_result['formal_grade']} / {card_result['status']}** |")
            for item in card_result["instances"]:
                lines.append(f"| {item['instance_id']} | {display(item['target'])} | {display(item['candidate'])} | {display(item['tolerance'])} | {display(item['deviation_ratio'])} | {display(item['score'])} | {item['formal_grade']} / {item['status']} |")
        lines.append("")
    lines += ["## 7. 审计与派生展示", ""]
    if result["audits"]:
        for audit in result["audits"]:
            lines.append(f"- {audit['audit_id']} {audit['name_zh']}：{audit['status']}；{display(audit['details'])}")
    else:
        lines.append("- 无审计结果。")
    lines += ["", "## 8. 样本不足、计算异常与结构不可达", ""]
    exceptions = [item for card in result["card_results"] for item in card["instances"] if item["status"] in {"样本不足", "计算异常", "不通过"}]
    if exceptions:
        for item in exceptions:
            lines.append(f"- `{item['instance_id']}`：{item['status']}；{item.get('reason_zh') or '见机器结果与样本证据'}")
    else:
        lines.append("- 无。")
    summary = result["summary"]
    lines += [
        "",
        "## 9. CALIBRATION与FORMAL证据",
        "",
        "本报告只呈现当前机器结果；任一N/J/P/B必需项失败时不得用分数补偿。",
        "",
        "## 10. 最终状态",
        "",
        f"- 最终状态：**{summary['final_status']}**",
        f"- 当前阶段等级：**{summary['final_grade']}**",
        f"- N类阶段分（当前等级使用）：{display(summary['category_scores']['N'])}",
        f"- J类分（已计算，跨分类权重待授权）：{display(summary['category_scores']['J'])}",
        f"- 当前评分范围：{', '.join(summary['score_scope'])}",
        f"- 完整框架预留：{', '.join(summary['planned_score_scope'])}",
        f"- 硬门禁失败实例：{summary['hard_gate_failures']}",
        f"- J/P/B失败实例：{summary['alignment_failures']}",
        f"- 样本不足或计算异常实例：{summary['insufficient_or_error_instances']}",
        f"- 最大偏差倍数：{display(summary['maximum_deviation_ratio'])}",
        f"- 最差实例：{display(summary['worst_instance_id'])}",
        "",
        "> 当前N卡分、J卡分和J类分已落定；N/J跨分类权重与P/B分数尚未授权，所以当前等级仍只使用N类阶段分。通过状态仍要求所有N/J/P/B必需项通过。",
        "",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="渲染slot-alignment v5判定报告")
    parser.add_argument("--contract", required=True)
    parser.add_argument("--result", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    Path(args.output).write_text(render(load_json(args.contract), load_json(args.result)), encoding="utf-8")


if __name__ == "__main__":
    main()
