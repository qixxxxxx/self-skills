# 状态与恢复快照规范

## 目录导航

- [目录](#目录)
- [`state.json` 字段](#statejson-字段)
- [写入协议](#写入协议)
- [核心不变量](#核心不变量)
- [恢复与修复决策](#恢复与修复决策)
- [命令摘要](#命令摘要)
- [旧版迁移](#旧版迁移)

## 目录

```text
<任务根目录>/.codex/long-task/
├── state.json       # 当前权威进度
├── journal.json     # 最新预写恢复快照
└── state.json.lock  # 同一任务的串行写锁
```

一个目录只承载一个任务，状态文件名固定为 `state.json`。`journal.json` 内保存绝对 `state_path`，脚本拒绝向同目录的其他文件名恢复。旧版迁移后可能保留 `events.jsonl`，新版不读取、追加或依赖它。

## `state.json` 字段

| 字段 | 含义 |
|---|---|
| `schema_version` | 协议版本，当前为 `4` |
| `revision` | 每次任务状态写入递增 |
| `task_id` | 初始化时生成的任务标识 |
| `workspace_root` | 绝对任务根目录 |
| `goal` | 可验收的最终目标 |
| `scope` / `constraints` | 范围和持续约束 |
| `status` | `in_progress`、`blocked` 或 `completed` |
| `steps` | 有序步骤、验收条件、状态、证据、完成摘要及最近尝试 |
| `current_step` | 唯一活动步骤 ID；最终阶段可为 `null` |
| `next_action` | 恢复后先执行的唯一具体动作 |
| `last_checkpoint` | 最近一次已落盘摘要和时间 |
| `changed_files` | 文件绝对路径、生命周期状态、用途和最近登记 revision |
| `decisions` / `verification` | 关键决定和验证结果 |
| `blockers` | 阻塞、重复次数、解决方式及活动状态 |
| `final_evidence` | 无活动步骤时的阶段证据及最终证据 |
| `recent_history` | 最近 12 次状态转换的 revision、摘要、步骤、结果和下一动作 |
| `task_revisions` | 最近 8 次目标、范围或约束修订的原因和字段差异 |
| `created_at` / `updated_at` | UTC 时间戳 |

步骤状态：`pending`、`in_progress`、`blocked`、`completed`、`skipped`。

每个步骤还包含：

- `attempts`：最近 5 次值得防止重做的尝试，记录动作、`failed`/`inconclusive`/`succeeded` 结果及原因；
- `completion_summary`：步骤终结时的压缩结论；未终结步骤必须为 `null`。

文件状态：`created`、`modified`、`removed`、`temporary`、`unchanged`。结构审计不依赖现场文件是否存在；`audit` 和 `resume` 会另外输出生命周期警告。

## 写入协议

每个修改命令在同一文件锁内执行：

1. 读取并校验 `state.json` 与 `journal.json` 一致。
2. 计算下一 revision，并把本次事件压缩到 `recent_history`；超过 12 条时丢弃最早记录。
3. 用临时文件、文件 `fsync`、原子替换和父目录 `fsync` 写入新的 `journal.json`。
4. 用相同方式写入 `state.json`。

因此：

- journal 写失败：state 不前进；
- journal 成功、state 写失败或进程中断：journal 比 state 更新，运行 `recover`；
- 两次写入都成功：同 revision 的内容完全一致；
- 不需要扫描不断增长的历史文件，恢复成本与当前状态大小相关。

## 核心不变量

`audit` 同时验证结构和磁盘一致性：

1. 根节点、嵌套对象和文本字段类型正确，关键文本不得为空白。
2. 步骤 ID 唯一，最多一个活动步骤，`current_step` 与其一致。
3. `completed` 有证据和完成摘要；`skipped` 同时有理由、现场证据和完成摘要。
4. 活动任务有唯一 `next_action`；活动阻塞只存在于 `blocked` 任务。
5. 完成任务所有步骤已终结、至少一个实际完成步骤、存在最终证据和非空验证、无活动阻塞。
6. `recent_history`、`attempts` 和 `task_revisions` 不超过固定上限，历史 revision 严格递增。
7. 文件记录路径唯一且为绝对路径，生命周期和 revision 有效。
8. journal 的 `state_path`、`task_id`、revision、时间和 `state_after` 与 state 一致。

## 恢复与修复决策

| 现场 | 动作 |
|---|---|
| state 缺失、损坏或 revision 落后，journal 有效 | `recover` |
| journal 缺失、损坏或 revision 落后，state 有效 | `repair` |
| 两者同 revision 且内容冲突 | 核对 Git/产物后选 `recover --force` 或 `repair --force` |
| 两者都损坏 | 依据 Git、产物和用户信息重建新状态，并明确不确定项 |
| state 已完成但证据失效 | 在独立目录建立修复任务，不改写已完成任务 |

`recover` 不增加 revision；它把 journal 的已授权快照恢复为 state。`repair` 也不增加 revision；它只由有效 state 重建 journal。

## 命令摘要

```text
init        创建 schema 4 任务，拒绝覆盖已有元数据
resume      校验并打印紧凑恢复摘要
show        校验后输出完整 state JSON
audit       校验状态结构及 state/journal 一致性
recover     由 journal 恢复缺失、损坏或落后的 state
repair      由有效 state 重建缺失、损坏或落后的 journal
migrate     把 schema 1、2 或 3 状态迁移为 schema 4
begin       按顺序开始最早 pending 步骤
checkpoint 保存成果、证据、决定、验证和下一动作
attempt     保存当前步骤的尝试、结果、原因和下一动作
complete    用证据完成当前步骤
revise      按用户指令更新目标、范围或约束
add-step    追加步骤，或用 before/after 插入非历史位置
skip        带理由和证据跳过步骤，包括 blocked 步骤
block       保存阻塞及恢复动作
unblock     解除阻塞并继续
finish      通过最终证据和非空验证结束任务
```

## 旧版迁移

`migrate` 支持 schema 1、2 和 3。若 state 缺失，它优先使用 journal 的完整快照，再尝试旧 `events.jsonl` 最后一条完整 `state_after`；两者都没有时不能自动恢复。

迁移时：

- 为步骤补充 `attempts` 和 `completion_summary`；
- 把旧字符串 `changed_files` 转为生命周期记录，迁移时不存在的路径标为 `removed`；
- 建立空的有界历史，并以迁移事件作为第一条 `recent_history`；
- 旧版 `skipped` 缺少证据时，逐项传入 `--skip-evidence 'S1=现场证据'`；
- 完成任务没有验证时，传入非空 `--final-verification '最终验证结果'`。

不得为了迁移编造证据。旧日志只保留作人工审计，不参与 schema 4 的日常恢复。
