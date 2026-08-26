# 收集与转换指标

版本：2.3.0
Owner：`atomic.collect`

## Owner边界

`atomic.collect`负责一次收集结算的输入数量，以及指定输入数量下的有序数值输出或无序类别输出，不重复评价完整Feature回报。输入数量是每个唯一Collect机会的单一边际，只按`mechanic.collect×state`统计；同一机会产生多个输出语义或单位时不能复制该边际。两类输出指标才按`output_semantic×output_unit`拆分，同一输出语义只能命中其中一类。

## 指标清单

| 顺序 | 指标ID | 中文名 | 类型 | 语义角色 | Owner及重叠关系说明 |
|---:|---|---|---|---|---|
| 10 | `collect.input_count_distribution` | 收集输入数量分布 | 评分指标 | 主评价 | 每个唯一Collect机会只统计一次，不按输出语义或单位重复拆分。 |
| 20 | `collect.output_value_given_input_count_distribution` | 指定收集数量下的输出价值分布 | 评分指标 | 主评价 | 仅承接画像登记的有序数值输出；以输入数量为条件，不重复输入数量边际。 |
| 30 | `collect.output_category_given_input_count_distribution` | 指定收集数量下的输出类别分布 | 评分指标 | 主评价 | 仅承接画像登记的无序类别输出；与有序输出按语义互斥。 |

## 派生与交叉关系

- `collect.input_count_distribution`使用`mechanic.collect×state`作用域保存唯一输入数量边际。
- `collect.output_value_given_input_count_distribution`继续使用`mechanic.collect×state×output_semantic×output_unit`，只对`output_axis_semantics_by_output`对象数组逐项登记的语义评价给定输入数量后的有序数值转换。
- `collect.output_category_given_input_count_distribution`使用相同作用域，只对`output_category_domains_by_output`对象数组逐项登记的语义评价给定输入数量后的无序类别构成。
- 两类输出指标都与`collect.input_count_distribution`组成“输入数量边际＋条件输出”的非重叠分解；同一`output_semantic`不得同时进入两项。


## 使用约束

- 输出价值轴按同一`output_semantic×output_unit`拆组，并从画像属性`output_axis_semantics_by_output`逐输出解析为自然线性或非负乘法语义；解析结果必须在候选出现前密封，不同量纲或不同轴语义不得混组。
- 输出类别按同一`output_semantic×output_unit`拆组。`output_category_domains_by_output`必须是非空对象数组，每项恰好包含`output_semantic`、`output_unit`、`categories`；`categories`必须包含至少2个非空唯一真实业务标签。奖项类别、Jackpot等级、升级类型和符号转换类别都只按身份比较，使用`grouped_total_variation`，不得虚构类别顺序或距离。
- `output_axis_semantics_by_output`仍沿用每项恰含`output_semantic`、`output_unit`、`axis_semantics`的对象数组结构，但整体改为可选。两个数组的`output_semantic`集合必须互斥且并集完整覆盖`output_semantic_domain`；至少一个数组存在且非空。
- 每个评分指标只有一个Owner和一个score_budget_key；同一指标拆分多个作用域时先按scope_aggregation聚合，不按实例数量自然增权。
- derived_diagnostic和audit的score_weight固定为0，不进入综合分。
- 条件分布只在其条件组内归一化；完整边际由对应主指标负责，禁止再次保存原始联合分布重复计分。
- 目标分桶、实际业务标签、样本单位和条件分母必须在查看候选结果前密封。
