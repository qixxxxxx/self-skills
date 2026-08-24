# 项目状态、检查点与恢复规范

## 目录

1. 权威关系
2. 目录选择与项目身份
3. 状态包结构
4. 元数据约定
5. 初始化
6. 软检查点
7. 硬检查点
8. 两级恢复
9. 门槛进度
10. 校验与一致性
11. 异常保存与回退
12. 用户状态回执

## 一、权威关系

- 完整现行文件代表当前有效状态。
- `PROGRESS.md` 是检查点最后提交标记和轻量恢复入口。
- `ACTIVE.md` 是当前尚未确认讨论的恢复入口。
- `PROJECT.md` 保存完整正式方案和阶段索引。
- `DECISIONS.md` 保存正式决定、理由和替代关系。
- `versions/` 保存不可变快照，只用于审计、比较和回退。
- 聊天记录、模型记忆和上下文压缩摘要不具有覆盖文件状态的权力。
- 用户最新明确要求可以提出变更，但必须落档后才能成为新的正式状态。

## 二、目录选择与项目身份

### 目录规则

1. 用户明确指定状态包目录时使用该绝对路径。
2. 用户未指定但只有一个明确项目目录时，展示拟使用的绝对路径并在首次写入前确认。
3. 存在多个候选目录、目标不明确或写入可能影响其他项目时询问。
4. 不自行改用 Skill 目录、用户主目录、临时目录或其他仓库。
5. 状态包目录与最终 Skill 创建目录分别确认。

### 项目身份

项目标识使用小写字母、数字和连字符。恢复已有状态包时至少比对：

- `project_id`
- `project_title`
- `PROJECT.md` 中的目标摘要
- 状态包绝对路径
- 最后已提交检查点

身份一致且校验通过时恢复；身份一致但异常时进入恢复事件；身份不一致或无法判断时询问。不得覆盖或删除已有状态包。

## 三、状态包结构

```text
<state-dir>/
├── PROJECT.md
├── PROGRESS.md
├── ACTIVE.md
├── DECISIONS.md
├── stages/
├── versions/
│   └── v0000/
│       ├── PROJECT.md
│       ├── PROGRESS.md
│       ├── ACTIVE.md
│       ├── DECISIONS.md
│       └── stages/
└── recovery/
```

职责：

| 位置 | 职责 |
|---|---|
| `PROJECT.md` | 当前正式目标、范围、非目标、顶层流程、术语、评价规则和阶段索引 |
| `PROGRESS.md` | 当前检查点、版本、软检查点、阶段、门槛、阻塞项、当前问题和下一步 |
| `ACTIVE.md` | 顶部当前完整快照；底部当前确认点逐轮流水 |
| `DECISIONS.md` | 决定编号、目的、场景、选项、利弊、选择、理由和替代关系 |
| `stages/` | 复杂阶段的输入、动作、输出、完成条件、评价、异常和责任边界 |
| `versions/` | 每个硬检查点的完整不可变快照 |
| `recovery/` | 异常事件现场，不删除、不覆盖 |

## 四、元数据约定

所有核心 Markdown 文件顶部使用简单 YAML frontmatter。字符串使用引号；编号使用固定宽度。

### `PROJECT.md`

```yaml
---
schema_version: "1"
document_type: "project"
project_id: "example-project"
project_title: "示例项目"
checkpoint: "CP-0000"
formal_version: "v0000"
---
```

### `PROGRESS.md`

```yaml
---
schema_version: "1"
document_type: "progress"
project_id: "example-project"
project_title: "示例项目"
checkpoint: "CP-0000"
formal_version: "v0000"
soft_checkpoint: "SC-0000"
current_level: "project-card"
current_stage: "stage-1"
stage_status: "waiting-confirmation"
current_question: "Q-0001"
stage_gates_done: "0"
stage_gates_total: "1"
project_gates_done: "0"
project_gates_total: "1"
blocked_count: "0"
---
```

### `ACTIVE.md`

```yaml
---
schema_version: "1"
document_type: "active"
project_id: "example-project"
project_title: "示例项目"
checkpoint: "CP-0000"
formal_version: "v0000"
soft_checkpoint: "SC-0000"
current_level: "project-card"
current_stage: "stage-1"
current_question: "Q-0001"
---
```

### `DECISIONS.md`

```yaml
---
schema_version: "1"
document_type: "decisions"
project_id: "example-project"
project_title: "示例项目"
checkpoint: "CP-0000"
formal_version: "v0000"
---
```

阶段文件使用 `document_type: "stage"`，并增加 `stage_id`。所有参与当前正式状态的文件必须使用相同 `project_id`、`checkpoint` 和 `formal_version`。

编号规则：

- 硬检查点：`CP-0000`、`CP-0001`……
- 软检查点：`SC-0000`、`SC-0001`……
- 正式版本：`v0000`、`v0001`……
- 决定：`D-001`、`D-002`……
- 确认点：`Q-0001`、`Q-0002`……
- 门槛：`G-01-01`、`G-01-02`……
- 恢复事件：`REC-0001`、`REC-0002`……

