# 抽取型奖励Feature语义

版本：2.2.0

`feature.award-draw`统一表达Pick、Wheel和其他奖励池抽取。界面表现不改变数学语义：

- `presentation_type=pick`表示玩家选择一个或多个可视对象；
- `presentation_type=wheel`表示转盘或等价单次/多次抽取；
- 其他表现只有在奖励池、抽取依赖和停止规则相同的情况下才能复用此语义。

必须保留每次抽取序号、实际结果、是否放回、结果是否依赖历史抽取、保证奖规则及Feature停止原因。若用户点击只负责揭示预先密封结果，`player_input_role`记录为`reveal_only`；不能因此误判为技巧玩法。

`entry_source_semantics`必须逐项覆盖`entry_sources`，把游戏规则产生的入口标记为`endogenous`，把Feature Buy、强制测试、测试注入或运营覆盖标记为`exogenous`；入口来源构成评分只允许使用内生事件集。

`stage_graph`必须包含`entry_stage`、`stages`、`transitions`、`terminal_stages`，转移项使用`from_stage`、`to_stage`、`branch_id`。`path_signature_definition`必须给出有限、真实且唯一的`path_id_domain`；`included_fields`只能包含`control_stage_id`、`branch_id`，`excluded_fields`至少包含`award_outcome`、`state_value`、`duration`、`return_bucket`，`canonicalization_rule`只按控制流顺序生成签名。

画像必须明确：

- `replacement_rule`：有放回、无放回或由状态决定是否放回；
- `draw_dependency_rule`：`independent_given_draw_index`或明确的前序状态依赖；
- `guarantee_rule`：没有保证奖时明确写`none`，存在时写清触发进度与强制结果；
- `draw_state_definition`：每次抽取前能复算下一结果概率的最小充分状态。首次抽取使用初始状态；无放回至少包含剩余奖池，保证奖至少包含保证进度。不得直接用完整历史序列替代可压缩的规则状态。
- `outcome_return_equivalence`：按每个`entry_source`填写七个布尔字段：`draw_state_definition_minimal_sufficient`、`transition_rule_deterministic`、`stop_rule_deterministic`、`award_aggregation_deterministic`、`terminal_return_projection_deterministic`、`extra_random_reward_outside_draw_chain`、`unmodeled_player_decision_affects_return`。只有前五项全为`true`且后两项全为`false`时，完整抽取随机链才能确定性复算路径与主回报。

通常完整Feature路径、主回报和总时长由`composite.feature-cycle`负责，本语义只评价给定抽取状态后的下一奖励结果。七项证明满足时，无论单抽、多抽、有放回、无放回或历史依赖，都可由条件抽取链复算Feature控制路径和主回报，对应Feature指标作确定性派生。存在链外额外随机奖励、非确定聚合或未承接玩家决策时，奖励结果与Feature路径/回报分别保留Owner。
