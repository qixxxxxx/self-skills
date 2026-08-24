---
name: slot-alignment
description: 根据 Slot 游戏原版采集协议、规则、规格、Runtime、服务端和模拟脚本建立统一玩法画像，匹配版本化指标包，执行结构可达性预检、硬指标门禁、100 分评分、受控 CALIBRATION、独立 FORMAL 验收和中文交付。用于老虎机原版数值对齐、玩法体验对齐、指标规划、参数搜索、候选验收、不可达与豁免审查，或生成阶段1至阶段5固定结构产物及`阶段4-数值对齐报告.md`。
---

# Slot 原版数值对齐v2.5

## 目标

在不改变玩法规则的前提下，把候选游戏的统计行为与原版证据对齐，并交付可复算机器结果和统一中文报告。资料、审批和执行链完整时，连续完成五阶段，不为普通中间结果打断用户。

## 必须遵守

- 全部用户说明和人类报告使用中文；状态使用中文。
- 原版资料、历史产物和正式证据只读；不得覆盖源文件。
- 只调整`parameter_authority.json`明确授权的数值参数。
- 禁止修改玩法、状态机、触发与结算语义、RNG 调用顺序、投注口径、封顶、最大中奖规则及未授权结构。
- 模拟脚本缺少统计输出时，可在保持游戏逻辑不变的前提下增强输出；修改后必须重新证明与 server 逻辑一致。
- 总 RTP 目标必须来自外部权威来源；不得从原版样本反推。
- Base、Feature、其他组件 RTP 目标必须使用原版组件贡献占比映射到权威总 RTP；原版组件绝对 RTP 只作诊断，不得直接作为目标。
- 新建任务默认加载`assets/policies/hard_gate_tolerance_policy.v1.json`，在候选结果出现前密封基础容差、指标系数和生效容差；已有任务不得回溯套用。
- 候选结果出现前密封指标合同、评价合同、权重、样本计划、预算和 FORMAL 计划；不得看结果后放宽标准。
- 自动连续执行不等于跳过阶段产物。每个阶段必须先生成固定机器结果和中文报告并通过阶段转换门禁，才能开始下一阶段；禁止用`work/`中的临时或候选scorecard替代`artifacts/03-scoring/`固定产物。
- 阶段1至5中文报告必须使用`assets/templates/artifacts/`对应模板的完整章节顺序和展示契约。每章模板必须明确展示方式、必需字段及顺序、空值规则和Markdown实例；无数据时写“无/不适用”及原因，不得删节。报告必须由确定性生成器生成，并与当前机器JSON逐字一致；手工改写、缺章节、章节错序、字段缺失、表头改名或调序、上游hash变化均阻塞下一阶段或交付。
- 预算可按密封阶梯自动扩张，但结构不可达一经有效证据密封即触发可达性上限；禁止继续仅靠增加候选数、样本量或运行时间扩张预算。
- 200x 以下倍率桶默认进入指标；200x 及以上与最大中奖默认只审计，但仍进入总 RTP、Sigma 和风险检查。
- 用户是指标库扩展和指标豁免的唯一批准者。未经批准不得跳过必需指标。
- 不执行配置同步、Git 提交、热更新或发布，除非用户另行明确授权。

## 环境与最低输入

先从用户输入、项目`AGENTS.md`和工作区规则解析以下值：

```text
workspace_root
slot_docs_root
server_root
python_bin
game_code
mode
rtp_group
target_rtp
```

路径不存在、结果不唯一、资料目录缺失或关键作用域不明确时停止询问，不自行猜测。Python 一律使用已解析的`python_bin`。

## 五阶段工作流

1. **资料确认与玩法画像**：读取[01-资料确认与玩法画像.md](references/01-资料确认与玩法画像.md)，检查证据、脚本资格、Runtime、作用域和参数权限，生成阶段 1 四件套，并运行`render_input_profile_report.py`生成完整中文报告。建立画像前读取`references/mechanics/index.json`及命中的中文目录说明。
2. **指标匹配**：读取[02-指标匹配.md](references/02-指标匹配.md)和`references/metrics/index.json`，按`mechanic_id + 标准属性`加载 Core、Atomic、Composite、Interaction；使用原版组件贡献占比生成组件 RTP 目标，为新任务应用默认硬指标容差政策并密封政策 hash；执行结构可达性预检后运行`render_metric_matching_report.py`生成完整中文报告。出现缺口或不可达时读取[02A-可达性与豁免.md](references/02A-可达性与豁免.md)。
3. **评分**：读取[03-评分系统.md](references/03-评分系统.md)、[03A-指标评价合同.md](references/03A-指标评价合同.md)和[03B-硬指标容差系数.md](references/03B-硬指标容差系数.md)，新任务先应用默认容差系数政策，再使用当前基线判全部未豁免硬指标并计算非硬指标 0～100 分和综合分；生成阶段3机器评分、中文报告和`stage3_gate.json`。
4. **自动对齐与 FORMAL**：只有`stage3_gate.json`为`通过`且`stage4_allowed=true`时，才读取[04-自动对齐与正式验收.md](references/04-自动对齐与正式验收.md)和[04A-搜索效率与预算.md](references/04A-搜索效率与预算.md)，依次执行敏感性、CALIBRATION、候选冻结、独立 FORMAL；生成`阶段4-数值对齐报告.md`。
5. **交付**：读取[05-交付.md](references/05-交付.md)，验证完整`artifacts/`，生成不可变交付版本与三份阶段 5 清单。

