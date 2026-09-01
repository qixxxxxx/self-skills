---
name: slot-alignment
description: 基于Slot原版采集证据、规则/规格、Runtime和用户认证的Python模拟脚本，冻结玩家感官导向的N数值门禁、J中奖结算、P玩法过程、B盘面呈现指标合同，并完成基线诊断、自动调参、独立FORMAL验收和中文交付。用于老虎机原版数值或体验对齐、盘面与中奖诊断、指标规划、候选验收及Runtime交付；所有画像命中的正式指标必须逐项通过且不得豁免，候选生成必须单次抽取生效，禁止重抽、拒绝采样和回溯规划。
---

# Slot 原版体验对齐 5.4.0

## 目标与边界

在不改变玩法规则的前提下，使候选游戏的长期数值和玩家实际看到、经历的体验与原版证据一致，并交付可复算机器结果、确定性中文报告和FORMAL Runtime。

- 全部说明、状态和报告使用中文。
- 原版资料、密封输入、认证脚本和FORMAL证据只读，不得覆盖。
- 只调整`parameter_authority.json`明确授权的数值参数。
- `reel-strip`默认归为可调数值权重：允许调整现有符号的重复次数与排列，并同步对应stop weights；必须保持轴数、盘面几何、符号域、特殊符号轴/位置限制及玩法语义不变。除非用户明确锁定，否则计划确认后不得为此重复询问。
- 禁止修改玩法、状态机、触发与结算语义、RNG顺序、投注口径、封顶及未授权结构。
- 原版Capture、规则和其他原版证据只用于冻结目标、估计参数、诊断差异和验收候选；禁止把原版完整盘面、单轴可见pattern、局部盘面组合、Tumble后续盘面或Feature链作为CALIBRATION候选或FORMAL模拟的直接生成数据，禁止重放、重采样或按经验盘面目录拼装模拟结果。
- 候选与FORMAL盘面必须由交付Runtime原生支持且经过认证的随机源和生成流程产生，例如reel strips、stop weights、高度权重、refill weights及获授权的reel-set路由。禁止引入`initial_board_weights`、经验盘面采样器、Capture查表出盘或其他仅在派生Python中生效的隐藏生成机制，并禁止把此类机制伪装成可交付Runtime。
- 候选与FORMAL的每个随机步骤必须单次抽取并立即生效。禁止在看到盘面、中奖、BONUS数量、Tumble深度、Feature结果或派奖后重抽；禁止拒绝采样、反复尝试、递归搜索、分支试探、回溯规划、失败换随机数，以及先指定目标结果再持续生成直到命中。
- 允许按显式权重一次选择reel-set、随机源或获授权的条件类别，但选择结果只能决定后续使用哪套原生分布，不得成为必须实现的中奖、盘面、Tumble深度、BONUS数量或派奖后置条件。选中后必须按该分布自然执行完整流程，不得因实际结果偏离类别标签而重选或修复。
- 条件随机源只有在玩法与交付Runtime明确授权、合法原子状态及其归一化权重可预先确定，并能一次加权抽取时才可使用。条件不可能、权重为空或配置矛盾时必须直接判为配置或实现错误；不得通过增加`attempt`、更换seed、重新抽stop/refill或搜索整条Tumble/Feature路径规避失败。
- 经验盘面重采样只允许作为明确标记的离线诊断或结构可达性上限实验，必须隔离在诊断过程目录；其测量不得参与候选排序、合同评价、候选冻结、FORMAL、交付或通过结论。
- 总RTP目标必须由用户直接提供，或由用户对资料候选值明确确认，并冻结为`(0,1]`内的唯一数值；区间、Agent自行选择和仅凭资料推定均无效。组件RTP按原版贡献占比映射用户确认总RTP。
- 候选出现前冻结玩法画像、指标实例、目标、作用域、距离、容差和样本计划。
- 画像命中的正式指标不得删除、降级或豁免；结构不可达判为不通过。
- 样本不足不停止后续计算，只保留状态和证据，最终结论为`无法完整判定`。
- 机器JSON是事实源；中文报告由确定性脚本生成。
- 不执行配置同步、Git提交、热更新或发布，除非用户另行明确授权。

