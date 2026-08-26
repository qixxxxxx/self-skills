# 重转语义

版本：3.1.0

## `feature.respin`：普通重转

按独立计数重新生成全部或部分盘面，可以保留位置，但不要求把持续增加的奖值占格作为终局核心结果。必须记录初始次数、稳定`position_domain`、实际重投范围、`held_position_rule`、延长规则和退出条件；没有保留位置时也要把保留规则明确写为`none`。`entry_source_semantics`必须逐项覆盖`entry_sources`，将游戏规则内生入口与购买、强制测试、测试注入等外生入口明确分开；入口来源构成评分只读取内生入口事件。

所有Respin和Hold & Spin节点都必须提供`stage_graph`和`path_signature_definition`。前者固定包含`entry_stage`、`stages`、`transitions`、`terminal_stages`，每条转移使用`from_stage`、`to_stage`、`branch_id`；后者必须给出有限且唯一的`path_id_domain`，`included_fields`只能为`control_stage_id`、`branch_id`，`excluded_fields`至少排除`award_outcome`、`state_value`、`duration`、`return_bucket`，并用`canonicalization_rule`只对控制流顺序做规范化。

仅在`duration_determinism`完整证明初始次数与最终执行次数一一对应，且不存在提前停止、可变消耗、计数重置或跨步骤依赖时，完整时长才可作为确定性派生不计分；“没有延长规则”本身不能证明时长固定。

普通Respin的位置过程固定拆为三层：按实际执行步骤统计保留位置数量、给定步骤与保留数量统计本步实际重转数量、给定步骤与两类数量统计重转位置份额；不建立高维保留位置集合或重转位置集合评分。下文`N`固定表示`position_domain`中的位置总数。`step_index_semantics`必须固定为`executed_respin_action_index_1_based`：每个Feature内第一次实际执行重转记1，之后按实际执行动作逐次加1；不能混用剩余次数、协议消息序号或状态值。

保留位置来自命名的`state.persistent-state(position_set)`时，`retained_position_state_binding`必须绑定唯一状态节点、业务`state_id`、本步选择前观察点和共享语义事件集。按步骤Respin保留数量是更细粒度Owner；同一事件域与观察点重复时，只允许使用原版步骤暴露权重把它边际化为持久状态占用数量，不能用跨步骤持久边际反推每一步的Respin分布。

`rerolled_set = position_domain - retained_set`完整成立时，本步重转数量可按固定规则结果不计分，但重转位置份额仍是按步骤细粒度Owner。若需生成同观察点的持久状态条件位置份额，只能在共享事件集、相同位置域和完整补集关系均有效时，对`0 < retained_count=k < N`逐步骤使用`Q_occupied(i | k,s) = [1 - (N-k) × Q_rerolled(i | s,k,N-k)] / k`复算，再按原版`P(step=s | k)`聚合；反向派生不成立。其他局部重转独立评价低维位置份额，不建立高维位置集合类别。

玩法`metric_requirements`通过必需包`atomic.respin`加载全部Respin位置过程指标；`state.persistent-state`不再条件加载`atomic.respin`，也不声明这些按步骤capability。若存在同观察点重复语义，由持久状态指标合同引用更细Respin Owner并执行边际化门禁。

`resource_count_derivation_bindings`只用于初始或延长资源数量的单一来源派生。只有同一事件全集中的`board.symbol_count_per_board_distribution`或`trigger.symbol_count_distribution`，通过覆盖全部源计数值的单值确定映射，才能派生对应资源数量分布；不能混合两个来源、使用部分映射或只证明均值。规则固定为一个单值时仍按退化支持处理，不能伪装成上游指标派生。

## `feature.hold-and-spin`：Hold & Spin锁定重转

核心不变量是“合格奖值对象持续锁定并累积到终局”。必须记录盘面容量、初始锁定对象、新锁定条件、剩余次数如何重置或增加、实际可达`terminal_state_domain`、终局如何聚合派奖，以及终局状态、锁定对象、Jackpot、动态奖值与完整Feature回报之间的`terminal_award_binding_rule`。`entry_source_semantics`同样必须逐项区分内生与外生来源，来源构成评分不得混入Feature Buy或测试注入。终局账本还必须能把升级、替换、Collect和Jackpot处理后的每笔最终金额唯一归入`terminal_award_rule`声明的互斥业务组件，用于0权重的终局奖项构成审计。若具体锁定位置会改变后续落入、结算、收集、升级或可见体验，还必须密封稳定`position_domain`，同时建立`state.persistent-state(position_set)`并条件加载`atomic.persistent-state`。同一`state_id + position_domain`的占用数量边际与数量推进由`atomic.hold-and-spin`承接，`persistent_state.occupied_position_count_distribution`和`persistent_state.position_count_transition_distribution`必须标记不适用；持久状态只补充给定数量的位置份额和扣除同组可用位置基线后的移除/新增依赖残差，并通过`position_count_owner_bindings`精确引用初始、终局或推进数量Owner实例，`retained`不评分。

