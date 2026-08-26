# Cascade/Tumble 语义

版本：2.4.0

`evolution.cascade`表示同一完整入口内由上一结算结果直接产生的连续盘面演化。每一步必须能区分：被处理格、保留或移动格、新补入格、结算结果和下一步编号。

存在两个及以上稳定轴列或业务区域时，必须密封`refill_partition_rule`：固定分区ID与顺序、有效坐标到分区的唯一映射，以及新补入格如何归属分区。标准Tumble可按轴列记录补入分配；PowerNudge、局部列下移等同一入口连续结算也沿用本语义，并用该规则证明实际移动/补入发生在哪些列或区域。只有单一整体分区或补入位置完全固定时记录受控`none`，不建立空间分配评分。

每个Cascade结算步骤还必须同时密封`effective_capacity_definition`、`effective_capacity_source`、`effective_capacity_axis_semantics`和`effective_capacity_unit_zh`：分别说明该步真正参与结算的容量口径、容量来自固定规则/可变几何/固定布局动态Ways还是其他可复算规则、容量轴使用`natural_linear`还是`nonnegative_multiplicative`，以及人类报告显示的真实业务单位。有效格数等自然计数量使用`natural_linear`，Ways或组合机会规模使用`nonnegative_multiplicative`；同一指标实例不得混合两种量纲。固定容量也要写入真实固定值和单位，不能用理论最大容量代替。

Cascade体验按`P(D) × P(C|D) × P(R|D,C)`拆分：深度分布负责到达各层的概率，各层实际有效容量分布负责已到达该层后出现哪些容量，单步回报只负责给定层级和容量后的回报。三项必须绑定同一Cascade链和步骤编号。活动容量合同只纳入具有两个及以上结构可达容量值的非退化深度，并把这些活动深度的原版到达概率重新归一；固定容量深度不进入容量目标组或容量距离，只由规则证据和回报合同中的唯一容量组保留。回报必须覆盖全部原版可达深度，包括固定容量深度；其条件组权重只能按原版层级到达概率乘原版`P(C|D)`生成。两类权重均禁止使用候选频率。同一Cascade事件集下，固定布局动态Ways容量不得再由`effective_ways.capacity_distribution`重复评分；可变网格容量只保留由几何布局确定性映射的0权重审计。

以下情况不是Cascade：

- 再次扣款后生成新盘面；
- 独立Respin按自身计数重新生成全部或部分盘面；
- 只有消除动画，但没有下一次实际结算。

若倍率随层级变化，画像同时加载`modifier.win-multiplier`并记录作用与组合规则。`same_depth_multiplier_randomness=false`只能在`step_multiplier_rule`证明每个合格深度对“未出现/出现未应用/已应用及最终倍率值”给出唯一完整结果时使用；此时倍率边际和层级依赖残差均由Cascade深度分布及该映射派生。任一同深度仍可出现两种及以上倍率状态时必须写`true`，倍率边际与交互残差分别评分。Cascade继续概率可由完整深度分布推导，不重复定义。
