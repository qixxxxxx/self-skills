# Wild与倍率依赖指标

版本：2.1.0
Owner：`interaction.wild-multiplier`

## Owner边界

本包只承接Wild辅助状态与最终倍率状态之间不能由各自边际推出的纯依赖残差。Wild机会内辅助率仍由`atomic.wild-effect`负责；倍率出现、应用和有效值边际仍由`atomic.modifier`负责。

## 指标清单

| 顺序 | 指标ID | 中文名 | 类型 | 语义角色 | Owner及重叠关系说明 |
|---:|---|---|---|---|---|
| 10 | `wild_multiplier.dependence_residual` | Wild辅助状态与倍率依赖残差 | 评分指标 | 主评价 | 从给定Wild状态的倍率概率中减去倍率总体边际，只评分联合依赖。 |

## 匹配约束

- Wild节点的`linked_multiplier_id`必须准确指向活动`modifier.win-multiplier`节点。
- `wild_multiplier_dependency_evidence`必须声明同一共享语义事件集、完整Wild状态域、完整倍率状态域和联合观测规则。
- Wild状态必须包含`none`；倍率状态必须包含`not_occurred`、`not_applied`、`1x`及全部实际有效值，禁止只筛选产生辅助或高倍率的正样本。
- Wild与倍率只是在同一游戏共存，不足以加载本包。

## 使用约束

- 每个评分指标只有一个Owner和一个`score_budget_key`；同一指标拆分多个作用域时先按`scope_aggregation`聚合。
- 状态域、字段顺序、组权重和共享事件集必须在查看候选结果前密封；每个Wild状态组内先平均倍率状态字段误差，再按原版组权重汇总。
- 残差向量不是概率分布；每个Wild状态下的倍率残差和必须为0。
