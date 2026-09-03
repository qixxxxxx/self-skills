---
name: slot-alignment
description: 基于Slot原版样本、Runtime和用户认证Python脚本，建立完整N数值、J中奖结算、P玩法过程、B盘面呈现合同，自动生成候选并执行独立FORMAL对齐和中文交付。用于老虎机原版数值或体验对齐、基线诊断、指标规划、自动调参、候选排序、FORMAL验收及Runtime交付；实现事实源只包含Runtime与用户认证脚本，不验证服务端。
---

# Slot 原版体验对齐 7.0.0

## 目标

在不改变玩法语义的前提下，用原版样本冻结玩家可感知目标，通过Runtime授权参数自动对齐，并交付同一认证脚本独立FORMAL验证过的Runtime、机器结果和中文报告。

## 必读文件

按任务范围读取，不要每次加载无关内容：

| 任务 | 必读文件 |
|---|---|
| 建立画像或指标 | [指标与画像](references/01-指标框架.md) |
| 编译合同或解释评分 | [评价合同](references/02-评价合同.md) |
| 执行对齐或交付 | [轻量执行流程](references/03-执行与报告.md) |
| 创建或校验任务目录 | [工作区结构](references/04-工作区目录结构.md) |
| 规划候选或FORMAL样本 | [样本与执行](references/05-性能与执行预算.md) |

机器事实源优先级固定为：政策JSON与指标目录JSON → Schema → 冻结合同 → 脚本结果 → Markdown解释 → 模板。

## 实现事实源

只使用以下两项确定本次可实现能力：

1. 密封Runtime四件套；
2. 用户明确认证的Python脚本。

候选、基线和FORMAL必须调用同一认证脚本核心。优化器只生成Runtime参数，不得重新实现RNG、盘面生成、状态机、Feature或结算。

不读取或验证服务端实现，不建立多层能力矩阵，不证明认证脚本与其他实现一致。Runtime中存在但认证脚本不能读取或执行的字段，本次视为不可调；需要扩展时先取得新的用户认证。

## 红线

- 原版资料、原始样本、密封Runtime和认证脚本只读。
- 只调整`preflight.json.parameter_authority`明确授权的Runtime参数。
- 轴数、盘面几何、符号域、玩法、状态机、触发、结算、RNG调用顺序、投注口径和封顶语义保持不变。
- 原版样本只用于目标、诊断和验收，不得作为候选或FORMAL的出盘数据。
- 每个随机步骤只抽取一次并立即生效。禁止结果导向重抽、拒绝采样、递归搜索、回溯、失败换seed或先定结果再生成。
- 允许按显式权重一次选择认证脚本支持的ReelSet、补符profile或条件类别；选择结果只能路由后续原生分布。
- 画像命中的指标必须在候选前冻结为活动、观察或不适用，候选结果不得改变角色。
- FORMAL使用冻结候选、同一认证脚本和新的独立seed；失败不得换seed重刷。
- 未经用户明确授权，不同步配置、不提交Git、不热更新、不发布。

## 必需输入

从用户输入、项目`AGENTS.md`和当前工作区解析：

```text
directory_map
runtime_environment
python_bin
game_code
game_name_zh
mode
task_id
target_rtp
certified_script
sample_plan
baseline_runtime
parameter_authority
game_profile
```

- Python只使用解析出的`python_bin`；本机默认`/Users/lq/slot_math_env/bin/python`。
- `rtp_group`固定为整数`1`。
- `task_id`缺失时生成`aln-<mode>-<YYYYMMDD>-<NNN>`，创建前确认目录不存在。
- `runtime_version`固定等于`task_id`。
- 唯一`target_rtp`必须由用户提供或明确确认，取值位于`(0,1]`。
- 脚本、样本计划、Runtime、调参权限、工作区或画像存在关键歧义时先询问，不自行猜测。

## 四阶段流程

### 1. 开工准备

一次确认认证脚本、样本数、Runtime、调参能力、工作区和游戏画像，密封Runtime四件套并生成`artifacts/preflight.json`。

