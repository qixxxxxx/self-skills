# 符号变形语义

版本：2.2.0

`modifier.symbol-transform`覆盖Mystery揭示、符号升级、普通符号转Wild、符号复制等真正改变数学身份的转换。必须保留转换前后格子身份、来源符号、目标符号、发生时点、实际改变格数、位置表示与坐标域，并用`target_assignment_scope`和`event_target_assignment_rule`说明同一事件是共用一次目标抽取、按来源组共用、逐格独立、确定映射还是混合状态规则；再用`transform_return_binding_rule`明确同一步骤回报如何绑定。多格事件使用目标一致性残差区分“全部变成同一符号”和“逐格独立抽取”，不保存完整目标向量。原版证明变形结果与回报存在额外依赖时记录`return_dependency_evidence`并加载交互指标；目标符号携带动态奖值时通过`value_symbol_node_ids`引用对应奖值节点。

以下情况不属于符号变形：

- Wild只在结算阶段替代另一个符号；
- 合格Wild按`expansion_geometry`纯几何生成或覆盖额外Wild位置，即使视觉上覆盖了原格；
- Cascade消除后向空位补入新符号；
- 同一稳定对象只移动到其他位置，数学符号身份没有改变；
- 动画或皮肤变化没有改变结算身份。

Walking Wild通常使用`modifier.wild-substitute + state.persistent-state(position_set)`表达；只有移动过程中另有格子或符号真正改变数学身份时，才为那部分额外加载`modifier.symbol-transform`，并排除纯移动对象格。Mystery转出动态奖值符号时再组合`award.value-symbol`，无需新增表现型玩法ID。
