#!/usr/bin/env python3
import copy
import hashlib
import json
import re
from pathlib import Path


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
        "### 6.1 Python脚本用户直接认证",
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
        "## 四、指标清单与详细目标",
        "### 4.1 硬指标",
        "### 4.2 评分指标",
        "### 4.3 审计指标",
        "## 五、组件RTP贡献占比映射",
        "## 六、控制关系与结构可达性",
        "## 七、指标缺口与扩展提案",
        "## 八、豁免与多Owner审查",
        "## 九、合同密封、Hash与复算",
        "## 十、阶段3准入结论",
    ],
    3: [
        "# 阶段3-评分报告",
        "## 一、首页结论与阶段职责",
        "## 二、评分输入与冻结合同",
        "## 三、指标评分详情",
        "### 3.1 硬指标",
        "### 3.2 评分指标",
        "### 3.3 审计指标",
        "## 四、综合评分组",
        "## 五、低于85分项与差距说明",
        "## 六、阻塞、豁免与不可判定项",
        "## 七、覆盖率与可测性复核",
        "## 八、版本、Hash与复算",
        "## 九、阶段3到阶段4门禁",
    ],
    4: [
        "# 阶段4-数值对齐报告",
        "## 首页结论",
        "### 一句话结论",
        "## 1. 任务范围与依据",
        "### 1.1 对齐范围",
        "### 1.2 权威资料与版本",
        "### 1.3 统计口径",
        "## 2. 指标对齐详情",
        "### 2.1 硬指标",
        "### 2.2 评分指标",
        "### 2.3 审计指标",
        "## 3. 综合评分汇总",
        "### 3.1 评分组汇总",
        "### 3.2 低于85分项",
        "## 4. 玩法画像与指标覆盖",
        "### 4.1 玩法画像",
        "### 4.2 指标包匹配",
        "### 4.3 覆盖率",
        "## 5. 参数变化",
        "### 5.1 权限与玩法边界确认",
        "## 6. CALIBRATION过程",
        "### 6.1 搜索与预算",
        "### 6.2 候选演进",
        "### 6.3 停止原因",
        "## 7. FORMAL验收",
        "### 7.1 独立性证明",
        "## 8. 豁免、不可达与阻塞",
        "## 9. 最终交付建议",
        "## 10. 版本、Hash与复算",
        "### 10.1 复算命令",
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
REPORT_CONTRACT_V27 = "slot-alignment.reports.v2.7"
REPORT_CONTRACT_V28 = "slot-alignment.reports.v2.8"
REPORT_CONTRACT_V29 = "slot-alignment.reports.v2.9"
REPORT_CONTRACT_V31 = "slot-alignment.reports.v3.1"
REPORT_CONTRACT_V32 = "slot-alignment.reports.v3.2"
REPORT_CONTRACT_V33 = "slot-alignment.reports.v3.3"
STRICT_REPORT_CONTRACTS = {REPORT_CONTRACT_V26, REPORT_CONTRACT_V27, REPORT_CONTRACT_V28, REPORT_CONTRACT_V29, REPORT_CONTRACT_V31, REPORT_CONTRACT_V32, REPORT_CONTRACT_V33}
METRIC_HEADING_PATTERN = re.compile(r"^#### M\d{2,}\s+.+$")
METRIC_GROUPS = (
    ("hard", "硬指标"),
    ("score", "评分指标"),
    ("audit", "审计指标"),
)
METRIC_CONTAINER_HEADINGS = {
    2: {"### 4.1 硬指标", "### 4.2 评分指标", "### 4.3 审计指标"},
    3: {"### 3.1 硬指标", "### 3.2 评分指标", "### 3.3 审计指标"},
    4: {"### 2.1 硬指标", "### 2.2 评分指标", "### 2.3 审计指标"},
}
METRIC_TABLE_HEADERS = {
    2: {
        ("目标值", "单位", "来源/说明"),
        ("目标下限", "目标上限", "单位", "来源/说明"),
        ("分布项", "目标占比", "单位", "来源/说明"),
        ("目标字段", "目标值", "单位", "来源/说明"),
    },
    3: {
        ("目标值", "单位", "基线值", "差距", "评分/门禁"),
        ("目标下限", "目标上限", "单位", "基线值", "差距", "评分/门禁"),
        ("分布项", "目标占比", "基线占比", "差值（百分点）", "评分/门禁"),
        ("目标字段", "目标值", "单位", "基线值", "差值", "评分/门禁"),
    },
    4: {
        ("目标值", "单位", "基线值", "FORMAL值", "变化/差距", "最终结果"),
        ("目标下限", "目标上限", "单位", "基线值", "FORMAL值", "变化/差距", "最终结果"),
        ("分布项", "目标占比", "基线占比", "FORMAL占比", "差值（百分点）", "最终结果"),
        ("目标字段", "目标值", "单位", "基线值", "FORMAL值", "差值", "最终结果"),
    },
}

SAMPLE_CAPABILITY_TABLE_HEADERS = {
    2: ("条件组", "支持项数", "侧别", "计划样本", "所需样本", "缺口", "状态"),
    3: ("条件组", "支持项数", "侧别", "计划样本", "所需样本", "缺口", "状态"),
    4: ("条件组", "支持项数", "侧别", "合同计划", "FORMAL实际", "所需样本", "缺口", "状态"),
}

METHOD_NAMES = {
    "absolute_error": "绝对差",
    "relative_error": "相对误差",
    "range_error": "目标区间判定",
    "total_variation": "总变差距离（比较整组分布）",
    "mean_absolute_error": "平均绝对差（逐项比较后取平均）",
    "max_absolute_error": "最大绝对差（最偏离字段优先）",
    "grouped_mean_absolute_error": "分组平均绝对差（组内逐项平均后按密封权重汇总）",
    "grouped_total_variation": "分组总变差距离（组内比较后按密封权重汇总）",
    "wasserstein_1d": "一维Wasserstein距离（考虑有序档位相邻程度）",
    "grouped_wasserstein_1d": "分组一维Wasserstein距离（各条件组按密封权重汇总）",
    "audit": "审计核对",
}

UNIT_NAMES = {
    "ratio": "%",
    "probability": "%",
    "distribution": "%（样本占比）",
    "bet_multiple": "倍投注额（x）",
    "spins": "次免费旋转",
    "respins": "次重转",
    "feature_actions": "次主要动作",
    "count": "次",
}

SOURCE_NAMES = {
    "normalized_complete_paid_entry": "原版合格完整付费入口样本",
    "authoritative_contract": "权威目标合同",
    "task_contract": "任务目标合同",
}

LEGACY_METRIC_DISPLAY_DEFAULTS = {
    "core.rtp.total": {
        "description_zh": "衡量玩家每投入100单位投注，长期平均返还多少单位奖金。",
        "usage_scene_zh": "用于确认整款模式的总体返还水平是否落在权威RTP范围内。",
        "target_meaning_zh": "目标值统计全部合格完整付费入口的总派奖÷总实际投注。",
    },
    "core.hit_rate.paid_entry": {
        "description_zh": "衡量一次完整付费入口最终是否产生任意奖金。",
        "usage_scene_zh": "用于判断玩家进入该模式后空手结束的频率，以及整体命中体验。",
        "target_meaning_zh": "目标值统计总奖金大于0的完整付费入口占全部入口的比例。",
    },
    "core.multiplier_distribution.lt200": {
        "description_zh": "衡量完整付费入口的总回报主要落在哪些200倍以下倍率区间。",
        "usage_scene_zh": "用于比较低倍、中倍回报结构，避免只看RTP而忽略常见中奖体验。",
        "target_meaning_zh": "每个目标占比统计该回报倍率区间内的完整付费入口数占200倍以下合格入口的比例。",
    },
    "core.sigma": {
        "description_zh": "衡量单次完整付费入口回报围绕平均值波动得有多大；数值越高，体验越起伏。",
        "usage_scene_zh": "用于判断整体或指定组件的波动强度是否接近原版。",
        "target_meaning_zh": "目标值统计完整付费入口回报倍数的总体标准差。",
    },
    "core.rtp.component_contribution": {
        "description_zh": "衡量某个玩法组件对整局总RTP贡献了多少。",
        "usage_scene_zh": "用于确认入口奖、免费旋转等奖金来源之间的占比结构没有失真。",
        "target_meaning_zh": "目标值统计该组件派奖÷全部完整付费入口实际投注，并按原版贡献占比映射到权威总RTP。",
    },
    "free_spin.length.mean": {
        "description_zh": "衡量一次Feature平均实际进行了多少次免费旋转。",
        "usage_scene_zh": "用于判断Feature节奏是偏短、偏长，及重触发带来的体感变化。",
        "target_meaning_zh": "目标值统计每个合格Feature入口的实际免费旋转次数平均值。",
    },
    "free_spin.retrigger_rate": {
        "description_zh": "衡量免费旋转过程中至少发生一次追加免费旋转的概率。",
        "usage_scene_zh": "用于比较Feature延长机会和玩家对续场的预期。",
        "target_meaning_zh": "目标值统计发生过重触发的Feature入口占全部合格Feature入口的比例。",
    },
    "free_spin.return_distribution": {
        "description_zh": "衡量免费旋转部分的奖金主要落在哪些回报倍率区间。",
        "usage_scene_zh": "用于分辨Feature是经常小奖、偶尔中奖，还是依赖少数高倍结果。",
        "target_meaning_zh": "每个目标占比统计Feature奖金÷触发该Feature的实际投注后，落入对应倍率区间的入口比例。",
    },
    "cascade.depth_distribution": {
        "description_zh": "衡量一次局面通常连续消除多少层后结束。",
        "usage_scene_zh": "用于比较Cascade节奏、连续中奖长度和局面推进感。",
        "target_meaning_zh": "每个目标占比统计最终Cascade深度等于对应层数的合格局面比例。",
    },
    "cascade.continuation_rate_by_step": {
        "description_zh": "衡量已经到达某一层后，还能继续进入下一层Cascade的机会。",
        "usage_scene_zh": "用于定位连续消除在哪一层过早中断或延续过强。",
        "target_meaning_zh": "每个目标值统计已到达当前层的局面中，继续到下一层的条件概率。",
    },
    "modifier.activation_rate": {
        "description_zh": "衡量符合条件的免费旋转局面中，WILD倍率真正大于1倍并参与结算的频率。",
        "usage_scene_zh": "用于判断倍率玩法出现得是否过少或过密。",
        "target_meaning_zh": "目标值统计WILD倍率实际生效的合格局面占全部可生效局面的比例。",
    },
    "modifier.value_distribution": {
        "description_zh": "衡量WILD倍率生效时，实际倍率主要集中在哪些档位。",
        "usage_scene_zh": "用于比较低倍率常见度和高倍率长尾是否接近原版。",
        "target_meaning_zh": "每个目标占比统计记录到的有效WILD倍率事件中，对应倍率档位所占比例。",
    },
    "feature_cycle.zero_return_rate": {
        "description_zh": "衡量一次完整Feature最终没有产生任何Feature奖金的概率。",
        "usage_scene_zh": "用于识别玩家进入Feature后零回报的挫败感是否偏高。",
        "target_meaning_zh": "目标值统计Feature奖金为0的合格Feature入口占比。",
    },
    "feature_cycle.median_return": {
        "description_zh": "衡量典型的一次Feature大约能获得多少倍投注回报；一半结果低于它，一半高于它。",
        "usage_scene_zh": "用于观察普通玩家最常感受到的Feature回报水平，避免平均值被少数大奖拉高。",
        "target_meaning_zh": "目标值统计Feature奖金÷触发投注后的中位数。",
    },
    "feature_cycle.duration_distribution": {
        "description_zh": "衡量初始资源、续命或重置、停止规则和跨步依赖共同作用后，一次完整Feature最终包含多少次主要动作。",
        "usage_scene_zh": "用于比较完整周期过短或过长，并与免费旋转、重转、Hold & Spin或抽奖的局部过程指标交叉定位。",
        "target_meaning_zh": "每个目标占比统计完整Feature最终主要动作总数落入对应实际次数档位的周期比例。",
    },
    "cascade_multiplier.joint_distribution": {
        "description_zh": "同时衡量Cascade深度和实际生效倍率的组合，而不是分别看两个指标。",
        "usage_scene_zh": "用于检查深层Cascade是否搭配了过强或过弱的倍率，识别单项看似正常但组合体验失真的情况。",
        "target_meaning_zh": "每个目标占比统计免费旋转局面中，对应Cascade深度×实际生效倍率组合所占比例。",
    },
    "board.symbol_presence_distribution": {
        "description_zh": "衡量每种符号有多大概率至少在一个完整盘面中出现一次。",
        "usage_scene_zh": "用于识别某些符号长期缺席，或少数符号几乎盘盘出现造成的单调感。",
        "target_meaning_zh": "每个目标值统计含有至少一个对应符号的合格盘面占全部同状态盘面的比例。",
    },
    "board.symbol_cell_share_distribution": {
        "description_zh": "衡量每种符号占全部有效可见格子的比例。",
        "usage_scene_zh": "用于识别总体盘面是否被少数符号占据，即使盘面签名看起来不同也能发现结构偏斜。",
        "target_meaning_zh": "每个目标占比统计对应符号格数除以同状态全部有效可见格数。",
    },
    "board.symbol_count_per_board_distribution": {
        "description_zh": "衡量单个盘面中同一种符号通常出现0个、1个、2个或更多个。",
        "usage_scene_zh": "用于识别某种符号经常整片出现或数量过度固定的问题。",
        "target_meaning_zh": "每个目标值统计在指定符号条件下，单盘数量落入对应档位的盘面比例。",
    },
    "board.symbol_stack_length_distribution": {
        "description_zh": "衡量同一种符号沿密封堆叠方向连续出现1个、2个、3个或更多个的结构。",
        "usage_scene_zh": "用于识别卷轴上长堆叠过密、过少或几乎固定的问题。",
        "target_meaning_zh": "每个目标值统计在指定符号的有效连续段中，对应堆叠长度档位所占比例。",
    },
    "board.generation_concentration": {
        "description_zh": "衡量盘面生成器是否反复使用少数停点窗口、模板或其他稳定生成单元。",
        "usage_scene_zh": "用于定位完整盘面仍较多变化，但每轴窗口或底层模板高度重复的问题。",
        "target_meaning_zh": "目标字段统计每个生成分区的最常见项占比、前五项占比和重复碰撞概率。",
    },
    "cascade.refill_symbol_distribution": {
        "description_zh": "衡量Cascade消除后新补入格子由哪些符号构成。",
        "usage_scene_zh": "用于防止初始盘面正常，但后续补充阶段长期掉落同一批符号。",
        "target_meaning_zh": "每个目标占比统计对应符号在同状态、同Cascade层新补入有效格子中的比例。",
    },
    "settlement.winning_symbol_distribution": {
        "description_zh": "衡量实际中奖结算主要由哪些符号产生。",
        "usage_scene_zh": "用于识别总体中奖率正常，但中奖长期集中在少数符号上的问题。",
        "target_meaning_zh": "每个目标占比统计对应符号中奖事件占全部合格中奖符号事件的比例。",
    },
    "settlement.winning_symbol_scale_joint_distribution": {
        "description_zh": "同时衡量中奖符号和该次中奖规模，判断谁在以多大规模中奖。",
        "usage_scene_zh": "用于识别符号构成和中奖规模分别正常，但二者组合关系失真的问题。",
        "target_meaning_zh": "每个目标占比统计对应中奖符号×实际中奖规模档位组合占全部合格中奖事件的比例。",
    },
    "core.long_tail.audit": {
        "description_zh": "衡量200倍以上高回报结果在各长尾倍率区间中的结构。",
        "usage_scene_zh": "用于审计大奖尾部是否异常集中、缺失或超出预期，不参与普通评分。",
        "target_meaning_zh": "每个目标占比统计全部合格付费入口中，回报落入对应200倍以上长尾倍率桶的比例；回报低于200x的入口在所有长尾桶中计0。",
    },
    "core.max_win.audit": {
        "description_zh": "核对样本观测最大中奖、规则理论最大中奖、封顶值、触顶次数、实际超限事件和超限处理规则。",
        "usage_scene_zh": "用于确认高倍结果、封顶触发和超限处理符合权威规则，不参与普通评分。",
        "target_meaning_zh": "目标对象逐字段记录观测最大值、理论最大值、封顶值、触顶次数、超限事件数及超限规则核对状态。",
        "object_labels": {
            "observed_max": "样本观测最大中奖",
            "theoretical_max": "规则理论最大中奖",
            "cap": "生效封顶值",
            "cap_hit_count": "触发封顶次数",
            "overflow_event_count": "实际超限事件次数",
            "overflow_rule_status": "超限处理规则核对状态",
        },
        "object_units": {
            "observed_max": "倍投注额（x）",
            "theoretical_max": "倍投注额（x）",
            "cap": "倍投注额（x）",
            "cap_hit_count": "次",
            "overflow_event_count": "次",
            "overflow_rule_status": "状态（符合/不符合/无法证明）",
        },
    },
}
LEGACY_METRIC_DISPLAY_DEFAULTS["core.return_distribution.lt200"] = dict(
    LEGACY_METRIC_DISPLAY_DEFAULTS["core.multiplier_distribution.lt200"]
)


def validate_server_flow_policy(input_manifest, alignment_manifest=None, candidate_archive=None, formal_result=None):
    if input_manifest.get("report_contract_version") not in STRICT_REPORT_CONTRACTS - {REPORT_CONTRACT_V33}:
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
    if qualification.get("certified_execution_path") != "python":
        errors.append("阶段2至阶段5的已认证执行路径必须是Python")
    simulation_script = input_manifest.get("paths", {}).get("simulation_script", "")
    if not isinstance(simulation_script, str) or not simulation_script.endswith(".py"):
        errors.append("阶段2至阶段5的模拟脚本必须是.py文件")
    if policy.get("stage1_certification_batches") != 1:
        errors.append("Server Flow政策未密封阶段1单认证批次")
    if policy.get("stage2_to_stage5_calls_allowed") is not False:
        errors.append("Server Flow政策未禁止阶段2至阶段5调用")
    if policy.get("stage2_to_stage5_python_only") is not True:
        errors.append("执行政策未锁定阶段2至阶段5仅使用Python")
    if policy.get("post_delivery_audit_attempts") != 1 or policy.get("post_delivery_audit_affects_status") is not False:
        errors.append("交付后Server Flow审计政策无效")
    if alignment_manifest is not None:
        stage4_policy = alignment_manifest.get("server_flow_policy", {})
        if stage4_policy.get("calibration_calls_allowed") is not False or stage4_policy.get("formal_calls_allowed") is not False:
            errors.append("阶段4未禁止CALIBRATION或FORMAL调用Server Flow")
        if stage4_policy.get("python_only_execution") is not True:
            errors.append("阶段4未锁定仅使用Python执行")
        if stage4_policy.get("post_delivery_audit_affects_status") is not False:
            errors.append("阶段4未隔离交付后Server Flow审计状态")
    if candidate_archive is not None and candidate_archive.get("server_flow_call_count") != 0:
        errors.append("CALIBRATION阶段存在Server Flow调用")
    if formal_result is not None:
        if formal_result.get("execution_path") != "python":
            errors.append("FORMAL执行路径不是Python")
        if formal_result.get("server_flow_call_count") != 0:
            errors.append("FORMAL阶段存在Server Flow调用")
        if formal_result.get("stage1_server_flow_certification_sha256") != evidence_sha:
            errors.append("FORMAL绑定的阶段1Server Flow认证证据hash无效")
    return errors


def validate_python_user_certification(input_manifest, alignment_manifest=None, formal_result=None):
    if input_manifest.get("report_contract_version") != REPORT_CONTRACT_V33 and input_manifest.get("script_qualification", {}).get("certification_method") != "user_direct":
        return []
    errors = []
    qualification = input_manifest.get("script_qualification", {})
    certification = qualification.get("user_certification", {})
    evidence_sha = certification.get("evidence_sha256", "")
    script_sha = input_manifest.get("hashes", {}).get("simulation_script", "")
    if qualification.get("status") != "通过":
        errors.append("阶段1模拟脚本资格未通过")
    if qualification.get("certified_execution_path") != "python":
        errors.append("用户认证的执行路径必须是Python")
    if qualification.get("certification_method") != "user_direct":
        errors.append("Python脚本必须由用户直接认证")
    if certification.get("status") != "通过" or certification.get("certified_by") != "user":
        errors.append("缺少有效的用户直接认证")
    if not certification.get("evidence_path") or len(evidence_sha) != 64:
        errors.append("用户直接认证证据hash无效")
    if len(script_sha) != 64 or certification.get("certified_script_sha256") != script_sha:
        errors.append("用户直接认证未绑定当前Python脚本hash")
    simulation_script = input_manifest.get("paths", {}).get("simulation_script", "")
    if not isinstance(simulation_script, str) or not simulation_script.endswith(".py"):
        errors.append("模拟脚本必须是.py文件")
    if input_manifest.get("report_contract_version") == REPORT_CONTRACT_V33:
        preflight = input_manifest.get("preflight_decision_gate", {})
        if preflight.get("status") != "通过":
            errors.append("开工前业务决策门禁未通过")
        if preflight.get("business_decision_window") != "preflight":
            errors.append("指标库扩展决策必须位于开工前窗口")
        if preflight.get("metric_library_gap_count") != 0:
            errors.append("正式执行前仍有未关闭的指标库缺口")
        if preflight.get("extension_decision_status") not in {"无需扩展", "已完成"}:
            errors.append("开工前指标库扩展决策尚未完成")
    if alignment_manifest is not None:
        policy = alignment_manifest.get("execution_policy", {})
        if policy.get("calibration_execution_path") != "python" or policy.get("formal_execution_path") != "python":
            errors.append("CALIBRATION和FORMAL执行路径必须锁定为Python")
        if policy.get("certification_method") != "user_direct":
            errors.append("阶段4未绑定用户直接认证方式")
        if input_manifest.get("report_contract_version") == REPORT_CONTRACT_V33:
            errors += validate_continuous_execution_policy(policy, Path(__file__).resolve().parent.parent)
    if formal_result is not None:
        if formal_result.get("execution_path") != "python":
            errors.append("FORMAL执行路径不是Python")
        if formal_result.get("user_script_certification_sha256") != evidence_sha:
            errors.append("FORMAL绑定的用户脚本认证证据hash无效")
    return errors


def validate_continuous_execution_policy(sealed, skill_root):
    errors = []
    source = sealed.get("source_path") if isinstance(sealed, dict) else None
    if not isinstance(source, str) or not source or Path(source).is_absolute() or ".." in Path(source).parts:
        return ["连续执行政策来源路径无效"]
    root = Path(skill_root).resolve()
    path = (root / source).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        return ["连续执行政策来源越出Skill目录"]
    if not path.is_file():
        return ["连续执行政策源文件不存在"]
    source_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    if sealed.get("source_sha256") != source_sha:
        errors.append("连续执行政策来源SHA-256失效")
    try:
        policy = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return errors + [f"连续执行政策无法读取: {exc}"]
    fields = (
        "policy_id", "version", "source_path", "retry_limit", "formal_candidate_limit",
        "auto_regenerate_reports", "auto_rebuild_invalid_samples",
        "auto_expand_formal_samples_within_sealed_budget",
        "auto_return_to_calibration_after_formal_failure", "auto_continue_after_candidate_failure",
        "auto_fix_task_runtime_metadata", "auto_waive_insufficient_data",
        "auto_waive_structurally_unattainable", "finish_with_blocked_or_waived_report",
        "interrupt_user_during_execution", "business_decision_windows",
        "preflight_metric_extension_decision_required",
    )
    mismatches = [field for field in fields if sealed.get(field) != policy.get(field)]
    if mismatches:
        errors.append(f"连续执行政策合同字段与来源不一致: {','.join(mismatches)}")
    return errors


def validate_execution_qualification(input_manifest, alignment_manifest=None, candidate_archive=None, formal_result=None):
    if input_manifest.get("report_contract_version") == REPORT_CONTRACT_V33 or input_manifest.get("script_qualification", {}).get("certification_method") == "user_direct":
        return validate_python_user_certification(input_manifest, alignment_manifest, formal_result)
    return validate_server_flow_policy(input_manifest, alignment_manifest, candidate_archive, formal_result)


def fmt(value):
    if value is None or value == "":
        return "—"
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, float):
        return f"{value:.9f}".rstrip("0").rstrip(".")
    if isinstance(value, dict):
        if "min" in value and "max" in value:
            return f"{fmt(value.get('min'))} ～ {fmt(value.get('max'))}"
        if "lower" in value and "upper" in value:
            return f"{fmt(value.get('lower'))} ～ {fmt(value.get('upper'))}"
        return f"共 {len(value)} 项"
    if isinstance(value, list):
        if len(value) <= 4 and all(not isinstance(item, (dict, list)) for item in value):
            return "、".join(fmt(item) for item in value) if value else "无"
        return f"共 {len(value)} 项"
    return str(value).replace("|", "\\|").replace("\n", " ")


