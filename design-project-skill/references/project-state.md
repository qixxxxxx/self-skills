# 项目状态、事务与恢复规范

## 目录

1. 权威关系
2. 目录与项目身份
3. 状态包结构
4. schema 2 元数据
5. 讨论项总账
6. 初始化
7. 软检查点事务
8. 硬检查点事务
9. 恢复、重新打开与迁移
10. 校验与完成门禁
11. 用户状态回执

## 一、权威关系

- 现行 Markdown 文件保存人类可读的项目状态。
- `ITEMS.md` 是全部问题、门槛、假设、暂缓项和阻塞项的结构化总账。
- `.project-state/manifest.json` 保存现行文件哈希、revision、schema 2 历史起始版本、各版本快照 manifest 索引和当前正式快照绑定。
- `.project-state/journal.json` 保存最后一次已授权事务的完整现行状态和当前版本快照，并在现行文件之前写入。
- `versions/` 保存硬检查点的不可变完整快照；`audit` 校验 schema 2 基线以来的每个版本，正式规则必须与当前版本快照一致。
- `PROGRESS.md` 仍最后落盘，但只有 Markdown、manifest、journal 和版本快照同时通过 `audit` 才属于有效提交。
- 聊天记录、Plan、Goal 和上下文压缩摘要都不能覆盖文件状态。

不要直接编辑现行核心文件。先用 `begin` 或 `reopen` 建立隔离工作区，只编辑命令返回的 `work/`，再由 `commit` 统一校验和提交。

## 二、目录与项目身份

### 目录选择

1. 用户指定状态包目录时使用该绝对路径。
2. 用户未指定但只有一个明确项目目录时，先展示拟使用的绝对路径并取得确认。
3. 存在多个候选位置、会影响其他项目或无法判断时询问，不自行猜测。
4. 状态包目录与目标 Skill 创建目录分别确认。

### 身份字段

恢复时同时验证：

- `project_id`
- `project_title`
- `state_id`
- `state_dir`
- `PROJECT.md` 的目标摘要
- 当前检查点和正式版本

`state_id` 在初始化时生成。`state_dir` 保存已确认的绝对路径；复制到其他目录不会被静默视为同一项目。目录确需移动时，先保存现场，再通过明确迁移操作更新路径和所有哈希。

## 三、状态包结构

```text
<state-dir>/
├── PROJECT.md
├── PROGRESS.md
├── ACTIVE.md
├── DECISIONS.md
├── ITEMS.md
├── stages/
├── versions/
│   └── v0000/
│       ├── PROJECT.md
│       ├── PROGRESS.md
│       ├── ACTIVE.md
│       ├── DECISIONS.md
│       ├── ITEMS.md
│       ├── stages/
│       └── .manifest.json
├── recovery/
└── .project-state/
    ├── manifest.json
    ├── journal.json
    ├── finish.json              # 仅最终 finish 通过后存在
    ├── active-transaction.json
    ├── state.lock
    └── transactions/
        └── TX-0001/
            ├── before/
            ├── work/
            └── transaction.json
```

| 位置 | 职责 |
|---|---|
| `PROJECT.md` | 正式目标、范围、非目标、顶层流程、术语和阶段索引 |
| `PROGRESS.md` | 当前版本、阶段、状态、计数和唯一下一动作 |
| `ACTIVE.md` | 当前确认点的完整解释、例子、建议和轮次流水 |
| `DECISIONS.md` | 已确认决定、理由、替代关系和完整规则 |
| `ITEMS.md` | 全部讨论项、依赖、状态、责任人和证据索引 |
| `stages/` | 已确认阶段契约 |
| `versions/` | 硬检查点完整快照与快照哈希 |
| `recovery/` | 异常、迁移和恢复现场；不删除、不覆盖 |
| `.project-state/` | 事务、锁、journal、现行哈希和当前 revision 的最终完成证明；不提交到目标 Skill |

## 四、schema 2 元数据

所有核心文件和阶段文件共同保存：

