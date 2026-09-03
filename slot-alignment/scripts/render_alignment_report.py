#!/usr/bin/env python3
import argparse
import json
import tempfile
from datetime import datetime
from pathlib import Path

from alignment import finite_number, grade_score, load_json, sha256_file


ROOT = Path(__file__).resolve().parents[1]
LIBRARY_PATH = ROOT / "references/指标目录/index.json"
EVALUATION_POLICY_PATH = ROOT / "assets/policies/alignment_evaluation_policy.json"

GRADE_NAMES = {
    "S": "高度一致", "A": "稳定一致", "B": "基本一致", "C": "最低通过",
    "F": "不通过", "U": "无法判定", "NA": "不适用",
}
CATEGORY_CONTENT = {
    "N": "RTP、中奖率、触发率、波动和组件贡献",
    "J": "中奖内容、单次中奖和连续结算",
    "P": "玩法入场、玩法长度和特色机制",
    "B": "符号构成、关键元素、聚集和盘面形态",
}
CATEGORY_NAMES = {"N": "数值指标", "J": "中奖结算", "P": "玩法过程", "B": "盘面呈现"}
FACET_SUMMARIES = {
    "total_rtp": "玩家长期每投入1单位，平均可以获得多少回报。",
    "positive_return_rate": "一次完整付费后，最终获得正奖励的概率。",
    "natural_trigger_rate": "不购买玩法时，自然进入指定Feature的概率。",
    "return_ge_cost_rate": "一次完整付费至少收回本次实际成本的概率。",
    "return_sigma": "回报结果上下起伏的大小，数值越高代表波动越强。",
    "component_rtp": "总RTP中由指定游戏组件贡献的部分。",
    "win_group_participation_rate": "发生中奖时，指定中奖内容参与结算的频率。",
    "primary_structure_bin_rate": "每次中奖落入指定结构规模档位的概率。",
    "primary_structure_distribution_shift": "主要中奖结构整套档位相对原版移动了多少。",
    "primary_structure_mean": "每次中奖的主要结构平均有多大。",
    "primary_structure_p50": "一半中奖结果不会超过的常见结构规模。",
    "primary_structure_p90": "较大中奖通常可以达到的结构规模。",
    "simultaneous_visible_win_count_bin_rate": "一次结算同时出现指定数量中奖的概率。",
    "simultaneous_visible_win_count_distribution_shift": "同时中奖数量的整套分布相对原版移动了多少。",
    "visible_step_reward_mean": "一次有奖结算平均可以获得多少倍投注。",
    "visible_step_reward_p50": "一半有奖结算不会超过的常见奖励。",
    "visible_step_reward_p90": "较高单次结算通常可以达到的奖励。",
    "total_depth_bin_rate": "一次玩家动作连续结算到指定深度的概率。",
    "total_depth_distribution_shift": "连续结算深度的整套分布相对原版移动了多少。",
    "entry_award_bin_rate": "进入Feature时获得指定起始资源档位的概率。",
    "entry_award_distribution_shift": "Feature入场奖励的整套分布相对原版移动了多少。",
    "feature_duration_mean": "一轮完整Feature平均会执行多少次主要动作。",
    "feature_duration_p50": "一半完整Feature不会超过的常见长度。",
    "feature_duration_p90": "较长Feature通常可以达到的长度。",
    "mechanic_result_bin_rate": "每次特色机制机会落入指定玩家可见结果的概率。",
    "mechanic_result_distribution_shift": "特色机制结果的整套分布相对原版移动了多少。",
    "symbol_group_share_bin_rate": "指定普通符号组占全部可见格子的比例。",
    "symbol_group_composition_shift": "普通符号组整体构成相对原版移动了多少。",
    "symbol_group_member_share_bin_rate": "同一普通符号组内，指定成员所占的比例。",
    "symbol_group_member_distribution_shift": "同组符号内部构成相对原版移动了多少。",
    "key_symbol_count_bin_rate": "稳定盘面出现指定数量关键符号的概率。",
    "key_symbol_count_distribution_shift": "关键符号数量的整套分布相对原版移动了多少。",
    "aggregation_bin_rate": "稳定盘面的主要堆叠或聚集落入指定档位的概率。",
    "aggregation_distribution_shift": "主要堆叠或聚集的整套分布相对原版移动了多少。",
    "reel_height_bin_rate": "指定卷轴出现某个高度档位的概率。",
    "reel_height_distribution_shift": "卷轴高度的整套分布相对原版移动了多少。",
    "active_cell_count_mean": "一张稳定盘面平均包含多少个有效格子。",
    "active_cell_count_p50": "一半稳定盘面不会超过的常见有效格数。",
    "active_cell_count_p90": "较大稳定盘面通常可以达到的有效格数。",
    "board_unevenness_mean": "盘面最高卷轴与最低卷轴平均相差多少层。",
    "board_unevenness_p90": "参差较明显的盘面通常相差多少层。",
}
PERCENT_METHODS = {"absolute_probability_error", "total_variation", "half_l1"}
GENERIC_LABELS = {
    "none": "无聚集",
    "single": "单个聚集",
    "two-plus": "2个以上聚集",
    "not-occurred": "没有出现",
    "not-effective": "出现但未生效",
}


