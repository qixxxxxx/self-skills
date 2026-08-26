# 动态实际Ways容量指标

版本：2.3.0

Owner：`atomic.effective-ways-capacity`

## Owner边界

本包承接非Cascade Ways中不能只由几何布局唯一推出的最终实际容量。它既适用于固定布局下的Split Symbol、符号多重计数、超大符号等变化，也适用于可变轴高或有效格布局再叠加这些非几何规则的组合场景。`geometry_layout_binding`先绑定真实布局，`effective_capacity_formula`再把布局和全部非几何输入合成为最终容量。可变网格的几何基础容量仍由`atomic.variable-grid`作0权重派生核对；同一Cascade步骤的实际容量由`cascade.effective_capacity_distribution_by_depth`拥有；某次中奖实际命中的Ways数仍归通用中奖规模指标。

## 指标清单

| 顺序 | 指标ID | 中文名 | 类型 | 语义角色 | Owner及重叠关系说明 |
|---:|---|---|---|---|---|
| 10 | `effective_ways.capacity_distribution` | 最终实际有效Ways容量分布 | 评分指标 | 主评价 | 按容量作用域和真实几何布局评价非几何规则合成后的最终实际容量；与Cascade层级容量Owner互斥。 |
| 20 | `effective_ways.return_distribution_by_capacity` | 固定布局不同有效Ways容量下的回报分布 | 评分指标 | 主评价 | 只评价非Cascade固定布局步骤；与通用、Cascade及可变网格容量回报互斥。 |

## 口径要求

- 实际有效Ways容量与容量条件回报均固定按非负乘法轴处理：实际位置使用`log10(1+x)`，距离单位固定为1个十倍数量级，不随支持集极值改变。
- `capacity_scope`必须说明容量是整盘口径还是其他稳定结算作用域；不同量纲必须拆分作用域。
- `geometry_layout_domain`必须列出当前容量作用域全部真实固定或可变布局ID；`geometry_layout_binding`必须把每个容量观察唯一绑定到其中一个布局。
- `effective_capacity_formula`必须能从密封盘面与规则事实逐盘复算，结果必须属于`capacity_domain`。
- 可变网格叠加非几何规则时，容量边际按`capacity_scope_id|geometry_layout_id`分组；固定布局自然退化为唯一几何组。几何基础容量不等于最终容量，不能把两者混成一个Owner。
- 容量表示该盘实际可用的Ways机会规模，不是理论最大Ways，也不是某次中奖实际命中的Ways数。
- `return_binding_rule`必须把容量与同一结算事实绑定；固定布局回报由本包评价，可变网格回报仍由`variable_grid.return_distribution_by_capacity`评价；完整步骤没有正派奖时记入独立`0x`桶。
- Cascade步骤不进入本包的容量或回报评分：`cascade.effective_capacity_distribution_by_depth`拥有`P(C|D)`，`cascade.step_return_distribution_by_depth`拥有`P(R|D,C)`。若同一事件集同时实例化本容量指标，必须以`semantic_owner_exclusive`标记不适用。
- 同一指标拆分多个作用域时先按`score_budget_key`聚合，不按作用域数量增加权重。