```yaml
schema_version: "2"
project_id: "example-project"
project_title: "示例项目"
state_id: "DPS-0123456789ab"
state_dir: "/absolute/state/path"
checkpoint: "CP-0000"
formal_version: "v0000"
```

`PROGRESS.md` 另外保存：

```yaml
soft_checkpoint: "SC-0000"
current_level: "project-card"
current_stage: "stage-design"
stage_status: "waiting-confirmation"
project_status: "active"
current_question: "Q-0001"
stage_gates_done: "0"
stage_gates_total: "9"
project_gates_done: "0"
project_gates_total: "9"
blocked_count: "0"
```

项目状态固定为：`active`、`blocked`、`ready-for-build`、`building`、`awaiting-acceptance`、`completed`。

正常前向顺序固定为：`active/blocked → ready-for-build → building → awaiting-acceptance → completed`。进入 `building`、`awaiting-acceptance` 和 `completed` 都必须使用硬事务，且分别只能来自前一个状态；从落地或验收阶段返回设计讨论、以及完成后再次修改，必须使用 `reopen`。

`ACTIVE.md` 另外保存 `explanation_depth: "L1|L2|L3"`。`ITEMS.md`、`ACTIVE.md` 与 `PROGRESS.md` 的软检查点、层级、阶段和当前问题必须一致。`PROGRESS.md` 正文中的“当前确认点、当前阶段、全项目”和 `ACTIVE.md` 正文中的“编号”是固定状态标记，必须与 frontmatter 和总账复算结果一致。

`stage-design` 表示跨目标流程的设计覆盖阶段，初始化的九类门槛全部归入这里；它不代表目标 Skill 的第一业务阶段。用户确认的目标流程阶段才写入 `stages/`，使用各自的 `stage-...` 标识并按需增加对应讨论项和门槛。

完成项目时：

- `project_status` 必须是 `completed`。
- `current_question` 必须是 `none`。
- `ITEMS.md` 不得存在活动问题、活动阻塞或未终结的必需项目。

## 五、讨论项总账

`ITEMS.md` 使用固定九列表格：

```markdown
| ID | 类型 | 必需 | 状态 | 摘要 | 阶段 | 依赖 | 责任人 | 证据或落点 |
|---|---|---|---|---|---|---|---|---|
| Q-0001 | question | yes | active | 确认项目目标 | stage-design | - | 用户 | ACTIVE.md |
| G-01-01 | gate | yes | pending | 项目目标得到确认 | stage-design | Q-0001 | 用户与 AI | 待用户确认 |
```

类型：`question`、`gate`、`assumption`、`deferred`、`blocker`、`fact`、`decision`。

状态：`pending`、`active`、`confirmed`、`completed`、`deferred`、`not-applicable`、`blocked`、`reopened`、`superseded`。

规则：

- 必须且只能有一个 `active` 问题，并与 `current_question` 一致。
- 活动问题的阶段必须与 `current_stage` 一致，所有讨论项阶段使用 `stage-...` 标识。
- 门槛计数从 `gate` 行机械复算，不在 `PROGRESS.md` 手工估算。
- `blocked_count` 统计所有状态为 `blocked` 的讨论项；存在阻塞项时 `project_status` 必须为 `blocked`。
- 完成门槛必须有可复核证据，不能写“待补充”。
- `not-applicable` 和 `superseded` 必须引用 `DECISIONS.md` 中真实存在的决定；用户确认的问题也必须引用对应决定，不能继续指向会被重置的 `ACTIVE.md`。
- `DECISIONS.md` 中每个 `D-...` 标题都必须在 `ITEMS.md` 有同编号 `type=decision` 条目，反向也必须存在；决定不能只留在正文或只留在总账。
- 必需门槛只有 `completed`、`not-applicable` 或 `superseded` 才算终结；`confirmed` 只表示规则已确认但门槛尚未完成。
- `depends_on` 中的所有编号必须存在。
- 问题进入 `active`，或问题/门槛进入 `confirmed`、`completed`、`not-applicable` 前，其依赖必须已经终结；不能越过未关闭的上层项目。
- 既有讨论项不得从总账删除；作废内容使用 `superseded` 并保留决定依据。
- 切换确认点前，把仍有效的假设、暂缓项、阻塞项和后续问题写入总账。
- `ACTIVE.md` 重置后，任何未确认事项都不能只存在于旧流水或聊天中。

