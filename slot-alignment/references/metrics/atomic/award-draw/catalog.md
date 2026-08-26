# Pick与Wheel抽取指标

版本：2.2.0
Owner：`atomic.award-draw`

## Owner边界

`atomic.award-draw`负责给定抽取序号和最小充分状态后的下一奖励结果。完整状态转移、停止、聚合和终局投影均确定，且无链外随机或未承接玩家决策时，该条件链可复算Feature路径与主回报，不限单抽、多抽、有放回或无放回。

## 指标清单

| 顺序 | 指标ID | 中文名 | 类型 | 语义角色 | Owner及重叠关系说明 |
|---:|---|---|---|---|---|
| 10 | `award_draw.outcome_distribution_given_draw_state` | 给定抽取状态的奖励结果分布 | 评分指标 | 主指标 | 以抽取序号和最小充分前序状态为条件；完整有限随机链可复算路径与终局回报时，是抽取、路径和回报三者的唯一评分Owner。 |

## 派生与交叉关系

与Feature路径指标存在受控条件关系：七项完整随机链证明满足时，`feature_cycle.stage_path_distribution`和`feature_cycle.return_distribution_by_stage_path`由本指标及密封状态转移链派生；任一证明不满足时，路径频率与路径回报继续独立评价。


## 使用约束

- 每个评分指标只有一个Owner和一个score_budget_key；同一指标拆分多个作用域时先按scope_aggregation聚合，不按实例数量自然增权。
- derived_diagnostic和audit的score_weight固定为0，不进入综合分。
- `draw_state_definition`只保留会改变下一次概率的最小充分状态：无放回使用剩余奖池状态，保证奖使用保证进度，独立有放回不伪造历史维度。
- 每个条件组单独归一化；结构上只有一个可达奖励的组保留规则证据但不计分。
- 七项`outcome_return_equivalence`证明前五项全为true、后两项全为false时，Feature路径和回报才能从完整Atomic链派生。
- 链外额外随机奖励、非确定聚合或未承接玩家决策时，Atomic奖励结果与Feature路径/回报都保留评分Owner。
- 禁止再建立逐抽边际评分或完整抽取序列签名，避免同一结果链重复计分和高维稀疏。
- 目标分桶、实际业务标签、样本单位和条件分母必须在查看候选结果前密封。
