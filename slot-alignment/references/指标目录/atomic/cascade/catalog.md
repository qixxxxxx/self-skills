# Cascade过程指标

版本：2.4.0
Owner：`atomic.cascade`

## Owner边界

`atomic.cascade`负责Cascade链深度、每层补入格数、给定补入数量后的稳定分区空间分配、补入符号、已到达各层后的实际有效容量，以及“层级 × 实际有效容量”条件回报。完整结果固定拆为`P(D) × P(C|D) × P(R|D,C)`；各层继续概率由深度分布派生，仅用于诊断。同一Cascade步骤不再进入固定布局动态Ways容量、可变网格容量回报或其他通用步骤回报评分。

## 指标清单

| 顺序 | 指标ID | 中文名 | 类型 | 语义角色 | Owner及重叠关系说明 |
|---:|---|---|---|---|---|
| 10 | `cascade.depth_distribution` | Cascade深度分布 | 评分指标 | 主评价 | 无；本指标为该语义变量的唯一Owner。 |
| 20 | `cascade.continuation_rate_by_step` | 各层继续概率 | 审计指标 | 派生诊断 | 由Cascade深度生存分布精确推出；跨层条件概率不使用Total Variation独立计分。 |
| 30 | `cascade.refill_cell_count_distribution_by_depth` | 各层新补入有效格数分布 | 评分指标 | 主评价 | 只评价到达该层后补入多少格，不重复层级到达频率或补入符号构成。 |
| 40 | `cascade.refill_symbol_distribution` | 连消补充符号分布 | 评分指标 | 主评价 | 只统计真实新补入格的符号构成。 |
| 50 | `cascade.refill_partition_count_vector_given_total_distribution` | 指定补入格数下的分区计数向量分布 | 评分指标 | 主评价 | 给定层级与补入总数后，只评价新格分配到哪些稳定轴列或区域。 |
| 60 | `cascade.effective_capacity_distribution_by_depth` | 各Cascade层实际有效容量分布 | 评分指标 | 主评价 | 活动目标只包含容量支持非退化的深度；固定容量深度不进入本指标目标。 |
| 70 | `cascade.step_return_distribution_by_depth` | 各Cascade层与有效容量下的单步回报分布 | 评分指标 | 主评价 | 保留全部可达深度，包括固定容量深度的唯一容量组，并与其他步骤回报Owner互斥。 |

## 派生与交叉关系

- `cascade.continuation_rate_by_step` ← `cascade.depth_distribution`：由Cascade深度生存分布精确推出；跨层条件概率不使用Total Variation独立计分。
- `cascade.refill_cell_count_distribution_by_depth`负责补入数量边际；`cascade.refill_partition_count_vector_given_total_distribution`只在给定层级和数量后评价稳定轴列/区域分配；`cascade.refill_symbol_distribution`只评价新格符号构成。三者组成非重叠分解并做守恒交叉核对。
- `cascade.effective_capacity_distribution_by_depth`以`cascade.depth_distribution`为条件，统计`P(C|D)`；同一Cascade事件集下与`effective_ways.capacity_distribution`互斥。`variable_grid.capacity_distribution`只保留几何到容量的0权重确定性审计。
- `cascade.step_return_distribution_by_depth`同时以前述深度和容量指标为条件，只统计`P(R|D,C)`；它与`settlement.step_return_distribution`、`variable_grid.return_distribution_by_capacity`、`effective_ways.return_distribution_by_capacity`互斥。
- 设`p_d=P_original(D_total>=d)`，`A`为容量支持数至少为2的活动深度集合。容量指标的目标组和`group_weights`都只包含`d∈A`，组权重为`p_d / Σ(j∈A)p_j`；固定容量深度不进入容量目标，由规则证据及回报合同的唯一容量组保留。若`A`为空，整个容量指标按`degenerate_reachable_support`不适用。
- 回报不使用上述活动集合裁剪。每个原版可达深度和正概率容量都必须保留，固定容量深度仍有唯一容量组；回报组权重为`p_d × P_original(C=c|d)`再在全部回报条件组内归一。两类权重都禁止使用候选频率。


## 使用约束

- 各层单步回报固定按非负乘法轴处理：实际桶位置使用`log10(1+x)`，距离单位固定为1个十倍数量级；补入格数保持自然线性轴，补入分区向量按无序真实向量类别比较。各层有效容量从画像`effective_capacity_axis_semantics`解析轴：有效格等自然计数用`natural_linear`，Ways或组合容量用`nonnegative_multiplicative`，报告单位使用`effective_capacity_unit_zh`。
- 补入空间指标必须使用`refill_partition_rule`密封的真实分区ID、顺序和坐标映射；0补入组、单一分区和确定性唯一向量不评分。不得保存完整下一盘签名，也不得用候选分区暴露生成条件组权重。
- 每个评分指标只有一个Owner和一个score_budget_key；同一指标拆分多个作用域时先按scope_aggregation聚合，不按实例数量自然增权。
- derived_diagnostic和audit的score_weight固定为0，不进入综合分。
- 条件分布只在其条件组内归一化；完整边际由对应主指标负责，禁止再次保存原始联合分布重复计分。
- 每个Cascade步骤必须提供按画像定义计算的真实`effective_capacity`；固定容量也使用带实际值的固定组，禁止填理论上限或占位桶。
- 各层容量指标与单步回报指标必须绑定同一`cascade_settlement_step`事件全集、同一链ID和层级。非退化深度的回报容量支持必须与容量指标目标完全一致；未出现在容量目标中的固定容量深度必须在回报中恰好保留一个真实容量组。
- 目标分桶、实际业务标签、样本单位和条件分母必须在查看候选结果前密封。
