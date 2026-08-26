# 网格语义

版本：2.5.0

## `board.fixed-grid`：固定网格

同一密封作用域内，实际参与结算的轴数和有效格坐标集合不变化。规则矩形直接记录固定`rows`；各轴高度不同但不会随结算变化的固定不规则盘面，还必须密封`fixed_height_by_reel`和唯一`fixed_valid_cell_layout_id`，其中`rows`表示坐标包围高度。界面动画、边框变化或未参与结算的装饰位置不构成可变网格，也不能因为固定不规则高度就误标为可变网格。

固定有效格布局不代表实际Ways容量必然固定。若同时命中`settlement.effective-ways-capacity`，必须条件加载`atomic.effective-ways-capacity`；该包只承接Split Symbol、符号多重计数等非布局规则造成的动态容量。

## `board.variable-grid`：可变网格

至少一个实际轴高、有效格坐标集合或参与结算的几何布局会在结算之间变化。每轴高度域必须分别记录，不能只写一个理论最大高度。仅有组合容量变化不足以命中`board.variable-grid`。

若有效格布局固定，只因Split Symbol、超大符号的多重占位、符号多重计数或其他非布局规则使实际Ways容量逐盘变化，应使用`board.fixed-grid + settlement.effective-ways-capacity`，由`atomic.effective-ways-capacity`承接，不能伪装成可变网格。

Megaways不是独立数学语义。只有实际轴高或有效格布局变化的Megaways游戏才使用`board.variable-grid + settlement.ways`表达；品牌名称或动态Ways数字本身不能用于指标匹配。

为加载盘面多样性指标，画像必须密封有效格、空间分区、符号角色和盘面阶段；固定网格与可变网格都必须命中“单盘符号数量分布”和“单盘不同可见符号种类数分布”。后者按每个完整盘面去重后的实际`symbol_id`计数，专门承接同盘共现广度，不能由逐符号数量边际或出镜率替代。其余属性按实际生成与结算语义密封：

- `generation_model`或`layout_generation_model`：`reel_strip`、`board_template`、`independent_cell`或有证据的其他稳定模型。
- `generator_partitions`：每个画像都必须调查。能从原版或实现证明稳定生成单元时，记录完整且互斥的卷轴编号、模板域或其他可比较分区；不存在稳定生成单元时固定写受控值`none`。只有前者加载生成单元重复碰撞率。
- `spatial_partitions`：每个可见盘面必需密封的互斥有效格分区，例如逐轴、逐列或规则明确的盘面区域；同一作用域内每个有效格必须恰好属于一个分区，主流多轴/多列盘面至少使用两个分区。
- `valid_cell_definition`：哪些可见位置属于实际统计与结算格。
- `symbol_role_map`：覆盖每个有效格可能出现的实际`symbol_id`及普通、WILD、Scatter、Bonus等角色；同一`symbol_id`的动态奖值、倍率或展示变体不另算新符号种类。无法把每个有效格唯一解析为一个已声明`symbol_id`时，盘面多样性测量缺失并阻塞。
- `board_phase_domain`：初始盘、Feature初始盘、演化后盘等阶段。
- `stack_axis`：每个画像都必须调查。连续堆叠确实是可见体验且方向可证明时记录实际方向；不存在该语义时固定写受控值`none`。只有前者加载最大连续长度分布。
- `reel_height_variation`：布尔值；至少一轴存在两个及以上结构可达实际高度时为`true`，全部轴高固定时为`false`。完整轴高布局指标只在该值为`true`时加载。
- `height_domain_by_reel`：每一轴各自允许的实际高度；轴高固定时也记录单值域，用于证明`reel_height_variation=false`。
- `valid_cell_layout_domain`：同一作用域内结构可达的完整有效格坐标布局域，不能用理论容量区间替代。
- `valid_cell_layout_representation`：完整布局的无歧义表示，例如有序有效格坐标集合，或带密封坐标映射的`layout_id`。轴高不变的非轴高布局变化由该表示加载有效格布局分布。
- `ways_capacity_mode`：每个可变网格都必须调查。没有Ways或等价容量语义时写`none`；最终容量只由几何布局决定时写`layout_only`；几何布局还叠加Split Symbol、超大符号、多重计数等非几何输入时写`layout_plus_non_layout`。
- `available_ways_formula`：`ways_capacity_mode`不是`none`时记录，只负责把当前真实几何布局复算为几何基础容量。
- `layout_capacity_projection_bindings`：`ways_capacity_mode`不是`none`时必需。每条绑定明确选择轴高布局或有效格布局Primary，并用`source_layout_to_capacity`完整覆盖其真实布局标签；这里只映射几何基础容量，不能从标签文本猜格数或Ways。
- `layout_plus_non_layout`必须同时建立共享事件域的`settlement.effective-ways-capacity`节点，由其`effective_capacity_formula`使用实际布局和全部非几何输入复算最终实际容量。几何基础容量仍是0权重阅读核对，最终容量由`effective_ways.capacity_distribution`评分，不能把两者当成同一Owner。

Split Symbol、超大符号多重占位或符号多重计数规则若在固定布局上改变容量，应记录在`settlement.effective-ways-capacity`节点，不属于`board.variable-grid`标准属性。

不得省略`generator_partitions`、`stack_axis`或`ways_capacity_mode`来回避调查。原版资料不足以证明“存在”或“不存在”时标记缺口；只有证据明确证明不存在时才能写`none`。其他属性不可证明时同样标记缺失或不适用，不根据候选盘面反推生成模型。
