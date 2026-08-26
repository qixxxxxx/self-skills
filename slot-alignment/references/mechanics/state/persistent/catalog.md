# 持久状态语义

版本：2.9.0

`state.persistent-state`统一表达持久倍率、收集进度、等级、Sticky Wild位置、解锁格和其他跨边界状态。`persistence_horizon`必须明确是跨Cascade步骤、Feature旋转、付费入口还是会话；“持久”不能只凭界面观感判断。位置数量由其他专用玩法Owner承接时，空间指标必须用`position_count_owner_bindings`引用精确指标实例，不能只写“来自Hold & Spin”。

`state_shape`只允许以下三种标准形状：

- `ordered_scalar`：有明确次序的计数、等级、倍率或进度值，同时密封`value_domain`、`value_order`和`ordered_axis_semantics`；若其他玩法按命名事件绑定状态转移，还必须用`transition_event_domain`列出全部可绑定事件ID；
- `categorical`：没有自然远近关系的离散状态，同时密封`value_domain`；
- `position_set`：Sticky Wild、Walking Wild、解锁格或其他位置集合，同时密封稳定且无重复的全局`position_domain`。容量可变时再密封`position_domain_by_actual_capacity`：容量键完整覆盖实际容量域，每个值是该容量下真实可用位置列表，长度等于容量且属于全局位置域。位置集合评价占用数量、给定数量后的位置份额、移除/新增数量转移及位置依赖残差；只有对象身份稳定且能完整一一配对时，才增加起点终点纯配对残差。

画像至少密封：

- 状态ID及上述标准形状；
- 每个标准观察点；
- 初始值、合法值域、状态转移和重置；
- 哪个玩法消费或改变该状态。

`position_set`存在跨观察点转移时，还要用`position_transition_bindings`逐项绑定业务转移事件、转移前观察点、转移后观察点和前后状态共同所属的密封语义事件集。

Walking Wild、移动标记或等价机制若需要评价移动方向与路径耦合，还必须提供`matched_position_transition_bindings`。每条绑定固定包含`transition_event`、前后观察点、共享事件集、对象身份规则、前后配对规则、`complete_bijective_matching=true`、`birth_or_death_possible=false`、无重复的`reachable_position_pairs`、`all_reachable_pairs_covered=true`及规则证据哈希。每个位置对固定包含唯一且不含`::`或`|`的`pair_id`、`origin_position_id`和`destination_position_id`，起点与终点必须来自真实`position_domain`且不得相同。只有协议ID、服务端状态ID或同等强度证据能无歧义识别同一对象，并证明位置对域覆盖全部结构可达移动时才成立；禁止按最近距离、坐标排序或事后最优匹配猜测身份。

固定容量时，下文`N`表示`position_domain`大小；可变容量时，位置份额实例带`actual_capacity`并取对应位置域大小，位置角色残差实例同时带`current_actual_capacity`和`next_actual_capacity`。一次位置集合转移只直接统计`removed_count`和`added_count`。`retained_count = current_count - removed_count`、`next_count = current_count - removed_count + added_count`必须确定性复算，不能再次作为独立随机维度评分。

空间转移只评价`removed`与`added`依赖残差。对同一个`current_count × removed_count × added_count`组：

- `removed`的可用位置是每次转移前实际占用的位置；每个事件先在这些位置上建立均匀可用基线，再与实际移除位置份额相减；
- `added`的可用位置是每次转移前实际未占用的位置；每个事件先在这些位置上建立均匀可用基线，再与实际新增位置份额相减；
- 每个活动组的残差和必须为0；`removed`的`available_count=current_count`，`added`的`available_count=N-current_count`，且只有`0 < role_count < available_count`时活动；
- `retained`不评分。若`current_count - removed_count > 0`，其位置份额由同组转移前占用份额与实际removed份额确定性复算。

