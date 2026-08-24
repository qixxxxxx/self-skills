#!/usr/bin/env python3
import json


REPORT_HEADINGS = {
    1: [
        "# 阶段1-资料确认与玩法画像",
        "## 一、首页结论与阶段准入",
        "## 二、任务范围、权威目标与统计口径",
        "### 2.1 任务作用域",
        "### 2.2 权威RTP与目标来源",
        "### 2.3 完整付费入口与金额口径",
        "## 三、输入资料与密封清单",
        "### 3.1 合格输入",
        "### 3.2 排除输入与原因",
        "## 四、原版样本与目标画像",
        "### 4.1 样本资格与批次",
        "### 4.2 RTP组件贡献占比与诊断值",
        "## 五、玩法画像",
        "### 5.1 玩法树",
        "### 5.2 玩法节点明细",
        "## 六、模拟脚本与执行链资格",
        "### 6.1 阶段1单次 Server Flow 一致性认证",
        "### 6.2 状态链、结算与封顶证据",
        "## 七、参数权限与控制拓扑",
        "### 7.1 授权参数",
        "### 7.2 禁止修改项",
        "## 八、数据门禁、缺口与风险",
        "## 九、阻塞与恢复动作",
        "## 十、阶段2准入结论",
        "## 十一、版本、Hash与复算",
    ],
    2: [
        "# 阶段2-指标匹配报告",
        "## 一、首页结论与阶段准入",
        "## 二、上游画像与目录版本绑定",
        "## 三、玩法节点到指标包映射",
        "## 四、指标合同总表",
        "### 4.1 Core硬指标",
        "### 4.2 100分评分指标",
        "### 4.3 审计指标",
        "## 五、组件RTP贡献占比映射",
        "## 六、硬指标容差政策",
        "## 七、测量、评价与样本资格合同",
        "## 八、控制关系与结构可达性",
        "## 九、指标缺口与扩展提案",
        "## 十、豁免与多Owner审查",
        "## 十一、合同密封、Hash与复算",
        "## 十二、阶段3准入结论",
    ],
    3: [
        "# 阶段3-评分报告",
        "## 一、首页结论与阶段职责",
        "## 二、评分输入与冻结合同",
        "## 三、硬指标门禁",
        "## 四、综合评分组",
        "## 五、逐项100分评分",
        "## 六、低于85分项与差距说明",
        "## 七、阻塞、豁免与不可判定项",
        "## 八、覆盖率与可测性复核",
        "## 九、版本、Hash与复算",
        "## 十、阶段3到阶段4门禁",
    ],
    4: [
        "# 阶段4-数值对齐报告",
        "## 首页结论",
        "### 一句话结论",
        "## 1. 任务范围与依据",
        "### 1.1 对齐范围",
        "### 1.2 权威资料与版本",
        "### 1.3 统计口径",
        "## 2. 硬指标结果",
        "### 2.1 总RTP",
        "### 2.2 中奖率与各类Feature自然触发率",
        "### 2.3 200x以下倍率分布",
        "### 2.4 Sigma",
        "### 2.5 Base / Feature / 其他组件RTP贡献",
        "## 3. 综合评分",
        "### 3.1 评分组汇总",
        "### 3.2 低于85分项",
        "### 3.3 全部评分指标",
        "## 4. 玩法画像与指标覆盖",
        "### 4.1 玩法画像",
        "### 4.2 指标包匹配",
        "### 4.3 覆盖率",
        "## 5. Feature专项结果",
        "## 6. 200x以上长尾与最大中奖审计",
        "## 7. 参数变化",
        "### 7.1 权限与玩法边界确认",
        "## 8. CALIBRATION过程",
        "### 8.1 搜索与预算",
        "### 8.2 候选演进",
        "### 8.3 停止原因",
        "## 9. FORMAL验收",
        "### 9.1 独立性证明",
        "## 10. 豁免、不可达与阻塞",
        "## 11. 最终交付建议",
        "## 12. 版本、Hash与复算",
        "### 12.1 复算命令",
        "## 附录索引",
    ],
    5: [
        "# 阶段5-交付清单",
        "## 一、交付结论与上线资格",
        "## 二、最终结论来源",
        "## 三、必需文件与职责清单",
        "## 四、逐项交付检查与证据",
        "## 五、不可变版本与Hash封存",
        "## 六、限制、风险与上线建议",
        "## 七、回退与复算方法",
        "## 八、历史版本",
    ],
}

