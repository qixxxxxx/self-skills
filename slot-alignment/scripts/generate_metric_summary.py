#!/usr/bin/env python3
import argparse
from pathlib import Path

from alignment import load_json


ROOT = Path(__file__).resolve().parents[1]


def render(library):
    category_names = {item["category_id"]: item["name_zh"] for item in library["categories"]}
    lines = [
        "# Slot Alignment 7.0 指标目录",
        "",
        f"版本：`{library['version']}`",
        "",
        "本文件由`references/指标目录/index.json`确定性生成，只用于快速阅读卡与Facet；不得手工修改或反向覆盖JSON。详细画像和实例规则见[指标与玩法画像](../01-指标框架.md)，算法与通过值见[评价合同](../02-评价合同.md)。",
        "",
        "中奖组、组件、结算模型、Feature、符号和盘面作用域只按框架扩展卡内子项，不增加卡权重。",
        "",
    ]
    for category in library["categories"]:
        category_id = category["category_id"]
        lines += [f"## {category_id}：{category_names[category_id]}", "", category["owner_boundary_zh"], "", "| 卡 | 名称 | 类型 | 玩家问题 | Facet |", "|---|---|---|---|---|"]
        for card in [item for item in library["cards"] if item["category_id"] == category_id]:
            facets = "；".join(f"{item['name_zh']}（{item['distance_method']}）" for item in card["facets"])
            lines.append(f"| {card['card_id']} | {card['name_zh']} | {card['kind']} | {card['player_question_zh']} | {facets} |")
        lines.append("")
    lines += ["## 审计", "", "| ID | 名称 | 来源卡 | 内容 |", "|---|---|---|---|"]
    for audit in library["audits"]:
        lines.append(f"| {audit['audit_id']} | {audit['name_zh']} | {', '.join(audit['source_cards'])} | {', '.join(audit['includes'])} |")
    lines += ["", "全部N/J/P/B活动正式项都只按“距离 <= C级通过值”判定，任一失败不得用分数补偿。原版证据低于最低线的实例在候选前整项或整组转为观察，不参与通过判定但必须完整披露；存在观察项时最多只能给出有限范围通过。当前已落定N/J/P/B单项分、卡分和分类分；跨分类综合权重留待后续授权。", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="生成7.0指标中文汇总")
    parser.add_argument("--library", default=str(ROOT / "references/指标目录/index.json"))
    parser.add_argument("--output", default=str(ROOT / "references/指标目录/index.md"))
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    text = render(load_json(args.library))
    output = Path(args.output)
    if args.check:
        if not output.is_file() or output.read_text(encoding="utf-8") != text:
            raise SystemExit("7.0指标中文汇总不是当前JSON的确定性结果")
        print("OK: 7.0指标中文汇总一致")
    else:
        output.write_text(text, encoding="utf-8")
        print(output)


if __name__ == "__main__":
    main()
