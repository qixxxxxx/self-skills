# Collect收集语义

版本：2.2.0

`modifier.collect`要求存在一个可识别收集器、合格来源对象集合、收集范围和聚合结果。它既可以收集对象数量，也可以聚合动态金额、倍率、状态增量或无序奖项类别。

边界如下：

- 全盘同符号数量直接查表派奖属于`settlement.count-pay`；
- 奖值对象持续锁定到终局属于`feature.hold-and-spin`；
- 收集结果跨后续步骤或付费入口保留时，另加`state.persistent-state`；
- 被收集对象携带实例级动态奖值时，另加`award.value-symbol`。

指标必须把“合格但收集0个”和“收集生效后的输出”分开表达，不能只统计有奖励的Collect事件。

画像必须先用非空唯一字符串数组`output_semantic_domain`列出全部实际输出语义。每个`output_semantic`必须恰好登记在以下一个数组中，两个数组的语义集合不得重叠，语义并集必须与`output_semantic_domain`完全一致；至少一个数组必须存在且非空，二者都缺失时阻塞：

- `output_axis_semantics_by_output`：可选的非空对象数组，每项恰好包含`output_semantic`、`output_unit`、`axis_semantics`三个字段；
- `output_category_domains_by_output`：可选的非空对象数组，每项恰好包含`output_semantic`、`output_unit`、`categories`三个字段；`categories`必须是至少2个非空唯一字符串组成的数组，并使用原版真实业务标签。

每个可排序输出在`output_axis_semantics_by_output`数组中按以下规则声明：

- 直接派奖统一先换算为`bet_multiple`，倍率结果使用自身倍率值，二者采用`nonnegative_multiplicative`；
- 状态增量、等级、自然计数和进度步数采用`natural_linear`；
- 无序奖项类别不得进入输出价值有序分布。奖项类别、Jackpot等级、升级类型、符号转换类别等必须逐项登记到`output_category_domains_by_output`数组，`categories`保存完整真实类别域，由Collect类别结果指标承接；只有确实存在独立抽取随机链时才另外组合`feature.award-draw`。

同一指标实例只能对应一个输出语义和一个单位。有序输出还只能对应一种轴语义，无序输出只能使用密封类别身份比较；混合量纲、混合类别域或同一语义双重登记都必须阻塞。
