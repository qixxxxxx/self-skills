# 指标库索引

版本：2.7.0
完整中文指标字典：[指标汇总.md](指标汇总.md)

## 七类指标

七类是人类阅读分组，由`categories[].source_categories`归并机器分类。`catalog.json.category`、`packages[].category`和每项指标的`category`必须保持真实玩法语义且彼此一致，不能为了报告排版改成七类阅读ID。

| 顺序 | 分类ID | 承接机器category | 中文分类 | 负责内容 |
|---:|---|---|---|---|
| 10 | `core` | `core` | 通用结果与风险 | 所有游戏共用的RTP、中奖率、触发率、波动、组件贡献、长尾及封顶门禁。 |
| 20 | `board` | `board` | 盘面生成与符号结构 | 可见符号组成、空间结构、生成集中度、可变轴高和组合容量。 |
| 30 | `settlement` | `settlement` | 中奖结算与构成 | 实际中奖符号、条件中奖规模、并发结果、赔付线和Cluster结算结构。 |
| 40 | `trigger` | `trigger` | 玩法触发与入口 | 触发符号数量、位置配置及已进入Feature后的游戏内生入口来源构成。 |
| 50 | `evolution` | `evolution` | 盘面演化与连续过程 | Cascade等一次入口内的连续盘面演化、补充和分层回报。 |
| 60 | `feature` | `feature`、`award`、`state` | 特色玩法、奖励与状态 | 免费旋转、重转、Hold & Spin、奖励抽取、价值符号、Jackpot、持久状态及完整Feature周期。 |
| 70 | `modifier` | `modifier`、`interaction` | 修饰器与跨玩法联合 | Collect、符号变形、Wild、倍率及有证据的跨玩法依赖。 |

## 包级目录

| 机器分类 | 类型 | 指标包 | 适用画像 |
|---|---|---|---|
| core | core | `core.general` | 全部游戏 |
| board | atomic | `atomic.board-diversity` | `board.fixed-grid` ／ `board.variable-grid` |
| board | atomic | `atomic.variable-grid` | `board.variable-grid` |
| settlement | atomic | `atomic.settlement-diversity` | `settlement.payline` ／ `settlement.ways` ／ `settlement.count-pay` ／ `settlement.cluster-pay` |
| settlement | atomic | `atomic.effective-ways-capacity` | Ways存在不能只由几何布局唯一推出的动态实际容量；可用于固定布局或可变布局叠加非几何规则 |
| trigger | atomic | `atomic.trigger` | `trigger.symbol-count` ／ `trigger.random-event` ／ `trigger.state-threshold`；以及声明游戏内生入口来源的Feature画像 |
| evolution | atomic | `atomic.cascade` | `evolution.cascade` |
| feature | atomic | `atomic.free-spin` | `feature.free-spin` |
| feature | atomic | `atomic.respin` | `feature.respin` |
| feature | composite | `composite.feature-cycle` | `feature.free-spin` ／ `feature.respin` ／ `feature.hold-and-spin` ／ `feature.award-draw` ／ `feature.bonus-sequence` |
| feature | atomic | `atomic.hold-and-spin` | `feature.hold-and-spin` |
| modifier | atomic | `atomic.collect` | `modifier.collect` |
| feature | atomic | `atomic.award-draw` | `feature.award-draw` |
| award | atomic | `atomic.jackpot` | `award.jackpot` |
| award | atomic | `atomic.value-symbol` | `award.value-symbol` |
| modifier | atomic | `atomic.symbol-transform` | `modifier.symbol-transform` |
| state | atomic | `atomic.persistent-state` | `state.persistent-state` |
| modifier | atomic | `atomic.wild-effect` | `modifier.wild-substitute` ／ `modifier.expanding-wild` |
| modifier | atomic | `atomic.modifier` | `modifier.win-multiplier` |
| interaction | interaction | `interaction.cascade-multiplier` | `evolution.cascade` ＋ `modifier.win-multiplier` |
| interaction | interaction | `interaction.multiplier-return` | `modifier.win-multiplier`且存在`return_dependency_evidence` |
| feature | interaction | `interaction.hold-spin-return` | `feature.hold-and-spin`的终局锁定占用格数可与完整回报绑定 |
| interaction | interaction | `interaction.wild-multiplier` | Wild节点通过`linked_multiplier_id`、专属依赖证据和共享事件集绑定倍率 |
| interaction | interaction | `interaction.transform-return` | `modifier.symbol-transform`且存在回报依赖证据 |

## Owner与去重规则

- 每个`metric_id`只有一个Owner；匹配只能使用`mechanic_id + 标准属性 + scope`。
- 完整分布是主评价时，其均值、中位数、零值率和可精确推出的条件率只能作为`derived_diagnostic`审计，权重固定为0。
- 联合体验通常使用“边际＋条件分布”或纯依赖残差表达，禁止原始联合分布与其可复算边际同时计分。稳定对象移动只有在完整一一配对和完整位置对域均可证明时，才按数量转移分组评价扣除候选自身起点与终点边际后的纯配对残差；移动数量、位置边际和位置角色仍由独立Owner负责。
- Core硬门禁允许交叉校验，但硬指标不进入综合分。
- Interaction必须有画像中的专属依赖证据，不能仅因两个玩法同时存在而自动加载；Wild与倍率使用`wild_multiplier_dependency_evidence`，不得复用Cascade的泛化证据。
- `trigger.entry_source_distribution`只评价`entry_source_domain=endogenous`；Feature Buy、强制测试、测试注入、运营覆盖和其他外生来源不得进入目标支持集或评分事件集。
- 完整有限抽取随机链可由条件奖励结果分布、确定性转移、停止、聚合和终局投影复算时，`award_draw.outcome_distribution_given_draw_state`保留唯一评分Owner，Feature路径及路径回报确定性派生；链外仍有随机奖励、非确定聚合或未承接玩家决策时继续独立评分。
- 同一指标拆成多个组件、状态或阶段时，先按`scope_aggregation`聚合；实例数量不得扩大`score_budget_key`预算。

## 目录承接与任务覆盖边界

- 公共目录只登记玩法画像到候选指标包的承接关系、Owner、统计语义和评价方法；目录引用完整不等于某个任务已实际覆盖。
- 画像命中的Primary和Guard由阶段2任务指标合同实例化；Audit和派生项单独保留，不得混入主评价数量或评分预算。
- 条件指标包只有在本游戏画像及属性证据命中后才加载，目录中存在不能视为任务已命中。
- 退化支持和不适用必须在阶段2合同中依据实际可达支持密封原因码与证据，公共目录不能替任务预判。
- 指标是否可测取决于任务统计脚本能否输出所需字段。必需覆盖率与指标可测率是否达到100%，只以阶段2任务指标合同为准。
- 派生项不要求独立采样，随其主指标状态传播；审计项默认不进入综合评分，但仍保留证据和风险结论。
- 矩阵中的审计/派生数量不属于Primary/Guard正式数值覆盖。Jackpot命中率先通过规则一致性和资料门禁：物质性层级使用“总体命中率＋命中后层级构成”低维评分，极低频且低贡献层级与动态奖值继续作不计分审计；已有活动Primary可完整投影时不重复评分。
- 新增、删除或变更任何指标时，必须重新生成[指标汇总.md](指标汇总.md)，并保证全部指标ID恰好出现一次。