def score_text(value):
    return "—" if not finite_number(value) else f"{float(value):.2f}"


def cell(value):
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def number_text(value):
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return f"{float(value):.6g}" if finite_number(value) else str(value)


def symbol_text(value):
    common = {
        "wild": "Wild符号", "scatter": "Scatter符号", "bonus": "Bonus符号",
        "high": "高值符号", "low": "低值符号",
    }
    return common.get(str(value).lower(), f"{str(value).upper()}符号")


def bin_text(value, facet_id, scope):
    raw = str(value)
    labels = scope.get("labels_zh", {})
    if raw in labels.get("states", {}):
        return labels["states"][raw]
    if raw in labels.get("symbol_groups", {}):
        return labels["symbol_groups"][raw]
    if facet_id.startswith("symbol_group_member_"):
        return symbol_text(raw)
    if facet_id.startswith("aggregation_"):
        return GENERIC_LABELS.get(raw, f"聚集档位{raw}")
    if facet_id.startswith("reel_height_"):
        return f"{raw}层"
    if facet_id.startswith("total_depth_"):
        return f"{raw}步"
    if facet_id.startswith("simultaneous_visible_win_count_"):
        return f"{raw}项中奖"
    if facet_id.startswith("key_symbol_count_"):
        return f"{raw}个"
    if facet_id.startswith("entry_award_"):
        unit = {
            "free-spin-count": "次免费旋转", "respin-count": "次重转",
            "pick-count": "次选择", "stage-count": "个阶段",
        }.get(scope.get("entry_award_unit"), "份起始资源")
        return f"{raw}{unit}"
    if facet_id.startswith("primary_structure_"):
        unit = {
            "ways": "Ways", "payline_reels": "轴连中", "pay_symbol_count": "个派奖符号",
            "cluster_size": "格连片", "cleared_cell_count": "个消除格",
        }.get(scope.get("primary_size_axis"), "")
        return f"{raw}{unit}"
    return GENERIC_LABELS.get(raw, raw)


def reel_text(value):
    raw = str(value)
    return raw[1:] if raw.startswith("r") and raw[1:].isdigit() else raw


def unit_for(facet_id, scope):
    if facet_id.startswith("visible_step_reward_"):
        return "倍投注"
    if facet_id.startswith("feature_duration_"):
        return {"spin": "次旋转", "respin_step": "次重转", "pick": "次选择", "stage": "个阶段", "visible_action": "次动作"}.get(scope.get("duration_unit"), "次动作")
    if facet_id.startswith("active_cell_count_"):
        return "格"
    if facet_id.startswith("board_unevenness_"):
        return "层"
    return ""


def value_text(value, method, facet_id, scope):
    if value is None:
        return "—"
    if isinstance(value, dict):
        if set(value) == {"min", "max"}:
            return f"{number_text(value['min'])}～{number_text(value['max'])}"
        parts = []
        for key, item in value.items():
            shown = f"{float(item) * 100:.2f}%" if method in PERCENT_METHODS and finite_number(item) else number_text(item)
            parts.append(f"{bin_text(key, facet_id, scope)}：{shown}")
        return "；".join(parts)
    if method in PERCENT_METHODS and finite_number(value):
        return f"{float(value) * 100:.4g}%"
    unit = unit_for(facet_id, scope)
    return f"{number_text(value)}{unit}"