def detail_rows(value, prefix=""):
    """把复杂值确定性展开为“字段、值”行，不输出JSON。"""
    if isinstance(value, dict):
        result = []
        for key in sorted(value):
            path = f"{prefix}.{key}" if prefix else str(key)
            result.extend(detail_rows(value[key], path))
        return result or [[prefix or "详情", "无"]]
    if isinstance(value, list):
        result = []
        for index, item in enumerate(value, 1):
            path = f"{prefix}[{index}]" if prefix else f"第{index}项"
            result.extend(detail_rows(item, path))
        return result or [[prefix or "详情", "无"]]
    return [[prefix or "值", value]]


def labeled_detail_rows(label, value):
    return [[label, field, item] for field, item in detail_rows(value)]


def metric_profile(metric):
    return metric.get("hard_gate_profile") or metric.get("score_profile") or metric.get("audit_profile") or {}


def apply_metric_display_metadata(contract, metadata=None):
    """把只影响阅读的展示元数据合并到合同副本，不改机器合同。"""
    result = copy.deepcopy(contract)
    entries = metadata.get("metrics", []) if isinstance(metadata, dict) else []
    exact = {(item.get("metric_id"), item.get("scope")): item for item in entries if item.get("scope")}
    generic = {item.get("metric_id"): item for item in entries if not item.get("scope")}
    version = result.get("report_contract_version")
    require_business_labels = metadata is not None or version in {REPORT_CONTRACT_V29, REPORT_CONTRACT_V31, REPORT_CONTRACT_V32, REPORT_CONTRACT_V33}
    allow_legacy_defaults = version not in {REPORT_CONTRACT_V31, REPORT_CONTRACT_V32, REPORT_CONTRACT_V33}
    required_display = {"description_zh", "usage_scene_zh", "target_meaning_zh", "display_unit"}
    for metric in result.get("metrics", []):
        display = dict(metric.get("display", {}))
        source = generic.get(metric.get("metric_id"), {})
        display.update({key: value for key, value in source.items() if key not in {"metric_id", "scope"}})
        source = exact.get(metric_key(metric), {})
        display.update({key: value for key, value in source.items() if key not in {"metric_id", "scope"}})
        if not allow_legacy_defaults:
            missing = sorted(key for key in required_display if not display.get(key))
            if missing:
                raise ValueError(f"新版指标合同缺少目录展示元数据: {metric.get('metric_id')} / {','.join(missing)}")
        metric["display"] = display
        metric["_require_business_labels"] = require_business_labels
        metric["_allow_legacy_display_defaults"] = allow_legacy_defaults
    return result


