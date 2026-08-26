# 可变网格与容量指标

版本：2.4.0
Owner：`atomic.variable-grid`

## Owner边界

`atomic.variable-grid`只负责真实几何变化：轴高实际变化时评价完整轴高布局；轴高固定但有效格坐标或参与结算几何变化时评价完整有效格布局。几何布局确定性映射出的基础容量始终只作0权重阅读；若同一可变布局还叠加Split Symbol、超大符号或多重计数，最终实际容量由`effective_ways.capacity_distribution`评价。非Cascade可变网格Ways步骤的最终容量条件回报仍由本包评价，纯几何和混合容量两种场景都不另建回报Owner。

## 指标清单

| 顺序 | 指标ID | 中文名 | 类型 | 语义角色 | Owner及重叠关系说明 |
|---:|---|---|---|---|---|
| 10 | `variable_grid.reel_height_layout_distribution` | 完整轴高布局模式分布 | 评分指标 | 主评价 | 仅在`reel_height_variation=true`时加载，评价完整轴高向量。 |
| 20 | `variable_grid.valid_cell_layout_distribution` | 有效格布局模式分布 | 评分指标 | 主评价 | 仅承接轴高固定但有效格坐标或参与结算几何实际变化的有限可枚举布局。 |
| 30 | `variable_grid.capacity_distribution` | 盘面几何基础容量分布 | 审计指标 | 派生诊断 | 由完整几何布局确定性推出；不包含Split Symbol、超大符号或多重计数，始终不计分。 |
| 40 | `variable_grid.return_distribution_by_capacity` | 不同容量下的回报分布 | 评分指标 | 主评价 | 只评价非Cascade可变网格Ways步骤，并与通用、Cascade及固定布局动态Ways容量回报互斥。 |

## 派生与交叉关系

- `variable_grid.reel_height_layout_distribution`只在画像明确`reel_height_variation=true`时加载；不能仅因存在`board.variable-grid`就实例化。
- `variable_grid.valid_cell_layout_distribution`只在`reel_height_variation=false`且完整有效格布局有限可枚举时加载；容量数字不能替代布局身份。
- `variable_grid.capacity_distribution`由当前适用的轴高布局或有效格布局按几何基础容量公式确定性映射。`ways_capacity_mode=layout_plus_non_layout`时，它只与最终容量交叉核对，不得纳入非几何输入。
- `variable_grid.return_distribution_by_capacity`使用最终实际容量：`layout_only`读取几何基础容量，`layout_plus_non_layout`读取`effective_ways.capacity_distribution`同事件事实。它与`settlement.step_return_distribution`、`cascade.step_return_distribution_by_depth`、`effective_ways.return_distribution_by_capacity`互斥，同一步骤只能由一个回报Owner评价。
- 容量条件回报固定按非负乘法轴处理：实际桶位置使用`log10(1+x)`，距离单位固定为1个十倍数量级，不随极端最大倍率改变。


## 使用约束

- 每个评分指标只有一个Owner和一个score_budget_key；同一指标拆分多个作用域时先按scope_aggregation聚合，不按实例数量自然增权。
- derived_diagnostic和audit的score_weight固定为0，不进入综合分。
- 条件分布只在其条件组内归一化；完整边际由对应主指标负责，禁止再次保存原始联合分布重复计分。
- 目标分桶、实际业务标签、样本单位和条件分母必须在查看候选结果前密封。
- `ways_capacity_mode`必须显式为`none`、`layout_only`或`layout_plus_non_layout`。组合容量场景缺少`settlement.effective-ways-capacity`节点、真实布局绑定或最终容量公式时阻塞，不得只用理论最大Ways补位。
