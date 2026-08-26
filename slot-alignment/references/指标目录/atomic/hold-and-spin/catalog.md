# Hold & Spin过程指标

版本：2.8.0
Owner：`atomic.hold-and-spin`

## Owner边界

`atomic.hold-and-spin`先用0权重阻塞审计核对重转资源状态机，再评价锁定盘面的初始占用、全部实际执行步骤开始时的当前占用、逐步容量变化、容量变化后的占用推进和终局填充，并审计终局奖项金额的唯一归属；完整Feature回报和总轮数仍由`composite.feature-cycle`负责。固定容量只把`board_capacity`作为常量条件，不实例化任何容量指标。可变容量按`P(C) × P(O|C) × P(C'|C,O) × P(O'|C,O,C')`拆分，分别由容量边际、当前占用、容量推进和占用推进唯一拥有；入口与终局占用分别条件于对应观察点容量边际，不保存原始联合分布重复计分。容量边际和容量推进默认权重各`0.5`，合计不超过容量语义预算`1.0`。

容量边际由完整布局、组合规则后的最终动态Ways容量或有序状态Primary精确推出时，本包对应实例确定性派生；逐步扩容由密封规则对每个`C,O`唯一确定`C'`时，容量推进按`deterministic_rule_result`派生且不评分。同一`state_id + position_domain`若同时建立`state.persistent-state(position_set)`，通用持久状态占用数量与移除/新增数量转移都必须不适用；位置份额和位置角色残差只能通过`position_count_owner_bindings`引用本包专用数量Owner后补充空间偏向。初始占用默认由本包评分；只有固定十字段`resource_count_derivation_bindings`绑定共享入口事件集中的单一活动Board或Trigger数量实例，并能按相同实际容量逐桶精确复算目标时，才改为确定性派生。固定单值只按退化支持处理，不允许同时保留派生Binding。

## 指标清单

| 顺序 | 指标ID | 中文名 | 类型 | 语义角色 | Owner及重叠关系说明 |
|---:|---|---|---|---|---|
| 5 | `hold_spin.respin_resource_rule_consistency.audit` | Hold & Spin重转资源规则一致性审计 | 审计指标 | 审计 | 逐项核对初始次数、每步消耗、续命触发、reset/add/replace语义、续命数量、上限与时点及退出条件；0权重，不重复过程结果评分。 |
| 8 | `hold_spin.actual_capacity_distribution_by_observation` | Hold & Spin各观察点实际容量分布 | 评分指标 | 主评价 | 仅容量可变时实例化并拥有入口、步骤开始和终局的`P(C)`；可由布局或有序状态Primary精确推送时确定性派生。 |
| 10 | `hold_spin.initial_occupancy_distribution` | Hold & Spin初始占用格分布 | 评分指标 | 主评价 | 拥有入口`P(O_initial|C_entry)`；同事件集计数完整映射可推出时由唯一活动Board/Trigger数量实例拥有，并与同状态持久占用数量互斥。 |
| 20 | `hold_spin.current_occupancy_distribution` | Hold & Spin步骤当前占用格分布 | 评分指标 | 主评价 | 拥有全部实际执行步骤开始时的`P(O|C)`，并提供后续两个条件分布的原版组权重因子。 |
| 25 | `hold_spin.capacity_transition_distribution` | Hold & Spin容量推进分布 | 评分指标 | 主评价 | 仅容量可变时实例化并拥有`P(C'|C,O)`；规则唯一确定下一容量时派生不评分。 |
| 30 | `hold_spin.occupancy_transition_distribution` | Hold & Spin占用格推进分布 | 评分指标 | 主评价 | 只拥有`P(O'|C,O,C')`，把扩容概率与扩容后的落入效果分开；与通用持久状态数量Owner互斥。 |
| 40 | `hold_spin.terminal_occupied_cell_count_distribution` | Hold & Spin终局占用格分布 | 评分指标 | 主评价 | 拥有退出边界`P(O_terminal|C_terminal)`；与同状态持久占用数量互斥。 |
| 50 | `hold_spin.terminal_award_value_composition.audit` | Hold & Spin终局奖项金额构成审计 | 审计指标 | 审计 | 按容量和终局占用核对互斥奖项组件的最终金额份额；0权重，不重复动态奖值、Collect、Jackpot或Feature回报评分。 |

## 派生与交叉关系