def metric_display(metric):
    result = dict(LEGACY_METRIC_DISPLAY_DEFAULTS.get(metric.get("metric_id"), {})) if metric.get("_allow_legacy_display_defaults", True) else {}
    result.update(metric.get("display", {}))
    name = metric.get("name_zh", metric.get("metric_id", "该指标"))
    if metric.get("_allow_legacy_display_defaults", True):
        result.setdefault("description_zh", f"衡量{name}在当前作用域内的统计表现。")
        result.setdefault("usage_scene_zh", f"用于判断{name}是否接近目标体验。")
        result.setdefault("target_meaning_zh", f"目标值统计合格原版样本中的{name}。")
    return result


def metric_unit(metric, field=None):
    display = metric_display(metric)
    if field is not None:
        field_units = display.get("object_units", {})
        if field in field_units:
            return field_units[field]
    return display.get("display_unit") or UNIT_NAMES.get(metric.get("unit"), metric.get("unit") or "无量纲")


def display_number(metric, value, *, distribution=False, delta=False, field=None):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return value
    unit = metric_unit(metric, field)
    if distribution or metric.get("unit") in {"ratio", "probability"}:
        scaled = value * 100
        return f"{scaled:+.6f}".rstrip("0").rstrip(".") if delta else f"{scaled:.6f}".rstrip("0").rstrip(".")
    return value


