# 倍率与中奖大小依赖指标

版本：2.2.0  
Owner：`interaction.multiplier-return`

## Owner边界

`interaction.multiplier-return`只在画像存在完整结构化`return_dependency_evidence`时加载。它先以倍率前正向中奖为样本，控制Cascade深度、持久倍率状态、Wild辅助状态及其他已登记直接驱动，再从同一控制层的各回报档倍率状态概率中扣除该控制层倍率状态总体概率，只保留不能由直接驱动Owner解释的剩余依赖。

## 指标清单

| 顺序 | 指标ID | 中文名 | 类型 | 语义角色 | Owner及重叠关系说明 |
|---:|---|---|---|---|---|
| 10 | `multiplier.return_dependence_residual` | 倍率与倍率前回报依赖残差 | 评分指标 | 主评价 | Atomic与其他Interaction负责倍率边际和直接驱动关系；本指标只评价控制全部直接驱动后的剩余依赖。 |

## 使用约束

- `return_dependency_evidence`至少包含`shared_semantic_event_set_id`、`controlled_driver_node_ids`、`control_stratum_fields`、`joint_observation_rule`和`residual_dependence_after_control=true`。
- `controlled_driver_node_ids`必须覆盖全部直接影响倍率状态的Cascade、持久状态、Wild及其他活动节点；少一个驱动节点都不得加载。
- 倍率前回报、控制字段和最终倍率状态必须按`joint_observation_rule`在同一`shared_semantic_event_set_id`逐事件联合观测。
- 只有原版证据证明控制全部直接驱动后仍存在剩余依赖时才加载；控制后依赖消失、普通共存或只有间接相关时不加载。
- 倍率状态必须包含未应用或1x状态和所有实际倍率档，不能只保留高倍率样本。
- 回报桶必须使用倍率应用前的实际投注倍数并在查看候选前密封，不能按候选结果临时改桶。
- 残差定义为`P(multiplier_state|control_stratum,pre_return_bucket)-P(multiplier_state|control_stratum)`；每个控制层×回报桶的残差和必须为0。
- 残差字段是百分点差，按控制层×倍率前回报桶分组；组内平均倍率状态字段误差，再按任务合同中候选前密封的原版组权重汇总，禁止冒用总变差距离。
- 同一指标拆成多个组件或状态时，先按`scope_aggregation`聚合，不按实例数量扩大评分预算。
