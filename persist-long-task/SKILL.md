---
name: persist-long-task
description: 通过项目内状态文件、原子检查点、有界近期历史、失败尝试、文件生命周期、恢复门禁和证据驱动的步骤转换，使长任务在上下文压缩、Goal 自动续跑、会话恢复、工具中断或 Agent 交接后从唯一下一动作继续，避免重做已完成工作或重复失败路线。用于预计跨多轮或长时间、步骤较多、修改多个文件、反复试验、运行长命令，或用户要求持续执行、Plan/Goal 配合、断点续做、压缩后恢复及 Agent 自行维护进度文件的任务。
---

# 长任务持久化协议

把磁盘状态当作执行真相源；聊天记忆、Plan 和 Goal 都只是派生视图。任何恢复场景都先读状态、近期轨迹和现场，再继续唯一的 `next_action`。

## 使用文件

- 默认状态：`<任务根目录>/.codex/long-task/state.json`
- 最新恢复快照：同目录 `journal.json`，先于状态写入且绑定唯一 `state.json` 路径
- `state.json` 内最多保留 12 条 `recent_history`、每步骤 5 条 `attempts` 和 8 条 `task_revisions`；它们用于恢复近期判断，不是无限事件日志
- 状态工具：`scripts/task_state.py`
- 首次建立或处理状态冲突时，完整阅读 [references/state-schema.md](references/state-schema.md)。
- 使用 Plan 或 Goal 时，完整阅读 [references/plan-goal-workflow.md](references/plan-goal-workflow.md)。

使用当前环境规定的 Python。若当前环境是用户的本机环境，调用：

```bash
/Users/lq/slot_math_env/bin/python /Users/lq/.codex/skills/self-skills/persist-long-task/scripts/task_state.py --state <绝对状态路径> <命令>
```

始终传入绝对状态路径，且文件名必须是 `state.json`；多个任务用独立目录区分，避免路径变化或误拼文件名造成分叉。

## 建立任务

1. 确定唯一任务根目录。优先使用仓库根目录；非仓库任务使用用户指定或当前工作目录。
2. 检查默认状态文件。若已存在：
   - 目标相同：恢复，不得重新初始化。
   - `schema_version` 为 `1`、`2` 或 `3`：先运行 `migrate` 建立 schema 4 恢复基线，再恢复。
   - 目标不同且旧任务未完成：停止并询问用户，不得覆盖。
   - 旧任务已完成：为新任务选择用户确认的独立状态目录，或在用户明确授权后处理旧状态。
3. 把工作拆成可独立验收的步骤。每步应能在一次合理工作单元内完成；长步骤继续拆分。最终审计步骤放在最后，后续新增工作用 `add-step --before <最终步骤ID>` 插入到它之前。
4. 初始化状态。步骤可写成 `标题` 或 `标题 => 验收条件`：

```bash
/Users/lq/slot_math_env/bin/python /Users/lq/.codex/skills/self-skills/persist-long-task/scripts/task_state.py --state <绝对路径> init \
  --goal "可验收的最终目标" \
  --workspace-root "<绝对任务根目录>" \
  --scope "本次包含的范围" \
  --constraint "不得破坏用户已有改动" \
  --step "调查现状 => 原因和影响范围有证据" \
  --step "实施修改 => 目标行为已实现" \
  --step "最终验证 => 验收命令全部通过"
```

5. 向用户简短说明状态文件路径。若有 Plan，把这些步骤镜像或归并到高层 Plan；不得让 Plan 取代状态文件。

## 每轮恢复门禁

在每个新回合、Goal 自动续跑、上下文压缩后、Agent 交接后、长时间工具等待后，或只要记忆不确定，修改任何任务文件前必须执行：

1. 运行 `resume` 并读取输出：

```bash
/Users/lq/slot_math_env/bin/python /Users/lq/.codex/skills/self-skills/persist-long-task/scripts/task_state.py --state <绝对路径> resume
```

2. 查看实际现场：任务根目录、`git status --short`、相关 diff、关键产物、最近验证结果，以及上次启动的后台命令是否仍在运行。非 Git 目录改为检查状态中列出的产物。
3. 对照 `current_step`、最近 5 条 `recent_history`、当前步骤的 `attempts`、`last_checkpoint`、带状态的 `changed_files` 和 `next_action`：
   - 证据已证明步骤完成：补记完成状态，不得重做。
   - 有部分产物：从缺失部分继续，不得从步骤开头覆盖重做。
   - 状态与现场矛盾或 `resume` 报告文件生命周期警告：先记录检查点或阻塞，查明后再写业务文件。
4. 若状态有效，只执行唯一 `next_action`。禁止凭聊天摘要重新规划整个任务。
5. 恢复 Plan 时，以状态文件逐项覆盖 Plan 的显示状态；恢复 Goal 时，先读取 Goal，再按状态继续。

没有状态文件、状态损坏或 `journal` 领先时，运行以下命令从最新快照恢复：

```bash
/Users/lq/slot_math_env/bin/python /Users/lq/.codex/skills/self-skills/persist-long-task/scripts/task_state.py --state <绝对路径> recover
```