def metric_source(metric):
    display = metric_display(metric)
    source = display.get("source_zh") or metric.get("data_source") or metric.get("target_source") or "指标合同"
    return SOURCE_NAMES.get(source, source)


def metric_groups(metrics):
    """按固定分类与合同原顺序生成跨阶段一致的指标编号。"""
    result, number = [], 1
    for kind, title in METRIC_GROUPS:
        items = []
        for metric in metrics:
            if metric.get("kind") != kind:
                continue
            items.append((f"M{number:02d}", metric))
            number += 1
        result.append((kind, title, items))
    other = [metric for metric in metrics if metric.get("kind") not in {item[0] for item in METRIC_GROUPS}]
    if other:
        items = []
        for metric in other:
            items.append((f"M{number:02d}", metric))
            number += 1
        result.append(("other", "其他指标", items))
    return result


def metric_key(metric):
    return metric.get("metric_id"), metric.get("scope")


def metric_shape(metric):
    target = metric.get("target")
    if isinstance(target, dict) and {"min", "max"}.issubset(target):
        return "range"
    if isinstance(target, dict) and {"lower", "upper"}.issubset(target):
        return "range"
    if isinstance(target, list):
        return "distribution"
    if isinstance(target, dict):
        return "object"
    return "scalar"


def metric_item_labels(metric, count):
    display = metric_display(metric)
    labels = display.get("item_labels")
    if isinstance(labels, list) and len(labels) == count:
        return labels
    profile = metric_profile(metric)
    labels = profile.get("bucket_labels")
    if isinstance(labels, list) and len(labels) == count:
        return labels
    metric_id = str(metric.get("metric_id", ""))
    fixed_return_labels = ["0x", "(0,1x)", "[1x,2x)", "[2x,5x)", "[5x,10x)", "[10x,20x)", "[20x,50x)", "[50x,100x)", "[100x,200x)", "[200x,500x)", "[500x,1000x)", "[1000x,2500x)", "[2500x,5000x)", "[5000x,10000x)", "[10000x,最大中奖]"]
    if metric_id in {"core.multiplier_distribution.lt200", "core.return_distribution.lt200"} and count <= 9:
        return fixed_return_labels[:count]
    if metric_id in {"free_spin.return_distribution", "core.long_tail.audit"} and count == 15:
        return fixed_return_labels
    if metric_id == "core.long_tail.audit" and count == 6:
        return fixed_return_labels[9:]
    if "cascade.depth_distribution" in metric_id:
        return [f"Cascade深度{i if i < count else f'{i}+'}" for i in range(1, count + 1)]
    if "continuation_rate_by_step" in metric_id:
        return [f"Cascade第{i}层 → 第{i + 1}层" for i in range(1, count + 1)]
    if metric.get("_require_business_labels"):
        raise ValueError(f"分布指标缺少实际业务标签: {metric.get('metric_id')} / {metric.get('scope')}")
    if "duration_distribution" in metric_id:
        return [f"时长桶{i:02d}" for i in range(1, count + 1)]
    if "return_distribution" in metric_id:
        return [f"回报桶{i:02d}" for i in range(1, count + 1)]
    if "value_distribution" in metric_id:
        return [f"取值桶{i:02d}" for i in range(1, count + 1)]
    if "joint_distribution" in metric_id:
        return [f"联合桶{i:02d}" for i in range(1, count + 1)]
    if "long_tail" in metric_id:
        return [f"长尾桶{i:02d}" for i in range(1, count + 1)]
    return [f"分布项{i:02d}" for i in range(1, count + 1)]


