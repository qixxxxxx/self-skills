---
name: slot-alignment
description: 根据 Slot 游戏原版采集协议、规则、规格、Runtime和用户认证的Python模拟脚本建立统一主流玩法画像，开工前由用户确认样本总数、完整重算选择、Python脚本名称与绝对路径，并完成指标库覆盖与业务决策预检，匹配版本化且语义去重的指标包，对齐RTP、盘面符号、中奖构成、玩法过程、奖励修饰与持久状态，执行结构可达性预检、自动可审计豁免、硬指标门禁、100分评分、受控CALIBRATION、独立FORMAL验收和中文交付，并维护全量中文指标汇总。用于老虎机原版数值/体验对齐、盘面重复或中奖单一诊断、指标规划、参数搜索、候选验收、不可达与豁免审查，或生成阶段1至阶段5固定结构产物及`阶段4-数值对齐报告.md`。
---

# Slot 原版数值对齐v4.0

## 目标

在不改变玩法规则的前提下，把候选游戏的统计行为与原版证据对齐，并交付可复算机器结果和统一中文报告。资料、审批和执行链完整时，连续完成五阶段，不为普通中间结果打断用户。

## 必须遵守

- 全部用户说明和人类报告使用中文；状态使用中文。
- 原版资料、历史产物和正式证据只读；不得覆盖源文件。
- 只调整`parameter_authority.json`明确授权的数值参数。
- 禁止修改玩法、状态机、触发与结算语义、RNG 调用顺序、投注口径、封顶、最大中奖规则及未授权结构。
- 模拟脚本缺少统计输出时，可在保持游戏逻辑不变的前提下增强输出；任何修改都会使原用户认证失效，必须由用户重新直接认证当前脚本hash。
- 阶段1只接收用户对当前Python模拟/统计脚本的直接认证。阶段2～5、CALIBRATION和FORMAL仅通过`python_bin`执行该已认证`.py`脚本；Skill不负责与服务端对齐，也不设置服务端认证或验证节点。
- 正式开工前必须向用户展示发现的原版样本总数、Python脚本文件名与绝对路径，并记录用户确认。用户要求重新统计时，必须重新处理全部已发现源，不得复用历史局部锁或抽样结果冒充全量重算；全量重算完成后必须再确认最终有效样本数。
- 总 RTP 目标必须来自外部权威来源；不得从原版样本反推。
- Base、Feature、其他组件 RTP 目标必须使用原版组件贡献占比映射到权威总 RTP；原版组件绝对 RTP 只作诊断，不得直接作为目标。
- 新建任务默认加载`assets/policies/hard_gate_tolerance_policy.v2.json`，在候选结果出现前密封基础容差、指标系数和生效容差；v1只保留给旧指标ID的历史任务，不得回溯套用新政策。
- 新建任务默认加载`assets/policies/jackpot_materiality_policy.v1.json`，只使用已密封的Jackpot评分分辨率与组件RTP生效容差确定物质性层级；候选结果不得重新分类，非物质性层级仍保留完整规则和低频审计。
- 新建任务默认加载`assets/policies/ordered_distance_policy.v1.json`。自然次数、长度和格数使用真实线性距离；非负回报、奖值、倍率和组合容量使用固定`log10(1+x)`尺度；Collect输出、中奖规模和有序持久状态必须先从玩法画像解析轴语义，再由政策写入合同。候选不得选择变换、尺度或支持集。
- 新建任务默认加载`assets/policies/score_group_weight_policy.v1.json`，只按活动体验语义组的固定基础预算确定性生成顶层评分组权重；指标数、作用域数、候选频率和候选结果不得改变组预算，人工覆盖必须使用用户批准的新政策ID与hash。
- 新建任务默认加载`assets/policies/sample_capability_policy.v1.json`与`assets/policies/automatic_metric_waiver_policy.v1.json`，以99%置信度分别检查原版目标样本与FORMAL计划/实际样本；条件指标逐活动组检查。纯计数不足按用户预授权自动豁免精确`metric_id + instance_id + scope`实例；定义缺失、输出缺失、计算异常、实现错误和配置异常仍阻塞，不能伪装成数据不足。
- 候选结果出现前密封指标合同、评价合同、权重、样本计划、预算和 FORMAL 计划；不得看结果后放宽标准。
- 自动连续执行不等于跳过阶段产物。每个阶段必须先生成固定机器结果和中文报告并通过阶段转换门禁，才能开始下一阶段；禁止用`work/`中的临时或候选scorecard替代`artifacts/03-scoring/`固定产物。
- 工作区必须使用`<slot_docs_root>/ai-math-workbench/<game_code>/alignments/<mode>/<task_id>/`，不增加Runtime版本或RTP Group目录层级。规范、模板和示例禁止写具体机器绝对路径；完整职责、路径表达规则和目录树以[92-命名与状态规范.md](references/92-命名与状态规范.md)为准。
- `artifacts/`只保存阶段机器JSON；所有中文Markdown写入`交付物/报告文档/rv####/`。FORMAL通过的Runtime四件套写入`交付物/runtime/`。
- 所有任务固定使用RTP Group 1。Runtime必须密封`default_group=1`、`groups=[1]`并移除其他Group配置；FORMAL Runtime的`game_core.json.meta.version`必须等于`task_id`。
- 阶段1至5中文报告必须使用`assets/templates/artifacts/`对应模板的完整章节顺序和展示契约。每章模板必须明确展示方式、必需字段及顺序、空值规则和Markdown实例；无数据时写“无/不适用”及原因，不得删节。报告必须由确定性生成器生成，并与当前机器JSON确定性等价；百分比等阅读转换必须能无损映射回机器值。手工改写、缺章节、章节错序、字段缺失、表头改名或调序、上游hash变化均阻塞下一阶段或交付。
- 中文报告的主表只展示标量摘要和结论；目标、数组、对象、评价参数、指标列表、审批详情及错误详情必须拆成明细表，禁止直接展示JSON。长路径必须使用稳定ID在摘要表中引用，并在同章路径表中单独展示。
- 阶段2、3、4的指标展示必须使用同一合同清单、分类、编号、顺序和标题；固定分为硬指标、评分指标、审计指标，每项指标使用独立小章节，并按标量、区间、分布或复合对象选择一张主详情表。阶段2展示目标合同，阶段3增加基线与评分，阶段4增加FORMAL与最终对齐结果。
- `references/指标目录/指标汇总.md`是全部已登记指标的中文阅读入口，必须从玩法和指标JSON目录确定性生成，禁止手工维护。任何玩法画像、指标、关系、单位或评分方法变更后都必须重新生成；缺项、重复、过期或包含机器绝对路径时，目录校验必须失败。
- 指标按“通用结果与风险、盘面生成与符号结构、中奖结算与构成、玩法触发与入口、盘面演化与连续过程、特色玩法/奖励/状态、修饰器与跨玩法联合”七类阅读；指标自身`category`必须与承接的玩法画像语义一致，不能为了报告方便改放到其他类别。
- 每个语义变量只能有一个主Owner。可由主指标确定性推出的阅读摘要必须标记为`derived_diagnostic`且不计分；交叉门禁和审计项必须说明重叠理由。多个作用域实例先按同一`score_budget_key`聚合，再进入评分组，禁止靠拆作用域或同义指标增加评分权重。
- 新任务必须使用`game_profile.schema_version=1.2`、固定产物`metric_contract.schema_version=1.4`与`report_contract_version=slot-alignment.reports.v3.3`。1.3只允许作为政策链中的展开中间合同和历史只读复算输入，进入阶段3前必须紧凑化为1.4。阶段转换和交付校验必须运行画像到合同的动态语义门禁：重算标准属性、目录命中、必需指标、包映射、覆盖率和Owner互斥，不接受合同自报。完成态玩法节点不得使用`可选`隐藏玩法；Core及全部画像命中指标即使退化或不适用也必须保留合同项，不适用必须绑定受控原因码和可核验证据。v2.5～v3.2已密封任务只允许显式`--historical-replay`复算，不得用于新任务或重新进入阶段2。
- 活动指标的目标证据必须同时绑定指标实例、目录测量口径和父事件集；不能只证明“证据JSON中的值等于合同目标”。无Feature Buy时保留标准不适用实例，但不得伪造`feature_buy` scope或事件文件。Core组件域必须覆盖`base`及每个顶层`feature:<node_id>`；嵌套Feature并入父Feature，组件RTP与Sigma使用同一域。
- 每项指标必须用通俗中文固定说明“指标说明、使用场景、目标值含义”，并展示业务单位。报告层把`ratio`、`probability`和分布概率转换为百分比，把`bet_multiple`转换为“倍投注额（x）”，不得直接把机器单位当成人类单位展示。
- 每个分布项必须展示由原版统计脚本、规格或密封结果证明的实际业务区间或维度；联合分布至少写明两个实际维度，例如“Cascade深度1 × 实际倍率2x”。禁止使用“联合桶01、回报桶01、取值桶01、时长桶01、分布项01”等占位标签。缺少可证明标签时停止补证，不自行猜测。
- 存在可见符号盘面时必须加载`atomic.board-diversity`；存在固定线、Ways、Count Pay或Cluster实际符号结算时必须加载`atomic.settlement-diversity`。入口初始盘、Feature初始盘、演化后完整盘和Cascade新补入格分开统计；Cascade补入数量、稳定分区空间分配和补入符号构成分别由唯一Owner承接，不能只凭RTP、中奖率或Cascade长度宣称盘面与中奖体验已对齐。
- 盘面多样性使用单盘符号数量、条件空间结构、可变布局，以及有稳定生成单元证据时的生成集中度；连续堆叠和生成集中度只有画像分别提供`stack_axis`、`generator_partitions`时加载。符号出镜率、格占比等可由完整数量分布确定的摘要只作派生阅读，不重复计分；不把完整可见盘面签名分布设为通用硬指标。中奖结构使用“中奖符号边际＋给定中奖符号后的实际中奖规模条件分布”：Ways使用实际中奖组合数，赔付线使用实际中奖线数或密封的连中轴数，Count Pay/Scatter使用实际派奖数量，Cluster使用独立派奖连通块大小，禁止使用理论上限。固定线多样性比较“实际结算方向＋规范坐标路径”，禁止直接比较`line_id`；Cluster近门槛连片专项只有画像密封`near_miss_structure_relevant`时加载。
- Hold & Spin先用0权重阻塞审计核对初始重转、逐步消耗、续命触发、reset/add/replace语义、续命数量、上限与时点及退出条件；统计后果由当前占用、占用推进、完整Feature时长和终局占用评价，不再默认增加剩余次数分布。续命数量存在独立随机性时停止并提出任务级扩展。终局锁定占用格数承接填盘结果，纯依赖残差评价终局占用与完整回报关系；终局奖项金额构成只从同一账本作0权重审计，不能把动态奖值、Collect、Jackpot和Feature回报原始联合量再次计分。
- Feature入口来源必须逐项密封为游戏规则产生的内生来源或Feature Buy、强制测试、测试注入等外生来源；`trigger.entry_source_distribution`只在专属内生入口事件域内评分，目标键与事件来源必须完全落在画像声明的内生集合，外生流量不得混入或改变评分权重。
- Pick、Wheel或等价抽取按当前入口来源密封最小充分抽取状态、确定性转移、停止、奖励聚合和终局路径/回报投影。完整有限随机链可由`award_draw.outcome_distribution_given_draw_state`复算时，该指标保留唯一评分Owner，Feature路径及路径回报改为确定性派生；存在链外随机奖励、非确定聚合或未承接玩家决策时，路径与回报继续独立评分。
- Wild机会内实际辅助率、辅助发生后的实际参与Wild格数量和辅助后增量回报分别评分；盘面Wild数量只拥有可见出现边际，不能替代实际参与强度。Wild增量RTP必须从同一逐入口账本按“反事实增量派奖总额/实际经济投注总额”直接审计，禁止用机会内命中率乘条件均值近似。Wild与倍率只有`linked_multiplier_id`、专属`wild_multiplier_dependency_evidence`及共享语义事件集均有效时才加载纯依赖残差，普通共存不加载。
- 无序类别分布使用总变差距离；次数、长度、格数、容量等自然线性有序量使用真实桶位置和`sealed_support_span`，回报、奖值和倍率等非负长尾量固定使用`log10(1+x)`位置变换且不再除以极端全跨度。条件分布与分组依赖残差都必须按候选出现前写入任务合同的组权重汇总，禁止使用候选频率。依赖残差先在每组内平均字段绝对差，不能让组内字段数或稀有组自然扩大权重。条件分布必须与其边际指标组成非重叠分解，不能用原始联合分布再次计算同一边际。
- 每个活动条件组指标必须用`conditional_group_weight_binding`证明组权重来自密封原版事件暴露，或来自精确绑定且有目标证据hash的上游指标因子；退化组先移除再重归一。位置角色残差还必须逐组密封完整位置域基线，基线与残差相加后仍是合法概率。
- Walking Wild或等价移动对象只有在身份稳定、前后完整一一配对且完整结构可达位置对已密封时，才加载`persistent_state.matched_position_pairing_residual_given_count_transition`。该指标按移除/新增数量转移分组，在相同结构支持上扣除保持候选自身起点与终点边际的最大熵基线，只评价“哪个起点配到哪个终点”的额外耦合；位置数量、位置份额和移除/新增位置角色仍由各自主Owner承接。纯Walking Wild使用`modifier.wild-substitute + state.persistent-state(position_set)`表达，未改变数学身份时不得误加载符号变形。
- 多格Mystery或批量符号变形必须声明同事件目标分配规则；使用目标一致性残差评价实际同目标率相对候选自身`P(target|source)`独立基线的额外耦合，给定变换格数和真实无序来源对分组。禁止保存完整目标向量或完整变形后盘面签名，也不得重复格数、单格目标边际、位置和回报Owner。
- Value Symbol与生效倍率、Cascade深度与倍率只有在画像提供完整结构化绑定且合同逐字段复制时才允许单Owner派生。确定Cascade映射下的层级依赖残差是`P(multiplier_state|step)-P(multiplier_state)`，不是恒为0；所有派生目标和组权重必须由深度Owner及逐步状态映射精确复算。
- 完整Feature时长只有在画像以结构化布尔合同证明“初始赠送与最终执行次数一一对应，且无提前停止、可变消耗、计数重置和跨步依赖”时才能标记为确定性派生；仅无重触发或无延长不足以判定。
- 指标合同优先在每项指标的`display`中密封`description_zh`、`usage_scene_zh`、`target_meaning_zh`、`display_unit`、`item_labels`和对象字段单位。旧封存任务可使用只读`--display-metadata`覆盖层生成新版阅读视图；覆盖层只能改变标签、解释、单位和显示精度，不得改变目标、测量、评分或结论。
- 四类完整步骤回报Owner必须由任务级分区合同绑定同一父步骤全集：Cascade步骤、非Cascade可变网格步骤、非Cascade固定网格动态Ways步骤和其余普通结算步骤。校验器必须逐`settlement_step_id`复算子集、两两不交和并集完整，优先级固定为`Cascade > 可变网格 > 固定网格动态Ways > 通用结算`；禁止信任“已完整/已互斥”自报布尔值。
- 预算可按密封阶梯自动扩张，但结构不可达一经有效证据密封即触发可达性上限；禁止继续仅靠增加候选数、样本量或运行时间扩张预算。
- 200x 以下付费入口回报倍率桶默认进入硬指标；200x及以上低频概率只作统计审计，但仍进入总RTP、Sigma和风险检查。最大中奖与封顶不计分，却是阻塞型规则一致性审计：规则缺失、无法证明或不一致时不得进入FORMAL。
- 指标库扩展仍由用户决定，并集中在正式开工前一次性处理。指标豁免只允许两条授权路径：用户单次批准，或本Skill内用户预授权自动政策处理`AUTO_WAIVED_INSUFFICIENT_DATA`和`AUTO_WAIVED_STRUCTURALLY_UNATTAINABLE`；其他原因不得自动跳过。
- 不执行配置同步、Git 提交、热更新或发布，除非用户另行明确授权。

