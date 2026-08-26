# 盘面与符号多样性指标

版本：2.0.0
Owner：`atomic.board-diversity`

## Owner边界

`atomic.board-diversity`只评价玩家实际看到的逐符号数量、同盘符号共现广度、跨分区分配、连续结构和稳定生成单元集中度。符号出镜率与格占比都由完整单盘数量分布派生。同一可见盘面、符号和计数范围下，Trigger数量及确定性Count Pay中奖构成/计数尾部也不得重复评分。

## 指标清单

| 顺序 | 指标ID | 中文名 | 类型 | 语义角色 | Owner及重叠关系说明 |
|---:|---|---|---|---|---|
| 10 | `board.symbol_presence_distribution` | 符号出镜盘面分布 | 审计指标 | 派生诊断 | 由单盘符号数量分布的0个桶精确推出，不独立计分。 |
| 20 | `board.symbol_cell_share_distribution` | 符号可见格占比分布 | 审计指标 | 派生诊断 | 由单盘符号数量分布的期望值和有效格数精确推出，不独立计分。 |
| 30 | `board.symbol_count_per_board_distribution` | 单盘符号数量分布 | 评分指标 | 主评价 | 拥有可见完整盘面的符号数量边际；同源Trigger与Count Pay实例只派生展示。 |
| 35 | `board.distinct_visible_symbol_count_distribution` | 单盘不同可见符号种类数分布 | 评分指标 | 主评价 | 拥有同一完整盘面的符号共现广度；逐符号数量边际无法推出同盘组合，不重复也不互相替代。 |
| 40 | `board.symbol_partition_count_vector_given_total_distribution` | 指定全盘数量下的分区计数向量分布 | 评分指标 | 主评价 | 给定数量评价跨分区分配；无损Trigger位置模式可推出时对应符号组不重复评分。 |
| 50 | `board.max_symbol_stack_length_given_count_distribution` | 指定全盘数量下的单盘最大连续长度分布 | 评分指标 | 主评价 | 给定数量评价最大连续结构；无损Trigger位置模式可推出时对应符号组不重复评分。 |
| 60 | `board.generation_concentration` | 生成单元重复碰撞率 | 评分指标 | 主评价 | 评价稳定生成单元的结果重复集中程度，不使用完整盘面签名。 |

## 派生与交叉关系

- `board.symbol_presence_distribution` ← `board.symbol_count_per_board_distribution`：由单盘符号数量分布的0个桶精确推出，不独立计分。
- `board.symbol_cell_share_distribution` ← `board.symbol_count_per_board_distribution`：由数量期望除以同作用域有效格数精确推出，不独立计分。
- `board.distinct_visible_symbol_count_distribution`与逐符号数量边际互为交叉核对：前者统计一盘同时出现几种符号，后者统计每种符号各出现几个；边际相同不代表同盘共现结构相同，因此两项均为独立主Owner。
- 两个空间指标都以`board.symbol_count_per_board_distribution`为条件，只补充跨分区分配和连续结构，不重复符号总量。
- 同一可见盘面、符号和计数范围下，Trigger数量与确定性Count Pay中奖构成/计数尾部由盘面数量目标复算，不获得独立评分预算。
- Trigger位置模式保存无损实际坐标时，同符号同作用域的分区向量与最大连续长度是派生摘要；有损模式并有不可推出证据时才并存。


## 使用约束

- 每个评分指标只有一个Owner和一个score_budget_key；同一指标拆分多个作用域时先按scope_aggregation聚合，不按实例数量自然增权。
- derived_diagnostic和audit的score_weight固定为0，不进入综合分。
- 条件分布只在其条件组内归一化；完整边际由对应主指标负责，禁止再次保存原始联合分布重复计分。
- 分组分布移除结构可达支持仅一项的局部退化组，并按原版活动组权重重新归一；全部条件组退化时整项使用`degenerate_reachable_support`标记不适用，不生成常量满分。
- 目标分桶、实际业务标签、样本单位和条件分母必须在查看候选结果前密封。
