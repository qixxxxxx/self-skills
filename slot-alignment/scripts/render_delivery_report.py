#!/usr/bin/env python3
from report_common import table


def render(manifest, checklist):
    files = manifest.get("files", [])
    checks = checklist.get("checks", [])
    passed_files = sum(x.get("valid") is True for x in files if x.get("required"))
    required_files = sum(x.get("required") is True for x in files)
    passed_checks = sum(x.get("status") == "通过" for x in checks)
    report = next((x for x in files if x.get("path") == "04-alignment/阶段4-数值对齐报告.md"), {})
    lines = [
        "# 阶段5-交付清单", "",
        "> 本报告由`seal_delivery.py`在阶段1至4校验通过后确定性生成，并与同版本`delivery_manifest.json`、`delivery_checklist.json`一起封存。", "",
        "## 一、交付结论与上线资格", "", table(["项目", "结果", "含义/通过标准"], [
            ["任务ID", manifest.get("task_id"), "与阶段1至4一致"], ["对齐状态", manifest.get("alignment_status"), "来自阶段4最终FORMAL，不由交付阶段改写"],
            ["交付状态", manifest.get("delivery_status"), "结构、hash和检查全部通过"], ["交付版本", manifest.get("delivery_version"), "不可变dv####"],
            ["必需文件", f"{passed_files} / {required_files}", "100%存在且hash有效"], ["交付检查", f"{passed_checks} / {len(checks)}", "全部通过"],
            ["上线资格", "可进入人工上线评审" if manifest.get("alignment_status") in {"通过", "豁免后通过"} and manifest.get("delivery_status") == "通过" else "不可上线", "交付完整不等于自动发布"],
        ]), "",
        "## 二、最终结论来源", "", table(["对象", "路径", "SHA-256", "职责"], [["阶段4中文报告", report.get("path", "04-alignment/阶段4-数值对齐报告.md"), report.get("sha256"), "最终人类结论、硬指标、评分和FORMAL"], ["交付manifest", "05-delivery/delivery_manifest.json", "由当前文件生成后校验", "机器文件清单与hash"], ["交付checklist", "05-delivery/delivery_checklist.json", "由当前检查生成后校验", "逐项交付门禁"]]), "",
        "## 三、必需文件与职责清单", "", table(["路径", "阶段", "职责", "必需", "有效", "SHA-256"], [[x.get("path"), str(x.get("path", "")).split("/", 1)[0], x.get("role"), x.get("required"), x.get("valid"), x.get("sha256")] for x in files]), "",
        "## 四、逐项交付检查与证据", "", table(["检查ID", "检查名称", "状态", "通过标准", "证据/错误"], [[x.get("check_id"), x.get("name_zh"), x.get("status"), x.get("criterion", "对应结构、状态或hash检查无错误"), x.get("evidence", x.get("errors"))] for x in checks]), "",
        "## 五、不可变版本与Hash封存", "", table(["项目", "值", "规则"], [["版本目录", f"versions/{manifest.get('delivery_version', '')}/", "创建后不得覆盖"], ["生成时间", manifest.get("generated_at"), "带时区ISO 8601"], ["文件数", len(files), "manifest逐项列出"], ["Hash算法", "SHA-256", "任一必需文件变化即失效"], ["根目录清单", "指向当前最新有效版本", "仅在版本目录完整写入后更新"]]), "",
        "## 六、限制、风险与上线建议", "", table(["事项", "结论", "要求"], [
            ["交付与数值通过", "两者独立", "上线以阶段4真实对齐状态为准"], ["配置同步", "未授权", "不得自动覆盖active cache或同步sl-config"],
            ["热更新/发布/Git提交", "未授权", "需要用户另行明确授权"], ["豁免", "以阶段4为准", "上线评审必须显式复核"], ["历史失败证据", "保留", "不得删除或覆盖"],
        ]), "",
        "## 七、回退与复算方法", "", table(["场景", "动作", "返回阶段"], [
            ["输入资料或Runtime hash变化", "重新生成画像和后续全部产物", "阶段1"], ["指标合同/容差/Owner变化", "重新密封合同并评分", "阶段2"],
            ["基线测量或评分变化", "重新生成scorecard、报告和stage3_gate", "阶段3"], ["候选参数或FORMAL变化", "重新CALIBRATION/FORMAL并生成阶段4报告", "阶段4"],
            ["仅交付清单生成失败", "不覆盖最近有效版本，修复后重新封存", "阶段5"],
        ]), "", "```bash", "<python_bin> <skill_root>/scripts/validate_artifacts.py --artifacts <artifacts>", "<python_bin> <skill_root>/scripts/seal_delivery.py --artifacts <artifacts>", "```", "",
        "## 八、历史版本", "", table(["当前版本", "目录", "状态", "说明"], [[manifest.get("delivery_version"), f"versions/{manifest.get('delivery_version', '')}/", manifest.get("delivery_status"), "根目录三份清单与本版本一致；更早版本保持只读"]]), ""
    ]
    return "\n".join(lines)
