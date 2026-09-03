---
name: slot-alignment
description: 基于Slot原版采集证据、规则规格、Runtime和用户认证模拟脚本，建立玩家可感知的N数值、J中奖结算、P玩法过程、B盘面呈现合同，完成Runtime能力审计、基线诊断、自动调参、独立FORMAL验收和中文交付。用于老虎机原版数值或体验对齐、盘面与中奖诊断、指标规划、候选验收及Runtime交付；要求活动正式指标逐项通过、原版低样本观察项完整披露，随机步骤单次抽取生效，并禁止结果导向重抽、经验盘面出盘和缩窄已授权原生能力。
---

# Slot 原版体验对齐 6.0.0

## 交付目标

在不改变玩法规则的前提下，使候选Runtime的长期数值和玩家实际看到、经历的体验接近原版证据，并交付可复算机器结果、确定性中文报告和经过独立FORMAL验收的Runtime。

## 先读哪些文件

按任务范围完整读取对应文件，不要只读摘要：

| 任务 | 必读文件 | 负责内容 |
|---|---|---|
| 每次执行 | [指标与画像](references/01-指标框架.md) | 术语、画像字段、N/J/P/B归属和实例生成 |
| 每次执行 | [评价合同](references/02-评价合同.md) | 距离、C级通过值、偏差倍数、分数、状态、样本和例子 |
| 实际对齐、FORMAL或交付 | [执行与报告](references/03-执行与报告.md) | 五阶段输入、动作、产物、失败去向和报告 |
| 读写任务目录 | [工作区结构](references/04-工作区目录结构.md) | 目录ID、固定目录树、晋级和写入规则 |
| 模拟、CALIBRATION或FORMAL | [性能与执行预算](references/05-性能与执行预算.md) | 分片、流式聚合、续跑、并行和等价验收 |

机器事实源优先级固定为：政策JSON与指标目录JSON → Schema → 冻结任务合同 → 脚本实现 → Markdown解释 → 报告模板。发现低优先级内容与高优先级内容冲突时，停止使用冲突结果，修正冲突并重新校验；不得用候选结果反向修改事实源。

## 不可违反的红线

- 全部说明、状态和报告使用中文；代码字段和固定枚举保留机器定义。
- 原版资料、密封输入、认证脚本和FORMAL证据只读，不得覆盖。
- 只调整`parameter_authority.json`明确授权的数值参数。`reel-strip`默认属于数值权重，可调整现有符号重复次数、排列和对应stop weights；轴数、盘面几何、符号域、特殊符号限制和玩法语义保持不变。
- 禁止修改玩法、状态机、触发与结算语义、RNG调用顺序、投注口径、封顶或未授权结构。
- 原版Capture只用于冻结目标、估计参数、诊断和验收。禁止把原版盘面、单轴pattern、局部组合、Tumble后续盘面或Feature链直接作为候选或FORMAL的出盘数据。
- 候选与FORMAL必须使用交付Runtime原生支持并完成等价认证的随机源。禁止`initial_board_weights`、Capture查表出盘、经验盘面采样器和仅在派生Python中生效的隐藏字段。
- 每个随机步骤只能抽取一次并立即生效。禁止看到盘面、中奖、BONUS数量、Tumble深度、Feature结果或派奖后重抽；禁止拒绝采样、反复尝试、递归搜索、分支试探、回溯、失败换seed，以及先定结果再生成到命中。
- 允许按显式权重一次选择获授权的reel-set、随机源或条件类别。选中项只能路由后续原生分布，不能保证某个中奖、盘面、深度、符号数量或派奖结果。
- 条件随机源必须能在抽取前列出合法原子状态和归一化权重。空权重、不可能条件或配置矛盾直接判为配置或实现错误，不得通过增加`attempt`或重抽规避。
- 经验盘面重采样只允许做隔离的离线诊断或可达性上限实验，不得进入候选排序、合同评价、候选冻结、FORMAL、交付或通过结论。
- 画像命中的预期指标不得静默删除。必须在候选出现前按`target_evidence_policy.json`冻结为活动正式指标或观察项；候选结果不得改变该决定。
- 观察项不是“不适用”或临时豁免，必须保留目标证据、原因和覆盖影响。活动正式指标逐项判定；候选结构无法达到活动目标中的原版已观测状态时判为不通过。
- 机器JSON是事实源；中文报告必须由当前机器JSON确定性生成。
- 未经用户另行明确授权，不执行配置同步、Git提交、热更新或发布。

## 输入、默认值与占位

从用户输入、项目`AGENTS.md`和当前工作区解析：