def metric_object_items(metric, value):
    if not isinstance(value, dict):
        return []
    labels = metric_display(metric).get("object_labels", {})
    return [(str(key), labels.get(key, key), value[key]) for key in sorted(value)]


def metric_value(value, index=None, key=None):
    if index is not None:
        return value[index] if isinstance(value, list) and index < len(value) else None
    if key is not None:
        return value.get(key) if isinstance(value, dict) else None
    return value


def numeric_delta(actual, target):
    if isinstance(actual, (int, float)) and not isinstance(actual, bool) and isinstance(target, (int, float)) and not isinstance(target, bool):
        return actual - target
    return None


def metric_meta_lines(number, metric):
    profile = metric_profile(metric)
    display = metric_display(metric)
    kind_name = dict(METRIC_GROUPS).get(metric.get("kind"), "其他指标")
    method = profile.get("method", "audit" if metric.get("kind") == "audit" else "未配置")
    qualification = metric.get("sample_qualification")
    if isinstance(qualification, dict):
        qualification = qualification.get("status", "已配置")
    lines = [
        f"> 指标编号：{number}｜指标ID：{fmt(metric.get('metric_id'))}｜类型：{kind_name}｜作用域：{fmt(metric.get('scope'))}",
        f"> 业务单位：{fmt(metric_unit(metric))}｜评价方法：{fmt(METHOD_NAMES.get(method, method))}｜样本资格：{fmt(qualification)}",
        f"> 指标说明：{fmt(display.get('description_zh'))}",
        f"> 使用场景：{fmt(display.get('usage_scene_zh'))}",
        f"> 目标值含义：{fmt(display.get('target_meaning_zh'))}",
    ]
    if metric.get("kind") == "hard":
        lines.append(f"> 基础容差：{fmt(profile.get('base_tolerance'))}｜系数：{fmt(profile.get('tolerance_factor'))}｜生效容差：{fmt(profile.get('tolerance'))}")
    elif metric.get("kind") == "score":
        lines.append(f"> 评分组：{fmt(metric.get('score_group'))}｜预算键：{fmt(metric.get('score_budget_key', metric.get('metric_id')))}｜权重：{fmt(metric.get('weight'))}｜控制簇：{fmt(metric.get('control_cluster'))}")
    else:
        rules = ["缺失阻塞" if profile.get("blocking_on_missing") else "缺失仅警告"]
        if "blocking_on_mismatch" in profile:
            rules.append("不一致阻塞" if profile.get("blocking_on_mismatch") else "不一致仅警告")
        if profile.get("required_result_status"):
            rules.append(f"要求状态={profile.get('required_result_status')}")
        if profile.get("exact_match_fields"):
            rules.append(f"精确比对={','.join(profile.get('exact_match_fields'))}")
        if profile.get("insufficient_sample_status"):
            rules.append(f"样本不足={profile.get('insufficient_sample_status')}{'并阻塞' if profile.get('insufficient_sample_blocks_formal') else '且不阻塞'}")
        requirement = "；".join(rules)
        lines.append(f"> 审计要求：{fmt(requirement)}｜控制簇：{fmt(metric.get('control_cluster'))}")
    if metric.get("kind") in {"hard", "score"} and method in {"wasserstein_1d", "grouped_wasserstein_1d"}:
        dimensions = metric.get("instance_dimensions") if isinstance(metric.get("instance_dimensions"), dict) else {}
        axis_unit = profile.get("axis_unit") or dimensions.get("output_unit") or display.get("axis_unit") or "以实际桶标签为准"
        lines.append(
            f"> 有序轴：{fmt(profile.get('axis_semantics'))}｜原始轴单位：{fmt(axis_unit)}｜位置变换：{fmt(profile.get('position_transform'))}｜距离单位：{fmt(profile.get('distance_unit'))}"
        )
    return lines


