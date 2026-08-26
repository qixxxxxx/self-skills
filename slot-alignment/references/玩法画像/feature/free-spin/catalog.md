# 免费旋转语义

版本：2.7.0

`feature.free-spin`必须记录每个入口来源、初始赠送规则、每次旋转如何消耗次数、追加次数、退出条件及内部状态。`entry_source_semantics`必须逐项覆盖`entry_sources`，把每个来源密封为游戏规则产生的`endogenous`或玩家购买、强制测试、测试注入等`exogenous`，并给出受控`source_kind`。入口来源构成评分只使用内生来源；购买和测试来源仍可用于各自Feature周期统计，但不得混入来源构成分布。

`retrigger_rule`是必查属性，不能因游戏看起来没有重触发而省略。存在重触发、加次、重置或其他延长路径时记录完整触发条件、赠送数量和生效时点；原版证据明确证明不存在任何追加路径时写受控值`none`。资料不足以证明不存在时形成语义缺口，不能用`none`代替调查。

每个节点还必须密封`feature_mode_domain`、`selected_feature_mode_id`、`mode_selection_rule`和`player_input_role`。没有可选模式时，模式域只含唯一默认模式，`mode_selection_rule.selection_type=single_fixed_mode`且`player_input_role=none`。玩家能在进入Feature前选择不同旋转数、倍率、波动或其他会改变数学结果的模式时，模式域必须列全，`selection_type=player_choice_before_feature`、`player_input_role=selects_feature_mode`；每个选项分别创建独立`mode`、任务和指标合同，本任务只允许一个`selected_feature_mode_id`，并把`fixed_for_task`密封为`true`。玩家点击若只揭示预先确定结果，`selection_type`和`player_input_role`都记录为`reveal_only`，不得把点击频率、选项受欢迎程度或玩家选择频率建立为游戏数学评分指标。未承接且会影响回报的玩家决策直接形成语义缺口。

`selected_feature_mode_id`必须属于`feature_mode_domain`，并与任务`scope.mode_contract.feature_mode_selections`中同一`feature_node_id`的固定选择一致。不同模式的原版事件、目标、组权重、候选样本和FORMAL样本不得混用；不能通过在同一合同中增加`choice`维度来代替拆分任务。

`stage_graph`必须结构化记录`entry_stage`、`stages`、`transitions`和`terminal_stages`，每条转移固定使用`from_stage`、`to_stage`、`branch_id`。`path_signature_definition`必须给出有限且唯一的`path_id_domain`；`included_fields`只能包含`control_stage_id`和`branch_id`，`excluded_fields`至少包含`award_outcome`、`state_value`、`duration`和`return_bucket`，`canonicalization_rule`只按控制流顺序生成稳定路径签名。

初始赠送次数、重触发事件和完整Feature总长度是三个不同事实。完整回报和总时长由通用Feature周期指标负责，免费旋转包只负责初始赠送及重触发过程，避免重复评分。

当初始或重触发赠送次数可由同一密封事件全集中的触发符号数量经完整确定映射推出时，可填写`resource_count_derivation_bindings`。数组中的每个对象必须且只能使用以下十个顶层字段：

```json
{
  "derived_metric_id": "free_spin.initial_grant_distribution",
  "derived_instance_dimensions": {"entry_source": "natural"},
  "primary_owner_metric_instance": {
    "metric_id": "board.symbol_count_per_board_distribution",
    "source_node_ids": ["board-main"],
    "instance_dimensions": {"component": "base", "state": "normal", "board_phase": "feature_entry"},
    "target_group_id": "SCATTER"
  },
  "shared_semantic_event_set_id": "natural-free-spin-entry-source-events",
  "relation": "deterministic_success_subset",
  "source_count_to_resource_count": {"0": null, "1": null, "2": null, "3": 10, "4": 15, "5": 20},
  "mapping_total_and_deterministic": true,
  "source_count_sufficient": true,
  "extra_random_or_state_dependency": false,
  "rule_evidence_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
}
```

`primary_owner_metric_instance`也固定且只能包含`metric_id`、`source_node_ids`、`instance_dimensions`、`target_group_id`。来源只能是一个活动`board.symbol_count_per_board_distribution`或`trigger.symbol_count_distribution`实例：Board来源必须用`target_group_id`指明真实`symbol_id`组，Trigger来源必须写`null`。`derived_instance_dimensions`必须与被派生合同实例完全一致，`shared_semantic_event_set_id`必须同时属于Feature节点和来源节点，`rule_evidence_sha256`必须绑定确定规则证据。

初始赠送固定使用`relation=deterministic_success_subset`：未进入Feature的源计数映射为`null`，保留事件重新归一后得到初始赠送分布。重触发赠送固定使用`relation=same_event_pushforward`：映射不得含`null`，未追加必须映射为`0`。映射必须覆盖来源目标的全部实际计数支持，`mapping_total_and_deterministic=true`、`source_count_sufficient=true`、`extra_random_or_state_dependency=false`必须同时成立，且推送结果必须与赠送目标完全一致。若同盘面计数已经由Board指标拥有，必须直接指向该活动Board实例，不能绕经已派生的Trigger实例。推送后只有一个正概率赠送值时属于固定单值，只使用`degenerate_reachable_support`，不得保留派生Binding；Feature Buy、强制测试等外生入口也不得引用自然触发盘面的计数Owner。

只有原版规则能结构化证明“初始赠送次数与最终执行次数一一对应，且不存在提前结束、可变消耗、计数重置或跨步骤依赖”时，才填写`duration_determinism`并把完整时长标记为确定性派生；仅仅没有重触发还不足以省略时长指标。
