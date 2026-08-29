# Slot Alignment v5指标目录

版本：`5.0.0`

本目录只包含新任务使用的四类十三张指标卡；元素、符号、Feature、线路和作用域只扩展卡内子项，不增加权重。

## N：数值指标

跨完整付费入口或组件的全局数值红线。

| 卡 | 名称 | 类型 | 玩家问题 | Facet |
|---|---|---|---|---|
| N1 | 总RTP | hard_gate | 玩家长期每投注1单位平均返还多少？ | 用户确认总RTP（absolute_probability_error） |
| N2 | 完整付费入口中奖率 | hard_gate | 一次实际付费入口最终获得任意正回报的概率是多少？ | 回报大于0概率（absolute_probability_error） |
| N3 | Feature自然触发率 | hard_gate | 各Feature通过游戏内生规则自然进入的概率是多少？ | 逐Feature自然触发率（absolute_probability_error） |
| N4 | 完整付费入口回报大于等于1x概率 | hard_gate | 一次完整付费入口至少收回实际成本的概率是多少？ | 回报大于等于实际成本概率（absolute_probability_error） |
| N5 | Sigma | hard_gate | 总体及主要作用域的回报波动有多大？ | 总体及适用作用域Sigma（relative_error） |
| N6 | 组件RTP贡献 | hard_gate | 总体返还由Base、各Feature和其他组件分别贡献多少？ | 逐组件RTP贡献（absolute_probability_error） |

## J：中奖结算

完整结算链中的实际派奖结果；Cascade连续消除属于本类。

| 卡 | 名称 | 类型 | 玩家问题 | Facet |
|---|---|---|---|---|
| J1 | 中奖构成 | alignment | 正派奖时通常由哪些元素或线路参与？ | 逐结算元素中奖参与率（absolute_probability_error）；逐规范线路中奖参与率（absolute_probability_error） |
| J2 | 中奖规模 | alignment | 单次中奖由多少符号、轴、Ways或结果构成，实际奖励有多大？ | 单个中奖结果结构规模（wasserstein_1d）；同步中奖结果数量（wasserstein_1d）；实际奖励大小（wasserstein_1d） |
| J3 | 连续结算 | alignment | 一次动作会连续结算多少层，各层中奖规模如何？ | 连续结算总深度（wasserstein_1d）；指定层级中奖规模（wasserstein_1d） |

## P：玩法过程

跨结算步骤的Feature周期和特色机制结果状态。

| 卡 | 名称 | 类型 | 玩家问题 | Facet |
|---|---|---|---|---|
| P1 | 周期节奏 | alignment | Feature开始时给多少免费旋转，完整Feature会持续多久？ | 初始免费旋转次数（wasserstein_1d）；完整Feature持续长度（wasserstein_1d） |
| P2 | 机制结果状态 | alignment | 每次特色机制机会最终落入什么可感知结果状态？ | 逐机制结果状态分布（total_variation） |

## B：盘面呈现

稳定可见盘面的符号数量、位置和空间形态。

| 卡 | 名称 | 类型 | 玩家问题 | Facet |
|---|---|---|---|---|
| B1 | 符号呈现 | alignment | 每个稳定可见盘面中，各符号通常出现多少个？ | 逐符号单盘数量分布（wasserstein_1d） |
| B2 | 盘面空间结构 | alignment | 盘面形状如何变化，玩家关注的关键符号通常出现在哪里？ | 可变盘面形态（structural_wasserstein）；关键符号空间位置密度（structural_wasserstein） |

## 审计

| ID | 名称 | 来源卡 | 内容 |
|---|---|---|---|
| A1 | 完整付费入口倍率分布与长尾 | N2, N4 | full_return_distribution, below_200x, above_or_equal_200x, observed_max, theoretical_max, cap |
| A2 | 结算元素与线路RTP守恒 | J1, N6 | absolute_rtp_contribution, share_of_settlement_rtp, component_sum_check |
| A3 | 连续结算派生统计 | J3 | continuation_probability, rtp_by_depth |
| A4 | 玩法过程派生统计 | P1, P2 | retrigger_count, extension_events, mechanic_occurrence_rate, mechanic_effective_rate, incremental_rtp |
| A5 | 盘面派生统计 | B1, B2 | symbol_presence_rate, fixed_board_rule_consistency |

正式门禁不使用权重、综合分或豁免；审计只展示和复核。