def sample_capability_policy_table(policy):
    """用一张短表说明统一样本能力政策；旧合同未启用时也明确展示。"""
    if not isinstance(policy, dict) or not policy:
        return table(
            ["样本能力政策项", "值", "说明"],
            [["政策状态", "未启用", "当前合同不受统一样本能力政策检验"]],
        )
    confidence = policy.get("confidence_level")
    confidence = f"{confidence * 100:g}%" if isinstance(confidence, (int, float)) and not isinstance(confidence, bool) else confidence
    adjustment = policy.get("multiple_testing", {}).get("grouped_adjustment")
    adjustment = {
        "bonferroni_across_sides_and_active_groups": "原版与FORMAL两侧，并按活动条件组校正",
    }.get(adjustment, adjustment)
    active = policy.get("active_metric_instances")
    return table(["样本能力政策项", "值", "说明"], [
        ["政策ID", policy.get("policy_id"), "确定使用哪套样本能力规则"],
        ["版本", policy.get("version"), "候选结果出现前固定"],
        ["置信水平", confidence, "原版与FORMAL两侧都必须满足"],
        ["多重校正", adjustment, "条件组越多，逐组要求越严格"],
        ["受检指标实例", len(active) if isinstance(active, list) else "无法判定", "只统计本政策实际覆盖的指标作用域"],
        ["政策状态", policy.get("status"), "阻塞时不得进入后续阶段或交付"],
        ["政策SHA-256", policy.get("source_sha256"), "用于确认政策文件未变化"],
    ])


def _sample_count_result(actual, required):
    if not isinstance(actual, int) or isinstance(actual, bool):
        return "缺失", "阻塞"
    if not isinstance(required, int) or isinstance(required, bool):
        return "无法判定", "阻塞"
    gap = max(required - actual, 0)
    return gap, "通过" if gap == 0 else "阻塞"


