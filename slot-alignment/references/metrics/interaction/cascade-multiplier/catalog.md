# Cascade与倍率依赖指标

版本：2.2.0
Owner：`interaction.cascade-multiplier`

## Owner边界

`interaction.cascade-multiplier`只评价`P(倍率|层级)-P(倍率)`残差。同深度仍有随机性时才评分；depth对完整倍率状态唯一确定时，该残差与倍率边际均派生。

## 指标清单

| 顺序 | 指标ID | 中文名 | 类型 | 语义角色 | Owner及重叠关系说明 |
|---:|---|---|---|---|---|
| 10 | `cascade_multiplier.dependence_by_depth` | Cascade层级与倍率依赖残差 | 评分指标 | 主评价 | Atomic指标负责Cascade深度与倍率边际；本指标只评价条件概率减去边际概率后的纯依赖残差。 |

## 派生与交叉关系

`same_depth_multiplier_randomness=false`且深度到完整倍率状态的映射可核验时，本指标由`cascade.depth_distribution`及密封映射确定性派生；`true`时保留残差评分。

- `cascade_multiplier.dependence_by_depth`与`cascade.depth_distribution`、`multiplier.occurrence_rate`、`multiplier.effective_value_distribution`交叉复核：Atomic指标负责Cascade深度与倍率边际；本指标只评价条件概率减去边际概率后的纯依赖残差。

## 使用约束

- 每个评分指标只有一个Owner和一个score_budget_key；同一指标拆分多个作用域时先按scope_aggregation聚合，不按实例数量自然增权。
- derived_diagnostic和audit的score_weight固定为0，不进入综合分。
- 残差字段使用`depth::multiplier_state`；每个层级先平均字段绝对误差，再按任务合同中候选前密封的原版层级权重汇总。
- 目标分桶、实际业务标签、样本单位和条件分母必须在查看候选结果前密封。