## 六、初始化

目录确认后运行：

```bash
/Users/lq/slot_math_env/bin/python "<skill-dir>/scripts/project_state.py" init \
  --state-dir "/absolute/path" \
  --project-id "example-project" \
  --title "示例项目"
```

初始化会：

1. 拒绝覆盖非空目录。
2. 创建 schema 2 核心文件、`ITEMS.md`、版本快照和事务元数据。
3. 建立 `CP-0000`、`SC-0000`、`v0000`、`Q-0001` 和九类从零设计覆盖门槛；不适用项必须后续用证据关闭。
4. 写入 journal、manifest 和版本快照清单。
5. 执行完整 `audit`。

## 七、软检查点事务

有新事实、建议、假设、暂缓项、问题、阻塞或解释内容时：

```bash
/Users/lq/slot_math_env/bin/python "<skill-dir>/scripts/project_state.py" begin \
  --state-dir "/absolute/path" \
  --kind soft \
  --reason "保存本轮讨论"
```

命令返回唯一 `work/` 目录。随后：

1. 只修改该工作区内的 `ACTIVE.md`、`ITEMS.md` 和必要的 `PROGRESS.md`。
2. 不修改现行状态，不修改 `PROJECT.md`、`DECISIONS.md` 或 `stages/`。
3. 保存当前确认点的完整解释、例子、影响、建议和轮次流水。
4. 更新总账中新增或变化的讨论项。
5. 不得把门槛改为 `completed`、`not-applicable` 或 `superseded`，也不得把问题改为 `confirmed`、`completed` 或 `not-applicable`；这些正式终结动作必须进入硬事务。
6. 运行提交：

```bash
/Users/lq/slot_math_env/bin/python "<skill-dir>/scripts/project_state.py" commit \
  --state-dir "/absolute/path"
```

`commit` 先校验工作区，再写 journal，随后原子替换目标文件并最后写 `PROGRESS.md` 和 manifest。任一步中断时不得继续讨论，先运行 `resume` 判断现场。

## 八、硬检查点事务

用户明确确认当前规则后运行：

```bash
/Users/lq/slot_math_env/bin/python "<skill-dir>/scripts/project_state.py" begin \
  --state-dir "/absolute/path" \
  --kind hard \
  --reason "用户确认 Q-0001"
```

在返回的工作区内：

1. 把原确认点改为 `confirmed`、`completed`、`not-applicable` 或 `superseded`。
2. 更新 `DECISIONS.md`、`PROJECT.md` 和受影响阶段文件，并在 `ITEMS.md` 登记同编号决定条目。
3. 更新门槛证据和计数来源。
4. 把遗留项写入 `ITEMS.md`。
5. 除项目最终完成外，准备唯一下一确认点，并在 `ACTIVE.md` 中保存完整说明。
6. 运行 `commit`。

新决定至少包含“决定、证据、影响”。原确认点为 L2 时，还必须保留“实际过程、正常例子”；为 L3 时继续保留“边界例子、异常例子”。原问题必须引用本次新增决定，不能拿旧决定代替本轮落档。

脚本自动递增 CP、正式版本和软检查点，创建带哈希的目标版本快照，并验证正式规则与快照一致。原问题未关闭、下一问题不唯一、状态跳级、决定解释深度不足、决定引用不存在、门槛计数或正文状态标记不符时拒绝提交。

## 九、恢复、重新打开与迁移

### 每轮恢复门

```bash
/Users/lq/slot_math_env/bin/python "<skill-dir>/scripts/project_state.py" resume \
  --state-dir "/absolute/path"
```

`resume` 验证结构、正文、总账、现行哈希、journal、正式快照和活动事务，只输出唯一下一动作。

### 异常恢复

```bash
/Users/lq/slot_math_env/bin/python "<skill-dir>/scripts/project_state.py" recover \
  --state-dir "/absolute/path"
```

