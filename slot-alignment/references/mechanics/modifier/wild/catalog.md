# Wild 语义

版本：2.4.0

- `modifier.wild-substitute`：实际结算替代规则，必须证明Wild真正进入了中奖结果。
- `modifier.expanding-wild`：由一个合格Wild按明确几何规则产生额外有效Wild位置。

两者可以同时存在；扩展后的Wild如何参与结算继续由结算语义定义。每个Wild节点都必须写清`wild_effect_scope`、如何判定“实际辅助”的`assistance_resolution_rule`，以及在同一盘面、同一结算规则下去除Wild作用后如何确定性复算增量派奖的`incremental_payout_rule`。当结算事实能稳定识别实际参与的Wild来源格或扩展后有效格时，再密封`assisting_cell_identity_rule`，说明同一步内去重身份、扩展格归属及多派奖块合并口径；无法稳定识别时不得猜测参与数量。Wild在盘面上的出现率、数量与位置由通用盘面指标承担；Wild专用评分分别衡量合格机会内的实际辅助率、辅助发生后的参与格数量和增量回报形状，RTP贡献则从同一逐入口账本按实际投注直接审计，不能用评分结果相乘近似。

纯几何扩展只归`modifier.expanding-wild`：即使画面上看起来覆盖了原有格，也不再加载`modifier.symbol-transform`。只有某个来源符号先按独立选择或分配规则改变数学身份，且该转换不能由扩展源与`expansion_geometry`完整解释时，才另外建立符号变形节点；两者的事件和位置必须可分开复算。

同一物理Wild的所有组合节点必须共享同一`wild_effect_id`并指向唯一`effect_owner_node_id`。辅助率、增量回报和增量RTP只由该Owner节点统计一次；每个扩展节点仍独立拥有`wild.expanded_cell_count_distribution`，不因经济效果Owner合并而丢失扩展几何信息。

Sticky Wild和Walking Wild都使用`modifier.wild-substitute + state.persistent-state(position_set)`表达，并由`persistence_state_id`引用同一活动持久状态；Walking Wild只有对象身份稳定、前后完整一一配对且完整可达位置对已密封时才加载位置移动联合指标。Multiplier Wild使用Wild节点与`modifier.win-multiplier`组合表达。只有Wild节点的`linked_multiplier_id`指向实际倍率节点、两者共享同一语义事件集，并提供专属`wild_multiplier_dependency_evidence`时，才加载Wild与倍率依赖残差；普通共存不加载。Mystery符号转成Wild使用`modifier.symbol-transform`表达。不要为这些组合另建品牌或表现型玩法ID。