## 必读资源

每次执行本Skill必须完整读取：

1. [指标框架](references/01-指标框架.md)：确定唯一Owner、卡和Facet。
2. [评价合同](references/02-评价合同.md)：确定距离、容差、状态和最终门禁。
3. 涉及实际游戏对齐、FORMAL或交付时，再完整读取[执行与报告](references/03-执行与报告.md)。
4. 创建、读取或写入任务目录时，再完整读取[工作区目录结构](references/04-工作区目录结构.md)。
5. 执行模拟、CALIBRATION或FORMAL时，再完整读取[性能与执行预算](references/05-性能与执行预算.md)。

机器事实源是[指标目录](references/指标目录/index.json)。Markdown汇总只用于人工阅读，不得反向覆盖JSON。

## 唯一指标架构

| 分类 | 指标卡 | 唯一Owner |
|---|---|---|
| N 数值指标 | N1～N6 | 跨完整付费入口或组件的全局数值红线 |
| J 中奖结算 | J1～J3 | 完整结算链中的实际派奖结果 |
| P 玩法过程 | P1～P2 | 跨结算步骤的Feature周期与机制结果状态 |
| B 盘面呈现 | B1～B2 | 稳定可见盘面的视觉符号组、关键符号数量与空间结构 |

归属冲突时使用：结果归J、过程归P、静态画面归B、全局红线归N。Cascade连续消除归J3。固定、条件必然或可由其他正式指标确定性派生的J细项不生成实例，也不得转为J审计。

## 判定规则

- 每个正式实例先计算`偏差倍数 = 实际距离 / 生效容差`，再按卡片阈值判为S/A/B/C/F；S、A、B、C均为通过，F为不通过，样本不足或计算异常为U。
- N类C级最高通过线固定为：N1 `0.5`、N2 `2.0`、N3 `1.0`、N4 `2.0`、N5 `0.3`、N6 `1.0`；S/A/B分别为该上限的25%/50%/75%。
- J中奖结算使用：S `<=1.0`、A `<=2.0`、B `<=4.0`、C `<=6.0`、F `>6.0`；P玩法过程使用：S `<=1.0`、A `<=2.5`、B `<=5.0`、C `<=8.0`、F `>8.0`；B盘面呈现使用：S `<=1.0`、A `<=3.0`、B `<=6.0`、C `<=10.0`、F `>10.0`。
- CALIBRATION默认把J/P/B全部实例推进到B级及以上，即`J<=4.0`、`P<=5.0`、`B<=6.0`；C级只表示达到硬通过线，报告必须标记“最低通过”，不得描述为基本一致或稳定一致。
- 每个画像命中的实例都必须取得S/A/B/C；卡、分类和最终FORMAL取最差等级，不按通过率删除或豁免实例。
- 不计算综合分，不使用权重、平均补偿或豁免。
- 卡状态取最差子项；条件组逐组评价。
- J1按组件和候选出现前冻结的2～5个互斥中奖组评价；只有一个派奖元素的组件不生成J1。J2每个结算模型最多评价一个玩家可识别且实际可变的主要结构轴，并按组件评价实际可变的同步可见中奖数和单步可见奖励。J3只评价实际可变的连续结算总深度与整链奖励；逐元素、逐线路、次要结构轴、逐深度规模及固定单值不生成指标。
- J1/J2/J3按Base、各Feature和其他玩家可区分组件拆分，不得合并平均。J2/J3奖励使用玩家界面展示投注基准，不使用Feature Buy购买成本；购买成本仍只进入N类经济口径。
- B类正式盘面作用域按组件拆分为`initial`和存在连续结算时的`cascade_visible`；无中奖初始盘不得以terminal重复计分，独立terminal只作审计。
- B1普通符号按候选出现前冻结的视觉符号组评价有效格密度；关键特殊符号保留含0的绝对数量分布。Base与Feature、initial与cascade_visible不得合并平均。
- 输出目标、候选、距离、生效容差、偏差倍数、C级通过上限、FORMAL等级、状态和样本证据。
- 普通概率使用绝对概率差；无序状态分布使用总变差；数量、密度和其他有序分布使用一维Wasserstein；可变盘面形态和关键符号位置使用结构Wasserstein。
- J/P/B使用候选出现前密封的原版联合99%自对照容差，容差系数固定1.0；FORMAL分级上限由冻结评价政策确定。
- N4固定为`P(return >= actual_entry_cost)`，Feature Buy使用实际购买成本，容差系数1.5。
- 原付费入口倍率分布只作A1审计。

