# 免费旋转过程指标

版本：2.2.0
Owner：`atomic.free-spin`

## Owner边界

`atomic.free-spin`只负责初始赠送和重触发赠送过程；完整周期长度与回报由`composite.feature-cycle`负责。重触发率由赠送0次桶派生。初始或追加赠送默认各自评分；只有画像中的固定十字段`resource_count_derivation_bindings`绑定同一共享事件集、单一活动`board.symbol_count_per_board_distribution`或`trigger.symbol_count_distribution`实例，并能逐桶精确复算目标时，赠送实例才改为确定性派生。固定单一赠送值只按退化支持处理，不允许同时保留派生Binding。

## 指标清单

| 顺序 | 指标ID | 中文名 | 类型 | 语义角色 | Owner及重叠关系说明 |
|---:|---|---|---|---|---|
| 10 | `free_spin.initial_grant_distribution` | 初始免费旋转赠送次数分布 | 评分指标 | 主评价 | 默认独立评分；同事件集计数经完整确定映射可推出时由唯一活动Board/Trigger数量实例拥有。 |
| 20 | `free_spin.retrigger_grant_distribution` | 免费旋转重触发赠送次数分布 | 评分指标 | 主评价 | 默认独立评分；同一合格步骤计数完整映射到含0次桶的新增次数时由唯一计数实例拥有。 |
| 30 | `free_spin.retrigger_rate` | 免费旋转重触发率 | 审计指标 | 派生诊断 | 由重触发赠送次数分布的0次桶精确推出，不独立计分。 |

## 派生与交叉关系

- `free_spin.retrigger_rate` ← `free_spin.retrigger_grant_distribution`：由重触发赠送次数分布的0次桶精确推出，不独立计分。
- 每条资源Binding必须且只能包含`derived_metric_id`、`derived_instance_dimensions`、`primary_owner_metric_instance`、`shared_semantic_event_set_id`、`relation`、`source_count_to_resource_count`、`mapping_total_and_deterministic`、`source_count_sufficient`、`extra_random_or_state_dependency`、`rule_evidence_sha256`。其中来源实例固定包含`metric_id`、`source_node_ids`、`instance_dimensions`、`target_group_id`。
- 初始赠送必须用`deterministic_success_subset`，未进入Feature的源计数映射为`null`并对保留概率重新归一；重触发赠送必须用`same_event_pushforward`，不得含`null`且未追加映射为`0`。
- 来源只能是一个活动Board或Trigger数量实例。Board来源必须指定真实`symbol_id`目标组，Trigger来源的`target_group_id`必须为`null`；若Trigger数量本身已由Board数量派生，资源项必须直接引用Board Owner。
- 映射必须覆盖来源目标全部实际计数支持，两个确定性/充分性字段必须为`true`，额外随机或状态依赖必须为`false`，规则证据必须是有效SHA-256；映射推送结果必须与赠送目标完全一致。推送后只有一个正概率结果时使用`degenerate_reachable_support`并删除Binding。


## 使用约束

- 每个评分指标只有一个Owner和一个score_budget_key；同一指标拆分多个作用域时先按scope_aggregation聚合，不按实例数量自然增权。
- derived_diagnostic和audit的score_weight固定为0，不进入综合分。
- 条件分布只在其条件组内归一化；完整边际由对应主指标负责，禁止再次保存原始联合分布重复计分。
- 目标分桶、实际业务标签、样本单位和条件分母必须在查看候选结果前密封。