```text
directory_map
runtime_environment
python_bin
game_code
game_name_zh
mode
task_id
target_rtp
target_rtp_confirmation_evidence
```

- `runtime_environment=test`只使用`config-test`和`server-dev`；`prod`只使用`config-prod`和`server-prod`，不得交叉取配置或缓存。
- `rtp_group`固定为整数`1`。
- `task_id`缺失时生成`aln-<mode>-<YYYYMMDD>-<NNN>`，创建前确认目录不存在。
- `runtime_version`固定等于`task_id`，不接受独立输入。
- 工作区固定为`slot-math-workbench:<game_code>/alignments/<mode>/<task_id>/`。
- Python只使用解析出的`python_bin`；本机默认是`/Users/lq/slot_math_env/bin/python`。
- 唯一`target_rtp`必须由用户直接提供或明确确认，取值位于`(0,1]`。资料候选值、区间和Agent自行选择都无效。
- 缺少非业务关键说明时，使用`PENDING_EVIDENCE`或`PENDING_USER_INPUT`占位并记录责任人、缺口和影响，不自行编造。
- 占位只允许存在于开工清单和过程产物。冻结合同、候选排序、FORMAL和交付Runtime不得包含未解决占位。
- 缺少唯一RTP、Runtime基线、认证脚本或参数权限时，可继续资料盘点和实现审计，但不得生成候选或开始FORMAL。

路径、Runtime封包、画像字段和开工确认细节见[执行与报告](references/03-执行与报告.md)与[工作区结构](references/04-工作区目录结构.md)。

## 五阶段工作流

### 1. 密封输入与冻结画像

列出全部Runtime候选、原版来源和原始Python脚本；记录路径、SHA-256和bundle hash。取得唯一基线、脚本认证、目标RTP及参数权限后，将实际使用的Runtime四件套复制到`work/baseline/runtime/`，后续只读取该封包。

建立玩法画像，明确组件、Feature、结算、连续结算、特色机制、盘面、投注基准、Sigma作用域以及固定/可变边界。候选出现前生成并冻结`runtime_capability_matrix.json`，验证认证脚本、服务端、候选生成器、CALIBRATION、FORMAL和优化器六层没有缩窄已授权能力。

### 2. 编译指标合同

使用[指标目录JSON](references/指标目录/index.json)、画像、目标、五份合同政策和样本计划生成`metric_contract.json`。五份合同政策分别负责N类通过值、统一评价、原版目标证据、样本执行和Runtime能力；目录政策只负责落盘校验，不编入指标合同。冻结全部画像命中实例的证据决策，并冻结全部活动实例的Owner、作用域、分母、目标、距离算法、C级通过值、候选样本要求和聚合关系。

阶段2完成后，任何指标库、政策、画像、目标、Runtime、认证脚本、参数权限、能力矩阵或样本计划变化，都使已有基线、候选和FORMAL结果失效。

### 3. 评价基线

使用冻结合同执行基线模拟。活动实例输出距离、偏差倍数、分数、等级、状态和样本证据；观察项只展示原版证据、观察原因和覆盖影响，不要求候选测量。基线`不通过`进入CALIBRATION；候选侧`样本不足`或`计算异常`继续后续流程，但必须保留U状态和证据。

### 4. 自动对齐与独立FORMAL

先做参数敏感性，再按确定性排序生成和淘汰候选。允许从低维参数开始；连续候选只改善RTP而失败结构没有改善时，必须按能力矩阵中的升级计划开放更多已授权原生维度。

CALIBRATION固定使用累计`100000 → 500000 → 2000000`局，前2名各自冻结参数与Runtime后另跑`2000000`局独立复核，再唯一选出FORMAL候选。FORMAL使用独立`chunk_seeded`样本；按活动条件实例的整体分母选择`10000000/20000000/50000000`档位，目标为每个条件实例至少`2000`个有效样本。

若`50000000`仍不足，完成该档并把受影响实例标为`样本不足/U`。FORMAL失败不得通过换seed反复重跑；只能修改候选、修正合同/实现/配置错误，并创建新的独立批次。

### 5. 校验与交付

按`workspace_layout_policy.json`校验目录、Schema、晋级hash、Runtime能力、单/多Worker等价、FORMAL独立性、Runtime四件套和manifest。把`game_core.json.meta.version`与`delivery_manifest.runtime_version`都写成`task_id`，再由输入清单、指标合同和FORMAL结果确定性生成唯一的`交付物/报告文档/对齐报告.md`。

