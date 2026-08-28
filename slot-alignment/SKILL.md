---
name: slot-alignment
description: 基于Slot原版采集协议、规则/规格、Runtime和用户一次直接认证的原始Python模拟脚本，自动派生并等价校验观测/输出增强脚本，建立玩法画像与版本化指标合同，执行开工前样本/脚本/指标覆盖确认、默认确定性多Worker样本分片、RTP与体验评分、持续扩预算CALIBRATION、独立FORMAL验收和五阶段中文交付。用于老虎机原版数值或体验对齐、盘面或中奖构成诊断、指标规划、参数搜索、候选验收、禁止变更边界下的结构不可达自动豁免，以及生成阶段1至阶段5固定产物。
---

# Slot 原版数值对齐 v4.4

## 目标与硬边界

在不改变玩法规则的前提下，把候选游戏的统计行为与原版证据对齐，并交付可复算机器结果、确定性中文报告和FORMAL使用的Runtime。

- 全部用户说明、状态和人类报告使用中文。
- 原版资料、历史产物和正式证据只读；不得覆盖源文件。
- 只调整`parameter_authority.json`明确授权的数值参数。
- 禁止修改玩法、状态机、触发与结算语义、RNG调用顺序、投注口径、封顶、最大中奖规则和未授权结构。
- 总RTP目标必须来自外部权威来源；Base、Feature和其他组件目标按原版贡献占比映射权威总RTP，原版组件绝对RTP只作诊断。
- 候选出现前密封指标合同、评价合同、权重、样本计划、预算和FORMAL计划；不得看结果后放宽标准。
- 机器JSON是权威事实。中文报告只能由确定性生成器产生，不得手工修改状态、分数、豁免或FORMAL结论。
- Skill不负责服务端一致性认证；阶段1只接收用户对原始Python脚本及hash的一次直接认证。原始脚本只读；仅为补充观测或兼容输出生成的派生脚本，必须自动证明与原始脚本的RTP、RNG顺序、逐局投注/派奖和状态语义等价。阶段2至5、CALIBRATION和FORMAL只能执行原始认证脚本或通过该等价门禁的派生脚本。
- 不执行配置同步、Git提交、热更新或发布，除非用户另行明确授权。

## 环境与最低输入

先从用户输入、项目`AGENTS.md`和工作区规则解析：

```text
workspace_root
slot_docs_root
python_bin
game_code
mode
task_id
target_rtp
```

- `rtp_group`固定为整数`1`，不得创建其他Group任务或Runtime路由。
- `task_id`缺失时生成`aln-<mode>-<YYYYMMDD>-<NNN>`，创建前确认目录不存在。
- 工作区固定为`<slot_docs_root>/ai-math-workbench/<game_code>/alignments/<mode>/<task_id>/`。
- 路径不存在、结果不唯一、资料目录缺失或关键作用域不明确时停止询问，不自行猜测。
- Python一律使用解析出的`python_bin`。完整路径、目录和状态规则见[92-命名与状态规范.md](references/92-命名与状态规范.md)。
- 模拟默认使用`workers=auto`，按`max(1, floor(进程可用逻辑核心数 × 70%))`解析；只把同一候选的既定总样本拆成不重叠分片并行执行，不增加候选数、预算或总样本量。分片、RNG和合并规则见[04A-搜索效率与预算.md](references/04A-搜索效率与预算.md)。

## 开工前合并确认

正式执行五阶段前只做只读、低成本预检，不运行CALIBRATION或FORMAL：

1. 扫描全部已发现原版源，汇总发现源数量和完整付费入口数。
2. 解析唯一Python脚本文件名、绝对`.py`路径和SHA-256。
3. 建立玩法画像，运行`compile_metric_instances.py`检查指标目录覆盖和统计能力。
4. 生成`metric_extension_proposal.json`，汇总未知玩法、缺少指标包、Owner缺口和观测能力缺口。
5. 第一次合并确认同时向用户展示样本数、是否全量重算、脚本身份、目标、作用域、指标扩展和参数权限。