## 环境与最低输入

先从用户输入、项目`AGENTS.md`和工作区规则解析以下值：

```text
workspace_root
slot_docs_root
python_bin
game_code
mode
task_id
target_rtp
```

`rtp_group`不再从外部选择，固定为整数`1`。`task_id`缺失时按`aln-<mode>-<YYYYMMDD>-<NNN>`生成，并在创建文件前确认任务目录不存在。路径不存在、结果不唯一、资料目录缺失或关键作用域不明确时停止询问，不自行猜测。Python一律使用已解析的`python_bin`。

## 开工前业务决策门禁

正式执行五阶段前先做只读、低成本预检，不运行CALIBRATION或FORMAL：扫描全部已发现原版源并汇总入口数，解析唯一Python脚本文件名、绝对路径与hash，建立玩法画像，运行`compile_metric_instances.py`对照当前指标目录与统计能力并输出`metric_extension_proposal.json`。第一次合并确认必须同时向用户展示样本数、脚本身份和指标库扩展提议。用户确认现有样本数时直接封存；用户要求重新统计时，必须按`all_discovered_sources`范围处理全部已发现源，密封处理源数、最终有效入口数和结果hash，再追加一次最终样本数确认。玩法画像包含未知玩法、要求的指标包不存在，或存在指标包但没有有效Primary/Guard/阻塞Audit承接时，必须由用户决定扩展提议；提议同时列出玩法语义目录、指标包、唯一Owner、测量合同、报告展示和脚本认证影响。扩展完成后再由用户认证最终Python脚本hash。`preflight_input_confirmation.status=通过`、`preflight_decision_gate.status=通过`、指标库缺口数为0且扩展决策为“无需扩展/已完成”后，才视为正式开工。

