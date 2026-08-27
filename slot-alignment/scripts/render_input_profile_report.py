#!/usr/bin/env python3
import argparse
import hashlib
import json
import sys
from pathlib import Path

from report_common import detail_rows, fmt, labeled_detail_rows, table, validate_preflight_input_confirmation


def load(path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(items, fields):
    result = []
    for item in items or []:
        if isinstance(item, dict):
            result.append([item.get(field) for field in fields])
        else:
            result.append([item] + [None] * (len(fields) - 1))
    return result


def render(manifest, profile, authority, source_hashes):
    scope = manifest.get("scope", {})
    mechanics = profile.get("mechanics", [])
    required = [x for x in mechanics if x.get("status") in {"必需", "适用"}]
    params = authority.get("parameters", [])
    allowed = [x for x in params if x.get("authorization_status", x.get("status")) in {"已授权", "可调", "允许"}]
    evidence = manifest.get("evidence", [])
    excluded = manifest.get("excluded_evidence", manifest.get("excluded_inputs", []))
    samples = manifest.get("source_samples", manifest.get("samples", []))
    shares = manifest.get("component_rtp_shares", [])
    gates = manifest.get("data_gates", [])
    qualification = manifest.get("script_qualification", {})
    preflight = manifest.get("preflight_decision_gate", {})
    input_confirmation = manifest.get("preflight_input_confirmation", {})
    sample_confirmation = input_confirmation.get("sample_count", {})
    script_confirmation = input_confirmation.get("python_script", {})
    certification = qualification.get("user_certification", {})
    strict_contract = manifest.get("report_contract_version") == "slot-alignment.reports.v3.3"
    input_confirmation_errors = validate_preflight_input_confirmation(manifest)
    confirmation_blockers = [{
        "id": f"preflight-input-{index:02d}",
        "reason": error,
        "owner": "用户/阶段1",
        "recovery_action": "在preflight完成样本数或Python脚本身份确认并重新生成阶段1报告",
        "return_stage": "preflight",
    } for index, error in enumerate(input_confirmation_errors, 1)]
    blockers = manifest.get("blockers", []) + profile.get("gaps", []) + authority.get("conflicts", []) + confirmation_blockers
    certification_ready = (
        certification.get("status") == "通过"
        and certification.get("certified_by") == "user"
        and bool(certification.get("evidence_sha256"))
        and qualification.get("certified_execution_path") == "python"
        and qualification.get("certification_method") == "user_direct"
        and certification.get("certified_script_sha256") == manifest.get("hashes", {}).get("simulation_script")
        and str(manifest.get("paths", {}).get("simulation_script", "")).endswith(".py")
    )
    preflight_ready = (
        not strict_contract
        or preflight.get("status") == "通过"
        and preflight.get("metric_library_gap_count") == 0
        and preflight.get("extension_decision_status") in {"无需扩展", "已完成"}
    )
    input_confirmation_ready = not strict_contract or not input_confirmation_errors
    ready = all(x.get("status") == "已完成" for x in (manifest, profile, authority)) and profile.get("semantic_gap_count", 0) == 0 and not blockers and input_confirmation_ready and preflight_ready and (certification_ready or not strict_contract)
    tree = profile.get("mechanic_tree") or "\n".join(f"- {x.get('mechanic_id', '未命名')}：{x.get('name_zh', '—')}" for x in mechanics) or "- 无已识别玩法节点"
    input_summary_rows, input_path_rows = [], []
    path_purposes = {
        "workspace_root": "任务工作区",
        "slot_docs_root": "原版资料根目录",
        "server_root": "服务端只读取证",
        "runtime": "候选基线",
        "simulation_script": "阶段2至FORMAL执行",
    }
    for index, (key, path) in enumerate(manifest.get("paths", {}).items(), 1):
        ref = f"P{index:02d}"
        input_summary_rows.append([ref, key, "—", "合格", path_purposes.get(key, "阶段1输入")])
        input_path_rows.append([ref, path, manifest.get("hashes", {}).get(key)])
    offset = len(input_summary_rows)
    for index, item in enumerate(evidence, offset + 1):
        ref = f"P{index:02d}"
        if isinstance(item, dict):
            input_summary_rows.append([ref, item.get("type"), item.get("version"), item.get("qualification"), item.get("purpose")])
            input_path_rows.append([ref, item.get("path"), item.get("sha256")])
        else:
            input_summary_rows.append([ref, item, "—", "待确认", "证据输入"])
            input_path_rows.append([ref, item, "—"])
    excluded_summary_rows, excluded_path_rows = [], []
    for index, item in enumerate(excluded, 1):
        ref = f"X{index:02d}"
        if isinstance(item, dict):
            excluded_summary_rows.append([ref, item.get("type"), item.get("status"), item.get("reason"), item.get("impact")])
            excluded_path_rows.append([ref, item.get("path", item.get("id"))])
        else:
            excluded_summary_rows.append([ref, item, "已排除", "未提供结构化原因", "待确认"])
            excluded_path_rows.append([ref, item])
    target_source_rows = [["T01", field, value] for field, value in detail_rows(manifest.get("target_rtp_source", "input_manifest.scope"), "来源")]
    sample_summary_rows, sample_evidence_rows = [], []
    for index, item in enumerate(samples, 1):
        ref = f"B{index:02d}"
        if isinstance(item, dict):
            sample_summary_rows.append([item.get("batch_id"), item.get("paid_entry_count"), item.get("status"), item.get("unit"), item.get("qualification"), ref])
            sample_evidence_rows.extend([[ref, field, value] for field, value in detail_rows(item.get("evidence"), "证据")])
        else:
            sample_summary_rows.append([item, "—", "无法判定", "—", "不合格", ref])
            sample_evidence_rows.append([ref, "证据", "未提供结构化证据"])
    sample_confirmation_rows = [
        ["发现数据源", sample_confirmation.get("discovered_source_count"), "必须等于source_samples条数"],
        ["发现付费入口", sample_confirmation.get("discovered_entry_count"), "必须等于source_samples入口数合计"],
        ["source_samples SHA-256", sample_confirmation.get("source_samples_sha256"), "绑定规范化source_samples JSON"],
        ["用户要求重新统计", sample_confirmation.get("recount_requested"), "用户要求时必须完整处理全部已发现源"],
        ["重新统计范围", sample_confirmation.get("recount_scope"), "固定为all_discovered_sources"],
        ["重新统计状态", sample_confirmation.get("recount_status"), "要求重算时必须为已完成"],
        ["全部已发现源已处理", sample_confirmation.get("all_discovered_sources_processed"), "要求重算时必须为是"],
        ["已处理源数量", sample_confirmation.get("processed_source_count"), "要求重算时必须等于发现源数量"],
        ["重算有效入口", sample_confirmation.get("recounted_entry_count"), "要求重算时必须有最终结果"],
        ["最终有效入口", sample_confirmation.get("effective_entry_count"), "未重算取发现总数，重算取重算结果"],
        ["用户确认入口", sample_confirmation.get("user_confirmed_entry_count"), "必须等于最终有效入口"],
        ["输入确认状态", input_confirmation.get("status"), "必须通过"],
    ]
    sample_confirmation_evidence_rows = [
        ["Q01", "确认人", input_confirmation.get("confirmed_by")],
        ["Q01", "确认时间", input_confirmation.get("confirmed_at")],
        ["Q01", "确认证据路径", input_confirmation.get("confirmation_evidence_path")],
        ["Q01", "确认证据SHA-256", input_confirmation.get("confirmation_evidence_sha256")],
        ["Q02", "重算结果路径", sample_confirmation.get("recount_result_path")],
        ["Q02", "重算结果SHA-256", sample_confirmation.get("recount_result_sha256")],
    ]
    share_summary_rows, share_evidence_rows = [], []
    for index, item in enumerate(shares, 1):
        ref = f"C{index:02d}"
        if isinstance(item, dict):
            share_summary_rows.append([item.get("scope"), item.get("original_component_share"), item.get("original_absolute_rtp_diagnostic"), item.get("sample_count"), ref, item.get("target_usage")])
            share_evidence_rows.extend([[ref, field, value] for field, value in detail_rows(item.get("source_evidence"), "证据")])
        else:
            share_summary_rows.append([item, "—", "—", "—", ref, "无法判定"])
            share_evidence_rows.append([ref, "证据", "未提供结构化证据"])
    mechanic_summary_rows, mechanic_attribute_rows, mechanic_evidence_rows = [], [], []
    for item in mechanics:
        mechanic_id = item.get("mechanic_id")
        mechanic_summary_rows.append([mechanic_id, item.get("name_zh"), item.get("parent_id"), item.get("scope"), item.get("required", item.get("status")), item.get("status"), item.get("confidence", item.get("confidence_status"))])
        mechanic_attribute_rows.extend([[mechanic_id, field, value] for field, value in detail_rows(item.get("attributes"))])
        mechanic_evidence_rows.extend([[mechanic_id, field, value] for field, value in detail_rows(item.get("evidence"))])
    certification_summary_rows = [[
        qualification.get("certification_method"), certification.get("certified_by"),
        qualification.get("certified_execution_path"), certification.get("status"), "V01",
    ]]
    certification_evidence_rows = [["V01", field, value] for field, value in detail_rows({
        "evidence_path": certification.get("evidence_path"),
        "evidence_sha256": certification.get("evidence_sha256"),
        "certified_script_sha256": certification.get("certified_script_sha256"),
        "approved_at": certification.get("approved_at"),
    })]
    certification_scope_rows = []
    for index, item in enumerate(certification.get("certified_scope", []), 1):
        certification_scope_rows.append([item, "用户直接确认", "通过", f"V{index:02d}"])
    script_confirmation_rows = [
        ["Python脚本文件名", script_confirmation.get("confirmed_name"), "必须等于执行路径basename"],
        ["Python脚本绝对路径", script_confirmation.get("confirmed_path"), "必须等于paths.simulation_script且为绝对.py路径"],
        ["Python脚本SHA-256", script_confirmation.get("confirmed_sha256"), "必须等于hashes.simulation_script"],
        ["脚本身份确认状态", script_confirmation.get("status"), "必须通过"],
    ]
    parameter_summary_rows, parameter_path_rows, parameter_metric_rows, parameter_detail_rows = [], [], [], []
    for index, item in enumerate(params, 1):
        ref = f"A{index:02d}"
        parameter_summary_rows.append([ref, item.get("type"), item.get("range", item.get("current")), item.get("authorization_status", item.get("status")), item.get("control_cluster")])
        parameter_path_rows.append([ref, item.get("path")])
        parameter_metric_rows.extend([[ref, field, value] for field, value in detail_rows(item.get("affected_metrics"), "影响指标")])
        parameter_detail_rows.extend(labeled_detail_rows(ref, {"约束": item.get("constraints"), "证据": item.get("evidence")}))
    gate_summary_rows, gate_evidence_rows = [], []
    for index, item in enumerate(gates, 1):
        ref = f"G{index:02d}"
        if isinstance(item, dict):
            gate_summary_rows.append([item.get("gate_id"), item.get("requirement"), item.get("status"), ref, item.get("failure_impact")])
            gate_evidence_rows.extend([[ref, field, value] for field, value in detail_rows(item.get("evidence"), "证据")])
        else:
            gate_summary_rows.append([item, "—", "无法判定", ref, "阻塞"])
            gate_evidence_rows.append([ref, "证据", "未提供结构化证据"])
    lines = [
        "# 阶段1-资料确认与玩法画像", "",
        "> 本报告必须由`render_input_profile_report.py`根据阶段1三份机器JSON确定性生成；任何手工删节都会在阶段转换门禁中失败。", "",
        "## 一、首页结论与阶段准入", "",
        table(["项目", "结果", "判定依据"], [
            ["任务ID", manifest.get("task_id"), "三份阶段1机器JSON必须一致"],
            ["游戏 / 模式 / RTP组", f"{scope.get('game_code', '')} / {scope.get('mode', '')} / {scope.get('rtp_group', '')}", "任务作用域"],
            ["阶段状态", "通过" if ready else "阻塞", "资料、画像、权限、缺口联合判定"],
            ["资料状态", manifest.get("status"), "input_manifest.json"],
            ["样本与脚本确认", input_confirmation.get("status", "不适用"), "preflight_input_confirmation"],
            ["脚本资格", qualification.get("status"), "用户直接认证"],
            ["必需玩法节点", f"{len(required)} / {profile.get('required_node_count', len(required))}", "game_profile.json"],
            ["语义缺口", profile.get("semantic_gap_count", 0), "缺口必须为0"],
            ["授权参数", len(allowed), "parameter_authority.json"],
            ["阶段2准入", "允许" if ready else "禁止", "本阶段全部门禁"],
        ]), "",
        "## 二、任务范围、权威目标与统计口径", "",
        "### 2.1 任务作用域", "", table(["字段", "值", "约束"], [
            ["game_code", scope.get("game_code"), "不得跨游戏"], ["mode", scope.get("mode"), "不得混入其他模式"],
            ["rtp_group", scope.get("rtp_group"), "不得混入其他RTP组"],
        ]), "",
        "### 2.2 权威RTP与目标来源", "", table(["目标项", "值"], detail_rows(scope.get("target_rtp"), "权威总RTP")), "", table(["项目", "内容", "证据ID/依据"], [
            ["权威总RTP来源", "见来源明细", "T01"],
            ["原版绝对组件RTP", "仅诊断", "不得直接作为组件目标"],
            ["组件目标方法", "原版贡献占比 × 权威总RTP", "阶段2密封"],
        ]), "", table(["来源ID", "来源项", "路径/标识"], target_source_rows), "",
        "### 2.3 完整付费入口与金额口径", "", table(["口径项", "定义", "证据/字段"], [
            ["统计单位", manifest.get("paid_entry_definition", "一次真实扣款至恢复可再次扣款状态的完整入口链"), "协议状态链"],
            ["总投注", manifest.get("bet_basis", "入口实际扣款"), "不得混用展示投注"],
            ["总派奖", manifest.get("payout_basis", "入口派奖 + 全部后续Feature派奖 + collect"), "完整链聚合"],
            ["状态链", manifest.get("state_chain", "entry → feature/retrigger → collect → ready"), "原始协议链"],
            ["定向样本", manifest.get("directed_sample_policy", "不得混入总体指标"), "样本资格门禁"],
        ]), "",
        "## 三、输入资料与密封清单", "",
        "### 3.1 合格输入", "", table(["资料ID", "类型/键", "版本", "资格", "用途"], input_summary_rows), "", table(["资料ID", "路径", "SHA-256"], input_path_rows), "",
        "### 3.2 排除输入与原因", "", table(["对象ID", "对象", "状态", "排除原因", "影响"], excluded_summary_rows), "", table(["对象ID", "路径/标识"], excluded_path_rows), "",
        "## 四、原版样本与目标画像", "",
        "### 4.1 样本资格与批次", "", table(["批次", "入口数", "完成状态", "入口口径", "资格", "证据ID"], sample_summary_rows), "", table(["证据ID", "证据项", "路径/标识"], sample_evidence_rows), "", table(["样本确认项", "当前值", "约束"], sample_confirmation_rows), "", table(["证据ID", "证据项", "路径/标识"], sample_confirmation_evidence_rows), "", "> 用户要求重新统计时，必须完整处理全部已发现源；历史局部锁或抽样结果不能作为全量重算结果。", "",
        "### 4.2 RTP组件贡献占比与诊断值", "", table(["组件作用域", "原版贡献占比", "原版绝对RTP诊断", "样本", "证据ID", "阶段2用途"], share_summary_rows), "", table(["证据ID", "证据项", "路径/标识"], share_evidence_rows), "",
        "> 贡献占比必须合计为1；绝对组件RTP只用于诊断，阶段2用占比映射权威总RTP。", "",
        "## 五、玩法画像", "",
        "### 5.1 玩法树", "", "字段：玩法层级、mechanic_id、中文名。", "", tree, "",
        "### 5.2 玩法节点明细", "", table(["mechanic_id", "中文名", "父节点", "作用域", "必需性", "状态", "置信状态"], mechanic_summary_rows), "", table(["mechanic_id", "属性", "值"], mechanic_attribute_rows), "", table(["mechanic_id", "证据项", "证据"], mechanic_evidence_rows), "",
        "## 六、模拟脚本与执行链资格", "",
        "### 6.1 Python脚本用户直接认证", "",
        f"认证方式：{fmt(qualification.get('certification_method'))}；认证人：{fmt(certification.get('certified_by'))}；执行路径：{fmt(qualification.get('certified_execution_path'))}。", "",
        table(["脚本确认项", "确认值", "绑定要求"], script_confirmation_rows), "", table(["认证方式", "认证人", "执行路径", "状态", "证据ID"], certification_summary_rows), "", table(["证据ID", "证据项", "路径/标识"], certification_evidence_rows), "",
        "### 6.2 状态链、结算与封顶证据", "", table(["认证范围", "确认方式", "状态", "证据ID"], certification_scope_rows), "", table(["证据ID", "证据项", "路径/标识"], certification_evidence_rows), "",
        "## 七、参数权限与控制拓扑", "",
        "### 7.1 授权参数", "", table(["参数ID", "类型", "当前值/范围", "授权状态", "控制簇"], parameter_summary_rows), "", table(["参数ID", "参数路径"], parameter_path_rows), "", table(["参数ID", "指标项", "影响指标"], parameter_metric_rows), "", table(["参数ID", "详情项", "内容"], parameter_detail_rows), "",
        "### 7.2 禁止修改项", "", table(["禁止类别", "原因", "执行要求"], [[x, "改变玩法或公共语义", "发现需求即停止并请求扩权"] for x in authority.get("forbidden_categories", [])]), "",
        "## 八、数据门禁、缺口与风险", "", table(["门禁/风险", "要求", "当前状态", "证据ID", "失败影响"], gate_summary_rows), "", table(["证据ID", "证据项", "路径/标识"], gate_evidence_rows), "", table(["开工前决策项", "当前值", "要求"], [
            ["样本与脚本确认", input_confirmation.get("status", "不适用"), "v3.3正式执行前必须通过"],
            ["决策窗口", preflight.get("business_decision_window"), "必须为preflight"],
            ["指标库缺口", preflight.get("metric_library_gap_count"), "正式执行前必须为0"],
            ["扩展决策", preflight.get("extension_decision_status"), "无需扩展或已完成"],
            ["开工前门禁", preflight.get("status"), "必须通过"],
        ]), "",
        "## 九、阻塞与恢复动作", "", table(["阻塞ID", "原因", "责任方", "恢复动作", "恢复后返回阶段"], rows(blockers, ["id", "reason", "owner", "recovery_action", "return_stage"])), "",
        "## 十、阶段2准入结论", "", table(["条件", "状态", "结论"], [
            ["资料、版本和hash已密封", manifest.get("status"), "必须已完成"], ["玩法语义无缺口", profile.get("semantic_gap_count", 0), "必须为0"],
            ["参数权限无冲突", authority.get("status"), "必须已完成"], ["样本与脚本确认", input_confirmation.get("status", "不适用"), "v3.3必须在开工前完成"], ["指标库扩展决策", preflight.get("status"), "必须在开工前完成"], ["最终准入", "允许" if ready else "禁止", "禁止时不得开始指标匹配"],
        ]), "",
        "## 十一、版本、Hash与复算", "", table(["对象", "Schema/版本", "SHA-256"], [
            ["input_manifest.json", manifest.get("schema_version"), source_hashes.get("input_manifest")], ["game_profile.json", profile.get("schema_version"), source_hashes.get("game_profile")],
            ["parameter_authority.json", authority.get("schema_version"), source_hashes.get("parameter_authority")], ["玩法语义目录", profile.get("mechanics_catalog", {}).get("version"), profile.get("mechanics_catalog", {}).get("sha256")],
        ]), "", "复算命令：", "", "```bash", "<python_bin> <skill_root>/scripts/render_input_profile_report.py --artifacts <artifacts> --output <report_dir>/阶段1-资料确认与玩法画像.md", "```", ""
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="确定性生成阶段1中文报告")
    parser.add_argument("--artifacts", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        base = args.artifacts / "01-input-profile"
        paths = {"input_manifest": base / "input_manifest.json", "game_profile": base / "game_profile.json", "parameter_authority": base / "parameter_authority.json"}
        data = {k: load(v) for k, v in paths.items()}
        task_ids = {x.get("task_id") for x in data.values() if x.get("task_id")}
        if len(task_ids) != 1:
            raise ValueError("阶段1三份机器JSON的task_id不一致")
        text = render(data["input_manifest"], data["game_profile"], data["parameter_authority"], {k: sha(v) for k, v in paths.items()})
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
        print(json.dumps({"status": "通过", "output": str(args.output)}, ensure_ascii=False))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "失败", "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
