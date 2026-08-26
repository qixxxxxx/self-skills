# 持久状态指标

版本：3.0.1
Owner：`atomic.persistent-state`

## Owner边界

`atomic.persistent-state`按状态形态拆分Owner。位置集合使用低维条件分解：占用数量负责规模，给定数量的位置份额负责空间边际，移除/新增数量负责状态推进，位置角色残差只评价扣除同组逐事件可用位置基线后的移除/新增偏向。固定容量时`N`为`position_domain`大小；可变容量时从`position_domain_by_actual_capacity`按实例容量取真实位置域，不把未解锁位置混入基线。Walking Wild等对象若具有稳定身份且能完整一一配对，则额外评价纯配对残差。普通Respin拥有按实际步骤的更细位置过程；Hold & Spin同状态数量仍由专用Owner承接，空间指标用`position_count_owner_bindings`引用同容量数量实例。

## 指标清单

| 顺序 | 指标ID | 中文名 | 类型 | 语义角色 | Owner及重叠关系说明 |
|---:|---|---|---|---|---|
| 10 | `persistent_state.ordered_value_distribution` | 有序标量持久状态值分布 | 评分指标 | 主评价 | 评价等级、累计值或进度在固定观测点的边际。 |
| 20 | `persistent_state.ordered_transition_distribution` | 有序标量持久状态转移分布 | 评分指标 | 主评价 | 只评价给定当前有序值后的下一实际值。 |
| 30 | `persistent_state.categorical_value_distribution` | 类别型持久状态值分布 | 评分指标 | 主评价 | 评价无自然顺序的模式、阶段或命名状态边际。 |
| 40 | `persistent_state.categorical_transition_distribution` | 类别型持久状态转移分布 | 评分指标 | 主评价 | 只评价给定当前类别后的下一类别。 |
| 50 | `persistent_state.occupied_position_count_distribution` | 位置集合占用数量分布 | 评分指标 | 主评价 | 只评价固定观测点同时占用多少个位置；可由同事件域的按步骤Respin保留数量边际化，Hold & Spin数量链由专用Owner承接。 |
| 60 | `persistent_state.position_share_given_occupied_count_distribution` | 指定占用数量下的位置份额分布 | 评分指标 | 主评价 | 仅在`0<count<N`时评价占用token落在哪些真实位置；一一配对残差只补充配对耦合，不替代本项。 |
| 70 | `persistent_state.position_count_transition_distribution` | 位置集合移除新增数量转移分布 | 评分指标 | 主评价 | 给定当前占用数后只评价移除数与新增数；保留数和下一数量确定性复算。 |
| 80 | `persistent_state.position_role_dependence_residual_given_count_transition` | 指定数量转移下的位置角色依赖残差 | 评分指标 | 主评价 | 仅评价`0<角色数量<可用数量`的移除/新增选择偏向；确定全选与`retained`不评分。 |
| 90 | `persistent_state.matched_position_pairing_residual_given_count_transition` | 指定数量转移下的一一配对位置移动残差 | 评分指标 | 主评价 | 仅在对象身份稳定、前后完整一一配对且完整位置对域已密封时，评价扣除候选起点与终点边际后的配对耦合。 |

## 位置指标详细口径

| 指标 | 统计量 | 主要用途 | 目标值含义 | 业务单位 | 防重复边界 |
|---|---|---|---|---|---|
| `persistent_state.occupied_position_count_distribution` | `P(occupied_count)` | 对齐位置集合的总体规模与波动 | 恰好占用0、1、2……个位置的观测占比 | %（位置集合观测占比） | 只拥有数量边际，不评价具体格位 |
| `persistent_state.position_share_given_occupied_count_distribution` | `Q(position_id | actual_capacity, occupied_count, occupied)` | 对齐同容量、同占用数量下的格位偏向 | 指定容量且`0<occupied_count<N`组内，一个占用位置token属于当前真实可用位置的比例 | %（组内占用位置token份额） | 数量由同容量上游Owner负责；未解锁位置不进入支持集 |
| `persistent_state.position_count_transition_distribution` | `P(removed_count, added_count | current_count)` | 对齐保持、释放、扩张、移动和重置的数量过程 | 指定当前占用数下，一次转移移除若干格并新增若干格的机会占比 | %（当前数量组内转移机会占比） | `retained_count`和`next_count`确定性复算，不再成为随机字段 |
| `persistent_state.position_role_dependence_residual_given_count_transition` | `实际移除或新增位置份额 - 同容量组逐事件可用位置基线份额` | 对齐前后容量与数量转移正确后仍存在的位置选择偏向 | 指定`C→C'`、数量转移与活动角色组内，某位置的实际选择份额比真实可用位置基线高或低多少 | 百分点差 | 新增支持集使用`C'`位置域；同一H&S Owner只读取匹配的`C|O|C'`组 |
| `persistent_state.matched_position_pairing_residual_given_count_transition` | `P_actual(pair|count_transition)-P_max_entropy(pair|candidate marginals)` | 对齐Walking Wild、移动标记等对象在位置边际正确后的移动方向、路径分支与配对关系 | 指定数量转移组内，每个真实起点终点对比保持候选起点与终点边际的同支持最大熵基线高或低多少 | 百分点差 | 数量、位置边际和位置角色由原Owner负责；本项只拥有无法由这些边际推出的配对耦合 |