用户确认现有统计时直接封存；用户要求重新统计时，必须处理`all_discovered_sources`中的全部已发现源。处理范围完整、最终入口数有效且结果路径与hash有效时，自动采用重算后的最终有效入口数并继续，不追加用户确认；只有重算不完整、数量异常或证据无效时才阻塞。观测或输出适配不得修改原始认证脚本，应生成派生脚本并自动运行等价门禁；失败时读取差异、仅修正观测/输出实现并重复校验，不得要求用户重新认证。若某些指标只有改变模式、玩法、游戏逻辑、状态机、RNG、结算语义或配置结构才能取得观测资格或达标，恢复原始认证脚本，密封受影响精确实例的结构不可达证据并自动豁免后继续，不停止询问用户。

只有以下条件全部满足才正式开工：

- `preflight_input_confirmation.status=通过`；
- `preflight_decision_gate.status=通过`；
- 用户已在第一次合并确认中确认发现样本数及是否全量重算；未重算时直接采用用户确认数，重算时自动采用证据有效的最终重算数；
- 指标库缺口数为0，扩展决策为“无需扩展”或“已完成”；
- 原始脚本已有有效用户直接认证；当前执行脚本为该原始脚本，或其派生脚本等价门禁已通过。

详细门禁见[01-资料确认与玩法画像.md](references/01-资料确认与玩法画像.md)、[02-指标匹配.md](references/02-指标匹配.md)和[02A-可达性与豁免.md](references/02A-可达性与豁免.md)。

## 版本与政策链

新任务固定使用：

- `game_profile.schema_version=1.2`；
- 政策链展开中间合同`metric_contract.schema_version=1.3`；
- 阶段2固定机器产物`metric_contract.schema_version=1.4`；
- `report_contract_version=slot-alignment.reports.v3.3`。
- 阶段4执行政策固定使用`continuous_execution_policy.v2.json`和`parallel_execution_policy.v1.json`。

已密封的v2.5至v2.9及v3.2任务只允许显式`--historical-replay`只读复算，不得用于新任务或重新进入阶段2。1.3/1.4存储、继承、hash和兼容边界见[98-通用合同架构升级.md](references/98-通用合同架构升级.md)。

完成适用性、退化和已批准豁免判定后，严格按以下顺序应用政策；前置结果变化会使全部后续结果失效：

1. `hard_gate_tolerance_policy.v2.json`；
2. `jackpot_materiality_policy.v1.json`；
3. `ordered_distance_policy.v1.json`；
4. `score_group_weight_policy.v1.json`；
5. `sample_capability_policy.v1.json`；
6. `automatic_metric_waiver_policy.v1.json`的精确实例重绑定。

纯样本计数不足和有密封证据的结构不可达可按预授权政策自动豁免。结构不可达包括：在当前授权参数空间内无法达标，或只有改变模式、玩法、游戏逻辑、状态机、RNG、结算语义、付费配置或配置结构才能完成的精确指标实例。定义、目标来源、输出实现或配置读取错误本身仍然阻塞；只有证明修复或达标必然越过上述禁止变更边界时，才转为结构不可达自动豁免。存在任一必需豁免时，最终最多显示`豁免后通过`。

## 五阶段工作流

每个阶段必须先生成固定机器JSON和中文报告并通过转换门禁，再进入下一阶段。`work/`中的临时结果不能替代`artifacts/`固定产物。

