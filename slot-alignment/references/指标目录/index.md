# Slot Alignment 7.0 指标目录

版本：`7.0.0`

本文件由`references/指标目录/index.json`确定性生成，只用于快速阅读卡与Facet；不得手工修改或反向覆盖JSON。详细画像和实例规则见[指标与玩法画像](../01-指标框架.md)，算法与通过值见[评价合同](../02-评价合同.md)。

中奖组、组件、结算模型、Feature、符号和盘面作用域只按框架扩展卡内子项，不增加卡权重。

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
| J1 | 中奖内容构成 | alignment | 每100次有奖结算中，通常会出现哪些玩家看得懂的中奖内容？ | 逐组件中奖组参与率（absolute_probability_error） |
| J2 | 单次结算体验 | alignment | 每一步中奖本身有多大、同时中了几份、这一步合计给了多少倍？ | 主要中奖结构自然档位占比（absolute_probability_error）；主要中奖结构整体移动量（total_variation）；平均主要中奖结构规模（absolute_error）；常见主要中奖结构规模（absolute_error）；较大主要中奖结构规模（absolute_error）；同时中奖数量档位占比（absolute_probability_error）；同时中奖数量整体移动量（total_variation）；平均单次结算奖励（absolute_error）；常见单次结算奖励（absolute_error）；较高单次结算奖励（absolute_error） |
| J3 | 连续结算 | alignment | 一次玩家动作开始后，有奖结算通常会连续走多深？ | 连续结算深度档位占比（absolute_probability_error）；连续结算深度整体移动量（total_variation） |

## P：玩法过程

跨结算步骤的Feature周期和特色机制结果状态。

| 卡 | 名称 | 类型 | 玩家问题 | Facet |
|---|---|---|---|---|
| P1 | 玩法入场与长度 | alignment | 进入玩法时拿到哪档起始资源，一整轮实际会经历多少个主要动作？ | 入场奖励档位占比（absolute_probability_error）；入场奖励档位整体移动量（total_variation）；平均完整玩法长度（absolute_error）；常见完整玩法长度（absolute_error）；较长完整玩法长度（absolute_error） |
| P2 | 特色机制结果 | alignment | 每次特色机制机会最终落入什么可感知结果状态？ | 逐机制结果档位占比（absolute_probability_error）；逐机制结果整体移动量（total_variation） |

## B：盘面呈现

稳定可见盘面的普通符号构成、关键元素数量、主要聚集形态和整体盘面轮廓。

| 卡 | 名称 | 类型 | 玩家问题 | Facet |
|---|---|---|---|---|
| B1 | 元素组成与聚集 | alignment | 盘面整体由哪些普通符号组成，关键元素出现多少，相同元素通常怎样聚集？ | 全盘普通符号组占比（absolute_probability_error）；普通符号组整体移动量（half_l1）；多符号组内部成员占比（absolute_probability_error）；多符号组内部整体移动量（total_variation）；关键元素数量档位占比（absolute_probability_error）；关键元素数量整体移动量（total_variation）；主要堆叠或聚集档位占比（absolute_probability_error）；主要堆叠或聚集整体移动量（total_variation） |
| B2 | 盘面形态 | alignment | 卷轴高矮、有效格数量和盘面参差程度是否接近原版？ | 逐卷轴高度档位占比（absolute_probability_error）；逐卷轴高度整体移动量（total_variation）；平均有效格数（absolute_error）；常见有效格数（absolute_error）；较大有效格数（absolute_error）；平均盘面参差程度（absolute_error）；较明显盘面参差程度（absolute_error） |

## 审计

| ID | 名称 | 来源卡 | 内容 |
|---|---|---|---|
| A1 | 完整付费入口倍率分布与长尾 | N2, N4 | full_return_distribution, below_200x, above_or_equal_200x, observed_max, theoretical_max, cap |
| A4 | 玩法过程派生统计 | P1, P2 | retrigger_count, extension_events, mechanic_occurrence_rate, mechanic_effective_rate, incremental_rtp |
| A5 | 盘面派生统计 | B1, B2 | visual_symbol_group_coverage, key_symbol_presence_rate, terminal_board_diagnostics, fixed_board_rule_consistency |

全部N/J/P/B活动正式项都只按“距离 <= C级通过值”判定，任一失败不得用分数补偿。原版证据不足的实例转为观察；分布缺桶时，证据达标档位仍正式评价，低样本档位和整体移动量转观察。存在观察项时最多只能给出有限范围通过。当前已落定N/J/P/B单项分、卡分和分类分；跨分类综合权重留待后续授权。
