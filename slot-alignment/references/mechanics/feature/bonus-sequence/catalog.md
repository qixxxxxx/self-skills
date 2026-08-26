# 复合Feature序列语义

版本：1.1.0

## `feature.bonus-sequence`：复合Feature序列（顶层编排）

本画像只承接一种窄语义：游戏进入一个独立、有限、期间不再次扣款的Feature周期，但免费旋转、普通重转、Hold & Spin或抽取型奖励都不能单独拥有整个生命周期；周期按明确阶段图依次或分支执行至少两种不同的已登记非Feature玩法动作。

父节点只拥有外层周期边界、阶段路由、完整路径、整周期回报和主要动作次数。盘面生成、Cascade、Wild、倍率、符号变形、Collect、动态奖值、Jackpot及持久状态等局部随机和派奖，仍由对应玩法节点承接。禁止把未识别的随机步骤或派奖塞进本画像。

Gems Bonanza Gold Fever这类按Level编排多种已类型化盘面动作、且没有单一现有Feature能够拥有完整周期的流程，可以在证据完整时使用本画像。营销名称包含Bonus、Fever或Feature，不构成匹配依据。

## 必需合同

- `entry_sources`与`entry_source_semantics`逐项区分游戏内生入口和Feature Buy、强制测试、测试注入等外生入口。
- `feature_cycle_owner_node_id`必须等于当前Bonus Sequence节点ID，明确完整周期只有这一个`composite.feature-cycle` Owner。
- `sequence_boundary_rule`密封稳定`cycle_id`、开始事件、终止事件、完整父事件集以及“周期内不再次扣款”。
- `stage_graph`使用统一的`entry_stage`、`stages`、`transitions`和`terminal_stages`结构；每条转移只含`from_stage`、`to_stage`和`branch_id`。
- `stage_action_bindings`恰好覆盖全部阶段。阶段角色只允许控制、已类型化动作或终止；动作阶段必须绑定活动的非Feature玩法节点和共享语义事件集，控制与终止阶段不得产生随机结果或派奖。全部动作阶段合计至少引用两种不同的已登记`mechanic_id`。
- `transition_resolution_rule`逐条覆盖阶段图全部分支。每个分支只能由确定性控制规则或已绑定玩法节点的结果解析，不得存在匿名路由随机性。
- `path_signature_definition`只使用`control_stage_id`和`branch_id`形成规范路径，排除奖项、状态值、时长和回报桶。
- `return_aggregation_rule`证明周期内全部派奖由绑定Owner恰好计入一次，并逐入口来源密封回报分母；父节点不得直接产生匿名奖励。
- `primary_action_count_rule`把一次已类型化阶段动作的实际完成定义为一个主要动作，纯路由和终止阶段计数为0，不把不同子玩法内部动作数直接相加。
- `stage_action_count_projection`使用固定`stage_path_to_primary_action_count_v1`投影，逐条覆盖`path_id_domain`全部有限路径，并列出该路径实际访问的已类型化动作阶段及最终主要动作数；时长指标只能从阶段路径边际和这份投影确定性推出。
- `exit_condition`明确全部合法终止条件。阶段图存在回边时，`stage_loop_contract`条件必需，并用单调资源、结构上限或最大动作数证明有限终止。
- `player_input_role`只允许`none`或`reveal_only`。会改变数学结果的继续、接受、Cash-out或技巧选择不属于本画像。

## 严格互斥

- 一个免费旋转计数贯穿完整周期时使用`feature.free-spin`。
- 一个普通重转计数贯穿完整周期时使用`feature.respin`。
- 锁定奖值对象持续累积至统一终局时使用`feature.hold-and-spin`。
- 最小充分随机过程是奖励池抽取时使用`feature.award-draw`。
- 同一现有Feature的多阶段、升级、重触发或模式变化继续写入该Feature的`stage_graph`，不新增父容器。
- 只由中奖后移除、补位和重判形成的连续过程使用`evolution.cascade`。
- 普通付费局内的一次性盘面或奖励修饰使用对应原子玩法；跨多个付费入口保留的进度使用`state.persistent-state`。
- v1禁止绑定任何完整Feature子周期。存在此类嵌套、匿名随机、匿名派奖、策略性玩家决策或无法证明有限终止时，保留语义缺口。

## 指标复用

- 必需加载`composite.feature-cycle`，评价外层阶段路径、指定路径回报和不能确定性推出时的完整主要动作次数。
- 存在游戏内生入口时条件加载`atomic.trigger`；入口来源构成只读取内生事件域。
- 各阶段的局部指标继续由`stage_action_bindings`引用的玩法节点加载，不建立`atomic.bonus-sequence`，也不新增评分预算。