def distance_text(value, method, facet_id, scope):
    if not finite_number(value):
        return "—"
    if method in PERCENT_METHODS or method == "relative_error":
        return f"{float(value) * 100:.4g}%"
    return f"{number_text(value)}{unit_for(facet_id, scope)}"


def scope_text(scope, facet_id):
    labels = scope.get("labels_zh", {})
    parts = []
    for key in ("scope", "component", "feature", "settlement", "continuous_settlement", "mechanic", "board", "win_group", "symbol_group", "state"):
        if labels.get(key) and labels[key] not in parts:
            parts.append(labels[key])
    if scope.get("scope") == "overall" and not parts:
        parts.append("整体游戏")
    if "reel" in scope:
        parts.append(f"第{reel_text(scope['reel'])}轴")
    if "bin" in scope:
        parts.append(bin_text(scope["bin"], facet_id, scope))
    for key, prefix in (("key_symbol", "关键符号"), ("symbol", "符号")):
        if scope.get(key):
            shown = symbol_text(scope[key])
            parts.append(shown if key == "symbol" else f"{prefix}{shown}")
    return " · ".join(parts) or "整体游戏"


def evidence_text(evidence):
    parts = []
    if evidence.get("sample_count") is not None:
        parts.append(f"原版有效样本{evidence['sample_count']}，最低{evidence['minimum_usable_count']}，建议{evidence['recommended_count']}")
    if evidence.get("minimum_event_count") is not None:
        parts.append(f"实际事件{evidence['event_count']}，最低{evidence['minimum_event_count']}，建议{evidence['recommended_event_count']}")
    if evidence.get("minimum_bucket_count") is not None:
        parts.append(f"当前档位{evidence['bucket_count']}次，最低{evidence['minimum_bucket_count']}次，建议{evidence['recommended_bucket_count']}次")
    return "；".join(parts)


def human_status(item):
    status = item["status"]
    low = item.get("target_evidence", {}).get("classification") == "low"
    if status == "通过":
        return "通过（低样本）" if low else "通过"
    if status == "不通过":
        return "不通过（低样本）" if low else "不通过"
    if status == "样本不足":
        return "候选样本不足"
    return status


def observation_status(item):
    return {
        "observe_no_evidence": "略过（无原版证据）",
        "observe_low_sample": "略过（原版样本不足）",
        "observe_distribution_group": "略过（分布证据不足）",
    }[item["decision"]]


def active_note(item, scope):
    parts = []
    if finite_number(item.get("distance")):
        parts.append(
            f"实际差异{distance_text(item['distance'], item['distance_method'], item['facet_id'], scope)}，"
            f"允许最大{distance_text(item['c_budget'], item['distance_method'], item['facet_id'], scope)}"
        )
    if item.get("target_evidence", {}).get("classification") == "low":
        parts.append(evidence_text(item["target_evidence"]))
    if item.get("reason_zh"):
        parts.append(item["reason_zh"])
    return "；".join(part for part in parts if part) or "结果正常"


def category_result(category, result, contract, policy):
    cards = [item for item in result["card_results"] if item["category_id"] == category]
    active = [item for item in cards if item["status"] not in {"不适用", "观察"}]
    observations = [item for item in contract["coverage"]["observational_instances"] if item["card_id"].startswith(category)]
    low_count = sum(
        item.get("target_evidence", {}).get("classification") == "low"
        for card in cards for item in card["instances"]
    )
    score = result["summary"]["category_scores"][category]
    if any(item["status"] in {"样本不足", "计算异常"} for item in active):
        return "U", score, "无法判定", "存在候选样本不足或计算异常。"
    if any(item["status"] == "不通过" for item in active):
        return "F", score, "不通过", "至少一个正式指标超出允许范围。"
    if active:
        grade = grade_score(float(score), policy) if finite_number(score) else "U"
        details = []
        if low_count:
            details.append(f"{low_count}项低样本")
        if observations:
            details.append(f"{len(observations)}项略过")
        status = "通过" + (f"（{'，'.join(details)}）" if details else "")
        conclusion = "全部活动指标已通过。" if not details else f"活动指标已通过，其中{'，'.join(details)}。"
        return grade, score, status, conclusion
    if observations:
        return "NA", None, "略过", "本类画像命中指标均因原版证据不足而略过正式判定。"
    return "NA", None, "不适用", "玩法画像确认本游戏没有需要评价的对应指标。"


