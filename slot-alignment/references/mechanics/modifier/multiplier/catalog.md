# 倍率修饰语义

版本：2.5.0

`modifier.win-multiplier`必须记录倍率从哪里产生、作用于哪笔结算、何时应用、多个倍率如何组合、实际可达`value_domain`，以及倍率出现后是否可能跳过应用。`progression_driver`固定说明无递进、持久状态驱动、Cascade深度驱动或其他有证据驱动；存在递进时必须补齐`progression_rule`、`reset_rule`、`cap_rule`和`state_to_effective_multiplier_rule`，并用`progression_state_id`或`cascade_node_id`引用真实驱动节点。必须同时保留应用前奖金、实际有效倍率和应用后奖金，避免与“本局最终回报倍数”混淆。

倍率出现、出现后真正应用、应用后的有效值是三个连续但不同的统计事实。持久倍率组合`state.persistent-state`；Cascade递增倍率组合`evolution.cascade`并加载层级交互指标。若倍率由Wild身份、数量或辅助状态驱动，Wild节点必须用`linked_multiplier_id`和专属`wild_multiplier_dependency_evidence`绑定本倍率，同时本节点密封`linked_symbol_domain`，才加载Wild与倍率联合残差。没有明确依赖证据时不加载。符号赔付表本身的高倍值不属于倍率修饰。

倍率与倍率前回报Interaction只能使用结构化`return_dependency_evidence`加载。该合同至少必须包含：

- `shared_semantic_event_set_id`：倍率前回报、最终倍率状态和全部控制变量共同所属的唯一语义事件集；
- `controlled_driver_node_ids`：全部直接影响倍率状态的活动节点ID，必须覆盖Cascade驱动节点、持久倍率状态节点、Wild驱动节点及其他已登记直接驱动；普通共存节点不得伪装成驱动；
- `control_stratum_fields`：从上述驱动节点确定性提取的控制分层字段，例如`cascade_depth`、`persistent_multiplier_state`、`wild_assistance_state`；
- `joint_observation_rule`：说明同一结算事件如何联合绑定倍率应用前回报、控制分层和最终倍率状态；
- `residual_dependence_after_control`：必须严格为`true`，表示控制全部直接驱动后仍存在可证明的剩余依赖。

`controlled_driver_node_ids`必须与画像中全部直接驱动引用闭合，不能漏掉`cascade_node_id`、倍率引用的持久状态节点或通过`linked_multiplier_id`绑定本倍率的Wild节点。若控制后依赖消失、共享事件集不成立、直接驱动不完整，或只是Cascade、持久状态、Wild与倍率普通共存，则不得加载`interaction.multiplier-return`。

持久状态值与生效倍率保持独立Owner：前者统计画像指定观测点上的状态边际，后者统计倍率已实际应用事件上的最终有效值。`state_to_effective_multiplier_rule`继续由倍率递进规则审计核对，但不得仅凭“值一一映射”停用任一统计Owner。

动态奖值符号与生效倍率默认也分别评价：前者以`value_symbol_assignment_event`为样本，后者以`applied_multiplier_event`为样本。只有存在`value_symbol_effective_multiplier_binding`时才允许去重；该对象必须且只能完整密封：

- `value_symbol_node_id`和`multiplier_node_id`：唯一一对活动画像节点，前者的`linked_multiplier_node_ids`必须包含后者；
- `shared_semantic_event_set_id`：双方共同声明的唯一语义事件全集；
- `value_symbol_instance_id_field`和`multiplier_application_event_id_field`：用于逐事件配对的稳定ID字段；
- `event_pairing_bijective=true`：每个赋值符号实例恰好对应一个倍率应用事件，反向也唯一；
- `all_assignments_realized_exactly_once=true`：事件全集内不存在未兑现、重复兑现或只截取已兑现子样本；
- `same_event_universe=true`：两项指标没有额外筛选、漏样本或不同作用域；
- `no_additional_multiplier_source=true`：该倍率没有Cascade、Wild、持久状态、独立随机数或其他额外数值来源；
- `value_to_effective_multiplier_mapping`与`mapping_total_and_bijective=true`：覆盖全部实际奖值和倍率支持，映射为单值且正反方向都唯一；
- `primary_owner_metric_id`：只能是`value_symbol.assignment_value_distribution`或`multiplier.effective_value_distribution`，指定唯一计分方向；
- `rule_evidence_sha256`：绑定上述配对、全集和映射规则的权威证据。

任一字段缺失、值不为严格`true`、映射不全、存在未兑现符号或额外倍率源时，两个值分布继续各自评分，不能因为数值名称相近或玩法节点互相引用而派生。绑定成立时，`primary_owner_metric_id`指定的指标保持活动，另一项必须使用`deterministically_derived_from_primary`，且不允许反向同时派生。

`progression_driver=cascade_depth`时必须密封`same_depth_multiplier_randomness`。写为`false`时还必须提供`cascade_depth_multiplier_binding`：唯一绑定Cascade和倍率节点及共享事件集；终局深度固定使用“完成的后续Cascade结算次数”，结算步骤固定为“初始结算0，随后Cascade步骤1、2……”；`terminal_depth_to_step_states`必须为每个可达终局深度列出从0到该深度的全部实际结算步骤，并逐步写明倍率是否出现、是否应用及实际生效值。绑定还必须证明全部可达深度已覆盖、映射完整确定、没有额外随机或状态依赖，并提供规则证据哈希。只有该结构可从`cascade.depth_distribution`精确复算倍率出现率、出现后应用率、生效倍率值分布，以及`P(multiplier_state|step)-P(multiplier_state)`层级依赖残差时，四项才作确定性派生；自由文本递进规则或单独的`same_depth_multiplier_randomness=false`不构成派生证据。同一深度仍有多个可达倍率状态时写`true`，不填写确定映射，保留倍率边际和Cascade依赖残差评分。

倍率恒定时也必须把单一倍率写入`value_domain`，把`progression_driver`写为`none`，再由阶段2按退化支持标记有效值分布不适用；不能因值域字段缺失而跳过倍率强度核对。