TEMPLATE_PATHS = {
    1: "assets/templates/artifacts/01-input-profile/阶段1-资料确认与玩法画像.md",
    2: "assets/templates/artifacts/02-metric-matching/阶段2-指标匹配报告.md",
    3: "assets/templates/artifacts/03-scoring/阶段3-评分报告.md",
    4: "assets/templates/artifacts/04-alignment/阶段4-数值对齐报告.md",
    5: "assets/templates/artifacts/05-delivery/阶段5-交付清单.md",
}

REPORT_CONTRACT_V26 = "slot-alignment.reports.v2.6"


def validate_server_flow_policy(input_manifest, alignment_manifest=None, candidate_archive=None, formal_result=None):
    if input_manifest.get("report_contract_version") != REPORT_CONTRACT_V26:
        return []
    errors = []
    qualification = input_manifest.get("script_qualification", {})
    certification = qualification.get("server_flow_certification", {})
    policy = input_manifest.get("server_flow_policy", {})
    evidence_sha = certification.get("evidence_sha256", "")
    consistency_checks = qualification.get("consistency_checks", [])
    semantic_checks = qualification.get("semantic_checks", [])
    if qualification.get("status") != "通过":
        errors.append("阶段1模拟脚本资格未通过")
    if certification.get("status") != "通过" or certification.get("batch_count") != 1:
        errors.append("阶段1必须且只能有一个有效Server Flow认证批次")
    if not certification.get("critical_state_chains"):
        errors.append("阶段1Server Flow认证未覆盖关键状态链")
    if not certification.get("evidence_path") or len(evidence_sha) != 64:
        errors.append("阶段1Server Flow认证证据hash无效")
    if not consistency_checks or any(item.get("status") not in {"通过", "一致"} for item in consistency_checks):
        errors.append("阶段1Server Flow数值一致性检查不完整或未通过")
    if not semantic_checks or any(item.get("status") != "通过" for item in semantic_checks):
        errors.append("阶段1Server Flow关键状态链语义检查不完整或未通过")
    if not qualification.get("certified_execution_path"):
        errors.append("阶段1未记录已认证模拟执行路径")
    if policy.get("stage1_certification_batches") != 1:
        errors.append("Server Flow政策未密封阶段1单认证批次")
    if policy.get("stage2_to_stage5_calls_allowed") is not False:
        errors.append("Server Flow政策未禁止阶段2至阶段5调用")
    if policy.get("post_delivery_audit_attempts") != 1 or policy.get("post_delivery_audit_affects_status") is not False:
        errors.append("交付后Server Flow审计政策无效")
    if alignment_manifest is not None:
        stage4_policy = alignment_manifest.get("server_flow_policy", {})
        if stage4_policy.get("calibration_calls_allowed") is not False or stage4_policy.get("formal_calls_allowed") is not False:
            errors.append("阶段4未禁止CALIBRATION或FORMAL调用Server Flow")
        if stage4_policy.get("post_delivery_audit_affects_status") is not False:
            errors.append("阶段4未隔离交付后Server Flow审计状态")
    if candidate_archive is not None and candidate_archive.get("server_flow_call_count") != 0:
        errors.append("CALIBRATION阶段存在Server Flow调用")
    if formal_result is not None:
        if formal_result.get("execution_path") != "certified_simulator":
            errors.append("FORMAL未使用阶段1已认证模拟路径")
        if formal_result.get("server_flow_call_count") != 0:
            errors.append("FORMAL阶段存在Server Flow调用")
        if formal_result.get("stage1_server_flow_certification_sha256") != evidence_sha:
            errors.append("FORMAL绑定的阶段1Server Flow认证证据hash无效")
    return errors


def fmt(value):
    if value is None or value == "":
        return "—"
    if isinstance(value, float):
        return f"{value:.9f}".rstrip("0").rstrip(".")
    if isinstance(value, (dict, list)):
        return f"`{json.dumps(value, ensure_ascii=False, sort_keys=True)}`"
    return str(value).replace("|", "\\|").replace("\n", " ")


def table(headers, rows):
    if not rows:
        rows = [["无"] + ["—"] * (len(headers) - 1)]
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines.extend("| " + " | ".join(fmt(v) for v in row) + " |" for row in rows)
    return "\n".join(lines)


