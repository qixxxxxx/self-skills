# 核心数值与风险指标

版本：2.1.0
Owner：`core.general`

## Owner边界

`core.general`只拥有所有游戏共用的数值硬门禁、长尾及封顶审计。总RTP、入口中奖率和组件贡献之间允许作为权重为0的硬门禁交叉校验，不进入综合分。

## 指标清单

| 顺序 | 指标ID | 中文名 | 类型 | 语义角色 | Owner及重叠关系说明 |
|---:|---|---|---|---|---|
| 10 | `core.rtp.total` | 总RTP | 硬指标 | 硬门禁交叉校验 | 与组件RTP贡献之和交叉校验；硬门禁不进入综合分。 |
| 20 | `core.hit_rate.paid_entry` | 完整付费入口中奖率 | 硬指标 | 硬门禁交叉校验 | 与完整回报中的0x概率交叉校验；作为业务硬门禁保留且不计分。 |
| 30 | `core.feature.natural_trigger_rate` | Feature自然触发率 | 硬指标 | 主评价 | 按全部合格付费入口二元归并；同一入口通过一个或多个游戏内生来源进入指定Feature多次仍只计1，外生入口不计。 |
| 40 | `core.return_distribution.lt200` | 200x以下付费入口回报分布 | 硬指标 | 主评价 | 与入口中奖率交叉检查0x结构，但本指标按<200x子样本条件归一，二者不能互相替代。 |
| 50 | `core.sigma` | Sigma | 硬指标 | 主评价 | 无；本指标为该语义变量的唯一Owner。 |
| 60 | `core.rtp.component_contribution` | 组件RTP贡献 | 硬指标 | 硬门禁交叉校验 | 组件向量之和与总RTP交叉校验；各组件份额仍提供总RTP无法表达的结构。 |
| 70 | `core.long_tail.audit` | 200x以上长尾审计 | 审计指标 | 审计 | 与200x以下主体分布共同覆盖完整回报范围，但长尾不参与综合评分。 |
| 80 | `core.max_win.audit` | 最大中奖与封顶审计 | 审计指标 | 审计 | 观测最大值属于长尾极值，但封顶和溢出决策是独立治理语义。 |

## 派生与交叉关系

无派生指标。

- `core.rtp.total`与`core.rtp.component_contribution`交叉复核：与组件RTP贡献之和交叉校验；硬门禁不进入综合分。
- `core.hit_rate.paid_entry`与`core.return_distribution.lt200`交叉复核：与完整回报中的0x概率交叉校验；作为业务硬门禁保留且不计分。
- `core.feature.natural_trigger_rate`与`trigger.entry_source_distribution`交叉复核：前者评价至少通过任一游戏内生来源进入Feature的总频率，后者只评价已进入后的内生来源条件构成；Feature Buy和测试流量不进入任何一个口径。
- `core.return_distribution.lt200`与`core.hit_rate.paid_entry`、`core.long_tail.audit`交叉复核：与入口中奖率交叉检查0x结构，但本指标按<200x子样本条件归一，二者不能互相替代。
- `core.rtp.component_contribution`与`core.rtp.total`交叉复核：组件向量之和与总RTP交叉校验；各组件份额仍提供总RTP无法表达的结构。
- `core.long_tail.audit`与`core.return_distribution.lt200`、`core.max_win.audit`交叉复核：与200x以下主体分布共同覆盖完整回报范围，但长尾不参与综合评分。
- `core.max_win.audit`与`core.long_tail.audit`交叉复核：观测最大值属于长尾极值，但封顶和溢出决策是独立治理语义。

## 使用约束

- 每个评分指标只有一个Owner和一个score_budget_key；同一指标拆分多个作用域时先按scope_aggregation聚合，不按实例数量自然增权。
- derived_diagnostic和audit的score_weight固定为0，不进入综合分。
- `core.feature.natural_trigger_rate`的样本单位是合格付费入口：每个入口只回答“是否至少通过画像声明的任一`endogenous`来源进入指定Feature”，通过同一或多个内生来源进入多次都不得重复计数；`feature_buy`、`forced_test`、`test_injection`、`operator_override`和`other_external`全部排除。
- `core.return_distribution.lt200`按实际回报倍率桶使用一维Wasserstein距离；轴固定为非负乘法语义，位置固定使用`log10(1+x)`，不得改用总变差、桶编号或极端支持跨度归一化。
- `core.long_tail.audit`的条件和分母均为全部合格付费入口；回报低于200x的入口在每个长尾桶中贡献0，各桶合计为`P(return>=200x)`，不得在长尾子样本内重新归一。
- `core.max_win.audit`是阻塞型逐字段规则门禁；理论上限、封顶、实际超限事件或溢出处理缺证、无法证明或不一致时不得进入FORMAL。
- 条件分布只在其条件组内归一化；完整边际由对应主指标负责，禁止再次保存原始联合分布重复计分。
- 目标分桶、实际业务标签、样本单位和条件分母必须在查看候选结果前密封。
