# Wild实际效果指标

版本：2.5.0
Owner：`atomic.wild-effect`

## Owner边界

`atomic.wild-effect`只评价Wild的实际辅助、辅助发生后的参与格数量、扩展几何和增量经济效果。同一`wild_effect_id`只有一个`effect_owner_node_id`拥有辅助率、实际辅助格数、增量回报和RTP审计；扩展节点仍各自拥有新增格数。

## 指标清单

| 顺序 | 指标ID | 中文名 | 类型 | 语义角色 | Owner及重叠关系说明 |
|---:|---|---|---|---|---|
| 10 | `wild.assistance_rate_given_opportunity` | Wild合格机会实际辅助率 | 评分指标 | 主评价 | 盘面包负责Wild出现和数量，本指标只评价在合格Wild结算机会内真正改变结算的条件命中率。 |
| 20 | `wild.assisting_cell_count_given_assistance_distribution` | Wild实际辅助格数分布 | 评分指标 | 主评价 | 只评价辅助发生后真正参与结算的去重Wild格数量，不重复盘面Wild总数。 |
| 30 | `wild.expanded_cell_count_distribution` | Wild扩展格数分布 | 评分指标 | 主评价 | 无；本指标为该语义变量的唯一Owner。 |
| 40 | `wild.incremental_return_given_assistance_distribution` | Wild实际辅助后的增量回报分布 | 评分指标 | 主评价 | 以已发生实际辅助为条件，只评价同盘去除Wild后的增量派奖。 |
| 50 | `wild.rtp_contribution.audit` | Wild增量RTP贡献审计 | 审计指标 | 审计 | 从同一逐入口账本直接按实际投注重算Wild增量RTP，权重为0。 |

## 派生与交叉关系

`wild.rtp_contribution.audit`不再由两个主指标相乘推导，而是从同一密封逐入口账本直接计算`全部Wild反事实增量派奖 / 全部实际经济投注`。这样能正确包含每次投注对应0次、1次或多次Wild机会的暴露差异。

- `wild.assistance_rate_given_opportunity`与`board.symbol_count_per_board_distribution`交叉复核：盘面包负责Wild出现和数量，本指标只评价合格Wild结算机会内真正改变结算的比例。
- `wild.assisting_cell_count_given_assistance_distribution`只在实际辅助发生后统计真正参与结算的去重Wild格；盘面Wild总数包含未起作用的Wild，扩展格数包含可能未参与最终派奖的新增覆盖格，三者不能互相替代。
- `wild.incremental_return_given_assistance_distribution`与`settlement.step_return_distribution`交叉复核：前者只拥有Wild的反事实增量，后者仍拥有实际步骤总回报。

## 使用约束

- Wild增量回报固定按非负乘法轴处理：实际增量位置使用`log10(1+x)`，距离单位固定为1个十倍数量级；实际辅助格数和扩展格数保持自然线性计数语义，辅助率保持概率语义。
- 实际辅助格数必须由`assisting_cell_identity_rule`逐步骤去重：同一来源格参与多个派奖块只计1；扩展Wild按实际生效格身份计数；盘面可见但未改变结算的Wild不计。身份或归属不能证明时阻塞，不得用派奖大小反推。
- 每个评分指标只有一个Owner和一个score_budget_key；同一指标拆分多个作用域时先按scope_aggregation聚合，不按实例数量自然增权。
- derived_diagnostic和audit的score_weight固定为0，不进入综合分。
- 条件分布只在其条件组内归一化；完整边际由对应主指标负责，禁止再次保存原始联合分布重复计分。
- 目标分桶、实际业务标签、样本单位和条件分母必须在查看候选结果前密封。