| 阶段 | 必读规范 | 核心动作 | 固定结果 |
|---|---|---|---|
| 1. 资料确认与玩法画像 | [01](references/01-资料确认与玩法画像.md)、[92](references/92-命名与状态规范.md)、[玩法画像索引](references/玩法画像/index.json) | 密封输入、原始脚本一次认证、派生脚本等价资格、模式与付费配置、玩法画像和参数权限 | `artifacts/01-input-profile/`三份JSON及阶段1报告 |
| 2. 指标匹配 | [02](references/02-指标匹配.md)、[02A](references/02A-可达性与豁免.md)、[03A](references/03A-指标评价合同.md)、[03B](references/03B-硬指标容差系数.md)、[指标索引](references/指标目录/index.json) | 编译实例、匹配Core/Atomic/Composite/Interaction、确定唯一Owner、生成目标、应用政策并紧凑化为1.4 | `artifacts/02-metric-matching/metric_contract.json`及阶段2报告 |
| 3. 基线评分 | [03](references/03-评分系统.md)、[90](references/90-跨阶段一致性.md) | 先判硬指标，再计算0至100分和综合分，生成真实阶段3门禁 | `scorecard.json`、`stage3_gate.json`及阶段3报告 |
| 4. 自动对齐与FORMAL | [04](references/04-自动对齐与正式验收.md)、[04A](references/04A-搜索效率与预算.md) | 读取通过的阶段3门禁，执行敏感性、CALIBRATION、候选冻结和独立FORMAL | `artifacts/04-alignment/`四份JSON及阶段4报告 |
| 5. 交付 | [05](references/05-交付.md)、[95](references/95-验收检查清单.md) | 验证全量产物，复制FORMAL Runtime四件套，封存`dv####`机器清单 | `artifacts/05-delivery/`、`交付物/runtime/`及阶段5报告 |

阶段2、3、4必须使用同一合同指标清单、分类、编号、顺序和标题。全部中文报告写入同一`交付物/报告文档/rv####/`；`artifacts/`只保存机器JSON。FORMAL Runtime四件套写入`交付物/runtime/`，其中`game_core.json.meta.version=task_id`且只保留RTP Group 1。

## 连续执行与停止

业务决策窗口固定为`preflight`和`final_report`。新任务开工后加载`continuous_execution_policy.v2.json`连续推进；v1只用于已密封历史任务。不为普通中间结果逐项询问：

- 同一密封输入的临时错误自动重试2次；
- 全量重算完整且证据有效时自动采用最终有效入口数，不追加用户确认；
- 观测/输出派生脚本等价失败时自动读取差异、修正适配实现并重跑；不得转为用户重新认证请求；
- 报告或可恢复缓存失效时自动重建；
- 候选失败继续下一个候选；
- FORMAL失败回CALIBRATION并继续生成不同冻结候选，不设固定候选次数上限；
- CALIBRATION与FORMAL预算按增量批次自动扩张，预算耗尽不构成停止条件，也不请求用户批准新增预算；
- FORMAL样本不足持续自动扩样，若形成结构不可达证据则按精确实例自动豁免并重生成阶段3/4；
- 结构不可达证据有效时停止仅靠追加预算，自动处理证据列出的精确实例。
- 指标只有改变模式、玩法、游戏逻辑、状态机、RNG、结算语义、付费配置或配置结构才能完成时，自动密封禁止变更边界证据并按结构不可达豁免，不请求用户改变边界。
- 阶段4敏感性、CALIBRATION四级样本和FORMAL的每个单候选模拟默认采用`parallel_execution_policy.v1.json`；Worker数只影响耗时，不得改变总样本预算、RNG语义、候选结果、候选排名或FORMAL独立性。任务专用搜索脚本不得绕过共享分片规则直接退回单进程统计入口。

资料、目标来源、定义、实现或配置读取错误、预检遗漏的新指标扩展及持续外部错误不能自动处理时，保存命令、输入hash、错误和最小恢复动作，以`不通过`或`无法判定`完成最终报告。不得把可由禁止变更边界证明的不可达指标归入上述阻塞；这类指标必须自动豁免并继续。边界与责任见[91-边界停止与责任.md](references/91-边界停止与责任.md)。

## 资源导航

按实际阶段读取，禁止无目的加载全部大目录。