业务决策窗口固定为`preflight`和`final_report`。正式执行中不得逐项询问；预检后意外发现的新玩法或指标缺口视为预检缺陷，停止新增计算并写入最终报告与下一次开工前提案，不在运行中临时扩库或猜测语义。

## 五阶段工作流

1. **资料确认与玩法画像**：先读取[92-命名与状态规范.md](references/92-命名与状态规范.md)创建任务工作区，再读取[01-资料确认与玩法画像.md](references/01-资料确认与玩法画像.md)，检查证据、用户脚本认证、Runtime、作用域和参数权限，生成阶段1三份机器JSON，并运行`render_input_profile_report.py`把完整中文报告写入当前`report_dir`。建立画像前读取`references/玩法画像/index.json`及命中的中文目录说明。
2. **指标匹配**：读取[02-指标匹配.md](references/02-指标匹配.md)、`references/指标目录/index.json`和[指标汇总.md](references/指标目录/指标汇总.md)，复用已通过的开工前实例计划；统计脚本必须为全部实例提交`measurement_capabilities.v1`，缺失能力时自动完成观测适配并在正式开工前重新认证最终脚本hash。随后按`mechanic_id + 标准属性`加载 Core、盘面多样性、中奖结构及其他 Atomic、Composite、Interaction；使用原版组件贡献占比生成组件 RTP 目标；严格按“硬指标容差 → Jackpot物质性 → 有序距离 → 评分组权重 → 样本能力 → 自动豁免重绑定”应用政策并密封来源hash。纯样本不足自动生成豁免并重算有序指标实例、评分组权重与样本能力；结构不可达只有在阶段4形成密封证明后才可自动豁免。最终1.3展开合同用`compact_metric_contract.py`写为1.4固定产物，再运行`render_metric_matching_report.py`生成完整中文报告。
3. **评分**：读取[03-评分系统.md](references/03-评分系统.md)、[03A-指标评价合同.md](references/03A-指标评价合同.md)和[03B-硬指标容差系数.md](references/03B-硬指标容差系数.md)，新任务先应用默认容差系数政策，再使用当前基线判全部未豁免硬指标并计算非硬指标 0～100 分和综合分；生成阶段3机器评分、中文报告和`stage3_gate.json`。
4. **自动对齐与 FORMAL**：只有`stage3_gate.json`为`通过`且`stage4_allowed=true`时，才读取[04-自动对齐与正式验收.md](references/04-自动对齐与正式验收.md)和[04A-搜索效率与预算.md](references/04A-搜索效率与预算.md)，只用`python_bin`执行阶段1由用户认证的Python模拟脚本，依次完成敏感性、CALIBRATION、候选冻结和独立FORMAL；机器结果写入`artifacts/04-alignment/`，中文报告写入当前`report_dir`。
5. **交付**：读取[05-交付.md](references/05-交付.md)，验证完整机器产物和中文报告，把FORMAL Runtime四件套复制到`交付物/runtime/`，生成不可变`dv####`机器清单和当前`report_dir/阶段5-交付清单.md`。交付完成即结束本流程，不追加服务端验证。