def report_rows(category, contract, result, library):
    result_cards = {item["card_id"]: item for item in result["card_results"]}
    instance_contract = {item["instance_id"]: item for card in contract["cards"] for item in card["instances"]}
    observations = contract["coverage"]["observational_instances"]
    rows = []
    for card in [item for item in library["cards"] if item["category_id"] == category]:
        result_card = result_cards[card["card_id"]]
        for facet in card["facets"]:
            facet_added = 0
            for item in [entry for entry in result_card["instances"] if entry["facet_id"] == facet["facet_id"]]:
                scope = instance_contract[item["instance_id"]]["scope"]
                rows.append({
                    "name": f"{card['card_id']} {facet['name_zh']}",
                    "scope": scope_text(scope, item["facet_id"]),
                    "summary": FACET_SUMMARIES.get(facet["facet_id"], card["player_question_zh"]),
                    "target": value_text(item["target"], item["distance_method"], item["facet_id"], scope),
                    "candidate": value_text(item["candidate"], item["distance_method"], item["facet_id"], scope),
                    "score": score_text(item["score"]),
                    "status": human_status(item),
                    "note": active_note(item, scope),
                    "priority": (
                        0 if item["status"] == "不通过" else
                        1 if item["status"] in {"样本不足", "计算异常"} else
                        3 if item["status"] == "通过" and item.get("target_evidence", {}).get("classification") == "low" else
                        4
                    ),
                })
                facet_added += 1
            for item in [entry for entry in observations if entry["card_id"] == card["card_id"] and entry["facet_id"] == facet["facet_id"]]:
                rows.append({
                    "name": f"{card['card_id']} {facet['name_zh']}",
                    "scope": scope_text(item["scope"], facet["facet_id"]),
                    "summary": FACET_SUMMARIES.get(facet["facet_id"], card["player_question_zh"]),
                    "target": value_text(item["target"], facet["distance_method"], facet["facet_id"], item["scope"]),
                    "candidate": "—",
                    "score": "—",
                    "status": observation_status(item),
                    "note": f"{item['reason_zh']}；{evidence_text(item['target_evidence'])}".rstrip("；"),
                    "priority": 2,
                })
                facet_added += 1
            if not facet_added:
                rows.append({
                    "name": f"{card['card_id']} {facet['name_zh']}",
                    "scope": "当前游戏",
                    "summary": FACET_SUMMARIES.get(facet["facet_id"], card["player_question_zh"]),
                    "target": "—", "candidate": "—", "score": "—", "status": "不适用",
                    "note": "玩法画像未生成该统计项，表示该维度不存在、结果固定或已被其他正式指标完整覆盖。", "priority": 4,
                })
    return rows


def final_summary(result):
    summary = result["summary"]
    failures = summary["hard_gate_failures"] + summary["alignment_failures"]
    if summary["conclusion"] == "完整范围通过":
        return "全部活动正式指标均已通过，且原版证据覆盖完整，可以认定本次对齐完整通过。"
    if summary["conclusion"] == "有限范围通过":
        return f"全部活动正式指标均已通过，但有{summary['observational_instance_count']}项因原版证据不足略过正式判定，因此只能认定为有限范围通过。"
    if summary["conclusion"] == "不通过":
        return f"当前有{failures}项活动正式指标未达到允许范围，本次对齐不通过。"
    return f"当前有{summary['insufficient_or_error_instances']}项活动指标因候选样本不足或计算异常无法判定。"


