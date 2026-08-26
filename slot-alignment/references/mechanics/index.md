# 玩法语义库索引

版本：2.6.0

玩法语义库只定义“玩法是什么”，不定义如何评分。所有游戏必须用`mechanic_id + 标准属性`复用语义；证据不足时标记语义缺口。

| 分类 | 包 | 主要语义 |
|---|---|---|
| board | board.grid | 固定/可变网格 |
| settlement | settlement.standard | 固定线、Ways、固定布局动态有效Ways容量、计数赔付、连片结算 |
| evolution | evolution.cascade | cascade/tumble 连续演化 |
| feature | feature.free-spin | 免费旋转 |
| feature | feature.respin | 普通重转、Hold & Spin |
| feature | feature.award-draw | Pick、Wheel及等价抽取型奖励 |
| feature | feature.bonus-sequence | 至少两类已登记非Feature动作组成的顶层复合Feature序列 |
| trigger | trigger.standard | 符号计数、随机事件、状态阈值触发 |
| modifier | modifier.wild | Wild 替代与扩展 |
| modifier | modifier.multiplier | 奖金或符号倍率 |
| modifier | modifier.collect | Collect收集与聚合 |
| modifier | modifier.symbol-transform | Mystery、升级、复制等符号变形 |
| award | award.prize | 动态奖值符号与Jackpot |
| state | state.persistent | 持久倍率、进度、等级与位置状态 |

## 24项主流玩法语义

| 顺序 | mechanic_id | 中文语义 | 唯一边界 |
|---:|---|---|---|
| 100 | `board.fixed-grid` | 固定网格 | 实际有效格坐标集合稳定；支持规则矩形和固定不规则各轴高度 |
| 110 | `board.variable-grid` | 可变网格 | 实际轴高或有效格几何布局变化；固定布局容量变化不归此项 |
| 200 | `settlement.payline` | 固定线结算 | 依赖预定义线路ID和坐标 |
| 210 | `settlement.ways` | Ways结算 | 相邻轴符号组合，不依赖线路ID |
| 215 | `settlement.effective-ways-capacity` | 固定布局动态有效Ways容量 | 布局固定但实际可用Ways机会规模逐盘变化 |
| 220 | `settlement.count-pay` | 计数赔付 | 按范围内同符号数量直接查表 |
| 230 | `settlement.cluster-pay` | 连片结算 | 按邻接规则形成独立连通块 |
| 300 | `evolution.cascade` | Cascade/Tumble | 上一结算直接产生下一盘和下一结算 |
| 400 | `feature.free-spin` | 免费旋转 | 不再次扣款的有限可追加旋转序列 |
| 410 | `feature.respin` | 普通重转 | 独立重转计数重新生成全部或部分盘面 |
| 420 | `feature.hold-and-spin` | Hold & Spin | 奖值对象持续锁定并累积至终局 |
| 430 | `feature.award-draw` | 抽取型奖励 | 从奖励池进行一次或多次Pick/Wheel抽取 |
| 440 | `feature.bonus-sequence` | 复合Feature序列 | 顶层有限周期编排至少两类已登记非Feature动作，不接管局部随机与派奖 |
| 500 | `trigger.symbol-count` | 符号计数触发 | 合格符号数量满足阈值后转移状态 |
| 510 | `trigger.random-event` | 随机事件触发 | 独立随机事件决定入口，盘面条件不能完全复算 |
| 520 | `trigger.state-threshold` | 状态阈值触发 | 命名状态达到或跨越阈值后转移 |
| 600 | `modifier.wild-substitute` | Wild替代 | Wild在实际结算中替代合格符号 |
| 610 | `modifier.expanding-wild` | 扩展Wild | 合格Wild按几何规则生成额外有效Wild位置 |
| 620 | `modifier.win-multiplier` | 中奖倍率修饰 | 普通赔付后应用独立可观察倍率 |
| 630 | `modifier.collect` | Collect收集 | 收集器聚合指定来源对象并产生输出 |
| 640 | `modifier.symbol-transform` | 符号变形 | 来源格或符号实际转换为目标身份 |
| 700 | `award.value-symbol` | 动态奖值符号 | 符号实例携带运行时奖值并按条件兑现 |
| 710 | `award.jackpot` | Jackpot奖项 | 命名层级、独立触发、奖值模型及重置 |
| 800 | `state.persistent-state` | 持久状态 | 命名状态跨声明边界保留并发生可复算转移 |

