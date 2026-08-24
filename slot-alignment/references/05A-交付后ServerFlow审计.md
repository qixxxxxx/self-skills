# 交付后 Server Flow 审计

## 执行前提

只在`seal_delivery.py`成功生成不可变`dv####`且`validate_artifacts.py`最终校验通过后执行。读取已封存的候选参数、Runtime、阶段 4 FORMAL硬指标和阶段 5 delivery manifest，全部只读。

## 单次调用规则

- 每个交付版本只执行一个 server flow 验证批次，`attempt_count`固定为 1，不自动重试。
- 只测量总 RTP、完整付费入口中奖率、各类 Feature 自然触发概率、200x 以下倍率分布、适用 Sigma、Base/Feature/其他组件 RTP 贡献等硬指标。
- 不重新执行 CALIBRATION、FORMAL、评分、候选冻结或交付封存。
- 不因 server flow 样本量较小而扩大为第二批；样本不足直接记录警告。

## 状态隔离

审计是交付后的附加观察，不是第六阶段门禁。无论执行成功、失败、超时、异常、样本不足或数值不一致：

- 不修改`artifacts/`及`versions/dv####/`；
- 不改变`alignment_status`、`delivery_status`或 FORMAL 状态；
- 不使候选、FORMAL、阶段报告、交付 manifest 或封包失效；
- 不自动回到阶段 1～5；
- 只把差异和异常写为中文警告。

## 固定输出

```text
post-delivery-server-flow/
└── dv####/
    ├── post_delivery_server_flow_audit.json
    └── 交付后ServerFlow验证报告.md
```

目录必须位于`artifacts/`之外。机器 JSON 绑定`delivery_version`、交付 manifest、FORMAL结果和阶段3 scorecard SHA-256，记录单次执行状态、输入 hash、样本、硬指标对照、异常和警告。中文报告由`render_post_delivery_server_flow_report.py`确定性生成；生成器以密封 FORMAL 硬指标清单为准，FORMAL未内嵌硬指标时回退读取阶段3 scorecard。缺少任一适用硬指标对照时必须显示警告，不得显示`审计通过`。

## 报告结论

- 全部可比硬指标一致且执行成功：显示`审计通过`，同时声明“不改变既有交付状态”。
- 任一指标不一致、不可比、样本不足或执行失败：显示`警告`并逐项列出原因。
- 报告不得使用`FORMAL失败`、`交付失败`、`封包失效`或任何会覆盖既有状态的措辞。