| 需要处理的事项 | 读取资源 |
|---|---|
| 阶段1输入、模式、脚本认证、盘面观测 | [01-资料确认与玩法画像.md](references/01-资料确认与玩法画像.md) |
| 指标加载、Owner、组件RTP、条件组和覆盖 | [02-指标匹配.md](references/02-指标匹配.md) |
| 可达性、扩库、样本不足和豁免 | [02A-可达性与豁免.md](references/02A-可达性与豁免.md) |
| 评分、综合分和阶段3门禁 | [03-评分系统.md](references/03-评分系统.md) |
| 距离、评价合同、退化支持和预算聚合 | [03A-指标评价合同.md](references/03A-指标评价合同.md) |
| 硬指标基础容差与系数 | [03B-硬指标容差系数.md](references/03B-硬指标容差系数.md) |
| CALIBRATION、候选冻结和FORMAL | [04-自动对齐与正式验收.md](references/04-自动对齐与正式验收.md) |
| 搜索效率、预算和可达性上限 | [04A-搜索效率与预算.md](references/04A-搜索效率与预算.md) |
| 交付、双状态和原子封存 | [05-交付.md](references/05-交付.md) |
| 历史Server Flow资源 | [05A-交付后ServerFlow审计.md](references/05A-交付后ServerFlow审计.md)，仅历史只读；新任务禁止读取或执行 |
| hash传播、退回阶段和报告确定性 | [90-跨阶段一致性.md](references/90-跨阶段一致性.md) |
| 停止、审批和责任边界 | [91-边界停止与责任.md](references/91-边界停止与责任.md) |
| 目录、命名、状态和路径表达 | [92-命名与状态规范.md](references/92-命名与状态规范.md) |
| FORMAL与交付最终检查 | [95-验收检查清单.md](references/95-验收检查清单.md) |
| 全部确定性命令和验证顺序 | [96-确定性工具与验证.md](references/96-确定性工具与验证.md) |
| 最小阅读示例 | [97-最小完整示例.md](references/97-最小完整示例.md) |
| metric_contract 1.4存储和兼容 | [98-通用合同架构升级.md](references/98-通用合同架构升级.md) |
| 玩法语义事实源 | `references/玩法画像/index.json`及命中的包 |
| 指标事实源与中文汇总 | `references/指标目录/index.json`及[指标汇总.md](references/指标目录/指标汇总.md) |
| 报告章节与展示合同 | `assets/templates/artifacts/`对应阶段模板 |

`references/指标目录/指标汇总.md`必须由玩法和指标JSON目录确定性生成，禁止手工维护。目录、关系、单位或评分方法变化后必须重新生成并校验。

## 确定性工具

全部命令、输入输出和执行时点以[96-确定性工具与验证.md](references/96-确定性工具与验证.md)为唯一人工说明。必须使用解析出的`python_bin`，不得直接编辑Markdown或机器JSON伪造状态。

正式阶段转换和交付至少运行：

- `semantic_contract_validation.py`；
- `validate_stage_transition.py`；
- `validate_artifacts.py`；
- `seal_delivery.py`。

## 完成门禁

只有以下条件全部满足才结束流程：

- 阶段1至5固定机器产物和五份中文报告齐全；
- Schema、版本、作用域、路径、引用和hash一致；
- 玩法覆盖率与指标可测率为100%，无未关闭必需缺口或Owner冲突；
- 未豁免硬指标全部通过，综合分至少80；
- FORMAL使用独立样本并复验实际逐指标、逐组样本能力；
- 阶段4绑定多Worker政策、实际Worker数、密封分片计划及其hash；同一分片计划以`workers=1`顺序执行和`workers=auto`并行执行时，原始累加器与最终指标必须等价；
- 报告与当前机器JSON确定性等价，模板章节、字段和表头完整；
- FORMAL Runtime与交付manifest逐文件一致，RTP Group和`meta.version`正确；
- 完整`artifacts/`通过最终交付校验，历史版本和失败证据保留；
- 阶段1用户直接认证绑定只读原始Python脚本hash；后续只执行该脚本或已绑定原始hash并通过自动等价门禁的派生脚本；
- 用户首次样本决策和全量重算自动采用证据满足开工前门禁。

FORMAL或交付前完整执行[95-验收检查清单.md](references/95-验收检查清单.md)。交付完成即结束，不追加服务端验证。