- 固定容量不得创建`hold_spin.actual_capacity_distribution_by_observation`或`hold_spin.capacity_transition_distribution`实例；初始、当前、推进和终局占用直接使用常量`board_capacity`。不得先创建容量指标再用退化支持退出。
- 可变容量时，`hold_spin.actual_capacity_distribution_by_observation`按每个`entry_source`固定使用`entry`、`step_start`、`terminal`三个作用域实例。每个实例独立密封原版观察事件暴露，全部实例先按同一`score_budget_key`聚合；其默认权重为`0.5`。
- `capacity_owner_bindings`只允许从`variable_grid.reel_height_layout_distribution`、`variable_grid.valid_cell_layout_distribution`、`effective_ways.capacity_distribution`或`persistent_state.ordered_value_distribution`中的一个活动Primary实例，向同一入口来源和容量观察点推送。绑定必须证明双方共享同一观察事件全集，完整覆盖来源支持，逐项映射到`actual_capacity_domain`且无额外随机或状态依赖；推送目标必须与容量实例完全一致，来源更丰富的布局、最终Ways容量或状态Owner保留活动，容量实例标记`deterministically_derived_from_primary`。
- `hold_spin.capacity_transition_distribution`逐组统计`P(C'|C,O)`。`C,O`固定取本步生成结果前的`step_start`，`C'`取本步落入与容量规则全部应用后的下一状态边界；继续时连接下一步`step_start`，退出时连接`terminal`。活动组权重必须精确使用原版`P_step_start(C) × P_current(O|C)`，不得使用候选频率。其默认权重为`0.5`，与容量边际合计不超过`1.0`。
- `variable_capacity_rule`或`unlock_or_upgrade_rule`若完整覆盖全部结构可达`C,O`，且每组只允许一个`C'`，容量推进目标由规则直接复算并标记`deterministic_rule_result`，不评分、不建立第二个扩容Owner。若任一活动组存在两个及以上结构可达`C'`，才评价该条件分布。
- `hold_spin.initial_occupancy_distribution`的Binding必须且只能包含`derived_metric_id`、`derived_instance_dimensions`、`primary_owner_metric_instance`、`shared_semantic_event_set_id`、`relation`、`source_count_to_resource_count`、`mapping_total_and_deterministic`、`source_count_sufficient`、`extra_random_or_state_dependency`、`rule_evidence_sha256`；来源实例固定包含`metric_id`、`source_node_ids`、`instance_dimensions`、`target_group_id`。
- `relation`固定为`deterministic_success_subset`：未进入Hold & Spin的源计数映射为`null`，保留事件重新归一后得到相同`actual_capacity`实例的初始占用分布。来源只能是一个活动Board或Trigger数量实例；Board来源必须指定真实`symbol_id`组，Trigger来源的`target_group_id`必须为`null`。若Trigger数量已由Board数量拥有，必须直接引用Board Owner。
- 映射必须覆盖来源目标全部实际计数支持，两个确定性/充分性字段为`true`，额外随机或状态依赖为`false`，规则证据为有效SHA-256，推送目标与初始占用目标完全一致。每个容量实例推送后只有一个正概率值时使用`degenerate_reachable_support`并删除Binding。
- `hold_spin.current_occupancy_distribution`直接统计全部实际执行步骤开始时的`P(O|C)`；`hold_spin.occupancy_transition_distribution`只统计`P(O'|C,O,C')`。后者的活动组权重必须精确使用原版`P_step_start(C) × P_current(O|C) × P_capacity_transition(C'|C,O)`；固定容量时两个容量因子都是`board_capacity`常量。禁止使用候选步骤频率。
- 重转资源规则只作阻塞型一致性审计；初始次数、逐步扣减、续命触发、重置/增加/替换语义、续命数量、上限与应用时点及退出条件必须逐项可证明。其统计后果已由当前占用、占用推进、Feature时长和终局占用评价，不再新增默认“剩余次数分布”。只有续命数量存在不能由新锁定结果和前置资源状态确定的独立随机性时，才提出任务级条件分布扩展。
- 终局奖项金额构成直接从同一终局结算账本审计，不由占用或回报边际反推。

## 使用约束

- 每个评分指标只有一个Owner和一个`score_budget_key`；同一指标拆分多个作用域时先按`scope_aggregation`聚合，不按实例数量自然增权。容量边际与容量推进各用唯一预算键和`0.5`默认权重，合计不超过容量语义预算`1.0`。
- `derived_diagnostic`和`audit`的`score_weight`固定为0，不进入综合分；按`deterministic_rule_result`退出的容量推进实例同样不进入评分。
- 条件分布只在其条件组内归一化；完整边际由对应主指标负责，禁止再次保存原始联合分布重复计分。
- 可变容量时，初始占用必须条件于同事件全集的`entry`容量实例，当前占用必须条件于`step_start`容量实例，终局占用必须条件于`terminal`容量实例；容量推进再条件于`step_start`容量和当前占用，占用推进再条件于容量推进。不得把终局容量分布复制给步骤或入口。
- 同一`state_id + position_domain`的锁定链由本包拥有占用数量语义；`persistent_state.occupied_position_count_distribution`与`persistent_state.position_count_transition_distribution`必须按`semantic_owner_exclusive`标记不适用，本包四项专用数量指标不得使用该原因码反向退出。
- 目标分桶、实际业务标签、样本单位和条件分母必须在查看候选结果前密封。
