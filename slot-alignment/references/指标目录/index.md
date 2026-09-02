# Slot Alignment v5指标目录

版本：`5.3.0`

本目录只包含新任务使用的四类十三张指标卡；中奖组、组件、结算模型、Feature、符号和盘面作用域只按框架规则扩展卡内子项，不增加权重。

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
| P1 | 周期节奏 | alignment | Feature开始时给多少免费旋转，完整Feature会持续多久？ | 初始免费旋转次数（wasserstein_1d）；完整Feature持续长度（wasserstein_1d） |
| P2 | 机制结果状态 | alignment | 每次特色机制机会最终落入什么可感知结果状态？ | 逐机制结果状态分布（total_variation） |

## B：盘面呈现

稳定可见盘面的视觉符号组密度、关键符号数量、位置和空间形态。

| 卡 | 名称 | 类型 | 玩家问题 | Facet |
|---|---|---|---|---|
| B1 | 可见符号构成 | alignment | 每个正式稳定盘面中，主题/普通符号组占比和关键特殊符号数量如何？ | 逐视觉符号组单盘密度分布（wasserstein_1d）；逐关键符号单盘数量分布（wasserstein_1d） |
| B2 | 盘面空间结构 | alignment | 盘面形状如何变化，玩家关注的关键符号通常出现在哪里？ | 可变盘面形态（structural_wasserstein）；关键符号空间位置密度（structural_wasserstein） |

## 审计

| ID | 名称 | 来源卡 | 内容 |
|---|---|---|---|
| A1 | 完整付费入口倍率分布与长尾 | N2, N4 | full_return_distribution, below_200x, above_or_equal_200x, observed_max, theoretical_max, cap |
| A4 | 玩法过程派生统计 | P1, P2 | retrigger_count, extension_events, mechanic_occurrence_rate, mechanic_effective_rate, incremental_rtp |
| A5 | 盘面派生统计 | B1, B2 | visual_symbol_group_coverage, key_symbol_presence_rate, terminal_board_diagnostics, fixed_board_rule_consistency |

全部N/J/P/B必需项先过C级线，任一失败不得用分数补偿。当前已落定N/J卡分和分类分；N/J跨分类权重及P/B评分留待后续授权。
