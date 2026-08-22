# Core 通用指标包

所有游戏必加载。硬指标包括总 RTP、完整付费入口中奖率、每类 Feature 自然触发率、200x 以下倍率分布、Sigma 与组件 RTP 贡献。200x 以上长尾、最大中奖、封顶和溢出只审计，不计分但不能丢失。

- `core.rtp.total`：总 RTP 硬门禁。
- `core.hit_rate.paid_entry`：完整付费入口中奖率硬门禁。
- `core.feature.natural_trigger_rate`：每类 Feature 自然触发率硬门禁。
- `core.multiplier_distribution.lt200`：200x 以下固定倍率桶硬门禁。
- `core.sigma`：总体及适用组件 Sigma 硬门禁。
- `core.rtp.component_contribution`：Base、Feature 和其他组件 RTP 贡献硬门禁。
- `core.long_tail.audit`：200x 以上固定倍率桶审计。
- `core.max_win.audit`：最大中奖、封顶与溢出审计。