若某个`transition_event`命中完整一一配对移动合同，则按`current_count × removed_count × added_count`分组统计真实起点终点联合量，并在相同`reachable_position_pairs`支持上用迭代比例拟合求出同时保持候选自身起点与终点边际的最大熵基线。指标只评价“实际联合量－同边际最大熵基线”的纯配对残差；每组残差总和、每个起点行和及每个终点列和都必须为0。数量转移、绑定前后全部占用位置边际以及移除/新增位置选择仍由原有Owner负责，不得因配对残差而停用。对象可能出生、消失、合并、拆分、无法稳定识别、完整位置对域不可证明或拟合不收敛时不得加载该指标。

持久状态只负责状态占用与转移。状态作为倍率、Wild、Collect进度或触发条件时，分别组合对应修饰器或触发语义，避免重复定义同一效果。

位置集合的总占用概率只作阅读摘要：它必须由占用数量边际与给定数量的位置份额确定性复算，不再建立独立评分指标。条件位置份额只对原版目标概率大于0且`0 < occupied_count < N`的数量组评分；`occupied_count=0`不建组，`occupied_count=N`固定为每位置`1/N`且不作为活动评分组。全部正概率数量只落在`0`或`N`时，整项按`degenerate_reachable_support`不适用。

## 外部位置数量Owner绑定

同一位置集合若正是Hold & Spin锁定链，数量边际和数量推进仍由`atomic.hold-and-spin`拥有；持久状态仅补充空间偏向。此时每条`position_count_owner_bindings`必须且只能包含六个字段：

| 字段 | 固定含义 |
|---|---|
| `consumer_metric_id` | 只能是条件位置份额或位置角色依赖残差指标ID |
| `consumer_instance_dimensions` | 固定容量：条件位置份额为`state_id + observation_point`，角色残差为`state_id + transition_event`；可变容量分别再加入`actual_capacity`，或`current_actual_capacity + next_actual_capacity` |
| `primary_owner_metric_instance` | 固定包含`metric_id`、仅含一个节点ID的`source_node_ids`和`instance_dimensions`，并引用实际Hold & Spin指标实例 |
| `shared_semantic_event_set_id` | 持久状态节点与Hold & Spin节点共同声明的同一事件集 |
| `relation` | 只允许`same_observation_count_marginal`或`monotone_count_transition` |
| `rule_evidence_sha256` | 绑定观察点或单调推进规则的证据哈希 |

允许关系只有两类：条件位置份额可绑定`hold_spin.initial_occupancy_distribution`或`hold_spin.terminal_occupied_cell_count_distribution`；位置角色残差可绑定`hold_spin.occupancy_transition_distribution`。后者必须满足`removed_count=0`、`added_count=next_count-current_count`，并只为`0 < added_count < N-current_count`的正概率组建立活动残差。来源实例的`actual_capacity`必须等于`position_domain`大小。

## 与普通Respin的边际关系

`atomic.respin`拥有按实际执行步骤的细粒度位置过程，持久状态不能反向恢复这些步骤目标。只有共享同一语义事件集、持久观察点就是步骤选择前观察点且原版步骤暴露权重已密封时，才允许从Respin向持久状态边际化：

- 占用数量：`P_persistent(k) = Σ_s P_original(step=s) × P_respin(k | step=s)`；
- 条件位置份额：完整满足`rerolled_set = position_domain - retained_set`且`0 < k < N`时，先逐步骤复算`Q_occupied(i | k,s) = [1 - (N-k) × Q_rerolled(i | s,k,N-k)] / k`，再按由原版步骤暴露与保留数量目标得到的`P_original(step=s | k)`聚合。

事件全集、观察点、位置域、完整补集等式或原版权重任一不成立时必须分别测量；禁止用跨步骤持久边际反推按步骤Respin指标。

`ordered_axis_semantics`只允许两类：计数、等级、进度使用`natural_linear`；累计倍率或同量纲经济价值使用`nonnegative_multiplicative`。同一`state_id`的值分布和转移分布必须共用这一声明，不能分别选择距离尺度。