固定阶段状态：

| 中文语义 | 元数据值 |
|---|---|
| 未开始 | `not-started` |
| 讨论中 | `discussing` |
| 等待确认 | `waiting-confirmation` |
| 已确认 | `confirmed` |
| 阻塞 | `blocked` |
| 重新打开 | `reopened` |
| 已完成 | `completed` |

## 五、初始化

目录获得确认后，可以运行：

先将 `<skill-dir>` 替换为当前 Skill 目录的绝对路径，不依赖调用时的工作目录：

```bash
/Users/lq/slot_math_env/bin/python "<skill-dir>/scripts/project_state.py" init \
  --state-dir "/absolute/path" \
  --project-id "example-project" \
  --title "示例项目"
```

初始化必须：

1. 拒绝覆盖已有核心文件。
2. 创建核心文件、`stages/`、`versions/v0000/` 和 `recovery/`。
3. 建立 `CP-0000`、`SC-0000`、`v0000` 和首个确认点。
4. 将初始快照写入 `versions/v0000/`。
5. 执行结构校验。

初始化文件只记录已知事实和明确的待确认项，不把 AI 推测写成项目目标。

## 六、软检查点

### 触发条件

本轮新增事实、约束、修正、建议、方案、理由、示例、假设、待确认项、阶段状态、阻塞项或下一步时触发。

### 写入顺序

1. 保持 `checkpoint` 和 `formal_version` 不变。
2. 递增 `soft_checkpoint`。
3. 更新 `ACTIVE.md` 顶部完整快照。
4. 在 `ACTIVE.md` 当前确认点流水中追加轮次记录。
5. 更新 `PROGRESS.md` 的软检查点、阶段、当前问题、门槛或下一步；`PROGRESS.md` 最后写入。
6. 运行当前状态结构校验。
7. 校验通过后再回复用户。

### `ACTIVE.md` 顶部快照内容

- 当前正式版本、硬检查点和软检查点。
- 当前层级、阶段和唯一确认点。
- 当前解释深度：L1、L2 或 L3，以及选择该深度的原因。
- 当前确认点的目的、影响范围和使用场景。
- 已知事实、用户修正和约束。
- 候选方案、优缺点、AI 建议和理由。
- 面向用户的普通语言规则，以及采用后实际先做什么、再做什么、最后得到什么。
- 与当前项目一致的正常例子；L3 同时保存边界和异常例子。
- 涉及算法时，保存输入及单位、执行步骤、小数字演算、结果含义、边界、限制，以及放在示例之后的公式。
- 涉及固定报告、清单或文档模板时，保存逐章展示目的、展示方式、必需字段及顺序、数据来源、空值规则、Markdown实例和一致性检查。
- 临时假设和替换条件。
- 本轮确认什么、明确不确认什么，以及用户只需要回答的问题。
- 确认后的下一步。

流水记录轮次、用户输入摘要、新增或修改内容、AI 方案及本轮状态变化。流水只覆盖当前确认点；确认后将用户确认时看到的完整规则、例子、算法说明和确认边界归档到 `DECISIONS.md`，不得只保留一句结论。

## 七、硬检查点

### 进入条件

用户明确确认当前决定，或直接提供无歧义正式规则。模糊认可、部分接受或附带新条件时继续软检查点，不得自动提交。

### 提交顺序

1. 生成新的决定编号、硬检查点、正式版本和软检查点。
2. 在 `versions/<new-version>/` 准备完整目标快照，包括核心文件和全部当前阶段文件。
3. 验证目标快照：

```bash
/Users/lq/slot_math_env/bin/python "<skill-dir>/scripts/project_state.py" validate \
  --state-dir "/absolute/path" \
  --snapshot "v0001"
```

4. 更新现行 `DECISIONS.md`。
5. 更新现行 `PROJECT.md` 和受影响阶段文件。
6. 将现行 `ACTIVE.md` 初始化为下一个确认点。
7. 执行结构和语义预提交检查。
8. 最后更新现行 `PROGRESS.md`，提交新检查点。
9. 重新验证现行状态：

```bash
/Users/lq/slot_math_env/bin/python "<skill-dir>/scripts/project_state.py" validate \
  --state-dir "/absolute/path"
```

只有 `PROGRESS.md` 标记的检查点属于已提交状态。其他文件编号较新但 `PROGRESS.md` 未提交时，视为部分写入。

`DECISIONS.md`、正式规则和 `versions/<new-version>/` 必须保留用户确认时看到的解释深度和完整含义，包括适用范围、实际过程、正常/边界/异常例子、影响与代价。涉及算法时还要保留输入、单位、计算顺序、示例数字、结果含义、权重、阈值、公式和异常处理。不得为了缩短快照而压缩成编号加一句摘要。

## 八、两级恢复