def heading_sequence(text):
    return [line.strip() for line in text.splitlines() if line.startswith("#")]


def section_map(text):
    lines = text.splitlines()
    headings = [(index, line.strip()) for index, line in enumerate(lines) if line.startswith("#")]
    result = {}
    for pos, (index, heading) in enumerate(headings):
        end = headings[pos + 1][0] if pos + 1 < len(headings) else len(lines)
        result[heading] = "\n".join(lines[index + 1:end]).strip()
    return result


def validate_structure(text, stage, allow_placeholders=False):
    errors = []
    actual = heading_sequence(text)
    expected = REPORT_HEADINGS[stage]
    if actual != expected:
        errors.append(f"阶段{stage}报告章节顺序与模板契约不一致")
    if not allow_placeholders and "{{" in text:
        errors.append(f"阶段{stage}报告仍含模板占位符")
    lines = text.splitlines()
    heading_lines = [(i, line.strip(), len(line) - len(line.lstrip("#"))) for i, line in enumerate(lines) if line.startswith("#")]
    for pos, (line_index, heading, level) in enumerate(heading_lines):
        end = len(lines)
        for next_index, _, next_level in heading_lines[pos + 1:]:
            if next_level <= level:
                end = next_index
                break
        if not any(line.strip() and not line.startswith("#") for line in lines[line_index + 1:end]):
            errors.append(f"阶段{stage}章节无内容: {heading}")
    return errors


def validate_template_text(text, stage):
    errors = validate_structure(text, stage, allow_placeholders=True)
    sections = section_map(text)
    for heading in REPORT_HEADINGS[stage][1:]:
        body = sections.get(heading, "")
        for marker in ("展示方式：", "必需字段：", "空值规则：", "展示实例：", "```markdown"):
            if marker not in body:
                errors.append(f"阶段{stage}模板章节缺少展示契约标记 {marker}: {heading}")
        for marker in ("展示方式：", "必需字段：", "空值规则："):
            line = next((item for item in body.splitlines() if marker in item), "")
            if not line.split(marker, 1)[-1].strip(" 。"):
                errors.append(f"阶段{stage}模板章节的{marker}没有具体内容: {heading}")
        if "```markdown" in body:
            example = body.split("```markdown", 1)[1].split("```", 1)[0].strip()
            if not example:
                errors.append(f"阶段{stage}模板章节展示实例为空: {heading}")
    return errors


def validate_templates(skill_root):
    errors = []
    for stage, rel in TEMPLATE_PATHS.items():
        path = skill_root / rel
        if not path.is_file():
            errors.append(f"缺少阶段{stage}中文报告模板: {rel}")
            continue
        errors.extend(f"模板错误: {error}" for error in validate_template_text(path.read_text(encoding="utf-8"), stage))
    return errors


def required_fields(template_section):
    for line in template_section.splitlines():
        if "必需字段：" not in line:
            continue
        value = line.split("必需字段：", 1)[1].strip().strip("。")
        if value.startswith("无独立字段"):
            return []
        return [item.strip(" `。") for item in value.split("、") if item.strip()]
    return []


def table_headers(text):
    lines, headers = text.splitlines(), []
    for index in range(len(lines) - 1):
        line, separator = lines[index].strip(), lines[index + 1].strip()
        if not (line.startswith("|") and line.endswith("|") and separator.startswith("|") and separator.endswith("|")):
            continue
        separator_cells = [cell.strip() for cell in separator.strip("|").split("|")]
        if separator_cells and all(cell and set(cell) <= {"-", ":"} for cell in separator_cells):
            headers.append([cell.strip() for cell in line.strip("|").split("|")])
    return headers


def validate_report_against_template(report_text, template_text, stage):
    errors = validate_structure(report_text, stage)
    report_sections, template_sections = section_map(report_text), section_map(template_text)
    for heading in REPORT_HEADINGS[stage][1:]:
        body = report_sections.get(heading, "")
        template_body = template_sections.get(heading, "")
        for field in required_fields(template_body):
            if field not in body:
                errors.append(f"阶段{stage}章节缺少模板必需字段 {field}: {heading}")
        expected_tables, actual_tables = table_headers(template_body), table_headers(body)
        if expected_tables != actual_tables[:len(expected_tables)]:
            errors.append(f"阶段{stage}章节表头名称或顺序与展示实例不一致: {heading}")
    return errors
