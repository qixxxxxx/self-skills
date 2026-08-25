#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

from report_common import detail_rows, table


def render(manifest, checklist):
    files = manifest.get("files", [])
    checks = checklist.get("checks", [])
    passed_files = sum(x.get("valid") is True for x in files if x.get("required"))
    required_files = sum(x.get("required") is True for x in files)
    passed_checks = sum(x.get("status") == "通过" for x in checks)
    report = next((x for x in files if str(x.get("path", "")).endswith("阶段4-数值对齐报告.md")), {})
    source_items = [
        ["S01", "阶段4中文报告", "最终人类结论、硬指标、评分和FORMAL", report.get("path", "交付物/报告文档/rv####/阶段4-数值对齐报告.md"), report.get("sha256")],
        ["S02", "交付manifest", "机器文件清单与hash", "artifacts/05-delivery/delivery_manifest.json", "由当前文件生成后校验"],
        ["S03", "交付checklist", "逐项交付门禁", "artifacts/05-delivery/delivery_checklist.json", "由当前检查生成后校验"],
    ]
    file_summary_rows, file_path_rows = [], []
    for index, item in enumerate(files, 1):
        ref = f"F{index:02d}"
        path = item.get("path")
        file_summary_rows.append([ref, str(path or "").split("/", 1)[0], item.get("role"), item.get("required"), item.get("valid")])
        file_path_rows.append([ref, path, item.get("sha256")])
    check_summary_rows, check_evidence_rows = [], []
    for item in checks:
        check_id = item.get("check_id")
        check_summary_rows.append([check_id, item.get("name_zh"), item.get("status"), item.get("criterion", "对应结构、状态或hash检查无错误")])
        evidence = item.get("evidence") if item.get("evidence") is not None else item.get("errors")
        check_evidence_rows.extend([[check_id, field, value] for field, value in detail_rows(evidence, "证据/错误")])
    lines = [
        "# 阶段5-交付清单", "",
        "> 本报告由`seal_delivery.py`在阶段1至4校验通过后确定性生成；同版本机器manifest与checklist封存在`versions/dv####/`，本报告保存在当前报告目录。", "",
        "## 一、交付结论与上线资格", "", table(["项目", "结果", "含义/通过标准"], [
            ["任务ID", manifest.get("task_id"), "与阶段1至4一致"], ["对齐状态", manifest.get("alignment_status"), "来自阶段4最终FORMAL，不由交付阶段改写"],
            ["交付状态", manifest.get("delivery_status"), "结构、hash和检查全部通过"], ["交付版本", manifest.get("delivery_version"), "不可变dv####"],
            ["必需文件", f"{passed_files} / {required_files}", "100%存在且hash有效"], ["交付检查", f"{passed_checks} / {len(checks)}", "全部通过"],
            ["上线资格", "可进入人工上线评审" if manifest.get("alignment_status") in {"通过", "豁免后通过"} and manifest.get("delivery_status") == "通过" else "不可上线", "交付完整不等于自动发布"],
        ]), "",
        "## 二、最终结论来源", "", table(["来源ID", "对象", "职责"], [[ref, name, role] for ref, name, role, _, _ in source_items]), "", table(["来源ID", "路径", "SHA-256/状态"], [[ref, path, hash_value] for ref, _, _, path, hash_value in source_items]), "",
        "## 三、必需文件与职责清单", "", table(["文件ID", "阶段", "职责", "必需", "有效"], file_summary_rows), "", table(["文件ID", "路径", "SHA-256"], file_path_rows), "",
        "## 四、逐项交付检查与证据", "", table(["检查ID", "检查名称", "状态", "通过标准"], check_summary_rows), "", table(["检查ID", "证据/错误项", "内容"], check_evidence_rows), "",
        "## 五、不可变版本与Hash封存", "", table(["项目", "值", "规则"], [["版本目录", f"versions/{manifest.get('delivery_version', '')}/", "创建后不得覆盖"], ["生成时间", manifest.get("generated_at"), "带时区ISO 8601"], ["文件数", len(files), "manifest逐项列出"], ["Hash算法", "SHA-256", "任一必需文件变化即失效"], ["根目录机器清单", "指向当前最新有效版本", "仅在版本目录完整写入后更新"]]), "",
        "## 六、限制、风险与上线建议", "", table(["事项", "结论", "要求"], [
            ["交付与数值通过", "两者独立", "上线以阶段4真实对齐状态为准"], ["配置同步", "未授权", "不得自动覆盖active cache或同步sl-config"],
            ["热更新/发布/Git提交", "未授权", "需要用户另行明确授权"], ["交付后Server Flow审计", "封存后单次执行", "结果只警告，不影响FORMAL、封包或本清单状态"],
            ["豁免", "以阶段4为准", "上线评审必须显式复核"], ["历史失败证据", "保留", "不得删除或覆盖"],
        ]), "",
        "## 七、回退与复算方法", "", table(["场景", "动作", "返回阶段"], [
            ["输入资料或Runtime hash变化", "重新生成画像和后续全部产物", "阶段1"], ["指标合同/容差/Owner变化", "重新密封合同并评分", "阶段2"],
            ["基线测量或评分变化", "重新生成scorecard、报告和stage3_gate", "阶段3"], ["候选参数或FORMAL变化", "重新CALIBRATION/FORMAL并生成阶段4报告", "阶段4"],
            ["仅交付清单生成失败", "不覆盖最近有效版本，修复后重新封存", "阶段5"],
        ]), "", "```bash", "<python_bin> <skill_root>/scripts/validate_artifacts.py --artifacts <artifacts> --reports <report_dir>", "<python_bin> <skill_root>/scripts/seal_delivery.py --artifacts <artifacts> --reports <report_dir> --formal-runtime <formal_runtime>", "```", "",
        "## 八、历史版本", "", table(["当前版本", "目录", "状态", "说明"], [[manifest.get("delivery_version"), f"versions/{manifest.get('delivery_version', '')}/", manifest.get("delivery_status"), "根目录两份机器清单与本版本一致；中文清单位于当前报告目录；更早版本保持只读"]]), ""
    ]
    return "\n".join(lines)


def load(path):
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def main():
    parser = argparse.ArgumentParser(description="由交付机器清单生成阶段5中文报告")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--checklist", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render(load(args.manifest), load(args.checklist)), encoding="utf-8")
    print(json.dumps({"status": "通过", "output": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