只做最小可运行检查：Runtime可以被认证脚本加载；授权参数可以被脚本读取；固定seed可以完成小样本运行。检查通过记为`READY_FOR_SAMPLES`。

### 2. 样本整理

只读扫描原版样本，统一聚合完整入口数、组件、Feature、结算、连续结算、特色机制和稳定盘面统计，生成`artifacts/source_summary.json`。

默认只保留聚合计数、目标值、证据路径和hash；只有排错时才保存少量事件样本。不得为每个指标拆分独立证据文件。

### 3. 指标与评分合同

使用玩法画像、`source_summary.json`、指标目录和评价政策生成`artifacts/metric_contract.json`，冻结全部N/J/P/B实例、角色、目标、分母、距离、C级通过值、评分和FORMAL样本要求。

合同通过Schema、实例完整性、目标证据和内部hash检查后记为`READY_FOR_ALIGNMENT`。合同冻结后，目标、画像、Runtime基线、认证脚本或参数权限变化会使已有候选失效；Worker和micro-batch等执行细节变化不改变业务合同。

### 4. 自动对齐、FORMAL与交付

先把基线作为`candidate_id=baseline`评价；通过时可直接进入FORMAL，不通过时进行参数敏感性和候选搜索。

候选默认使用`PROBE → SCREEN → REFINE → FINAL`累计阶梯，但允许按冻结规则提前淘汰、提前晋级或升级参数面，不要求每个参数层跑满全部档位。普通候选只写入`work/candidate_ledger.jsonl`；只有唯一入选候选才物化完整Runtime。

FORMAL重新运行合同中的全部活动指标，不复用候选统计。完成后生成：

```text
artifacts/alignment_manifest.json
artifacts/formal_result.json
artifacts/delivery_manifest.json
交付物/runtime/四件套
交付物/报告文档/对齐报告.md
```

搜索穷尽仍无通过候选时，选择证据最完整的最优候选执行一次FORMAL并交付不通过证据。

## 唯一评价规则

每个活动实例只按以下链路判定：

```text
D = 距离(冻结目标, 候选结果)
通过 = D <= C级通过值T
T > 0时，偏差倍数R = D / T
单项分 = max(0, 100 × (1 - R))
```

任一活动实例失败，整体不能通过；高分不能补偿失败项。观察项不参与通过和评分，但必须完整披露。最终状态只允许`通过`、`不通过`或`无法完整判定`。

## 确定性工具

```bash
<python_bin> scripts/validate_metric_library.py
<python_bin> scripts/validate_preflight.py --preflight <preflight.json>
<python_bin> scripts/validate_source_summary.py --summary <source_summary.json>
<python_bin> scripts/compile_metric_contract.py --preflight <preflight.json> --source-summary <source_summary.json> --output <metric_contract.json>
<python_bin> scripts/evaluate_alignment.py --contract <metric_contract.json> --measurements <measurements.json> --phase <BASELINE|CALIBRATION|FORMAL> --output <result.json>
<python_bin> scripts/validate_workspace_layout.py --task-root <任务根目录> --through-stage <1-4>
<python_bin> scripts/validate_delivery.py --task-root <任务根目录>
<python_bin> scripts/render_alignment_report.py --preflight <preflight.json> --contract <metric_contract.json> --result <formal_result.json> --output <对齐报告.md>
```

## 完成条件

- 六份权威JSON、交付Runtime和唯一中文报告存在并通过校验。
- 候选账本逐条绑定用户认证脚本和当前合同；FORMAL绑定同一认证脚本、唯一候选Runtime hash并使用独立seed。
- 全部活动N/J/P/B实例得到S/A/B/C、F或有证据的U；观察项和不适用项完整披露。
- 不存在未解决占位、合同漂移、未授权参数、结果导向重抽或经验盘面出盘。
- 交付Runtime与FORMAL实际使用的Runtime逐文件一致，`rtp_group=1`，版本字段等于`task_id`。
