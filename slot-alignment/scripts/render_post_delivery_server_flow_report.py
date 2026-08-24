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


def metric_key(item):
    return item.get("metric_id"), item.get("scope")


def normalize_audit(audit):
    if not isinstance(audit, dict):
        return {"execution_status": "异常", "warnings": ["审计JSON根节点不是对象"]}
    return audit


def render(audit, delivery, delivery_manifest_sha256, formal=None, scorecard=None, source_hashes=None):
    audit = normalize_audit(audit)
    formal = formal if isinstance(formal, dict) else {}
    scorecard = scorecard if isinstance(scorecard, dict) else {}
    source_hashes = source_hashes or {}
    raw_comparisons = audit.get("hard_metric_comparisons", [])
    warnings = [str(item) for item in audit.get("warnings", [])] if isinstance(audit.get("warnings", []), list) else ["warnings字段不是数组"]
    if not isinstance(raw_comparisons, list):
        warnings.append("hard_metric_comparisons字段不是数组")
        raw_comparisons = []
    comparisons = []
    for index, item in enumerate(raw_comparisons):
        if isinstance(item, dict):
            comparisons.append(item)
            missing_fields = [name for name in ("metric_id", "scope", "formal_value", "server_flow_value", "difference", "tolerance", "sample_qualification", "status") if name not in item]
            if missing_fields:
                warnings.append(f"硬指标对照第{index + 1}项缺少字段：{','.join(missing_fields)}")
            if item.get("sample_qualification") not in {"有效", "合格"}:
                warnings.append(f"硬指标{item.get('metric_id', '未命名')}样本资格无效")
        else:
            warnings.append(f"硬指标对照第{index + 1}项不是对象")
    formal_hard = formal.get("scorecard", {}).get("hard_gates") if isinstance(formal.get("scorecard"), dict) else None
    required_hard = formal_hard if isinstance(formal_hard, list) and formal_hard else scorecard.get("hard_gates", [])
    required_hard = [item for item in required_hard if isinstance(item, dict)] if isinstance(required_hard, list) else []
    if not required_hard:
        warnings.append("密封FORMAL和阶段3 scorecard均未提供硬指标清单")
    comparisons_by_key = {metric_key(item): item for item in comparisons}
    for item in required_hard:
        key = metric_key(item)
        comparison = comparisons_by_key.get(key)
        if comparison is None:
            warnings.append(f"缺少硬指标对照：{key[0] or '未命名'}@{key[1] or '未记录作用域'}")
            continue
        if comparison.get("formal_value") != item.get("candidate"):
            warnings.append(f"硬指标{key[0]}的FORMAL值未绑定密封结果")
        if comparison.get("tolerance") != item.get("tolerance"):
            warnings.append(f"硬指标{key[0]}的容差未绑定密封合同")
    if not comparisons:
        warnings.append("未生成任何硬指标数值对照")
    if audit.get("attempt_count") != 1:
        warnings.append("Server Flow审计调用次数不是1")
    if audit.get("status_effect") != "无":
        warnings.append("审计错误声明会影响既有状态；实际按无影响处理")
    if audit.get("task_id") != delivery.get("task_id") or audit.get("delivery_version") != delivery.get("delivery_version"):
        warnings.append("审计任务或交付版本绑定不一致")
    if audit.get("delivery_manifest_sha256") != delivery_manifest_sha256:
        warnings.append("交付manifest SHA-256绑定不一致")
    input_hashes = audit.get("input_hashes", {})
    if not isinstance(input_hashes, dict):
        warnings.append("input_hashes字段不是对象")
        input_hashes = {}
    for name in ("server", "runtime", "candidate"):
        value = input_hashes.get(name)
        if not isinstance(value, str) or len(value) != 64:
            warnings.append(f"{name} SHA-256缺失或无效")
    for name, actual_hash in source_hashes.items():
        if input_hashes.get(name) != actual_hash:
            warnings.append(f"{name} SHA-256绑定不一致")
    sample = audit.get("sample", {})
    if not isinstance(sample, dict):
        warnings.append("sample字段不是对象")
        sample = {}
    if not isinstance(sample.get("paid_entry_count"), int) or sample.get("paid_entry_count", 0) <= 0:
        warnings.append("Server Flow审计样本数无效")
    if not sample.get("seed_set_hash"):
        warnings.append("Server Flow审计种子集hash缺失")
    if audit.get("execution_status") != "成功":
        warnings.append(f"Server Flow执行状态：{audit.get('execution_status', '未记录')}")
    for item in comparisons:
        if item.get("status") != "一致":
            warnings.append(f"硬指标{item.get('metric_id', '未命名')}对照状态：{item.get('status', '无法对照')}")
    if audit.get("error"):
        warnings.append(str(audit["error"]))
    conclusion = "审计通过" if not warnings else "警告"
    warning_rows = [["审计警告", item, "仅记录，不改变既有状态"] for item in dict.fromkeys(warnings)]
    lines = [
        "# 交付后Server Flow验证报告", "",
        "> 本报告位于不可变交付包之外，只做单次Server Flow硬指标对照；任何结果都不改变阶段1至5、FORMAL、候选或交付状态。", "",
        "## 一、审计结论与状态隔离", "", table(["项目", "结果", "含义"], [
            ["审计结论", conclusion, "仅用于交付后观察与排查"],
            ["Server Flow执行", audit.get("execution_status"), "单次调用，不自动重试"],
            ["原对齐状态", delivery.get("alignment_status"), "保持不变"],
            ["原交付状态", delivery.get("delivery_status"), "保持不变"],
            ["既有状态影响", "无", "不回写FORMAL、候选、封包或阶段报告"],
        ]), "",
        "> [!WARNING]" if warnings else "> [!NOTE]", "> " + ("；".join(dict.fromkeys(warnings)) if warnings else "本次对照未发现警告；既有交付状态仍保持不变。"), "",
        "## 二、交付版本与输入绑定", "", table(["对象", "值", "校验"], [
            ["任务ID", audit.get("task_id"), "与交付manifest一致" if audit.get("task_id") == delivery.get("task_id") else "警告"],
            ["交付版本", audit.get("delivery_version"), "只读绑定"],
            ["交付manifest SHA-256", audit.get("delivery_manifest_sha256"), "一致" if audit.get("delivery_manifest_sha256") == delivery_manifest_sha256 else "警告"],
            ["调用次数", audit.get("attempt_count"), "固定为1"],
            *[[name, value, "一致" if name in source_hashes and source_hashes.get(name) == value else "已记录" if name not in source_hashes and isinstance(value, str) and len(value) == 64 else "警告"] for name, value in input_hashes.items()],
            ["样本", sample, "只用于本次审计"],
        ]), "",
        "## 三、硬指标数值对照", "", table(["指标", "作用域", "FORMAL", "Server Flow", "差距", "容差", "样本资格", "对照状态"], [[
            item.get("name_zh", item.get("metric_id")), item.get("scope"), item.get("formal_value"), item.get("server_flow_value"),
            item.get("difference"), item.get("tolerance"), item.get("sample_qualification"), item.get("status")
        ] for item in comparisons]), "",
        "## 四、异常与警告", "", table(["类型", "内容", "处置"], warning_rows), "",
        "## 五、不可变性声明", "", table(["对象", "结果", "规则"], [
            ["阶段1至5", "保持原状态", "审计不参与阶段门禁"], ["候选与FORMAL", "保持原状态", "不重新评分、不失效、不回滚"],
            ["交付版本", delivery.get("delivery_version"), "不修改versions/dv####及其hash"], ["交付manifest/checklist", "保持原文件", "审计目录位于artifacts之外"],
        ]), ""
    ]
    return "\n".join(lines), conclusion


def main():
    parser = argparse.ArgumentParser(description="生成交付后Server Flow非阻塞审计报告")
    parser.add_argument("--audit", required=True, type=Path)
    parser.add_argument("--delivery-manifest", required=True, type=Path)
    parser.add_argument("--formal-result", required=True, type=Path)
    parser.add_argument("--scorecard", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        delivery, formal, scorecard = load(args.delivery_manifest), load(args.formal_result), load(args.scorecard)
        try:
            audit = load(args.audit)
        except Exception as exc:
            audit = {"execution_status": "异常", "status_effect": "无", "warnings": [f"审计JSON读取失败：{exc}"], "hard_metric_comparisons": []}
        source_hashes = {"formal_result": sha(args.formal_result), "scorecard": sha(args.scorecard)}
        text, conclusion = render(audit, delivery, sha(args.delivery_manifest), formal, scorecard, source_hashes)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
        print(json.dumps({"status": "通过", "audit_conclusion": conclusion, "status_effect": "无", "output": str(args.output)}, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "失败", "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