执行跨阶段 hash、状态传播或重新进入任务时读取[90-跨阶段一致性.md](references/90-跨阶段一致性.md)。遇到权限、资料、审批或停止判断时读取[91-边界停止与责任.md](references/91-边界停止与责任.md)。创建或检查文件时读取[92-命名与状态规范.md](references/92-命名与状态规范.md)。FORMAL 或交付前必须读取[95-验收检查清单.md](references/95-验收检查清单.md)。需要最小样例时读取[97-最小完整示例.md](references/97-最小完整示例.md)。

## 核心判定

- Core 硬指标：总 RTP、完整付费入口中奖率、各类 Feature 自然触发概率、200x 以下付费入口回报分布、所有适用作用域 Sigma、按原版贡献占比映射的 Base/Feature/其他组件 RTP 贡献。
- 通用体验评分：有可见盘面时以单盘数量、连续堆叠/连片、布局关系和生成集中度为主，出镜率与格占比只作可复算摘要；有标准符号结算时评价中奖符号边际及指定中奖符号下的实际中奖规模；Cascade启动、深度和补充符号分开评价。
- 硬指标只显示`通过`、`不通过`或`硬指标已豁免`及差距，不进入综合分。
- 非硬指标单项采用 100 分制：`高度对齐`、`对齐通过`、`轻度偏差`、`明显偏差`、`严重偏差`；单项 85 分表示自身通过。
- 综合分只汇总有效且未豁免评分指标，最低 80 分；自动豁免后按剩余评分组与预算重归一。定义/测量缺失、计算异常和必需缺口直接阻塞，不按0分处理；纯样本不足按预授权自动豁免。审计按目录中的`blocking_on_missing`、`blocking_on_mismatch`和置信策略执行。
- 最终普通通过：数据门禁有效、全部未豁免硬指标通过、综合分≥80、FORMAL 有效且不存在必需豁免。
- 存在用户单次批准或预授权自动政策产生的必需豁免时，满足其余条件只能显示`豁免后通过`。