def render(input_manifest, contract, result, library, policy):
    if not (input_manifest["task_id"] == contract["task_id"] == result["task_id"]):
        raise SystemExit("输入清单、指标合同和评价结果的task_id不一致")
    if result["phase"] != "FORMAL":
        raise SystemExit("最终对齐报告只能使用FORMAL结果")
    summary = result["summary"]
    score_scope = "、".join(f"{item}类" for item in summary["score_scope"])
    grade = summary["final_grade"]
    overall = final_summary(result)
    category_results = {category: category_result(category, result, contract, policy) for category in "NJPB"}
    all_rows = {category: report_rows(category, contract, result, library) for category in "NJPB"}
    attention = sorted(
        [row for rows in all_rows.values() for row in rows if row["priority"] < 4],
        key=lambda row: (row["priority"], row["name"], row["scope"]),
    )[:10]
    active_low = summary["active_low_sample_instance_count"]
    observed = summary["observational_instance_count"]
    normal = max(0, summary["active_instance_count"] - active_low)
    lines = [
        f"# {input_manifest['game_name_zh']} 对齐报告",
        "",
        f"> **对齐结论：{summary['conclusion']}**",
        ">",
        f"> **总对齐等级：{grade} · {GRADE_NAMES[grade]}　综合分：{score_text(summary['composite_score'])}**",
        ">",
        f"> {overall}",
        "",
        "## 一、对齐总览",
        "",
        "| 项目 | 内容 |",
        "|---|---|",
        f"| 游戏 | {input_manifest['game_name_zh']}（{input_manifest['game_code']}） |",
        f"| 任务 | {contract['task_id']} · {contract['mode']} · {input_manifest['runtime_environment']}环境 |",
        f"| 目标RTP | {input_manifest['target_rtp']['value'] * 100:.4g}% |",
        f"| 正式验证 | FORMAL · RTP Group {contract['rtp_group']} |",
        "",
        "### 总体结果",
        "",
        "| 项目 | 结果 | 说明 |",
        "|---|---:|---|",
        f"| 对齐状态 | {summary['conclusion']} | {overall} |",
        f"| 总对齐等级 | {grade} · {GRADE_NAMES[grade]} | 按当前已授权评分范围评定 |",
        f"| 综合分 | {score_text(summary['composite_score'])} | 当前评分范围：{score_scope}；不代表N/J/P/B加权总分 |",
        f"| 覆盖范围 | {summary['coverage_status']} | 活动{summary['active_instance_count']}项，低样本{active_low}项，略过{observed}项 |",
        "",
        "### 四大指标结果",
        "",
        "| 分类 | 主要关注内容 | 对齐等级 | 分类综合分 | 状态 | 一句话结论 |",
        "|---|---|---:|---:|---|---|",
    ]
    for category in "NJPB":
        cat_grade, cat_score, cat_status, cat_conclusion = category_results[category]
        lines.append(f"| {category} {CATEGORY_NAMES[category]} | {CATEGORY_CONTENT[category]} | {cat_grade} · {GRADE_NAMES[cat_grade]} | {score_text(cat_score)} | {cell(cat_status)} | {cell(cat_conclusion)} |")
    lines += [
        "",
        "## 二、指标详情",
        "",
        "状态说明：通过表示达到允许范围；通过（低样本）表示原版证据达到最低线但未达到建议线；略过表示原版证据不足，不参与正式判定；候选样本不足和计算异常会使结果无法判定。",
        "",
    ]
    for category in "NJPB":
        lines += [
            f"### {category} {CATEGORY_NAMES[category]}",
            "",
            f"{next(item['owner_boundary_zh'] for item in library['categories'] if item['category_id'] == category)}",
            "",
            "| 指标名称 | 统计范围 | 一句话说明 | 原版目标 | 对齐结果 | 分数 | 状态 | 备注 |",
            "|---|---|---|---:|---:|---:|---|---|",
        ]
        for row in all_rows[category]:
            lines.append("| " + " | ".join(cell(row[key]) for key in ("name", "scope", "summary", "target", "candidate", "score", "status", "note")) + " |")
        lines.append("")
    lines += ["## 三、需要关注的指标", ""]
    if attention:
        lines += ["| 优先级 | 指标 | 当前状态 | 玩家可能感受到的差异 | 建议 |", "|---:|---|---|---|---|"]
        for index, row in enumerate(attention, 1):
            if row["status"].startswith("不通过"):
                advice = "继续调整相关授权参数后重新FORMAL验证。"
            elif row["status"] in {"候选样本不足", "计算异常"}:
                advice = "补足候选样本或修复计算问题后重新判定。"
            elif row["status"].startswith("略过"):
                advice = "补充原版证据后重新冻结指标合同。"
            else:
                advice = "结果已通过，但后续结论需保留低样本提示。"
            lines.append(f"| {index} | {cell(row['name'])} · {cell(row['scope'])} | {cell(row['status'])} | {cell(row['summary'])} | {advice} |")
    else:
        lines.append("当前没有需要继续处理的正式指标。")
    lines += [
        "",
        "## 四、样本与覆盖说明",
        "",
        "| 类型 | 数量 | 说明 |",
        "|---|---:|---|",
        f"| 正常样本正式指标 | {normal} | 原版证据达到建议线 |",
        f"| 低样本正式指标 | {active_low} | 达到最低线但未达到建议线，仍参与正式判定 |",
        f"| 略过正式判定指标 | {observed} | 原版证据低于最低线，不参与通过和评分 |",
        f"| 候选侧未判定指标 | {summary['insufficient_or_error_instances']} | FORMAL样本不足或计算异常 |",
        "",
        "## 五、最终结论",
        "",
        f"> **{summary['conclusion']} · {grade} · {GRADE_NAMES[grade]} · 综合分{score_text(summary['composite_score'])}**",
        "",
        overall,
        "",
        f"当前总等级和综合分只使用{score_scope}；N/J/P/B各分类分单独展示，未授权跨分类权重前不得把它们合成为四类总分。",
        "",
        "---",
        "",
        "等级：S 高度一致 · A 稳定一致 · B 基本一致 · C 最低通过 · F 不通过 · U 无法判定",
        "",
        "“略过”只表示原版证据不足，无法承担正式判定；指标没有被删除，并已在本报告中完整披露。",
        "",
    ]
    return "\n".join(lines)


