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
    certification = qualification.get("server_flow_certification", {})
    server_flow_policy = manifest.get("server_flow_policy", {})
    chains = qualification.get("consistency_checks", qualification.get("evidence", []))
    blockers = manifest.get("blockers", []) + profile.get("gaps", []) + authority.get("conflicts", [])
    v26 = manifest.get("report_contract_version") == "slot-alignment.reports.v2.6"
    certification_ready = (
        certification.get("status") == "通过"
        and certification.get("batch_count") == 1
        and bool(certification.get("critical_state_chains"))
        and bool(certification.get("evidence_sha256"))
        and qualification.get("certified_execution_path")
        and bool(qualification.get("consistency_checks"))
        and all(item.get("status") in {"通过", "一致"} for item in qualification.get("consistency_checks", []))
        and bool(qualification.get("semantic_checks"))
        and all(item.get("status") == "通过" for item in qualification.get("semantic_checks", []))
    )
    ready = all(x.get("status") == "已完成" for x in (manifest, profile, authority)) and profile.get("semantic_gap_count", 0) == 0 and not blockers and (certification_ready or not v26)
    tree = profile.get("mechanic_tree") or "\n".join(f"- {x.get('mechanic_id', '未命名')}：{x.get('name_zh', '—')}" for x in mechanics) or "- 无已识别玩法节点"
    path_rows = [[k, v, manifest.get("hashes", {}).get(k), "合格"] for k, v in manifest.get("paths", {}).items()]
    evidence_rows = rows(evidence, ["type", "path", "version", "sha256", "qualification", "purpose"])
    if evidence_rows:
        path_rows.extend(evidence_rows)
    lines = [
        "# 阶段1-资料确认与玩法画像", "",
        "> 本报告必须由`render_input_profile_report.py`根据阶段1三份机器JSON确定性生成；任何手工删节都会在阶段转换门禁中失败。", "",
        "## 一、首页结论与阶段准入", "",
        table(["项目", "结果", "判定依据"], [
            ["任务ID", manifest.get("task_id"), "三份阶段1机器JSON必须一致"],
            ["游戏 / 模式 / RTP组", f"{scope.get('game_code', '')} / {scope.get('mode', '')} / {scope.get('rtp_group', '')}", "任务作用域"],
            ["阶段状态", "通过" if ready else "阻塞", "资料、画像、权限、缺口联合判定"],
            ["资料状态", manifest.get("status"), "input_manifest.json"],
            ["脚本资格", qualification.get("status"), "一致性证据"],
            ["必需玩法节点", f"{len(required)} / {profile.get('required_node_count', len(required))}", "game_profile.json"],
            ["语义缺口", profile.get("semantic_gap_count", 0), "缺口必须为0"],
            ["授权参数", len(allowed), "parameter_authority.json"],
            ["阶段2准入", "允许" if ready else "禁止", "本阶段全部门禁"],
        ]), "",
        "## 二、任务范围、权威目标与统计口径", "",
        "### 2.1 任务作用域", "", table(["字段", "值", "约束"], [
            ["game_code", scope.get("game_code"), "不得跨游戏"], ["mode", scope.get("mode"), "不得混入其他模式"],
            ["rtp_group", scope.get("rtp_group"), "不得混入其他RTP组"], ["target_rtp", scope.get("target_rtp"), "必须来自外部权威来源"],
        ]), "",
        "### 2.2 权威RTP与目标来源", "", table(["项目", "内容", "证据"], [
            ["权威总RTP目标", scope.get("target_rtp"), manifest.get("target_rtp_source", "input_manifest.scope")],
            ["原版绝对组件RTP", "仅诊断", "不得直接作为组件目标"],
            ["组件目标方法", "原版贡献占比 × 权威总RTP", "阶段2密封"],
        ]), "",
        "### 2.3 完整付费入口与金额口径", "", table(["口径项", "定义", "证据/字段"], [
            ["统计单位", manifest.get("paid_entry_definition", "一次真实扣款至恢复可再次扣款状态的完整入口链"), "协议状态链"],
            ["总投注", manifest.get("bet_basis", "入口实际扣款"), "不得混用展示投注"],
            ["总派奖", manifest.get("payout_basis", "入口派奖 + 全部后续Feature派奖 + collect"), "完整链聚合"],
            ["状态链", manifest.get("state_chain", "entry → feature/retrigger → collect → ready"), "原始协议链"],
            ["定向样本", manifest.get("directed_sample_policy", "不得混入总体指标"), "样本资格门禁"],
        ]), "",
        "## 三、输入资料与密封清单", "",
        "### 3.1 合格输入", "", table(["类型/键", "路径", "版本", "SHA-256", "资格", "用途"], path_rows), "",
        "### 3.2 排除输入与原因", "", table(["对象", "路径/标识", "状态", "排除原因", "影响"], rows(excluded, ["type", "path", "status", "reason", "impact"])), "",
        "## 四、原版样本与目标画像", "",
        "### 4.1 样本资格与批次", "", table(["批次", "入口数", "完成状态", "入口口径", "资格", "证据"], rows(samples, ["batch_id", "paid_entry_count", "status", "unit", "qualification", "evidence"])), "",
        "### 4.2 RTP组件贡献占比与诊断值", "", table(["组件作用域", "原版贡献占比", "原版绝对RTP诊断", "样本", "证据", "阶段2用途"], rows(shares, ["scope", "original_component_share", "original_absolute_rtp_diagnostic", "sample_count", "source_evidence", "target_usage"])), "",
        "> 贡献占比必须合计为1；绝对组件RTP只用于诊断，阶段2用占比映射权威总RTP。", "",
        "## 五、玩法画像", "",
        "### 5.1 玩法树", "", "字段：玩法层级、mechanic_id、中文名。", "", tree, "",
        "### 5.2 玩法节点明细", "", table(["mechanic_id", "中文名", "父节点", "作用域", "必需性", "状态", "标准属性", "证据", "置信状态"], [[x.get("mechanic_id"), x.get("name_zh"), x.get("parent_id"), x.get("scope"), x.get("required", x.get("status")), x.get("status"), x.get("attributes"), x.get("evidence"), x.get("confidence", x.get("confidence_status"))] for x in mechanics]), "",
        "## 六、模拟脚本与执行链资格", "",
        "### 6.1 阶段1单次 Server Flow 一致性认证", "",
        f"阶段1认证批次：{fmt(certification.get('batch_count'))}；认证路径：{fmt(qualification.get('certified_execution_path'))}；阶段2至阶段5Server Flow调用：{'禁止' if server_flow_policy.get('stage2_to_stage5_calls_allowed') is False else '未密封'}。", "",
        table(["认证批次", "检查项", "比较对象", "种子/RNG trace", "样本", "结果", "证据"], [[certification.get("certification_id", "cert-001"), *row] for row in rows(chains, ["check_id", "subjects", "seed_or_trace", "sample_count", "status", "evidence"])]), "",
        "### 6.2 状态链、结算与封顶证据", "", table(["语义", "预期", "实测", "状态", "证据"], rows(qualification.get("semantic_checks", []), ["semantic", "expected", "actual", "status", "evidence"])), "",
        "## 七、参数权限与控制拓扑", "",
        "### 7.1 授权参数", "", table(["参数路径", "类型", "当前值/范围", "授权状态", "影响指标", "控制簇", "约束", "证据"], [[x.get("path"), x.get("type"), x.get("range", x.get("current")), x.get("authorization_status", x.get("status")), x.get("affected_metrics"), x.get("control_cluster"), x.get("constraints"), x.get("evidence")] for x in params]), "",
        "### 7.2 禁止修改项", "", table(["禁止类别", "原因", "执行要求"], [[x, "改变玩法或公共语义", "发现需求即停止并请求扩权"] for x in authority.get("forbidden_categories", [])]), "",
        "## 八、数据门禁、缺口与风险", "", table(["门禁/风险", "要求", "当前状态", "证据", "失败影响"], rows(gates, ["gate_id", "requirement", "status", "evidence", "failure_impact"])), "",
        "## 九、阻塞与恢复动作", "", table(["阻塞ID", "原因", "责任方", "恢复动作", "恢复后返回阶段"], rows(blockers, ["id", "reason", "owner", "recovery_action", "return_stage"])), "",
        "## 十、阶段2准入结论", "", table(["条件", "状态", "结论"], [
            ["资料、版本和hash已密封", manifest.get("status"), "必须已完成"], ["玩法语义无缺口", profile.get("semantic_gap_count", 0), "必须为0"],
            ["参数权限无冲突", authority.get("status"), "必须已完成"], ["最终准入", "允许" if ready else "禁止", "禁止时不得开始指标匹配"],
        ]), "",
        "## 十一、版本、Hash与复算", "", table(["对象", "Schema/版本", "SHA-256"], [
            ["input_manifest.json", manifest.get("schema_version"), source_hashes.get("input_manifest")], ["game_profile.json", profile.get("schema_version"), source_hashes.get("game_profile")],
            ["parameter_authority.json", authority.get("schema_version"), source_hashes.get("parameter_authority")], ["玩法语义目录", profile.get("mechanics_catalog", {}).get("version"), profile.get("mechanics_catalog", {}).get("sha256")],
        ]), "", "复算命令：", "", "```bash", "<python_bin> <skill_root>/scripts/render_input_profile_report.py --artifacts <artifacts> --output <artifacts/01-input-profile/阶段1-资料确认与玩法画像.md>", "```", ""
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