def metric_sample_capability_lines(metric, stage, formal_sample_count=None):
    """展示逐指标、逐条件组样本能力；FORMAL实际值只接受formal_result中的计数。"""
    capability = metric.get("sample_capability")
    if not isinstance(capability, dict):
        return ["> 样本能力：不适用；本指标不受当前统一样本能力政策检验。"]
    if stage not in SAMPLE_CAPABILITY_TABLE_HEADERS:
        raise ValueError(f"不支持的样本能力报告阶段: {stage}")

    support = capability.get("support_count_by_group")
    required = capability.get("required_sample_count_by_group")
    original_plan = capability.get("original_sample_count_by_group")
    formal_plan = capability.get("formal_sample_count_by_group")
    if not all(isinstance(value, dict) and value for value in (support, required, original_plan, formal_plan)):
        raise ValueError(f"指标样本能力逐组数据不完整: {metric.get('metric_id')} / {metric.get('scope')}")
    groups = sorted(support)
    if any(set(value) != set(groups) for value in (required, original_plan, formal_plan)):
        raise ValueError(f"指标样本能力条件组不一致: {metric.get('metric_id')} / {metric.get('scope')}")

    method = METHOD_NAMES.get(capability.get("method"), capability.get("method"))
    confidence = capability.get("confidence_level")
    confidence = f"{confidence * 100:g}%" if isinstance(confidence, (int, float)) and not isinstance(confidence, bool) else confidence
    rows = []
    formal_actual_statuses = []
    actual_groups = formal_sample_count.get("group_sample_counts") if isinstance(formal_sample_count, dict) else None
    for group in groups:
        label = "全部样本" if group == "__all__" else group
        original_gap, original_status = _sample_count_result(original_plan.get(group), required.get(group))
        if stage in {2, 3}:
            formal_gap, formal_status = _sample_count_result(formal_plan.get(group), required.get(group))
            rows.extend([
                [label, support.get(group), "原版", original_plan.get(group), required.get(group), original_gap, original_status],
                [label, support.get(group), "FORMAL", formal_plan.get(group), required.get(group), formal_gap, formal_status],
            ])
            continue

        if group == "__all__":
            formal_actual = formal_sample_count.get("sample_count") if isinstance(formal_sample_count, dict) else None
        else:
            formal_actual = actual_groups.get(group) if isinstance(actual_groups, dict) else None
        formal_gap, formal_status = _sample_count_result(formal_actual, required.get(group))
        formal_actual_statuses.append(formal_status)
        rows.extend([
            [label, support.get(group), "原版", original_plan.get(group), "不适用", required.get(group), original_gap, original_status],
            [label, support.get(group), "FORMAL", formal_plan.get(group), formal_actual, required.get(group), formal_gap, formal_status],
        ])

    status = capability.get("status")
    if stage == 4:
        actual_status = "通过" if formal_actual_statuses and all(item == "通过" for item in formal_actual_statuses) else "阻塞"
        status = f"计划{status}｜FORMAL实际{actual_status}"
    summary = (
        f"> 样本能力门禁：{fmt(status)}｜方法：{fmt(method)}｜置信水平：{fmt(confidence)}"
        f"｜比较噪声预算：{fmt(capability.get('comparison_noise_budget'))}"
        f"｜单侧误差预算：{fmt(capability.get('per_side_error_budget'))}"
    )
    return [summary, "", table(list(SAMPLE_CAPABILITY_TABLE_HEADERS[stage]), rows)]


def metric_stage2_table(metric):
    target, shape = metric.get("target"), metric_shape(metric)
    source = metric_source(metric)
    unit = metric_unit(metric)
    if shape == "range":
        lower = target.get("min", target.get("lower"))
        upper = target.get("max", target.get("upper"))
        return table(["目标下限", "目标上限", "单位", "来源/说明"], [[display_number(metric, lower), display_number(metric, upper), unit, source]])
    if shape == "distribution":
        labels = metric_item_labels(metric, len(target))
        return table(["分布项", "目标占比", "单位", "来源/说明"], [[label, display_number(metric, value, distribution=True), unit, source if index == 0 else "—"] for index, (label, value) in enumerate(zip(labels, target))])
    if shape == "object":
        return table(["目标字段", "目标值", "单位", "来源/说明"], [[label, display_number(metric, value, field=key), metric_unit(metric, key), source if index == 0 else "—"] for index, (key, label, value) in enumerate(metric_object_items(metric, target))])
    return table(["目标值", "单位", "来源/说明"], [[display_number(metric, target), unit, source]])


def metric_result_summary(metric, result, empty_text="本阶段无结果"):
    if not isinstance(result, dict):
        return empty_text
    if metric.get("kind") == "hard":
        return f"门禁：{fmt(result.get('status'))}；差距：{fmt(result.get('distance'))}；生效容差：{fmt(result.get('tolerance'))}"
    if metric.get("kind") == "score":
        return f"得分：{fmt(result.get('score'))}；档位：{fmt(result.get('band'))}；状态：{fmt(result.get('status'))}"
    return f"审计状态：{fmt(result.get('status'))}"


def metric_brief_result(metric, result, empty_text="—"):
    if not isinstance(result, dict):
        return empty_text
    if metric.get("kind") == "hard":
        return fmt(result.get("status"))
    if metric.get("kind") == "score":
        return fmt(result.get("score"))
    return fmt(result.get("status"))


def metric_stage3_table(metric, result):
    target, shape = metric.get("target"), metric_shape(metric)
    candidate = result.get("candidate") if isinstance(result, dict) else None
    summary = metric_result_summary(metric, result, "不参与阶段3评分")
    if shape == "range":
        lower = target.get("min", target.get("lower"))
        upper = target.get("max", target.get("upper"))
        return table(["目标下限", "目标上限", "单位", "基线值", "差距", "评分/门禁"], [[display_number(metric, lower), display_number(metric, upper), metric_unit(metric), display_number(metric, candidate), display_number(metric, result.get("distance") if isinstance(result, dict) else None), summary]])
    if shape == "distribution":
        labels = metric_item_labels(metric, len(target))
        return table(["分布项", "目标占比", "基线占比", "差值（百分点）", "评分/门禁"], [[label, display_number(metric, value, distribution=True), display_number(metric, metric_value(candidate, index=index), distribution=True), display_number(metric, numeric_delta(metric_value(candidate, index=index), value), distribution=True, delta=True), summary if index == 0 else "—"] for index, (label, value) in enumerate(zip(labels, target))])
    if shape == "object":
        return table(["目标字段", "目标值", "单位", "基线值", "差值", "评分/门禁"], [[label, display_number(metric, value, field=key), metric_unit(metric, key), display_number(metric, metric_value(candidate, key=key), field=key), display_number(metric, numeric_delta(metric_value(candidate, key=key), value), field=key), summary if index == 0 else "—"] for index, (key, label, value) in enumerate(metric_object_items(metric, target))])
    return table(["目标值", "单位", "基线值", "差距", "评分/门禁"], [[display_number(metric, target), metric_unit(metric), display_number(metric, candidate), display_number(metric, result.get("distance") if isinstance(result, dict) else None), summary]])