## 自动执行与停止

开工前把样本总数/全量重算、Python脚本名称与绝对路径、目标、作用域、指标库扩展、参数权限和最终脚本认证决策完毕。正式执行加载`continuous_execution_policy.v1.json`后连续推进：临时错误同输入自动重试2次；报告/缓存失效自动重建；候选失败自动继续；FORMAL失败自动回CALIBRATION并尝试下一个冻结候选，最多3个；FORMAL样本不足先在密封预算阶梯内扩样，仍不足则自动豁免对应实例并重生成阶段3/4结果；结构不可达证据有效时停止扩张预算、自动豁免受影响实例并重生成评分。

执行中不向用户逐项提问。不可自动处理的资料/权限/实现错误、玩法规则变更需求、未在开工前识别的指标扩展或持续外部错误，保存完整证据并以`不通过`或`无法判定`完成最终报告；需要用户选择的事项集中列在最终报告。只有开工前门禁阶段允许提出一次合并问题。

## 确定性工具

使用解析出的 Python 环境运行：

```bash
<python_bin> <skill_root>/scripts/generate_metric_summary.py --skill-root <skill_root>
<python_bin> <skill_root>/scripts/catalog_tool.py validate --skill-root <skill_root>
<python_bin> <skill_root>/scripts/catalog_tool.py hash --skill-root <skill_root>
<python_bin> <skill_root>/scripts/compile_metric_instances.py --game-profile <game_profile.json> --input-manifest <input_manifest.json> --task-root <task_root> [--measurement-capabilities <measurement_capabilities.json>] --output <metric_instance_plan.json> --extension-proposal <metric_extension_proposal.json>
<python_bin> <skill_root>/scripts/render_input_profile_report.py --artifacts <artifacts> --output <report_dir>/阶段1-资料确认与玩法画像.md
<python_bin> <skill_root>/scripts/derive_component_rtp_targets.py --input <component_rtp_shares.json> --output <component_rtp_targets.json>
<python_bin> <skill_root>/scripts/apply_hard_gate_tolerance_policy.py --contract <base_metric_contract.json> --policy <skill_root>/assets/policies/hard_gate_tolerance_policy.v2.json --output <tolerance_metric_contract.json>
<python_bin> <skill_root>/scripts/apply_jackpot_materiality_policy.py --contract <tolerance_metric_contract.json> --game-profile <artifacts/01-input-profile/game_profile.json> --policy <skill_root>/assets/policies/jackpot_materiality_policy.v1.json --output <jackpot_metric_contract.json>
<python_bin> <skill_root>/scripts/apply_ordered_distance_policy.py --contract <jackpot_metric_contract.json> --policy <skill_root>/assets/policies/ordered_distance_policy.v1.json --output <ordered_metric_contract.json>
<python_bin> <skill_root>/scripts/apply_score_group_weight_policy.py --contract <ordered_metric_contract.json> --policy <skill_root>/assets/policies/score_group_weight_policy.v1.json --output <metric_contract.json>
<python_bin> <skill_root>/scripts/apply_sample_capability_policy.py --contract <metric_contract.json> --policy <skill_root>/assets/policies/sample_capability_policy.v1.json --automatic-waiver-policy <skill_root>/assets/policies/automatic_metric_waiver_policy.v1.json --output <artifacts/02-metric-matching/metric_contract.json>
<python_bin> <skill_root>/scripts/apply_automatic_waiver_policy.py --contract <metric_contract.json> --policy <skill_root>/assets/policies/automatic_metric_waiver_policy.v1.json --source structural-unattainability --attainability-evidence <attainability_evidence.json> --output <metric_contract.json>
<python_bin> <skill_root>/scripts/apply_automatic_waiver_policy.py --contract <metric_contract.json> --policy <skill_root>/assets/policies/automatic_metric_waiver_policy.v1.json --source formal-sample-capability --formal-result <formal_result.json> --output <metric_contract.json>
<python_bin> <skill_root>/scripts/compact_metric_contract.py --contract <metric_contract_1.3.json> --output <artifacts/02-metric-matching/metric_contract.json>
<python_bin> <skill_root>/scripts/benchmark_contract_io.py --contract <metric_contract_1.3_or_1.4.json> [--baseline-contract <metric_contract_1.3.json>] --work-dir <work/contract-benchmark> --output <work/contract-benchmark/result.json>
<python_bin> <skill_root>/scripts/render_metric_matching_report.py --contract <artifacts/02-metric-matching/metric_contract.json> [--display-metadata <report_display_metadata.json>] --output <report_dir>/阶段2-指标匹配报告.md
<python_bin> <skill_root>/scripts/semantic_contract_validation.py --input-manifest <artifacts/01-input-profile/input_manifest.json> --game-profile <artifacts/01-input-profile/game_profile.json> --parameter-authority <artifacts/01-input-profile/parameter_authority.json> --metric-contract <artifacts/02-metric-matching/metric_contract.json> --skill-root <skill_root>
<python_bin> <skill_root>/scripts/score_alignment.py --contract <metric_contract.json> --measurements <measurements.json> --output <scorecard.json>
<python_bin> <skill_root>/scripts/render_scoring_report.py --contract <metric_contract.json> --scorecard <scorecard.json> [--display-metadata <report_display_metadata.json>] --output <report_dir>/阶段3-评分报告.md
<python_bin> <skill_root>/scripts/validate_stage_transition.py --artifacts <artifacts> --reports <report_dir> --output <artifacts/03-scoring/stage3_gate.json>
<python_bin> <skill_root>/scripts/render_alignment_report.py --artifacts <artifacts> [--display-metadata <report_display_metadata.json>] --output <report_dir>/阶段4-数值对齐报告.md
<python_bin> <skill_root>/scripts/render_delivery_report.py --manifest <delivery_manifest.json> --checklist <delivery_checklist.json> --output <report_dir>/阶段5-交付清单.md
<python_bin> <skill_root>/scripts/validate_artifacts.py --artifacts <artifacts> --reports <report_dir>
<python_bin> <skill_root>/scripts/seal_delivery.py --artifacts <artifacts> --reports <report_dir> --formal-runtime <formal_runtime>
```

