# 触发语义

版本：2.1.0

所有触发节点都必须用`target_node_id + target_kind`引用唯一活动目标节点；`target_kind`只允许`feature`或`reward_state`，并分别指向Feature节点或`state.persistent-state`奖励状态节点。禁止只保存业务名称或旧式`target_feature_id`，因为它们不能证明画像节点之间的真实依赖边。

## `trigger.symbol-count`：符号计数触发

由当前盘面、步骤或入口范围内的合格符号数量满足阈值后发生状态转移。Scatter只是最常见的符号角色，不再使用Scatter专属触发ID。若相同符号同时直接派奖，另加`settlement.count-pay`。目标必须由`target_node_id + target_kind`直接引用。

画像必须密封`position_pattern_representation`和`position_pattern_coordinate_domain`。不评价位置时分别写`none`与`not_applicable`；保存完整实际坐标时写明无损表示和坐标域，使阶段2能够判断盘面分区向量、最大连续长度是否可由触发位置模式确定性推出。

同一可见完整盘面、同一符号和同一计数范围下，符号数量边际由`board.symbol_count_per_board_distribution`拥有；Trigger数量、Count Pay中奖符号边际和实际计数尾部只能派生展示或标记不适用。不同计数范围、隐藏状态或跨步骤累计必须提供不可推出证据后才可独立评分。

## `trigger.random-event`：随机事件触发

触发由独立RNG事件决定，不能由当前可见盘面完全复算。必须密封合格机会、判定时点、随机来源及`target_node_id + target_kind`；仅有动画上的“随机出现”不足以作为证据。

## `trigger.state-threshold`：状态阈值触发

命名状态在一个或多个步骤、Feature或付费入口中累积，达到阈值后触发目标状态。触发节点必须同时保存状态业务身份`state_id`和实际持久状态节点引用`state_node_id`，并记录触发后状态是否消耗、回退或重置。`trigger.state-threshold`自身只要求`atomic.trigger`；被引用的`state.persistent-state`节点由其自身画像要求加载`atomic.persistent-state`，不能由Trigger节点重复声明Owner。

同一个入口若有多个来源，应建立多个触发节点并用`target_node_id`指向同一目标Feature，不能用一个混合概率掩盖来源结构。