def atomic_write_text(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(content)
        temporary = Path(handle.name)
    temporary.replace(path)


def validate_report_paths(task_root, input_path, contract_path, result_path, report_path, manifest_path):
    expected = [
        (input_path, "artifacts/01-input-profile/input_manifest.json"),
        (contract_path, "artifacts/02-metric-matching/metric_contract.json"),
        (result_path, "artifacts/04-alignment/formal_result.json"),
        (report_path, "交付物/报告文档/对齐报告.md"),
        (manifest_path, "交付物/报告文档/report_manifest.json"),
    ]
    for actual, relative in expected:
        if actual.resolve() != (task_root / relative).resolve():
            raise SystemExit(f"正式报告路径必须为{relative}: {actual}")


def write_report_manifest(task_root, input_path, contract_path, result_path, report_path, manifest_path):
    expected = [
        (input_path, "artifacts/01-input-profile/input_manifest.json"),
        (contract_path, "artifacts/02-metric-matching/metric_contract.json"),
        (result_path, "artifacts/04-alignment/formal_result.json"),
        (report_path, "交付物/报告文档/对齐报告.md"),
    ]
    manifest = {
        "schema_version": "slot-alignment.alignment-report-manifest.v6",
        "report_contract_version": "slot-alignment.report.v6",
        "task_id": task_root.name,
        "source_files": [
            {"path": relative, "sha256": sha256_file(actual)}
            for actual, relative in expected[:3]
        ],
        "report_file": {"path": expected[3][1], "sha256": sha256_file(report_path)},
        "placeholders_resolved": True,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    atomic_write_text(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description="生成唯一的人类可读Slot对齐报告")
    parser.add_argument("--input-manifest", required=True)
    parser.add_argument("--contract", required=True)
    parser.add_argument("--result", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--task-root", help="正式交付时提供任务根目录，并同时生成report_manifest.json")
    args = parser.parse_args()
    input_path, contract_path, result_path, output = map(Path, (args.input_manifest, args.contract, args.result, args.output))
    input_manifest, contract, result = load_json(input_path), load_json(contract_path), load_json(result_path)
    task_root = Path(args.task_root).resolve() if args.task_root else None
    manifest_path = task_root / "交付物/报告文档/report_manifest.json" if task_root else None
    if task_root:
        if input_manifest["task_id"] != task_root.name:
            raise SystemExit(f"任务根目录名必须等于task_id: {task_root.name} != {input_manifest['task_id']}")
        validate_report_paths(task_root, input_path, contract_path, result_path, output, manifest_path)
    atomic_write_text(
        output,
        render(input_manifest, contract, result, load_json(LIBRARY_PATH), load_json(EVALUATION_POLICY_PATH)),
    )
    if task_root:
        write_report_manifest(task_root, input_path, contract_path, result_path, output, manifest_path)
    print(output)


if __name__ == "__main__":
    main()