### 轻量恢复门

每个有效回合读取 `PROGRESS.md` 和 `ACTIVE.md` 顶部，核对：

- 项目标识
- 硬检查点和正式版本
- 软检查点
- 当前层级和阶段
- 唯一确认点
- 门槛进度、阻塞项和下一步

### 完整恢复触发条件

- 首次打开、跨时段继续或已知发生上下文压缩。
- 轻量文件不一致或当前问题无法解释。
- 用户要求修改历史规则。
- 当前问题依赖项目方案、阶段细则或决定理由。
- 即将硬提交、阶段切换、全局定稿或 Skill 落地。

完整恢复读取 `PROJECT.md`、完整 `ACTIVE.md`、相关 `DECISIONS.md`、当前和直接依赖阶段文件，必要时读取最近已提交版本。不要加载无关历史。

恢复当前确认点时，至少恢复其原有解释深度：原来是 L2，就重新展示背景、过程、正常例子、边界、影响和建议；原来是 L3，就同时恢复正常、边界、异常场景以及算法的可复算例子。不能因为上下文压缩而把完整规则降成几句摘要，也不能根据一句旧摘要重新猜测细节。

## 九、门槛进度

每个门槛至少记录：

- 稳定唯一编号
- 所属阶段
- 完成条件
- 验收证据
- 当前状态
- 关闭依据
- 责任边界
- 重开记录

只有具有证据的完成门槛计入完成数。新增范围增加总数；删除或不适用必须有决定记录；重新打开立即移出完成数。进度以“已完成门槛数/已定义总门槛数”表达，不使用主观百分比。

## 十、校验与一致性

### 结构校验

使用 `scripts/project_state.py validate` 检查：

- 核心文件和目录存在。
- frontmatter 必填字段和编号格式正确。
- 项目标识、检查点、版本、阶段和确认点一致。
- 当前版本快照存在并可以解析。
- 阶段状态、门槛计数和阻塞数合法。
- 被引用的阶段文件存在。

### 语义检查

AI 检查：

- 目标偏移和范围越界。
- 术语、状态、对象和单位冲突。
- 阶段输入输出断裂、职责空白和循环依赖。
- 决定互相矛盾或隐式替代。
- 评价指标缺少数据来源或无法验收。
- 异常缺少负责人、动作或回退点。
- 最终输出无法证明顶层目标完成。
- 普通用户无法说明当前要决定什么、采用后会发生什么。
- 抽象规则缺少项目内例子，或 L3 缺少正常、边界、异常情况。
- 算法只有公式或最终数字，没有输入、步骤、示例计算、结果含义、边界和限制。
- 固定输出模板只有章节名，没有逐章展示目的、方式、字段顺序、数据来源、空值规则和Markdown实例；或同类字段的名称、单位、顺序不一致。
- 恢复后的解释深度低于保存时的深度，或确认内容需要重新猜测。

硬检查点、阶段切换、异常恢复、全局定稿和 Skill 落地前必须同时通过结构与语义检查。

## 十一、异常保存与回退

发现半完成检查点或损坏状态时：

1. 冻结新的讨论和提交。
2. 创建唯一 `recovery/REC-####/`。
3. 将每个异常文件分别复制到事件目录，记录来源路径、编号和校验错误；不删除原文件。
4. 确定最后已提交检查点及其完整版本。
5. 只有以下条件全部满足时才恢复：
   - 最后已提交检查点无歧义。
   - 对应版本完整且通过校验。
   - 当前异常可证明是部分写入，而非用户有意修改。
   - 所有异常和未确认内容已经保存。
   - 不需要猜测用户意图或合并竞争版本。
6. 恢复后重新执行结构、语义和轻量恢复检查。
7. 任一条件不满足时停止并询问用户。

不批量删除恢复事件、历史版本或异常文件。

## 十二、用户状态回执

用户可见格式以 `user-interaction-templates.md` 为唯一模板来源，本文件只定义状态数据约束，避免两处模板发生偏差。需要判断说明是否足够易懂，或涉及算法、评分、权重、概率和阈值时，同时按 `human-readable-explanations.md` 检查。

正常状态行必须从 `PROGRESS.md` 读取：

```text
状态：<formal_version>｜<checkpoint>｜<soft_checkpoint>｜<current_stage>｜<done>/<total>｜待确认：<current_question>
```

总门槛尚未定义时显示“总门槛待定义”，不伪造分母。

事件映射：

- 普通单一确认点：T-02。
- 多方案比较：T-03。
- 部分确认或歧义：T-04。
- 硬检查点完成：T-05。
- 阶段完成：T-06。
- 只查询状态：T-07。
- 完整恢复：T-08。
- 异常或阻塞：T-09。
- 请求 Skill 落地授权：T-10。
- Skill 落地完成：T-11。

输出前必须验证模板中的版本、检查点、阶段、门槛和确认点与现行状态一致。恢复或写入失败时不得使用正常成功模板。