恢复前先把现行异常文件保存到新的 `recovery/REC-####/`。journal 候选状态校验通过后才恢复；多余现行文件、损坏的当前快照和未提交的未来快照移动到恢复事件中，不删除，再恢复 journal 保存的现行状态和当前版本快照。旧历史快照损坏时 `audit` 会冻结推进；journal 不保存全部旧版本正文，因此不得伪称已自动修复旧历史。

### journal 修复

如果 journal 缺失、损坏或落后，但 manifest 与现行文件哈希一致、无活动事务、正式规则与当前快照一致，可运行：

```bash
/Users/lq/slot_math_env/bin/python "<skill-dir>/scripts/project_state.py" repair \
  --state-dir "/absolute/path"
```

`repair` 先把旧 journal 和现行状态保存到新的恢复事件，再由可信 manifest、现行文件和当前快照重建 journal，并执行完整 `audit`。manifest/现行文件不一致、活动事务未收尾或快照损坏时拒绝 repair；journal revision 领先时应使用 `recover`。

### 修改已确认规则

```bash
/Users/lq/slot_math_env/bin/python "<skill-dir>/scripts/project_state.py" reopen \
  --state-dir "/absolute/path" \
  --reason "用户要求修改 D-001"
```

`reopen` 创建硬事务。必须把至少一个已终结门槛明确改为 `reopened`，记录被替代决定、影响范围和新的唯一确认点；普通软/硬事务不能重新打开已终结项目，空 `reopen` 也会被拒绝。

### schema 1 迁移

```bash
/Users/lq/slot_math_env/bin/python "<skill-dir>/scripts/project_state.py" migrate \
  --state-dir "/absolute/path"
```

迁移前完整保存 schema 1 现场；原 `versions/` 条目逐项原样移动到本次恢复事件的 `legacy-versions/`，不修改也不删除，并以迁移产生的新版本作为 schema 2 的 `history_start_version`。无法结构化还原、处于终结状态但缺少依据的门槛改为 `reopened`；原阻塞项恢复为 `project_status=blocked`，不编造证据。

## 十、校验与完成门禁

### `validate`

校验 Markdown 结构、frontmatter、正文栏目、讨论项依赖和门槛计数：

```bash
/Users/lq/slot_math_env/bin/python "<skill-dir>/scripts/project_state.py" validate \
  --state-dir "/absolute/path"
```

### `audit`

在 `validate` 基础上继续校验：

- 现行文件与 manifest 哈希一致。
- journal 与现行 revision 和完整内容一致。
- 正式规则与当前版本快照一致。
- 从 `history_start_version` 到当前版本的快照连续、哈希有效且未被事后修改。
- L2/L3 所需正文栏目存在。
- 当前问题、讨论项、决定引用、正文状态标记、门槛计数和项目状态一致。

### AI 语义检查

机器校验通过后，AI 仍需检查目标偏移、术语冲突、输入输出断裂、循环依赖、评价不可测、异常无负责人、模板字段不一致和最终输出不能证明目标完成。

### `finish`

只有用户最终验收已经通过，并通过硬事务提交 `project_status=completed`、`current_question=none` 后运行：

```bash
/Users/lq/slot_math_env/bin/python "<skill-dir>/scripts/project_state.py" finish \
  --state-dir "/absolute/path"
```

`finish` 不替代用户验收，也不自动关闭未决项。脚本只允许 `awaiting-acceptance` 通过用户验收硬事务进入 `completed`；所有必需门槛必须真正完成或有决定依据地排除，且活动问题和阻塞必须为空。通过后写入 `.project-state/finish.json`，绑定当前 `state_id`、revision、版本、检查点、现行文件摘要和正式快照摘要；`resume` 只有在该记录仍与当前状态匹配时才报告“已通过 finish”。

## 十一、用户状态回执

正常状态行从现行状态读取：

```text
状态：<formal_version>｜<checkpoint>｜<soft_checkpoint>｜<current_stage>｜<done>/<total>｜待确认：<current_question>
```

写入、恢复或 audit 失败时只能使用异常模板。模板编号和事件路由以 `user-interaction-templates.md` 为唯一来源。