## 派生与交叉关系

有序与类别转移分别以同形态观测边际为条件。位置集合按以下关系复算：

- 总体逐位置占用率由占用数量边际与给定数量的位置份额精确推出，只在报告中展示；
- `retained_count = current_count - removed_count`；
- `next_count = current_count - removed_count + added_count`；
- 持久占用数量只有在同事件集、同观测点且原版步骤暴露权重已密封时，才能按`P(k)=Σ_s P_original(s)P_respin(k|s)`由Respin保留数量边际化；
- 完整补集下，持久条件位置份额仅在`0<k<N`时先按`Q_occupied(i|k,s)=[1-(N-k)Q_rerolled(i|s,k,N-k)]/k`逐步骤复算，再按原版`P(step=s|k)`聚合；不得反向恢复Respin按步骤目标。
- 稳定对象完整一一配对时，在每个`current_count|removed_count|added_count`组内统计实际起点终点联合量，并在同一结构支持上用迭代比例拟合求出保持候选自身起点与终点边际的最大熵基线；二者之差只表达配对耦合，不能推出或替代位置份额与位置角色残差。


## 使用约束

- 有序值边际和有序转移不预设线性或乘法轴；必须按画像属性`ordered_axis_semantics`在候选出现前解析，同一指标实例混合两种轴语义时阻塞并拆分作用域。
- 每个评分指标只有一个Owner和一个score_budget_key；同一指标拆分多个作用域时先按scope_aggregation聚合，不按实例数量自然增权。
- derived_diagnostic和audit的score_weight固定为0，不进入综合分。
- 条件分布只在其条件组内归一化；组权重必须由原版上游数量边际或原版密封事件暴露确定性生成，禁止使用候选频率或完整联合分布再次计算同一边际。一一配对位置移动残差按原版`matched_moving_object_token`数量转移组暴露加权。
- 有序转移、类别转移、位置份额和位置数量转移只保留具有两个及以上结构可达结果的活动条件组；局部退化组移除后按原版密封权重重新归一，全部条件组退化时整项按`degenerate_reachable_support`不适用且不生成评分预算。一一配对位置移动残差只有在同一数量转移组存在至少两个结构可达位置对，且相同起点与终点边际下配对不唯一时活动；唯一配对组移除并重归一。
- `position_share_given_occupied_count_distribution`只为原版正概率且`0<occupied_count<N`的组按占用位置token归一为100%；0占用不建立位置组，N占用固定为每位置`1/N`且不评分。若全部正概率数量只落在0或N，整项为`degenerate_reachable_support`。总体逐位置占用率不得另设评分Owner。
- `position_count_transition_distribution`只保存`current_count::removed_count|added_count`。可确定的保留数和下一数量不得再次作为字段、指标或评分预算。
- `position_role_dependence_residual_given_count_transition`只评价`removed`与`added`。同一个数量转移组内，每次事件分别把1份基线质量均匀分给该角色当次实际可用位置：`removed`使用转移前占用位置，`added`使用转移前未占用位置；已removed的位置不得再次计入added可用集合。再把1份实际质量均匀分给当次真正被移除或新增的位置。两者在事件间等权汇总后相减，每组残差和必须为0，且基线加残差必须仍是合法概率。
- `retained`不建立评分组。当`current_count-removed_count>0`时，位置`i`的retained份额按`[current_count×baseline_removed(i)-removed_count×actual_removed_share(i)]/[current_count-removed_count]`确定性复算。
- `removed`固定`available_count=current_count`，`added`固定`available_count=N-current_count`；只有`0<role_count<available_count`时活动。角色数量为0不建组，角色数量等于可用数量是确定全选、残差恒为0，也不建活动组。组权重由数量转移概率乘对应`removed_count`或`added_count`后归一化。
- `matched_position_transition_bindings`只用于前后对象身份稳定、全部移动对象可无歧义一一配对、无出生或消失混入的转移。除原有身份与规则字段外，必须密封无重复的`reachable_position_pairs`并设置`all_reachable_pairs_covered=true`；每个位置对必须包含唯一且不含`::`或`|`的`pair_id`，并使用真实`position_domain`中的不同原位置和终点。任务合同按Binding顺序为每个活动数量转移组写入完整`pair_id`残差向量；统计脚本必须保存最大熵迭代比例拟合的收敛证明，且每组残差总和、每个起点行和及每个终点列和均为0。每个移动对象产生一个配对token，禁止按最近距离、坐标排序或事后最优匹配猜测身份。若对象身份、完整位置对域或最大熵基线不可证明，继续使用数量转移、位置份额与位置角色残差，不加载配对残差指标。
- 同一`state_id + position_domain`若对应Hold & Spin锁定链，`persistent_state.occupied_position_count_distribution`和`persistent_state.position_count_transition_distribution`必须按`semantic_owner_exclusive`标记不适用。条件位置份额用`same_observation_count_marginal`绑定初始或终局数量Owner；角色残差用`monotone_count_transition`绑定推进Owner，且只允许`removed_count=0`、`added_count=next_count-current_count`。每条绑定必须精确指向单一Owner实例、共享事件集、相同实际容量和规则证据哈希。
- 不建立高维保留位置集合或转移位置集合评分指标。
- 目标分桶、实际业务标签、样本单位和条件分母必须在查看候选结果前密封。