报告只保留一份Markdown，不生成阶段3报告、分类明细、说明页、阅读入口或版本目录。报告必须先给出对齐状态、总等级、综合分和N/J/P/B分类结果，再在同一文件内逐项展示全部活动、低样本、观察和不适用指标。机器字段必须转换成中文名称、自然单位和通俗说明，不得直接堆放实例ID或JSON字段名。

若全部授权搜索层都已尝试仍没有通过候选，交付完整失败证据、最优候选和下一步建议，最终状态为`不通过`；不得无限循环，也不得宣称已对齐。

## 评价总则

- 每个统计实例只按一条判定链执行：距离算法根据冻结目标和候选结果计算距离`D`；政策在候选出现前计算并冻结C级通过值`T`；唯一通过规则是`D <= T`。
- `C级通过值`只负责规定最大允许距离，不负责描述实际偏离程度；机器字段固定为`c_budget`。
- `偏差倍数`只负责把不同单位的距离归一化，公式为`R = D / T`。它用于比较、评分、候选排序和报告，不得作为通过条件，也不得覆盖`D <= T`的判定。
- `分数`只负责区分已通过实例的接近程度并支持卡级、分类级汇总；高分、卡分或分类分都不能补偿任何失败实例。
- `T=0`表示确定性精确规则：仅`D=0`通过并记S；`D>0`直接不通过并记F，失败项偏差倍数为`null`。
- N负责全局数值红线，J负责实际派奖结果，P负责跨结算步骤的玩法过程，B负责稳定可见盘面。归属冲突时使用“全局归N、结果归J、过程归P、静态画面归B”。
- 每个活动正式实例先按距离与C级通过值判定，再计算单项、卡和分类分。观察项不计算距离、通过值、偏差倍数或分数。
- 当前计算N/J/P/B四个分类分，但跨分类权重尚未授权，最终等级只使用`score_scope=["N"]`。报告不得把N类阶段分写成完整综合分。
- `通过`表示全部活动正式实例都满足`距离 <= C级通过值`；`不通过`表示不存在候选侧未判定项且至少一个活动实例为F；`无法完整判定`表示至少一个活动实例为候选样本不足、计算异常或存在未解决合同缺口。
- 覆盖范围独立记录：没有观察项为`完整`，存在观察项为`有限`。活动指标通过时，最终结论分别写`完整范围通过`或`有限范围通过`；观察项本身不会把结果改成U。
- 固定规则不生成概率分布实例，但必须通过规则一致性校验。玩法确实不存在时才使用`不适用`；证据不足不得改成`不适用`。

全部指标定义、算法、通过值、例子和去重关系只在[指标与画像](references/01-指标框架.md)和[评价合同](references/02-评价合同.md)维护。

## 版本合同

6.0.0是当前开发期唯一有效架构。全部机器Schema统一使用`v6`，全部政策统一使用`6.0.0`；不读取、不迁移、不转换任何旧架构产物：

```text
metric_library.schema_version = slot-alignment.metric-library.v6
metric_library.version = 6.0.0
alignment_evaluation_policy.schema_version = slot-alignment.alignment-evaluation-policy.v6
alignment_evaluation_policy.version = 6.0.0
target_evidence_policy.schema_version = slot-alignment.target-evidence-policy.v6
target_evidence_policy.version = 6.0.0
hard_gate_budget_policy.schema_version = slot-alignment.hard-gate-budget-policy.v6
hard_gate_budget_policy.version = 6.0.0
sample_execution_policy.schema_version = slot-alignment.sample-execution-policy.v6
sample_execution_policy.version = 6.0.0
runtime_capability_policy.schema_version = slot-alignment.runtime-capability-policy.v6
runtime_capability_policy.version = 6.0.0
workspace_layout_policy.schema_version = slot-alignment.workspace-layout-policy.v6
workspace_layout_policy.version = 6.0.0
runtime_capability_matrix.schema_version = slot-alignment.runtime-capability-matrix.v6
input_manifest.schema_version = slot-alignment.input-manifest.v6
parameter_authority.schema_version = slot-alignment.parameter-authority.v6
script_equivalence.schema_version = slot-alignment.script-equivalence.v6
game_profile.schema_version = slot-alignment.game-profile.v6
metric_targets.schema_version = slot-alignment.metric-targets.v6
contract_bindings.schema_version = slot-alignment.contract-bindings.v6
sample_execution_plan.schema_version = slot-alignment.sample-execution-plan.v6
metric_contract.schema_version = slot-alignment.metric-contract.v6
metric_measurements.schema_version = slot-alignment.metric-measurements.v6
alignment_result.schema_version = slot-alignment.alignment-result.v6
stage3_gate.schema_version = slot-alignment.stage3-gate.v6
execution_shard.schema_version = slot-alignment.execution-shard.v6
sensitivity_plan.schema_version = slot-alignment.sensitivity-plan.v6
sensitivity_result.schema_version = slot-alignment.sensitivity-result.v6
calibration_batch_manifest.schema_version = slot-alignment.calibration-batch-manifest.v6
parameter_record.schema_version = slot-alignment.parameter-record.v6
candidate_freeze_manifest.schema_version = slot-alignment.candidate-freeze-manifest.v6
formal_plan.schema_version = slot-alignment.formal-plan.v6
alignment_manifest.schema_version = slot-alignment.alignment-manifest.v6
aligned_parameters.schema_version = slot-alignment.aligned-parameters.v6
delivery_manifest.schema_version = slot-alignment.delivery-manifest.v6
alignment_report_manifest.schema_version = slot-alignment.alignment-report-manifest.v6
report_contract_version = slot-alignment.report.v6
```