## 输入与工作区

从用户输入、项目`AGENTS.md`和工作区规则解析：

```text
directory_map
runtime_environment
python_bin
game_code
mode
task_id
target_rtp
target_rtp_confirmation_evidence
```

- 固定目录ID为`slot-docs`、`slot-math-workbench`和`pragmatic-workbench`；`runtime_environment=test`选择`config-test`与`server-dev`，`runtime_environment=prod`选择`config-prod`与`server-prod`，不得交叉混用。
- 项目内非绝对路径统一写成`<directory-id>:<relative-path>`；目录ID必须来自`directory_map`，不得继续使用自定义根变量。
- `rtp_group`固定为整数`1`。
- `task_id`缺失时生成`aln-<mode>-<YYYYMMDD>-<NNN>`，创建前确认目录不存在。
- `runtime_version`不接受独立输入，固定派生为`task_id`；所有FORMAL与交付Runtime的`game_core.json.meta.version`必须严格等于当前`task_id`，不得使用其他版本号。
- 工作区固定为`slot-math-workbench:<game_code>/alignments/<mode>/<task_id>/`。
- 任务内部目录和文件必须符合[工作区目录结构](references/04-工作区目录结构.md)，不得自创平行目录或用`work/`替代权威`artifacts/`。
- 选定基线Runtime后立即将实际使用的四件套逐文件复制到`work/baseline/runtime/`，校验并记录源路径、逐文件SHA-256和bundle hash；基线模拟与候选派生只读取该只读封包，不得继续读取外部配置仓库或服务端缓存。
- 默认扫描`slot-math-workbench:<game_code>/capture-summary/`下全部原版源。
- 原始Python脚本优先扫描`slot-docs:<game_code>/math/scripts/`；该目录无候选时再检查其他资料路径，目录内结果不唯一时停止并询问。
- 路径缺失、结果不唯一或关键作用域不明确时停止并询问，不自行猜测。
- Python只使用解析出的`python_bin`。
- 多Worker必须使用不重叠确定性分片；Worker数不得改变总样本量或结果。
- CALIBRATION与FORMAL默认使用`chunk_seeded`；`crn_v1`只允许用于隔离的离线诊断，不得作为候选排序或FORMAL正式协议。
- 样本执行计划固定使用候选`100000 -> 500000 -> 2000000`累计局数、前2名另跑`2000000`独立复核，以及FORMAL `10000000/20000000/50000000`三档；按活动条件指标实例的整体有效分母选择最小满足档位，目标为每个实例至少`2000`个条件有效样本。
- 不得按分布内单个稀有状态、单个P2状态或其他偶发桶反推FORMAL局数。`50000000`仍不足时不暂停、不再询问，继续跑完该档并把受影响实例标为`样本不足/U`。
- 用户未确认唯一`target_rtp`时停止在开工确认阶段；资料只能用于核验或提出候选值，不得替用户作最终选择。

## 开工确认

候选计算前一次性完成并让用户确认：

