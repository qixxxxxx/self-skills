# 完整Feature周期指标

版本：2.4.0

Owner：`composite.feature-cycle`

## Owner边界

路径只包含控制流阶段和分支，不包含奖项值、状态值、时长或回报桶。路径边际与给定路径后的回报构成非重叠分解；完整Atomic链可结合`stage_graph`确定复算路径与终局回报时，对应项派生。Award Draw不限单抽或放回规则；链外随机、非确定聚合或未承接玩家决策时保留双Owner。`feature.bonus-sequence`只把至少两种已登记非Feature动作编排成外层有限周期，本包只拥有外层路径、整周期回报和主要动作次数，局部随机与派奖仍由各阶段玩法Owner承接。

## 指标清单

| 顺序 | 指标ID | 中文名 | 类型 | 语义角色 | Owner及重叠关系说明 |
|---:|---|---|---|---|---|
| 10 | `feature_cycle.stage_path_distribution` | Feature阶段路径分布 | 评分指标 | 主指标 | 两条及以上可达路径时评分；完整奖励抽取随机链可复算路径时确定性派生；单一可达路径按退化支持处理。 |
| 20 | `feature_cycle.return_distribution_by_stage_path` | 指定阶段路径下的Feature回报分布 | 评分指标 | 主指标 | 通常只评价给定路径后的回报；完整奖励抽取随机链可复算路径与终局回报时标记为确定性派生，不重复计分。 |
| 30 | `feature_cycle.return_distribution` | 完整Feature回报边际分布 | 审计指标 | 派生诊断 | 由路径边际与路径条件回报确定性加权得到。 |
| 40 | `feature_cycle.base_bet_equivalent_return_distribution` | Feature Buy按正常基础投注折算回报审计 | 审计指标 | 审计 | 对同一密封原始周期按正常基础投注额逐事件重算，权重为0。 |
| 50 | `feature_cycle.duration_distribution` | 完整Feature主要动作次数分布 | 评分指标 | 主指标 | 仅在最终动作数不能由局部主指标确定性推出时评分，默认权重为0.5。 |
| 60 | `feature_cycle.zero_return_rate` | Feature零回报率 | 审计指标 | 派生诊断 | 只读取完整回报边际中独立精确0x桶。 |
| 70 | `feature_cycle.median_return` | Feature回报中位档位 | 审计指标 | 派生诊断 | 由完整回报边际累计概率确定性推出。 |

路径条件回报使用实际倍投注额位置，并固定按`log10(1+x)`比较长尾距离；距离尺度为1个对数十倍级，不再被极少见的极端最大值跨度稀释。路径组权重仍只来自候选出现前密封的原版路径边际。

## 使用约束

- 单一路径不是缺失，但属于退化可达支持：保留路径结构证据，任务指标状态写“不适用”，不进入评分预算。
- 每个Feature必须密封`stage_graph`四部分、有限`path_id_domain`及只含`control_stage_id/branch_id`的规范化签名。
- `feature.bonus-sequence`的主要动作固定为已类型化阶段动作的实际完成；纯路由和终止阶段计数为0。其阶段必须绑定至少两种不同的已登记非Feature玩法，禁止绑定完整Feature子周期或匿名随机、匿名派奖。
- Award Draw的七项链完整性证明满足时，路径和回报可使用`deterministically_derived_from_primary`；否则保留独立评分。
- `feature_cycle.duration_distribution`与局部过程指标交叉诊断；只有结构化合同证明最终主要动作总数可由已评分局部Owner完整且确定性推出时，本实例才标记不适用。免费旋转或重转还必须证明初始赠送与最终执行次数一一对应，且不存在提前停止、可变消耗、计数重置和跨步依赖；Award Draw必须有完整随机链动作数投影；复合Feature序列必须有覆盖全部路径的阶段动作数投影。逐次重触发、延长赠送数量边际以及Hold & Spin步骤当前占用边际都不能恢复完整周期总次数，禁止作为派生来源；不能确定性推出时以`default_weight=0.5`评分。
- Feature Buy主回报以购买成本为分母；基础投注折算审计必须绑定同一事件集hash，并逐事件密封`event_id`、总派奖、实际购买成本、正常基础投注额、入口来源和折算桶，不能从粗分桶换算。
- Feature主回报的每个路径条件分布都必须单独保留精确`0x`桶；总体回报无损聚合该桶，零回报率只能由此读取。
- 回报桶、阶段路径真实名称、样本单位和条件分母必须在查看候选结果前密封。
- 同一指标拆分多个作用域时先按`scope_aggregation`聚合，不按实例数量自然增权。
