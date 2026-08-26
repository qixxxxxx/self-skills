# 重转过程指标

版本：2.6.0
Owner：`atomic.respin`

## Owner边界

`atomic.respin`负责初始与延长资源，并把普通Respin位置过程低维拆为“按步骤的保留数量、给定保留数量后的重转数量、给定两类数量后的重转位置份额”；下文`N`固定表示`position_domain`大小。不建立高维保留位置集合或重转位置集合评分。三项位置过程都是按实际步骤的细粒度Owner；持久状态只负责自身跨步骤观测边际，满足严格事件与权重门禁时可从Respin目标边际化，不能反向派生Respin目标。

## 指标清单

| 顺序 | 指标ID | 中文名 | 类型 | 语义角色 | Owner及重叠关系说明 |
|---:|---|---|---|---|---|
| 10 | `respin.initial_grant_distribution` | 初始重转次数分布 | 评分指标 | 主评价 | 通常拥有初始资源数量；完整单一符号计数映射成立时才派生。 |
| 20 | `respin.extension_grant_distribution` | 重转延长赠送次数分布 | 评分指标 | 主评价 | 通常拥有每步新增资源数量；完整单一符号计数映射成立时才派生。 |
| 30 | `respin.retained_position_count_distribution_by_step` | 按步骤的保留位置数量分布 | 评分指标 | 主评价 | 评价每个实际执行步骤开始时保留多少位置；跨步骤持久边际不能反推本项。 |
| 40 | `respin.rerolled_position_count_distribution_given_retained_count` | 给定保留数量后的重转位置数量分布 | 评分指标 | 主评价 | 保留数量已固定后评价本步重转多少位置；完整固定数量规则可不计分。 |
| 50 | `respin.rerolled_position_share_given_counts_distribution` | 给定保留与重转数量后的位置份额分布 | 评分指标 | 主评价 | 仅在`0<rerolled_count<N`时评价重转位置token空间份额；0不建组，N固定均匀。 |
| 60 | `respin.extension_rate` | 重转延长发生率 | 审计指标 | 派生诊断 | 由延长赠送次数分布的0次桶精确推出，不独立计分。 |

## 指标详细口径

| 指标 | 统计量 | 主要用途 | 目标值含义 | 业务单位 | 防重复边界 |
|---|---|---|---|---|---|
| `respin.initial_grant_distribution` | `P(initial_grant_count)` | 对齐进入玩法时的初始重转资源 | 初始获得0、1、2……次重转的入口占比 | %（重转入口占比） | 完整单一符号计数映射成立时由上游派生；固定单值走退化支持 |
| `respin.extension_grant_distribution` | `P(extension_grant_count)` | 对齐每步续命、增加或重置的资源数量 | 合格步骤新增0、1、2……次重转的步骤占比 | %（合格重转步骤占比） | 完整单一符号计数映射成立时由上游派生；发生率由本分布0次桶复算 |
| `respin.retained_position_count_distribution_by_step` | `P(retained_count | executed_step_index)` | 对齐不同实际步骤开始时的保留规模 | 指定步骤组内恰好保留若干位置的步骤占比 | %（指定步骤组内重转步骤占比） | 本项拥有步骤条件分布；只允许向同事件域持久边际聚合，不允许反向派生 |
| `respin.rerolled_position_count_distribution_given_retained_count` | `P(rerolled_count | step, retained_count)` | 对齐给定保留规模后的实际重转范围大小 | 指定步骤与保留数量组内，实际重转若干位置的步骤占比 | %（指定条件组内重转步骤占比） | 不评价具体格位；完整固定数量规则可用`deterministic_rule_result` |
| `respin.rerolled_position_share_given_counts_distribution` | `P(position_id | step, retained_count, rerolled_count, rerolled)` | 对齐数量都正确后的重转格位偏向 | 指定`0<rerolled_count<N`组内，一个重转位置token属于对应真实位置的比例 | %（指定条件组内重转位置token份额） | 数量由前两项负责；0不建组，N固定为每位置`1/N`且不评分 |
| `respin.extension_rate` | `1-P(extension_grant_count=0)` | 直观阅读续命发生频率 | 合格步骤实际新增至少一次重转的比例 | %（合格重转步骤占比） | 由延长赠送次数分布确定性派生，权重为0 |

## 派生与交叉关系

- `respin.extension_rate` ← `respin.extension_grant_distribution`：由延长赠送次数分布的0次桶精确推出，不独立计分。
- `persistent_state.occupied_position_count_distribution` ← `respin.retained_position_count_distribution_by_step`：仅限共享事件集、同一选择前观察点和原版步骤暴露权重已密封，按`P(k)=Σ_s P_original(s)P_respin(k|s)`边际化。
- `persistent_state.position_share_given_occupied_count_distribution` ← `respin.rerolled_position_share_given_counts_distribution`：仅限位置域相同、共享事件集及`rerolled_set=position_domain-retained_set`逐步完整成立；对`0<k<N`按`Q_occupied(i|k,s)=[1-(N-k)Q_rerolled(i|s,k,N-k)]/k`逐步骤复算，再按原版`P(step=s|k)`聚合。


## 使用约束

- 每个评分指标只有一个Owner和一个score_budget_key；同一指标拆分多个作用域时先按scope_aggregation聚合，不按实例数量自然增权。
- derived_diagnostic和audit的score_weight固定为0，不进入综合分。
- `step_index_semantics`必须严格等于`executed_respin_action_index_1_based`：每个Feature内第一次实际执行重转记1并按动作递增；不得使用剩余次数、协议包序号或持久状态值冒充步骤轴。
- 初始与延长次数只有在`resource_count_derivation_bindings`绑定同一事件全集、单一`board.symbol_count_per_board_distribution`或`trigger.symbol_count_distribution`，并覆盖全部源计数值的单值映射时才能确定性派生。不能混合来源、缺桶、使用一对多映射或只证明均值/发生率。固定单值仍走`degenerate_reachable_support`。
- 保留数量与持久状态数量只有事件集、观测点和原版步骤暴露权重完全相同时，才能从本项向持久状态边际化；只引用同一`state_id`不足以判定，跨步骤持久边际永远不能反推步骤分布。
- 固定全盘、固定局部数量或完整补集规则可以使`rerolled_position_count_distribution_given_retained_count`成为`deterministic_rule_result`，但不会自动使位置份额成为常量结果。
- 重转位置份额只为原版正概率且`0<rerolled_count<N`的步骤、保留数量和重转数量组归一化。0不建立位置组，N固定为每位置`1/N`且不评分；若全部正概率重转数量只落在0或N，整项为`degenerate_reachable_support`。组权重由步骤暴露、保留数量目标、条件重转数量目标和实际重转数量确定性生成，禁止使用候选频率。
- 不保存高维保留位置集合、重转位置集合或二者联合类别；数量和条件位置份额已经覆盖主流可测体验语义。
- 条件分布只在其条件组内归一化；完整边际由对应主指标负责，禁止再次保存原始联合分布重复计分。
- 三项按步骤位置条件分布只保留具有两个及以上结构可达结果的活动组；局部退化组移除后按原版密封权重重新归一，全部条件组退化时整项按`degenerate_reachable_support`不适用且不生成评分预算。完整固定数量规则仍可使用更严格的`deterministic_rule_result`。
- 目标分桶、实际业务标签、样本单位和条件分母必须在查看候选结果前密封。