1. 只读列举配置仓库、服务端缓存和资料目录的完整Runtime候选及bundle hash。
2. 汇总全部原版样本根目录、来源数和完整付费入口数。
3. 解析唯一原始Python脚本路径与SHA-256，并取得用户直接认证。
4. 建立包含结算、Feature、特色机制、盘面、组件和Sigma作用域的玩法画像；逐组件冻结界面展示投注基准、2～5个互斥中奖组、每种结算模型唯一主要结构轴、J2/J3各维度是否存在多个可达值、连续结算作用域，以及`initial`与适用的`cascade_visible`盘面、视觉符号组、关键计数符号、B2关键空间符号及原版证据。只有一个派奖元素的组件不得创建常量中奖组。
5. 视觉符号组必须互斥并与关键计数符号共同覆盖正式盘面的可见符号域；默认优先使用主题标志组、其他高价值组、低价值组，只有证据要求时才增加组。列出观测缺口、未知玩法和参数权限；默认授权reel-strip数值权重调整，只有超出其结构边界时才询问新增权限。正式指标缺口必须在候选出现前补齐。
6. 取得用户直接提供或明确确认的唯一目标RTP及确认记录hash；若用户只提供区间，必须继续询问唯一数值。随后确认Runtime基线、样本范围、是否重算和参数权限。

原始认证脚本保持只读。派生观测脚本必须证明RTP、RNG、逐局投注/派奖和状态语义等价。

## 轻量执行硬约束

- 候选出现前必须用确定性小样本审计随机调用：逐入口、逐状态和逐refill记录实际抽取次数及调用位置，证明不存在结果观察后的重抽、拒绝采样、搜索、回溯或失败换随机数。同一输入与seed必须一次执行即可复现；审计失败的模型不得进入CALIBRATION候选排序。
- 完整逐局账本、逐RNG调用序列和状态哈希只用于候选出现前的小样本等价验证，不得默认覆盖CALIBRATION或FORMAL全样本。
- CALIBRATION与FORMAL必须采用Worker内流式聚合：单局观测立即累计正式指标，不持久化全量逐局JSON/NDJSON，不写后再读。
- 大样本执行的内存复杂度必须为单Worker `O(1)`每入口，持久化文件数量为`O(分片数)`；每个分片只保存聚合测量、累计器checkpoint、输入指纹和hash。
- 禁止为观测重复执行一次完整结算算法。确需补充中奖明细时，使用一次计算同时返回结算与观测结果，或使用已证明等价的优化实现。
- 每个分片必须原子落盘并可校验续跑；只有task、合同、候选、Runtime、脚本bundle、种子、分片范围和输出hash全部一致时才允许复用。
- 大样本执行前必须做代表性吞吐基准，记录局/秒、预计总时长、Worker数、临时磁盘量和续跑能力；基准用于发现并修正明显低效实现，但不生成性能通过/不通过状态，也不得阻止既定样本计划执行。
- 轻量版必须与完整观测版在同种子小样本上取得逐入口语义、最终RNG状态、全部正式测量、累计器和单/多Worker完全等价，证据随任务保存。

## 五阶段工作流

1. 资料与画像：密封输入、脚本、玩法画像和参数权限。
2. 指标合同：编译全部适用N/J/P/B实例，校准联合99%容差并冻结合同。
3. 基线判定：逐硬门禁、逐卡、逐子项输出距离和偏差倍数。
4. 自动对齐：CALIBRATION按`10万 -> 累计50万 -> 累计200万 -> 前2名另跑200万独立复核`逐级淘汰；冻结候选后使用独立`chunk_seeded`样本执行FORMAL，并按条件实例整体分母自动选择`1000万/2000万/5000万`档位。
5. 交付：验证机器产物、确定性中文报告、FORMAL Runtime和manifest；把`game_core.json.meta.version`与manifest中的`runtime_version`固定为`task_id`。

阶段2至4必须使用同一冻结指标清单、顺序、目标、作用域、距离和容差。候选失败后继续不同候选；普通中间结果不要求用户确认。定义、观测、配置读取或合同错误必须修复，不得伪装成样本不足或不适用。

## 固定版本

```text
metric_library.schema_version = slot-alignment.metric-library.v5
metric_library.version = 5.2.0
alignment_evaluation_policy.version = 5.4.0
sample_execution_policy.version = 1.0.0
game_profile.schema_version = slot-alignment.game-profile.v5
joint_self_comparison.schema_version = slot-alignment.joint-self-comparison.v5
sample_execution_plan.schema_version = slot-alignment.sample-execution-plan.v1
metric_contract.schema_version = slot-alignment.metric-contract.v5
alignment_result.schema_version = slot-alignment.alignment-result.v5
stage3_gate.schema_version = slot-alignment.stage3-gate.v5
delivery_manifest.schema_version = slot-alignment.delivery-manifest.v5
report_contract_version = slot-alignment.report.v5
```