不得直接编辑 Markdown 改变机器 JSON 中的状态、分数、豁免或 FORMAL 结论。

## 完成条件

- 阶段 1～5 固定产物齐全，Schema、引用、版本、hash 和作用域一致。
- 玩法与指标目录通过严格校验；`references/指标目录/指标汇总.md`与当前目录及生成器确定性一致，全部指标恰好出现一次，七类目录清楚且不存在重复主Owner或重复评分预算。
- 任务路径符合`<game_code>/alignments/<mode>/<task_id>/`；不存在Runtime版本和RTP Group目录层级，作用域及Runtime只保留RTP Group 1。
- `artifacts/`只包含机器JSON；五阶段中文报告位于同一`交付物/报告文档/rv####/`；FORMAL Runtime四件套位于`交付物/runtime/`且`meta.version=task_id`。
- 五份中文报告均通过模板章节顺序、章节非空、展示实例完整、必需字段存在、表头名称与顺序、无占位符、确定性重渲染一致性校验；阶段2、3、4每项指标均有三类通俗说明、业务单位和真实分布标签。
- 玩法必需覆盖率与指标可测率均为100%；开工前不存在未关闭指标库缺口。样本不足或结构不可达可由用户单次批准或预授权自动政策豁免，并保留完整审计。
- 适用游戏的盘面多样性、中奖结构、Cascade补入数量/稳定分区空间分配/补充符号及Wild实际辅助强度指标已实例化并按状态拆分；不适用项具有原版或实现证据。
- 评分可由密封输入确定性复算；评分组权重、有序距离轴和尺度均与政策来源逐字段及hash一致，中文报告与机器结果一致。
- Jackpot物质性分类和逐指标样本能力可由密封画像、评价合同与政策源确定性复算；未豁免实例的原版和FORMAL逐组样本满足99%置信门禁，自动豁免实例完整展示所需、实际、缺口、条件组和授权来源。
- 阶段3固定产物完整且转换门禁通过；阶段4的所有候选均绑定同一有效`stage3_gate.json`。
- FORMAL 使用独立样本并给出真实结论。
- 完整`artifacts/`通过交付校验；历史版本和失败证据保留。
- 阶段1存在有效的用户直接认证，认证证据绑定当前Python脚本hash；阶段2～5、CALIBRATION和FORMAL只执行该认证脚本。
- 阶段1存在有效的开工前输入确认：用户确认最终有效样本数以及当前Python脚本文件名、绝对路径和hash；若用户要求全量重算，证据证明全部已发现源均已处理。