若 `state.json` 有效而 `journal.json` 缺失、损坏或落后，运行 `repair` 由状态重建快照。两者同 revision 但内容冲突时，先核对实际现场，再明确选择 `recover --force` 或 `repair --force`；不得猜测。

## 执行循环

对每个原子步骤严格执行：

1. `begin <步骤ID> --next-action "当前要执行的具体动作"`，先落盘再工作。
2. 只做当前步骤；子 Agent 不直接写状态，由主 Agent 汇总其证据后单写入。
3. 在以下任一时点立即运行 `checkpoint`：
   - 完成一个可验证工作单元；
   - 修改关键文件或形成不可轻易重建的结论；
   - 即将运行长命令、大批量修改、复杂生成或高上下文消耗操作；
   - 等待外部结果、切换 Agent，或预计可能发生压缩；
   - 距上次检查点已有约 10 分钟。
   - 即将执行不可幂等的外部写操作；先记录目标、预期效果和可用于查重的标识，恢复后先查外部状态，不直接重放。
4. 检查点必须包含已完成摘要和一个具体、唯一的下一动作；同时登记修改文件、验证、关键决定：

```bash
/Users/lq/slot_math_env/bin/python /Users/lq/.codex/skills/self-skills/persist-long-task/scripts/task_state.py --state <绝对路径> checkpoint \
  --summary "已实现配置读取并保留现有兼容分支" \
  --changed "/绝对路径/config.py" \
  --verification "目标单测 12 项通过" \
  --decision "继续兼容旧字段，因为仍有调用方" \
  --next-action "补充缺失字段的回归测试"
```

5. 若一次实现、调参或排错路线失败、结论不确定或成功但值得防止重做，立即用 `attempt` 记录动作、结果、原因和下一动作。每步骤只保留最近 5 条：

```bash
/Users/lq/slot_math_env/bin/python /Users/lq/.codex/skills/self-skills/persist-long-task/scripts/task_state.py --state <绝对路径> attempt \
  --action "直接放宽状态转换" \
  --result failed \
  --reason "破坏必须 reopen 的约束" \
  --next-action "改为只放行显式 reopen 路径"
```

6. 用 `--changed`、`--created`、`--removed`、`--temporary` 或 `--unchanged` 登记文件生命周期；需要说明用途时使用 `--file-role '绝对路径=用途'`。`resume` 会对“应存在却缺失”或“已移除却仍存在”给出现场警告。

7. 只有获得可复核证据后才运行 `complete`。不得只因代码已写完就标记完成：

```bash
/Users/lq/slot_math_env/bin/python /Users/lq/.codex/skills/self-skills/persist-long-task/scripts/task_state.py --state <绝对路径> complete S2 \
  --evidence "tests/test_config.py 全部通过" \
  --changed "/绝对路径/config.py"
```

8. 若用户调整目标、范围或约束，先用 `revise` 记录原因、字段差异和新的下一动作，再同步 Goal/Plan。`scope` 和 `constraint` 是整体替换，必须传完整新列表；重大变化未获明确授权时先询问用户。
9. 若计划变化，使用 `add-step --reason ... [--before ID|--after ID]` 增补，或用 `skip` 同时记录理由和证据。新步骤不能插到已终结历史之前；`blocked` 步骤可直接跳过并保留解除阻塞记录。不要直接改 JSON，也不得越过更早的 pending 步骤。
10. 若受阻，使用 `block --reason ... --next-action ...`；恢复后用 `unblock`。阻塞状态也必须保留唯一下一动作。

## 完成门禁

只在以下条件全部满足时运行 `finish`：

- 所有步骤均为 `completed` 或有证据的 `skipped`；
- 至少一个步骤实际为 `completed`，不能把全部步骤跳过后宣称完成；
- 最终验收已运行且结果已记录；
- 实际 diff、产物和状态文件一致；
- 没有未说明的活动阻塞；
- 用户要求的交付物已存在。

```bash
/Users/lq/slot_math_env/bin/python /Users/lq/.codex/skills/self-skills/persist-long-task/scripts/task_state.py --state <绝对路径> finish \
  --evidence "完整测试套件通过" \
  --evidence "交付文件已生成并人工抽查" \
  --verification "完整验收命令退出码为 0"
```

最后再把 Plan 标为完成；若使用 Goal，确认目标确实达成后才把 Goal 标为 `complete`。状态未通过 `audit` 时不得宣称完成。

## 不可违反的规则

- 不把聊天摘要、Todo、Plan 或 Goal 当成完成证据。
- 不覆盖现有活动状态，不删除历史来“重新开始”。
- 不重做已经有有效证据的步骤。
- 不使用“继续处理”“完成剩余工作”等模糊 `next_action`；写成下一次可直接执行的单一动作。
- 不让多个 Agent 同时更新状态；主 Agent 是唯一写入者。
- 不手工编辑 JSON，除非脚本无法运行；手工修复后必须立即运行 `audit` 并记录原因。
- 不依赖不断增长的聊天或事件全文；恢复所需的当前步骤、证据、近期轨迹、失败尝试、决定、验证和阻塞必须保留在 `state.json`，并受固定上限控制；`journal.json` 只保存最新可恢复快照。
- 把 `.codex/long-task/` 视为本地运行元数据；未经用户同意，不提交它，也不擅自修改 `.gitignore`。
