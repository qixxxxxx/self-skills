# 触发结构指标

版本：2.3.0
Owner：`atomic.trigger`

## Owner边界

`atomic.trigger`直接审计每个Trigger节点的规则与节点引用，并评价不能由通用盘面Owner确定性推出的触发数量、位置结构及随机事件在自身合格机会内的成功率；已进入Feature后的游戏内生来源构成仍按目标Feature汇总，包括严格匹配的`feature.bonus-sequence`外层周期。自然触发总频率由`core.feature.natural_trigger_rate`拥有。Feature Buy、强制测试、测试注入、运营覆盖和其他外生选择不属于游戏随机模型目标，必须从来源构成评分事件集排除。

## 指标清单

| 顺序 | 指标ID | 中文名 | 类型 | 语义角色 | Owner及重叠关系说明 |
|---:|---|---|---|---|---|
| 5 | `trigger.rule_consistency.audit` | 触发规则一致性审计 | 审计指标 | 审计 | 每个Trigger节点直接加载；缺失、无法证明或与权威规则不一致均阻塞FORMAL。 |
| 10 | `trigger.symbol_count_distribution` | 触发符号数量分布 | 评分指标 | 主评价 | 同一可见盘面、符号和计数范围由盘面数量Owner承接；只有不可推出实例独立评分。 |
| 20 | `trigger.position_pattern_given_count_distribution` | 指定数量下的触发位置组合分布 | 评分指标 | 主评价 | 无损实际坐标可推出同符号盘面空间摘要时，后者对应实例不重复评分。 |
| 30 | `trigger.random_event_rate_given_eligibility` | 随机事件合格机会触发率 | 评分指标 | 主评价 | 每个随机触发节点按自身合格判定机会计分，不用Feature总入口数反推。 |
| 40 | `trigger.entry_source_distribution` | 游戏内生Feature入口来源构成 | 评分指标 | 主评价 | Core负责游戏内生入口总频率；本指标只评价已进入Feature后的内生规则来源构成，外生入口不计分。 |

## 派生与交叉关系

- `trigger.rule_consistency.audit`直接绑定`trigger.symbol-count`、`trigger.random-event`或`trigger.state-threshold`节点，逐项核对资格、判定规则、`target_node_id + target_kind`及适用的`state_node_id`等引用；审计不计分但属于阻塞门禁。
- `trigger.symbol_count_distribution`与盘面数量及Count Pay中奖符号/实际计数交叉：同源实例只保留盘面数量评分。
- `trigger.position_pattern_given_count_distribution`保存无损实际坐标时，可确定性推出同符号同作用域的盘面分区计数向量和最大连续长度；有损表示必须密封不可推出证据。
- `trigger.random_event_rate_given_eligibility`使用每次合格RNG判定机会作为分母；`core.feature.natural_trigger_rate`使用完整付费入口，`trigger.entry_source_distribution`使用已进入Feature的内生入口事件，三者不能互相替代。
- `trigger.entry_source_distribution`与`core.feature.natural_trigger_rate`交叉复核：Core负责游戏内生入口总频率，本指标只在`entry_source_domain=endogenous`的专属事件集中评价内生规则来源构成。

## 使用约束

- 每个评分指标只有一个Owner和一个score_budget_key；同一指标拆分多个作用域时先按scope_aggregation聚合，不按实例数量自然增权。
- derived_diagnostic和audit的score_weight固定为0，不进入综合分。
- 条件分布只在其条件组内归一化；完整边际由对应主指标负责，禁止再次保存原始联合分布重复计分。
- `position_pattern_representation=none`时位置指标不实例化；其他表示必须同时密封实际坐标域。
- 每个Feature画像的`entry_source_semantics`必须与`entry_sources`逐项一致，并为每项给出`origin`和受控`source_kind`。`feature_buy`、`forced_test`、`test_injection`、`operator_override`和`other_external`只能标为`exogenous`。
- 入口来源评分目标键必须恰好等于该Feature全部`endogenous`来源ID；密封事件逐条使用`entry_source_id`和`target_feature_node_id`核验，出现任何外生或未声明来源即阻塞FORMAL。只有一个内生来源时按退化支持不计分；没有内生来源时不实例化。
- 目标分桶、实际业务标签、样本单位和条件分母必须在查看候选结果前密封。