容量固定时，`board_capacity`就是全部占用实例的唯一容量常量；不得再声明`actual_capacity_domain`、`capacity_observation_points`或`capacity_owner_bindings`，也不得实例化`hold_spin.actual_capacity_distribution_by_observation`和`hold_spin.capacity_transition_distribution`后再标记退化不适用。初始、当前、推进和终局占用仍按这个固定容量解释，但不为常量容量增加指标或权重。

存在`variable_capacity_rule`或`unlock_or_upgrade_rule`时，必须密封至少两个正整数构成的`actual_capacity_domain`，把`capacity_observation_points`固定为`entry`、`step_start`、`terminal`，并提供结构化`capacity_transition_contract`。合同以真实`current_capacity|current_occupancy`为键，逐组列出全部结构可达`next_capacity`，完整覆盖所有可达组并绑定规则证据hash；不得只写“会扩盘”一类自然语言。`C,O`取本步开始、生成本步结果之前的实际容量和锁定占用；`C',O'`取本步全部落入、扩容或升级规则应用完成后的同一下一状态边界，继续玩法时是下一步开始，退出时是终局。

可变容量过程固定拆为`P(C) × P(O|C) × P(C'|C,O) × P(O'|C,O,C')`。`hold_spin.actual_capacity_distribution_by_observation`拥有各观察点容量边际`P(C)`；`hold_spin.current_occupancy_distribution`拥有步骤开始占用`P(O|C)`；`hold_spin.capacity_transition_distribution`拥有扩容规律`P(C'|C,O)`；`hold_spin.occupancy_transition_distribution`只拥有容量变化确定后的占用推进`P(O'|C,O,C')`。入口和终局分别使用`P(C_entry) × P(O_initial|C_entry)`与`P(C_terminal) × P(O_terminal|C_terminal)`，不得保存原始高维联合分布再次评分。

若观察点容量完全由可变网格布局或有序持久状态确定，可用`capacity_owner_bindings`把对应活动Primary实例确定性推送到容量边际；绑定不成立时必须独立测量`P(C)`，不能只保留条件占用。若`variable_capacity_rule`或`unlock_or_upgrade_rule`完整证明每个结构可达`C,O`只有一个`C'`，容量转移按规则确定性派生并不评分；不得再用相同扩容结果建立第二个评分Owner。容量边际与容量转移的默认权重各为`0.5`，合计不超过原容量语义预算`1.0`；观察点、入口来源和条件组数量都不得扩张这份预算。

可变容量下若具体锁定位置影响落入、升级、Collect、Jackpot或可见体验，关联的`state.persistent-state(position_set)`必须同时保留全局唯一位置集合`position_domain`和`position_domain_by_actual_capacity`。后者逐容量列出当时真实可用位置，键完整覆盖`actual_capacity_domain`，每个列表长度必须等于容量且属于全局位置域。位置份额实例必须带`actual_capacity`；占用推进空间残差还必须带`current_actual_capacity`与`next_actual_capacity`，只读取H&S Owner中相同`C|O|C'`组，不能把不同容量支持混在一起。

Hold & Spin的`resource_count_derivation_bindings`只允许把初始锁定占用数量绑定到同事件全集、单一来源且完整确定映射的盘面符号数量或触发符号数量分布。初始占用始终为固定单值时仍走退化支持，不得因为“规则固定”而伪造上游派生。

二者不能对同一个Feature节点同时作为主语义。Hold & Spin使用专用语义和过程指标；完整Feature回报与时长仍复用通用Feature周期指标，终局状态与完整回报的依赖由`interaction.hold-spin-return`承接。若锁定对象携带动态奖值或Jackpot，再通过`value_symbol_node_ids`或`jackpot_node_ids`引用对应画像节点，组合`award.value-symbol`或`award.jackpot`。存在独立Collect聚合事件时，`collector_rule`必须通过`collect_node_ids`引用活动`modifier.collect`节点并共享语义事件集；只写自然语言规则但漏建Collect画像视为语义缺口。
