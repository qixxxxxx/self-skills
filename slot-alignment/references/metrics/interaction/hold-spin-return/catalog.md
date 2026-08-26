# Hold & Spin终局回报交互指标包

版本：2.2.0  
Owner：`interaction.hold-spin-return`

## Owner边界

仅承接“实际容量下终局锁定占用格数与完整回报之间的依赖残差”。终局占用边际仍由`atomic.hold-and-spin`负责，完整回报边际仍由`composite.feature-cycle`负责，避免重复评分。

## 指标清单

| 指标 | 用途 | 单位 |
|---|---|---|
| `hold_spin.return_dependence_by_terminal_occupancy` | 对齐实际容量、终局锁定占用格数与完整回报之间的纯依赖 | 百分点差 |

按“实际容量×终局占用格数”分组：组内平均各回报档残差的绝对误差，再按任务合同中候选前密封的原版组权重汇总。