## 组合规则

- Megaways不建立品牌ID。实际轴高或有效格布局变化时使用`board.variable-grid + settlement.ways`；布局固定而仅Split Symbol、符号多重计数等改变容量时使用`board.fixed-grid + settlement.ways + settlement.effective-ways-capacity`。
- Scatter直接派奖使用`settlement.count-pay`；Scatter进入Feature使用`trigger.symbol-count`，二者可以同时存在但证据分别保存。
- Cluster Cascade使用`settlement.cluster-pay + evolution.cascade`。
- PowerNudge、局部列下移或其他由上一结算直接产生下一盘并继续结算的玩法仍使用`evolution.cascade`；通过`refill_partition_rule`密封真实轴列/区域分配，不另建品牌ID。
- Sticky Wild使用`modifier.wild-substitute + state.persistent-state`。
- Walking Wild使用`modifier.wild-substitute + state.persistent-state(position_set)`；只有对象身份稳定、完整一一配对且全部结构可达位置对已密封时，才按数量转移分组评价扣除起点与终点边际后的纯配对残差。纯位置移动不属于`modifier.symbol-transform`。
- Multiplier Wild使用Wild节点与`modifier.win-multiplier`组合；只有`linked_multiplier_id`、专属`wild_multiplier_dependency_evidence`和共享事件集均有效时才加载`interaction.wild-multiplier`。
- 倍率随Cascade层级变化时加载`interaction.cascade-multiplier`；高低倍率系统性偏向不同倍率前中奖大小时，必须有`return_dependency_evidence`才加载`interaction.multiplier-return`，普通独立倍率不加载Interaction。
- Mystery转Wild或普通符号升级使用`modifier.symbol-transform`；转换后如何结算仍由结算语义定义。
- Hold & Spin中的动态金币使用`feature.hold-and-spin + award.value-symbol`；出现命名奖池时再加`award.jackpot`。
- Collect写入跨局进度时使用`modifier.collect + state.persistent-state`；达到阈值触发Feature时再加`trigger.state-threshold`。
- Pick与Wheel统一使用`feature.award-draw`，仅用`presentation_type`区分表现；按每个入口来源填写七项`outcome_return_equivalence`。最小充分抽取状态、转移、停止、聚合和终局投影组成的完整有限随机链可复算时，奖励结果分布是唯一评分Owner，路径与路径回报只作确定性派生。
- 一个完整周期确实由至少两类已登记非Feature动作构成，且没有Free Spin、Respin、Hold & Spin或Award Draw单一节点能够拥有整个生命周期时，才使用`feature.bonus-sequence`承接外层路径、整周期回报和主要动作次数；局部动作继续由原玩法Owner承接。

所有Feature画像必须用`entry_source_semantics`逐项区分游戏规则内生入口和Feature Buy、强制测试、测试注入等外生入口；入口来源构成评分只允许使用内生事件域。固定/可变网格画像还应记录生成模型、生成分区、有效格、符号角色、盘面阶段和堆叠方向；标准结算画像必须记录真实中奖规模维度。每个玩法节点的`metric_requirements`只引用指标包，条件包必须由标准属性或组合玩法事实证明后加载。

不为品牌名、界面动画、普通大奖、理论最大中奖、Sticky/Walking等组合表现另建ID。已有语义能够通过组合与标准属性准确表达时，新增玩法ID视为冗余。