def metric_stage4_table(metric, baseline, formal):
    target, shape = metric.get("target"), metric_shape(metric)
    baseline_value = baseline.get("candidate") if isinstance(baseline, dict) else None
    formal_value = formal.get("candidate") if isinstance(formal, dict) else None
    summary = metric_result_summary(metric, formal, "FORMAL未生成该指标结果")
    if shape == "range":
        lower = target.get("min", target.get("lower"))
        upper = target.get("max", target.get("upper"))
        return table(["目标下限", "目标上限", "单位", "基线值", "FORMAL值", "变化/差距", "最终结果"], [[display_number(metric, lower), display_number(metric, upper), metric_unit(metric), display_number(metric, baseline_value), display_number(metric, formal_value), display_number(metric, formal.get("distance") if isinstance(formal, dict) else None), summary]])
    if shape == "distribution":
        labels = metric_item_labels(metric, len(target))
        return table(["分布项", "目标占比", "基线占比", "FORMAL占比", "差值（百分点）", "最终结果"], [[label, display_number(metric, value, distribution=True), display_number(metric, metric_value(baseline_value, index=index), distribution=True), display_number(metric, metric_value(formal_value, index=index), distribution=True), display_number(metric, numeric_delta(metric_value(formal_value, index=index), value), distribution=True, delta=True), summary if index == 0 else "—"] for index, (label, value) in enumerate(zip(labels, target))])
    if shape == "object":
        return table(["目标字段", "目标值", "单位", "基线值", "FORMAL值", "差值", "最终结果"], [[label, display_number(metric, value, field=key), metric_unit(metric, key), display_number(metric, metric_value(baseline_value, key=key), field=key), display_number(metric, metric_value(formal_value, key=key), field=key), display_number(metric, numeric_delta(metric_value(formal_value, key=key), value), field=key), summary if index == 0 else "—"] for index, (key, label, value) in enumerate(metric_object_items(metric, target))])
    return table(["目标值", "单位", "基线值", "FORMAL值", "变化/差距", "最终结果"], [[display_number(metric, target), metric_unit(metric), display_number(metric, baseline_value), display_number(metric, formal_value), display_number(metric, formal.get("distance") if isinstance(formal, dict) else None), summary]])


def table(headers, rows):
    if not rows:
        rows = [["无"] + ["—"] * (len(headers) - 1)]
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines.extend("| " + " | ".join(fmt(v) for v in row) + " |" for row in rows)
    return "\n".join(lines)


def heading_sequence(text, expected=None):
    headings = [line.strip() for line in text.splitlines() if line.startswith("#")]
    return [heading for heading in headings if expected is None or heading in expected]


def section_map(text, expected=None):
    lines = text.splitlines()
    headings = [(index, line.strip()) for index, line in enumerate(lines) if line.startswith("#") and (expected is None or line.strip() in expected)]
    result = {}
    for pos, (index, heading) in enumerate(headings):
        end = headings[pos + 1][0] if pos + 1 < len(headings) else len(lines)
        result[heading] = "\n".join(lines[index + 1:end]).strip()
    return result


def validate_structure(text, stage, allow_placeholders=False):
    errors = []
    expected = REPORT_HEADINGS[stage]
    actual = heading_sequence(text, expected)
    if actual != expected:
        errors.append(f"阶段{stage}报告章节顺序与模板契约不一致")
    unexpected = [line.strip() for line in text.splitlines() if line.startswith("#") and line.strip() not in expected and not METRIC_HEADING_PATTERN.match(line.strip())]
    if unexpected:
        errors.append(f"阶段{stage}报告存在未声明章节: {unexpected[0]}")
    if not allow_placeholders and "{{" in text:
        errors.append(f"阶段{stage}报告仍含模板占位符")
    if re.search(r"`\s*[\[{]", text):
        errors.append(f"阶段{stage}报告包含行内JSON，复杂字段必须拆分为表格")
    if stage in {2, 3, 4} and re.search(r"(?:联合桶|回报桶|取值桶|时长桶|长尾桶|分布项)\d+", text):
        errors.append(f"阶段{stage}报告仍含无业务含义的分布占位标签")
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
    sections = section_map(text, REPORT_HEADINGS[stage])
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


def metric_blocks(text):
    lines = text.splitlines()
    headings = [(index, line.strip()) for index, line in enumerate(lines) if METRIC_HEADING_PATTERN.match(line.strip())]
    result = []
    for pos, (index, heading) in enumerate(headings):
        end = headings[pos + 1][0] if pos + 1 < len(headings) else len(lines)
        for next_index in range(index + 1, end):
            if lines[next_index].startswith(("# ", "## ", "### ")):
                end = next_index
                break
        result.append((heading, "\n".join(lines[index + 1:end]).strip()))
    return result


def validate_report_against_template(report_text, template_text, stage):
    errors = validate_structure(report_text, stage)
    report_sections = section_map(report_text, REPORT_HEADINGS[stage])
    template_sections = section_map(template_text, REPORT_HEADINGS[stage])
    for heading in REPORT_HEADINGS[stage][1:]:
        body = report_sections.get(heading, "")
        template_body = template_sections.get(heading, "")
        if heading in METRIC_CONTAINER_HEADINGS.get(stage, set()) and not any(METRIC_HEADING_PATTERN.match(line.strip()) for line in body.splitlines()):
            if "无适用指标" not in body:
                errors.append(f"阶段{stage}指标分类章节没有指标且未说明: {heading}")
            continue
        for field in required_fields(template_body):
            if field not in body:
                errors.append(f"阶段{stage}章节缺少模板必需字段 {field}: {heading}")
        expected_tables, actual_tables = table_headers(template_body), table_headers(body)
        if heading not in METRIC_CONTAINER_HEADINGS.get(stage, set()) and expected_tables != actual_tables[:len(expected_tables)]:
            errors.append(f"阶段{stage}章节表头名称或顺序与展示实例不一致: {heading}")
    blocks = metric_blocks(report_text)
    numbers = []
    for heading, body in blocks:
        numbers.append(int(re.match(r"^#### M(\d+)", heading).group(1)))
        headers = table_headers(body)
        if not headers:
            errors.append(f"阶段{stage}指标章节缺少详情表: {heading}")
        elif tuple(headers[0]) not in METRIC_TABLE_HEADERS.get(stage, set()):
            errors.append(f"阶段{stage}指标章节使用了不允许的表头: {heading}")
        if "指标ID：" not in body or "作用域：" not in body:
            errors.append(f"阶段{stage}指标章节缺少统一元数据: {heading}")
        for marker in ("指标说明：", "使用场景：", "目标值含义：", "业务单位："):
            if marker not in body:
                errors.append(f"阶段{stage}指标章节缺少{marker}: {heading}")
        if "样本能力门禁：" in body:
            expected_sample_header = SAMPLE_CAPABILITY_TABLE_HEADERS.get(stage)
            if expected_sample_header not in {tuple(header) for header in headers}:
                errors.append(f"阶段{stage}受检指标章节缺少样本能力明细表: {heading}")
        elif "样本能力：" not in body:
            errors.append(f"阶段{stage}指标章节缺少样本能力适用性说明: {heading}")
        if "Wasserstein距离" in body:
            for marker in ("有序轴：", "原始轴单位：", "位置变换：", "距离单位："):
                if marker not in body:
                    errors.append(f"阶段{stage}有序指标章节缺少{marker}: {heading}")
    if blocks and numbers != list(range(1, len(numbers) + 1)):
        errors.append(f"阶段{stage}指标编号不连续")
    return errors
