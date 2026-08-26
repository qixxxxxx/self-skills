# Jackpot指标

版本：2.3.0
Owner：`atomic.jackpot`

## Owner边界

`atomic.jackpot`把正式数值覆盖限定在物质性层级：先评价“任一重要层级是否命中”，再评价“已经命中后落在哪个重要层级”，形成不重叠的低维分解。物质性由候选出现前密封的统一政策按原版命中率或RTP贡献判定；极冷门且贡献很小的层级继续进入逐层审计，不挤占正式评分。若已有活动Primary能从同一机会事件完整推出层级或未命中，两项正式指标只作确定性派生，不重复计分。规则一致性、动态奖值和Hold & Spin绑定继续由0权重审计负责。

## 指标清单

| 顺序 | 指标ID | 中文名 | 类型 | 语义角色 | Owner及重叠关系说明 |
|---:|---|---|---|---|---|
| 5 | `jackpot.rule_consistency.audit` | Jackpot规则一致性审计 | 审计指标 | 审计 | 规则、配置与实现逐字段核对；缺证或不一致阻塞FORMAL。 |
| 10 | `jackpot.material_hit_rate` | 物质性Jackpot总体命中率 | 评分指标 | 主指标 | 拥有同一机会集“是否命中任一物质性层级”的总体边际。 |
| 20 | `jackpot.material_tier_distribution_given_hit` | 物质性Jackpot命中层级构成 | 评分指标 | 主指标 | 只拥有已经命中后的层级构成；与总体命中率不重叠。 |
| 30 | `jackpot.hit_rate_by_tier` | 各等级Jackpot命中率审计 | 审计指标 | 审计 | 展示全部层级，包括非物质性冷门层级，不进入评分。 |
| 40 | `jackpot.award_value_distribution_by_tier` | 各等级Jackpot奖值分布审计 | 审计指标 | 审计 | 只审计动态奖值形状；固定值和来源由规则审计门禁。 |
| 50 | `jackpot.hold_spin_binding_consistency.audit` | Hold & Spin与Jackpot绑定一致性审计 | 审计指标 | 审计 | 只核对终局状态、层级映射、回报纳入和防重复结算。 |

## 派生与交叉关系

当`jackpot_material_owner_bindings`证明同一机会集的完整来源支持都能映射为真实Jackpot层级或未命中时，两项正式指标必须从该活动Primary精确复算并标记为确定性派生。否则由Jackpot自身直接评分；同一机会集不能同时使用上游投影和直接评分。

- `jackpot.rule_consistency.audit`是规则一致性门禁，并与正式指标及逐层审计交叉复核：规则审计证明层级、机会口径和奖值实现身份，数值项只在这些身份成立后测量。
- `jackpot.hit_rate_by_tier`与`core.rtp.component_contribution`交叉复核：Jackpot贡献由组件RTP硬门禁交叉检查；命中率样本稀疏只影响置信标记，不替代资料门禁。
- `jackpot.hold_spin_binding_consistency.audit`与`hold_spin.return_dependence_by_terminal_occupancy`、`feature_cycle.return_distribution_by_stage_path`交叉复核：前者核对规则和事件绑定，后两者评价终局占用依赖与完整回报形状，职责不重叠。

## 使用约束

- 每个评分指标只有一个Owner和一个score_budget_key；同一指标拆分多个作用域时先按scope_aggregation聚合，不按实例数量自然增权。
- derived_diagnostic和audit的score_weight固定为0，不进入综合分。
- `jackpot.rule_consistency.audit`要求全部适用字段状态为“符合”；有外部池或Jackpot专属封顶时必须核对合同与实际返回，无此机制时也必须以权威证据标记不适用。
- 必须区分“资料缺失”和“低频置信不足”：前者按各指标`missing_policy`阻塞FORMAL，后者只在权威规则、机会分母和事件绑定完整时标记“置信不足”。
- `jackpot.hit_rate_by_tier`与`jackpot.award_value_distribution_by_tier`必须按`jackpot_opportunity_set`拆分作用域；不同机会集即使层级名称相同，也不得合并机会分母、命中事件或奖值样本。
- 每个机会集没有物质性层级时，两项正式指标使用`below_materiality_resolution`；只有一个物质性层级时，层级构成使用退化支持不适用，总体命中率仍保留。
- 物质性指标必须通过统一样本能力门禁。样本不足且没有合法上游投影时形成阻塞缺口，不得改成普通审计或“不适用”。
- 条件分布只在其条件组内归一化；完整边际由对应主指标负责，禁止再次保存原始联合分布重复计分。
- 目标分桶、实际业务标签、样本单位和条件分母必须在查看候选结果前密封。