执行跨阶段 hash、状态传播或重新进入任务时读取[90-跨阶段一致性.md](references/90-跨阶段一致性.md)。遇到权限、资料、审批或停止判断时读取[91-边界停止与责任.md](references/91-边界停止与责任.md)。创建或检查文件时读取[92-命名与状态规范.md](references/92-命名与状态规范.md)。FORMAL 或交付前必须读取[95-验收检查清单.md](references/95-验收检查清单.md)。需要最小样例时读取[97-最小完整示例.md](references/97-最小完整示例.md)。

## 核心判定

- Core 硬指标：总 RTP、完整付费入口中奖率、各类 Feature 自然触发概率、200x 以下倍率分布、所有适用作用域 Sigma、按原版贡献占比映射的 Base/Feature/其他组件 RTP 贡献。
- 硬指标只显示`通过`、`不通过`或`硬指标已豁免`及差距，不进入综合分。
- 非硬指标单项采用 100 分制：`高度对齐`、`对齐通过`、`轻度偏差`、`明显偏差`、`严重偏差`；单项 85 分表示自身通过。
- 综合分只汇总有效非硬指标，最低 80 分；缺失、样本不足、计算异常和必需缺口直接阻塞，不按 0 分处理。
- 最终普通通过：数据门禁有效、全部未豁免硬指标通过、综合分≥80、FORMAL 有效且不存在必需豁免。
- 存在用户批准的必需豁免时，满足其余条件只能显示`豁免后通过`。

## 自动执行与停止

无资料缺失、审批、授权冲突或持续外部错误时自动推进至交付。临时执行错误以完全相同的密封输入自动重试，单步默认最多 2 次。

只在以下情况停止并向用户提出一个明确问题：

- 关键资料、目标、路径或作用域缺失/不唯一；
- 需要批准指标库扩展或指标豁免；
- 参数授权与实际配置冲突；
- 同一外部服务、权限或执行错误重试后仍失败；
- 授权合法参数空间已由密封证据判定结构不可达；停止自动扩张预算，只能等待扩权、目标变更或豁免决定；
- 发现会改变玩法规则才能达标。

## 确定性工具

使用解析出的 Python 环境运行：

```bash
<python_bin> <skill_root>/scripts/catalog_tool.py validate --skill-root <skill_root>
<python_bin> <skill_root>/scripts/render_input_profile_report.py --artifacts <artifacts> --output <artifacts/01-input-profile/阶段1-资料确认与玩法画像.md>
<python_bin> <skill_root>/scripts/derive_component_rtp_targets.py --input <component_rtp_shares.json> --output <component_rtp_targets.json>
<python_bin> <skill_root>/scripts/apply_hard_gate_tolerance_policy.py --contract <base_metric_contract.json> --policy <skill_root>/assets/policies/hard_gate_tolerance_policy.v1.json --output <metric_contract.json>
<python_bin> <skill_root>/scripts/render_metric_matching_report.py --contract <artifacts/02-metric-matching/metric_contract.json> --output <artifacts/02-metric-matching/阶段2-指标匹配报告.md>
<python_bin> <skill_root>/scripts/score_alignment.py --contract <metric_contract.json> --measurements <measurements.json> --output <scorecard.json>
<python_bin> <skill_root>/scripts/render_scoring_report.py --contract <metric_contract.json> --scorecard <scorecard.json> --output <阶段3-评分报告.md>
<python_bin> <skill_root>/scripts/validate_stage_transition.py --artifacts <artifacts> --output <artifacts/03-scoring/stage3_gate.json>
<python_bin> <skill_root>/scripts/render_alignment_report.py --artifacts <artifacts> --output <阶段4-数值对齐报告.md>
<python_bin> <skill_root>/scripts/validate_artifacts.py --artifacts <artifacts>
<python_bin> <skill_root>/scripts/seal_delivery.py --artifacts <artifacts>
```

不得直接编辑 Markdown 改变机器 JSON 中的状态、分数、豁免或 FORMAL 结论。

## 完成条件

- 阶段 1～5 固定产物齐全，Schema、引用、版本、hash 和作用域一致。
- 五份中文报告均通过模板章节顺序、章节非空、展示实例完整、必需字段存在、表头名称与顺序、无占位符、确定性重渲染一致性校验。
- 玩法必需覆盖率与指标可测率均为 100%，或存在用户批准且仍保留审计的有效豁免。
- 评分可由密封输入确定性复算，中文报告与机器结果一致。
- 阶段3固定产物完整且转换门禁通过；阶段4的所有候选均绑定同一有效`stage3_gate.json`。
- FORMAL 使用独立样本并给出真实结论。
- 完整`artifacts/`通过交付校验；历史版本和失败证据保留。
