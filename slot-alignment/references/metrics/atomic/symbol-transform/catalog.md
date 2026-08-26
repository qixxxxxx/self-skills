# 符号变形指标

版本：2.1.0
Owner：`atomic.symbol-transform`

## Owner边界

`atomic.symbol-transform`负责真实变换格数、被变换来源符号边际、给定来源后的目标符号、同一多格事件内扣除目标边际后的额外一致性，以及给定改变格数后的位置选择；不保存完整目标向量，也不重复普通盘面符号边际或步骤回报边际。

## 指标清单

| 顺序 | 指标ID | 中文名 | 类型 | 语义角色 | Owner及重叠关系说明 |
|---:|---|---|---|---|---|
| 10 | `transform.changed_cell_count_distribution` | 符号变换格数分布 | 评分指标 | 主评价 | 无；本指标为该语义变量的唯一Owner。 |
| 20 | `transform.source_symbol_distribution` | 实际被变换来源符号构成 | 评分指标 | 主评价 | 提供被变换来源边际，不重复普通盘面总体符号构成。 |
| 30 | `transform.target_symbol_given_source_distribution` | 指定来源下的目标符号分布 | 评分指标 | 主评价 | 只评价给定来源后的目标符号，与来源边际组成非重复条件分解。 |
| 40 | `transform.target_coherence_residual_given_count` | 指定变换格数下的目标一致性残差 | 评分指标 | 主评价 | 只评价同一次多格事件内相对`P(target|source)`独立基线的额外同目标耦合；格数、目标边际、位置和回报均由其他Owner负责。 |
| 50 | `transform.changed_position_pattern_given_count_distribution` | 指定变换格数下的位置模式分布 | 评分指标 | 主评价 | 改变格数边际由原指标拥有，本项只评价同格数下的位置选择。 |

## 派生与交叉关系

无派生指标。目标一致性残差按每个多格事件等权计算实际同目标率，再减去候选自身`P(target|source)`边际给出的独立基线，因此不会重复单格目标构成；无序来源对按画像`source_domain`顺序规范化，来源ID不得包含`|`、`+`或`::`，否则必须先映射为密封稳定ID；位置模式与通用盘面空间结构交叉核对，但只保留变形事件条件下的专属位置语义。


## 使用约束

- 每个评分指标只有一个Owner和一个score_budget_key；同一指标拆分多个作用域时先按scope_aggregation聚合，不按实例数量自然增权。
- derived_diagnostic和audit的score_weight固定为0，不进入综合分。
- 条件分布只在其条件组内归一化；完整边际由对应主指标负责，禁止再次保存原始联合分布重复计分。
- 目标一致性只使用`changed_count|source_a+source_b::same_target_residual`低维字段；无序来源对按画像`source_domain`顺序规范化，每组权重来自密封原版事件暴露。禁止保存完整目标向量或让大事件按格对数量自然增权。
- 目标分桶、实际业务标签、样本单位和条件分母必须在查看候选结果前密封。
