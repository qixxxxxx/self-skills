# 标准结算语义

版本：2.4.0

- `settlement.payline`：固定线路坐标及方向决定中奖结果。
- `settlement.ways`：按相邻轴上的实际符号组合数量结算。
- `settlement.effective-ways-capacity`：固定有效格布局下，实际可用Ways容量仍按可复算规则逐盘变化。
- `settlement.count-pay`：在指定范围内按同符号实际数量直接赔付。
- `settlement.cluster-pay`：按邻接规则形成的独立同符号连通块赔付。

同一游戏可以同时具有多个结算语义，但每一笔结算必须能归属到唯一语义。Scatter按数量直接派奖属于`settlement.count-pay`；Scatter导致Feature入口则另外加载`trigger.symbol-count`，不能把赔付与触发合成一个自由文本标签。

Megaways使用`board.variable-grid + settlement.ways`表达，不创建品牌专用结算ID。固定布局下若Split Symbol、符号多重计数或超大符号使实际可用Ways容量逐盘变化，额外加载`settlement.effective-ways-capacity`；它只表示机会容量，不替代某次中奖实际Ways规模。仅由轴高或有效格布局变化产生的容量仍归`board.variable-grid`，两种容量画像不能描述同一变化来源。

每个`settlement.ways`节点都必须显式填写`variable_ways`和`available_ways_formula`。容量固定时写`variable_ways=false`，公式仍要从有效格与结算规则确定性得到该常量；容量逐盘变化时写`variable_ways=true`。纯几何变化由`board.variable-grid`承接；固定布局的非几何变化，或可变布局再叠加Split Symbol、超大符号、多重计数等非几何变化，由`settlement.effective-ways-capacity`承接最终实际容量。资料不足时形成缺口，不能省略字段，也不能用品牌Ways数字或理论最大Ways代替实际机会容量。

`settlement.effective-ways-capacity`必须密封`geometry_layout_domain`与`geometry_layout_binding`，把每个容量观察绑定到一个真实固定布局ID或可变布局ID。其`effective_capacity_formula`使用该几何事实和全部非几何规则输入复算最终实际容量。可变网格中的`layout_capacity_projection_bindings`只核对几何基础容量，不能冒充最终容量；同一最终容量边际只由`effective_ways.capacity_distribution`评分。

四类结算画像都必须密封`winning_scale_dimension`和`winning_scale_axis_semantics`，以保证中奖规模主指标不会因画像字段遗漏或距离尺度误判而失真：

| 结算玩法 | 默认维度 |
|---|---|
| 固定线结算 | `aggregation_unit=per_line`时只能使用该线实际连中轴数；`aggregation_unit=per_step_symbol`时才能使用同一步骤同一中奖符号的实际中奖线数 |
| Ways结算 | 对应符号实际参与结算的Ways数量 |
| 计数赔付 | 对应符号实际参与派奖的数量 |
| 连片结算 | 单个实际派奖连通块的成员格数量 |

禁止使用理论最大Ways、总线数或仅凭盘面推测的规模替代实际结算事实。

轴语义不是运行时选项：Ways的实际中奖组合数固定使用`nonnegative_multiplicative`；固定线连中轴数/中奖线数、Count Pay数量和Cluster格数固定使用`natural_linear`。任务合同必须复制画像结论，候选结果不能改变它。

固定线的公共对齐键必须是“实际结算方向 + 由`line_definitions`按该方向排列的`(reel,row)`坐标序列”，协议`line_id`只用于回查本游戏线路定义且不得进入规范键。Both Ways必须逐中奖事件保留实际方向。原版与候选即使线路编号不同，只要规范几何相同就视为同一线路；同一作用域若两个`line_id`映射到同一规范几何则fail fast，缺少编号到几何的确定性映射时不得评价线路分布。

固定线合法组合只有两种：

- `per_line + matched_reel_count`：每条已派奖线是一个独立结算块，规模是该线实际连中的轴数。
- `per_step_symbol + winning_line_count`：同一步骤同一中奖符号的全部已派奖线先聚合成一个结算块，规模是该聚合块的实际中奖线数。

`per_line + winning_line_count`恒为1，`per_step_symbol + matched_reel_count`口径不唯一，二者均为非法组合并阻塞指标匹配。

实际只存在一个可达规模时仍要密封该单值支持，再由阶段2按退化支持标记指标不适用；不能把`winning_scale_dimension`留空。

每个Cluster画像都必须调查并以布尔值密封`near_miss_structure_relevant`。为`true`时，按同一邻接规则，在每个合格盘面、每个声明符号及其全盘精确总数量条件下识别未达到实际派奖门槛的最大连通块；没有未中奖连通块时记0。为`false`时明确表示已调查但不把近门槛连片作为独立体验，不加载专项指标；字段缺失表示未调查，阶段1直接阻塞。符号总数量边际仍由盘面数量指标负责。已派奖连通块只进入通用中奖规模指标；未达门槛连通块只参与逐盘最大未中奖连片专项，同一连通块不能重复进入两项。

边界说明：

- 动态奖值符号按自身携带金额兑现时使用`award.value-symbol`，不是计数赔付。
- Cluster必须有可证明的邻接与独立连通块；仅统计全盘同符号数量时仍是计数赔付。
- 同一结算步内多个Cluster是多个结算结果，不能按“该符号本步出现一次中奖”合并。