5.4.0不改变指标Schema与`metric_library.version`。N逐卡门槛保持不变；J改为`1/2/4/6`，P改为`1/2.5/5/8`，B保持`1/3/6/10`。J最接近实际中奖和派奖，门槛仍严于P；P允许Feature节奏和机制状态有更大波动；B主要负责防止明显怪异盘面。门槛放宽不豁免任何命中实例，也不放宽规则守恒、结构可达性和候选生成合法性。5.2.1的单次抽取要求继续对所有尚未完成交付的候选生效。评价政策hash或版本变化后，尚未完成交付的任务如采用新政策，必须重新编译合同并重算基线、候选和FORMAL，不得直接修改旧合同或旧结果。

政策只使用：

- `assets/policies/hard_gate_tolerance_policy.json`
- `assets/policies/alignment_evaluation_policy.json`
- `assets/policies/sample_execution_policy.json`

## 确定性工具

```bash
<python_bin> scripts/validate_metric_library.py
<python_bin> scripts/generate_metric_summary.py --check
<python_bin> scripts/calibrate_joint_tolerances.py --input <self-distance.json> --output <joint-tolerance.json>
<python_bin> scripts/validate_sample_plan.py --plan <sample-execution-plan.json>
<python_bin> scripts/compile_metric_contract.py --profile <game-profile.json> --targets <targets.json> --joint-tolerances <joint-tolerance.json> --bindings <bindings.json> --sample-plan <sample-execution-plan.json> --output <metric-contract.json>
<python_bin> scripts/evaluate_alignment.py --contract <metric-contract.json> --measurements <measurements.json> --phase BASELINE --output <alignment-result.json>
<python_bin> scripts/generate_stage3_gate.py --result <alignment-result.json> --output <stage3-gate.json>
<python_bin> scripts/validate_artifacts.py --contract <metric-contract.json> --result <alignment-result.json> --stage3-gate <stage3-gate.json>
<python_bin> scripts/validate_delivery.py --formal-result <formal-result.json> --runtime-dir <交付物/runtime> --manifest <delivery-manifest.json>
<python_bin> scripts/render_alignment_report.py --contract <metric-contract.json> --result <alignment-result.json> --output <report.md>
```

FORMAL把`--phase`改为`FORMAL`并重新执行产物校验。任何工具不得从候选结果反向修改冻结合同。

## 完成门禁

只有以下条件全部满足才宣称对齐完成：

- 五阶段机器产物、报告、hash和路径一致。
- 任务目录符合固定结构，机器JSON、过程数据、报告和Runtime职责没有混放。
- N1～N6全部实例取得S/A/B/C。
- 每张适用J/P/B卡及全部命中子项取得S/A/B/C。
- 无样本不足、计算异常、指标缺口、Owner冲突或合同漂移。
- FORMAL使用独立样本，实际实例清单与冻结合同完全一致。
- 多Worker与单Worker在同一分片计划下结果等价。
- 报告由当前机器JSON确定性生成。
- 候选模拟器和FORMAL Runtime不包含原版盘面/局部pattern样本池、Capture查表出盘、经验盘面采样器或Runtime不支持的隐藏生成字段；诊断性经验重采样结果未进入候选排序、FORMAL和交付证据。
- 候选模拟器和FORMAL Runtime不存在重抽、拒绝采样、反复尝试、递归搜索、分支回溯、完整路径预规划或结果不符后更换随机数；显式类别选择只路由随机源，不强制兑现结果标签。
- FORMAL Runtime与交付manifest逐文件一致且只包含RTP Group 1；`game_core.json.meta.version`和`delivery_manifest.runtime_version`均严格等于`task_id`。

存在任一样本不足或计算异常时，流程继续并交付报告，但最终等级为U、最终状态为`无法完整判定`；不存在未判定项但有F级实例时为`不通过`。
