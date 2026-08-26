# 中奖结算结构指标

版本：2.3.0
Owner：`atomic.settlement-diversity`

## Owner边界

中奖符号边际与指定中奖符号后的实际派奖规模组成非重叠条件分解。完整非Cascade结算步骤总回报只按`component×state×board_phase`保留一个Owner：同一步骤混合Payline、Ways、Count Pay、Cluster等结算时，先汇总全部实际派奖再统计一次，不能按`settlement_type`复制。中奖符号、规模、并发派奖块和线路几何仍可按各自结算类型拆分。固定线的独立结算块由`aggregation_unit`决定，且必须与`winning_scale_dimension`使用合法组合；线路多样性比较规范几何而不是协议编号。Cluster近门槛结构只在画像明确声明重要时按盘评价；同一连通块不得同时进入已派奖规模与未中奖专项。

## 指标清单

| 顺序 | 指标ID | 中文名 | 类型 | 语义角色 | Owner及重叠关系说明 |
|---:|---|---|---|---|---|
| 10 | `settlement.winning_symbol_distribution` | 中奖符号构成 | 评分指标 | 主指标 | 负责实际独立正派奖块的中奖符号边际；可由盘面数量确定性推出的Count Pay实例不重复评分。 |
| 20 | `settlement.scale_given_symbol_distribution` | 指定中奖符号下的中奖规模分布 | 评分指标 | 主指标 | 固定线按合法聚合口径使用连中轴数或聚合中奖线数；同源Count Pay数量尾部不重复评分。 |
| 30 | `settlement.symbol_rtp_contribution_distribution` | 各中奖符号RTP贡献审计 | 审计指标 | 审计 | 与组件RTP贡献交叉复核，不进入评分。 |
| 40 | `settlement.step_return_distribution` | 完整非Cascade结算步骤总回报分布 | 评分指标 | 主指标 | 每个完整步骤只汇总一次全部结算类型派奖；只负责未被Cascade层级、可变网格容量或动态Ways有效容量回报Owner覆盖的步骤。 |
| 50 | `settlement.paid_result_block_count_per_winning_step_distribution` | 单个中奖步骤的独立派奖块数量分布 | 评分指标 | 主指标 | 评价同一步骤中实际并发的独立正派奖块数量。 |
| 60 | `payline.winning_line_geometry_distribution` | 中奖线几何路径分布 | 评分指标 | 主指标 | 只适用于固定赔付线，先用线路定义把编号映射为规范坐标路径。 |
| 70 | `cluster.nonwinning_connected_group_size_given_symbol_distribution` | 指定符号与总数量下的单盘最大未中奖连通块大小分布 | 评分指标 | 主指标 | 仅在`near_miss_structure_relevant`命中时加载；给定全盘精确总数量后，每盘每符号只取最大未中奖连通块并包含0。 |

## 使用约束

- 单步回报固定按非负乘法轴处理：实际桶位置使用`log10(1+x)`，距离单位固定为1个十倍数量级。中奖规模轴不预设；必须按玩法画像的`winning_scale_axis_semantics`在候选出现前解析为自然线性或非负乘法语义。
- Cluster已派奖连通块进入`settlement.scale_given_symbol_distribution`；只有画像明确声明近门槛结构重要时，未达门槛连通块才参与逐盘最大值，完全没有时记0，同一连通块不得进入两边。
- 固定线必须通过密封`line_definitions`把实际`line_id`映射为按轴顺序排列的规范坐标路径；跨原版与候选禁止直接比较线路编号。
- 固定线只允许`per_line + matched_reel_count`或`per_step_symbol + winning_line_count`；其他组合阻塞指标匹配。
- Count Pay若由同一可见完整盘面的精确符号数量和确定性派奖聚合规则直接产生，中奖符号边际与实际计数尾部均只能派生展示或标记不适用。
- 上述Count Pay关系必须与`board.symbol_count_per_board_distribution`及`trigger.symbol_count_distribution`双向记录；不同计数范围只有在密封不可推出证据后才可独立评分。
- 条件分布只在组内归一化，条件组权重在候选出现前密封；支持少于两个实际值的组不计分。
- 完整非Cascade步骤总回报不含`settlement_type`作用域；同一步骤的Payline、Ways、Count Pay、Cluster等派奖必须先汇总后只统计一次，0x步骤同样只统计一次。中奖符号、规模、并发块和线路几何可继续按`settlement_type`拆分。
- 完整非Cascade步骤总回报与Cascade分层回报、可变网格容量回报、动态Ways有效容量回报按完整步骤互斥。
- 审计指标权重固定为0；同一指标的多个作用域先按`scope_aggregation`聚合。