任何非`v6` Schema或非`6.0.0`政策都按无效输入处理，不设置兼容分支。6.0内部任一冻结输入或hash变化后，已有合同、基线、候选和FORMAL全部失效并重新生成。

## 确定性工具

```bash
<python_bin> scripts/validate_metric_library.py
<python_bin> scripts/generate_metric_summary.py --check
<python_bin> scripts/validate_sample_plan.py --plan <sample-execution-plan.json>
<python_bin> scripts/validate_runtime_capability_coverage.py --matrix <runtime-capability-matrix.json> --phase PRE_CALIBRATION
<python_bin> scripts/compile_metric_contract.py --profile <game-profile.json> --targets <targets.json> --bindings <contract-bindings.json> --sample-plan <sample-execution-plan.json> --runtime-capabilities <runtime-capability-matrix.json> --output <metric-contract.json>
<python_bin> scripts/evaluate_alignment.py --contract <metric-contract.json> --measurements <measurements.json> --phase BASELINE --output <alignment-result.json>
<python_bin> scripts/generate_stage3_gate.py --result <alignment-result.json> --output <stage3-gate.json>
<python_bin> scripts/validate_artifacts.py --contract <metric-contract.json> --result <alignment-result.json> --stage3-gate <stage3-gate.json>
<python_bin> scripts/validate_workspace_layout.py --task-root <任务根目录> --through-stage <1-5>
<python_bin> scripts/validate_delivery.py --task-root <任务根目录> --formal-result <formal-result.json> --alignment-manifest <alignment-manifest.json> --aligned-parameters <aligned-parameters.json> --runtime-dir <交付物/runtime> --manifest <delivery-manifest.json>
<python_bin> scripts/render_alignment_report.py --input-manifest <任务根目录>/artifacts/01-input-profile/input_manifest.json --contract <任务根目录>/artifacts/02-metric-matching/metric_contract.json --result <任务根目录>/artifacts/04-alignment/formal_result.json --output <任务根目录>/交付物/报告文档/对齐报告.md --task-root <任务根目录>
```

CALIBRATION、独立复核和FORMAL分别把`--phase`改为`CALIBRATION`、`INDEPENDENT_RECHECK`和`FORMAL`，并重新执行产物校验。任何工具不得从测量或候选结果反向修改冻结合同。

## 完成门禁

只有以下条件全部满足才宣称本次流程完成：

- 五阶段机器产物、路径和hash一致，`validate_workspace_layout.py --through-stage 5`通过；报告目录只有一份`对齐报告.md`，且由当前机器JSON生成。
- N1～N6及每张适用J/P/B卡的全部活动实例取得S/A/B/C；观察项已完整列出证据等级、样本缺口和影响范围。
- 不存在候选侧样本不足、计算异常、指标缺口、Owner冲突、占位或合同漂移。
- FORMAL使用独立样本，实例清单与冻结合同完全一致。
- 单Worker、多Worker、不同micro-batch和中断续跑结果等价。
- Runtime能力矩阵通过，六层实现没有缩窄已授权原生能力；候选冻结和FORMAL前复核同一矩阵hash。
- 候选与FORMAL不存在经验盘面出盘、隐藏生成字段、结果导向重抽、拒绝采样、回溯或路径预规划。
- FORMAL Runtime与交付manifest逐文件一致，只包含RTP Group 1，两个Runtime版本字段都严格等于`task_id`。

完整范围通过还要求`observational_instance_count=0`。存在观察项但全部活动指标通过时，只能写`有限范围通过`；存在候选侧未判定项时最终等级为U、状态为`无法完整判定`；无候选侧未判定项但有活动失败实例时为`不通过`。
